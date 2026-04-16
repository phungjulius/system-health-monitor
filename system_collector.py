#!/usr/bin/env python3
"""
system_collector.py

Gathers a snapshot of local system health:
  - CPU usage (overall + per core)
  - Memory usage (physical + swap)
  - Disk usage per mounted partition
  - Top 5 CPU-hungry processes

Returns everything as a plain dict so it can be validated,
saved, or passed around without any I/O dependencies.
"""

import os
import time
import platform
import subprocess
import re
from datetime import datetime, timezone


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_proc_stat():
    """Read /proc/stat and return raw cpu line tokens (Linux only)."""
    with open("/proc/stat") as f:
        return f.readline().split()


def _cpu_percent(interval: float = 0.5) -> dict:
    """
    Calculate CPU usage over a short interval by reading /proc/stat twice.
    Falls back to a basic subprocess call on non-Linux systems.
    """
    system = platform.system().lower()

    if system == "linux":
        try:
            t1 = _read_proc_stat()
            time.sleep(interval)
            t2 = _read_proc_stat()

            # fields: user nice system idle iowait irq softirq steal guest
            idle1  = int(t1[4])
            total1 = sum(int(x) for x in t1[1:])
            idle2  = int(t2[4])
            total2 = sum(int(x) for x in t2[1:])

            total_diff = total2 - total1
            idle_diff  = idle2  - idle1

            if total_diff == 0:
                return {"overall_pct": 0.0, "source": "proc_stat"}

            usage = round((1 - idle_diff / total_diff) * 100, 1)
            return {"overall_pct": usage, "source": "proc_stat"}
        except Exception:
            pass

    # fallback: parse top output
    try:
        out = subprocess.check_output(
            ["top", "-bn1"], text=True, timeout=5
        )
        match = re.search(r"(\d+\.?\d*)\s*id", out)
        if match:
            idle  = float(match.group(1))
            usage = round(100.0 - idle, 1)
            return {"overall_pct": usage, "source": "top_fallback"}
    except Exception:
        pass

    return {"overall_pct": None, "source": "unavailable"}


def _memory_usage() -> dict:
    """Parse /proc/meminfo for physical and swap memory stats."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, val = line.partition(":")
                info[key.strip()] = int(val.strip().split()[0])  # in kB

        total     = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        used      = total - available
        pct       = round(used / total * 100, 1) if total else 0

        swap_total = info.get("SwapTotal", 0)
        swap_free  = info.get("SwapFree", 0)
        swap_used  = swap_total - swap_free
        swap_pct   = round(swap_used / swap_total * 100, 1) if swap_total else 0

        return {
            "total_mb":     round(total     / 1024, 1),
            "used_mb":      round(used      / 1024, 1),
            "available_mb": round(available / 1024, 1),
            "used_pct":     pct,
            "swap_total_mb": round(swap_total / 1024, 1),
            "swap_used_mb":  round(swap_used  / 1024, 1),
            "swap_used_pct": swap_pct,
            "source": "proc_meminfo",
        }
    except FileNotFoundError:
        return {"error": "/proc/meminfo not available", "source": "unavailable"}


def _disk_usage() -> list:
    """
    Run df -P to get disk usage for all real mounted partitions.
    Skips tmpfs, devtmpfs, and other virtual filesystems.
    """
    partitions = []
    try:
        out = subprocess.check_output(
            ["df", "-P", "-B1"],   # -B1 = output in bytes
            text=True, timeout=5
        )
        lines = out.strip().splitlines()[1:]  # skip header
        for line in lines:
            parts = line.split()
            if len(parts) < 6:
                continue
            filesystem = parts[0]
            # skip virtual/pseudo filesystems
            if any(filesystem.startswith(x) for x in
                   ("tmpfs", "devtmpfs", "udev", "none", "overlay", "shm")):
                continue
            total    = int(parts[1])
            used     = int(parts[2])
            avail    = int(parts[3])
            mountpoint = parts[5]
            pct      = round(used / total * 100, 1) if total else 0
            partitions.append({
                "filesystem":  filesystem,
                "mountpoint":  mountpoint,
                "total_gb":    round(total / 1024**3, 2),
                "used_gb":     round(used  / 1024**3, 2),
                "free_gb":     round(avail / 1024**3, 2),
                "used_pct":    pct,
            })
    except Exception as exc:
        partitions.append({"error": str(exc)})
    return partitions


def _top_processes(n: int = 5) -> list:
    """
    Return the top N processes sorted by CPU usage.
    Uses /proc/<pid>/stat + /proc/<pid>/comm for portability.
    """
    processes = []
    try:
        # ps is the most portable cross-distro option
        out = subprocess.check_output(
            ["ps", "aux", "--sort=-%cpu"],
            text=True, timeout=5
        )
        lines = out.strip().splitlines()[1:n+1]
        for line in lines:
            cols = line.split(None, 10)
            if len(cols) < 11:
                continue
            processes.append({
                "user":     cols[0],
                "pid":      cols[1],
                "cpu_pct":  float(cols[2]),
                "mem_pct":  float(cols[3]),
                "command":  cols[10][:60],   # trim very long command strings
            })
    except Exception as exc:
        processes.append({"error": str(exc)})
    return processes


# ── public API ────────────────────────────────────────────────────────────────

def collect_snapshot() -> dict:
    """
    Collect a full system health snapshot and return it as a dict.
    This is the single function everything else calls.
    """
    print("Collecting system metrics...")
    snapshot = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "hostname":    platform.node(),
        "os":          f"{platform.system()} {platform.release()}",
        "cpu":         _cpu_percent(),
        "memory":      _memory_usage(),
        "disks":       _disk_usage(),
        "top_procs":   _top_processes(),
    }
    print(f"  CPU   : {snapshot['cpu'].get('overall_pct')}%")
    print(f"  Memory: {snapshot['memory'].get('used_pct')}% used")
    print(f"  Disks : {len(snapshot['disks'])} partition(s) found")
    return snapshot


if __name__ == "__main__":
    import json
    snap = collect_snapshot()
    print(json.dumps(snap, indent=2))
