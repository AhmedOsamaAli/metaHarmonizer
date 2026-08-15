#!/usr/bin/env python3
"""Production health checks, capacity snapshots, and growth reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GIB = 1024**3
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.prod.yml")
CORE_SERVICES = ("api", "worker", "postgres", "redis")
KB_KEYS = ("ENGINE_CACHE_VOLUME", "CORPUS_DATA_VOLUME", "HF_CACHE_VOLUME")


def run(command: list[str], *, timeout: int = 60) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    ).stdout.strip()


def compose(repo: Path, *args: str, timeout: int = 60) -> str:
    command = ["docker", "compose"]
    for file in COMPOSE_FILES:
        command.extend(("-f", file))
    command.extend(args)
    return run(command, timeout=timeout)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value.split(" #", 1)[0].strip().strip('"').strip("'")
    return values


def parse_size(value: str) -> int:
    match = re.fullmatch(r"([0-9.]+)\s*([KMGT]?B)", value.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Unsupported size: {value}")
    units = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    return round(float(match.group(1)) * units[match.group(2).upper()])


def human_bytes(value: int | float) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def forecast_days(current: int, threshold: int, daily_growth: float) -> float | None:
    if current >= threshold:
        return 0.0
    if daily_growth <= 0:
        return None
    return (threshold - current) / daily_growth


def fetch_health(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310
            return response.status, response.read(512).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, str(exc)


def fetch_metrics(url: str, token: str) -> tuple[int, str]:
    if not token:
        return 0, ""
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError):
        return 0, ""


def count_server_errors(metrics: str) -> float:
    total = 0.0
    for line in metrics.splitlines():
        if line.startswith("http_requests_total{") and re.search(r'status="5\d\d"', line):
            total += float(line.rsplit(" ", 1)[-1])
    return total


def systemd_state(unit: str) -> dict[str, str]:
    output = run(
        [
            "systemctl", "show", unit,
            "-p", "LoadState", "-p", "UnitFileState", "-p", "ActiveState",
            "-p", "Result", "-p", "LastTriggerUSec", "-p", "ExecMainExitTimestamp",
        ]
    )
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def database_metrics(repo: Path) -> dict[str, int]:
    sql = """select json_build_object(
      'database_bytes', pg_database_size(current_database()),
    'registered_users', (select count(*) from users),
      'studies', (select count(*) from studies),
      'queued_jobs', (select count(*) from job_runs where state='queued'),
      'running_jobs', (select count(*) from job_runs where state='running'),
      'failed_jobs_24h', (select count(*) from job_runs where state='failed' and created_at >= now() - interval '24 hours'),
      'unresolved_failures', (select count(*) from job_failures where resolved_at is null)
    );"""
    output = compose(
        repo,
        "exec", "-T", "postgres", "sh", "-c",
        f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "{sql}"',
    )
    return {key: int(value) for key, value in json.loads(output).items()}


def service_health(repo: Path) -> dict[str, str]:
    output = compose(repo, "ps", "--format", "json")
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    by_service = {row["Service"]: row for row in rows}
    result: dict[str, str] = {}
    for service in CORE_SERVICES:
        row = by_service.get(service)
        if row is None:
            result[service] = "missing"
        elif row.get("Health"):
            result[service] = row["Health"]
        else:
            result[service] = row.get("State", "unknown")
    return result


def collect_check(repo: Path) -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    status, body = fetch_health(os.getenv("OPS_HEALTH_URL", "https://metaharmonizer.online/healthz"))
    metrics_status, metrics_body = fetch_metrics(
        os.getenv("OPS_METRICS_URL", "https://metaharmonizer.online/metrics"),
        os.getenv("OPS_METRICS_BEARER_TOKEN", ""),
    )
    queue_depth = int(compose(repo, "exec", "-T", "redis", "redis-cli", "ZCARD", "arq:queue"))
    active_cutoff = time.time() - 5 * 60
    active_users_5m = int(
        compose(
            repo,
            "exec", "-T", "redis", "redis-cli", "EVAL",
            "redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1]); return redis.call('ZCARD', KEYS[1])",
            "1", "ops:active-users:5m", str(active_cutoff),
        )
    )
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "filesystem": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "used_percent": round(disk.used / disk.total * 100, 2),
        },
        "public_health": {"status": status, "body": body},
        "metrics": {
            "configured": bool(os.getenv("OPS_METRICS_BEARER_TOKEN", "")),
            "status": metrics_status,
            "server_errors_total": count_server_errors(metrics_body),
        },
        "services": service_health(repo),
        "queue_depth": queue_depth,
        "active_users_5m": active_users_5m,
        "database": database_metrics(repo),
        "backup_timer": systemd_state("metaharmonizer-backup.timer"),
        "backup_service": systemd_state("metaharmonizer-backup.service"),
        "kb_timer": systemd_state("metaharmonizer-kb-update.timer"),
        "kb_service": systemd_state("metaharmonizer-kb-update.service"),
    }


def assess(check: dict[str, Any], *, require_backup: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def add(severity: str, code: str, message: str) -> None:
        issues.append({"severity": severity, "code": code, "message": message})

    used = float(check["filesystem"]["used_percent"])
    if used >= 85:
        add("critical", "disk_stop", f"Filesystem use is {used:.1f}% (stop threshold 85%).")
    elif used >= 70:
        add("warning", "disk_warning", f"Filesystem use is {used:.1f}% (warning threshold 70%).")
    if check["public_health"]["status"] != 200:
        add("critical", "public_health", f"Public health returned {check['public_health']['status']}.")
    metrics = check.get("metrics", {})
    if not metrics.get("configured"):
        add("warning", "metrics_auth_unconfigured", "5xx alerting requires an admin-scoped metrics bearer token.")
    elif metrics.get("status") != 200:
        add("warning", "metrics_unavailable", f"Metrics returned HTTP {metrics.get('status', 0)}.")
    elif float(metrics.get("server_errors_delta", 0)) > 0:
        add("critical", "server_errors", f"{metrics['server_errors_delta']:.0f} new 5xx responses since the previous check.")
    for service, health in check["services"].items():
        if health not in {"healthy", "running"}:
            add("critical", f"service_{service}", f"{service} is {health}.")
    depth = int(check["queue_depth"])
    if depth >= 200:
        add("critical", "queue_full", f"Queue depth is {depth} (limit 200).")
    elif depth >= 160:
        add("warning", "queue_warning", f"Queue depth is {depth} (80% of limit 200).")
    active_users = int(check.get("active_users_5m", 0))
    if active_users >= 50:
        add(
            "warning",
            "active_users_planning_limit",
            f"{active_users} distinct authenticated users were active in five minutes (planning limit 50).",
        )
    elif active_users >= 40:
        add(
            "warning",
            "active_users_warning",
            f"{active_users} distinct authenticated users were active in five minutes (expansion trigger 40).",
        )
    database = check["database"]
    if database["unresolved_failures"]:
        add("critical", "unresolved_failures", f"{database['unresolved_failures']} job failures are unresolved.")
    elif database["failed_jobs_24h"]:
        add("warning", "recent_failures", f"{database['failed_jobs_24h']} jobs failed in 24 hours.")
    backup_active = check["backup_timer"].get("ActiveState") == "active"
    if not backup_active:
        add(
            "critical" if require_backup else "warning",
            "backup_inactive",
            "Encrypted off-host backup timer is not active.",
        )
    elif require_backup:
        backup_result = check["backup_service"].get("Result")
        if backup_result not in {"success", ""}:
            add("critical", "backup_failed", f"Last backup service result is {backup_result}.")
        backup_timestamp = check["backup_service"].get("ExecMainExitTimestamp", "")
        backup_age = timestamp_age_hours(backup_timestamp)
        if backup_age is None or backup_age > 36:
            message = "No completed backup timestamp is available." if backup_age is None else f"Last backup completed {backup_age:.1f} hours ago."
            add("critical", "backup_stale", message)
    if check["kb_timer"].get("ActiveState") != "active":
        add("warning", "kb_timer_inactive", "KB update timer is not active.")
    kb_result = check["kb_service"].get("Result")
    if kb_result not in {"success", ""}:
        add("warning", "kb_update_failed", f"Last KB update service result is {kb_result}.")
    return issues


def timestamp_age_hours(value: str, *, now: datetime | None = None) -> float | None:
    if not value or value == "n/a":
        return None
    try:
        parsed = datetime.strptime(value, "%a %Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    current = now or datetime.now(timezone.utc)
    return max((current - parsed).total_seconds() / 3600, 0.0)


def volume_size(volume: str) -> int:
    kib = int(
        run(
            [
                "docker", "run", "--rm", "-v", f"{volume}:/data:ro",
                "alpine:3.20", "sh", "-c", "du -sk /data | cut -f1",
            ],
            timeout=180,
        )
    )
    return kib * 1024


def docker_storage() -> dict[str, dict[str, int]]:
    output = run(["docker", "system", "df", "--format", "{{json .}}"])
    result: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        row = json.loads(line)
        result[row["Type"]] = {
            "size_bytes": parse_size(row["Size"]),
            "reclaimable_bytes": parse_size(row["Reclaimable"].split(" ", 1)[0]),
        }
    return result


def release_storage(repo: Path, state_dir: Path) -> dict[str, Any]:
    env = parse_env(repo / ".env")
    current_names = [env.get(key, "") for key in KB_KEYS]
    previous_path = state_dir.parent / "kb-deploy" / "previous-volumes"
    previous_names = previous_path.read_text(encoding="utf-8").splitlines() if previous_path.exists() else []
    if not previous_names and any(re.search(r"_[0-9a-f]{12}$", name) for name in current_names):
        defaults = (
            "metaharmonizer_engine_cache",
            "metaharmonizer_corpus_data",
            "metaharmonizer_hf_cache",
        )
        available = set(run(["docker", "volume", "ls", "--format", "{{.Name}}"] ).splitlines())
        if all(name in available for name in defaults):
            previous_names = list(defaults)

    def measure(names: list[str]) -> dict[str, Any]:
        volumes = {name: volume_size(name) for name in names if name}
        return {"volumes": volumes, "total_bytes": sum(volumes.values())}

    return {
        "current_sha256": env.get("KB_BUNDLE_SHA256", ""),
        "current": measure(current_names),
        "previous": measure(previous_names),
    }


def load_growth(state_dir: Path, current: dict[str, Any]) -> dict[str, Any]:
    snapshots = sorted((state_dir / "snapshots").glob("*.json"))
    if not snapshots:
        return {"sample_days": 0.0, "daily_total_growth_bytes": 0.0, "days_to_70_percent": None, "days_to_85_percent": None}
    oldest = json.loads(snapshots[0].read_text(encoding="utf-8"))
    first_time = datetime.fromisoformat(oldest["timestamp"])
    current_time = datetime.fromisoformat(current["timestamp"])
    days = max((current_time - first_time).total_seconds() / 86400, 0.0)
    if days < 0.5:
        return {"sample_days": round(days, 3), "daily_total_growth_bytes": 0.0, "days_to_70_percent": None, "days_to_85_percent": None}
    filesystem = current["filesystem"]
    daily = (filesystem["used_bytes"] - oldest["filesystem"]["used_bytes"]) / days
    return {
        "sample_days": round(days, 3),
        "daily_total_growth_bytes": round(daily),
        "days_to_70_percent": forecast_days(filesystem["used_bytes"], round(filesystem["total_bytes"] * 0.70), daily),
        "days_to_85_percent": forecast_days(filesystem["used_bytes"], round(filesystem["total_bytes"] * 0.85), daily),
    }


def build_report(repo: Path, state_dir: Path) -> dict[str, Any]:
    check = collect_check(repo)
    check["issues"] = assess(check, require_backup=os.getenv("OPS_REQUIRE_BACKUP", "0") == "1")
    check["docker_storage"] = docker_storage()
    check["kb_releases"] = release_storage(repo, state_dir)
    data_names = (
        "metaharmonizer_uploads", "metaharmonizer_pg_data", "metaharmonizer_redis_data",
        "metaharmonizer_schema_versions", "metaharmonizer_schema_aliases",
    )
    check["data_volumes"] = {name: volume_size(name) for name in data_names}
    check["growth"] = load_growth(state_dir, check)
    return check


def render_report(report: dict[str, Any]) -> str:
    filesystem = report["filesystem"]
    docker = report["docker_storage"]
    releases = report["kb_releases"]
    growth = report["growth"]
    lines = [
        f"# Production operations report - {report['timestamp'][:10]}",
        "",
        "## Status",
        "",
        f"- Public health: HTTP {report['public_health']['status']}",
        f"- Filesystem: {filesystem['used_percent']:.1f}% used; {human_bytes(filesystem['free_bytes'])} free",
        f"- Queue: {report['queue_depth']} pending; {report['database']['unresolved_failures']} unresolved failures",
        f"- Users: {report['active_users_5m']} distinct authenticated users active in five minutes; {report['database']['registered_users']} registered",
        f"- Backup timer: {report['backup_timer'].get('ActiveState', 'unknown')}",
        f"- KB update timer: {report['kb_timer'].get('ActiveState', 'unknown')}",
        "",
        "## Storage",
        "",
        "| Component | Size | Reclaimable |",
        "|---|---:|---:|",
    ]
    for name, values in docker.items():
        lines.append(f"| Docker {name.lower()} | {human_bytes(values['size_bytes'])} | {human_bytes(values['reclaimable_bytes'])} |")
    lines.extend([
        f"| Current KB release | {human_bytes(releases['current']['total_bytes'])} | - |",
        f"| Previous KB release | {human_bytes(releases['previous']['total_bytes'])} | removable after retention |",
    ])
    for name, size in report["data_volumes"].items():
        lines.append(f"| {name.removeprefix('metaharmonizer_')} | {human_bytes(size)} | - |")
    lines.extend(["", "## Growth forecast", ""])
    if growth["sample_days"] < 0.5:
        lines.append("Forecast pending: at least 12 hours of production snapshots are required.")
    elif growth["daily_total_growth_bytes"] <= 0:
        lines.append(f"No positive filesystem growth over {growth['sample_days']:.1f} days.")
    else:
        lines.append(
            f"Observed growth is {human_bytes(growth['daily_total_growth_bytes'])}/day over "
            f"{growth['sample_days']:.1f} days."
        )
        for threshold in (70, 85):
            days = growth[f"days_to_{threshold}_percent"]
            lines.append(f"- Estimated time to {threshold}%: {days:.1f} days" if days is not None else f"- Estimated time to {threshold}%: unavailable")
    lines.extend(["", "## Alerts and ownership", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- **{issue['severity']} / {issue['code']}**: {issue['message']}")
    else:
        lines.append("- No active threshold violations.")
    lines.extend([
        "- External 3 a.m. delivery remains unverified until an accountable recipient and webhook are configured.",
        "- Backup monitoring becomes critical only after `OPS_REQUIRE_BACKUP=1`; keep it disabled until the R2 restore drill passes.",
        "",
    ])
    return "\n".join(lines)


def send_webhook(message: str) -> bool:
    url = os.getenv("OPS_ALERT_WEBHOOK_URL", "")
    if not url:
        return False
    payload = json.dumps({"text": message}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        if response.status >= 300:
            raise RuntimeError(f"alert webhook returned HTTP {response.status}")
    return True


def alert_if_needed(issues: list[dict[str, str]], state_dir: Path) -> None:
    fingerprint = hashlib.sha256(json.dumps(issues, sort_keys=True).encode()).hexdigest()
    state_path = state_dir / "alert-state.json"
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if not issues:
        if previous.get("fingerprint"):
            state_path.write_text(
                json.dumps({"fingerprint": "", "delivered": False, "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n",
                encoding="utf-8",
            )
        return
    if (
        previous.get("fingerprint") == fingerprint and previous.get("delivered")
    ):
        return
    summary = "MetaHarmonizer production alert\n" + "\n".join(
        f"[{item['severity'].upper()}] {item['message']}" for item in issues
    )
    delivered = send_webhook(summary)
    state_path.write_text(
        json.dumps({"fingerprint": fingerprint, "delivered": delivered, "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n",
        encoding="utf-8",
    )


def add_counter_deltas(current: dict[str, Any], previous: dict[str, Any] | None) -> None:
    current_total = float(current.get("metrics", {}).get("server_errors_total", 0))
    previous_total = float((previous or {}).get("metrics", {}).get("server_errors_total", current_total))
    current["metrics"]["server_errors_delta"] = max(current_total - previous_total, 0.0)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def prune_snapshots(snapshot_dir: Path, keep: int = 400) -> None:
    snapshots = sorted(snapshot_dir.glob("*.json"), reverse=True)
    for snapshot in snapshots[keep:]:
        snapshot.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "report"))
    parser.add_argument("--repo", type=Path, default=Path(os.getenv("OPS_REPO_ROOT", Path.cwd())))
    parser.add_argument("--state-dir", type=Path, default=Path(os.getenv("OPS_STATE_DIR", Path.home() / ".local/state/metaharmonizer/operations")))
    args = parser.parse_args(argv)
    os.chdir(args.repo)
    args.state_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "check":
        result = collect_check(args.repo)
        previous_path = args.state_dir / "latest-check.json"
        previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else None
        add_counter_deltas(result, previous)
        result["issues"] = assess(result, require_backup=os.getenv("OPS_REQUIRE_BACKUP", "0") == "1")
        write_json(previous_path, result)
        alert_if_needed(result["issues"], args.state_dir)
        print(json.dumps({"timestamp": result["timestamp"], "issues": result["issues"]}))
        return 2 if any(issue["severity"] == "critical" for issue in result["issues"]) else 0

    result = build_report(args.repo, args.state_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = args.state_dir / "snapshots" / f"{stamp}.json"
    write_json(snapshot, result)
    prune_snapshots(snapshot.parent)
    write_json(args.state_dir / "latest-report.json", result)
    markdown = render_report(result)
    (args.state_dir / "latest-report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    if os.getenv("OPS_SEND_DAILY_REPORT", "0") == "1":
        send_webhook(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())