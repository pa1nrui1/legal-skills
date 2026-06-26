#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert a structured case material packet into complaint draft inputs.

This script is a deterministic test harness for the legal complaint workflow.
It does not OCR or infer unstated facts; missing values become known_gaps.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
BUSINESS_GATE = SCRIPT_DIR / "complaint_business_gate.py"
PROFILE = "litigation_standard"


def load_gate():
    spec = importlib.util.spec_from_file_location("complaint_business_gate", BUSINESS_GATE)
    if not spec or not spec.loader:
        raise RuntimeError("cannot load complaint_business_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("material packet root must be a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def source_label(material: dict[str, Any], key: str) -> str:
    name = material.get("name") or material.get("file") or material.get("id") or "合成材料"
    return f"[材料包:{name}/{key}]"


def add_field(
    fields: dict[str, Any],
    source_map: dict[str, str],
    known_gaps: list[dict[str, str]],
    field_id: str,
    value: Any,
    source: str,
    label: str,
) -> None:
    if value not in ("", None, [], {}):
        fields[field_id] = value
        source_map[field_id] = source
    else:
        known_gaps.append({"field_id": field_id, "label": label, "reason": "材料包未提供，禁止自动补全"})


def party_fields(prefix: str, party: dict[str, Any], source: str, fields: dict[str, Any], source_map: dict[str, str], gaps: list[dict[str, str]]) -> None:
    person_type = party.get("type", "natural")
    base = f"{prefix}.{person_type}"
    for key, label in [
        ("name", "姓名/名称"),
        ("id_number", "身份证号/证照号码"),
        ("phone", "联系电话"),
        ("address", "住所/地址"),
    ]:
        add_field(fields, source_map, gaps, f"{base}.{key}", party.get(key), source, f"{prefix}.{label}")


def evidence_summary(evidence: list[dict[str, Any]]) -> str:
    names = [str(item.get("name")) for item in evidence if item.get("name")]
    return "；".join(names)


def build_reading_review(packet: dict[str, Any]) -> str:
    materials = packet.get("materials", [])
    facts = packet.get("facts", {})
    evidence = packet.get("evidence", [])
    material_names = "、".join(str(item.get("name") or item.get("id") or "未命名材料") for item in materials) or "无"
    key_data = [
        f"案由：{packet.get('case_cause') or '未提供'}",
        f"原告：{packet.get('plaintiff', {}).get('name') or '缺失'}",
        f"被告：{packet.get('defendant', {}).get('name') or '缺失'}",
        f"本金/主要金额：{facts.get('principal') or facts.get('amount') or '缺失'}",
        f"关键日期：{facts.get('loan_date') or facts.get('contract_date') or '缺失'}",
        f"证据：{evidence_summary(evidence) or '缺失'}",
    ]
    return (
        "# 读取复查摘要\n"
        f"文件名：{material_names}\n"
        "读取方式：结构化合成材料包读取\n"
        "读取覆盖范围：material packet 全部 JSON 字段\n"
        f"关键数据提取：{'；'.join(key_data)}\n"
        "存疑项：以 known_gaps 记录为准\n"
        "完整性评估：仅用于本轮材料抽取链路测试，不代表真实案卷已完整读取\n"
    )


def build_source_boundary(packet: dict[str, Any]) -> str:
    return (
        "# 来源边界记录\n"
        "已核验：结构化合成材料包中的显式字段\n"
        "未核验：真实文件原文、OCR、法规现行状态、外部案例\n"
        "缺口：以 known_gaps 或 preflight-meta.json known_gaps 为准\n"
        "输出边界：仅用于材料抽取到起诉状输入的回归测试，不作为正式法律文书\n"
    )


def build_legal_verification(packet: dict[str, Any]) -> tuple[str, list[str]]:
    refs = packet.get("legal_references", [])
    if not refs:
        return "# 法规校验摘要\n已核验：本测试材料包未引用实体法条。\n现行有效：不适用\n", []
    missing = []
    lines = ["# 法规校验摘要"]
    for idx, item in enumerate(refs, 1):
        if not isinstance(item, dict) or not item.get("verification"):
            missing.append(f"legal_references[{idx}]")
            continue
        lines.append(f"- {item.get('name', '未命名法规')}：{item.get('verification')}")
    if missing:
        lines.append("未完成核验：" + "、".join(missing))
    return "\n".join(lines) + "\n", missing


def build_user_confirmation(packet: dict[str, Any]) -> str:
    confirmations = packet.get("confirmations", [])
    if not confirmations:
        return "# 用户确认记录\n已确认：使用合成材料包进行回归测试。\n"
    lines = ["# 用户确认记录"]
    lines.extend(f"- {item}" for item in confirmations)
    return "\n".join(lines) + "\n"


def common_records(packet: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    paths = {
        "reading_review": out_dir / "reading_review.md",
        "source_boundary": out_dir / "source_boundary.md",
        "legal_verification": out_dir / "legal_verification.md",
        "user_confirmation": out_dir / "user_confirmation.md",
    }
    legal_text, _ = build_legal_verification(packet)
    write_text(paths["reading_review"], build_reading_review(packet))
    write_text(paths["source_boundary"], build_source_boundary(packet))
    write_text(paths["legal_verification"], legal_text)
    write_text(paths["user_confirmation"], build_user_confirmation(packet))
    return paths


def build_complaint_data(packet: dict[str, Any], route_info: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    source_map: dict[str, str] = {}
    gaps: list[dict[str, str]] = []
    facts = packet.get("facts", {})
    evidence = packet.get("evidence", [])
    material = (packet.get("materials") or [{}])[0]

    party_fields("plaintiff", packet.get("plaintiff", {}), source_label(material, "plaintiff"), fields, source_map, gaps)
    party_fields("defendant", packet.get("defendant", {}), source_label(material, "defendant"), fields, source_map, gaps)
    party_fields("service", packet.get("service", packet.get("plaintiff", {})), source_label(material, "service"), fields, source_map, gaps)
    add_field(fields, source_map, gaps, "claims.principal", facts.get("principal") or facts.get("amount"), source_label(material, "principal"), "本金/主要金额")
    add_field(fields, source_map, gaps, "claims.interest", facts.get("interest"), source_label(material, "interest"), "利息")
    add_field(fields, source_map, gaps, "claims.total", facts.get("total"), source_label(material, "total"), "合计金额")
    add_field(fields, source_map, gaps, "facts.loan_date", facts.get("loan_date") or facts.get("contract_date"), source_label(material, "date"), "关键日期")
    add_field(fields, source_map, gaps, "facts.summary", facts.get("summary"), source_label(material, "summary"), "事实摘要")
    add_field(fields, source_map, gaps, "evidence.summary", evidence_summary(evidence), source_label(material, "evidence"), "证据名称")
    add_field(fields, source_map, gaps, "signature.petitioner", packet.get("plaintiff", {}).get("name"), source_label(material, "signature"), "具状人")

    return {
        "template_id": route_info.get("template_id"),
        "case_cause": packet.get("case_cause"),
        "fields": fields,
        "source_map": source_map,
        "known_gaps": gaps,
    }


def build_html(packet: dict[str, Any]) -> str:
    plaintiff = packet.get("plaintiff", {})
    defendant = packet.get("defendant", {})
    facts = packet.get("facts", {})
    evidence = packet.get("evidence", [])
    esc = html.escape
    claim_amount = facts.get("amount") or facts.get("principal") or "金额待补充"
    summary = facts.get("summary") or "事实摘要待补充"
    evidence_text = evidence_summary(evidence) or "证据待补充"
    return f"""<!doctype html>
<html>
<body>
<article>
<h1>民事起诉状</h1>
<p class="meta">原告：{esc(str(plaintiff.get('name') or '待补充'))}，联系电话：{esc(str(plaintiff.get('phone') or '待补充'))}。</p>
<p class="meta">被告：{esc(str(defendant.get('name') or '待补充'))}，联系电话：{esc(str(defendant.get('phone') or '待补充'))}。</p>
<section>
<h2>诉讼请求</h2>
<p>1. 请求判令被告承担与本案有关的付款责任，暂计{esc(str(claim_amount))}。</p>
<p>2. 请求判令被告承担本案诉讼费用。</p>
</section>
<section>
<h2>事实与理由</h2>
<p>{esc(str(summary))}</p>
</section>
<section>
<h2>证据线索</h2>
<p>{esc(evidence_text)}</p>
</section>
<p class="signature">具状人：{esc(str(plaintiff.get('name') or '待补充'))}</p>
</article>
</body>
</html>
"""


def write_template_clone_inputs(packet: dict[str, Any], out_dir: Path, records: dict[str, Path], route_info: dict[str, Any]) -> dict[str, Any]:
    complaint_data = build_complaint_data(packet, route_info)
    complaint_path = out_dir / "complaint-data.json"
    write_json(complaint_path, complaint_data)
    validation = gate.validate_output(str(packet.get("case_cause") or ""), str(packet.get("doc_type") or "民事起诉状"), "template_clone", complaint_path)
    return {
        "route": "template_clone",
        "complaint_data": str(complaint_path),
        "records": {k: str(v) for k, v in records.items()},
        "validation": validation,
    }


def write_html_inputs(packet: dict[str, Any], out_dir: Path, records: dict[str, Path], route_info: dict[str, Any]) -> dict[str, Any]:
    draft = out_dir / "draft.html"
    meta = out_dir / "preflight-meta.json"
    known_gaps = []
    for party_key in ["plaintiff", "defendant"]:
        party = packet.get(party_key, {})
        for field in ["name", "id_number", "phone", "address"]:
            if not party.get(field):
                known_gaps.append(f"{party_key}.{field}")
    if not (packet.get("facts", {}).get("amount") or packet.get("facts", {}).get("principal")):
        known_gaps.append("claims.amount")
    write_text(draft, build_html(packet))
    write_json(
        meta,
        {
            "source_skill": "诉讼文书起草",
            "doc_type": packet.get("doc_type") or "民事起诉状",
            "case_cause": packet.get("case_cause"),
            "output_purpose": "工作草稿",
            "profile": PROFILE,
            "evidence": {
                "reading_review_path": str(records["reading_review"]),
                "source_boundary_path": str(records["source_boundary"]),
                "legal_verification_path": str(records["legal_verification"]),
                "user_confirmation_source": str(records["user_confirmation"]),
            },
            "required_confirmations": [],
            "known_gaps": known_gaps,
        },
    )
    return {
        "route": "html",
        "draft_html": str(draft),
        "preflight_meta": str(meta),
        "known_gaps": known_gaps,
        "records": {k: str(v) for k, v in records.items()},
    }


def convert(packet: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    route_info = gate.route(str(packet.get("case_cause") or ""), str(packet.get("doc_type") or "民事起诉状"))
    records = common_records(packet, out_dir)
    legal_text, missing_legal = build_legal_verification(packet)
    if missing_legal:
        result = {
            "status": "NEEDS_LEGAL_VERIFICATION",
            "route": route_info,
            "missing_legal_verification": missing_legal,
            "records": {k: str(v) for k, v in records.items()},
        }
        write_json(out_dir / "material-extraction-report.json", result)
        return result
    if route_info["status"] != "PASS":
        result = {
            "status": "NEEDS_CONFIRMATION",
            "route": route_info,
            "records": {k: str(v) for k, v in records.items()},
        }
        write_json(out_dir / "material-extraction-report.json", result)
        return result
    if route_info["route"] == "template_clone":
        result = write_template_clone_inputs(packet, out_dir, records, route_info)
    else:
        result = write_html_inputs(packet, out_dir, records, route_info)
    result["status"] = "PASS" if result.get("validation", {}).get("status", "PASS") == "PASS" else "FAIL"
    result["case_cause"] = packet.get("case_cause")
    write_json(out_dir / "material-extraction-report.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert structured materials to complaint input artifacts.")
    parser.add_argument("--materials", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    packet = load_json(args.materials)
    result = convert(packet, args.out.expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
