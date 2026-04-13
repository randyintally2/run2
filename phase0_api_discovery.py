"""
Phase 0: API Discovery
Tests each API, confirms keys work, finds working endpoints for OHLCV, search, trending, metadata.
"""
import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

BIRDEYE_KEY = os.getenv("BIRDEYE_API_KEY")
HELIUS_KEY = os.getenv("HELIUS_API_KEY")
NANSEN_KEY = os.getenv("NANSEN_API_KEY")

# Well-known Solana meme token for testing: WIF (dogwifhat)
TEST_TOKEN = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
# SOL token
SOL_TOKEN = "So11111111111111111111111111111111111111112"

results = []

def log(msg):
    print(msg)
    results.append(msg)

def test_birdeye():
    log("\n=== BIRDEYE API ===")
    base = "https://public-api.birdeye.so"
    headers = {"X-API-KEY": BIRDEYE_KEY, "x-chain": "solana"}

    # Test 1: OHLCV v3
    log("\n[Test] Birdeye OHLCV v3 - /defi/v3/ohlcv")
    try:
        import time
        now = int(time.time())
        params = {
            "address": TEST_TOKEN,
            "type": "1m",
            "time_from": now - 3600,
            "time_to": now
        }
        r = requests.get(f"{base}/defi/v3/ohlcv", headers=headers, params=params, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("data", {}).get("items", [])
            log(f"  SUCCESS: Got {len(items)} OHLCV bars")
            if items:
                log(f"  Sample bar: {json.dumps(items[0], indent=2)[:200]}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 2: OHLCV pair
    log("\n[Test] Birdeye OHLCV v3 pair - /defi/v3/ohlcv/pair")
    try:
        params = {
            "address": TEST_TOKEN,
            "type": "1m",
            "time_from": now - 3600,
            "time_to": now
        }
        r = requests.get(f"{base}/defi/v3/ohlcv/pair", headers=headers, params=params, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("data", {}).get("items", [])
            log(f"  Got {len(items)} bars")
        else:
            log(f"  Response: {r.text[:200]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 3: Token trending
    log("\n[Test] Birdeye Token Trending - /defi/token_trending")
    try:
        params = {"sort_by": "rank", "sort_type": "asc", "offset": 0, "limit": 10}
        r = requests.get(f"{base}/defi/token_trending", headers=headers, params=params, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            tokens = data.get("data", {}).get("items", data.get("data", []))
            if isinstance(tokens, list):
                log(f"  SUCCESS: Got {len(tokens)} trending tokens")
                if tokens:
                    log(f"  First: {json.dumps(tokens[0], indent=2)[:200]}")
            else:
                log(f"  Response structure: {json.dumps(data, indent=2)[:300]}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 4: Gainers/Losers
    log("\n[Test] Birdeye Gainers/Losers - /trader/gainers-losers")
    try:
        params = {"type": "1W", "sort_by": "PnL", "sort_type": "desc", "offset": 0, "limit": 10}
        r = requests.get(f"{base}/trader/gainers-losers", headers=headers, params=params, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            log(f"  SUCCESS: {json.dumps(data, indent=2)[:300]}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 5: Token list (sorted by volume change)
    log("\n[Test] Birdeye Token List v3 - /defi/v3/token/list")
    try:
        params = {
            "sort_by": "volume_24h_change_percent",
            "sort_type": "desc",
            "offset": 0,
            "limit": 10,
            "min_liquidity": 10000
        }
        r = requests.get(f"{base}/defi/v3/token/list", headers=headers, params=params, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            tokens = data.get("data", {}).get("items", [])
            log(f"  SUCCESS: Got {len(tokens)} tokens")
            if tokens:
                t = tokens[0]
                log(f"  First token: address={t.get('address','?')}, name={t.get('name','?')}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 6: Token metadata
    log("\n[Test] Birdeye Token Metadata - /defi/v3/token/meta-data-single")
    try:
        params = {"address": TEST_TOKEN}
        r = requests.get(f"{base}/defi/v3/token/meta-data-single", headers=headers, params=params, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            log(f"  SUCCESS: {json.dumps(data.get('data',{}), indent=2)[:300]}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 7: Search
    log("\n[Test] Birdeye Search - /defi/v3/search")
    try:
        params = {"keyword": "dogwifhat", "chain": "solana", "target": "token", "sort_by": "volume_24h_usd", "sort_type": "desc", "offset": 0, "limit": 5}
        r = requests.get(f"{base}/defi/v3/search", headers=headers, params=params, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            log(f"  SUCCESS: {json.dumps(data, indent=2)[:300]}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")


def test_helius():
    log("\n=== HELIUS API ===")
    log("(Helius is an RPC/DAS provider - no OHLCV endpoints. Testing token metadata via DAS)")
    base = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

    # Test: getAsset
    log("\n[Test] Helius DAS getAsset")
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "test",
            "method": "getAsset",
            "params": {"id": TEST_TOKEN, "options": {"showFungible": True}}
        }
        r = requests.post(base, json=payload, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if "result" in data:
                result = data["result"]
                log(f"  SUCCESS: Token name = {result.get('content',{}).get('metadata',{}).get('name','?')}")
                token_info = result.get("token_info", {})
                log(f"  Token info: {json.dumps(token_info, indent=2)[:200]}")
            else:
                log(f"  Error: {data.get('error', data)}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test: searchAssets for fungible tokens
    log("\n[Test] Helius DAS searchAssets (fungible)")
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "test2",
            "method": "searchAssets",
            "params": {
                "tokenType": "fungible",
                "page": 1,
                "limit": 5
            }
        }
        r = requests.post(base, json=payload, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if "result" in data:
                items = data["result"].get("items", [])
                log(f"  SUCCESS: Got {len(items)} fungible tokens")
            else:
                log(f"  Error: {data.get('error', data)}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")


def test_dexscreener():
    log("\n=== DEXSCREENER API ===")
    log("(Free API, no authentication needed. No OHLCV endpoint.)")
    base = "https://api.dexscreener.com"

    # Test 1: Search
    log("\n[Test] DexScreener Search - /latest/dex/search")
    try:
        r = requests.get(f"{base}/latest/dex/search", params={"q": "dogwifhat"}, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            pairs = data.get("pairs", [])
            log(f"  SUCCESS: Got {len(pairs)} pairs")
            if pairs:
                p = pairs[0]
                log(f"  First: {p.get('baseToken',{}).get('name','?')} / {p.get('quoteToken',{}).get('name','?')}")
                log(f"  Address: {p.get('baseToken',{}).get('address','?')}")
                log(f"  Price USD: {p.get('priceUsd','?')}")
                log(f"  Volume 24h: {p.get('volume',{}).get('h24','?')}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 2: Token pairs
    log("\n[Test] DexScreener Token Pairs - /token-pairs/v1/solana/{address}")
    try:
        r = requests.get(f"{base}/token-pairs/v1/solana/{TEST_TOKEN}", timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                log(f"  SUCCESS: Got {len(data)} pairs for token")
            else:
                pairs = data.get("pairs", data)
                log(f"  SUCCESS: Response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                log(f"  Sample: {json.dumps(data, indent=2)[:300]}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")

    # Test 3: Top boosted tokens (proxy for trending)
    log("\n[Test] DexScreener Top Boosts - /token-boosts/top/v1")
    try:
        r = requests.get(f"{base}/token-boosts/top/v1", timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                log(f"  SUCCESS: Got {len(data)} boosted tokens")
                if data:
                    log(f"  First: {json.dumps(data[0], indent=2)[:200]}")
            else:
                log(f"  Response: {json.dumps(data, indent=2)[:300]}")
        else:
            log(f"  FAILED: {r.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")


def test_nansen():
    log("\n=== NANSEN API ===")
    base = "https://api.nansen.ai"
    headers = {"Authorization": f"Bearer {NANSEN_KEY}", "Accept": "application/json"}

    # Test: token metadata or any working endpoint
    log("\n[Test] Nansen API - checking available endpoints")
    try:
        # Try the token endpoint
        r = requests.get(f"{base}/v1/token/metadata", headers=headers,
                        params={"chain": "solana", "address": TEST_TOKEN}, timeout=15)
        log(f"  Status: {r.status_code}")
        if r.status_code == 200:
            log(f"  SUCCESS: {r.text[:300]}")
        else:
            log(f"  Response: {r.text[:300]}")
            # Try alternate auth
            headers2 = {"api-key": NANSEN_KEY, "Accept": "application/json"}
            r2 = requests.get(f"{base}/v1/token/metadata", headers=headers2,
                            params={"chain": "solana", "address": TEST_TOKEN}, timeout=15)
            log(f"  Alt auth status: {r2.status_code}")
            log(f"  Alt response: {r2.text[:300]}")
    except Exception as e:
        log(f"  ERROR: {e}")


if __name__ == "__main__":
    log(f"Phase 0: API Discovery - {datetime.now(timezone.utc).isoformat()}")
    log(f"API Keys loaded: Birdeye={'YES' if BIRDEYE_KEY else 'NO'}, Helius={'YES' if HELIUS_KEY else 'NO'}, Nansen={'YES' if NANSEN_KEY else 'NO'}")

    test_birdeye()
    test_helius()
    test_dexscreener()
    test_nansen()

    # Write results
    os.makedirs("data", exist_ok=True)
    with open("data/api_status.txt", "w") as f:
        f.write("\n".join(results))

    log("\n\nResults saved to data/api_status.txt")
