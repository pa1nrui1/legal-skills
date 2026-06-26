#!/usr/bin/env python3
"""Shared helpers for legal Word export regression tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


LEGAL_DIR = Path(__file__).resolve().parents[3]
EXPORT_DIR = LEGAL_DIR / "法律文书模板与导出"
PREFLIGHT = LEGAL_DIR / "法律文书出稿前审查" / "scripts" / "preflight_check.py"
EXPORT = EXPORT_DIR / "scripts" / "html_to_docx.py"
FILLER = EXPORT_DIR / "scripts" / "fill_docx_template.py"
HEALTH = EXPORT_DIR / "scripts" / "health_check.py"
SELECTOR = EXPORT_DIR / "scripts" / "select_legal_template.py"
AUDIT = EXPORT_DIR / "scripts" / "audit_formal_delivery.py"
RUNTIME_PYTHON = Path(os.environ.get("LEGAL_QC_PYTHON", sys.executable)).expanduser()


def export_python() -> str:
    return str(RUNTIME_PYTHON if RUNTIME_PYTHON.exists() else Path(sys.executable))


def make_workspace(root: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    workspace = root / "legal_workspace"
    matter = workspace / "matter"
    system_record = workspace / "_系统记录" / "matter"
    current_matter = workspace / "_系统记录" / "当前事项.md"
    matter.mkdir(parents=True, exist_ok=True)
    system_record.mkdir(parents=True, exist_ok=True)
    current_matter.parent.mkdir(parents=True, exist_ok=True)
    current_matter.write_text(
        f"业务文件路径：{matter}\n系统记录路径：{system_record}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["LEGAL_WORKSPACE"] = str(workspace)
    env["LEGAL_CURRENT_MATTER"] = str(current_matter)
    return matter, system_record, current_matter, env
