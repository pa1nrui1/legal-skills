#!/usr/bin/env python3
"""Regression tests for coordinate-safe DOCX template filling."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


from helpers import FILLER, export_python


def write_template(path: Path) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>姓名：</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>姓名：</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""
    with ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/settings.xml", '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')


def docx_text(path: Path) -> str:
    with ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    return xml


class TemplateClonePositioningTests(unittest.TestCase):
    def filler_python(self) -> str:
        return export_python()

    def run_fill(self, root: Path, fields: list[dict]) -> subprocess.CompletedProcess[str]:
        template = root / "template.docx"
        plan = root / "fill-plan.json"
        output = root / "output.docx"
        log = root / "fill-log.json"
        write_template(template)
        plan.write_text(
            json.dumps({"template_id": "positioning_test", "fields": fields}, ensure_ascii=False),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                self.filler_python(),
                str(FILLER),
                "--template",
                str(template),
                "--plan",
                str(plan),
                "--output",
                str(output),
                "--log",
                str(log),
                "--allow-unchecked",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_repeated_anchor_fills_only_target_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_fill(
                root,
                [
                    {
                        "field_id": "second.name",
                        "value": "李四",
                        "target": {"table_index": 2, "row_index": 1, "cell_index": 1, "anchor_text": "姓名："},
                        "mode": "append_after_anchor",
                    }
                ],
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            text = docx_text(root / "output.docx")
            self.assertIn("<w:t>姓名：</w:t>", text)
            self.assertIn("<w:t>姓名：李四</w:t>", text)

    def test_missing_coordinate_fails_instead_of_global_anchor_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_fill(
                root,
                [
                    {
                        "field_id": "missing.coordinate",
                        "value": "李四",
                        "target": {"table_index": 2, "row_index": 1, "anchor_text": "姓名："},
                        "mode": "append_after_anchor",
                    }
                ],
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn('"failed": 1', proc.stdout)
            self.assertIn("cell_index", proc.stdout)

    def test_blank_anchor_fails_for_anchor_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_fill(
                root,
                [
                    {
                        "field_id": "blank.anchor",
                        "value": "李四",
                        "target": {"table_index": 2, "row_index": 1, "cell_index": 1, "anchor_text": ""},
                        "mode": "append_after_anchor",
                    }
                ],
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("anchor_text is required", proc.stdout)


if __name__ == "__main__":
    unittest.main()
