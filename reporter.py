"""
reporter.py

Handles saving measurement results to disk in two formats:
  1. JSON — machine-readable, good for parsing or feeding into dashboards
  2. Plain text — human-readable summary you can read at a glance

Keeps the last 30 reports and cleans up older ones automatically.
"""

import json
from datetime import datetime
from pathlib import Path
from validator import ValidationResult

REPORT_DIR  = Path("reports")
MAX_REPORTS = 30


# ── JSON report ───────────────────────────────────────────────────────────────

def save_json_report(snapshot: dict, results: list, summary: dict) -> Path:
    """Save a full structured report as JSON."""
    REPORT_DIR.mkdir(exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"health_{ts}.json"

    report = {
        "summary":    summary,
        "snapshot":   snapshot,
        "validation": [
            {
                "rule":   r.rule,
                "passed": r.passed,
                "level":  r.level,
                "detail": r.detail,
                "value":  r.value,
                "limit":  r.limit,
            }
            for r in results
        ],
    }
    path.write_text(json.dumps(report, indent=2))
    return path


# ── Plain text report ─────────────────────────────────────────────────────────

def save_text_report(snapshot: dict, results: list, summary: dict) -> Path:
    """Save a human-readable text summary."""
    REPORT_DIR.mkdir(exist_ok=True)
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    path    = REPORT_DIR / f"health_{ts}.txt"
    lines   = []

    lines.append("=" * 56)
    lines.append("  SYSTEM HEALTH REPORT")
    lines.append("=" * 56)
    lines.append(f"  Generated : {snapshot.get('timestamp', 'unknown')}")
    lines.append(f"  Host      : {snapshot.get('hostname', 'unknown')}")
    lines.append(f"  OS        : {snapshot.get('os', 'unknown')}")
    lines.append("")

    # quick metrics
    cpu  = snapshot.get("cpu", {}).get("overall_pct", "N/A")
    mem  = snapshot.get("memory", {}).get("used_pct", "N/A")
    lines.append(f"  CPU usage : {cpu}%")
    lines.append(f"  RAM usage : {mem}%")

    for disk in snapshot.get("disks", []):
        if "error" not in disk:
            lines.append(f"  Disk {disk['mountpoint']:10s}: {disk['used_pct']}% used  ({disk['free_gb']} GB free)")

    lines.append("")
    lines.append("-" * 56)
    lines.append("  VALIDATION RESULTS")
    lines.append("-" * 56)
    for r in results:
        lines.append(f"  {r}")

    lines.append("")
    lines.append("-" * 56)
    lines.append(f"  Total   : {summary['total']}")
    lines.append(f"  Passed  : {summary['passed']}")
    lines.append(f"  Warnings: {summary['warnings']}")
    lines.append(f"  Critical: {summary['critical']}")
    lines.append("")
    status = "ALL CHECKS PASSED" if summary["ok"] else "CHECKS FAILED — review above"
    lines.append(f"  STATUS  : {status}")
    lines.append("=" * 56)

    path.write_text("\n".join(lines))
    return path


# ── cleanup ───────────────────────────────────────────────────────────────────

def cleanup_old_reports():
    """Keep only the most recent MAX_REPORTS files. Delete the rest."""
    if not REPORT_DIR.exists():
        return
    all_files = sorted(REPORT_DIR.glob("health_*"), key=lambda p: p.stat().st_mtime)
    to_delete = all_files[:-MAX_REPORTS] if len(all_files) > MAX_REPORTS else []
    for f in to_delete:
        f.unlink()
        print(f"  Removed old report: {f.name}")
