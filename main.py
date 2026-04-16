#!/usr/bin/env python3
"""
main.py

Entrypoint for the system health monitor.
Runs the full pipeline:
  1. Collect system metrics
  2. Validate against thresholds
  3. Save reports (JSON + text)
  4. Print summary
  5. Exit with code 1 if any check failed — this is what makes
     the CI/CD pipeline go red so you notice problems immediately.
"""

import sys
from system_collector import collect_snapshot
from validator        import run_all_checks, summarise
from reporter         import save_json_report, save_text_report, cleanup_old_reports


def main():
    print("\n" + "=" * 56)
    print("  System Health Monitor")
    print("=" * 56 + "\n")

    # step 1: collect
    snapshot = collect_snapshot()

    # step 2: validate
    print("\nRunning validation checks...")
    results = run_all_checks(snapshot)
    for r in results:
        print(f"  {r}")

    # step 3: summarise
    summary = summarise(results)
    print(f"\n{'=' * 56}")
    print(f"  Passed   : {summary['passed']} / {summary['total']}")
    print(f"  Warnings : {summary['warnings']}")
    print(f"  Critical : {summary['critical']}")

    # step 4: save reports
    json_path = save_json_report(snapshot, results, summary)
    txt_path  = save_text_report(snapshot, results, summary)
    print(f"\n  JSON report → {json_path}")
    print(f"  Text report → {txt_path}")

    # step 5: cleanup old reports
    cleanup_old_reports()

    # step 6: exit code
    print()
    if summary["ok"]:
        print("  STATUS: ALL CHECKS PASSED")
        print("=" * 56 + "\n")
        sys.exit(0)
    elif summary["has_critical"]:
        print("  STATUS: CRITICAL FAILURES DETECTED")
        print("=" * 56 + "\n")
        sys.exit(2)    # exit 2 = critical issues
    else:
        print("  STATUS: WARNINGS DETECTED")
        print("=" * 56 + "\n")
        sys.exit(1)    # exit 1 = warnings


if __name__ == "__main__":
    main()
