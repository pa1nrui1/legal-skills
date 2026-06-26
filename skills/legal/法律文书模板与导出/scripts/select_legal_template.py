#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Select a registered legal content template and compatible Word profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
LEGAL_DIR = SKILL_DIR.parent
REGISTRY_PATH = Path(os.environ.get("LEGAL_TEMPLATE_REGISTRY", str(SKILL_DIR / "assets" / "legal-template-registry.json"))).expanduser()
FORMAT_MANIFEST_PATH = SKILL_DIR / "assets" / "template-manifest.json"
CLONE_MANIFEST_PATH = Path(
    os.environ.get("LEGAL_TEMPLATE_CLONE_MANIFEST", str(SKILL_DIR / "assets" / "template-clone-manifest.json"))
).expanduser()

REPORT_MARKERS = ["报告", "法律意见", "法律服务建议书", "检索报告", "案例汇编", "案件提纲", "审查意见", "尽调"]
CONTRACT_MARKERS = ["合同", "协议", "补充协议", "解除协议", "终止协议"]
LITIGATION_MARKERS = [
    "代理词",
    "答辩状",
    "申请书",
    "意见书",
    "辩护词",
    "辩护意见",
    "质证意见",
    "上诉状",
    "证据目录",
    "证据清单",
    "保全",
    "调查令",
    "诉讼",
    "仲裁",
]
JUDGMENT_MARKERS = ["判决书", "裁定书", "审理报告"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_unresolved_env(value: str) -> bool:
    return "$" in value and os.path.expandvars(value) == value


def resolve_config_path(value: str) -> Path:
    expanded = Path(os.path.expandvars(value)).expanduser()
    if expanded.is_absolute():
        return expanded
    if expanded.parts and expanded.parts[0] in {LEGAL_DIR.name, "skills"}:
        return LEGAL_DIR.parent / expanded
    return LEGAL_DIR / expanded


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("templates"), list):
        raise ValueError("legal-template-registry.json must contain templates array")
    return data


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} root must be object")
    return data


def text_hits(value: str, needles: list[str]) -> list[str]:
    haystack = value.lower()
    return [needle for needle in needles if str(needle).lower() in haystack]


def clean_template_stem(source: str) -> str:
    stem = Path(source).stem
    for suffix in ["排版规范", "模板", "框架", "格式"]:
        stem = stem.replace(suffix, "")
    return stem


def negated_hit(value: str, term: str) -> bool:
    for marker in ["不是", "非", "并非", "不属于", "无需", "不要", "不走"]:
        if f"{marker}{term}" in value:
            return True
    return False


def positive_text_hits(value: str, needles: list[str]) -> list[str]:
    haystack = value.lower()
    return [needle for needle in needles if str(needle).lower() in haystack and not negated_hit(value, str(needle))]


def profile_version(profile: str) -> str:
    path = SKILL_DIR / "assets" / "profiles" / f"{profile}.json"
    if not path.exists():
        return "1.0"
    data = load_json_file(path)
    return str(data.get("version") or "1.0")


def profile_selection(
    *,
    selection_type: str,
    source_skill: str,
    doc_type: str,
    business_scene: str,
    profile: str,
    reasons: list[str],
    format_reference_source: str = "",
    fallback_reason: str = "",
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = {
        "selection_status": "PASS",
        "selection_type": selection_type,
        "route_kind": "html_to_docx",
        "source_skill": source_skill,
        "doc_type": doc_type,
        "business_scene": business_scene,
        "profile_id": profile,
        "profile_version": profile_version(profile),
        "format_standard": profile,
        "match_reasons": reasons,
        "candidates": candidates or [],
    }
    if format_reference_source:
        result["format_reference_source"] = format_reference_source
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result


def complaint_like(doc_type: str) -> bool:
    return "起诉状" in doc_type


def select_clone_template(
    *,
    source_skill: str,
    doc_type: str,
    business_scene: str,
    user_request: str,
) -> dict[str, Any] | None:
    if not complaint_like(doc_type):
        return None
    manifest = load_json_file(CLONE_MANIFEST_PATH)
    query = "\n".join([source_skill, doc_type, business_scene, user_request])
    matches: list[dict[str, Any]] = []
    for template in manifest.get("templates", []):
        if not isinstance(template, dict):
            continue
        case_cause = str(template.get("case_cause") or "")
        template_doc_type = str(template.get("doc_type") or "")
        if template_doc_type and template_doc_type not in doc_type and doc_type not in template_doc_type:
            continue
        if case_cause and case_cause in query:
            matches.append(template)
    if not matches:
        raise ValueError("complaint document requires case_cause/template-clone routing; no registered complaint template matched, so it must not fall back to a generic profile")
    if len(matches) > 1:
        ids = ", ".join(str(item.get("template_id")) for item in matches)
        raise ValueError(f"ambiguous complaint clone template match: {ids}")
    selected = matches[0]
    return {
        "selection_status": "ROUTE_TO_TEMPLATE_CLONE",
        "selection_type": "template_clone",
        "route_kind": "template_clone",
        "source_skill": source_skill,
        "doc_type": doc_type,
        "business_scene": business_scene,
        "clone_template_id": selected.get("template_id"),
        "clone_template_doc_type": selected.get("doc_type"),
        "case_cause": selected.get("case_cause"),
        "clone_template_path": selected.get("source_docx"),
        "clone_template_sha256": selected.get("sha256"),
        "next_action": "Use complaint-data.json, fill-plan.json, qc-meta.json and the DOCX clone chain; do not use HTML fallback export.",
        "match_reasons": [f"case_cause: {selected.get('case_cause')}"],
    }


def select_format_reference(
    *,
    source_skill: str,
    doc_type: str,
    business_scene: str,
    user_request: str,
) -> dict[str, Any] | None:
    manifest = load_json_file(FORMAT_MANIFEST_PATH)
    query = "\n".join([doc_type, business_scene, user_request])
    candidates: list[dict[str, Any]] = []
    for item in manifest.get("format_candidates", []):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        profile = str(item.get("profile") or "")
        stem = Path(source).stem
        clean_stem = clean_template_stem(source)
        score = 0
        reasons: list[str] = []
        for term in [stem, clean_stem]:
            if term and term in query and not negated_hit(query, term):
                score += 50
                reasons.append(f"format source: {term}")
        if score <= 0:
            continue
        if source_skill and source.startswith(f"{source_skill}/"):
            score += 15
            reasons.append("source_skill path match")
        candidates.append(
            {
                "source": source,
                "profile": profile,
                "score": score,
                "reasons": reasons,
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item["score"], reverse=True)
    selected = candidates[0]
    return profile_selection(
        selection_type="format_reference",
        source_skill=source_skill,
        doc_type=doc_type,
        business_scene=business_scene,
        profile=selected["profile"],
        reasons=selected["reasons"],
        format_reference_source=selected["source"],
        candidates=candidates,
    )


def infer_profile_fallback(
    *,
    source_skill: str,
    doc_type: str,
    business_scene: str,
    user_request: str,
) -> dict[str, Any]:
    query = "\n".join([doc_type, business_scene, user_request])
    if positive_text_hits(query, JUDGMENT_MARKERS):
        return profile_selection(
            selection_type="profile_fallback",
            source_skill=source_skill,
            doc_type=doc_type,
            business_scene=business_scene,
            profile="judgment_style",
            reasons=["fallback category: judgment_style"],
            fallback_reason="no registered template matched; judgment/court-style document category inferred",
        )
    if positive_text_hits(query, REPORT_MARKERS) or source_skill in {"初步法律分析", "法规案例检索", "案件讨论与提纲"}:
        return profile_selection(
            selection_type="profile_fallback",
            source_skill=source_skill,
            doc_type=doc_type,
            business_scene=business_scene,
            profile="legal_report",
            reasons=["fallback category: legal_report"],
            fallback_reason="no registered template matched; report/opinion category inferred",
        )
    if positive_text_hits(doc_type, CONTRACT_MARKERS) and not positive_text_hits(doc_type, REPORT_MARKERS):
        return profile_selection(
            selection_type="profile_fallback",
            source_skill=source_skill,
            doc_type=doc_type,
            business_scene=business_scene,
            profile="contract_standard",
            reasons=["fallback category: contract_standard"],
            fallback_reason="no registered template matched; contract/agreement category inferred",
        )
    if positive_text_hits(query, LITIGATION_MARKERS) or any(marker in source_skill for marker in ["诉讼", "辩护", "立案", "庭审", "特殊程序", "审查起诉", "侦查"]):
        return profile_selection(
            selection_type="profile_fallback",
            source_skill=source_skill,
            doc_type=doc_type,
            business_scene=business_scene,
            profile="litigation_standard",
            reasons=["fallback category: litigation_standard"],
            fallback_reason="no registered template matched; litigation/application category inferred",
        )
    return profile_selection(
        selection_type="profile_fallback",
        source_skill=source_skill,
        doc_type=doc_type,
        business_scene=business_scene,
        profile="fallback_desktop_word",
        reasons=["fallback category: fallback_desktop_word"],
        fallback_reason="no registered template matched and no reliable document category inferred",
    )


def score_template(template: dict[str, Any], query: str, source_template_path: str | None) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    if source_template_path:
        source_path = str(resolve_config_path(str(template.get("source_path") or "")).resolve())
        supplied_path = str(resolve_config_path(source_template_path).resolve())
        if source_path == supplied_path:
            score += 100
            reasons.append("source_path exact match")
        else:
            return 0, []
    excludes = text_hits(query, [str(item) for item in template.get("exclude_keywords", [])])
    if excludes:
        return 0, [f"excluded by keywords: {', '.join(excludes)}"]
    for field, weight in [("doc_types", 30), ("business_scenes", 20), ("keywords", 10)]:
        hits = text_hits(query, [str(item) for item in template.get(field, [])])
        if hits:
            score += weight * len(hits)
            reasons.append(f"{field}: {', '.join(hits)}")
    return score, reasons


def select_template(
    *,
    source_skill: str,
    doc_type: str,
    business_scene: str,
    user_request: str,
    source_template_path: str | None = None,
    preferred_profile: str | None = None,
) -> dict[str, Any]:
    registry = load_registry()
    query = "\n".join([source_skill, doc_type, business_scene, user_request])
    candidates: list[dict[str, Any]] = []
    for template in registry["templates"]:
        if source_skill and template.get("owner_skill") not in {source_skill, "法律文书模板与导出"}:
            # Keep cross-skill templates available through textual hits only when no source path is supplied.
            if source_template_path:
                continue
        score, reasons = score_template(template, query, source_template_path)
        if score <= 0:
            continue
        source_value = str(template.get("source_path") or "")
        source_path = resolve_config_path(source_value)
        actual_sha = sha256(source_path) if source_path.exists() else ""
        candidates.append(
            {
                "template_id": template.get("template_id"),
                "version": template.get("version"),
                "score": score,
                "reasons": reasons,
                "source_path": str(source_path),
                "expected_sha256": template.get("sha256"),
                "actual_sha256": actual_sha,
                "default_profile": template.get("default_profile"),
                "compatible_profiles": template.get("compatible_profiles", []),
                "profile_versions": template.get("profile_versions", {}),
                "format_standard": template.get("format_standard"),
            }
        )
    if not candidates:
        if source_template_path:
            raise ValueError("no registered legal template matched the request")
        clone_selection = select_clone_template(
            source_skill=source_skill,
            doc_type=doc_type,
            business_scene=business_scene,
            user_request=user_request,
        )
        if clone_selection:
            return clone_selection
        format_selection = select_format_reference(
            source_skill=source_skill,
            doc_type=doc_type,
            business_scene=business_scene,
            user_request=user_request,
        )
        if format_selection:
            return format_selection
        return infer_profile_fallback(
            source_skill=source_skill,
            doc_type=doc_type,
            business_scene=business_scene,
            user_request=user_request,
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    top_score = candidates[0]["score"]
    top = [item for item in candidates if item["score"] == top_score]
    if len(top) > 1:
        ids = ", ".join(str(item["template_id"]) for item in top)
        raise ValueError(f"ambiguous registered legal template match: {ids}")
    selected = candidates[0]
    if selected["expected_sha256"] and selected["actual_sha256"] != selected["expected_sha256"]:
        raise ValueError(f"registered template sha256 mismatch: {selected['template_id']}")
    profile = preferred_profile or selected["default_profile"]
    if profile not in selected["compatible_profiles"]:
        raise ValueError(f"profile {profile} is not compatible with template {selected['template_id']}")
    return {
        "selection_status": "PASS",
        "selection_type": "registered_content_template",
        "route_kind": "html_to_docx",
        "source_skill": source_skill,
        "doc_type": doc_type,
        "business_scene": business_scene,
        "content_template_id": selected["template_id"],
        "content_template_version": selected["version"],
        "content_template_path": selected["source_path"],
        "content_template_sha256": selected["expected_sha256"],
        "profile_id": profile,
        "profile_version": selected["profile_versions"].get(profile, "1.0"),
        "format_standard": selected["format_standard"],
        "compatible_profiles": selected["compatible_profiles"],
        "match_reasons": selected["reasons"],
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Select a registered legal template.")
    parser.add_argument("--source-skill", required=True)
    parser.add_argument("--doc-type", required=True)
    parser.add_argument("--business-scene", default="")
    parser.add_argument("--user-request", default="")
    parser.add_argument("--source-template-path")
    parser.add_argument("--preferred-profile")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = select_template(
            source_skill=args.source_skill,
            doc_type=args.doc_type,
            business_scene=args.business_scene,
            user_request=args.user_request,
            source_template_path=args.source_template_path,
            preferred_profile=args.preferred_profile,
        )
    except Exception as exc:
        print(f"template_selection_error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"template_selection: {args.output}")
    print(f"selection_status: {result.get('selection_status')}")
    if result.get("content_template_id"):
        print(f"content_template_id: {result['content_template_id']}")
    if result.get("clone_template_id"):
        print(f"clone_template_id: {result['clone_template_id']}")
    if result.get("profile_id"):
        print(f"profile_id: {result['profile_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
