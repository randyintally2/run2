"""
Phase 2: Feature Engineering
For each token, compute features using ONLY the first 15 minutes after breakout.
Features compare breakout behavior to the quiet baseline period.
"""
import os
import json
import csv
import statistics
from datetime import datetime, timezone

os.makedirs("data", exist_ok=True)


def load_data():
    with open("data/winners.json") as f:
        winners = json.load(f)
    with open("data/losers.json") as f:
        losers = json.load(f)
    print(f"Loaded {len(winners)} winners, {len(losers)} losers")
    return winners, losers


def safe_median(values):
    """Median of non-zero positive values, or 0 if empty."""
    filtered = [v for v in values if v and v > 0]
    return statistics.median(filtered) if filtered else 0


def safe_slope(values):
    """Simple linear regression slope over a list of values."""
    n = len(values)
    if n < 2:
        return 0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0


def compute_features(token):
    """Compute all features for a single token."""
    pre_bars = token["pre_breakout_bars"]
    post_bars = token["post_breakout_bars"]
    quiet_med_price = token["quiet_period_median_price"]

    # Use the last 30 bars of pre-breakout as the quiet/baseline period
    baseline = pre_bars[-30:] if len(pre_bars) >= 30 else pre_bars
    # First 15 bars post-breakout
    breakout_15 = post_bars[:15]

    if not baseline or not breakout_15 or quiet_med_price <= 0:
        return None

    # Baseline volume stats
    base_vols = [b.get("v", 0) or 0 for b in baseline]
    base_nz_vols = [v for v in base_vols if v > 0]
    base_med_vol = statistics.median(base_nz_vols) if base_nz_vols else 0

    # Baseline close prices
    base_closes = [b.get("c", 0) or 0 for b in baseline]
    base_nz_closes = [c for c in base_closes if c > 0]

    # Breakout volumes and prices
    bk_vols = [b.get("v", 0) or 0 for b in breakout_15]
    bk_closes = [b.get("c", 0) or 0 for b in breakout_15]
    bk_lows = [b.get("l", 0) or 0 for b in breakout_15]
    bk_highs = [b.get("h", 0) or 0 for b in breakout_15]

    if base_med_vol <= 0:
        return None

    features = {}

    # === VOLUME FEATURES ===

    # vol_ratio_vs_baseline: avg breakout volume / baseline median volume
    bk_avg_vol = sum(bk_vols) / len(bk_vols) if bk_vols else 0
    features["vol_ratio_vs_baseline"] = bk_avg_vol / base_med_vol if base_med_vol > 0 else 0

    # vol_acceleration: slope of volume over last 5 breakout bars
    if len(bk_vols) >= 5:
        features["vol_acceleration"] = safe_slope(bk_vols[-5:])
    else:
        features["vol_acceleration"] = safe_slope(bk_vols)

    # vol_consistency: % of breakout bars with volume above baseline median
    above_baseline = sum(1 for v in bk_vols if v > base_med_vol)
    features["vol_consistency"] = above_baseline / len(bk_vols) if bk_vols else 0

    # vol_no_gap: longest consecutive streak above 2x baseline median
    streak = 0
    max_streak = 0
    for v in bk_vols:
        if v > 2 * base_med_vol:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    features["vol_no_gap"] = max_streak

    # === PRICE FEATURES ===

    # price_higher_lows: count of bars where low > previous bar's low
    higher_lows = 0
    for j in range(1, len(breakout_15)):
        cur_low = bk_lows[j] if bk_lows[j] > 0 else float('inf')
        prev_low = bk_lows[j-1] if bk_lows[j-1] > 0 else 0
        if cur_low > prev_low and prev_low > 0:
            higher_lows += 1
    features["price_higher_lows"] = higher_lows

    # price_retracement_depth: deepest pullback as % of move so far
    if bk_closes and bk_closes[0] > 0:
        running_high = bk_closes[0]
        max_retrace = 0
        for c in bk_closes:
            if c > 0:
                running_high = max(running_high, c)
                move = running_high - quiet_med_price
                if move > 0:
                    pullback = running_high - c
                    retrace_pct = pullback / move
                    max_retrace = max(max_retrace, retrace_pct)
        features["price_retracement_depth"] = max_retrace
    else:
        features["price_retracement_depth"] = 0

    # price_vs_baseline_range: current price / quiet period median (multiple)
    last_close = 0
    for c in reversed(bk_closes):
        if c > 0:
            last_close = c
            break
    features["price_vs_baseline_range"] = last_close / quiet_med_price if quiet_med_price > 0 else 0

    # price_staircase_ratio: ratio of higher-low bars to total bars
    total_price_bars = len(breakout_15) - 1  # First bar has no previous
    features["price_staircase_ratio"] = higher_lows / total_price_bars if total_price_bars > 0 else 0

    # === BASELINE COMPARISON FEATURES ===

    # volume_trend_before: slope of volume in last 30 baseline bars
    if base_nz_vols:
        features["volume_trend_before"] = safe_slope(base_vols[-30:])
    else:
        features["volume_trend_before"] = 0

    # price_trend_before: slope of price in last 30 baseline bars
    if base_nz_closes:
        features["price_trend_before"] = safe_slope(base_closes[-30:])
    else:
        features["price_trend_before"] = 0

    # === TRANSACTION FEATURES (proxy) ===

    # tx_count_vs_baseline: ratio of breakout volume bars > 0 to baseline volume bars > 0
    # (proxy for transaction count since we don't have actual tx data)
    bk_active = sum(1 for v in bk_vols if v > 0)
    base_active = sum(1 for v in base_vols if v > 0)
    base_active_rate = base_active / len(base_vols) if base_vols else 0
    bk_active_rate = bk_active / len(bk_vols) if bk_vols else 0
    features["tx_count_vs_baseline"] = bk_active_rate / base_active_rate if base_active_rate > 0 else 0

    # unique_buyer_estimate: not available from OHLCV data, use volume variance as proxy
    # High variance in volume = many different-sized trades = likely more unique buyers
    if len(bk_vols) >= 3 and any(v > 0 for v in bk_vols):
        nz_bk = [v for v in bk_vols if v > 0]
        if len(nz_bk) >= 2:
            vol_cv = statistics.stdev(nz_bk) / statistics.mean(nz_bk) if statistics.mean(nz_bk) > 0 else 0
            features["unique_buyer_estimate"] = vol_cv
        else:
            features["unique_buyer_estimate"] = 0
    else:
        features["unique_buyer_estimate"] = 0

    return features


def main():
    print(f"Phase 2: Feature Engineering — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    winners, losers = load_data()

    rows = []
    skipped = 0

    for token in winners + losers:
        features = compute_features(token)
        if features is None:
            skipped += 1
            print(f"  Skipped {token['address'][:16]}... (insufficient data)")
            continue

        row = {
            "token_address": token["address"],
            "label": token["label"],
            "breakout_timestamp": token["breakout_timestamp"],
            "quiet_period_median_price": token["quiet_period_median_price"],
        }
        row.update(features)
        rows.append(row)

    print(f"\nComputed features for {len(rows)} tokens ({skipped} skipped)")

    # Feature columns
    feature_cols = [
        "vol_ratio_vs_baseline", "vol_acceleration", "vol_consistency", "vol_no_gap",
        "price_higher_lows", "price_retracement_depth", "price_vs_baseline_range",
        "price_staircase_ratio", "volume_trend_before", "price_trend_before",
        "tx_count_vs_baseline", "unique_buyer_estimate"
    ]

    all_cols = ["token_address", "label", "breakout_timestamp", "quiet_period_median_price"] + feature_cols

    # Save CSV
    with open("data/features.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved to data/features.csv")

    # Print summary statistics
    print(f"\n{'='*60}")
    print("Feature Summary (Winner avg vs Loser avg)")
    print(f"{'Feature':<30s} {'Winner Avg':>12s} {'Loser Avg':>12s} {'Direction':>10s}")
    print("-" * 66)

    winner_rows = [r for r in rows if r["label"] == "winner"]
    loser_rows = [r for r in rows if r["label"] == "loser"]

    for feat in feature_cols:
        w_vals = [r[feat] for r in winner_rows if r[feat] is not None]
        l_vals = [r[feat] for r in loser_rows if r[feat] is not None]
        w_avg = sum(w_vals) / len(w_vals) if w_vals else 0
        l_avg = sum(l_vals) / len(l_vals) if l_vals else 0
        direction = "W>L" if w_avg > l_avg else "L>W"
        print(f"{feat:<30s} {w_avg:>12.4f} {l_avg:>12.4f} {direction:>10s}")

    print(f"\nWinners: {len(winner_rows)}, Losers: {len(loser_rows)}")


if __name__ == "__main__":
    main()
