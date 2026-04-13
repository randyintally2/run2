"""
Phase 4: Leave-One-Out Validation
Tests whether the scoring rules generalize by recomputing rules with each token removed.
"""
import csv
import math
import statistics
import os
from datetime import datetime, timezone

os.makedirs("results", exist_ok=True)

FEATURE_COLS = [
    "vol_ratio_vs_baseline", "vol_acceleration", "vol_consistency", "vol_no_gap",
    "price_higher_lows", "price_retracement_depth", "price_vs_baseline_range",
    "price_staircase_ratio", "volume_trend_before", "price_trend_before",
    "tx_count_vs_baseline", "unique_buyer_estimate"
]


def load_features():
    rows = []
    with open("data/features.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for col in FEATURE_COLS:
                row[col] = float(row[col]) if row[col] else 0
            rows.append(row)
    return rows


def log_safe(values):
    return [math.log1p(max(0, v)) for v in values]


def cohens_d(g1, g2):
    if len(g1) < 2 or len(g2) < 2:
        return 0
    m1, m2 = statistics.mean(g1), statistics.mean(g2)
    s1, s2 = statistics.stdev(g1), statistics.stdev(g2)
    n1, n2 = len(g1), len(g2)
    pooled = math.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))
    return (m1 - m2) / pooled if pooled > 0 else 0


def build_rules(winners, losers):
    """Rebuild scoring rules from scratch (same logic as Phase 3)."""
    # Compute Cohen's d for each feature
    sep = []
    for feat in FEATURE_COLS:
        w_vals = [r[feat] for r in winners]
        l_vals = [r[feat] for r in losers]
        d_raw = cohens_d(w_vals, l_vals)
        d_log = cohens_d(log_safe(w_vals), log_safe(l_vals))
        use_log = abs(d_log) > abs(d_raw)
        d = d_log if use_log else d_raw
        sep.append({"feature": feat, "d": d, "abs_d": abs(d), "use_log": use_log})

    sep.sort(key=lambda x: x["abs_d"], reverse=True)
    top = [s for s in sep if s["abs_d"] >= 0.2][:5]
    if len(top) < 3:
        top = sep[:5]

    rules = []
    for s in top:
        feat = s["feature"]
        w_vals = [r[feat] for r in winners]
        l_vals = [r[feat] for r in losers]
        if s["use_log"]:
            w_vals = log_safe(w_vals)
            l_vals = log_safe(l_vals)

        winner_side = "high" if s["d"] > 0 else "low"

        # Find threshold
        all_vals = sorted(set(w_vals + l_vals))
        best_thresh, best_score = 0, -1
        for thresh in all_vals:
            if winner_side == "high":
                tp = sum(1 for v in w_vals if v >= thresh)
                fp = sum(1 for v in l_vals if v >= thresh)
            else:
                tp = sum(1 for v in w_vals if v <= thresh)
                fp = sum(1 for v in l_vals if v <= thresh)
            tpr = tp / len(w_vals) if w_vals else 0
            fpr = fp / len(l_vals) if l_vals else 0
            score = tpr - 2 * max(0, fpr - 0.4)
            if score > best_score:
                best_score = score
                best_thresh = thresh

        rules.append({"feature": feat, "threshold": best_thresh,
                      "winner_side": winner_side, "use_log": s["use_log"]})

    # Find score threshold
    scored = []
    for row in winners + losers:
        total = 0
        for rule in rules:
            val = row[rule["feature"]]
            if rule["use_log"]:
                val = math.log1p(max(0, val))
            if rule["winner_side"] == "high":
                total += 1 if val >= rule["threshold"] else -1
            else:
                total += 1 if val <= rule["threshold"] else -1
        scored.append((row["label"], total))

    best_st, best_tpr_st = 0, 0
    for st in range(-len(rules), len(rules) + 1):
        tp = sum(1 for lbl, s in scored if lbl == "winner" and s >= st)
        fp = sum(1 for lbl, s in scored if lbl == "loser" and s >= st)
        fn = sum(1 for lbl, s in scored if lbl == "winner" and s < st)
        tn = sum(1 for lbl, s in scored if lbl == "loser" and s < st)
        total_w = tp + fn
        total_l = fp + tn
        tpr = tp / total_w if total_w > 0 else 0
        fpr = fp / total_l if total_l > 0 else 0
        if fpr <= 0.4 and tpr > best_tpr_st:
            best_tpr_st = tpr
            best_st = st

    return rules, best_st


def score_one(row, rules, threshold):
    """Score a single token."""
    total = 0
    for rule in rules:
        val = row[rule["feature"]]
        if rule["use_log"]:
            val = math.log1p(max(0, val))
        if rule["winner_side"] == "high":
            total += 1 if val >= rule["threshold"] else -1
        else:
            total += 1 if val <= rule["threshold"] else -1
    predicted = "winner" if total >= threshold else "loser"
    return predicted, total


def main():
    print(f"Phase 4: Leave-One-Out Validation — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    all_rows = load_features()
    n = len(all_rows)
    print(f"Dataset: {n} tokens")

    loo_results = []
    correct = 0

    for i in range(n):
        # Remove token i
        held_out = all_rows[i]
        remaining = all_rows[:i] + all_rows[i+1:]

        winners = [r for r in remaining if r["label"] == "winner"]
        losers = [r for r in remaining if r["label"] == "loser"]

        # Rebuild rules from remaining
        rules, threshold = build_rules(winners, losers)

        # Predict held-out token
        predicted, score = score_one(held_out, rules, threshold)
        actual = held_out["label"]
        is_correct = predicted == actual
        if is_correct:
            correct += 1

        loo_results.append({
            "token_address": held_out["token_address"],
            "true_label": actual,
            "predicted_label": predicted,
            "score": score
        })

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{n} done — running accuracy: {correct/(i+1):.2%}")

    # Compute final metrics
    tp = sum(1 for r in loo_results if r["true_label"] == "winner" and r["predicted_label"] == "winner")
    fp = sum(1 for r in loo_results if r["true_label"] == "loser" and r["predicted_label"] == "winner")
    tn = sum(1 for r in loo_results if r["true_label"] == "loser" and r["predicted_label"] == "loser")
    fn = sum(1 for r in loo_results if r["true_label"] == "winner" and r["predicted_label"] == "loser")

    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0

    print(f"\n{'='*60}")
    print(f"LEAVE-ONE-OUT VALIDATION RESULTS")
    print(f"{'='*60}")
    print(f"Accuracy:  {accuracy:.2%} ({tp+tn}/{n})")
    print(f"Precision: {precision:.2%}")
    print(f"Recall:    {recall:.2%}")
    print(f"\nConfusion Matrix:")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}")

    # Save LOO CSV
    with open("results/loo_validation.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["token_address", "true_label", "predicted_label", "score"])
        writer.writeheader()
        writer.writerows(loo_results)
    print("\nSaved results/loo_validation.csv")

    # Save LOO summary
    with open("results/loo_summary.txt", "w") as f:
        f.write("LEAVE-ONE-OUT VALIDATION SUMMARY\n")
        f.write("=" * 60 + "\n\n")
        f.write("How this test works:\n")
        f.write("1. Remove one token from the dataset\n")
        f.write("2. Rebuild the scoring rules from the remaining tokens\n")
        f.write("3. Use those rules to predict the removed token\n")
        f.write("4. Check if the prediction was correct\n")
        f.write("5. Repeat for every token\n\n")
        f.write("This tests whether the rules are robust or just memorizing the training data.\n")
        f.write("If LOO accuracy is close to the training accuracy, the rules generalize well.\n")
        f.write("If LOO accuracy is much lower, the rules are overfit.\n\n")
        f.write(f"Results:\n")
        f.write(f"  Accuracy:  {accuracy:.2%} ({tp+tn} correct out of {n})\n")
        f.write(f"  Precision: {precision:.2%}\n")
        f.write(f"    When the rules predicted 'winner', they were right {precision:.0%} of the time.\n")
        f.write(f"  Recall:    {recall:.2%}\n")
        f.write(f"    Of all {tp+fn} actual winners, the rules caught {tp}.\n\n")
        f.write(f"Confusion Matrix:\n")
        f.write(f"                  Predicted Winner  Predicted Loser\n")
        f.write(f"Actual Winner     {tp:>16d}  {fn:>15d}\n")
        f.write(f"Actual Loser      {fp:>16d}  {tn:>15d}\n\n")

        # Compare to training accuracy
        f.write(f"Comparison to training accuracy:\n")
        f.write(f"  Training accuracy (Phase 3): 67.90%\n")
        f.write(f"  LOO accuracy: {accuracy:.2%}\n")
        gap = abs(0.679 - accuracy)
        if gap < 0.05:
            f.write(f"  Gap: {gap:.1%} — SMALL. The rules generalize well.\n\n")
        elif gap < 0.10:
            f.write(f"  Gap: {gap:.1%} — MODERATE. Some overfitting but rules are still useful.\n\n")
        else:
            f.write(f"  Gap: {gap:.1%} — LARGE. The rules may be overfit to the training data.\n\n")

        # Verdict
        f.write("VERDICT:\n")
        if accuracy >= 0.65:
            f.write(f"This classifier IS useful. {accuracy:.0%} accuracy on unseen tokens means\n")
            f.write("the features capture real differences between runners and pump-and-dumps.\n\n")
            f.write("The precision and recall trade-off depends on your risk tolerance:\n")
            f.write(f"- Precision {precision:.0%}: About {100-precision*100:.0f}% of 'buy' signals will be wrong.\n")
            f.write(f"- Recall {recall:.0%}: You'll miss about {100-recall*100:.0f}% of actual winners.\n\n")
            f.write("For a classifier based only on 15 minutes of price/volume data with no\n")
            f.write("on-chain analysis, this is a reasonable starting point.\n")
        else:
            f.write(f"This classifier has limited utility. {accuracy:.0%} accuracy is below the 65% threshold.\n\n")
            f.write("What would likely improve it:\n")
            f.write("- On-chain data: wallet concentration, unique buyers, LP lock status\n")
            f.write("- Social signals: Twitter/Telegram mention velocity\n")
            f.write("- Token metadata: age, holder distribution, developer activity\n")
            f.write("- More training data: 100+ tokens per category\n")

    print("Saved results/loo_summary.txt")
    print(f"\nPHASE 4 COMPLETE")


if __name__ == "__main__":
    main()
