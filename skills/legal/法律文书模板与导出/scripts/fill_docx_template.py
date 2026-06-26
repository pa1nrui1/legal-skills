#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clone a DOCX template and fill fields without tracked changes."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
MATTER_ROOT = Path(os.environ.get("LEGAL_WORKSPACE", ".")).expanduser()
SYSTEM_RECORD_ROOT = MATTER_ROOT / "_系统记录"
DRAFT_OUTPUT_NAME_PATTERN = re.compile(r"draft|unchecked|草稿|实验|未审查|未出稿")


def qn(local: str) -> str:
    return f"{{{W_NS}}}{local}"


@dataclass
class FillResult:
    field_id: str
    status: str
    message: str


def cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS))


def set_cell_text(cell: etree._Element, value: str) -> None:
    texts = cell.xpath(".//w:t", namespaces=NS)
    if not texts:
        paragraph = cell.find(".//w:p", namespaces=NS)
        if paragraph is None:
            paragraph = etree.SubElement(cell, qn("p"))
        run = etree.SubElement(paragraph, qn("r"))
        text_node = etree.SubElement(run, qn("t"))
        text_node.text = value
        return
    texts[0].text = value
    for extra in texts[1:]:
        extra.text = ""


def replace_in_text_node(cell: etree._Element, anchor: str, value: str, mode: str) -> bool:
    for text_node in cell.xpath(".//w:t", namespaces=NS):
        if text_node.text and anchor in text_node.text:
            if mode == "append_after_anchor":
                text_node.text = text_node.text.replace(anchor, anchor + value, 1)
            elif mode == "replace_anchor":
                text_node.text = text_node.text.replace(anchor, value, 1)
            else:
                raise ValueError(f"unsupported text-node mode: {mode}")
            return True
    full_text = cell_text(cell)
    if anchor in full_text:
        if mode == "append_after_anchor":
            set_cell_text(cell, full_text.replace(anchor, anchor + value, 1))
        elif mode == "replace_anchor":
            set_cell_text(cell, full_text.replace(anchor, value, 1))
        else:
            raise ValueError(f"unsupported text-node mode: {mode}")
        return True
    return False


def target_cell(document: etree._Element, target: dict[str, Any]) -> etree._Element:
    tables = document.xpath(".//w:tbl", namespaces=NS)
    table_index = int(target["table_index"]) - 1
    row_index = int(target["row_index"]) - 1
    cell_index = int(target["cell_index"]) - 1
    try:
        table = tables[table_index]
        row = table.xpath("./w:tr", namespaces=NS)[row_index]
        cell = row.xpath("./w:tc", namespaces=NS)[cell_index]
    except IndexError as exc:
        raise ValueError(
            f"target not found: table={table_index + 1}, row={row_index + 1}, cell={cell_index + 1}"
        ) from exc
    return cell


def apply_field(document: etree._Element, field: dict[str, Any]) -> FillResult:
    field_id = str(field.get("field_id") or "")
    value = str(field.get("value") or "")
    mode = str(field.get("mode") or "append_after_anchor")
    target = field.get("target")
    if not field_id:
        return FillResult("", "failed", "missing field_id")
    if not isinstance(target, dict):
        return FillResult(field_id, "failed", "missing target")
    try:
        cell = target_cell(document, target)
        anchor = str(target.get("anchor_text") or "")
        if mode in {"append_after_anchor", "replace_anchor"}:
            if not anchor:
                raise ValueError("anchor_text is required")
            if anchor not in cell_text(cell):
                raise ValueError(f"anchor not found in target cell: {anchor}")
            if not replace_in_text_node(cell, anchor, value, mode):
                raise ValueError(f"anchor cannot be filled safely: {anchor}")
        elif mode == "replace_cell":
            set_cell_text(cell, value)
        else:
            raise ValueError(f"unsupported mode: {mode}")
        return FillResult(field_id, "applied", "ok")
    except Exception as exc:
        return FillResult(field_id, "failed", str(exc))


def clean_revision_settings(parts: dict[str, bytes]) -> None:
    settings_name = "word/settings.xml"
    if settings_name not in parts:
        return
    settings = etree.fromstring(parts[settings_name])
    for node in settings.xpath(".//w:trackRevisions", namespaces=NS):
        node.getparent().remove(node)
    parts[settings_name] = etree.tostring(
        settings, xml_declaration=True, encoding="UTF-8", standalone=True
    )


def inspect_cleanliness(document: etree._Element, parts: dict[str, bytes]) -> dict[str, Any]:
    settings_has_track = False
    if "word/settings.xml" in parts:
        settings = etree.fromstring(parts["word/settings.xml"])
        settings_has_track = bool(settings.xpath(".//w:trackRevisions", namespaces=NS))
    return {
        "insertions": len(document.xpath(".//w:ins", namespaces=NS)),
        "deletions": len(document.xpath(".//w:del", namespaces=NS)),
        "trackRevisions": settings_has_track,
        "comments_part": "word/comments.xml" in parts,
    }


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_output_path(output_path: Path, allow_unchecked: bool) -> None:
    resolved = output_path.expanduser().resolve()
    if resolved.suffix.lower() != ".docx":
        raise ValueError("DOCX output path must end with .docx")

    if allow_unchecked:
        if is_relative_to(resolved, MATTER_ROOT):
            raise ValueError("unchecked DOCX export must not write into formal business area")
        return

    if ".cache" in resolved.parts:
        raise ValueError("formal DOCX output must not be under .cache")
    if is_relative_to(resolved, SYSTEM_RECORD_ROOT):
        raise ValueError("formal DOCX output must not be under system record root")
    if not is_relative_to(resolved, MATTER_ROOT):
        raise ValueError("formal DOCX output must be under business matter root")
    if DRAFT_OUTPUT_NAME_PATTERN.search(resolved.name.lower()):
        raise ValueError("formal DOCX filename must not look like draft or experiment")


def fill_docx_template(template: Path, plan_path: Path, output: Path, log_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    fields = plan.get("fields")
    if not isinstance(fields, list):
        raise ValueError("fill plan must contain fields array")

    with ZipFile(template, "r") as zin:
        parts = {name: zin.read(name) for name in zin.namelist()}
    if "word/document.xml" not in parts:
        raise ValueError("template missing word/document.xml")

    document = etree.fromstring(parts["word/document.xml"])
    results = [apply_field(document, field) for field in fields if isinstance(field, dict)]
    parts["word/document.xml"] = etree.tostring(
        document, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    clean_revision_settings(parts)
    cleanliness = inspect_cleanliness(etree.fromstring(parts["word/document.xml"]), parts)

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)

    summary = {
        "template": str(template),
        "plan": str(plan_path),
        "output": str(output),
        "applied": sum(1 for result in results if result.status == "applied"),
        "failed": sum(1 for result in results if result.status == "failed"),
        "results": [result.__dict__ for result in results],
        "cleanliness": cleanliness,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill a DOCX template without tracked changes.")
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--allow-unchecked", action="store_true", help="Only for explicit non-deliverable tests.")
    args = parser.parse_args()
    validate_output_path(args.output, args.allow_unchecked)
    summary = fill_docx_template(args.template, args.plan, args.output, args.log)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 and not any(summary["cleanliness"].values()) else 2


if __name__ == "__main__":
    sys.exit(main())
