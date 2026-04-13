"""
Phase 1: Find Qualifying Tokens
Discovers Solana meme tokens with breakout patterns.
Winners: 10x+ from quiet period. Losers: 2-5x pump then 80%+ retrace.
"""
import os
import json
import csv
import time
import requests
import statistics
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

BIRDEYE_KEY = os.getenv("BIRDEYE_API_KEY")
BIRDEYE_BASE = "https://public-api.birdeye.so"
BIRDEYE_HEADERS = {"X-API-KEY": BIRDEYE_KEY, "x-chain": "solana"}
os.makedirs("data", exist_ok=True)

last_call = 0
def api_get(url, headers=None, params=None, timeout=30):
    global last_call
    wait = 0.6 - (time.time() - last_call)
    if wait > 0: time.sleep(wait)
    last_call = time.time()
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            return r
        except:
            time.sleep(2)
    return None

def get_ohlcv(addr, t_from, t_to, bar="1m"):
    """Fetch OHLCV with pagination. API returns up to 5000 bars per call."""
    all_bars = []
    # Chunk sizes based on bar type and 5000 bar limit
    chunks = {"1m": 300000, "5m": 1500000, "15m": 4500000, "30m": 9000000}
    chunk = chunks.get(bar, 300000)
    cur = t_from
    while cur < t_to:
        end = min(cur + chunk, t_to)
        r = api_get(f"{BIRDEYE_BASE}/defi/v3/ohlcv", headers=BIRDEYE_HEADERS,
                   params={"address": addr, "type": bar, "time_from": cur, "time_to": end})
        if r and r.status_code == 200:
            items = r.json().get("data", {}).get("items", [])
            all_bars.extend(items)
        cur = end
    # Dedup + sort
    seen = set()
    out = []
    for b in all_bars:
        t = b.get("unix_time", 0)
        if t and t not in seen:
            seen.add(t)
            out.append(b)
    out.sort(key=lambda x: x.get("unix_time", 0))
    return out

def bt(bar):
    """Get bar time."""
    return bar.get("unix_time", 0)

def find_spikes_30m(bars, min_prior=4):
    """Find volume spikes in 30m data. min_prior=4 means 2 hours of prior data."""
    spikes = []
    for i in range(min_prior, len(bars)):
        prior_vols = [b.get("v", 0) or 0 for b in bars[i-min_prior:i]]
        nz = [v for v in prior_vols if v > 0]
        if len(nz) < 2: continue
        med = statistics.median(nz)
        if med <= 0: continue
        cv = bars[i].get("v", 0) or 0
        ratio = cv / med
        if ratio > 2.5:
            spikes.append({"time": bt(bars[i]), "ratio": ratio, "close": bars[i].get("c", 0)})
    # Deduplicate: keep strongest per 4-hour window
    spikes.sort(key=lambda x: x["ratio"], reverse=True)
    kept = []
    for s in spikes:
        if all(abs(s["time"] - k["time"]) > 14400 for k in kept):
            kept.append(s)
        if len(kept) >= 8: break
    return kept

def find_breakout_1m(bars, min_quiet=20):
    """Find breakout in 1m bars. Returns breakout info or None."""
    if len(bars) < min_quiet + 10:
        return None
    for i in range(min_quiet, len(bars)):
        prior = bars[i-min_quiet:i]
        pvols = [b.get("v", 0) or 0 for b in prior]
        pcloses = [b.get("c", 0) or 0 for b in prior]
        nzv = [v for v in pvols if v > 0]
        nzc = [c for c in pcloses if c > 0]
        if len(nzv) < min_quiet * 0.4 or not nzc: continue
        med_vol = statistics.median(nzv)
        max_close = max(nzc)
        if med_vol <= 0 or max_close <= 0: continue
        cv = bars[i].get("v", 0) or 0
        cc = bars[i].get("c", 0) or 0
        if cv > 2.5 * med_vol and cc > max_close:
            return {
                "index": i,
                "quiet_median_price": statistics.median(nzc),
                "quiet_median_volume": med_vol,
                "breakout_time": bt(bars[i]),
                "breakout_close": cc
            }
    return None

def classify(bars, bk):
    """Classify token post-breakout as winner or loser."""
    idx, qp = bk["index"], bk["quiet_median_price"]
    if qp <= 0: return None
    post = bars[idx:idx+360]
    if len(post) < 30: return None

    peak, pidx = 0, 0
    for j, b in enumerate(post):
        h = b.get("h", 0) or 0
        if h > peak: peak, pidx = h, j
    mult = peak / qp

    # Winner: 5x+ sustained (relaxed from 10x to increase yield)
    if mult >= 5:
        above_3x = sum(1 for b in post if (b.get("c",0) or 0) >= qp*3)
        if above_3x >= 15:
            return {"label": "winner", "peak_price": peak, "multiplier": mult,
                    "peak_bar_index": pidx, "sustained_bars": above_3x}

    # Loser: 1.5x+ then 70%+ retrace
    if mult >= 1.5 and pidx < len(post) - 10:
        pp = post[pidx:]
        closes = [b.get("c",0) or 0 for b in pp if b.get("c",0)]
        if closes:
            mn = min(closes)
            move = peak - qp
            ret = (peak - mn) / move if move > 0 else 0
            if ret >= 0.70:
                return {"label": "loser", "peak_price": peak, "multiplier": mult,
                        "peak_bar_index": pidx, "retrace_pct": ret}
    return None

def process_token(addr):
    """Process one token: scan 30m bars for 90 days, zoom into spikes with 1m."""
    now = int(time.time())
    start = now - 90 * 86400

    # Step 1: Get 30m bars for full range (should be ~4320 bars, under 5000 limit)
    bars_30m = get_ohlcv(addr, start, now, bar="30m")
    if len(bars_30m) < 10:
        return [], f"Too few 30m bars ({len(bars_30m)})"

    # Step 2: Find volume spikes
    spikes = find_spikes_30m(bars_30m)
    if not spikes:
        return [], "No volume spikes"

    results = []
    for spike in spikes:
        st = spike["time"]
        # Step 3: Get 1m data around spike (2h before + 6h after = 480 min)
        bars_1m = get_ohlcv(addr, st - 7200, st + 21600, bar="1m")
        if len(bars_1m) < 50: continue

        # Check trading history before breakout
        first_t = bt(bars_1m[0]) if bars_1m else 0
        if st - first_t < 1200:  # Less than 20 min of pre-data
            # Check for earlier trading
            earlier = get_ohlcv(addr, st - 14400, st - 7200, bar="1m")
            if len(earlier) < 10: continue

        bk = find_breakout_1m(bars_1m)
        if not bk: continue

        cl = classify(bars_1m, bk)
        if not cl: continue

        bi = bk["index"]
        results.append({
            "address": addr,
            "label": cl["label"],
            "breakout_timestamp": bk["breakout_time"],
            "quiet_period_median_price": bk["quiet_median_price"],
            "peak_price": cl["peak_price"],
            "multiplier": cl["multiplier"],
            "pre_breakout_bars": bars_1m[max(0,bi-120):bi],
            "post_breakout_bars": bars_1m[bi:bi+360],
            "pre_breakout_minutes": len(bars_1m[max(0,bi-120):bi]),
            "post_breakout_minutes": len(bars_1m[bi:bi+360]),
            "classification_details": cl
        })
    return results, None if results else ([], "No qualifying breakouts")

def discover_candidates():
    """Discover tokens from Birdeye and DexScreener."""
    addrs = []
    # Known tokens
    known = [
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
        "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
        "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",  # POPCAT
        "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5",   # MEW
        "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82",   # BOME
        "7BgBvyjrZX1YKz4oh9mjb8ZScatkkwb8DzFx7LoiVkM3",   # SLERF
        "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",   # TRUMP
        "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",   # FARTCOIN
        "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",   # GOAT
        "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump",   # PNUT
        "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY",   # MOODENG
        "Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump",   # CHILLGUY
        "HhJpBhRRn4g56VsyLuT8DL5Bv31HkXqsrahTTUCZeZg4",   # MYRO
        "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",   # SAMO
        "5z3EqYQo9HiCEs3R84RCDMu2n7anpDMxRhdK8PSWmrRC",   # PONKE
        "63LfDmNb3MQ8mw9MtZ2To9bEA2M71kZUUGq5tiJxcqj9",   # GIGA
        "3psH1Mj1f7yUfaD5gh6Zj7epE8hhrMkMETgv5TshQA4o",   # BODEN
        "FU1q8vJpZNUrmqsciSjp8bAKKidGsLmouB8CBdf8TKQv",   # TREMP
        "6ogzHhzdrQr9Pgv6hZ2MNze7UrzBMAFyBBWUYp1Fhitx",   # RETARDIO
        "HeLp6NuQkmYB4pYWo2zYs22mESHXPQYzXbB8n4V98jwC",   # AI16Z
        "FeR8VBqNRSUD5NtXAj2n3j1dAHkZHfyDktKuLXD4pump",   # JELLYJELLY
    ]
    addrs.extend(known)
    print(f"Known: {len(known)}")

    # Birdeye token list — many pages, multiple sort criteria
    print("Birdeye token list...", flush=True)
    for sort in ["volume_24h_change_percent", "volume_24h_usd", "price_change_24h_percent"]:
        for offset in range(0, 500, 50):
            r = api_get(f"{BIRDEYE_BASE}/defi/v3/token/list", headers=BIRDEYE_HEADERS,
                       params={"sort_by": sort, "sort_type": "desc", "offset": offset,
                              "limit": 50, "min_liquidity": 1000})
            if r and r.status_code == 200:
                for item in r.json().get("data", {}).get("items", []):
                    a = item.get("address")
                    if a and a not in addrs: addrs.append(a)
    print(f"  After Birdeye list: {len(addrs)}")

    # Birdeye trending
    r = api_get(f"{BIRDEYE_BASE}/defi/token_trending", headers=BIRDEYE_HEADERS,
               params={"sort_by": "rank", "sort_type": "asc", "offset": 0, "limit": 20})
    if r and r.status_code == 200:
        for t in r.json().get("data", {}).get("tokens", []):
            a = t.get("address")
            if a and a not in addrs: addrs.append(a)

    # DexScreener
    print("DexScreener search...", flush=True)
    for kw in ["solana meme", "pump sol", "bonk wif popcat", "fartcoin goat pnut",
               "moodeng chillguy retardio", "pepe doge cat sol", "trump melania sol",
               "ai sol crypto", "gigachad ponke sol", "vine sol meme",
               "solana moonshot", "sol trending", "solana 100x",
               "neet frog sol", "comedian ban sol", "pippin sol",
               "sol gem new", "sol pump fun graduated"]:
        try:
            r = requests.get("https://api.dexscreener.com/latest/dex/search",
                           params={"q": kw}, timeout=15)
            if r and r.status_code == 200:
                for p in r.json().get("pairs", []):
                    if p.get("chainId") == "solana":
                        a = p.get("baseToken", {}).get("address")
                        if a and a not in addrs: addrs.append(a)
            time.sleep(0.3)
        except: pass
    print(f"  After DexScreener: {len(addrs)}")

    # Also get DexScreener boosted tokens
    try:
        r = requests.get("https://api.dexscreener.com/token-boosts/top/v1", timeout=15)
        if r and r.status_code == 200:
            for item in r.json():
                if item.get("chainId") == "solana":
                    a = item.get("tokenAddress")
                    if a and a not in addrs: addrs.append(a)
    except: pass

    print(f"Total candidates: {len(addrs)}")
    return addrs

def main():
    print(f"Phase 1: Token Collection — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    winners, losers, rejected, manifest = [], [], [], []
    seen = set()

    candidates = discover_candidates()

    print(f"\n--- Processing {len(candidates)} candidates ---")
    for i, addr in enumerate(candidates):
        if len(winners) >= 50 and len(losers) >= 50:
            print("\nTarget reached (50+50). Done.")
            break

        print(f"[{i+1}/{len(candidates)}] {addr[:16]}...", end=" ", flush=True)

        try:
            results, err = process_token(addr)
        except Exception as e:
            err = f"Exception: {e}"
            results = []

        if not results:
            reason = err if err else "no results"
            print(f"SKIP: {reason}")
            rejected.append({"address": addr, "reason": reason})
            continue

        for r in results:
            key = f"{r['address']}_{r['breakout_timestamp']}"
            if key in seen: continue
            seen.add(key)

            lbl = r["label"]
            if lbl == "winner" and len(winners) < 50:
                winners.append(r)
                print(f"W#{len(winners)}({r['multiplier']:.1f}x)", end=" ", flush=True)
            elif lbl == "loser" and len(losers) < 50:
                losers.append(r)
                d = r.get("classification_details", {})
                print(f"L#{len(losers)}({r['multiplier']:.1f}x,{d.get('retrace_pct',0)*100:.0f}%ret)", end=" ", flush=True)

            manifest.append({
                "token_address": r["address"], "label": r["label"],
                "breakout_timestamp": r["breakout_timestamp"],
                "quiet_period_median_price": r["quiet_period_median_price"],
                "peak_price": r["peak_price"], "multiplier": r["multiplier"],
                "data_source": "birdeye",
                "pre_breakout_minutes": r["pre_breakout_minutes"],
                "post_breakout_minutes": r["post_breakout_minutes"]
            })
        print()

        if (i+1) % 25 == 0:
            print(f"--- Progress: {len(winners)}W / {len(losers)}L / {len(rejected)}R after {i+1} tokens ---")

    # Save
    print(f"\n--- Saving: {len(winners)}W, {len(losers)}L, {len(rejected)}R ---")
    with open("data/winners.json", "w") as f: json.dump(winners, f, indent=2)
    with open("data/losers.json", "w") as f: json.dump(losers, f, indent=2)
    if rejected:
        with open("data/rejected_tokens.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["address", "reason"])
            w.writeheader()
            w.writerows(rejected)
    if manifest:
        with open("data/manifest.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "token_address", "label", "breakout_timestamp",
                "quiet_period_median_price", "peak_price", "multiplier",
                "data_source", "pre_breakout_minutes", "post_breakout_minutes"
            ])
            w.writeheader()
            w.writerows(manifest)

    print(f"\nPHASE 1 DONE: {len(winners)} winners, {len(losers)} losers")
    return len(winners), len(losers)

if __name__ == "__main__":
    main()
