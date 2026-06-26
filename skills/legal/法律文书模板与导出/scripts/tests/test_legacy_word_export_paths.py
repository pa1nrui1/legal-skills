#!/usr/bin/env python3
"""Regression tests for legacy Word export path detection."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


from helpers import HEALTH


def load_health_module():
    spec = importlib.util.spec_from_file_location("health_check", HEALTH)
    if not spec or not spec.loader:
        raise RuntimeError("cannot load health_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LegacyWordExportPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.health = load_health_module()

    def test_detects_pandoc_markdown_to_docx_export_references(self) -> None:
        samples = [
            "pandoc draft.md -o 正式交付.docx",
            "subprocess.run(['pandoc', 'draft.md', '--output', '正式交付.docx'])",
            "Markdown -> docx",
            "markdown 转 docx",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertRegex(sample, self.health.TECH_PATTERN)

    def test_direct_script_detector_catches_pandoc_docx_output(self) -> None:
        samples = [
            "subprocess.run(['pandoc', 'draft.md', '-o', 'output.docx'])",
            "await execa('pandoc', ['draft.md', '--output', 'output.docx'])",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertRegex(sample, self.health.SCRIPT_DIRECT_DOCX_PATTERN)

    def test_pandoc_text_extraction_reference_is_not_docx_export(self) -> None:
        sample = "使用 pandoc 将 Word 内容转换为文本便于分析"
        self.assertNotRegex(sample, self.health.TECH_PATTERN)
        self.assertNotRegex(sample, self.health.SCRIPT_DIRECT_DOCX_PATTERN)


if __name__ == "__main__":
    unittest.main()
