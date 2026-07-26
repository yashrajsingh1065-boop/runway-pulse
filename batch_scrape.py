#!/usr/bin/env python3
"""Batch scrape: SS26 all weeks + FW25 Paris image downloads."""

import subprocess
import sys
import time

PYTHON = sys.executable

FASHION_WEEKS = [
    "paris", "milan", "london", "new-york", "florence",
    "tokyo", "seoul", "copenhagen", "shanghai", "mumbai",
]


def run(cmd: list[str], label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}\n")
    start = time.time()
    result = subprocess.run(cmd, cwd="/Users/yashrajsingh/runway-pulse")
    elapsed = time.time() - start
    status = "OK" if result.returncode == 0 else "FAILED"
    print(f"\n  [{status}] {label} — {elapsed:.0f}s")
    return result.returncode == 0


def main():
    results = {}

    # Step 1: Download FW25 Paris images (already scraped, just need images)
    ok = run(
        [PYTHON, "-m", "ingestion.batch_download", "FW25"],
        "FW25 — Download images for 4,337 looks",
    )
    results["FW25 images"] = ok

    # Step 2: Scrape SS26 for each fashion week
    for week in FASHION_WEEKS:
        ok = run(
            [PYTHON, "main.py", "scrape", "runway", "--season", "SS26", "--week", week],
            f"SS26 — {week.title()} (scrape + images)",
        )
        results[f"SS26 {week}"] = ok

    # Summary
    print(f"\n{'='*60}")
    print("  BATCH COMPLETE")
    print(f"{'='*60}")
    for label, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  [{status}] {label}")


if __name__ == "__main__":
    main()
