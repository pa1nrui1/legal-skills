#!/usr/bin/env python3
"""End-to-end tests for material packet to complaint input artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "material_to_complaint_input.py"
GATE = Path(__file__).resolve().parents[1] / "complaint_business_gate.py"


def base_packet(case_cause: str = "民间借贷纠纷") -> dict:
    return {
        "doc_type": "民事起诉状",
        "case_cause": case_cause,
        "materials": [{"name": "借款合成材料", "type": "structured"}],
        "plaintiff": {
            "type": "natural",
            "name": "张三",
            "id_number": "220102199001011234",
            "phone": "13800000000",
            "address": "长春市净月区示例地址一",
        },
        "defendant": {
            "type": "natural",
            "name": "李四",
            "id_number": "220102198812121234",
            "phone": "13900000000",
            "address": "长春市朝阳区示例地址二",
        },
        "service": {
            "type": "natural",
            "name": "张三",
            "phone": "13800000000",
            "address": "长春市净月区示例地址一",
        },
        "facts": {
            "loan_date": "2025年1月1日",
            "principal": "100000元",
            "interest": "5000元",
            "total": "105000元",
            "summary": "2025年1月1日，张三向李四出借100000元，李四到期未还。",
        },
        "evidence": [
            {"name": "借条", "fact": "借贷合意"},
            {"name": "银行转账凭证", "fact": "款项交付"},
        ],
    }


class MaterialToComplaintInputTests(unittest.TestCase):
    def run_convert(self, packet: dict, root: Path) -> subprocess.CompletedProcess[str]:
        materials = root / "materials.json"
        materials.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--materials", str(materials), "--out", str(root / "out")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_registered_case_cause_generates_complaint_data_with_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_convert(base_packet(), root)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            data = json.loads((root / "out" / "complaint-data.json").read_text(encoding="utf-8"))
            self.assertEqual(data["template_id"], "civil_complaint_private_lending_v1")
            self.assertEqual(data["fields"]["plaintiff.natural.name"], "张三")
            self.assertEqual(data["fields"]["defendant.natural.id_number"], "220102198812121234")
            self.assertEqual(data["fields"]["claims.principal"], "100000元")
            self.assertEqual(data["fields"]["claims.total"], "105000元")
            self.assertIn("银行转账凭证", data["fields"]["evidence.summary"])
            for field_id in data["fields"]:
                self.assertIn(field_id, data["source_map"])
            self.assertIn("读取复查摘要", (root / "out" / "reading_review.md").read_text(encoding="utf-8"))
            self.assertIn("来源边界记录", (root / "out" / "source_boundary.md").read_text(encoding="utf-8"))

            gate_proc = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "check-output",
                    "--case-cause",
                    "民间借贷纠纷",
                    "--output-kind",
                    "template_clone",
                    "--complaint-data",
                    str(root / "out" / "complaint-data.json"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(gate_proc.returncode, 0, gate_proc.stdout)

    def test_missing_material_fields_become_known_gaps(self) -> None:
        packet = base_packet()
        packet["defendant"].pop("phone")
        packet["facts"].pop("interest")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_convert(packet, root)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            data = json.loads((root / "out" / "complaint-data.json").read_text(encoding="utf-8"))
            self.assertNotIn("defendant.natural.phone", data["fields"])
            self.assertNotIn("claims.interest", data["fields"])
            gap_ids = {item["field_id"] for item in data["known_gaps"]}
            self.assertIn("defendant.natural.phone", gap_ids)
            self.assertIn("claims.interest", gap_ids)

    def test_unregistered_case_cause_generates_html_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_convert(base_packet("房屋租赁合同纠纷"), root)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertTrue((root / "out" / "draft.html").exists())
            self.assertTrue((root / "out" / "preflight-meta.json").exists())
            self.assertFalse((root / "out" / "complaint-data.json").exists())
            html = (root / "out" / "draft.html").read_text(encoding="utf-8")
            self.assertIn("民事起诉状", html)
            self.assertIn("张三", html)
            self.assertIn("银行转账凭证", html)

    def test_unverified_legal_reference_blocks_output(self) -> None:
        packet = base_packet()
        packet["legal_references"] = [{"name": "中华人民共和国民法典", "article": "第六百七十五条"}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_convert(packet, root)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("NEEDS_LEGAL_VERIFICATION", proc.stdout)
            self.assertFalse((root / "out" / "complaint-data.json").exists())


if __name__ == "__main__":
    unittest.main()
