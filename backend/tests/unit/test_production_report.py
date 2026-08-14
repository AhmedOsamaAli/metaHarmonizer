from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "production_report.py"
SPEC = importlib.util.spec_from_file_location("production_report", SCRIPT)
assert SPEC and SPEC.loader
production_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production_report)


def healthy_check() -> dict:
    return {
        "filesystem": {"used_percent": 50.0},
        "public_health": {"status": 200},
        "metrics": {"configured": True, "status": 200, "server_errors_delta": 0},
        "services": {name: "healthy" for name in ("api", "worker", "postgres", "redis")},
        "queue_depth": 0,
        "database": {"unresolved_failures": 0, "failed_jobs_24h": 0},
        "backup_timer": {"ActiveState": "active"},
        "backup_service": {"Result": "success", "ExecMainExitTimestamp": "Fri 2026-08-14 01:00:00 UTC"},
        "kb_timer": {"ActiveState": "active"},
        "kb_service": {"Result": "success"},
    }


def test_parse_size_and_forecast():
    assert production_report.parse_size("12.21GB") == 12_210_000_000
    assert production_report.parse_size("417.6MB (4%)".split(" ", 1)[0]) == 417_600_000
    assert production_report.forecast_days(60, 70, 2) == 5
    assert production_report.forecast_days(60, 70, 0) is None


def test_assess_applies_measured_thresholds():
    check = healthy_check()
    check["filesystem"]["used_percent"] = 70.0
    check["queue_depth"] = 160
    issues = production_report.assess(check, require_backup=False)
    assert {issue["code"] for issue in issues} == {"disk_warning", "queue_warning"}
    assert all(issue["severity"] == "warning" for issue in issues)


def test_assess_keeps_unconfigured_backup_visible_without_false_claim():
    check = healthy_check()
    check["backup_timer"]["ActiveState"] = "inactive"
    warning = production_report.assess(check, require_backup=False)
    critical = production_report.assess(check, require_backup=True)
    assert warning[0] == {
        "severity": "warning",
        "code": "backup_inactive",
        "message": "Encrypted off-host backup timer is not active.",
    }
    assert critical[0]["severity"] == "critical"


def test_metrics_require_auth_and_alert_on_new_server_errors():
    check = healthy_check()
    check["metrics"] = {"configured": False, "status": 0, "server_errors_delta": 0}
    assert production_report.assess(check, require_backup=False)[0]["code"] == "metrics_auth_unconfigured"

    check["metrics"] = {"configured": True, "status": 200, "server_errors_delta": 2}
    issue = production_report.assess(check, require_backup=False)[0]
    assert issue["code"] == "server_errors"
    assert issue["severity"] == "critical"


def test_prometheus_server_error_count_and_counter_reset():
    text = '\n'.join([
        'http_requests_total{method="GET",path="/healthz",status="200"} 20',
        'http_requests_total{method="GET",path="/api",status="500"} 2',
        'http_requests_total{method="POST",path="/api",status="503"} 3',
    ])
    assert production_report.count_server_errors(text) == 5
    current = {"metrics": {"server_errors_total": 2}}
    production_report.add_counter_deltas(current, {"metrics": {"server_errors_total": 5}})
    assert current["metrics"]["server_errors_delta"] == 0


def test_alert_retries_after_delivery_becomes_available(tmp_path: Path, monkeypatch):
    issues = [{"severity": "warning", "code": "test", "message": "Test warning."}]
    delivered: list[str] = []
    monkeypatch.setattr(production_report, "send_webhook", lambda message: False)
    production_report.alert_if_needed(issues, tmp_path)

    monkeypatch.setattr(
        production_report,
        "send_webhook",
        lambda message: delivered.append(message) is None or True,
    )
    production_report.alert_if_needed(issues, tmp_path)
    assert len(delivered) == 1

    production_report.alert_if_needed([], tmp_path)
    production_report.alert_if_needed(issues, tmp_path)
    assert len(delivered) == 2


def test_stale_backup_and_failed_kb_update_are_reported():
    check = healthy_check()
    check["backup_service"]["ExecMainExitTimestamp"] = "n/a"
    check["kb_service"]["Result"] = "exit-code"
    issues = production_report.assess(check, require_backup=True)
    assert {issue["code"] for issue in issues} == {"backup_stale", "kb_update_failed"}


def test_systemd_timestamp_age():
    now = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
    assert production_report.timestamp_age_hours("Fri 2026-08-14 01:00:00 UTC", now=now) == 36
    assert production_report.timestamp_age_hours("n/a", now=now) is None


def test_snapshot_retention_keeps_newest_files(tmp_path: Path):
    for name in ("001.json", "002.json", "003.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    production_report.prune_snapshots(tmp_path, keep=2)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["002.json", "003.json"]