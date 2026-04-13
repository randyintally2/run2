"""
Real-Time Early Runner Detector
Standalone script that monitors 1-minute OHLCV bars for a token and detects breakout patterns.
Designed to be plugged into a Birdeye WebSocket listener.

Usage:
    from detector import RunnerDetector
    det = RunnerDetector()
    det.feed_bar({"unix_time": ..., "o": ..., "h": ..., "l": ..., "c": ..., "v": ...})

Or run standalone with simulated bars:
    python detector.py <token_address>
"""
import math
import statistics
from collections import deque
from datetime import datetime, timezone


# === HARDCODED RULES FROM PHASE 3 TRAINING ===
# These are the scoring rules derived from 81 tokens (31 winners, 50 losers).
# Each rule checks one feature after 15 minutes of breakout activity.

RULES = [
    {
        "name": "price_vs_baseline_range",
        "description": "How far price moved from baseline (as a multiple). Log-transformed.",
        "threshold": 0.864617,    # ln(1 + value) must exceed this
        "winner_side": "high",    # Winners have HIGHER values
        "log_transform": True,
        "cohens_d": 0.938,
        "plain_english": "Price has moved more than ~1.4x above the quiet period average"
    },
    {
        "name": "vol_ratio_vs_baseline",
        "description": "Average breakout volume / baseline median volume. Log-transformed.",
        "threshold": 1.601410,    # ln(1 + value) must be BELOW this
        "winner_side": "low",     # Winners have LOWER volume ratio (pump-and-dumps spike harder)
        "log_transform": True,
        "cohens_d": -0.598,
        "plain_english": "Volume is elevated but not insanely spiked (under ~4x baseline)"
    },
    {
        "name": "vol_consistency",
        "description": "Fraction of bars with volume above baseline median. Log-transformed.",
        "threshold": 0.470004,
        "winner_side": "low",     # Winners have LOWER consistency (organic = varied, pump = artificially consistent)
        "log_transform": True,
        "cohens_d": -0.514,
        "plain_english": "Not every single bar has above-average volume (organic buying is lumpy)"
    },
    {
        "name": "price_retracement_depth",
        "description": "Deepest pullback as fraction of the move. Log-transformed.",
        "threshold": 0.406471,
        "winner_side": "low",     # Winners retrace LESS
        "log_transform": True,
        "cohens_d": -0.367,
        "plain_english": "Price hasn't pulled back more than ~50% of the move (shallow dips = strong)"
    },
    {
        "name": "vol_no_gap",
        "description": "Longest streak of bars above 2x baseline volume. Log-transformed.",
        "threshold": 1.386294,
        "winner_side": "low",     # Winners have SHORTER streaks (organic = episodic, pump = sustained blast)
        "log_transform": True,
        "cohens_d": -0.321,
        "plain_english": "Volume comes in waves, not one continuous blast (organic accumulation pattern)"
    },
]

SCORE_THRESHOLD = 0  # Predict "winner" if total score >= 0


class RunnerDetector:
    """
    Monitors 1-minute OHLCV bars for a single token.
    Maintains a 30-minute rolling baseline, detects breakouts, and scores them.
    """

    def __init__(self, token_address="unknown", baseline_window=30, scoring_window=15):
        self.token_address = token_address
        self.baseline_window = baseline_window  # minutes of quiet period to track
        self.scoring_window = scoring_window    # minutes after breakout to score
        self.bars = deque(maxlen=baseline_window + scoring_window + 10)
        self.breakout_detected = False
        self.breakout_bar_index = -1
        self.breakout_time = None
        self.post_breakout_bars = []
        self.alert_fired = False

    def feed_bar(self, bar):
        """
        Feed a new 1-minute OHLCV bar. Bar format:
        {"unix_time": int, "o": float, "h": float, "l": float, "c": float, "v": float}

        Returns an alert dict if conditions are met, or None.
        """
        self.bars.append(bar)

        if len(self.bars) < self.baseline_window + 1:
            return None  # Not enough data yet

        if self.breakout_detected:
            return self._score_breakout(bar)
        else:
            return self._check_for_breakout(bar)

    def _get_baseline(self):
        """Get the baseline (quiet period) statistics from the rolling window."""
        baseline_bars = list(self.bars)[-self.baseline_window - 1:-1]
        volumes = [b.get("v", 0) or 0 for b in baseline_bars]
        closes = [b.get("c", 0) or 0 for b in baseline_bars]

        nz_vols = [v for v in volumes if v > 0]
        nz_closes = [c for c in closes if c > 0]

        return {
            "median_volume": statistics.median(nz_vols) if nz_vols else 0,
            "median_price": statistics.median(nz_closes) if nz_closes else 0,
            "max_close": max(nz_closes) if nz_closes else 0,
            "volumes": volumes,
            "closes": closes,
            "zero_vol_pct": sum(1 for v in volumes if not v or v == 0) / len(volumes) if volumes else 1
        }

    def _check_for_breakout(self, bar):
        """Check if the current bar triggers a breakout."""
        baseline = self._get_baseline()

        if baseline["median_volume"] <= 0 or baseline["max_close"] <= 0:
            return None
        if baseline["zero_vol_pct"] > 0.5:
            return None  # Too many dead bars

        cur_vol = bar.get("v", 0) or 0
        cur_close = bar.get("c", 0) or 0

        if cur_vol > 3 * baseline["median_volume"] and cur_close > baseline["max_close"]:
            self.breakout_detected = True
            self.breakout_time = bar.get("unix_time", 0)
            self.baseline_at_breakout = baseline
            self.post_breakout_bars = [bar]
            dt = datetime.fromtimestamp(self.breakout_time, tz=timezone.utc)
            print(f"\n*** BREAKOUT DETECTED at {dt.strftime('%Y-%m-%d %H:%M:%S UTC')} ***")
            print(f"    Token: {self.token_address}")
            print(f"    Volume: {cur_vol:.0f} (baseline median: {baseline['median_volume']:.0f}, ratio: {cur_vol/baseline['median_volume']:.1f}x)")
            print(f"    Price: {cur_close:.10f} (baseline median: {baseline['median_price']:.10f})")
            return None  # Wait for 15 bars before scoring

        return None

    def _score_breakout(self, bar):
        """Accumulate post-breakout bars and score after 15 minutes."""
        self.post_breakout_bars.append(bar)

        if len(self.post_breakout_bars) < self.scoring_window:
            return None  # Not enough post-breakout data yet

        if self.alert_fired:
            return None  # Already scored this breakout

        # Compute features
        features = self._compute_features()
        if not features:
            return None

        # Score
        total_score, details = self._apply_rules(features)
        predicted = "winner" if total_score >= SCORE_THRESHOLD else "loser"
        self.alert_fired = True

        baseline = self.baseline_at_breakout
        current_price = bar.get("c", 0) or 0
        current_mult = current_price / baseline["median_price"] if baseline["median_price"] > 0 else 0

        alert = {
            "token_address": self.token_address,
            "breakout_time": self.breakout_time,
            "current_price": current_price,
            "baseline_price": baseline["median_price"],
            "current_multiplier": current_mult,
            "total_score": total_score,
            "prediction": predicted,
            "feature_details": details,
            "rules_used": len(RULES)
        }

        self._print_alert(alert)
        return alert

    def _compute_features(self):
        """Compute scoring features from first 15 post-breakout bars."""
        baseline = self.baseline_at_breakout
        post = self.post_breakout_bars[:self.scoring_window]
        bmed_vol = baseline["median_volume"]
        qmed_price = baseline["median_price"]

        if bmed_vol <= 0 or qmed_price <= 0:
            return None

        vols = [b.get("v", 0) or 0 for b in post]
        closes = [b.get("c", 0) or 0 for b in post]
        lows = [b.get("l", 0) or 0 for b in post]

        features = {}

        # vol_ratio_vs_baseline
        avg_vol = sum(vols) / len(vols) if vols else 0
        features["vol_ratio_vs_baseline"] = avg_vol / bmed_vol

        # vol_consistency
        above = sum(1 for v in vols if v > bmed_vol)
        features["vol_consistency"] = above / len(vols) if vols else 0

        # vol_no_gap
        streak, max_streak = 0, 0
        for v in vols:
            if v > 2 * bmed_vol:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        features["vol_no_gap"] = max_streak

        # price_vs_baseline_range
        last_close = 0
        for c in reversed(closes):
            if c > 0:
                last_close = c
                break
        features["price_vs_baseline_range"] = last_close / qmed_price if qmed_price > 0 else 0

        # price_retracement_depth
        running_high = closes[0] if closes and closes[0] > 0 else 0
        max_retrace = 0
        for c in closes:
            if c > 0:
                running_high = max(running_high, c)
                move = running_high - qmed_price
                if move > 0:
                    pullback = running_high - c
                    max_retrace = max(max_retrace, pullback / move)
        features["price_retracement_depth"] = max_retrace

        return features

    def _apply_rules(self, features):
        """Apply scoring rules to features. Returns (total_score, details_list)."""
        total = 0
        details = []

        for rule in RULES:
            feat_name = rule["name"]
            raw_val = features.get(feat_name, 0)

            if rule["log_transform"]:
                val = math.log1p(max(0, raw_val))
            else:
                val = raw_val

            if rule["winner_side"] == "high":
                s = +1 if val >= rule["threshold"] else -1
            else:
                s = +1 if val <= rule["threshold"] else -1

            total += s
            details.append({
                "feature": feat_name,
                "raw_value": raw_val,
                "transformed_value": val,
                "threshold": rule["threshold"],
                "side": rule["winner_side"],
                "score": s,
                "plain_english": rule["plain_english"]
            })

        return total, details

    def _print_alert(self, alert):
        """Print a human-readable alert."""
        pred = alert["prediction"].upper()
        dt = datetime.fromtimestamp(alert["breakout_time"], tz=timezone.utc)

        print(f"\n{'='*70}")
        print(f"  ALERT: {pred} SIGNAL — {self.token_address}")
        print(f"{'='*70}")
        print(f"  Breakout time:     {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Current price:     {alert['current_price']:.10f}")
        print(f"  Baseline price:    {alert['baseline_price']:.10f}")
        print(f"  Current multiple:  {alert['current_multiplier']:.2f}x")
        print(f"  Total score:       {alert['total_score']} (threshold: {SCORE_THRESHOLD})")
        print(f"")
        print(f"  Feature Breakdown:")
        for d in alert["feature_details"]:
            icon = "+" if d["score"] == 1 else "-"
            print(f"    [{icon}] {d['feature']}: {d['raw_value']:.4f} "
                  f"(threshold: {d['threshold']:.4f}, side: {d['side']}) "
                  f"— {d['plain_english']}")
        print(f"{'='*70}\n")

    def reset(self):
        """Reset detector for a new breakout detection cycle."""
        self.bars.clear()
        self.breakout_detected = False
        self.breakout_bar_index = -1
        self.breakout_time = None
        self.post_breakout_bars = []
        self.alert_fired = False


def demo_with_saved_data():
    """Demo: replay a winner and a loser from saved data."""
    import json

    print("RUNNER DETECTOR — DEMO MODE")
    print("Replaying saved token data through the detector\n")

    for label_file in ["data/winners.json", "data/losers.json"]:
        with open(label_file) as f:
            tokens = json.load(f)

        if not tokens:
            continue

        # Pick first token with enough data
        token = tokens[0]
        all_bars = token["pre_breakout_bars"] + token["post_breakout_bars"]

        det = RunnerDetector(token_address=token["address"])
        print(f"\n--- Replaying {token['label'].upper()}: {token['address'][:20]}... ---")
        print(f"    True multiplier: {token['multiplier']:.1f}x")
        print(f"    Bars: {len(all_bars)}")

        for bar in all_bars:
            alert = det.feed_bar(bar)
            if alert:
                print(f"\n    Detector prediction: {alert['prediction'].upper()}")
                print(f"    True label: {token['label'].upper()}")
                correct = alert['prediction'] == token['label']
                print(f"    {'CORRECT' if correct else 'WRONG'}")
                break


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo_with_saved_data()
    else:
        print("Usage:")
        print("  python detector.py --demo     Run demo with saved data")
        print("")
        print("Integration:")
        print("  from detector import RunnerDetector")
        print("  det = RunnerDetector(token_address='...')")
        print("  for bar in stream:")
        print("    alert = det.feed_bar(bar)")
        print("    if alert: handle_alert(alert)")
