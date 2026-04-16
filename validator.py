"""
validator.py

The validation framework. Each function is one named rule that takes
a system snapshot and returns a list of ValidationResult objects.

Adding a new check is as simple as writing a new function and calling
it inside run_all_checks(). No changes needed anywhere else.
"""

from dataclasses import dataclass, field
from typing import Any


# ── thresholds — tweak these to match the environment you're testing ──────────

THRESHOLDS = {
    # CPU
    "max_cpu_pct":           85.0,   # overall CPU usage limit
    "max_cpu_sustained_pct": 95.0,   # hard ceiling — no excuses above this

    # Memory
    "max_memory_pct":        80.0,   # physical RAM usage limit
    "max_swap_pct":          50.0,   # swap usage limit — heavy swap = trouble

    # Disk
    "max_disk_pct":          85.0,   # any partition above this is a warning
    "critical_disk_pct":     95.0,   # above this the system may start failing

    # Processes
    "max_single_proc_cpu":   80.0,   # one process shouldn't hog more than this
}


# ── result type ───────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    rule:    str
    passed:  bool
    detail:  str
    value:   Any = field(default=None)
    limit:   Any = field(default=None)
    level:   str = "warning"    # "warning" | "critical"

    def __str__(self):
        tag = "PASS" if self.passed else f"FAIL:{self.level.upper()}"
        return f"[{tag}] {self.rule}: {self.detail}"


# ── individual rules ──────────────────────────────────────────────────────────

def check_cpu_usage(snapshot: dict) -> list[ValidationResult]:
    """CPU usage must stay below the defined limit."""
    cpu_pct = snapshot.get("cpu", {}).get("overall_pct")

    if cpu_pct is None:
        return [ValidationResult(
            rule="cpu_usage", passed=False, level="warning",
            detail="CPU measurement not available on this platform",
        )]

    results = []

    limit = THRESHOLDS["max_cpu_pct"]
    results.append(ValidationResult(
        rule   = "cpu_usage_normal",
        passed = cpu_pct <= limit,
        detail = f"CPU at {cpu_pct}% (limit {limit}%)",
        value  = cpu_pct,
        limit  = limit,
        level  = "warning",
    ))

    hard_limit = THRESHOLDS["max_cpu_sustained_pct"]
    results.append(ValidationResult(
        rule   = "cpu_usage_critical",
        passed = cpu_pct <= hard_limit,
        detail = f"CPU at {cpu_pct}% (hard ceiling {hard_limit}%)",
        value  = cpu_pct,
        limit  = hard_limit,
        level  = "critical",
    ))

    return results


def check_memory_usage(snapshot: dict) -> list[ValidationResult]:
    """Physical RAM and swap must both be within limits."""
    mem = snapshot.get("memory", {})
    results = []

    if "error" in mem:
        return [ValidationResult(
            rule="memory_usage", passed=False, level="warning",
            detail=f"Memory info unavailable: {mem['error']}",
        )]

    # physical RAM
    ram_pct = mem.get("used_pct", 0)
    limit   = THRESHOLDS["max_memory_pct"]
    results.append(ValidationResult(
        rule   = "memory_ram",
        passed = ram_pct <= limit,
        detail = f"RAM {mem.get('used_mb')} MB / {mem.get('total_mb')} MB = {ram_pct}% (limit {limit}%)",
        value  = ram_pct,
        limit  = limit,
        level  = "warning",
    ))

    # swap
    swap_pct   = mem.get("swap_used_pct", 0)
    swap_limit = THRESHOLDS["max_swap_pct"]
    swap_total = mem.get("swap_total_mb", 0)

    if swap_total > 0:
        results.append(ValidationResult(
            rule   = "memory_swap",
            passed = swap_pct <= swap_limit,
            detail = f"Swap {mem.get('swap_used_mb')} MB / {swap_total} MB = {swap_pct}% (limit {swap_limit}%)",
            value  = swap_pct,
            limit  = swap_limit,
            level  = "warning",
        ))
    else:
        results.append(ValidationResult(
            rule="memory_swap", passed=True,
            detail="No swap configured — skipped",
            level="warning",
        ))

    return results


def check_disk_usage(snapshot: dict) -> list[ValidationResult]:
    """
    Each mounted partition must have disk usage below the threshold.
    Partitions above the critical threshold get flagged separately.
    """
    disks = snapshot.get("disks", [])
    results = []

    if not disks:
        return [ValidationResult(
            rule="disk_usage", passed=False, level="warning",
            detail="No disk partitions found",
        )]

    for disk in disks:
        if "error" in disk:
            results.append(ValidationResult(
                rule=f"disk:{disk.get('mountpoint', 'unknown')}",
                passed=False, level="warning",
                detail=f"Could not read disk info: {disk['error']}",
            ))
            continue

        pct   = disk["used_pct"]
        mount = disk["mountpoint"]
        limit = THRESHOLDS["max_disk_pct"]
        crit  = THRESHOLDS["critical_disk_pct"]

        # critical check first
        results.append(ValidationResult(
            rule   = f"disk_critical:{mount}",
            passed = pct <= crit,
            detail = f"{mount} at {pct}% used — {disk['free_gb']} GB free (critical limit {crit}%)",
            value  = pct,
            limit  = crit,
            level  = "critical",
        ))

        # normal threshold
        results.append(ValidationResult(
            rule   = f"disk_warning:{mount}",
            passed = pct <= limit,
            detail = f"{mount} at {pct}% used (warning limit {limit}%)",
            value  = pct,
            limit  = limit,
            level  = "warning",
        ))

    return results


def check_process_cpu(snapshot: dict) -> list[ValidationResult]:
    """No single process should be consuming an unreasonable amount of CPU."""
    procs = snapshot.get("top_procs", [])
    results = []
    limit = THRESHOLDS["max_single_proc_cpu"]

    for proc in procs:
        if "error" in proc:
            continue
        cpu  = proc.get("cpu_pct", 0)
        cmd  = proc.get("command", "unknown")[:40]
        pid  = proc.get("pid", "?")
        results.append(ValidationResult(
            rule   = f"process_cpu:pid={pid}",
            passed = cpu <= limit,
            detail = f"PID {pid} using {cpu}% CPU — [{cmd}] (limit {limit}%)",
            value  = cpu,
            limit  = limit,
            level  = "warning",
        ))

    return results


def check_snapshot_freshness(snapshot: dict) -> list[ValidationResult]:
    """
    Make sure the snapshot has a timestamp — a basic sanity check that
    the collection step actually ran and produced a real result.
    """
    has_ts = bool(snapshot.get("timestamp"))
    return [ValidationResult(
        rule   = "snapshot_freshness",
        passed = has_ts,
        detail = "Snapshot has a valid timestamp" if has_ts else "Snapshot is missing a timestamp",
        level  = "critical",
    )]


# ── framework entry point ─────────────────────────────────────────────────────

def run_all_checks(snapshot: dict) -> list[ValidationResult]:
    """
    Run every validation rule against the snapshot.
    To add a new rule: write a function above and call it here.
    """
    results: list[ValidationResult] = []
    results += check_snapshot_freshness(snapshot)
    results += check_cpu_usage(snapshot)
    results += check_memory_usage(snapshot)
    results += check_disk_usage(snapshot)
    results += check_process_cpu(snapshot)
    return results


def summarise(results: list[ValidationResult]) -> dict:
    """Count passes, failures (by level), and return overall ok status."""
    passed   = [r for r in results if r.passed]
    warnings = [r for r in results if not r.passed and r.level == "warning"]
    critical = [r for r in results if not r.passed and r.level == "critical"]

    return {
        "total":            len(results),
        "passed":           len(passed),
        "warnings":         len(warnings),
        "critical":         len(critical),
        "failed":           len(warnings) + len(critical),
        "ok":               len(warnings) + len(critical) == 0,
        "has_critical":     len(critical) > 0,
    }
