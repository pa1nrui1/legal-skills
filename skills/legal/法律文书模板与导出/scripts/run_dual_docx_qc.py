#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-button smoke test for both DOCX export quality gates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
LEGAL_DIR = SCRIPT_DIR.parents[1]
PREFLIGHT = LEGAL_DIR / "法律文书出稿前审查" / "scripts" / "preflight_check.py"
HTML_EXPORT = SCRIPT_DIR / "html_to_docx.py"
CLONE_QC = SCRIPT_DIR / "run_template_clone_qc.py"
HEALTH = SCRIPT_DIR / "health_check.py"
DEFAULT_PYTHON = Path(os.environ.get("LEGAL_QC_PYTHON", sys.executable)).expanduser()


def load_clone_fixture() -> tuple[dict, dict]:
    spec = importlib.util.spec_from_file_location("run_template_clone_qc", CLONE_QC)
    if not spec or not spec.loader:
        raise RuntimeError("cannot load run_template_clone_qc fixture helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.fixture_private_lending_basic()


def run(cmd: list[str], env: dict[str, str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    return proc.returncode, proc.stdout


def ensure_test_workspace(root: Path) -> tuple[dict[str, str], str, str]:
    env = os.environ.copy()
    matter_root = Path(env.get("LEGAL_WORKSPACE", str(root / "_legal_workspace"))).expanduser().resolve()
    system_root = matter_root / "_系统记录"
    current_matter = Path(env.get("LEGAL_CURRENT_MATTER", str(system_root / "当前事项.md"))).expanduser().resolve()
    matter_path = matter_root / "合成正式事项"
    system_record_path = system_root / "合成正式事项"
    matter_path.mkdir(parents=True, exist_ok=True)
    system_record_path.mkdir(parents=True, exist_ok=True)
    current_matter.parent.mkdir(parents=True, exist_ok=True)
    if not current_matter.exists():
        current_matter.write_text(
            f"业务文件路径：{matter_path}\n系统记录路径：{system_record_path}\n",
            encoding="utf-8",
        )
    env["LEGAL_WORKSPACE"] = str(matter_root)
    env["LEGAL_CURRENT_MATTER"] = str(current_matter)
    return env, str(matter_path), str(system_record_path)


def current_paths(current_matter: Path) -> tuple[str, str]:
    text = current_matter.read_text(encoding="utf-8", errors="ignore")
    matter = re.search(r"业务文件路径：(.+)", text)
    system = re.search(r"系统记录路径：(.+)", text)
    if not matter or not system:
        raise ValueError("当前事项.md 缺少业务文件路径或系统记录路径")
    return matter.group(1).strip(), system.group(1).strip()


def write_html_fixture(root: Path, matter_path: str, system_record_path: str, formal_output_root: Path) -> dict[str, Path]:
    html_dir = root / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    formal_output_root.mkdir(parents=True, exist_ok=True)
    reading = html_dir / "reading_review.md"
    boundary = html_dir / "source_boundary.md"
    draft = html_dir / "draft.html"
    meta = html_dir / "preflight-meta.json"
    checked = html_dir / "draft_checked.html"
    report = html_dir / "出稿前审查报告.md"
    output = formal_output_root / "html通道测试.docx"
    reading.write_text(
        "# 读取复查摘要\n文件名：HTML通道测试材料\n读取方式：合成测试\n关键数据提取：测试原告、测试请求、测试日期\n存疑项：无\n完整性评估：可用于导出链路测试\n",
        encoding="utf-8",
    )
    boundary.write_text(
        "# 来源边界记录\n已核验：HTML通道测试材料\n未核验：无\n缺口：无\n输出边界：仅用于导出链路测试\n",
        encoding="utf-8",
    )
    draft.write_text(
        """<!doctype html><html><body><article>
<h1>民事起诉状</h1>
<p class=\"meta\">原告：测试原告，联系电话：18686488305。</p>
<p>诉讼请求：请求被告支付测试款项1000元。</p>
<p>事实与理由：本段为HTML原通道导出测试正文，不引用法律条文。</p>
<p class=\"signature\">律师：潘睿</p>
<table><tr><th>项目</th><th>内容</th></tr><tr><td>本金</td><td>1000元</td></tr></table>
</article></body></html>
""",
        encoding="utf-8",
    )
    meta.write_text(
        json.dumps(
            {
                "source_skill": "诉讼文书起草",
                "doc_type": "民事起诉状",
                "output_purpose": "正式交付",
                "profile": "litigation_standard",
                "matter_path": matter_path,
                "system_record_path": system_record_path,
                "evidence": {
                    "reading_review_path": str(reading),
                    "source_boundary_path": str(boundary),
                },
                "required_confirmations": [],
                "known_gaps": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "draft": draft,
        "meta": meta,
        "checked": checked,
        "report": report,
        "output": output,
    }


def write_clone_preflight_fixture(root: Path, matter_path: str, system_record_path: str) -> dict[str, Path]:
    clone_preflight = root / "clone_preflight"
    clone_preflight.mkdir(parents=True, exist_ok=True)
    complaint_data, fill_plan = load_clone_fixture()
    reading = clone_preflight / "reading_review.md"
    boundary = clone_preflight / "source_boundary.md"
    legal = clone_preflight / "legal_verification.md"
    confirmation = clone_preflight / "user_confirmation.md"
    data = clone_preflight / "complaint-data.json"
    plan = clone_preflight / "fill-plan.json"
    meta = clone_preflight / "qc-meta.json"
    report = clone_preflight / "要素式出稿前审查报告.md"

    reading.write_text(
        "# 读取复查摘要\n文件名：民间借贷要素式起诉状合成材料\n读取方式：合成测试\n关键数据提取：张三、本金100000元、利息5000元、合计105000元\n存疑项：无\n完整性评估：可用于要素式起诉状填充链路测试\n",
        encoding="utf-8",
    )
    boundary.write_text(
        "# 来源边界记录\n已核验：民间借贷要素式起诉状合成材料\n未核验：无\n缺口：无\n输出边界：仅用于模板克隆链路测试\n",
        encoding="utf-8",
    )
    legal.write_text(
        "# 法规校验摘要\n已核验：本测试不输出实体法条正文，仅验证要素式起诉状技术链路。\n现行有效：不适用\n",
        encoding="utf-8",
    )
    confirmation.write_text(
        "# 用户确认记录\n已确认：使用合成测试字段验证要素式起诉状模板克隆填充链路。\n",
        encoding="utf-8",
    )
    data.write_text(json.dumps(complaint_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan.write_text(json.dumps(fill_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta.write_text(
        json.dumps(
            {
                "template_id": "civil_complaint_private_lending_v1",
                "source_skill": "诉讼文书起草",
                "doc_type": "民事起诉状",
                "case_cause": "民间借贷纠纷",
                "output_purpose": "正式交付",
                "matter_path": matter_path,
                "system_record_path": system_record_path,
                "legal_verification_required": True,
                "evidence": {
                    "reading_review_path": str(reading),
                    "source_boundary_path": str(boundary),
                    "legal_verification_path": str(legal),
                    "user_confirmation_source": str(confirmation),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "complaint_data": data,
        "fill_plan": plan,
        "qc_meta": meta,
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run both HTML and template-clone DOCX QC gates.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--python", default=DEFAULT_PYTHON, type=Path)
    args = parser.parse_args()

    root = args.out.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    env, matter_path, system_record_path = ensure_test_workspace(root)
    Path(matter_path).mkdir(parents=True, exist_ok=True)
    Path(system_record_path).mkdir(parents=True, exist_ok=True)
    formal_output_root = Path(matter_path) / "_SkillOpt合成Word回归" / root.name / "html"
    html = write_html_fixture(root, matter_path, system_record_path, formal_output_root)
    clone_preflight = write_clone_preflight_fixture(root, matter_path, system_record_path)
    clone_dir = root / "clone"

    steps = []
    commands = [
        (
            "html_preflight",
            [
                str(args.python),
                str(PREFLIGHT),
                "--html",
                str(html["draft"]),
                "--meta",
                str(html["meta"]),
                "--output-html",
                str(html["checked"]),
                "--report",
                str(html["report"]),
            ],
        ),
        (
            "html_export",
            [
                str(args.python),
                str(HTML_EXPORT),
                "--input",
                str(html["checked"]),
                "--output",
                str(html["output"]),
                "--profile",
                "litigation_standard",
                "--preflight-report",
                str(html["report"]),
                "--check",
            ],
        ),
        (
            "clone_preflight",
            [
                str(args.python),
                str(PREFLIGHT),
                "--complaint-data",
                str(clone_preflight["complaint_data"]),
                "--fill-plan",
                str(clone_preflight["fill_plan"]),
                "--qc-meta",
                str(clone_preflight["qc_meta"]),
                "--report",
                str(clone_preflight["report"]),
            ],
        ),
        (
            "template_clone_qc",
            [
                str(args.python),
                str(CLONE_QC),
                "--template-id",
                "civil_complaint_private_lending_v1",
                "--fixture",
                "private_lending_basic",
                "--out",
                str(clone_dir),
            ],
        ),
        (
            "html_health",
            [
                str(args.python),
                str(HEALTH),
                "--docx",
                str(html["output"]),
                "--expect-title",
                "民事起诉状",
                "--expect-table",
                "--expect-text",
                "诉讼请求：请求被告支付测试款项1000元。",
                "--expect-text",
                "事实与理由：本段为HTML原通道导出测试正文，不引用法律条文。",
                "--expect-text",
                "潘睿",
            ],
        ),
        (
            "template_clone_health",
            [
                str(args.python),
                str(HEALTH),
                "--docx",
                str(clone_dir / "民间借贷纠纷民事起诉状-模板克隆填充.docx"),
                "--expect-clean-clone",
                "--expect-text",
                "姓名：张三",
                "--expect-text",
                "尚欠本金100000元",
                "--expect-text",
                "欠利息5000元",
                "--expect-text",
                "105000元",
                "--template-clone-report",
                str(clone_dir / "qc-report.json"),
            ],
        ),
    ]
    status = "PASS"
    for name, cmd in commands:
        code, output = run(cmd, env)
        steps.append({"name": name, "returncode": code, "output": output})
        if code != 0:
            status = "FAIL"
            break

    summary = {
        "status": status,
        "steps": steps,
        "paths": {
            "html_docx": str(html["output"]),
            "clone_docx": str(clone_dir / "民间借贷纠纷民事起诉状-模板克隆填充.docx"),
            "clone_report": str(clone_dir / "qc-report.json"),
        },
    }
    (root / "dual-qc-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
