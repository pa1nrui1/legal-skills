#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Business-side routing gate for civil complaint generation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
LEGAL_DIR = SCRIPT_DIR.parents[1]
CLONE_MANIFEST_PATH = LEGAL_DIR / "法律文书模板与导出" / "assets" / "template-clone-manifest.json"
ELEMENTAL_REQUIRED_OUTPUTS = ["complaint-data.json", "fill-plan.json", "qc-meta.json"]
HTML_REQUIRED_OUTPUTS = ["draft.html", "preflight-meta.json"]
CORE_FIELD_GROUPS = ["plaintiff", "defendant", "claims", "facts", "evidence", "signature"]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return data


def load_templates() -> list[dict[str, Any]]:
    data = load_json(CLONE_MANIFEST_PATH)
    templates = data.get("templates", [])
    if not isinstance(templates, list):
        raise ValueError("template-clone-manifest.json templates must be an array")
    return [item for item in templates if isinstance(item, dict)]


def normalize_text(value: str) -> str:
    return re.sub(r"[\s　：:，,。；;（）()【】\\[\\]「」\"']", "", value or "")


def template_by_case_cause() -> dict[str, dict[str, Any]]:
    return {str(item.get("case_cause") or ""): item for item in load_templates() if item.get("case_cause")}


def fuzzy_candidates(case_cause: str, template_map: dict[str, dict[str, Any]]) -> list[str]:
    normalized = normalize_text(case_cause)
    if not normalized:
        return []
    candidates: list[str] = []
    for registered in template_map:
        reg_norm = normalize_text(registered)
        reg_stem = reg_norm.removesuffix("纠纷")
        if normalized == reg_stem or reg_stem in normalized or normalized in reg_stem:
            candidates.append(registered)
    if "借款" in normalized and "金融借款合同纠纷" in template_map:
        candidates.append("金融借款合同纠纷")
    if ("借贷" in normalized or "借款" in normalized) and "民间借贷纠纷" in template_map:
        candidates.append("民间借贷纠纷")
    return sorted(set(candidates), key=candidates.index)


def route(case_cause: str, doc_type: str) -> dict[str, Any]:
    template_map = template_by_case_cause()
    doc = normalize_text(doc_type)
    cause = str(case_cause or "").strip()

    if not cause:
        return {
            "status": "NEEDS_CONFIRMATION",
            "route": "needs_confirmation",
            "reason": "缺少案由，不能判断要素式或 HTML 技术路线。",
            "candidate_case_causes": list(template_map.keys()),
        }

    if "起诉状" not in doc:
        return {
            "status": "PASS",
            "route": "html",
            "reason": "非起诉状文书不适用要素式起诉状母版。",
            "required_outputs": HTML_REQUIRED_OUTPUTS,
        }

    if cause in template_map:
        template = template_map[cause]
        return {
            "status": "PASS",
            "route": "template_clone",
            "reason": "案由命中登记的要素式起诉状母版，必须走 DOCX 母版克隆填充链路。",
            "case_cause": cause,
            "template_id": template.get("template_id"),
            "required_outputs": ELEMENTAL_REQUIRED_OUTPUTS,
            "forbidden_outputs": HTML_REQUIRED_OUTPUTS,
        }

    candidates = fuzzy_candidates(cause, template_map)
    if candidates:
        return {
            "status": "NEEDS_CONFIRMATION",
            "route": "needs_confirmation",
            "reason": "案由表述未精确命中登记模板，但与要素式案由相近，需先确认案由。",
            "case_cause": cause,
            "candidate_case_causes": candidates,
        }

    return {
        "status": "PASS",
        "route": "html",
        "reason": "案由未命中登记的要素式起诉状母版，走普通 HTML 技术路线。",
        "case_cause": cause,
        "required_outputs": HTML_REQUIRED_OUTPUTS,
        "forbidden_outputs": ELEMENTAL_REQUIRED_OUTPUTS,
    }


def gap_field_ids(known_gaps: Any) -> set[str]:
    if not isinstance(known_gaps, list):
        return set()
    ids: set[str] = set()
    for item in known_gaps:
        if isinstance(item, dict):
            field_id = item.get("field_id") or item.get("field") or item.get("id")
            if field_id:
                ids.add(str(field_id))
        elif item:
            ids.add(str(item))
    return ids


def group_covered(group: str, fields: dict[str, Any], gaps: set[str]) -> bool:
    prefix = f"{group}."
    return any(field_id == group or field_id.startswith(prefix) for field_id in fields) or any(
        gap == group or gap.startswith(prefix) for gap in gaps
    )


def validate_complaint_data(data: dict[str, Any], expected_template_id: str | None) -> list[str]:
    failures: list[str] = []
    fields = data.get("fields")
    source_map = data.get("source_map")
    known_gaps = data.get("known_gaps", [])

    if expected_template_id and data.get("template_id") != expected_template_id:
        failures.append(f"complaint-data.json template_id 不匹配：{data.get('template_id')} != {expected_template_id}")
    if not isinstance(fields, dict) or not fields:
        failures.append("complaint-data.json 必须包含非空 fields 对象")
        fields = {}
    if not isinstance(source_map, dict):
        failures.append("complaint-data.json 必须包含 source_map 对象")
        source_map = {}
    if not isinstance(known_gaps, list):
        failures.append("complaint-data.json known_gaps 必须是数组")
        known_gaps = []

    gaps = gap_field_ids(known_gaps)
    for group in CORE_FIELD_GROUPS:
        if not group_covered(group, fields, gaps):
            failures.append(f"complaint-data.json 缺少核心字段组或缺口说明：{group}")

    for field_id, value in fields.items():
        if field_id not in source_map and field_id not in gaps:
            failures.append(f"字段缺少来源或缺口说明：{field_id}")
        if value in ("", None) and field_id not in gaps:
            failures.append(f"空字段必须写入 known_gaps：{field_id}")
        if "agent" in str(field_id).lower() or "代理人" in str(value):
            failures.append(f"起诉状字段不得列示诉讼代理人信息：{field_id}")
    return failures


def validate_output(case_cause: str, doc_type: str, output_kind: str, complaint_data_path: Path | None) -> dict[str, Any]:
    route_info = route(case_cause, doc_type)
    failures: list[str] = []
    expected = route_info["route"]

    if expected == "needs_confirmation":
        failures.append("案由需要先确认，不能直接生成正式业务输出。")
    elif expected == "template_clone" and output_kind != "template_clone":
        failures.append("该案由必须走要素式 complaint-data.json / fill-plan.json / qc-meta.json，不得生成普通 HTML 起诉状。")
    elif expected == "html" and output_kind != "html":
        failures.append("该案由未登记要素式母版，不得强行走 DOCX 母版克隆填充链路。")

    if expected == "template_clone" and output_kind == "template_clone":
        if not complaint_data_path:
            failures.append("要素式业务输出缺少 complaint-data.json。")
        elif not complaint_data_path.exists():
            failures.append(f"complaint-data.json 不存在：{complaint_data_path}")
        else:
            try:
                complaint_data = load_json(complaint_data_path)
                failures.extend(validate_complaint_data(complaint_data, str(route_info.get("template_id") or "")))
            except Exception as exc:
                failures.append(f"complaint-data.json 无法解析：{exc}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "route": route_info,
        "output_kind": output_kind,
        "failures": failures,
    }


def write_report(path: Path | None, data: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check civil complaint business routing and field payloads.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    route_parser = subparsers.add_parser("route")
    route_parser.add_argument("--case-cause", required=True)
    route_parser.add_argument("--doc-type", default="民事起诉状")
    route_parser.add_argument("--report", type=Path)

    check_parser = subparsers.add_parser("check-output")
    check_parser.add_argument("--case-cause", required=True)
    check_parser.add_argument("--doc-type", default="民事起诉状")
    check_parser.add_argument("--output-kind", required=True, choices=["html", "template_clone"])
    check_parser.add_argument("--complaint-data", type=Path)
    check_parser.add_argument("--report", type=Path)

    args = parser.parse_args()
    if args.command == "route":
        result = route(args.case_cause, args.doc_type)
        write_report(args.report, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 2

    result = validate_output(args.case_cause, args.doc_type, args.output_kind, args.complaint_data)
    write_report(args.report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
