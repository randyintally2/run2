"""
Phase 3: Find the Decision Boundary
Compute Cohen's d for each feature, build a simple scoring system.
No ML — just statistics and thresholds.
"""
import csv
import math
import os
import statistics
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
    winners = [r for r in rows if r["label"] == "winner"]
    losers = [r for r in rows if r["label"] == "loser"]
    print(f"Loaded {len(winners)} winners, {len(losers)} losers")
    return rows, winners, losers


def cohens_d(group1, group2):
    """
    Cohen's d measures how different two groups are.
    d = (mean1 - mean2) / pooled_std
    Interpretation: 0.2 = small, 0.5 = medium, 0.8 = large effect.
    """
    if not group1 or not group2:
        return 0
    m1, m2 = statistics.mean(group1), statistics.mean(group2)
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return 0
    s1 = statistics.stdev(group1)
    s2 = statistics.stdev(group2)
    # Pooled standard deviation
    pooled = math.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    if pooled == 0:
        return 0
    return (m1 - m2) / pooled


def log_safe(values):
    """Log-transform values, handling zeros and negatives."""
    return [math.log1p(max(0, v)) for v in values]


def compute_separability(winners, losers):
    """Compute Cohen's d for each feature. Try both raw and log-transformed."""
    results = []
    for feat in FEATURE_COLS:
        w_vals = [r[feat] for r in winners]
        l_vals = [r[feat] for r in losers]

        # Raw Cohen's d
        d_raw = cohens_d(w_vals, l_vals)

        # Log-transformed Cohen's d (handles extreme outliers)
        w_log = log_safe(w_vals)
        l_log = log_safe(l_vals)
        d_log = cohens_d(w_log, l_log)

        # Use whichever has higher absolute d
        use_log = abs(d_log) > abs(d_raw)
        d = d_log if use_log else d_raw

        w_mean = statistics.mean(w_vals) if w_vals else 0
        l_mean = statistics.mean(l_vals) if l_vals else 0
        w_std = statistics.stdev(w_vals) if len(w_vals) >= 2 else 0
        l_std = statistics.stdev(l_vals) if len(l_vals) >= 2 else 0

        # Plain English interpretation
        abs_d = abs(d)
        if abs_d >= 0.8:
            strength = "STRONG separation"
        elif abs_d >= 0.5:
            strength = "MEDIUM separation"
        elif abs_d >= 0.2:
            strength = "WEAK separation"
        else:
            strength = "NO meaningful separation"

        direction = "winners higher" if d > 0 else "losers higher"
        note = f"{strength} — {direction}"

        results.append({
            "feature": feat,
            "winner_mean": w_mean,
            "loser_mean": l_mean,
            "winner_std": w_std,
            "loser_std": l_std,
            "cohens_d": d,
            "abs_d": abs_d,
            "used_log": use_log,
            "note": note
        })

    results.sort(key=lambda x: x["abs_d"], reverse=True)
    return results


def find_threshold(w_vals, l_vals, winner_side="high"):
    """
    Find the threshold that best separates winners from losers.
    winner_side: 'high' means winners tend to have higher values.
    Returns (threshold, true_positive_rate, false_positive_rate).
    """
    all_vals = sorted(set(w_vals + l_vals))
    best = None
    best_score = -1

    for thresh in all_vals:
        if winner_side == "high":
            tp = sum(1 for v in w_vals if v >= thresh)
            fp = sum(1 for v in l_vals if v >= thresh)
        else:
            tp = sum(1 for v in w_vals if v <= thresh)
            fp = sum(1 for v in l_vals if v <= thresh)

        tpr = tp / len(w_vals) if w_vals else 0
        fpr = fp / len(l_vals) if l_vals else 0

        # Score: maximize TPR while keeping FPR below 0.4
        score = tpr - 2 * max(0, fpr - 0.4)
        if score > best_score:
            best_score = score
            best = (thresh, tpr, fpr)

    return best if best else (0, 0, 0)


def build_scoring_system(separability, winners, losers):
    """Build scoring rules from top features."""
    # Take top 5 features by Cohen's d
    top_features = [s for s in separability if s["abs_d"] >= 0.2][:5]

    if len(top_features) < 3:
        # If too few features have d >= 0.2, take top 5 regardless
        top_features = separability[:5]

    rules = []
    for s in top_features:
        feat = s["feature"]
        w_vals = [r[feat] for r in winners]
        l_vals = [r[feat] for r in losers]

        # If log was better, transform
        if s["used_log"]:
            w_vals = log_safe(w_vals)
            l_vals = log_safe(l_vals)

        # Determine direction: winners higher or lower?
        winner_side = "high" if s["cohens_d"] > 0 else "low"
        thresh, tpr, fpr = find_threshold(w_vals, l_vals, winner_side)

        rules.append({
            "feature": feat,
            "threshold": thresh,
            "winner_side": winner_side,
            "tpr": tpr,
            "fpr": fpr,
            "cohens_d": s["cohens_d"],
            "used_log": s["used_log"],
            "note": s["note"]
        })

    return rules


def score_token(token_row, rules):
    """Score a single token using the rules. Returns total score and per-feature details."""
    total = 0
    details = []
    for rule in rules:
        feat = rule["feature"]
        val = token_row[feat]
        if rule["used_log"]:
            val = math.log1p(max(0, val))

        if rule["winner_side"] == "high":
            if val >= rule["threshold"]:
                s = +1
            else:
                s = -1
        else:
            if val <= rule["threshold"]:
                s = +1
            else:
                s = -1

        total += s
        details.append({
            "feature": feat,
            "value": token_row[feat],
            "threshold": rule["threshold"],
            "side": rule["winner_side"],
            "score": s,
            "used_log": rule["used_log"]
        })

    return total, details


def find_best_score_threshold(all_rows, rules):
    """Find the score threshold that maximizes TPR with FPR < 40%."""
    scored = []
    for row in all_rows:
        total, _ = score_token(row, rules)
        scored.append((row["label"], total))

    best_thresh = 0
    best_tpr = 0
    best_fpr = 1

    for thresh in range(-len(rules), len(rules) + 1):
        tp = sum(1 for lbl, s in scored if lbl == "winner" and s >= thresh)
        fp = sum(1 for lbl, s in scored if lbl == "loser" and s >= thresh)
        fn = sum(1 for lbl, s in scored if lbl == "winner" and s < thresh)
        tn = sum(1 for lbl, s in scored if lbl == "loser" and s < thresh)

        total_w = tp + fn
        total_l = fp + tn
        tpr = tp / total_w if total_w > 0 else 0
        fpr = fp / total_l if total_l > 0 else 0

        # Maximize TPR with FPR < 0.4
        if fpr <= 0.4 and tpr > best_tpr:
            best_tpr = tpr
            best_fpr = fpr
            best_thresh = thresh

    return best_thresh


def main():
    print(f"Phase 3: Decision Boundary — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    all_rows, winners, losers = load_features()

    # Step 1: Compute separability
    print("\n--- Step 1: Feature Separability (Cohen's d) ---\n")
    separability = compute_separability(winners, losers)

    print(f"{'Feature':<30s} {'Winner Avg':>12s} {'Loser Avg':>12s} {'Cohen d':>9s} {'Note'}")
    print("-" * 95)
    for s in separability:
        print(f"{s['feature']:<30s} {s['winner_mean']:>12.4f} {s['loser_mean']:>12.4f} {s['cohens_d']:>9.3f} {s['note']}")

    # Save separability CSV
    with open("results/feature_separability.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["feature", "winner_mean", "loser_mean",
                                                "winner_std", "loser_std", "cohens_d",
                                                "abs_d", "used_log", "note"])
        writer.writeheader()
        writer.writerows(separability)

    # Step 2: Build scoring rules
    print("\n\n--- Step 2: Scoring Rules ---\n")
    rules = build_scoring_system(separability, winners, losers)

    rule_lines = []
    for i, rule in enumerate(rules):
        direction = "above" if rule["winner_side"] == "high" else "below"
        log_note = " (log-transformed)" if rule["used_log"] else ""
        line = (f"Rule {i+1}: IF {rule['feature']}{log_note} is {direction} "
                f"{rule['threshold']:.6f} THEN score +1 (else -1)")
        print(line)
        print(f"  Cohen's d = {rule['cohens_d']:.3f}, TPR = {rule['tpr']:.2f}, FPR = {rule['fpr']:.2f}")
        rule_lines.append(line)
        rule_lines.append(f"  Cohen's d = {rule['cohens_d']:.3f}")
        rule_lines.append(f"  True Positive Rate = {rule['tpr']:.2f} (what % of actual winners this rule catches)")
        rule_lines.append(f"  False Positive Rate = {rule['fpr']:.2f} (what % of losers this rule wrongly flags)")
        rule_lines.append(f"  {rule['note']}")
        rule_lines.append("")

    # Step 3: Find best score threshold
    score_thresh = find_best_score_threshold(all_rows, rules)
    print(f"\nBest score threshold: {score_thresh}")
    print(f"(Predict 'winner' if total score >= {score_thresh})")

    # Step 4: Compute confusion matrix at this threshold
    tp, fp, tn, fn = 0, 0, 0, 0
    backtest = []

    for row in all_rows:
        total_score, details = score_token(row, rules)
        predicted = "winner" if total_score >= score_thresh else "loser"
        actual = row["label"]

        if actual == "winner" and predicted == "winner": tp += 1
        elif actual == "loser" and predicted == "winner": fp += 1
        elif actual == "loser" and predicted == "loser": tn += 1
        elif actual == "winner" and predicted == "loser": fn += 1

        triggered = [d["feature"] for d in details if d["score"] == 1]
        backtest.append({
            "token_address": row["token_address"],
            "true_label": actual,
            "predicted_label": predicted,
            "score": total_score,
            "triggered_features": ", ".join(triggered)
        })

    accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    total_w = tp + fn
    total_l = fp + tn

    print(f"\n--- Step 4: Confusion Matrix ---\n")
    print(f"                  Predicted Winner  Predicted Loser")
    print(f"Actual Winner     {tp:>16d}  {fn:>15d}")
    print(f"Actual Loser      {fp:>16d}  {tn:>15d}")
    print(f"\nAccuracy:  {accuracy:.2%} ({tp+tn} correct out of {tp+fp+tn+fn})")
    print(f"Precision: {precision:.2%} (of tokens predicted as winners, {tp} actually were)")
    print(f"Recall:    {recall:.2%} (of actual winners, we caught {tp} out of {total_w})")

    # Save scoring rules
    with open("results/scoring_rules.txt", "w") as f:
        f.write("EARLY RUNNER CLASSIFIER — SCORING RULES\n")
        f.write("=" * 50 + "\n\n")
        f.write("How it works:\n")
        f.write("Each rule checks one feature of the token's first 15 minutes after breakout.\n")
        f.write("If the feature value is on the 'winner side' of the threshold, score +1.\n")
        f.write("If it's on the 'loser side', score -1.\n")
        f.write(f"If the total score is {score_thresh} or higher, predict WINNER.\n\n")
        f.write("Rules:\n")
        f.write("-" * 50 + "\n")
        for line in rule_lines:
            f.write(line + "\n")
        f.write(f"\nScore threshold: {score_thresh}\n")
        f.write(f"Predict WINNER if total score >= {score_thresh}\n")
    print("\nSaved results/scoring_rules.txt")

    # Save confusion matrix
    with open("results/confusion_matrix.txt", "w") as f:
        f.write("CONFUSION MATRIX\n")
        f.write("=" * 50 + "\n\n")
        f.write("What this table means:\n")
        f.write("- True Positive (TP): We predicted winner and it WAS a winner — good!\n")
        f.write("- False Positive (FP): We predicted winner but it was a loser — bad, we lose money\n")
        f.write("- True Negative (TN): We predicted loser and it WAS a loser — good, we avoided a loss\n")
        f.write("- False Negative (FN): We predicted loser but it was a winner — bad, we missed a gain\n\n")
        f.write(f"                  Predicted Winner  Predicted Loser\n")
        f.write(f"Actual Winner     {tp:>16d}  {fn:>15d}\n")
        f.write(f"Actual Loser      {fp:>16d}  {tn:>15d}\n\n")
        f.write(f"Accuracy:  {accuracy:.2%}\n")
        f.write(f"  Out of {tp+fp+tn+fn} tokens, we got {tp+tn} right.\n\n")
        f.write(f"Precision: {precision:.2%}\n")
        f.write(f"  When we said 'this is a winner', we were right {precision:.0%} of the time.\n")
        f.write(f"  This matters most — it's how often our BUY signal is correct.\n\n")
        f.write(f"Recall: {recall:.2%}\n")
        f.write(f"  Of all {total_w} actual winners, we caught {tp}.\n")
        f.write(f"  Missing some winners is OK; wrongly buying losers is expensive.\n\n")
        f.write(f"Score threshold used: {score_thresh}\n")
    print("Saved results/confusion_matrix.txt")

    # Save backtest
    with open("results/backtest_summary.txt", "w") as f:
        f.write("BACKTEST SUMMARY\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'Address':<46s} {'True':>6s} {'Pred':>6s} {'Score':>6s} Triggered Features\n")
        f.write("-" * 100 + "\n")
        for b in backtest:
            mark = "OK" if b["true_label"] == b["predicted_label"] else "WRONG"
            f.write(f"{b['token_address']:<46s} {b['true_label']:>6s} {b['predicted_label']:>6s} "
                    f"{b['score']:>6d} {b['triggered_features']}  [{mark}]\n")
    print("Saved results/backtest_summary.txt")

    print(f"\n{'='*60}")
    print(f"PHASE 3 COMPLETE")
    print(f"Top features by Cohen's d:")
    for s in separability[:5]:
        print(f"  {s['feature']}: d={s['cohens_d']:.3f} ({s['note']})")
    print(f"Score threshold: {score_thresh}")
    print(f"Accuracy: {accuracy:.2%}, Precision: {precision:.2%}, Recall: {recall:.2%}")


if __name__ == "__main__":
    main()
