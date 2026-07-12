#!/usr/bin/env python3
"""Validate the single internal earnings-review data ledger."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

import render_data_appendix as appendix


def number(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", "").replace("%", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def close_enough(left: Decimal, right: Decimal) -> bool:
    tolerance = max(Decimal("0.01"), abs(right) * Decimal("0.001"))
    return abs(left - right) <= tolerance


def validate_contract(rows: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    by_metric = {row["metric"]: row for row in rows}
    for index, row in enumerate(rows, start=1):
        key = (row["metric"], row["period"], row["scope"], row["balance_type"])
        if key in seen_keys:
            errors.append(f"row {index}: duplicate metric-period-scope-basis key: {key}")
        seen_keys.add(key)
        status, confidence = row["status"], row["confidence"]
        allowed = {
            "disclosed": {"A"},
            "calculated": {"B", "D"},
            "estimated": {"C", "D"},
            "inferred": {"D"},
            "N/A": {"N/A"},
        }
        if confidence not in allowed.get(status, set()):
            errors.append(
                f"row {index} {row['metric']}: {status}/{confidence} violates status-confidence mapping"
            )
        if status != "N/A" and number(row["value"]) is None and row["metric"] not in {
            "行业分布",
            "区域分布",
            "外部资本工具",
        }:
            errors.append(f"row {index} {row['metric']}: value must be numeric")

    def values(names: list[str]) -> list[Decimal] | None:
        result: list[Decimal] = []
        periods: set[str] = set()
        scopes: set[str] = set()
        for name in names:
            row = by_metric.get(name)
            if not row or row["status"] == "N/A" or number(row["value"]) is None:
                return None
            result.append(number(row["value"]) or Decimal("0"))
            periods.add(row["period"])
            scopes.add(row["scope"])
        if len(periods) != 1 or len(scopes) != 1:
            warnings.append(f"identity skipped because period/scope differs: {', '.join(names)}")
            return None
        return result

    revenue = values(["净利息收入", "手续费及佣金净收入", "其他非息收入", "营业收入"])
    if revenue and not close_enough(sum(revenue[:3]), revenue[3]):
        errors.append("营业收入 does not reconcile to NII + fee income + other non-interest income")
    deposits = values(["公司存款", "零售存款", "客户存款"])
    if deposits and not close_enough(deposits[0] + deposits[1], deposits[2]):
        warnings.append("公司存款 + 零售存款 does not reconcile to 客户存款; verify residual categories")
    maturity = values(["活期存款", "定期存款", "客户存款"])
    if maturity and not close_enough(maturity[0] + maturity[1], maturity[2]):
        warnings.append("活期存款 + 定期存款 does not reconcile to 客户存款; verify residual categories")
    coverage = values(["贷款减值准备期末", "不良贷款余额", "拨备覆盖率"])
    if coverage and coverage[1] != 0:
        calculated = coverage[0] / coverage[1] * Decimal("100")
        if not close_enough(calculated, coverage[2]):
            errors.append("拨备覆盖率 does not reconcile to ending loan provision / NPL balance")
    for metric, row in by_metric.items():
        if metric.startswith("评分-") and row["status"] != "N/A":
            value = number(row["value"])
            if value is None or not Decimal("0") <= value <= Decimal("5"):
                errors.append(f"{metric}: raw score must be between 0 and 5")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "earnings-review-data-template.csv",
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()
    try:
        with args.input.open(encoding="utf-8-sig", newline="") as handle:
            rows = appendix.read_rows(handle)
        metrics = appendix.expected_metrics(args.template)
        appendix.validate_rows(rows, metrics)
        errors, warnings = validate_contract(rows)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors or (args.strict and warnings):
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"PASS: {len(rows)} ledger rows validated; {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
