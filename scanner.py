"""自动发现热门币 (只读, 不下单).

流程: DexScreener boosts(top) -> solana 过滤 -> pair详情(enrich)
     -> 流动性/买卖盘/年龄过滤 -> RugCheck 安全检查 -> 按流动性排序取前5.

买入动作不在这里, 在 auto.py (纸面专用).
"""
import time

import requests

import config

UA = {"User-Agent": "fomo-dagou-scanner/1.0"}
BOOSTS_URL = "https://api.dexscreener.com/token-boosts/top/v1"


def _get(url, timeout=15):
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


def top_boosts(limit=15):
    """取 DexScreener 热门助推榜的 solana mint 列表."""
    data = _get(BOOSTS_URL)
    out = []
    for b in data:
        if b.get("chainId") == "solana" and b.get("tokenAddress"):
            out.append(b["tokenAddress"])
        if len(out) >= limit:
            break
    return out


def enrich(mint):
    """拉 pair 详情并做基础过滤, 通过返回 dict, 不通过返回 None."""
    data = _get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    pairs = [p for p in (data.get("pairs") or []) if p.get("chainId") == "solana"]
    if not pairs:
        return None
    p = max(pairs, key=lambda x: ((x.get("liquidity") or {}).get("usd") or 0))
    liq = ((p.get("liquidity") or {}).get("usd")) or 0
    if liq < config.MIN_LIQ_USD:
        return None
    tx = ((p.get("txns") or {}).get("h24")) or {}
    buys, sells = tx.get("buys") or 0, tx.get("sells") or 0
    if buys < config.MIN_BUYS_24H or sells < config.MIN_SELLS_24H:
        return None
    created = p.get("pairCreatedAt") or 0
    age_h = (time.time() * 1000 - created) / 3600e3 if created else 1e9
    if age_h > config.MAX_PAIR_AGE_H:
        return None
    price = float(p.get("priceUsd") or 0)
    if price <= 0:
        return None
    base = p.get("baseToken") or {}
    return {"mint": mint,
            "symbol": base.get("symbol") or mint[:6],
            "price": price, "liq": liq, "fdv": p.get("fdv"),
            "buys": buys, "sells": sells, "age_h": round(age_h, 1)}


def rugcheck_ok(mint):
    """RugCheck 安全检查. danger/不可达 -> 不通过 (fail-closed).
    成功时同时返回完整 report, 供持仓集中度分析复用."""
    try:
        r = _get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", timeout=20)
    except Exception:
        return False, "rugcheck unreachable", None
    risks = r.get("risks") or []
    bad = [x for x in risks if str(x.get("level", "")).lower() == "danger"]
    if bad:
        return False, f"danger: {bad[0].get('name', '?')}", None
    return True, f"risks={len(risks)}", r


def holder_concentration(report):
    """前10持仓占比 (排除LP池金库地址). 返回 (pct, 排除的LP数).
    拿不到持仓数据 -> (None, n), 调用方应跳过 (fail-closed)."""
    lp_addrs = set()
    for m in report.get("markets") or []:
        for k in ("liquidityA", "liquidityB"):
            if m.get(k):
                lp_addrs.add(m[k])
    pct, n, excluded = 0.0, 0, 0
    for h in report.get("topHolders") or []:
        if h.get("address") in lp_addrs:
            excluded += 1
            continue
        pct += float(h.get("pct") or 0)
        n += 1
        if n >= 10:
            break
    if n == 0:
        return None, excluded
    return round(pct, 2), excluded


def scan(limit=5):
    """返回最多 limit 个候选 [{mint, symbol, price, ...}], 按流动性排序."""
    cands = []
    for mint in top_boosts(limit=15):
        try:
            info = enrich(mint)
        except Exception:
            continue
        if not info:
            continue
        try:
            ok, note, report = rugcheck_ok(mint)
        except Exception:
            continue
        if not ok:
            continue
        top10, _nlp = holder_concentration(report)
        if top10 is None or top10 > config.TOP10_MAX_PCT:
            continue  # 筹码太集中, 跳过
        info["safety"] = note
        info["top10_pct"] = top10
        cands.append(info)
        if len(cands) >= limit:
            break
    cands.sort(key=lambda c: c["liq"], reverse=True)
    return cands[:limit]
