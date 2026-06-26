#!/usr/bin/env python3
"""Regression tests for formal DOCX delivery audit artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


from helpers import AUDIT


def write_bundle(root: Path, *, omit: str | None = None, status: str = "PASS", health_ok: bool = True, mention_docx: bool = True) -> Path:
    docx = root / "正式交付文件.docx"
    files = {
        "draft.html": "<!doctype html><html><body><h1>审计测试</h1><p>正文</p></body></html>\n",
        "preflight-meta.json": json.dumps({"source_skill": "test", "output_purpose": "正式交付"}, ensure_ascii=False),
        "draft_checked.html": "<!doctype html><html><body><h1>审计测试</h1><p>正文</p></body></html>\n",
        "出稿前审查报告.md": f"# 出稿前审查报告\n\nreview_status: {status}\n",
        "health-check-report.txt": (
            f"docx_checked: {docx}\nhealth_check_ok: {'True' if health_ok else 'False'}\n"
            if mention_docx
            else f"health_check_ok: {'True' if health_ok else 'False'}\n"
        ),
    }
    for name, text in files.items():
        if name != omit:
            (root / name).write_text(text, encoding="utf-8")
    if omit != "正式交付文件.docx":
        docx.write_bytes(b"synthetic docx placeholder")
    return docx


class FormalDeliveryAuditTests(unittest.TestCase):
    def run_audit(self, root: Path, docx: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(AUDIT), "--bundle-dir", str(root), "--docx", str(docx)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_complete_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = write_bundle(root)
            proc = self.run_audit(root, docx)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn('"status": "PASS"', proc.stdout)

    def test_missing_required_artifacts_fail(self) -> None:
        required = [
            "draft.html",
            "preflight-meta.json",
            "draft_checked.html",
            "出稿前审查报告.md",
            "health-check-report.txt",
            "正式交付文件.docx",
        ]
        for name in required:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                docx = write_bundle(root, omit=name)
                proc = self.run_audit(root, docx)
                self.assertNotEqual(proc.returncode, 0, proc.stdout)
                self.assertIn("FAIL", proc.stdout)

    def test_failed_preflight_status_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = write_bundle(root, status="NEEDS_BUSINESS_REVISION")
            proc = self.run_audit(root, docx)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("preflight report status is not allowed", proc.stdout)

    def test_health_check_record_must_pass_and_reference_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = write_bundle(root, health_ok=False)
            proc = self.run_audit(root, docx)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("health check record is not PASS", proc.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = write_bundle(root, mention_docx=False)
            proc = self.run_audit(root, docx)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("health check record does not reference final docx", proc.stdout)


if __name__ == "__main__":
    unittest.main()
