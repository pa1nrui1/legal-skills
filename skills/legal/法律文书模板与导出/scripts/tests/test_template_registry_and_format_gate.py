#!/usr/bin/env python3
"""Regression tests for global template registry selection and format gates."""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


from helpers import EXPORT, HEALTH, PREFLIGHT, SELECTOR, export_python, make_workspace


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_docx(path: Path, *, size: int = 24, line: int = 360, line_rule: str = "auto") -> None:
    spacing = f'<w:spacing w:line="{line}" w:lineRule="{line_rule}"/>'
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr>{spacing}</w:pPr><w:r><w:rPr><w:sz w:val="32"/></w:rPr><w:t>解除委托协议</w:t></w:r></w:p>
    <w:p><w:pPr>{spacing}</w:pPr><w:r><w:rPr><w:sz w:val="{size}"/></w:rPr><w:t>甲方：长春新同洲物业服务有限公司</w:t></w:r></w:p>
    <w:p><w:pPr>{spacing}</w:pPr><w:r><w:rPr><w:sz w:val="{size}"/></w:rPr><w:t>正文测试段落。</w:t></w:r></w:p>
    <w:sectPr><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""
    footer_xml = "<w:ftr><w:p><w:r><w:t>PAGE</w:t></w:r></w:p></w:ftr>"
    with ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/footer1.xml", footer_xml)
        zf.writestr("word/settings.xml", "<w:settings/>")


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


class TemplateRegistryAndFormatGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = tempfile.TemporaryDirectory()
        self.registry_tmp = tempfile.TemporaryDirectory()
        matter, system_record, _, env = make_workspace(Path(self.workspace_tmp.name))
        self.matter_path = str(matter)
        self.system_record_path = str(system_record)
        self.env = env
        self.template = Path(self.registry_tmp.name) / "解除委托协议模板.docx"
        self.template.write_text("synthetic registered template", encoding="utf-8")
        self.template_sha = file_sha256(self.template)
        self.registry = Path(self.registry_tmp.name) / "legal-template-registry.json"
        self.registry.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "templates": [
                        {
                            "template_id": "contract_termination_entrustment_lawyer_client_v1",
                            "version": "1.0",
                            "owner_skill": "合同起草",
                            "source_type": "external_docx_template",
                            "source_path": str(self.template),
                            "sha256": self.template_sha,
                            "doc_types": ["解除委托协议", "解除委托合同", "终止委托协议"],
                            "business_scenes": ["解除委托", "终止委托", "撤诉解除委托"],
                            "keywords": ["解除委托", "终止委托", "撤诉", "律师事务所", "客户"],
                            "exclude_keywords": ["委托代理合同", "授权委托书", "风险义务告知书", "服务质量监督卡"],
                            "default_profile": "contract_standard",
                            "compatible_profiles": ["contract_standard", "fallback_desktop_word"],
                            "profile_versions": {"contract_standard": "1.0", "fallback_desktop_word": "1.0"},
                            "format_standard": "contract_standard",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.env["LEGAL_TEMPLATE_REGISTRY"] = str(self.registry)

    def tearDown(self) -> None:
        self.registry_tmp.cleanup()
        self.workspace_tmp.cleanup()

    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )

    def write_basic_preflight_fixture(
        self,
        root: Path,
        *,
        profile: str = "contract_standard",
        template_id: str = "contract_termination_entrustment_lawyer_client_v1",
        template_sha256: str | None = None,
    ) -> tuple[Path, Path, Path, Path]:
        template_sha256 = template_sha256 or self.template_sha
        for name, text in {
            "reading.md": "# 读取复查摘要\n存疑项：无\n",
            "boundary.md": "# 来源边界记录\n已核验：合成\n未核验：无\n缺口：无\n输出边界：测试\n",
        }.items():
            (root / name).write_text(text, encoding="utf-8")
        html = root / "draft.html"
        meta = root / "preflight-meta.json"
        report = root / "report.md"
        checked = root / "draft_checked.html"
        html.write_text("<html><body><h1>解除委托协议</h1><p>测试正文。</p></body></html>", encoding="utf-8")
        meta.write_text(
            json.dumps(
                {
                    "source_skill": "合同起草",
                    "doc_type": "解除委托协议",
                    "output_purpose": "正式交付",
                    "profile": profile,
                    "profile_id": profile,
                    "profile_version": "1.0",
                    "content_template_id": template_id,
                    "content_template_version": "1.0",
                    "content_template_sha256": template_sha256,
                    "format_standard": "contract_standard",
                    "matter_path": self.matter_path,
                    "system_record_path": self.system_record_path,
                    "evidence": {
                        "reading_review_path": str(root / "reading.md"),
                        "source_boundary_path": str(root / "boundary.md"),
                    },
                    "required_confirmations": [],
                    "known_gaps": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return html, meta, checked, report

    def write_profile_selection_preflight_fixture(
        self,
        root: Path,
        *,
        selection: dict,
        profile: str | None = None,
        doc_type: str = "代理词",
        title: str = "民事代理词",
    ) -> tuple[Path, Path, Path, Path]:
        selected_profile = profile or selection["profile_id"]
        selection_path = root / "template-selection.json"
        selection_path.write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
        for name, text in {
            "reading.md": "# 读取复查摘要\n存疑项：无\n",
            "boundary.md": "# 来源边界记录\n已核验：合成\n未核验：无\n缺口：无\n输出边界：测试\n",
        }.items():
            (root / name).write_text(text, encoding="utf-8")
        html = root / "draft.html"
        meta = root / "preflight-meta.json"
        report = root / "report.md"
        checked = root / "draft_checked.html"
        html.write_text(
            f"<html><body><h1>{title}</h1><p>合成测试正文，用于验证模板路由选择进入出稿前审查。</p></body></html>",
            encoding="utf-8",
        )
        meta.write_text(
            json.dumps(
                {
                    "source_skill": selection.get("source_skill") or "民事一审诉讼",
                    "doc_type": doc_type,
                    "output_purpose": "正式交付",
                    "profile": selected_profile,
                    "profile_id": selected_profile,
                    "profile_version": selection.get("profile_version") or "1.0",
                    "format_standard": selection.get("format_standard") or selected_profile,
                    "template_selection_path": str(selection_path),
                    "matter_path": self.matter_path,
                    "system_record_path": self.system_record_path,
                    "evidence": {
                        "reading_review_path": str(root / "reading.md"),
                        "source_boundary_path": str(root / "boundary.md"),
                    },
                    "required_confirmations": [],
                    "known_gaps": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return html, meta, checked, report

    def select(self, root: Path, *args: str) -> dict:
        out = root / "template-selection.json"
        proc = self.run_cmd(str(SELECTOR), *args, "--output", str(out))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        return json.loads(out.read_text(encoding="utf-8"))

    def test_selector_matches_termination_template_to_contract_standard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "template-selection.json"
            proc = self.run_cmd(
                str(SELECTOR),
                "--source-skill",
                "合同起草",
                "--doc-type",
                "解除委托协议",
                "--business-scene",
                "撤诉解除委托",
                "--user-request",
                "客户撤诉，钱款不退，后续抵扣",
                "--source-template-path",
                str(self.template),
                "--preferred-profile",
                "contract_standard",
                "--output",
                str(out),
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["content_template_id"], "contract_termination_entrustment_lawyer_client_v1")
            self.assertEqual(data["profile_id"], "contract_standard")

    def test_selector_blocks_incompatible_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "template-selection.json"
            proc = self.run_cmd(
                str(SELECTOR),
                "--source-skill",
                "合同起草",
                "--doc-type",
                "解除委托协议",
                "--business-scene",
                "撤诉解除委托",
                "--user-request",
                "客户撤诉",
                "--source-template-path",
                str(self.template),
                "--preferred-profile",
                "entrustment_contract",
                "--output",
                str(out),
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("not compatible", proc.stdout)

    def test_selector_blocks_unregistered_source_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "unregistered-template.docx"
            source.write_text("not registered", encoding="utf-8")
            out = root / "template-selection.json"
            proc = self.run_cmd(
                str(SELECTOR),
                "--source-skill",
                "合同起草",
                "--doc-type",
                "解除委托协议",
                "--business-scene",
                "撤诉解除委托",
                "--user-request",
                "客户撤诉，钱款不退，后续抵扣",
                "--source-template-path",
                str(source),
                "--output",
                str(out),
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("no registered legal template matched", proc.stdout)

    def test_selector_routes_registered_complaint_to_template_clone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.select(
                root,
                "--source-skill",
                "民事一审诉讼",
                "--doc-type",
                "民事起诉状",
                "--business-scene",
                "民间借贷纠纷立案",
                "--user-request",
                "生成民间借贷纠纷要素式起诉状",
            )
            self.assertEqual(data["selection_status"], "ROUTE_TO_TEMPLATE_CLONE")
            self.assertEqual(data["route_kind"], "template_clone")
            self.assertEqual(data["clone_template_id"], "civil_complaint_private_lending_v1")

    def test_selector_blocks_complaint_without_registered_case_cause_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "template-selection.json"
            proc = self.run_cmd(
                str(SELECTOR),
                "--source-skill",
                "民事一审诉讼",
                "--doc-type",
                "民事起诉状",
                "--business-scene",
                "人格权纠纷立案",
                "--user-request",
                "生成起诉状但未命中要素式模板案由",
                "--output",
                str(out),
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("must not fall back", proc.stdout)

    def test_selector_uses_format_reference_for_evidence_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.select(
                root,
                "--source-skill",
                "诉讼文书起草",
                "--doc-type",
                "证据目录",
                "--business-scene",
                "起诉材料提交",
                "--user-request",
                "按证据目录格式生成第一组证据和证明目的",
            )
            self.assertEqual(data["selection_type"], "format_reference")
            self.assertEqual(data["profile_id"], "litigation_standard")
            self.assertEqual(data["format_reference_source"], "诉讼文书起草/templates/证据目录格式.md")

    def test_format_reference_requires_document_name_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.select(
                root,
                "--source-skill",
                "民事判决书",
                "--doc-type",
                "交接说明",
                "--business-scene",
                "内部交接",
                "--user-request",
                "生成交接说明，不是判决书",
            )
            self.assertEqual(data["selection_type"], "profile_fallback")
            self.assertEqual(data["profile_id"], "fallback_desktop_word")
            self.assertNotIn("format_reference_source", data)

    def test_selector_uses_best_available_route_by_document_category(self) -> None:
        cases = [
            ("民事一审诉讼", "代理词", "庭审提交", "生成普通代理词", "litigation_standard", {"profile_fallback"}),
            ("民事一审诉讼", "财产保全申请书", "诉前保全", "冻结被告账户", "litigation_standard", {"profile_fallback"}),
            ("法规案例检索", "法律检索报告", "类案检索", "输出律师版检索报告", "legal_report", {"profile_fallback", "format_reference"}),
            ("合同起草", "软件开发合同", "软件委托开发", "起草SaaS服务合同", "contract_standard", {"registered_content_template", "profile_fallback"}),
            ("民事判决书", "民事判决书", "法院文书", "生成判决书样式文本", "judgment_style", {"format_reference", "profile_fallback"}),
            ("法律工作总控", "交接备忘录", "内部记录", "生成普通备忘录", "fallback_desktop_word", {"profile_fallback"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for idx, (source_skill, doc_type, scene, request, expected_profile, allowed_types) in enumerate(cases):
                out_root = root / str(idx)
                out_root.mkdir()
                data = self.select(
                    out_root,
                    "--source-skill",
                    source_skill,
                    "--doc-type",
                    doc_type,
                    "--business-scene",
                    scene,
                    "--user-request",
                    request,
                )
                self.assertIn(data["selection_type"], allowed_types)
                self.assertEqual(data["profile_id"], expected_profile)

    def test_preflight_allows_profile_fallback_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selection = {
                "selection_status": "PASS",
                "selection_type": "profile_fallback",
                "route_kind": "html_to_docx",
                "source_skill": "民事一审诉讼",
                "doc_type": "代理词",
                "business_scene": "庭审提交",
                "profile_id": "litigation_standard",
                "profile_version": "1.0",
                "format_standard": "litigation_standard",
            }
            html, meta, checked, report = self.write_profile_selection_preflight_fixture(root, selection=selection)
            proc = self.run_cmd(str(PREFLIGHT), "--html", str(html), "--meta", str(meta), "--output-html", str(checked), "--report", str(report))
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertRegex(report.read_text(encoding="utf-8"), r"review_status: (PASS|FIXED_PASS)")

    def test_preflight_blocks_clone_selection_in_html_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selection = {
                "selection_status": "ROUTE_TO_TEMPLATE_CLONE",
                "selection_type": "template_clone",
                "route_kind": "template_clone",
                "source_skill": "民事一审诉讼",
                "doc_type": "民事起诉状",
                "business_scene": "民间借贷纠纷",
                "clone_template_id": "civil_complaint_private_lending_v1",
            }
            html, meta, checked, report = self.write_profile_selection_preflight_fixture(
                root,
                selection=selection,
                profile="litigation_standard",
                doc_type="民事起诉状",
                title="民事起诉状",
            )
            proc = self.run_cmd(str(PREFLIGHT), "--html", str(html), "--meta", str(meta), "--output-html", str(checked), "--report", str(report))
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("不得进入普通 HTML 导出", report.read_text(encoding="utf-8"))

    def test_preflight_blocks_profile_incompatible_with_registered_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html, meta, checked, report = self.write_basic_preflight_fixture(root, profile="entrustment_contract")
            proc = self.run_cmd(str(PREFLIGHT), "--html", str(html), "--meta", str(meta), "--output-html", str(checked), "--report", str(report))
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("profile entrustment_contract 不兼容模板", report.read_text(encoding="utf-8"))

    def test_preflight_blocks_unregistered_template_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html, meta, checked, report = self.write_basic_preflight_fixture(root, template_id="unregistered_contract_template_v1")
            proc = self.run_cmd(str(PREFLIGHT), "--html", str(html), "--meta", str(meta), "--output-html", str(checked), "--report", str(report))
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("content_template_id 未命中 legal-template-registry.json", report.read_text(encoding="utf-8"))

    def test_preflight_blocks_template_sha_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html, meta, checked, report = self.write_basic_preflight_fixture(root, template_sha256="0" * 64)
            proc = self.run_cmd(str(PREFLIGHT), "--html", str(html), "--meta", str(meta), "--output-html", str(checked), "--report", str(report))
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("preflight-meta 模板 sha256 不一致", report.read_text(encoding="utf-8"))

    def test_health_check_blocks_meta_five_point_and_single_spacing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "bad.docx"
            write_docx(docx, size=21, line=240)
            proc = self.run_cmd(str(HEALTH), "--docx", str(docx), "--expect-title", "解除委托协议", "--format-standard", "contract_standard")
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("font size below", proc.stdout)
            self.assertIn("line spacing is not 1.5x", proc.stdout)

    def test_contract_standard_export_passes_format_gate(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.matter_path) as tmp:
            root = Path(tmp)
            html = root / "draft_checked.html"
            report = root / "出稿前审查报告.md"
            output = root / "解除委托协议正式测试.docx"
            html.write_text(
                """<!doctype html><html><body>
<h1>解除委托协议</h1>
<p class="meta">甲方：长春新同洲物业服务有限公司</p>
<p>正文测试段落。</p>
<p class="signature">广东广和（长春）律师事务所 律师：潘睿</p>
</body></html>""",
                encoding="utf-8",
            )
            write_preflight_report(report)
            export = self.run_cmd(str(EXPORT), "--input", str(html), "--output", str(output), "--profile", "contract_standard", "--preflight-report", str(report))
            self.assertEqual(export.returncode, 0, export.stdout)
            health = self.run_cmd(str(HEALTH), "--docx", str(output), "--expect-title", "解除委托协议", "--format-standard", "contract_standard")
            self.assertEqual(health.returncode, 0, health.stdout)


if __name__ == "__main__":
    unittest.main()
