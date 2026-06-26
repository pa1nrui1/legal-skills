#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-button QC for DOCX template clone filling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
MANIFEST_PATH = Path(
    os.environ.get("LEGAL_TEMPLATE_CLONE_MANIFEST", str(SKILL_DIR / "assets" / "template-clone-manifest.json"))
).expanduser()
FILLER_PATH = SCRIPT_DIR / "fill_docx_template.py"
DEFAULT_RENDER = Path(os.environ.get("LEGAL_DOCX_RENDER_SCRIPT", "__missing_render_script__")).expanduser()
DEFAULT_PYTHON = Path(os.environ.get("LEGAL_QC_PYTHON", sys.executable)).expanduser()
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_config_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def load_template(template_id: str) -> dict[str, Any]:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for item in data.get("templates", []):
        if item.get("template_id") == template_id:
            return item
    raise ValueError(f"unknown template_id: {template_id}")


def load_templates() -> list[dict[str, Any]]:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    templates = data.get("templates", [])
    if not isinstance(templates, list):
        raise ValueError("template clone manifest templates must be an array")
    return [item for item in templates if isinstance(item, dict)]


def inspect_docx(path: Path) -> dict[str, Any]:
    with ZipFile(path) as zf:
        names = set(zf.namelist())
        document = etree.fromstring(zf.read("word/document.xml"))
        settings_has_track = False
        if "word/settings.xml" in names:
            settings = etree.fromstring(zf.read("word/settings.xml"))
            settings_has_track = bool(settings.xpath(".//w:trackRevisions", namespaces=NS))
        text = "".join(document.xpath(".//w:t/text()", namespaces=NS))
    return {
        "tables": len(document.xpath(".//w:tbl", namespaces=NS)),
        "grid_span": len(document.xpath(".//w:gridSpan", namespaces=NS)),
        "vmerge": len(document.xpath(".//w:vMerge", namespaces=NS)),
        "row_heights": len(document.xpath(".//w:trHeight", namespaces=NS)),
        "insertions": len(document.xpath(".//w:ins", namespaces=NS)),
        "deletions": len(document.xpath(".//w:del", namespaces=NS)),
        "trackRevisions": settings_has_track,
        "comments_part": "word/comments.xml" in names,
        "text": text,
    }


def fixture_private_lending_basic() -> tuple[dict[str, Any], dict[str, Any]]:
    complaint_data = {
        "template_id": "civil_complaint_private_lending_v1",
        "fields": {
            "plaintiff.natural.name": "张三",
            "plaintiff.natural.phone": "13800000000",
            "plaintiff.natural.id_number": "220102199001011234",
            "service.address": "长春市净月区示例地址",
            "service.receiver": "张三",
            "service.phone": "13800000000",
            "claims.principal": "100000元",
            "claims.interest": "5000元",
            "claims.total": "105000元",
            "signature.petitioner": "张三",
            "signature.date": "2026年6月25日"
        },
        "source_map": {
            "plaintiff.natural.name": "fixture",
            "plaintiff.natural.phone": "fixture",
            "plaintiff.natural.id_number": "fixture",
            "service.address": "fixture",
            "service.receiver": "fixture",
            "service.phone": "fixture",
            "claims.principal": "fixture",
            "claims.interest": "fixture",
            "claims.total": "fixture",
            "signature.petitioner": "fixture",
            "signature.date": "fixture"
        },
        "known_gaps": []
    }
    fill_plan = {
        "template_id": "civil_complaint_private_lending_v1",
        "fields": [
            {
                "field_id": "plaintiff.natural.name",
                "value": "张三",
                "target": {"table_index": 1, "row_index": 3, "cell_index": 2, "anchor_text": "姓名："},
                "mode": "append_after_anchor"
            },
            {
                "field_id": "plaintiff.natural.phone",
                "value": "13800000000",
                "target": {"table_index": 1, "row_index": 3, "cell_index": 2, "anchor_text": "联系电话："},
                "mode": "append_after_anchor"
            },
            {
                "field_id": "plaintiff.natural.id_number",
                "value": "220102199001011234",
                "target": {"table_index": 1, "row_index": 3, "cell_index": 2, "anchor_text": "证件号码："},
                "mode": "append_after_anchor"
            },
            {
                "field_id": "service.address",
                "value": "长春市净月区示例地址",
                "target": {"table_index": 1, "row_index": 6, "cell_index": 2, "anchor_text": "地址："},
                "mode": "append_after_anchor"
            },
            {
                "field_id": "service.receiver",
                "value": "张三",
                "target": {"table_index": 1, "row_index": 6, "cell_index": 2, "anchor_text": "收件人："},
                "mode": "append_after_anchor"
            },
            {
                "field_id": "service.phone",
                "value": "13800000000",
                "target": {"table_index": 1, "row_index": 6, "cell_index": 2, "anchor_text": "电话："},
                "mode": "append_after_anchor"
            },
            {
                "field_id": "claims.principal",
                "value": "截至2026年6月25日止，尚欠本金100000元",
                "target": {
                    "table_index": 2,
                    "row_index": 8,
                    "cell_index": 2,
                    "anchor_text": "截至   年  月   日止，尚欠本金         元"
                },
                "mode": "replace_anchor"
            },
            {
                "field_id": "claims.interest",
                "value": "截至2026年6月25日止，欠利息5000元；",
                "target": {"table_index": 3, "row_index": 1, "cell_index": 2, "anchor_text": "截至   年  月  日止，欠利息    元；"},
                "mode": "replace_anchor"
            },
            {
                "field_id": "claims.total",
                "value": "105000元",
                "target": {"table_index": 3, "row_index": 6, "cell_index": 2},
                "mode": "replace_cell"
            },
        ]
    }
    return complaint_data, fill_plan


def render_docx(python: Path, render_script: Path, docx: Path, out_dir: Path) -> tuple[bool, str]:
    if not render_script.exists():
        return True, f"render skipped: render script not configured or missing: {render_script}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(python), str(render_script), str(docx), "--output_dir", str(out_dir), "--emit_pdf"]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode == 0, proc.stdout


def run_structure_only_qc(
    *,
    template: dict[str, Any],
    out_dir: Path,
    python: Path,
    render_script: Path,
) -> dict[str, Any]:
    template_path = resolve_config_path(str(template["source_docx"]))
    failures: list[str] = []
    if not template_path.exists():
        failures.append(f"template source missing: {template_path}")
        template_audit: dict[str, Any] = {}
    elif sha256(template_path) != template["sha256"]:
        failures.append("template sha256 mismatch")
        template_audit = inspect_docx(template_path)
        failures.extend(compare_template(template, template_audit))
    else:
        template_audit = inspect_docx(template_path)
        failures.extend(compare_template(template, template_audit))
    render_dir = out_dir / "render"
    render_ok, render_log = render_docx(python, render_script, template_path, render_dir)
    if not render_ok:
        failures.append("render failed")
    render_pages = len(list(render_dir.glob("page-*.png")))
    if render_ok and render_pages <= 0:
        failures.append("render produced no pages")
    report = {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "template_id": template.get("template_id"),
        "case_cause": template.get("case_cause"),
        "fixture": "structure_only",
        "template_audit": {k: v for k, v in template_audit.items() if k != "text"},
        "render_pages": render_pages,
        "expected_template_render_pages": template.get("expected_render_pages"),
        "paths": {
            "template_docx": str(template_path),
            "render_dir": str(render_dir),
        },
        "render_stdout": render_log,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "qc-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def compare_template(template: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    checks = [
        ("tables", "expected_tables"),
        ("grid_span", "expected_grid_span"),
        ("vmerge", "expected_vmerge"),
        ("row_heights", "expected_row_heights"),
    ]
    for actual_key, expected_key in checks:
        if actual[actual_key] != template[expected_key]:
            failures.append(f"{actual_key}: {actual[actual_key]} != {template[expected_key]}")
    for anchor in template.get("required_anchors", []):
        if anchor not in actual["text"]:
            failures.append(f"required anchor missing: {anchor}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DOCX template clone QC.")
    parser.add_argument("--template-id")
    parser.add_argument("--all", action="store_true", help="Run structure/render QC for every registered complaint template.")
    parser.add_argument("--fixture", default="private_lending_basic")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--render-script", type=Path, default=DEFAULT_RENDER)
    args = parser.parse_args()

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.all:
        reports = []
        for template in load_templates():
            template_dir = out_dir / str(template.get("template_id"))
            reports.append(
                run_structure_only_qc(
                    template=template,
                    out_dir=template_dir,
                    python=args.python,
                    render_script=args.render_script,
                )
            )
        summary = {
            "status": "PASS" if all(report["status"] == "PASS" for report in reports) else "FAIL",
            "fixture": "structure_only",
            "template_count": len(reports),
            "reports": reports,
        }
        (out_dir / "all-template-qc-report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["status"] == "PASS" else 2

    if not args.template_id:
        raise SystemExit("--template-id is required unless --all is used")
    template = load_template(args.template_id)
    template_path = resolve_config_path(str(template["source_docx"]))
    failures: list[str] = []
    if not template_path.exists():
        failures.append(f"template source missing: {template_path}")
        template_audit: dict[str, Any] = {}
    elif sha256(template_path) != template["sha256"]:
        failures.append("template sha256 mismatch")
        template_audit = inspect_docx(template_path)
        failures.extend(f"template {item}" for item in compare_template(template, template_audit))
    else:
        template_audit = inspect_docx(template_path)
        failures.extend(f"template {item}" for item in compare_template(template, template_audit))

    if args.fixture == "structure_only":
        report = run_structure_only_qc(
            template=template,
            out_dir=out_dir,
            python=args.python,
            render_script=args.render_script,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 2

    if args.fixture != "private_lending_basic":
        failures.append(f"unknown fixture: {args.fixture}")
        complaint_data, fill_plan = {}, {"fields": []}
    else:
        complaint_data, fill_plan = fixture_private_lending_basic()
    data_path = out_dir / "complaint-data.json"
    plan_path = out_dir / "fill-plan.json"
    data_path.write_text(json.dumps(complaint_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan_path.write_text(json.dumps(fill_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output_docx = out_dir / "民间借贷纠纷民事起诉状-模板克隆填充.docx"
    fill_log = out_dir / "fill-execution-log.json"
    fill_cmd = [
        str(args.python),
        str(FILLER_PATH),
        "--template",
        str(template_path),
        "--plan",
        str(plan_path),
        "--output",
        str(output_docx),
        "--log",
        str(fill_log),
        "--allow-unchecked",
    ]
    if template_path.exists():
        fill_proc = subprocess.run(fill_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    else:
        fill_proc = subprocess.CompletedProcess(fill_cmd, 2, "", f"template source missing: {template_path}")
    if fill_proc.returncode != 0:
        failures.append("fill_docx_template failed")

    output_audit: dict[str, Any] = {}
    if output_docx.exists():
        output_audit = inspect_docx(output_docx)
        failures.extend(f"output {item}" for item in compare_template(template, output_audit))
        if output_audit["insertions"] or output_audit["deletions"] or output_audit["trackRevisions"] or output_audit["comments_part"]:
            failures.append("output is not clean")
        for needle in ["姓名：张三", "尚欠本金100000元", "欠利息5000元", "105000元"]:
            if needle not in output_audit["text"]:
                failures.append(f"filled text missing: {needle}")
    else:
        failures.append("output docx missing")

    render_dir = out_dir / "render"
    render_ok, render_log = (False, "")
    if output_docx.exists():
        render_ok, render_log = render_docx(args.python, args.render_script, output_docx, render_dir)
        if not render_ok:
            failures.append("render failed")
    render_pages = len(list(render_dir.glob("page-*.png")))
    if render_ok and render_pages <= 0:
        failures.append("render produced no pages")

    report = {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "template_id": args.template_id,
        "fixture": args.fixture,
        "template_audit": {k: v for k, v in template_audit.items() if k != "text"},
        "output_audit": {k: v for k, v in output_audit.items() if k != "text"},
        "render_pages": render_pages,
        "expected_template_render_pages": template.get("expected_render_pages"),
        "paths": {
            "complaint_data": str(data_path),
            "fill_plan": str(plan_path),
            "output_docx": str(output_docx),
            "fill_log": str(fill_log),
            "render_dir": str(render_dir),
        },
        "fill_stdout": fill_proc.stdout,
        "render_stdout": render_log,
    }
    (out_dir / "qc-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_lines = [
        "# 模板克隆填充质控报告",
        "",
        f"status: {report['status']}",
        f"template_id: {args.template_id}",
        f"render_pages: {render_pages}",
        "",
        "failures:",
    ]
    md_lines.extend(f"- {item}" for item in (failures or ["无"]))
    (out_dir / "qc-report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
