"""
tests/test_validator.py

Unit tests for every validation rule in validator.py.
Each test uses hand-crafted snapshot dicts so no real system
calls are made — the tests run identically on any machine,
including the CI runner in GitHub Actions.

Run with: pytest tests/ -v
"""

import pytest
from validator import (
    check_cpu_usage,
    check_memory_usage,
    check_disk_usage,
    check_process_cpu,
    check_snapshot_freshness,
    run_all_checks,
    summarise,
    THRESHOLDS,
)


# ── shared fixtures ───────────────────────────────────────────────────────────

def make_snapshot(cpu_pct=20.0, ram_pct=40.0, swap_pct=10.0,
                  disk_pct=50.0, proc_cpu=5.0, has_timestamp=True):
    """Build a synthetic snapshot dict for testing. Defaults are all healthy."""
    return {
        "timestamp": "2026-04-10T12:00:00+00:00" if has_timestamp else None,
        "hostname":  "test-host",
        "os":        "Linux 6.1",
        "cpu": {
            "overall_pct": cpu_pct,
            "source":      "proc_stat",
        },
        "memory": {
            "total_mb":      16000,
            "used_mb":       round(16000 * ram_pct / 100),
            "available_mb":  round(16000 * (1 - ram_pct / 100)),
            "used_pct":      ram_pct,
            "swap_total_mb": 4000,
            "swap_used_mb":  round(4000 * swap_pct / 100),
            "swap_used_pct": swap_pct,
            "source":        "proc_meminfo",
        },
        "disks": [
            {
                "filesystem": "/dev/sda1",
                "mountpoint": "/",
                "total_gb":   100.0,
                "used_gb":    round(100 * disk_pct / 100, 1),
                "free_gb":    round(100 * (1 - disk_pct / 100), 1),
                "used_pct":   disk_pct,
            }
        ],
        "top_procs": [
            {
                "user": "julius", "pid": "1234",
                "cpu_pct": proc_cpu, "mem_pct": 1.2,
                "command": "python3 main.py",
            }
        ],
    }


# ── snapshot freshness ────────────────────────────────────────────────────────

class TestSnapshotFreshness:
    def test_passes_when_timestamp_present(self):
        snap = make_snapshot()
        results = check_snapshot_freshness(snap)
        assert results[0].passed

    def test_fails_when_timestamp_missing(self):
        snap = make_snapshot(has_timestamp=False)
        results = check_snapshot_freshness(snap)
        assert not results[0].passed

    def test_result_is_critical_level(self):
        snap = make_snapshot(has_timestamp=False)
        assert check_snapshot_freshness(snap)[0].level == "critical"


# ── CPU checks ────────────────────────────────────────────────────────────────

class TestCPUUsage:
    def test_passes_with_normal_cpu(self):
        snap = make_snapshot(cpu_pct=30.0)
        results = check_cpu_usage(snap)
        assert all(r.passed for r in results)

    def test_warning_triggered_above_limit(self):
        limit = THRESHOLDS["max_cpu_pct"]
        snap  = make_snapshot(cpu_pct=limit + 5)
        results = check_cpu_usage(snap)
        warning = next(r for r in results if r.rule == "cpu_usage_normal")
        assert not warning.passed

    def test_critical_not_triggered_below_hard_ceiling(self):
        # between normal limit and hard ceiling — warning fires, critical doesn't
        normal_limit = THRESHOLDS["max_cpu_pct"]
        hard_limit   = THRESHOLDS["max_cpu_sustained_pct"]
        cpu_val = (normal_limit + hard_limit) / 2
        snap    = make_snapshot(cpu_pct=cpu_val)
        results = check_cpu_usage(snap)
        critical = next(r for r in results if r.rule == "cpu_usage_critical")
        assert critical.passed

    def test_critical_triggered_above_hard_ceiling(self):
        limit = THRESHOLDS["max_cpu_sustained_pct"]
        snap  = make_snapshot(cpu_pct=limit + 1)
        results = check_cpu_usage(snap)
        critical = next(r for r in results if r.rule == "cpu_usage_critical")
        assert not critical.passed

    def test_handles_missing_cpu_data(self):
        snap = make_snapshot()
        snap["cpu"]["overall_pct"] = None
        results = check_cpu_usage(snap)
        assert not results[0].passed

    def test_value_stored_in_result(self):
        snap = make_snapshot(cpu_pct=55.0)
        results = check_cpu_usage(snap)
        normal = next(r for r in results if r.rule == "cpu_usage_normal")
        assert normal.value == 55.0


# ── Memory checks ─────────────────────────────────────────────────────────────

class TestMemoryUsage:
    def test_passes_with_healthy_memory(self):
        snap = make_snapshot(ram_pct=40.0, swap_pct=5.0)
        results = check_memory_usage(snap)
        assert all(r.passed for r in results)

    def test_fails_when_ram_too_high(self):
        limit = THRESHOLDS["max_memory_pct"]
        snap  = make_snapshot(ram_pct=limit + 5)
        results = check_memory_usage(snap)
        ram = next(r for r in results if r.rule == "memory_ram")
        assert not ram.passed

    def test_fails_when_swap_too_high(self):
        limit = THRESHOLDS["max_swap_pct"]
        snap  = make_snapshot(swap_pct=limit + 10)
        results = check_memory_usage(snap)
        swap = next(r for r in results if r.rule == "memory_swap")
        assert not swap.passed

    def test_swap_skipped_when_no_swap_configured(self):
        snap = make_snapshot()
        snap["memory"]["swap_total_mb"] = 0
        results = check_memory_usage(snap)
        swap = next(r for r in results if r.rule == "memory_swap")
        # should still pass (not fail) — no swap is not an error
        assert swap.passed

    def test_handles_missing_meminfo(self):
        snap = make_snapshot()
        snap["memory"] = {"error": "/proc/meminfo not available", "source": "unavailable"}
        results = check_memory_usage(snap)
        assert not results[0].passed


# ── Disk checks ───────────────────────────────────────────────────────────────

class TestDiskUsage:
    def test_passes_with_healthy_disk(self):
        snap = make_snapshot(disk_pct=50.0)
        results = check_disk_usage(snap)
        assert all(r.passed for r in results)

    def test_warning_triggered_above_threshold(self):
        limit = THRESHOLDS["max_disk_pct"]
        snap  = make_snapshot(disk_pct=limit + 3)
        results = check_disk_usage(snap)
        warnings = [r for r in results if "disk_warning" in r.rule and not r.passed]
        assert len(warnings) > 0

    def test_critical_triggered_above_critical_threshold(self):
        limit = THRESHOLDS["critical_disk_pct"]
        snap  = make_snapshot(disk_pct=limit + 1)
        results = check_disk_usage(snap)
        criticals = [r for r in results if "disk_critical" in r.rule and not r.passed]
        assert len(criticals) > 0

    def test_fails_when_no_partitions_found(self):
        snap = make_snapshot()
        snap["disks"] = []
        results = check_disk_usage(snap)
        assert not results[0].passed

    def test_multiple_partitions_checked_independently(self):
        snap = make_snapshot()
        # add a second partition with high usage
        snap["disks"].append({
            "filesystem": "/dev/sdb1",
            "mountpoint": "/data",
            "total_gb": 500.0, "used_gb": 480.0,
            "free_gb": 20.0, "used_pct": 96.0,
        })
        results = check_disk_usage(snap)
        data_criticals = [r for r in results if "/data" in r.rule and not r.passed]
        assert len(data_criticals) > 0


# ── Process CPU checks ────────────────────────────────────────────────────────

class TestProcessCPU:
    def test_passes_with_low_process_cpu(self):
        snap = make_snapshot(proc_cpu=5.0)
        results = check_process_cpu(snap)
        assert all(r.passed for r in results)

    def test_fails_when_process_hogs_cpu(self):
        limit = THRESHOLDS["max_single_proc_cpu"]
        snap  = make_snapshot(proc_cpu=limit + 5)
        results = check_process_cpu(snap)
        assert any(not r.passed for r in results)

    def test_rule_name_includes_pid(self):
        snap    = make_snapshot()
        results = check_process_cpu(snap)
        assert any("1234" in r.rule for r in results)

    def test_handles_empty_process_list(self):
        snap = make_snapshot()
        snap["top_procs"] = []
        results = check_process_cpu(snap)
        assert results == []


# ── Full framework integration ────────────────────────────────────────────────

class TestFullFramework:
    def test_all_pass_with_healthy_snapshot(self):
        snap    = make_snapshot()
        results = run_all_checks(snap)
        summary = summarise(results)
        assert summary["ok"] is True
        assert summary["critical"] == 0
        assert summary["warnings"] == 0

    def test_critical_detected_with_extreme_cpu(self):
        snap    = make_snapshot(cpu_pct=99.0)
        results = run_all_checks(snap)
        summary = summarise(results)
        assert summary["has_critical"] is True

    def test_failures_detected_with_bad_snapshot(self):
        snap = make_snapshot(
            cpu_pct=92.0,    # above warning limit
            ram_pct=90.0,    # above limit
            disk_pct=97.0,   # above critical
            proc_cpu=90.0,   # above limit
        )
        results = run_all_checks(snap)
        summary = summarise(results)
        assert summary["failed"] > 0
        assert summary["ok"] is False

    def test_summary_totals_are_consistent(self):
        snap    = make_snapshot()
        results = run_all_checks(snap)
        summary = summarise(results)
        assert summary["total"] == summary["passed"] + summary["failed"]

    def test_summarise_separates_warning_from_critical(self):
        # RAM warning but no critical
        limit = THRESHOLDS["max_memory_pct"]
        snap  = make_snapshot(ram_pct=limit + 5)
        results = run_all_checks(snap)
        summary = summarise(results)
        assert summary["warnings"] > 0
        # disk and CPU are healthy so no critical expected
        assert summary["has_critical"] is False
