#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit that a formal legal DOCX delivery has all required trace artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "draft.html",
    "preflight-meta.json",
    "draft_checked.html",
    "出稿前审查报告.md",
    "health-check-report.txt",
]
ALLOWED_PREFLIGHT_STATUS = {"PASS", "FIXED_PASS"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def preflight_status(path: Path) -> str | None:
    for line in read_text(path).splitlines():
        if line.startswith("review_status:"):
            return line.split(":", 1)[1].strip()
    return None


def audit(bundle_dir: Path, docx: Path) -> dict[str, Any]:
    errors: list[str] = []
    bundle = bundle_dir.expanduser().resolve()
    docx_path = docx.expanduser().resolve()

    for name in REQUIRED_FILES:
        path = bundle / name
        if not path.exists():
            errors.append(f"missing required artifact: {name}")
        elif not path.is_file():
            errors.append(f"required artifact is not a file: {name}")

    meta_path = bundle / "preflight-meta.json"
    if meta_path.exists() and meta_path.is_file():
        try:
            meta = json.loads(read_text(meta_path))
            if not isinstance(meta, dict):
                errors.append("preflight-meta.json root must be an object")
        except Exception as exc:
            errors.append(f"preflight-meta.json parse failed: {exc}")

    report_path = bundle / "出稿前审查报告.md"
    if report_path.exists() and report_path.is_file():
        status = preflight_status(report_path)
        if status not in ALLOWED_PREFLIGHT_STATUS:
            errors.append(f"preflight report status is not allowed: {status or 'missing'}")

    if not docx_path.exists():
        errors.append(f"missing final docx: {docx_path}")
    elif not docx_path.is_file():
        errors.append(f"final docx is not a file: {docx_path}")
    elif docx_path.suffix.lower() != ".docx":
        errors.append(f"final output is not .docx: {docx_path}")

    health_path = bundle / "health-check-report.txt"
    if health_path.exists() and health_path.is_file():
        health_text = read_text(health_path)
        if "health_check_ok: True" not in health_text:
            errors.append("health check record is not PASS")
        if str(docx_path) not in health_text and docx_path.name not in health_text:
            errors.append("health check record does not reference final docx")

    return {
        "status": "PASS" if not errors else "FAIL",
        "bundle_dir": str(bundle),
        "docx": str(docx_path),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit formal legal DOCX delivery trace artifacts.")
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--docx", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.bundle_dir, args.docx)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
