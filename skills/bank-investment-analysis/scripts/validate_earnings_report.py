#!/usr/bin/env python3
"""Validate the reader-facing Markdown earnings review before publication."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


TERMS = {
    "QoQ": "环比",
    "YoY": "同比",
    "NIM": "净息差",
    "NII": "净利息收入",
    "RWA": "风险加权资产",
    "CET1": "核心一级资本",
    "RORWA": "风险加权资产收益率",
    "AUM": "管理客户总资产",
    "LCR": "流动性覆盖率",
    "NSFR": "净稳定资金比例",
    "ABS": "资产证券化",
    "OCI": "其他综合收益",
}
REQUIRED_HEADINGS = (
    "利润表与单季趋势",
    "资产结构",
    "贷款结构",
    "负债与存款结构",
    "风险存量、流量与缓冲",
    "不良贷款余额变化及核对",
    "贷款减值准备余额变化及核对",
    "资本与增长质量",
    "财报基本面评分",
    "数据完整度与可信度",
)


def visible_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append((index, line))
    return result


def table_cells(line: str) -> list[str]:
    value = line.strip()
    if not (value.startswith("|") and value.endswith("|")):
        return []
    cells = re.split(r"(?<!\\)\|", value[1:-1])
    return [cell.strip() for cell in cells]


def validate(text: str, mode: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    lines = text.splitlines()
    if "{{" in text or "}}" in text:
        errors.append("template placeholders remain")
    for heading in REQUIRED_HEADINGS:
        if not any(line.startswith("##") and heading in line for line in lines):
            errors.append(f"missing required section: {heading}")

    table_count = 0
    current_columns: int | None = None
    previous_was_table = False
    for number, line in visible_lines(text):
        cells = table_cells(line)
        if cells:
            if not previous_was_table:
                table_count += 1
                current_columns = len(cells)
                if current_columns > 8:
                    errors.append(f"line {number}: table has {current_columns} columns; maximum is 8")
            elif len(cells) != current_columns:
                errors.append(
                    f"line {number}: table row has {len(cells)} columns; expected {current_columns}"
                )
            previous_was_table = True
        else:
            previous_was_table = False
            current_columns = None
    charts = len(re.findall(r"^```mermaid\s*$", text, flags=re.MULTILINE))
    if mode == "default":
        if len(lines) > 360:
            errors.append(f"default report has {len(lines)} lines; maximum is 360")
        if table_count > 12:
            errors.append(f"default report has {table_count} tables; maximum is 12")
        if charts > 2:
            errors.append(f"default report has {charts} charts; maximum is 2")
        if "子项评分依据" in text or "26个子项" in text:
            errors.append("default report must not expand the 26 scoring subitems")
        if "附录A：可追溯数据底稿" in text:
            errors.append("default report must not include the audit appendix")
        if len(lines) < 180:
            warnings.append(f"default report has only {len(lines)} lines; verify coverage")
        if table_count < 8:
            warnings.append(f"default report has only {table_count} tables; verify coverage")
    elif "附录A：可追溯数据底稿" not in text:
        errors.append("audit mode requires the traceable data appendix")

    for number, line in visible_lines(text):
        if "http://" in line or "https://" in line:
            check_line = re.sub(r"https?://\S+", "", line)
        else:
            check_line = line
        for term, meaning in TERMS.items():
            bare = re.compile(
                rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z]|（{re.escape(meaning)}）)"
            )
            if bare.search(check_line):
                errors.append(f"line {number}: reader-facing {term} lacks （{meaning}）")
    if re.search(r"^#{1,6} .*桥", text, flags=re.MULTILINE):
        errors.append("reader-facing heading contains unexplained 桥")
    if "新生成不良代理下限" in text:
        required = ("转入/并表影响已完整识别", "核销/转出估算有支持", "不存在重复计算")
        missing = [item for item in required if item not in text]
        if missing:
            errors.append("NPL lower-bound label used without all three validity statements: " + ", ".join(missing))
    if re.search(r"残差[^\n]{0,20}(独立验证|验证了)", text):
        errors.append("constructed residual must not be described as independent validation")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mode", choices=("default", "audit"), default="default")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()
    try:
        text = args.input.read_text(encoding="utf-8")
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors, warnings = validate(text, args.mode)
    if args.ledger:
        command = [
            sys.executable,
            str(Path(__file__).with_name("validate_earnings_ledger.py")),
            "--input",
            str(args.ledger),
        ]
        if args.strict:
            command.append("--strict")
        ledger_result = subprocess.run(command, text=True, capture_output=True, check=False)
        if ledger_result.returncode:
            errors.append("ledger validation failed:\n" + ledger_result.stderr.strip())
        elif ledger_result.stderr.strip():
            warnings.append(ledger_result.stderr.strip())
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors or (args.strict and warnings):
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        f"PASS: {args.mode} report validated; {len(text.splitlines())} lines, "
        f"{sum(1 for _, line in visible_lines(text) if table_cells(line) and '---' in line)} table separators"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
