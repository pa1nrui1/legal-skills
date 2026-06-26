#!/usr/bin/env python3
"""Regression tests for legal citation verification triggers."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


from helpers import PREFLIGHT, make_workspace


class LegalCitationPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = tempfile.TemporaryDirectory()
        matter, system_record, _, env = make_workspace(Path(self.workspace_tmp.name))
        self.matter_path = str(matter)
        self.system_record_path = str(system_record)
        self.env = env

    def tearDown(self) -> None:
        self.workspace_tmp.cleanup()

    def write_case(self, root: Path, body: str, *, include_legal_verification: bool = False) -> dict[str, Path]:
        reading = root / "reading_review.md"
        boundary = root / "source_boundary.md"
        legal = root / "legal_verification.md"
        reading.write_text("# 读取复查摘要\n文件名：合成测试\n存疑项：无\n", encoding="utf-8")
        boundary.write_text("# 来源边界记录\n已核验：合成测试\n未核验：无\n缺口：无\n输出边界：仅用于测试\n", encoding="utf-8")
        legal.write_text("# 法规校验摘要\n已核验：合成引用\n现行有效：是\n", encoding="utf-8")
        html = root / "draft.html"
        meta = root / "preflight-meta.json"
        output_html = root / "draft_checked.html"
        report = root / "出稿前审查报告.md"
        html.write_text(
            f"""<!doctype html><html><body>
<h1>法规触发校验测试文书</h1>
<p>{body}</p>
<p class="signature">广东广和（长春）律师事务所 律师：潘睿</p>
</body></html>""",
            encoding="utf-8",
        )
        evidence = {
            "reading_review_path": str(reading),
            "source_boundary_path": str(boundary),
        }
        if include_legal_verification:
            evidence["legal_verification_path"] = str(legal)
        meta.write_text(
            json.dumps(
                {
                    "source_skill": "诉讼文书起草",
                    "doc_type": "合成测试文书",
                    "output_purpose": "正式交付",
                    "profile": "litigation_standard",
                    "matter_path": self.matter_path,
                    "system_record_path": self.system_record_path,
                    "evidence": evidence,
                    "required_confirmations": [],
                    "known_gaps": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {"html": html, "meta": meta, "output_html": output_html, "report": report}

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
                str(paths["output_html"]),
                "--report",
                str(paths["report"]),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def assert_missing_legal_verification_blocks(self, body: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_case(Path(tmp), body)
            proc = self.run_preflight(paths)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            report = paths["report"].read_text(encoding="utf-8")
            self.assertIn("NEEDS_MATERIAL", report)
            self.assertIn("缺少法规校验摘要路径", report)

    def test_code_and_article_reference_requires_legal_verification(self) -> None:
        self.assert_missing_legal_verification_blocks("依据《民法典》第六百七十五条，借款人应按约还款。")

    def test_judicial_interpretation_reference_requires_legal_verification(self) -> None:
        self.assert_missing_legal_verification_blocks("本案还涉及相关司法解释的适用边界。")

    def test_case_reference_requires_legal_verification(self) -> None:
        self.assert_missing_legal_verification_blocks("本文参考最高人民法院相关案例的裁判规则。")

    def test_citation_with_legal_verification_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_case(Path(tmp), "依据《民法典》第六百七十五条进行合成测试。", include_legal_verification=True)
            proc = self.run_preflight(paths)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("review_status: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
