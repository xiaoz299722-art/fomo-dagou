"""Paper-only FOMO strategy runner and authenticated dashboard."""
import argparse
import os
import threading
import time

import config
import pricefeed
from portfolio import Portfolio


def tick_once(pf, prices=None):
    mints = pf.open_mints()
    prices = pricefeed.get_prices(mints) if mints else {}
    pf.on_tick(prices)
    return prices


def loop(pf, price_cache, lock, auto=False):
    while True:
        try:
            if os.path.exists(config.KILL_SWITCH_FILE):
                print("kill-switch engaged, stopping")
                break
            prices = pricefeed.get_prices(pf.open_mints())
            with lock:
                price_cache.clear()
                price_cache.update(prices)
                pf.on_tick(prices)
                if auto:
                    import auto as auto_mod
                    auto_mod.maybe_autobuy(pf)
            st = pf.stats(price_cache)
            print(f"[{time.strftime('%H:%M:%S')}] 持仓{st['open_positions']} "
                  f"(自动{st['auto_open']}) 虚拟现金${st['virtual_cash']} "
                  f"虚拟总权益${st['virtual_equity_usd']} 动作{st['closed_actions']}")
        except Exception as e:  # noqa: BLE001 - loop must survive transient errors
            print(f"loop error: {e}")
        time.sleep(config.POLL_SEC)


def _serve_dashboard(pf, cache, lock):
    from dashboard import create_app
    from waitress import serve
    app = create_app(pf, cache, lock, {
        "r1_mult": config.R1_MULT, "r4_mult": config.R4_MULT,
        "stop_mult": config.STOP_MULT, "trail_start": config.TRAIL_START_MULT,
        "trail_retrace": config.TRAIL_RETRACE})
    print(f"认证看板已启动: http://0.0.0.0:{config.DASHBOARD_PORT} (模式 paper)", flush=True)
    serve(app, host="0.0.0.0", port=config.DASHBOARD_PORT, threads=6)


def cmd_check():
    pf = Portfolio()
    if not pf.open_mints():
        print("无持仓。自动发现实验需运行 paper-auto。")
        return
    prices = tick_once(pf)
    for r in pf.position_rows(prices):
        print(f"{r['symbol']}: {r['mult']}x (峰值{r['peak']}x) 已卖{r['sold_pct']}% -> {r['next_trigger']}")


def cmd_paper():
    pf = Portfolio()
    cache, lock = {}, threading.Lock()
    loop(pf, cache, lock)


def cmd_paper_auto():
    if config.MODE != "paper":
        raise RuntimeError("paper-only deployment mode required")
    config.AUTO_BUY = True
    print(f"纸面自动实验启动: 虚拟本金${config.VIRTUAL_BANKROLL_USD:.0f}, "
          f"每笔${config.AUTO_TRADE_USD:.0f}, 最多{config.MAX_AUTO_POSITIONS}个自动仓, "
          f"每{config.SCAN_INTERVAL_SEC // 60}分钟扫描一次。", flush=True)
    print("无实盘执行器、无私钥读取；所有买卖只记入纸面状态。", flush=True)
    pf = Portfolio()
    cache, lock = {}, threading.Lock()
    worker = threading.Thread(target=loop, args=(pf, cache, lock),
                              kwargs={"auto": True}, daemon=True,
                              name="paper-auto-loop")
    worker.start()
    _serve_dashboard(pf, cache, lock)


def cmd_dashboard():
    pf = Portfolio()
    cache, lock = {}, threading.Lock()
    worker = threading.Thread(target=loop, args=(pf, cache, lock),
                              daemon=True, name="price-loop")
    worker.start()
    _serve_dashboard(pf, cache, lock)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "paper", "paper-auto", "dashboard"])
    args = ap.parse_args()
    print("模式: paper (实盘执行器已移除)", flush=True)
    {"check": cmd_check, "paper": cmd_paper,
     "paper-auto": cmd_paper_auto, "dashboard": cmd_dashboard}[args.cmd]()
