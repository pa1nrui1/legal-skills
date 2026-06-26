#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Health checks for the legal document template/export skill."""

from __future__ import annotations

import argparse
import hashlib
from html import unescape as html_unescape
import json
import os
import re
import sys
from pathlib import Path
from zipfile import ZipFile


SKILL_DIR = Path(__file__).resolve().parents[1]
LEGAL_DIR = SKILL_DIR.parent
PROFILES_DIR = SKILL_DIR / "assets" / "profiles"
MANIFEST_PATH = SKILL_DIR / "assets" / "template-manifest.json"
LEGAL_TEMPLATE_REGISTRY_PATH = Path(
    os.environ.get("LEGAL_TEMPLATE_REGISTRY", str(SKILL_DIR / "assets" / "legal-template-registry.json"))
).expanduser()
CLONE_MANIFEST_PATH = Path(
    os.environ.get("LEGAL_TEMPLATE_CLONE_MANIFEST", str(SKILL_DIR / "assets" / "template-clone-manifest.json"))
).expanduser()
MASTER_SKILL = LEGAL_DIR / "法律工作总控" / "SKILL.md"
PREFLIGHT_SKILL = LEGAL_DIR / "法律文书出稿前审查" / "SKILL.md"
EXPORT_SCRIPT = SKILL_DIR / "scripts" / "html_to_docx.py"
CLONE_FILLER_SCRIPT = SKILL_DIR / "scripts" / "fill_docx_template.py"
CLONE_QC_SCRIPT = SKILL_DIR / "scripts" / "run_template_clone_qc.py"
AUDIT_SCRIPT = SKILL_DIR / "scripts" / "audit_formal_delivery.py"

FORMAT_PATTERN = re.compile(
    r"Word输出格式设置|Word输出格式|文书格式规范|排版参数|格式说明|页边距|行距|"
    r"标题.*黑体|正文.*宋体|标题.*宋体|正文.*仿宋|python-docx|Node\.js docx|"
    r"Word生成技术方案|生成Word文档|本地Word|本地word"
)
TECH_PATTERN = re.compile(
    r"python-docx|Node\.js docx|docx库|Word生成技术方案|生成Word文档|doc\.save|"
    r"require\(['\"]docx['\"]\)|Skill: docx|调用 `Skill: docx`|Packer\.toBuffer|"
    r"writeFileSync\([^\n]+\.docx|doc\.save|"
    r"pandoc[^\n]*(?:-o|--output)[^\n]*\.docx|pandoc[^\n]*(?:md|markdown)[^\n]*\.docx|"
    r"(?:md|markdown|Markdown)\s*(?:->|→|转|转换为|生成)\s*docx"
)
SCRIPT_DIRECT_DOCX_PATTERN = re.compile(
    r"require\(['\"]docx['\"]\)|Packer\.toBuffer|new Document\(|writeFileSync\([^\n]+\.docx|doc\.save|"
    r"pandoc[^\n]*(?:-o|--output)[^\n]*\.docx|pandoc[^\n]*(?:md|markdown)[^\n]*\.docx"
)
ALLOWED_TECH_STATUS = {"迁移替换", "保留引用", "暂不迁移"}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def scan_format_candidates() -> list[str]:
    candidates: list[str] = []
    paths = list(LEGAL_DIR.glob("*/templates/**/*.md"))
    paths.extend(LEGAL_DIR.glob("*/references/**/*排版规范.md"))
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        if FORMAT_PATTERN.search(text):
            candidates.append(str(path.relative_to(LEGAL_DIR)))
    return sorted(candidates)


def check_profiles() -> list[str]:
    errors: list[str] = []
    required = {"litigation_standard", "legal_report", "judgment_style", "fallback_desktop_word", "contract_standard"}
    found = {p.stem for p in PROFILES_DIR.glob("*.json")}
    missing = required - found
    if missing:
        errors.append(f"missing profiles: {sorted(missing)}")
    for path in PROFILES_DIR.glob("*.json"):
        try:
            data = load_json(path)
        except Exception as exc:
            errors.append(f"profile parse failed {path.name}: {exc}")
            continue
        for key in ["page", "fonts", "paragraph", "table", "page_number"]:
            if key not in data:
                errors.append(f"profile {path.name} missing {key}")
    return errors


def check_manifest() -> list[str]:
    errors: list[str] = []
    try:
        data = load_json(MANIFEST_PATH)
    except Exception as exc:
        return [f"manifest parse failed: {exc}"]
    profiles = {p.stem for p in PROFILES_DIR.glob("*.json")}
    for item in data.get("format_candidates", []):
        source = LEGAL_DIR / item.get("source", "")
        if not source.exists():
            errors.append(f"format source missing: {item.get('source')}")
        if item.get("profile") not in profiles:
            errors.append(f"unknown profile for {item.get('source')}: {item.get('profile')}")
    for item in data.get("technical_plan_assessments", []):
        if item.get("status") not in ALLOWED_TECH_STATUS:
            errors.append(f"invalid tech status for {item.get('source')}: {item.get('status')}")
    return errors


def check_legal_template_registry() -> list[str]:
    errors: list[str] = []
    try:
        data = load_json(LEGAL_TEMPLATE_REGISTRY_PATH)
    except Exception as exc:
        return [f"legal template registry parse failed: {exc}"]
    profiles = {p.stem for p in PROFILES_DIR.glob("*.json")}
    seen_ids: set[str] = set()
    for item in data.get("templates", []):
        template_id = str(item.get("template_id") or "")
        if not template_id:
            errors.append("legal template item missing template_id")
            continue
        if template_id in seen_ids:
            errors.append(f"duplicate legal template id: {template_id}")
        seen_ids.add(template_id)
        for key in ["version", "owner_skill", "source_path", "sha256", "default_profile", "compatible_profiles", "format_standard"]:
            if key not in item or item.get(key) in ("", None, []):
                errors.append(f"legal template {template_id} missing {key}")
        source_value = str(item.get("source_path") or "")
        source = resolve_config_path(source_value)
        if not source.exists():
            if not has_unresolved_env(source_value):
                errors.append(f"legal template source missing: {source}")
        elif item.get("sha256") and sha256(source) != item.get("sha256"):
            errors.append(f"legal template sha256 mismatch: {template_id}")
        default_profile = str(item.get("default_profile") or "")
        compatible_profiles = [str(profile) for profile in item.get("compatible_profiles", [])]
        if default_profile and default_profile not in compatible_profiles:
            errors.append(f"legal template default profile not compatible: {template_id}")
        for profile in compatible_profiles:
            if profile not in profiles:
                errors.append(f"legal template {template_id} unknown profile: {profile}")
    return errors


def check_template_clone_manifest() -> list[str]:
    errors: list[str] = []
    if not CLONE_MANIFEST_PATH.exists():
        return ["template clone manifest missing"]
    try:
        data = load_json(CLONE_MANIFEST_PATH)
    except Exception as exc:
        return [f"template clone manifest parse failed: {exc}"]
    for item in data.get("templates", []):
        template_id = item.get("template_id", "")
        source_value = str(item.get("source_docx", ""))
        source = resolve_config_path(source_value)
        if not template_id:
            errors.append("template clone item missing template_id")
        if not source.exists():
            if not has_unresolved_env(source_value):
                errors.append(f"template clone source missing: {source}")
            continue
        expected_hash = item.get("sha256")
        if expected_hash and sha256(source) != expected_hash:
            errors.append(f"template clone sha256 mismatch: {template_id}")
        for key in ["expected_tables", "expected_grid_span", "expected_vmerge", "expected_row_heights"]:
            if key not in item:
                errors.append(f"template clone {template_id} missing {key}")
    for path in [CLONE_FILLER_SCRIPT, CLONE_QC_SCRIPT]:
        if not path.exists():
            errors.append(f"template clone script missing: {path.name}")
    return errors


def check_manifest_coverage() -> list[str]:
    errors: list[str] = []
    manifest = load_json(MANIFEST_PATH)
    manifest_candidates = sorted(item["source"] for item in manifest.get("format_candidates", []))
    scanned_candidates = scan_format_candidates()
    missing_from_manifest = sorted(set(scanned_candidates) - set(manifest_candidates))
    stale_manifest = sorted(set(manifest_candidates) - set(scanned_candidates))
    if missing_from_manifest:
        errors.append(f"format candidates missing from manifest: {missing_from_manifest}")
    if stale_manifest:
        errors.append(f"manifest format candidates no longer detected: {stale_manifest}")
    return errors


def scan_tech_references() -> list[str]:
    references: list[str] = []
    excluded = {
        "法律工作总控/SKILL.md",
        "law-to-markdown/SKILL.md",
    }
    for pattern in ["*/SKILL.md", "*/references/**/*.md", "*/templates/**/*.md", "*/scripts/**/*.js", "*/scripts/**/*.py"]:
        for path in LEGAL_DIR.glob(pattern):
            if SKILL_DIR in path.parents:
                continue
            if "_backups" in path.parts:
                continue
            rel = str(path.relative_to(LEGAL_DIR))
            if rel in excluded:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="ignore")
            if TECH_PATTERN.search(text):
                references.append(rel)
    return sorted(set(references))


def scan_direct_docx_scripts() -> list[str]:
    references: list[str] = []
    allowed = {
        "法律文书模板与导出/scripts/html_to_docx.py",
        "法律文书模板与导出/scripts/health_check.py",
        "law-to-markdown/scripts/law_to_markdown.py",
    }
    for pattern in ["*/scripts/**/*.js", "*/scripts/**/*.py"]:
        for path in LEGAL_DIR.glob(pattern):
            if "_backups" in path.parts:
                continue
            if SKILL_DIR in path.parents and "tests" in path.parts:
                continue
            rel = str(path.relative_to(LEGAL_DIR))
            if rel in allowed:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="ignore")
            if SCRIPT_DIRECT_DOCX_PATTERN.search(text):
                references.append(rel)
    return sorted(set(references))


def check_tech_assessments() -> list[str]:
    errors: list[str] = []
    manifest = load_json(MANIFEST_PATH)
    assessed = {item["source"] for item in manifest.get("technical_plan_assessments", [])}
    found = set(scan_tech_references())
    missing = sorted(found - assessed)
    if missing:
        errors.append(f"technical Word export references missing assessment: {missing}")
    return errors


def check_direct_docx_scripts() -> list[str]:
    errors: list[str] = []
    manifest = load_json(MANIFEST_PATH)
    assessed = {item["source"] for item in manifest.get("technical_plan_assessments", [])}
    found = set(scan_direct_docx_scripts())
    missing = sorted(found - assessed)
    if missing:
        errors.append(f"direct DOCX scripts missing assessment: {missing}")
    for rel in sorted(found & assessed):
        path = LEGAL_DIR / rel
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "LEGAL_ALLOW_LEGACY_DOCX" not in text and "法律文书模板与导出" not in text:
            errors.append(f"direct DOCX script is not guarded: {rel}")
    return errors


def check_master_skill() -> list[str]:
    if not MASTER_SKILL.exists():
        return ["master skill missing"]
    text = MASTER_SKILL.read_text(encoding="utf-8")
    required_bits = [
        "法律文书模板与导出",
        "法律文书出稿前审查",
        ".docx",
        "必须",
        "PASS",
        "FIXED_PASS",
        "不得覆盖",
        "语义 HTML → DOCX",
    ]
    missing = [bit for bit in required_bits if bit not in text]
    return [f"master skill missing forced routing marker: {bit}" for bit in missing]


def check_preflight_integration() -> list[str]:
    errors: list[str] = []
    if not PREFLIGHT_SKILL.exists():
        errors.append("preflight skill missing")
    else:
        text = PREFLIGHT_SKILL.read_text(encoding="utf-8")
        for bit in ["NEEDS_BUSINESS_REVISION", "NEEDS_USER_CONFIRMATION", "NEEDS_MATERIAL", "PASS", "FIXED_PASS"]:
            if bit not in text:
                errors.append(f"preflight skill missing status marker: {bit}")
    export_text = EXPORT_SCRIPT.read_text(encoding="utf-8")
    for bit in ["--preflight-report", "draft_checked.html", "ALLOWED_PREFLIGHT_STATUS", "--allow-unchecked"]:
        if bit not in export_text:
            errors.append(f"export script missing preflight guard marker: {bit}")
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for bit in ["法律文书出稿前审查", "draft_checked.html", "PASS", "FIXED_PASS"]:
        if bit not in skill_text:
            errors.append(f"export skill missing preflight instruction: {bit}")
    if not AUDIT_SCRIPT.exists():
        errors.append("formal delivery audit script missing")
    else:
        audit_text = AUDIT_SCRIPT.read_text(encoding="utf-8", errors="ignore")
        for bit in ["draft.html", "preflight-meta.json", "draft_checked.html", "出稿前审查报告.md", "health-check-report.txt", "health_check_ok: True"]:
            if bit not in audit_text:
                errors.append(f"formal delivery audit script missing marker: {bit}")
    return errors


def check_template_clone_report(path: Path) -> list[str]:
    try:
        report = load_json(path)
    except Exception as exc:
        return [f"template clone report parse failed: {exc}"]
    if report.get("status") != "PASS":
        return [f"template clone report not PASS: {report.get('status')}"]
    return []


def extract_docx_text(document_xml: str) -> str:
    return "".join(
        html_unescape(part)
        for part in re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", document_xml, flags=re.S)
    )


def docx_paragraphs(document_xml: str) -> list[dict[str, object]]:
    paragraphs: list[dict[str, object]] = []
    for paragraph_xml in re.findall(r"<w:p(?:\s[^>]*)?>(.*?)</w:p>", document_xml, flags=re.S):
        text = extract_docx_text(paragraph_xml)
        sizes = [int(value) for value in re.findall(r"<w:sz\s[^>]*w:val=\"(\d+)\"", paragraph_xml)]
        spacing_match = re.search(r"<w:spacing\s([^>]*)/?>", paragraph_xml)
        spacing_attrs: dict[str, str] = {}
        if spacing_match:
            for key, value in re.findall(r"w:(\w+)=\"([^\"]+)\"", spacing_match.group(1)):
                spacing_attrs[key] = value
        fonts = re.findall(r"<w:rFonts\s([^>]*)/?>", paragraph_xml)
        paragraphs.append({"text": text, "sizes": sizes, "spacing": spacing_attrs, "fonts": fonts})
    return paragraphs


def check_contract_standard_format(document_xml: str) -> list[str]:
    errors: list[str] = []
    visible_paragraphs = [p for p in docx_paragraphs(document_xml) if str(p["text"]).strip()]
    if not visible_paragraphs:
        return ["contract_standard format check found no visible paragraphs"]

    for idx, paragraph in enumerate(visible_paragraphs, 1):
        text = str(paragraph["text"]).strip()
        sizes = paragraph["sizes"]
        if not sizes:
            errors.append(f"paragraph {idx} missing explicit font size: {text[:30]}")
            continue
        min_size = min(int(size) for size in sizes)
        if min_size < 24:
            errors.append(f"paragraph {idx} font size below 小四/12pt: {min_size / 2:g}pt ({text[:30]})")

        spacing = paragraph["spacing"]
        line = spacing.get("line")
        line_rule = spacing.get("lineRule", "")
        if not line:
            errors.append(f"paragraph {idx} missing line spacing: {text[:30]}")
            continue
        try:
            line_value = int(line)
        except ValueError:
            errors.append(f"paragraph {idx} invalid line spacing value: {line}")
            continue
        is_multiple_15 = line_value == 360 and line_rule in {"", "auto"}
        is_exact_24_to_28 = 480 <= line_value <= 560 and line_rule == "exact"
        if not (is_multiple_15 or is_exact_24_to_28):
            errors.append(f"paragraph {idx} line spacing is not 1.5x or 24-28pt exact: line={line}, rule={line_rule or 'auto'} ({text[:30]})")
    return errors


def check_docx(
    path: Path,
    expect_title: str | None,
    expect_table: bool,
    expect_texts: list[str],
    *,
    require_page_number: bool = True,
    format_standard: str | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        with ZipFile(path) as zf:
            names = set(zf.namelist())
            if "word/document.xml" not in names:
                return ["word/document.xml missing"]
            document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            footer_xml = "".join(
                zf.read(name).decode("utf-8", errors="ignore")
                for name in names
                if name.startswith("word/footer") and name.endswith(".xml")
            )
    except Exception as exc:
        return [f"docx open failed: {exc}"]
    visible_text = extract_docx_text(document_xml)
    if expect_title and expect_title not in document_xml:
        errors.append(f"title not found: {expect_title}")
    for expect_text in expect_texts:
        if expect_text not in visible_text and expect_text not in document_xml:
            errors.append(f"expected text not found: {expect_text}")
    if "<w:pgMar" not in document_xml:
        errors.append("page margin not found")
    if require_page_number and "PAGE" not in footer_xml:
        errors.append("PAGE field not found in footer")
    if expect_table and "<w:tbl>" not in document_xml:
        errors.append("real table not found")
    if format_standard:
        if format_standard == "contract_standard":
            errors.extend(check_contract_standard_format(document_xml))
        else:
            errors.append(f"unsupported format standard check: {format_standard}")
    return errors


def check_clean_clone_docx(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        with ZipFile(path) as zf:
            names = set(zf.namelist())
            document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            settings_xml = zf.read("word/settings.xml").decode("utf-8", errors="ignore") if "word/settings.xml" in names else ""
    except Exception as exc:
        return [f"clean clone docx open failed: {exc}"]
    if re.search(r"<w:ins(?:\\s|>)", document_xml):
        errors.append("clean clone contains w:ins")
    if re.search(r"<w:del(?:\\s|>)", document_xml):
        errors.append("clean clone contains w:del")
    if "trackRevisions" in settings_xml:
        errors.append("clean clone has trackRevisions enabled")
    if "word/comments.xml" in names:
        errors.append("clean clone contains comments.xml")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Health check legal document export skill.")
    parser.add_argument("--docx", type=Path)
    parser.add_argument("--expect-title")
    parser.add_argument("--expect-table", action="store_true")
    parser.add_argument("--expect-text", action="append", default=[])
    parser.add_argument("--expect-clean-clone", action="store_true")
    parser.add_argument("--template-clone-report", type=Path)
    parser.add_argument("--format-standard")
    parser.add_argument("--profile")
    parser.add_argument("--strict-migration", action="store_true")
    parser.add_argument("--list-tech-references", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    profile_errors = check_profiles()
    manifest_errors = check_manifest()
    registry_errors = check_legal_template_registry()
    clone_manifest_errors = check_template_clone_manifest()
    master_errors = check_master_skill()
    preflight_errors = check_preflight_integration()
    candidates = scan_format_candidates()
    coverage_errors = check_manifest_coverage() if args.strict_migration else []
    tech_errors = check_tech_assessments() if args.strict_migration else []
    direct_script_errors = check_direct_docx_scripts() if args.strict_migration else []
    errors.extend(profile_errors)
    errors.extend(manifest_errors)
    errors.extend(registry_errors)
    errors.extend(clone_manifest_errors)
    errors.extend(master_errors)
    errors.extend(preflight_errors)
    errors.extend(coverage_errors)
    errors.extend(tech_errors)
    errors.extend(direct_script_errors)
    if args.docx:
        errors.extend(
            check_docx(
                args.docx,
                args.expect_title,
                args.expect_table,
                args.expect_text,
                require_page_number=not args.expect_clean_clone,
                format_standard=args.format_standard,
            )
        )
        if args.expect_clean_clone:
            errors.extend(check_clean_clone_docx(args.docx))
    if args.template_clone_report:
        errors.extend(check_template_clone_report(args.template_clone_report))

    print(f"format_candidates_detected: {len(candidates)}")
    print(f"profiles_ok: {not profile_errors}")
    print(f"manifest_ok: {not manifest_errors}")
    print(f"legal_template_registry_ok: {not registry_errors}")
    print(f"template_clone_manifest_ok: {not clone_manifest_errors}")
    print(f"master_routing_ok: {not master_errors}")
    print(f"preflight_integration_ok: {not preflight_errors}")
    if args.strict_migration:
        print(f"manifest_coverage_ok: {not coverage_errors}")
        print(f"tech_assessments_ok: {not tech_errors}")
        print(f"direct_docx_scripts_ok: {not direct_script_errors}")
    if args.list_tech_references:
        print("technical_references:")
        for rel in scan_tech_references():
            print(f"- {rel}")
        print("direct_docx_scripts:")
        for rel in scan_direct_docx_scripts():
            print(f"- {rel}")
    if args.docx:
        print(f"docx_checked: {args.docx}")
    if args.template_clone_report:
        print(f"template_clone_report_checked: {args.template_clone_report}")
    if errors:
        print("errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("health_check_ok: True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
