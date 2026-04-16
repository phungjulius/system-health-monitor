# System Health Monitor

A Python tool that collects CPU, memory, and disk metrics from a Linux system, runs them through a rule-based validation framework, and produces structured reports — all automated through a CI/CD pipeline on GitHub Actions.

The idea behind this project was to build something that mirrors real reliability testing work: you define what "healthy" looks like, measure the actual state of the system, and flag anything that doesn't match. Same principle used in production monitoring for embedded and critical systems.

---

## What it does

1. **Collects** — reads CPU usage from `/proc/stat`, memory from `/proc/meminfo`, disk from `df`, and top processes from `ps`
2. **Validates** — runs each metric through named rules with configurable thresholds; distinguishes between warnings and critical failures
3. **Reports** — saves both a machine-readable JSON report and a human-readable text summary
4. **Automates** — GitHub Actions runs the pipeline on every push, pull request, and every 3 hours on a schedule

---

## Project structure

```
system-health-monitor/
├── system_collector.py         # Collects CPU / memory / disk / process metrics
├── validator.py                # Validation framework — rules and thresholds
├── reporter.py                 # Saves JSON + text reports, cleans up old ones
├── main.py                     # Entrypoint: collect → validate → report → exit
├── setup_and_run.sh            # Bash script: install deps, run tests, run monitor
├── requirements.txt
├── pytest.ini
├── tests/
│   └── test_validator.py       # 25 unit tests covering all validation rules
├── reports/                    # Auto-generated reports (git-ignored)
└── .github/
    └── workflows/
        └── ci.yml              # Two-job CI/CD pipeline
```

---

## How to run locally

**Requirements:** Python 3.10+, Linux (or WSL on Windows)

```bash
git clone https://github.com/YOUR_USERNAME/system-health-monitor.git
cd system-health-monitor

pip install -r requirements.txt

# run unit tests only
pytest tests/ -v

# run the full monitor
python main.py

# or use the bash script (does everything in one go)
bash setup_and_run.sh
```

---

## Validation framework

`validator.py` defines independent, named rules. Each rule takes the snapshot dict and returns `ValidationResult` objects with a `passed` flag, a human-readable `detail`, and a `level` of either `warning` or `critical`.

### Default thresholds

| Metric | Warning | Critical |
|---|---|---|
| CPU usage | > 85% | > 95% |
| RAM usage | > 80% | — |
| Swap usage | > 50% | — |
| Disk usage | > 85% | > 95% |
| Single process CPU | > 80% | — |

Edit `THRESHOLDS` in `validator.py` to adjust any limit without touching the rule logic.

---

## CI/CD pipeline

The pipeline in `.github/workflows/ci.yml` has two jobs:

**Job 1 — unit tests**
Runs all 25 pytest tests against the validation framework using synthetic data. No real system calls needed — runs identically on any machine.

**Job 2 — live health check** (only runs if job 1 passes)
Spins up a fresh Ubuntu environment, collects real system metrics, runs them through the validation framework, and uploads the JSON and text reports as downloadable artifacts.

Exit codes:
- `0` — all checks passed
- `1` — warnings detected (pipeline continues)
- `2` — critical failures (pipeline fails the build)

---

## Example output

```
════════════════════════════════════════════════════════
  System Health Monitor
════════════════════════════════════════════════════════

Collecting system metrics...
  CPU   : 12.4%
  Memory: 38.7% used
  Disks : 1 partition(s) found

Running validation checks...
  [PASS] snapshot_freshness: Snapshot has a valid timestamp
  [PASS] cpu_usage_normal: CPU at 12.4% (limit 85%)
  [PASS] cpu_usage_critical: CPU at 12.4% (hard ceiling 95%)
  [PASS] memory_ram: RAM 6192 MB / 16000 MB = 38.7% (limit 80%)
  [PASS] memory_swap: Swap 0 MB / 4000 MB = 0.0% (limit 50%)
  [PASS] disk_critical:/: / at 54.2% used — 45.8 GB free (critical limit 95%)
  [PASS] disk_warning:/: / at 54.2% used (warning limit 85%)
  [PASS] process_cpu:pid=1: PID 1 using 0.0% CPU — [systemd] (limit 80%)

════════════════════════════════════════════════════════
  Passed   : 8 / 8
  Warnings : 0
  Critical : 0

  STATUS: ALL CHECKS PASSED
════════════════════════════════════════════════════════
```

---

## Author

Julius Phung — MSc Communications Engineering student, Aalto University
