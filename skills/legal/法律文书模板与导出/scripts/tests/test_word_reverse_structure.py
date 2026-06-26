#!/usr/bin/env python3
"""Regression tests for DOCX reverse-structure health checks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


from helpers import HEALTH


def write_docx(
    path: Path,
    *,
    texts: list[str],
    include_table: bool = True,
    include_page_number: bool = True,
    track_revisions: bool = False,
    comments: bool = False,
) -> None:
    paragraphs = "\n".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in texts)
    table = "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格内容</w:t></w:r></w:p></w:tc></w:tr></w:tbl>" if include_table else ""
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {paragraphs}
    {table}
    <w:sectPr><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""
    footer_xml = "<w:ftr><w:p><w:r><w:t>PAGE</w:t></w:r></w:p></w:ftr>" if include_page_number else "<w:ftr/>"
    settings_xml = "<w:settings><w:trackRevisions/></w:settings>" if track_revisions else "<w:settings/>"
    with ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/footer1.xml", footer_xml)
        zf.writestr("word/settings.xml", settings_xml)
        if comments:
            zf.writestr("word/comments.xml", "<w:comments/>")


class WordReverseStructureTests(unittest.TestCase):
    def run_health(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HEALTH), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_html_docx_requires_title_table_body_signature_and_page_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "html.docx"
            write_docx(
                docx,
                texts=["民事起诉状", "事实与理由：合成测试正文", "律师：潘睿"],
                include_table=True,
                include_page_number=True,
            )
            proc = self.run_health(
                "--docx",
                str(docx),
                "--expect-title",
                "民事起诉状",
                "--expect-table",
                "--expect-text",
                "事实与理由：合成测试正文",
                "--expect-text",
                "潘睿",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("health_check_ok: True", proc.stdout)

    def test_health_check_blocks_missing_expected_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "missing-text.docx"
            write_docx(docx, texts=["民事起诉状", "事实与理由：合成测试正文"])
            proc = self.run_health(
                "--docx",
                str(docx),
                "--expect-title",
                "民事起诉状",
                "--expect-table",
                "--expect-text",
                "律师：潘睿",
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("expected text not found: 律师：潘睿", proc.stdout)

    def test_clone_docx_requires_clean_output_and_filled_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "clone.docx"
            write_docx(
                docx,
                texts=["姓名：张三", "截至2026年6月25日止，尚欠本金100000元", "欠利息5000元", "105000元"],
                include_page_number=False,
            )
            proc = self.run_health(
                "--docx",
                str(docx),
                "--expect-clean-clone",
                "--expect-text",
                "姓名：张三",
                "--expect-text",
                "尚欠本金100000元",
                "--expect-text",
                "欠利息5000元",
                "--expect-text",
                "105000元",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_clean_clone_blocks_comments_and_missing_field_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "dirty-clone.docx"
            write_docx(docx, texts=["姓名：张三"], include_page_number=False, comments=True)
            proc = self.run_health(
                "--docx",
                str(docx),
                "--expect-clean-clone",
                "--expect-text",
                "105000元",
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("clean clone contains comments.xml", proc.stdout)
            self.assertIn("expected text not found: 105000元", proc.stdout)


if __name__ == "__main__":
    unittest.main()
