"""Price feed: DexScreener (free, no key). Batch-capable."""
import time
import requests

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "fomo-dagou/0.1"})


def get_prices(mints):
    """Return {mint: price_usd}. Missing/failed mints are omitted."""
    out = {}
    mints = [m for m in dict.fromkeys(mints) if m]
    for i in range(0, len(mints), 30):
        chunk = mints[i:i + 30]
        try:
            r = _SESSION.get(
                "https://api.dexscreener.com/latest/dex/tokens/" + ",".join(chunk),
                timeout=20,
            )
            r.raise_for_status()
            pairs = r.json().get("pairs") or []
        except Exception:
            continue
        best = {}
        for p in pairs:
            base = (p.get("baseToken") or {}).get("address")
            if not base:
                continue
            try:
                liq = float((p.get("liquidity") or {}).get("usd") or 0)
                price = float(p.get("priceUsd") or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if base not in best or liq > best[base][1]:
                best[base] = (price, liq)
        for mint, (price, _liq) in best.items():
            out[mint] = price
        time.sleep(0.3)
    return out
