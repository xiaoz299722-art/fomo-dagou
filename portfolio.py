"""Portfolio persistence and paper fills."""
import json
import os
import time

import config
from strategy import PositionState, Cfg, evaluate


def _cfg():
    return Cfg(r1_mult=config.R1_MULT, r1_pct=config.R1_PCT,
               r4_mult=config.R4_MULT, r4_pct=config.R4_PCT,
               stop_mult=config.STOP_MULT, trail_start=config.TRAIL_START_MULT,
               trail_retrace=config.TRAIL_RETRACE)


class Portfolio:
    def __init__(self, slippage_bps=None):
        self.slippage = (slippage_bps if slippage_bps is not None
                         else config.SLIPPAGE_BPS) / 10000.0
        self.positions = {}
        self.trades = []
        self.events = []
        self.equity_curve = []
        self.virtual_cash = config.VIRTUAL_BANKROLL_USD
        self._last_snapshot_at = 0.0
        self.load()

    def save(self):
        path = os.path.abspath(config.STATE_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        payload = {
            "positions": {k: vars(v) for k, v in self.positions.items()},
            "trades": self.trades[-10000:],
            "events": self.events[-10000:],
            "equity_curve": self.equity_curve[-5000:],
            "virtual_cash": self.virtual_cash,
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def load(self):
        try:
            with open(config.STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.get("positions", {}).items():
                self.positions[k] = PositionState(**v)
            self.trades = data.get("trades", [])
            self.events = data.get("events", [])
            self.equity_curve = data.get("equity_curve", [])
            if "virtual_cash" in data:
                self.virtual_cash = float(data["virtual_cash"])
            if self.equity_curve:
                self._last_snapshot_at = float(self.equity_curve[-1][0])
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, TypeError, ValueError):
            raise RuntimeError(f"无法读取有效的纸面状态文件: {config.STATE_FILE}")

    def add_position(self, mint, symbol, entry_price, amount_tokens,
                     source="manual", cost_usd=0.0, top10_pct=0.0):
        if mint in self.positions and not self.positions[mint].closed:
            return False, "position already open for this mint"
        self.positions[mint] = PositionState(
            mint=mint, symbol=symbol, entry_price=entry_price,
            initial_amount=amount_tokens, amount=amount_tokens,
            opened_at=time.time(), source=source, cost_usd=cost_usd,
            top10_pct=top10_pct)
        self.save()
        return True, "ok"

    def add_auto_position(self, candidate, cost_usd):
        """Atomically record one simulated auto-buy and debit virtual cash."""
        mint = candidate["mint"]
        if mint in self.positions and not self.positions[mint].closed:
            return False, "position already open for this mint"
        if self.virtual_cash < cost_usd:
            return False, "insufficient virtual cash"
        price = float(candidate["price"])
        if price <= 0:
            return False, "invalid candidate price"
        amount = cost_usd / price
        pos = PositionState(
            mint=mint, symbol=candidate["symbol"], entry_price=price,
            initial_amount=amount, amount=amount, opened_at=time.time(),
            source="auto", cost_usd=cost_usd,
            top10_pct=float(candidate.get("top10_pct") or 0))
        event = {"type": "auto_buy", "ts": time.time(),
                 "mint": mint, "symbol": candidate["symbol"],
                 "price": price, "tokens": amount, "cost_usd": cost_usd,
                 "top10_pct": pos.top10_pct, "liq_usd": candidate.get("liq"),
                 "mode": "paper"}
        self.positions[mint] = pos
        self.virtual_cash = round(self.virtual_cash - cost_usd, 2)
        self.events.append(event)
        try:
            self.save()
        except Exception:
            self.positions.pop(mint, None)
            self.virtual_cash = round(self.virtual_cash + cost_usd, 2)
            self.events.pop()
            raise
        return True, "ok"

    def open_mints(self):
        return [m for m, p in self.positions.items() if not p.closed]

    def on_tick(self, prices, executor=None):
        """Evaluate holdings and record simulated sell fills only."""
        cfg = _cfg()
        for mint, pos in list(self.positions.items()):
            if pos.closed:
                continue
            price = prices.get(mint)
            if not price:
                continue
            for act in evaluate(pos, price, cfg):
                sell_tokens = pos.initial_amount * act.pct_of_original
                if act.kind == "close":
                    sell_tokens = pos.amount
                sell_tokens = min(sell_tokens, pos.amount)
                if sell_tokens <= 0:
                    continue
                fill = price * (1 - self.slippage)
                proceeds = sell_tokens * fill
                pos.amount -= sell_tokens
                pos.realized_usd += proceeds
                if pos.source == "auto":
                    self.virtual_cash = round(self.virtual_cash + proceeds, 2)
                if act.kind == "close" or pos.amount <= 1e-12:
                    pos.closed = True
                trade = {"mint": mint, "symbol": pos.symbol, "ts": time.time(),
                         "price": price, "fill": round(fill, 8),
                         "tokens": round(sell_tokens, 8),
                         "proceeds_usd": round(proceeds, 2),
                         "reason": act.reason, "mode": "paper",
                         "source": pos.source}
                self.trades.append(trade)
                if pos.source == "auto":
                    self.events.append({"type": "auto_sell", **trade})
                print(f"[{time.strftime('%H:%M:%S')}] {pos.symbol} {act.reason} "
                      f"卖出{round(sell_tokens, 2)}枚 ≈${proceeds:.2f}")
        self._snapshot(prices)
        self.save()

    def _snapshot(self, prices):
        now = time.time()
        if self._last_snapshot_at and now - self._last_snapshot_at < 60:
            return
        auto_unreal = sum(
            p.amount * (prices.get(mint) or 0)
            for mint, p in self.positions.items()
            if p.source == "auto" and not p.closed
        )
        total = round(self.virtual_cash + auto_unreal, 2)
        self.equity_curve.append([now, total])
        self.equity_curve = self.equity_curve[-5000:]
        self._last_snapshot_at = now

    def stats(self, prices=None):
        prices = prices or {}
        auto_open = [p for p in self.positions.values()
                     if not p.closed and p.source == "auto"]
        unreal = sum(p.amount * (prices.get(p.mint) or 0) for p in auto_open)
        equity = round(self.virtual_cash + unreal, 2)
        return {"mode": "paper",
                "open_positions": len(self.open_mints()),
                "closed_actions": len(self.trades),
                "realized_usd": round(sum(t["proceeds_usd"] for t in self.trades), 2),
                "virtual_cash": round(self.virtual_cash, 2),
                "virtual_equity_usd": equity,
                "virtual_pnl_usd": round(equity - config.VIRTUAL_BANKROLL_USD, 2),
                "auto_open": len(auto_open),
                "auto_bankroll": round(config.VIRTUAL_BANKROLL_USD, 2)}

    def position_rows(self, prices):
        rows = []
        for mint, p in self.positions.items():
            if p.closed:
                continue
            px = prices.get(mint, 0) or 0
            m = px / p.entry_price if p.entry_price else 0
            rows.append({"mint": mint, "symbol": p.symbol,
                         "entry": p.entry_price, "price": px,
                         "mult": round(m, 3), "peak": round(p.peak_mult, 3),
                         "remaining": round(p.amount, 2),
                         "sold_pct": round((1 - p.amount / p.initial_amount) * 100, 1)
                         if p.initial_amount else 0,
                         "r1": p.r1_fired, "r4": p.r4_fired,
                         "source": p.source, "top10_pct": p.top10_pct,
                         "next_trigger": self._next_trigger(p, m)})
        return rows

    @staticmethod
    def _next_trigger(p, m):
        if m <= config.STOP_MULT:
            return "止损"
        if p.peak_mult >= config.TRAIL_START_MULT:
            t = p.peak_mult * (1 - config.TRAIL_RETRACE)
            return f"回撤到{t:.2f}x清仓"
        if not p.r1_fired:
            return f"到{config.R1_MULT}x卖50%"
        if not p.r4_fired:
            return f"到{config.R4_MULT}x卖30%"
        return "持有等20%博高倍"
