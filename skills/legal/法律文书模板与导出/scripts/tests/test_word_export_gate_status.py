#!/usr/bin/env python3
"""Regression tests for blocking formal DOCX export on failed gate status."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


from helpers import EXPORT, HEALTH, export_python, make_workspace


def write_checked_html(path: Path) -> None:
    path.write_text(
        """<!doctype html>
<html>
<body>
<h1>合成测试文书</h1>
<p>这是用于失败状态禁止导出硬门禁测试的合成正文。</p>
<p class="signature">律师：潘睿</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def write_preflight_report(path: Path, status: str) -> None:
    path.write_text(
        f"""# 出稿前审查报告

review_status: {status}
next_owner: test
next_action: 合成测试
rerun_required: false
""",
        encoding="utf-8",
    )


def write_minimal_docx(path: Path) -> None:
    with ZipFile(path, "w") as zf:
        zf.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:t>合成测试</w:t></w:r></w:p><w:sectPr><w:pgMar/></w:sectPr></w:body>
</w:document>""",
        )
        zf.writestr("word/settings.xml", "<w:settings/>")


class WordExportGateStatusTests(unittest.TestCase):
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
            [sys.executable, str(HEALTH), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def test_html_export_allows_pass_and_fixed_pass_reports(self) -> None:
        for status in ["PASS", "FIXED_PASS"]:
            with self.subTest(status=status), tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
                root = Path(tmp)
                html = root / "draft_checked.html"
                report = root / "report.md"
                output = root / f"{status}.docx"
                write_checked_html(html)
                write_preflight_report(report, status)
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

    def test_html_export_blocks_failed_preflight_statuses(self) -> None:
        for status in ["NEEDS_MATERIAL", "NEEDS_BUSINESS_REVISION", "NEEDS_USER_CONFIRMATION", "HARD_BLOCK"]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                html = root / "draft_checked.html"
                report = root / "report.md"
                output = root / "blocked.docx"
                write_checked_html(html)
                write_preflight_report(report, status)
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
                self.assertIn("preflight report status is not allowed", proc.stdout)
                self.assertFalse(output.exists())

    def test_html_export_blocks_missing_preflight_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "draft_checked.html"
            output = root / "blocked.docx"
            write_checked_html(html)
            proc = self.run_export(
                "--input",
                str(html),
                "--output",
                str(output),
                "--profile",
                "litigation_standard",
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("formal DOCX export requires --preflight-report", proc.stdout)
            self.assertFalse(output.exists())

    def test_html_export_blocks_unchecked_formal_input_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "draft.html"
            report = root / "report.md"
            output = root / "blocked.docx"
            write_checked_html(html)
            write_preflight_report(report, "PASS")
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
            self.assertIn("formal DOCX export requires input file named draft_checked.html", proc.stdout)
            self.assertFalse(output.exists())

    def test_template_clone_health_blocks_failed_or_missing_qc_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = root / "clone.docx"
            failed_report = root / "qc-report.json"
            missing_report = root / "missing-qc-report.json"
            write_minimal_docx(docx)
            failed_report.write_text(json.dumps({"status": "FAIL"}, ensure_ascii=False), encoding="utf-8")

            failed = self.run_health(
                "--docx",
                str(docx),
                "--expect-clean-clone",
                "--template-clone-report",
                str(failed_report),
            )
            self.assertNotEqual(failed.returncode, 0, failed.stdout)
            self.assertIn("template clone report not PASS: FAIL", failed.stdout)

            missing = self.run_health(
                "--docx",
                str(docx),
                "--expect-clean-clone",
                "--template-clone-report",
                str(missing_report),
            )
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("template clone report parse failed", missing.stdout)


if __name__ == "__main__":
    unittest.main()
