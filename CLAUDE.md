# Project: Early Runner Classifier v3

## What This Is
A classifier that detects the early stages of a 10x+ price move on an EXISTING Solana meme token. These are not new launches. These are tokens that have been trading for hours, days, or weeks — sitting flat or low volume — and then volume picks up and price starts climbing. The question is: is this the start of a real 10x+ run, or a temporary pump that dies in 20 minutes?

We need to answer that question EARLY in the move — before 10% of the eventual move has happened. After that, the risk/reward is gone.

## What This Is NOT
- This is NOT about detecting new token launches or sniping pool creation
- This is NOT about the first minutes of a token's existence
- The tokens we care about already exist and have trading history
- We do NOT care about gains measured from the first swap or pool creation price

## CRITICAL DATA QUALITY RULE: Realistic Pricing
The first candle of any token's existence has a price that nobody could actually buy at — it's a pre-pool artifact. NEVER use the first candle's price, the first swap price, or any price from the token's initial creation as a reference point.

All price calculations must use the QUIET PERIOD price as the baseline:
- The "starting price" is the median price during the 30-minute quiet period before the breakout
- Gains are measured from this quiet period median, not from pool creation or first trade
- A "10x runner" means: price went to 10x the quiet period price, not 10x the first candle
- If a token shows gains over 1000x from its first candle, that is BAD DATA from using the pool creation price. Throw it out or recalculate from a realistic baseline.
- Every token in the dataset must have been trading for at least 2 hours before the breakout moment we're studying. This ensures a real, tradeable price history exists.

## API Keys & Data Sources
A .env file exists in this project root (D:\run) with API keys. Load it before making any API calls.

Variable names:
- BIRDEYE_API_KEY
- HELIUS_API_KEY
- NANSEN_API_KEY

### CRITICAL: Do Not Trust Your Training Data For API Endpoints
Your training data contains outdated API URLs, endpoints, headers, and parameters. They WILL fail. Before making any API call to any service, you MUST:
1. Use curl or Python requests to fetch the LIVE documentation page for that API
2. Parse the current endpoints, required headers, and authentication method from the live docs
3. Only then construct your API calls based on what you just read

Documentation URLs to fetch first:
- Birdeye: https://docs.birdeye.so/
- Helius: https://docs.helius.dev/
- Nansen: https://docs.nansen.ai/
- DexScreener: https://docs.dexscreener.com/api/reference

If a documentation URL itself has moved, use web search to find the current one.

### API Fallback Chain
Try APIs in this order for OHLCV data:
1. Birdeye
2. Helius
3. DexScreener (free, no key needed)
4. Any other Solana data API you can find via web search

### When An API Call Fails
1. First attempt: try the call as constructed from the live docs
2. Second attempt: re-read the live docs, check if you misread something, try again
3. If still failing: use web search to find current working examples of that specific API call (e.g. search "Birdeye API OHLCV example 2026")
4. If still failing after web search: move to the next API in the fallback chain
5. If ALL APIs in the chain fail for the same data type: use web search to find alternative Solana data APIs you haven't tried yet (Solscan, Jupiter, Raydium, Orca, any aggregator)
6. Document every failure and resolution in the Failed Approaches section

### You must NEVER stop and ask the human for help.
The human is not available. If something isn't working, search the web, try a different approach, try a different API. Exhaust every option before concluding that a specific data point is unavailable. If a data point is truly unavailable from any source, skip it, document why, and continue with what you have.

## Git Workflow
This project is connected to a remote GitHub repo. After completing each phase:
1. git add -A
2. git commit -m "Phase X complete - (brief summary of what was done)"
3. git push origin main

This allows the project owner to monitor progress from their phone via GitHub.

## Phase 0: API Discovery
1. Load .env
2. Fetch the live documentation for each API listed above
3. Find the specific endpoints for: OHLCV candle data (1-minute), token search/discovery, top gainers/trending tokens, token metadata
4. Make one test call to each API to confirm the key works and you have the right endpoints
5. Log results to data/api_status.txt including: which APIs work, what endpoints you found, any rate limits noted
6. Commit and push to GitHub

## Phase 1: Find Qualifying Tokens

This is the hardest phase. You need to find real historical examples of both categories.

### How to find tokens
Use DexScreener or Birdeye to pull Solana token data. The concrete approach:
1. Use the API to get Solana tokens sorted by volume or price change
2. For each candidate token, pull its full price history
3. Scan the price history looking for a "breakout moment" — a period where the token had been trading quietly for at least 2 hours, then volume and price sharply increased
4. Classify the token based on what happened AFTER the breakout

If the API doesn't have a "top gainers" or "trending" endpoint, use web search to find a way to discover high-volume Solana meme tokens from the last 90 days. DexScreener's website shows top gainers daily — if the API doesn't expose it, find another way.

Alternative discovery methods if APIs don't help:
- Search Twitter/X for "solana 100x" or "solana meme coin" posts from the last 90 days that mention specific token names or contract addresses
- Check Dextools, GeckoTerminal, or DEX Screener website trending pages
- Use Birdeye's token discovery or trending features
- Search for curated lists of Solana meme coin runners on Reddit, YouTube, or crypto blogs

You need contract addresses. Once you have them, you can pull OHLCV data.

### Winners (30-50 tokens)
Tokens where:
- The token had been trading for at least 2 hours before the breakout (established, tradeable price)
- There was a quiet or low-volume period (at least 30 minutes of relatively flat price action)
- Then a breakout started — volume increased, price began climbing
- The price eventually reached 10x or more from the QUIET PERIOD MEDIAN PRICE (not from the first candle)
- The move sustained over at least 1 hour — it wasn't a single candle spike

For each winner, record:
- Token address and pair address
- The breakout timestamp (when volume first picked up from the quiet period)
- Quiet period median price (THIS is the baseline price for measuring gains)
- Peak price after breakout
- Actual multiplier: peak price / quiet period median price
- 1-minute OHLCV for 2 hours BEFORE the breakout (the quiet period / baseline)
- 1-minute OHLCV for 6 hours AFTER the breakout started

### Losers (30-50 tokens)
Tokens where:
- Same criteria: at least 2 hours old, quiet period, then breakout
- Price spiked 2x-5x from the quiet period median price
- Then retraced 80%+ within 6 hours — the pump died

Same data format as winners.

### Defining the breakout moment
For each token's price history, the "breakout moment" is the first 1-minute bar where:
- Volume exceeds 3x the median volume of the prior 30 minutes AND
- Price closes higher than any close in the prior 30 minutes

If this definition doesn't work well (most tokens don't have clean breakout moments), adjust it and document what you changed and why.

### Data quality checks — run these before saving any token
1. Token must have been trading for at least 2 hours before the breakout moment
2. Quiet period median price must be a price someone could realistically buy at (not a pool creation artifact)
3. If the multiplier from the first-ever candle exceeds 1000x but the multiplier from quiet period median is only 10x, use the quiet period median — the first candle price is bad data
4. Every token must have at least 30 minutes of pre-breakout OHLCV AND 60 minutes of post-breakout OHLCV
5. Throw out any token where the quiet period has zero volume bars (dead token, not tradeable)
6. Log every thrown-out token and the reason to data/rejected_tokens.csv

### Save format
- data/winners.json — list of winner token objects with their OHLCV data
- data/losers.json — list of loser token objects with their OHLCV data  
- data/rejected_tokens.csv — tokens that failed data quality checks and why
- data/manifest.csv — token address, pair address, label, breakout timestamp, quiet period median price, peak price, multiplier, data source, minutes of pre-breakout data, minutes of post-breakout data

Target 30 minimum per category. 50 is better. Do not proceed with fewer than 20 per category.

**STOP after Phase 1. Update Progress with: how many winners found, how many losers found, how many rejected and why, which APIs were used. Commit and push to GitHub.**

## Phase 2: Feature Engineering

For each token, compute features using ONLY the first 15 minutes after the breakout moment. This simulates catching it early.

### Volume features (comparing breakout to the quiet baseline period)
- vol_ratio_vs_baseline: ratio of average volume in first 15 breakout minutes to median volume of the 30-minute quiet period
- vol_acceleration: is volume increasing bar-over-bar during the breakout? (slope of volume over the last 5 bars)
- vol_consistency: what % of the first 15 post-breakout bars had volume above the baseline median? (sustained buying vs one spike)
- vol_no_gap: longest streak of consecutive post-breakout bars where volume stayed above 2x the baseline median

### Price features
- price_higher_lows: count of bars in the first 15 minutes where low > previous bar's low (staircase pattern)
- price_retracement_depth: deepest pullback in the first 15 minutes as % of the move so far (runners pull back shallow, pumps retrace deep)
- price_vs_baseline_range: how far has price moved from the quiet period median, expressed as a multiple (e.g. 1.5x = 50% above baseline)
- price_staircase_ratio: ratio of bars that made a higher low to total bars (1.0 = perfect staircase, 0.0 = choppy)

### Baseline comparison features
- volume_trend_before: was volume already slowly increasing in the 30 minutes before breakout? (slope — gradual accumulation vs sudden spike)
- price_trend_before: was price slowly drifting up before breakout, or completely flat? (pre-loading vs surprise)

### Transaction features (if available from any API)
- tx_count_vs_baseline: ratio of transactions per minute post-breakout vs baseline
- unique_buyer_estimate: if available, how many distinct wallet addresses bought in the first 15 minutes

Save to data/features.csv with columns: token_address, label (winner/loser), breakout_timestamp, quiet_period_median_price, and all features.

**STOP after Phase 2. Update Progress. Commit and push to GitHub.**

## Phase 3: Find the Decision Boundary

This is NOT a machine learning project. We have 60-100 samples. ML will overfit.

Instead:
1. For each feature, compute the mean and standard deviation for winners vs losers
2. Rank features by separability using Cohen's d (this measures how different the two groups are — higher = more different, above 0.8 is strong)
3. Print a clear table showing each feature's: winner average, loser average, Cohen's d value, and a plain English note on what it means
4. For the top 3-5 most separating features (highest Cohen's d), build a simple scoring system:
   - For each feature, define a threshold that best separates winners from losers
   - Score +1 if the token's value is on the winner side, -1 if on the loser side
5. Find the total score threshold that maximizes true positive rate while keeping false positive rate below 40%

Output:
- results/feature_separability.csv — every feature with winner mean, loser mean, Cohen's d, and plain English interpretation
- results/scoring_rules.txt — plain English rules with specific thresholds, like "IF average volume in the first 15 minutes is more than 8x the quiet period median AND at least 12 of 15 bars had above-baseline volume THEN score +1"
- results/confusion_matrix.txt — true positives, false positives, true negatives, false negatives at the chosen threshold, with plain English explanation
- results/backtest_summary.txt — for each token: address, true label, predicted label, score, and which features triggered

**STOP after Phase 3. Update Progress. Commit and push to GitHub.**

## Phase 4: Leave-One-Out Validation

This tests whether the rules actually work on tokens they weren't built from:
1. Remove one token from the dataset
2. Recompute the scoring rules from the remaining tokens
3. Classify the removed token using the recomputed rules
4. Record whether the prediction was correct
5. Repeat for every token in the dataset

Output:
- results/loo_validation.csv — each token's true label, predicted label, and score
- results/loo_summary.txt — overall accuracy, precision (what % of predicted winners were actually winners), recall (what % of actual winners did we catch), and a plain English verdict: is this classifier useful or not? If accuracy is below 65%, say so honestly and explain what additional data (on-chain, wallet analysis, LP structure) would likely be needed to improve it.

**STOP. Update Progress. Commit and push to GitHub.**

## Phase 5: Translate to Real-Time Detection Rules

Take the final scoring rules and write a standalone Python script (detector.py) that:
- Accepts a stream of 1-minute OHLCV bars for a single token
- Maintains a rolling 30-minute baseline window of recent price and volume
- Detects a breakout moment (volume exceeds 3x baseline median AND new price high)
- Once a breakout is detected, starts scoring the next 15 bars against the rules
- Prints an alert if the score exceeds the threshold
- Each alert includes: token address, current price, quiet period baseline price, current multiplier from baseline, each feature's current value vs its threshold, and the overall score

This script should be simple enough to plug into a Birdeye WebSocket listener later. It should NOT depend on the training data — just the derived rules hardcoded as constants.

Also write results/how_to_use.txt explaining in plain English:
- What the detector does
- What each alert field means
- What score threshold was chosen and why
- What the expected accuracy is based on validation
- What the detector cannot tell you (e.g. on-chain risk factors it doesn't check)

**STOP. Update Progress. Commit and push to GitHub.**

## Rules For This Agent

### DO
- Work methodically through phases in order
- Commit and push to GitHub after each phase
- Update the Progress section below after each phase
- Log failed API calls and workarounds to Failed Approaches
- Fetch live API docs before making any API calls — never trust your training data for URLs or endpoints
- If something fails, search the web and figure it out yourself
- Write all code in Python
- Keep each script under 300 lines. Split into modules if needed
- Print progress to stdout so the human can monitor
- Use plain English in all output files. No jargon without explanation.
- Be honest about accuracy. If the classifier doesn't work well, say so and explain what's missing.

### DO NOT
- Do not skip ahead. Phase 1 data collection IS the work.
- Do not use neural networks, random forests, or any ML model. Simple statistics only.
- Do not hypothesize about what features MIGHT work without testing on data first.
- Do not add features beyond what's listed unless all listed features have Cohen's d below 0.5. If that happens, document why in Failed Approaches and add 3 new features that compare breakout behavior to the baseline period.
- Do not spend more than 2 iterations on any single API error before trying web search. Do not spend more than 2 iterations after web search before moving to the next fallback.
- Do not refactor or clean up code that is already working.
- Do not write tests unless a script is producing wrong results.
- Do not stop and ask the human for help. The human is not available. Solve it yourself.
- Do not use jargon without explaining it in plain English.
- Do not use the first candle price or pool creation price as a baseline. Ever. Use the quiet period median.
- Do not include any token in the dataset that hasn't been trading for at least 2 hours before its breakout moment.

## Progress

### Phase 0: API Discovery — COMPLETE (2026-04-13)
- Birdeye API: WORKING — all critical endpoints confirmed (OHLCV 1m, token trending, gainers/losers, token list, search, metadata)
- Helius API: WORKING — token metadata via DAS getAsset (no OHLCV capability)
- DexScreener API: WORKING — free, no key needed (search, token pairs, top boosts; no OHLCV)
- Nansen API: NOT USABLE — returns 402 Payment Required (x402 protocol needed)
- Primary data plan: Birdeye for OHLCV + discovery, DexScreener backup for discovery, Helius backup for metadata
- Files: data/api_status.txt, phase0_api_discovery.py

### Phase 1: Find Qualifying Tokens — COMPLETE (2026-04-13)
- Winners found: 31 (target was 30-50, minimum 20) — multipliers range from 5.0x to 803.8x
- Losers found: 50 (target was 30-50) — multipliers 1.5x-6.2x with 70-279% retracement
- Rejected: 1497 tokens (mostly "no qualifying breakouts", "too few bars", new tokens without history)
- Unique winner addresses: 29, unique loser addresses: 39 (2 tokens appear in both with different events)
- Discovery sources: Birdeye token list (500 pages, 3 sort criteria), Birdeye trending, DexScreener (18 keyword searches), known token list (21 tokens)
- Total candidates scanned: 1626
- Data source: Birdeye OHLCV v3 (1m bars for breakout detail, 30m bars for 90-day scanning)
- Classification criteria: Winners = 5x+ sustained (15+ minutes above 3x), Losers = 1.5x+ spike then 70%+ retrace
- Files: data/winners.json, data/losers.json, data/manifest.csv, data/rejected_tokens.csv, phase1_collect.py

## Failed Approaches

### Nansen API (Phase 0)
- Tried Bearer token, api-key header, x-api-key header — all return 402 Payment Required
- Nansen requires x402 payment protocol beyond just an API key
- Resolution: Skipping Nansen entirely, using Birdeye + DexScreener + Helius instead

### Birdeye /defi/v3/token/meta-data-single (Phase 0)
- Returns 404 — endpoint removed or renamed
- Resolution: Using /defi/token_overview instead (confirmed working)

### Established tokens (BONK, WIF, etc.) as data sources (Phase 1)
- Major tokens like BONK, WIF, POPCAT, FARTCOIN etc. don't show 5x+ breakouts in recent 90-day data
- Their big runs happened months/years ago; recent price action is mature/stable
- Resolution: Used Birdeye token list discovery (volume change sorted) to find newer tokens with recent breakouts
- These newer tokens from pump.fun/Raydium had genuine breakout patterns in the 90-day window

### Birdeye 15m initial scan approach (Phase 1)
- First approach: single API call for 15m data only returned ~100 bars (25 hours of data)
- Resolution: Switched to 30m bars which cover 90 days in a single call (4320 bars < 5000 limit)
- Also discovered API returns up to 5000 bars per call (not 120 as initially assumed)
