"""Paper-only automatic discovery and simulated buys."""
import time

import config
import scanner

_last_scan = 0.0


def _auto_open(pf):
    return [p for p in pf.positions.values()
            if not p.closed and p.source == "auto"]


def maybe_autobuy(pf):
    """Scan and simulate buys; return bought candidate records."""
    global _last_scan
    if config.MODE != "paper" or not config.AUTO_BUY:
        return []
    now = time.time()
    if now - _last_scan < config.SCAN_INTERVAL_SEC:
        return []
    _last_scan = now

    if len(_auto_open(pf)) >= config.MAX_AUTO_POSITIONS:
        return []
    if pf.virtual_cash < config.AUTO_TRADE_USD:
        print(f"[auto] 虚拟资金不足 ${pf.virtual_cash:.2f}, 跳过本轮")
        return []

    held = {p.mint for p in pf.positions.values() if not p.closed}
    bought = []
    try:
        cands = scanner.scan(limit=config.MAX_AUTO_POSITIONS)
    except Exception as e:  # noqa: BLE001
        print(f"[auto] 扫描失败: {e}")
        return []
    for c in cands:
        if len(_auto_open(pf)) >= config.MAX_AUTO_POSITIONS:
            break
        if pf.virtual_cash < config.AUTO_TRADE_USD:
            break
        if c["mint"] in held:
            continue
        top10 = float(c.get("top10_pct") or 0)
        ok, reason = pf.add_auto_position(c, config.AUTO_TRADE_USD)
        if ok:
            held.add(c["mint"])
            bought.append(c)
            print(f"[auto] 纸面买入 {c['symbol']} ${config.AUTO_TRADE_USD:.0f} "
                  f"@{c['price']:.8f} (liq ${c['liq']:.0f}, "
                  f"top10 {top10}%, {c['safety']})")
        else:
            print(f"[auto] 跳过 {c['symbol']}: {reason}")
    return bought
