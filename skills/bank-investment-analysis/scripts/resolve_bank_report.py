#!/usr/bin/env python3
"""Validate and lock the exact official bank report used for an analysis.

The script deliberately does not guess which report the analyst meant.  It
validates a small JSON manifest produced after searching bank IR, exchanges or
statutory disclosure platforms, then emits one locked report record.  A missing
or mismatched full report exits non-zero so an older annual report cannot be
silently substituted for a newer quarterly report.
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse


OFFICIAL_SOURCES = {"bank_ir", "exchange", "cninfo", "hkex"}
PERIOD_RE = re.compile(r"^(19|20)\d{2}(Q1|H1|Q3|FY)$")
EXCLUDED_TITLE_WORDS = ("摘要", "英文版", "取消", "审计报告", "财务报表及审计报告")
PERIOD_WORDS = {
    "Q1": ("第一季度报告", "一季度报告"),
    "H1": ("半年度报告", "中期报告"),
    "Q3": ("第三季度报告", "三季度报告"),
    "FY": ("年度报告", "年报"),
}


def load_candidates(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = payload.get("candidates")
    else:
        candidates = None
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("manifest must contain a non-empty candidates list")
    if not all(isinstance(item, dict) for item in candidates):
        raise ValueError("every candidate must be a JSON object")
    return candidates


def parse_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD: {value!r}") from exc


def validate_local_pdf(path_value: object, expected_sha256: object = "") -> dict[str, Any]:
    path = Path(str(path_value)).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"local_file does not exist: {path}")
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"local_file is not a PDF: {path}")
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest.lower() != str(expected_sha256).lower():
        raise ValueError(f"sha256 mismatch for {path}")
    return {"local_file": str(path), "sha256": digest, "file_size": len(data)}


def title_matches_period(title: str, period: str) -> bool:
    year, suffix = period[:4], period[4:]
    return year in title and any(word in title for word in PERIOD_WORDS[suffix])


def validate_candidate(
    item: dict[str, Any],
    bank_name: str,
    stock_code: str,
    target_period: str,
    cutoff: date,
    require_local_pdf: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    if str(item.get("bank_name", "")).strip() != bank_name:
        reasons.append("bank_name mismatch")
    if stock_code and str(item.get("stock_code", "")).strip() != stock_code:
        reasons.append("stock_code mismatch")
    period = str(item.get("report_period", "")).upper().strip()
    if period != target_period:
        reasons.append("report_period mismatch")
    title = str(item.get("title", "")).strip()
    if not title_matches_period(title, target_period):
        reasons.append("title does not identify the target period")
    if any(word in title for word in EXCLUDED_TITLE_WORDS):
        reasons.append("title indicates an abstract or non-full report")
    if item.get("is_full_report") is not True:
        reasons.append("is_full_report is not true")
    source_class = str(item.get("source_class", "")).lower().strip()
    if source_class not in OFFICIAL_SOURCES:
        reasons.append("source_class is not an approved official source")
    url = str(item.get("url", "")).strip()
    if urlparse(url).scheme != "https":
        reasons.append("url must be an https official link")
    try:
        publication_date = parse_date(item.get("publication_date"), "publication_date")
        if publication_date > cutoff:
            reasons.append("publication_date is after cutoff_date")
    except ValueError as exc:
        reasons.append(str(exc))
        publication_date = cutoff

    locked = dict(item)
    if item.get("local_file"):
        try:
            locked.update(validate_local_pdf(item["local_file"], item.get("sha256", "")))
        except ValueError as exc:
            reasons.append(str(exc))
    elif require_local_pdf:
        reasons.append("local_file is required; download and open the complete PDF first")

    if reasons:
        return None, reasons
    locked.update(
        {
            "bank_name": bank_name,
            "stock_code": stock_code or str(item.get("stock_code", "")),
            "report_period": target_period,
            "publication_date": publication_date.isoformat(),
            "source_class": source_class,
            "resolution_status": "locked",
            "cutoff_date": cutoff.isoformat(),
        }
    )
    return locked, []


def rank_candidate(item: dict[str, Any]) -> tuple[int, date, int]:
    title = str(item.get("title", ""))
    corrected = int(any(word in title for word in ("修订", "更正", "更新")))
    source_rank = {"exchange": 4, "cninfo": 4, "hkex": 4, "bank_ir": 3}.get(
        str(item.get("source_class", "")), 0
    )
    return corrected, parse_date(item["publication_date"], "publication_date"), source_rank


def resolve(args: argparse.Namespace) -> dict[str, Any]:
    period = args.period.upper().strip()
    if not PERIOD_RE.fullmatch(period):
        raise ValueError("period must look like 2026Q1, 2025H1, 2025Q3 or 2025FY")
    cutoff = parse_date(args.cutoff, "cutoff_date")
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(load_candidates(args.manifest), start=1):
        locked, reasons = validate_candidate(
            item,
            args.bank,
            args.code,
            period,
            cutoff,
            args.require_local_pdf,
        )
        if locked:
            valid.append(locked)
        else:
            rejected.append({"candidate": index, "reasons": reasons})
    if not valid:
        detail = json.dumps(rejected, ensure_ascii=False, indent=2)
        raise ValueError(
            "STOP: no complete official report matches bank, code, period and cutoff. "
            "Do not substitute another reporting period.\n" + detail
        )
    chosen = sorted(valid, key=rank_candidate, reverse=True)[0]
    return {
        "status": "locked",
        "target": chosen,
        "valid_candidate_count": len(valid),
        "rejected_candidates": rejected,
        "rule": "Only this locked full official report may be called the target-period report.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bank", required=True, help="Exact bank full name")
    parser.add_argument("--code", default="", help="Stock code, recommended")
    parser.add_argument("--period", required=True, help="For example 2026Q1")
    parser.add_argument("--cutoff", required=True, help="YYYY-MM-DD")
    parser.add_argument("--require-local-pdf", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = resolve(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
