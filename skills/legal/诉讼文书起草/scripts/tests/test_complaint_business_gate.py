#!/usr/bin/env python3
"""Tests for civil complaint business routing gate."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "complaint_business_gate.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("complaint_business_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate()


class ComplaintBusinessGateTests(unittest.TestCase):
    def write_complaint_data(self, root: Path, *, missing_source: bool = False) -> Path:
        source_map = {
            "plaintiff.natural.name": "fixture",
            "defendant.natural.name": "fixture",
            "claims.principal": "fixture",
            "facts.loan": "fixture",
            "evidence.transfer": "fixture",
            "signature.petitioner": "fixture",
        }
        if missing_source:
            source_map.pop("claims.principal")
        data = {
            "template_id": "civil_complaint_private_lending_v1",
            "fields": {
                "plaintiff.natural.name": "张三",
                "defendant.natural.name": "李四",
                "claims.principal": "100000元",
                "facts.loan": "2025年1月1日出借款项",
                "evidence.transfer": "银行转账凭证",
                "signature.petitioner": "张三",
            },
            "source_map": source_map,
            "known_gaps": [],
        }
        path = root / "complaint-data.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def run_check(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_all_registered_case_causes_route_to_template_clone(self) -> None:
        templates = gate.load_templates()
        self.assertEqual(len(templates), 11)
        for template in templates:
            with self.subTest(case_cause=template["case_cause"]):
                result = gate.route(template["case_cause"], "民事起诉状")
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(result["route"], "template_clone")
                self.assertEqual(result["template_id"], template["template_id"])

    def test_unregistered_case_cause_routes_to_html(self) -> None:
        result = gate.route("房屋租赁合同纠纷", "民事起诉状")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["route"], "html")

    def test_fuzzy_case_cause_requires_confirmation(self) -> None:
        result = gate.route("借款合同纠纷", "民事起诉状")
        self.assertEqual(result["status"], "NEEDS_CONFIRMATION")
        self.assertEqual(result["route"], "needs_confirmation")
        self.assertIn("金融借款合同纠纷", result["candidate_case_causes"])
        self.assertIn("民间借贷纠纷", result["candidate_case_causes"])

    def test_registered_case_cause_rejects_html_output(self) -> None:
        proc = self.run_check(
            "check-output",
            "--case-cause",
            "民间借贷纠纷",
            "--output-kind",
            "html",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("不得生成普通 HTML 起诉状", proc.stdout)

    def test_unregistered_case_cause_rejects_template_clone_output(self) -> None:
        proc = self.run_check(
            "check-output",
            "--case-cause",
            "房屋租赁合同纠纷",
            "--output-kind",
            "template_clone",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("不得强行走 DOCX 母版克隆填充链路", proc.stdout)

    def test_complete_complaint_data_passes_template_clone_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = self.write_complaint_data(Path(tmp))
            proc = self.run_check(
                "check-output",
                "--case-cause",
                "民间借贷纠纷",
                "--output-kind",
                "template_clone",
                "--complaint-data",
                str(data_path),
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn('"status": "PASS"', proc.stdout)

    def test_missing_field_source_fails_template_clone_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = self.write_complaint_data(Path(tmp), missing_source=True)
            proc = self.run_check(
                "check-output",
                "--case-cause",
                "民间借贷纠纷",
                "--output-kind",
                "template_clone",
                "--complaint-data",
                str(data_path),
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("字段缺少来源或缺口说明：claims.principal", proc.stdout)


if __name__ == "__main__":
    unittest.main()
