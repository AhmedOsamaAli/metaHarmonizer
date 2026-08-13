"""Fail a KB refresh when ontology benchmark quality regresses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def compare_results(
    policy: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    expected_corpus = policy["benchmark_sha256"]
    for label, result in (("before", before), ("after", after)):
        if result.get("benchmark_sha256") != expected_corpus:
            errors.append(f"{label} result does not match the policy benchmark checksum")
    if before.get("benchmark_sha256") != after.get("benchmark_sha256"):
        errors.append("before and after results use different benchmark corpora")

    minimum_queries = int(policy["minimum_queries"])
    for label, result in (("before", before), ("after", after)):
        if int(result.get("query_count", 0)) < minimum_queries:
            errors.append(
                f"{label} evaluated {result.get('query_count', 0)} queries; "
                f"minimum is {minimum_queries}"
            )

    metrics: dict[str, Any] = {}
    for name, limits in policy["metrics"].items():
        before_value = float(before.get(name, -1))
        after_value = float(after.get(name, -1))
        minimum = float(limits["minimum"])
        max_drop = float(limits["max_absolute_drop"])
        drop = before_value - after_value
        passed = after_value >= minimum and drop <= max_drop
        metrics[name] = {
            "before": before_value,
            "after": after_value,
            "absolute_drop": round(drop, 6),
            "minimum": minimum,
            "max_absolute_drop": max_drop,
            "passed": passed,
        }
        if after_value < minimum:
            errors.append(f"{name} {after_value:.4f} is below floor {minimum:.4f}")
        if drop > max_drop:
            errors.append(
                f"{name} dropped {drop:.4f}; maximum allowed drop is {max_drop:.4f}"
            )

    return {
        "schema_version": 1,
        "benchmark_id": policy["benchmark_id"],
        "passed": not errors,
        "errors": errors,
        "before_bundle_sha256": before.get("bundle_sha256", ""),
        "after_bundle_sha256": after.get("bundle_sha256", ""),
        "benchmark_sha256": after.get("benchmark_sha256", ""),
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check KB benchmark regression policy.")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    report = compare_results(policy, before, after)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for name, metric in report["metrics"].items():
        print(
            f"{name}: {metric['before']:.4f} -> {metric['after']:.4f} "
            f"(floor {metric['minimum']:.4f}, max drop {metric['max_absolute_drop']:.4f})"
        )
    if report["errors"]:
        for error in report["errors"]:
            print(f"REGRESSION: {error}")
        return 1
    print("benchmark regression gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())