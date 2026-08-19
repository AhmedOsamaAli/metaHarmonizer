from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


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
        "active_users_5m": 0,
        "database": {
            "registered_users": 4,
            "unresolved_failures": 0,
            "failed_jobs_24h": 0,
            "oldest_queued_seconds": 0,
        },
        "backup_timer": {"ActiveState": "active"},
        "backup_service": {"Result": "success", "ExecMainExitTimestamp": "Fri 2026-08-14 01:00:00 UTC"},
        "backup_last_success_age_hours": 1.0,
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


def test_assess_active_user_window_uses_planning_thresholds():
    check = healthy_check()
    check["active_users_5m"] = 40
    assert production_report.assess(check, require_backup=False)[0]["code"] == "active_users_warning"
    check["active_users_5m"] = 50
    issue = production_report.assess(check, require_backup=False)[0]
    assert issue["code"] == "active_users_planning_limit"
    assert issue["severity"] == "warning"


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
    check["backup_last_success_age_hours"] = None
    check["kb_service"]["Result"] = "exit-code"
    issues = production_report.assess(check, require_backup=True)
    assert {issue["code"] for issue in issues} == {"backup_stale", "kb_update_failed"}


def test_queue_wait_is_reported_independently_of_depth():
    # A short queue of slow jobs is still a long wait for the curator.
    check = healthy_check()
    check["database"]["oldest_queued_seconds"] = 360
    issues = production_report.assess(check, require_backup=False)
    assert [i["code"] for i in issues] == ["queue_wait_warning"]
    assert "6 minutes" in issues[0]["message"]

    check["database"]["oldest_queued_seconds"] = 1200
    issue = production_report.assess(check, require_backup=False)[0]
    assert issue["code"] == "queue_wait_critical"
    assert issue["severity"] == "critical"


def capacity_check(used_percent: float = 72.0) -> dict:
    check = healthy_check()
    check["filesystem"] = {
        "total_bytes": 45 * 1024**3,
        "used_bytes": int(45 * 1024**3 * used_percent / 100),
        "free_bytes": int(45 * 1024**3 * (100 - used_percent) / 100),
        "used_percent": used_percent,
    }
    check["docker_storage"] = {
        "Images": {"size_bytes": 9 * 1024**3, "reclaimable_bytes": 1024**3},
        "Build Cache": {"size_bytes": 8 * 1024**3, "reclaimable_bytes": 8 * 1024**3},
    }
    return check


def test_capacity_summary_reports_current_sizes():
    summary = production_report.capacity_summary(capacity_check())
    assert "72.0% used" in summary
    assert "of 45.0 GiB" in summary
    assert "Docker 17.0 GiB" in summary
    assert "reclaimable" in summary


def test_alert_message_includes_current_capacity(tmp_path: Path, monkeypatch):
    delivered: list[str] = []
    monkeypatch.setattr(production_report, "send_webhook", lambda message: delivered.append(message) is None or True)
    issues = [{"severity": "warning", "code": "disk_warning", "message": "Filesystem use is 72.0%."}]

    production_report.alert_if_needed(issues, tmp_path, capacity=production_report.capacity_summary(capacity_check()))

    assert "Current capacity:" in delivered[0]
    assert "12.6 GiB free" in delivered[0]


def test_reclaim_runs_only_above_threshold_and_respects_cooldown(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def fake_reclaim(**_kwargs):
        calls.append("reclaim")
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "freed_bytes": 3 * 1024**3,
            "freed_by_type": {"Build Cache": 3 * 1024**3},
            "docker_storage": {"Images": {"size_bytes": 9 * 1024**3, "reclaimable_bytes": 0}},
        }

    monkeypatch.setattr(production_report, "reclaim_storage", fake_reclaim)
    monkeypatch.setattr(production_report, "filesystem_usage", lambda: capacity_check(61.0)["filesystem"])

    below = capacity_check(65.0)
    assert production_report.maybe_reclaim(below, tmp_path) is None
    assert calls == []

    above = capacity_check(72.0)
    result = production_report.maybe_reclaim(above, tmp_path)
    assert result["freed_bytes"] == 3 * 1024**3
    assert above["filesystem"]["used_percent"] == 61.0
    assert "automatic cleanup freed 3.0 GiB" in production_report.capacity_summary(above)

    assert production_report.maybe_reclaim(capacity_check(72.0), tmp_path) is None
    assert calls == ["reclaim"]


def test_auto_prune_can_be_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPS_AUTO_PRUNE", "0")
    monkeypatch.setattr(production_report, "reclaim_storage", lambda **_: pytest.fail("must not prune"))
    assert production_report.maybe_reclaim(capacity_check(99.0), tmp_path) is None


def test_reclaim_escalates_when_still_above_threshold(tmp_path: Path, monkeypatch):
    passes: list[bool] = []
    usage = iter([capacity_check(88.0)["filesystem"], capacity_check(62.0)["filesystem"]])

    def fake_reclaim(*, cap_build_cache=False, **_kwargs):
        passes.append(cap_build_cache)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capped_build_cache": cap_build_cache,
            "freed_bytes": 5 * 1024**3 if cap_build_cache else 0,
            "freed_by_type": {"Build Cache": 5 * 1024**3 if cap_build_cache else 0},
            "docker_storage": {"Images": {"size_bytes": 9 * 1024**3, "reclaimable_bytes": 0}},
        }

    monkeypatch.setattr(production_report, "reclaim_storage", fake_reclaim)
    monkeypatch.setattr(production_report, "filesystem_usage", lambda: next(usage))

    check = capacity_check(90.0)
    result = production_report.maybe_reclaim(check, tmp_path)

    assert passes == [False, True]
    assert result["freed_bytes"] == 5 * 1024**3
    assert check["filesystem"]["used_percent"] == 62.0


def test_systemd_timestamp_age():
    now = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
    assert production_report.timestamp_age_hours("Fri 2026-08-14 01:00:00 UTC", now=now) == 36
    assert production_report.timestamp_age_hours("n/a", now=now) is None


def test_backup_success_marker_age(tmp_path: Path):
    marker = tmp_path / "last-success"
    assert production_report.file_age_hours(marker) is None
    marker.write_text("", encoding="utf-8")
    age = production_report.file_age_hours(marker)
    assert age is not None and age < 0.01


def test_snapshot_retention_keeps_newest_files(tmp_path: Path):
    for name in ("001.json", "002.json", "003.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    production_report.prune_snapshots(tmp_path, keep=2)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["002.json", "003.json"]