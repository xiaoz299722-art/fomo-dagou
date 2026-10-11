"""Print a rolling 24-hour paper-experiment report from persisted state."""
import json
import time
from datetime import datetime

import config
import pricefeed


def stamp(ts):
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def main():
    with open(config.STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
    now = time.time()
    cutoff = now - 86400
    points = state.get("equity_curve", [])
    before = [p for p in points if p[0] <= cutoff]
    after = [p for p in points if p[0] > cutoff]
    if before and after:
        start = before[-1]
    elif points:
        start = points[0]
    else:
        start = [now, config.VIRTUAL_BANKROLL_USD]
    end = points[-1] if points else [now, config.VIRTUAL_BANKROLL_USD]

    buys = [e for e in state.get("events", [])
            if e.get("type") == "auto_buy" and e.get("ts", 0) >= cutoff]
    sells = [t for t in state.get("trades", [])
             if t.get("source") == "auto" and t.get("ts", 0) >= cutoff]
    positions = state.get("positions", {})
    open_auto = [(mint, p) for mint, p in positions.items()
                 if p.get("source") == "auto" and not p.get("closed")]
    prices = pricefeed.get_prices([mint for mint, _ in open_auto]) if open_auto else {}
    cash = float(state.get("virtual_cash", config.VIRTUAL_BANKROLL_USD))
    unreal = sum(float(p.get("amount", 0)) * (prices.get(mint) or 0)
                 for mint, p in open_auto)
    equity = cash + unreal
    delta = equity - start[1]

    print("FOMO 打狗纸面实验日报（仅虚拟数据）")
    print(f"统计区间：{stamp(start[0])} — {stamp(now)}")
    print(f"虚拟资金：可用现金 ${cash:.2f}；当前总权益约 ${equity:.2f}；"
          f"区间权益变化约 ${delta:+.2f}（区间起点 ${start[1]:.2f}）")
    print("自动买入：")
    if buys:
        for e in buys:
            print(f"- {e.get('symbol','?')}：${float(e.get('cost_usd',0)):.2f}，"
                  f"前10持仓占比 {float(e.get('top10_pct',0)):.2f}% ，"
                  f"时间 {stamp(e['ts'])}")
    else:
        print("- 无")
    print("当前自动持仓（买入时前10持仓占比）：")
    if open_auto:
        for mint, p in open_auto:
            px = prices.get(mint)
            value = float(p.get("amount", 0)) * px if px else None
            value_text = f"，现值约 ${value:.2f}" if value is not None else "，现价暂不可用"
            print(f"- {p.get('symbol','?')}：{float(p.get('top10_pct',0)):.2f}%{value_text}")
    else:
        print("- 无")
    print("触发的自动卖出规则：")
    if sells:
        for t in sells:
            print(f"- {stamp(t['ts'])} {t.get('symbol','?')}：{t.get('reason','未知规则')}，"
                  f"纸面回收 ${float(t.get('proceeds_usd',0)):.2f}")
    else:
        print("- 无")


if __name__ == "__main__":
    main()
