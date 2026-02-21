#!/usr/bin/env python3
"""
Production API validation — no auth required.
Tests all 3 arxiv papers end-to-end via Cloud Run backend.
"""
import sys
import os
import time
import json
import urllib.request
import urllib.error

BACKEND = "https://readpaper-backend-989182646968.us-central1.run.app"

CASES = [
    {"arxiv_id": "1706.03762", "deepdive": False, "name": "Case 1 — Attention Is All You Need"},
    {"arxiv_id": "2310.06825", "deepdive": True,  "name": "Case 2 — Mistral 7B + DeepDive"},
    {"arxiv_id": "2602.04705", "deepdive": False, "name": "Case 3 — DeepSeek-R1 (multi-file)"},
]

def req(url, data=None):
    headers = {"Content-Type": "application/json"}
    req_obj = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers=headers
    )
    try:
        with urllib.request.urlopen(req_obj, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return -1, {"error": str(e)}


def run_case(case):
    print(f"\n{'='*60}")
    print(f"  {case['name']}")
    print(f"  arxiv_id={case['arxiv_id']}  deepdive={case['deepdive']}")
    print(f"{'='*60}")

    arxiv_id = case["arxiv_id"]
    url = f"https://arxiv.org/abs/{arxiv_id}"

    print(f"  → POST /translate ...")
    status_code, resp = req(
        f"{BACKEND}/translate",
        data={"arxiv_url": url, "model": "flash", "deepdive": case["deepdive"]}
    )
    print(f"    Response ({status_code}): {str(resp)[:200]}")

    if status_code not in (200, 202):
        print(f"  ❌ /translate failed with {status_code}")
        return False

    # Poll /status
    print(f"  → Polling /status/{arxiv_id} ...")
    start = time.time()
    last_msg = ""
    last_pct = -1

    for attempt in range(360):  # max 30 min @ 5s interval
        time.sleep(5)
        s, data = req(f"{BACKEND}/status/{arxiv_id}")
        if s != 200:
            if attempt % 10 == 0:
                print(f"    [poll {attempt}] HTTP {s}")
            continue

        st = data.get("status", "?")
        msg = data.get("message", "")
        pct = data.get("progress_percent", 0)
        elapsed = int(time.time() - start)

        if msg != last_msg or pct != last_pct:
            print(f"    [{elapsed:5d}s] {st:12s} | {pct:3d}% | {msg}")
            last_msg = msg
            last_pct = pct

        if st == "completed":
            print(f"\n  ✅ COMPLETED in {elapsed}s")
            return True
        elif st == "failed":
            error_msg = data.get("message", data.get("compile_log", ""))[:300]
            print(f"\n  ❌ FAILED: {error_msg}")
            return False

    print(f"\n  ❌ TIMEOUT after 30 minutes (last: {last_msg} {last_pct}%)")
    return False


if __name__ == "__main__":
    print("ReadPaper Production API Validation (No Auth)")
    print(f"Backend: {BACKEND}")

    # Health check
    s, h = req(f"{BACKEND}/")
    print(f"Root endpoint ({s}): {str(h)[:100]}")

    results = []
    for case in CASES:
        passed = run_case(case)
        results.append((case["name"], passed))

    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    sys.exit(0 if all_passed else 1)
