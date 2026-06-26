#!/usr/bin/env python3
"""Regression tests for fixed lawyer identity in formal DOCX output."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


from helpers import EXPORT, PREFLIGHT, export_python, make_workspace

FIXED_VALUES = [
    "广东广和（长春）律师事务所",
    "潘睿",
    "净月区华荣泰七栋608室",
    "18686488305",
    "418869057@qq.com",
]
OLD_VALUES = ["吉林旧所律师事务所", "李四", "旧地址", "13900000000", "old@example.com"]


def docx_text(path: Path) -> str:
    with ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    return re.sub(r"<[^>]+>", "", xml)


class FixedIdentityDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = tempfile.TemporaryDirectory()
        matter, system_record, _, env = make_workspace(Path(self.workspace_tmp.name))
        self.matter_path = str(matter)
        self.system_record_path = str(system_record)
        self.env = env

    def tearDown(self) -> None:
        self.workspace_tmp.cleanup()

    def export_python(self) -> str:
        return export_python()

    def write_case(self, root: Path) -> dict[str, Path]:
        reading = root / "reading_review.md"
        boundary = root / "source_boundary.md"
        reading.write_text("# 读取复查摘要\n文件名：合成测试\n存疑项：无\n", encoding="utf-8")
        boundary.write_text("# 来源边界记录\n已核验：合成测试\n未核验：无\n缺口：无\n输出边界：仅用于测试\n", encoding="utf-8")
        html = root / "draft.html"
        meta = root / "preflight-meta.json"
        checked = root / "draft_checked.html"
        report = root / "出稿前审查报告.md"
        html.write_text(
            """<!doctype html><html><body>
<h1>身份信息固定测试文书</h1>
<p>本文书仅用于身份信息固定测试，不涉及真实案件材料。</p>
<p class="signature">吉林旧所律师事务所 律师：李四 地址：旧地址 电话：13900000000 邮箱：old@example.com</p>
</body></html>""",
            encoding="utf-8",
        )
        meta.write_text(
            json.dumps(
                {
                    "source_skill": "诉讼文书起草",
                    "doc_type": "合成测试文书",
                    "output_purpose": "正式交付",
                    "profile": "litigation_standard",
                    "matter_path": self.matter_path,
                    "system_record_path": self.system_record_path,
                    "evidence": {
                        "reading_review_path": str(reading),
                        "source_boundary_path": str(boundary),
                    },
                    "required_confirmations": [],
                    "known_gaps": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {"html": html, "meta": meta, "checked": checked, "report": report}

    def run_preflight(self, paths: dict[str, Path]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PREFLIGHT),
                "--html",
                str(paths["html"]),
                "--meta",
                str(paths["meta"]),
                "--output-html",
                str(paths["checked"]),
                "--report",
                str(paths["report"]),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def run_export(self, paths: dict[str, Path], output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.export_python(),
                str(EXPORT),
                "--input",
                str(paths["checked"]),
                "--output",
                str(output),
                "--profile",
                "litigation_standard",
                "--preflight-report",
                str(paths["report"]),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def test_old_identity_is_replaced_in_formal_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_case(Path(tmp))
            preflight = self.run_preflight(paths)
            self.assertEqual(preflight.returncode, 0, preflight.stdout)

            output = Path(self.matter_path) / "身份信息固定正式交付文件.docx"
            export = self.run_export(paths, output)
            self.assertEqual(export.returncode, 0, export.stdout)

            text = docx_text(output)
            for value in FIXED_VALUES:
                self.assertIn(value, text)
            for value in OLD_VALUES:
                self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main()
