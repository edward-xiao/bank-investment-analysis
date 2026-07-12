#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import tempfile
import unittest

import resolve_bank_report as resolver
import validate_earnings_ledger as ledger
import validate_earnings_report as report


class QualityGateTest(unittest.TestCase):
    def candidate(self, pdf: Path, period: str = "2026Q1") -> dict[str, object]:
        suffix = {"Q1": "第一季度报告", "H1": "半年度报告", "Q3": "第三季度报告", "FY": "年度报告"}[period[4:]]
        return {
            "bank_name": "测试银行股份有限公司",
            "stock_code": "600000",
            "report_period": period,
            "title": f"测试银行股份有限公司{period[:4]}年{suffix}",
            "publication_date": "2026-04-30",
            "source_class": "exchange",
            "url": "https://example.exchange/full-report.pdf",
            "is_full_report": True,
            "local_file": str(pdf),
        }

    def resolve_args(self, manifest: Path) -> argparse.Namespace:
        return argparse.Namespace(
            manifest=manifest,
            bank="测试银行股份有限公司",
            code="600000",
            period="2026Q1",
            cutoff="2026-05-01",
            require_local_pdf=True,
            output=None,
        )

    def test_report_resolver_stops_on_wrong_period(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "report.pdf"
            pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"candidates": [self.candidate(pdf, "2025FY")]}, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Do not substitute another reporting period"):
                resolver.resolve(self.resolve_args(manifest))

    def test_report_resolver_locks_exact_full_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "report.pdf"
            pdf.write_bytes(b"%PDF-1.7\nfull official report\n%%EOF\n")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"candidates": [self.candidate(pdf)]}, ensure_ascii=False),
                encoding="utf-8",
            )
            result = resolver.resolve(self.resolve_args(manifest))
            self.assertEqual(result["status"], "locked")
            self.assertEqual(result["target"]["report_period"], "2026Q1")
            self.assertEqual(len(result["target"]["sha256"]), 64)

    def test_markdown_gate_catches_layout_and_term_errors(self) -> None:
        headings = "\n".join(f"## {name}" for name in report.REQUIRED_HEADINGS)
        text = headings + "\n\n| a | b | c | d | e | f | g | h | i |\n|---|---|---|---|---|---|---|---|---|\nQoQ declined.\n"
        errors, _ = report.validate(text, "default")
        self.assertTrue(any("maximum is 8" in error for error in errors))
        self.assertTrue(any("QoQ" in error for error in errors))

    def test_markdown_gate_requires_lower_bound_conditions(self) -> None:
        headings = "\n".join(f"## {name}" for name in report.REQUIRED_HEADINGS)
        errors, _ = report.validate(headings + "\n新生成不良代理下限为10亿元。\n", "default")
        self.assertTrue(any("three validity statements" in error for error in errors))

    def test_ledger_gate_catches_conflict_and_score_overflow(self) -> None:
        rows = [
            {
                "metric": "净利息收入",
                "value": "100",
                "period": "2026Q1",
                "scope": "集团",
                "balance_type": "累计",
                "status": "disclosed",
                "confidence": "B",
            },
            {
                "metric": "评分-NII",
                "value": "6",
                "period": "2026Q1",
                "scope": "集团",
                "balance_type": "累计",
                "status": "calculated",
                "confidence": "B",
            },
        ]
        errors, _ = ledger.validate_contract(rows)
        self.assertTrue(any("status-confidence" in error for error in errors))
        self.assertTrue(any("between 0 and 5" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
