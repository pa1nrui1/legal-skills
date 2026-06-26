#!/usr/bin/env python3
"""Regression tests for formal DOCX output path and draft isolation gates."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


from helpers import EXPORT, FILLER, export_python, make_workspace


def write_checked_html(path: Path) -> None:
    path.write_text(
        """<!doctype html>
<html>
<body>
<h1>正式输出路径隔离测试文书</h1>
<p>这是用于正式 Word 输出路径隔离测试的合成正文，不涉及真实案件材料。</p>
<p class="signature">广东广和（长春）律师事务所 律师：潘睿</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def write_preflight_report(path: Path) -> None:
    path.write_text(
        """# 出稿前审查报告

review_status: PASS
next_owner: test
next_action: 合成测试
rerun_required: false
""",
        encoding="utf-8",
    )


def write_clone_template(path: Path) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>姓名：</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""
    with ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/settings.xml", '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')


def write_fill_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "template_id": "output_path_test",
                "fields": [
                    {
                        "field_id": "plaintiff.name",
                        "value": "张三",
                        "target": {"table_index": 1, "row_index": 1, "cell_index": 1, "anchor_text": "姓名："},
                        "mode": "append_after_anchor",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class WordOutputPathIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = tempfile.TemporaryDirectory()
        matter, system_record, _, env = make_workspace(Path(self.workspace_tmp.name))
        self.matter_path = matter
        self.system_record_path = system_record
        self.env = env

    def tearDown(self) -> None:
        self.workspace_tmp.cleanup()

    def export_python(self) -> str:
        return export_python()

    def run_export(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.export_python(), str(EXPORT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def run_fill(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.export_python(), str(FILLER), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def test_formal_export_allows_business_area_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            root = Path(tmp)
            html = root / "draft_checked.html"
            report = root / "出稿前审查报告.md"
            output = root / "正式交付文件.docx"
            write_checked_html(html)
            write_preflight_report(report)

            proc = self.run_export(
                "--input",
                str(html),
                "--output",
                str(output),
                "--profile",
                "litigation_standard",
                "--preflight-report",
                str(report),
            )

            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertTrue(output.exists())

    def test_formal_export_blocks_temp_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "draft_checked.html"
            report = root / "出稿前审查报告.md"
            output = root / "正式交付文件.docx"
            write_checked_html(html)
            write_preflight_report(report)

            proc = self.run_export(
                "--input",
                str(html),
                "--output",
                str(output),
                "--profile",
                "litigation_standard",
                "--preflight-report",
                str(report),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("formal DOCX output must be under business matter root", proc.stdout)
            self.assertFalse(output.exists())

    def test_formal_export_blocks_system_record_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.system_record_path) as tmp:
            root = Path(tmp)
            html = root / "draft_checked.html"
            report = root / "出稿前审查报告.md"
            output = root / "正式交付文件.docx"
            write_checked_html(html)
            write_preflight_report(report)

            proc = self.run_export(
                "--input",
                str(html),
                "--output",
                str(output),
                "--profile",
                "litigation_standard",
                "--preflight-report",
                str(report),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("formal DOCX output must not be under system record root", proc.stdout)
            self.assertFalse(output.exists())

    def test_formal_export_blocks_draft_or_experiment_filename(self) -> None:
        blocked_names = ["draft.docx", "草稿.docx", "实验稿.docx", "未审查.docx", "unchecked.docx"]
        for name in blocked_names:
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
                root = Path(tmp)
                html = root / "draft_checked.html"
                report = root / "出稿前审查报告.md"
                output = root / name
                write_checked_html(html)
                write_preflight_report(report)

                proc = self.run_export(
                    "--input",
                    str(html),
                    "--output",
                    str(output),
                    "--profile",
                    "litigation_standard",
                    "--preflight-report",
                    str(report),
                )

                self.assertNotEqual(proc.returncode, 0, proc.stdout)
                self.assertIn("formal DOCX filename must not look like draft or experiment", proc.stdout)
                self.assertFalse(output.exists())

    def test_unchecked_export_blocks_business_area_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            root = Path(tmp)
            html = root / "draft.html"
            output = root / "实验稿.docx"
            write_checked_html(html)

            proc = self.run_export(
                "--input",
                str(html),
                "--output",
                str(output),
                "--profile",
                "litigation_standard",
                "--allow-unchecked",
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("unchecked DOCX export must not write into formal business area", proc.stdout)
            self.assertFalse(output.exists())

    def test_template_clone_formal_output_allows_business_area(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            root = Path(tmp)
            template = root / "template.docx"
            plan = root / "fill-plan.json"
            output = root / "要素式正式交付文件.docx"
            log = root / "fill-log.json"
            write_clone_template(template)
            write_fill_plan(plan)

            proc = self.run_fill(
                "--template",
                str(template),
                "--plan",
                str(plan),
                "--output",
                str(output),
                "--log",
                str(log),
            )

            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertTrue(output.exists())

    def test_template_clone_formal_output_blocks_temp_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template.docx"
            plan = root / "fill-plan.json"
            output = root / "要素式正式交付文件.docx"
            log = root / "fill-log.json"
            write_clone_template(template)
            write_fill_plan(plan)

            proc = self.run_fill(
                "--template",
                str(template),
                "--plan",
                str(plan),
                "--output",
                str(output),
                "--log",
                str(log),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("formal DOCX output must be under business matter root", proc.stdout)
            self.assertFalse(output.exists())

    def test_template_clone_unchecked_output_blocks_business_area(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            root = Path(tmp)
            template = root / "template.docx"
            plan = root / "fill-plan.json"
            output = root / "要素式实验稿.docx"
            log = root / "fill-log.json"
            write_clone_template(template)
            write_fill_plan(plan)

            proc = self.run_fill(
                "--template",
                str(template),
                "--plan",
                str(plan),
                "--output",
                str(output),
                "--log",
                str(log),
                "--allow-unchecked",
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("unchecked DOCX export must not write into formal business area", proc.stdout)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
