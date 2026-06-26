#!/usr/bin/env python3
"""Regression tests for HTML input safety and graceful structure handling."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


from helpers import EXPORT, HEALTH, export_python, make_workspace


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


class HtmlInputSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = tempfile.TemporaryDirectory()
        matter, _, _, env = make_workspace(Path(self.workspace_tmp.name))
        self.matter_path = matter
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

    def run_health(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.export_python(), str(HEALTH), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def export_case(self, root: Path, html_text: str, output_name: str = "正式交付文件.docx") -> tuple[subprocess.CompletedProcess[str], Path]:
        html = root / "draft_checked.html"
        report = root / "出稿前审查报告.md"
        output = root / output_name
        html.write_text(html_text, encoding="utf-8")
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
        return proc, output

    def assert_docx_contains(self, output: Path, text: str) -> None:
        health = self.run_health("--docx", str(output), "--expect-text", text)
        self.assertEqual(health.returncode, 0, health.stdout)

    def test_unsupported_tags_preserve_body_text(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            proc, output = self.export_case(
                Path(tmp),
                """<!doctype html><html><body>
<h1>HTML 输入安全测试</h1>
<aside><custom-law-node>非标准标签中的关键正文不能丢失。</custom-law-node></aside>
<p class="signature">广东广和（长春）律师事务所 律师：潘睿</p>
</body></html>""",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assert_docx_contains(output, "非标准标签中的关键正文不能丢失。")

    def test_nested_table_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            proc, output = self.export_case(
                Path(tmp),
                """<!doctype html><html><body>
<h1>HTML 输入安全测试</h1>
<table><tr><td>外层<table><tr><td>内层</td></tr></table></td></tr></table>
<p>嵌套表格应明确失败，避免表格结构跑位。</p>
</body></html>""",
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("nested table is not supported", proc.stdout)
            self.assertFalse(output.exists())

    def test_empty_title_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            proc, output = self.export_case(
                Path(tmp),
                """<!doctype html><html><body>
<h1>   </h1>
<p>空标题不应生成正式 Word。</p>
</body></html>""",
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("formal DOCX input requires non-empty h1 title", proc.stdout)
            self.assertFalse(output.exists())

    def test_empty_paragraph_does_not_drop_later_body(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            proc, output = self.export_case(
                Path(tmp),
                """<!doctype html><html><body>
<h1>HTML 输入安全测试</h1>
<p>   </p>
<p>空段落之后的正文必须保留。</p>
<p class="signature">广东广和（长春）律师事务所 律师：潘睿</p>
</body></html>""",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assert_docx_contains(output, "空段落之后的正文必须保留。")

    def test_abnormal_control_characters_are_sanitized(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            proc, output = self.export_case(
                Path(tmp),
                "<!doctype html><html><body><h1>HTML 输入安全测试</h1><p>异常\x00字符正文仍应保留。</p></body></html>",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assert_docx_contains(output, "异常字符正文仍应保留。")


if __name__ == "__main__":
    unittest.main()
