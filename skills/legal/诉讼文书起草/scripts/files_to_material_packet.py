#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read real files and build a structured material packet for complaint inputs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SCRIPT_DIR = Path(__file__).resolve().parent
MATERIAL_TO_INPUT = SCRIPT_DIR / "material_to_complaint_input.py"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_docx(path: Path) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as zf:
        root = ElementTree.fromstring(zf.read("word/document.xml"))
    parts = []
    for paragraph in root.findall(".//w:p", ns):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        if texts:
            parts.append("".join(texts))
    return "\n".join(parts)


def read_pdf(path: Path) -> str:
    try:
        import fitz  # type: ignore

        doc = fitz.open(path)
        try:
            return "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    except Exception:
        proc = subprocess.run(["pdftotext", str(path), "-"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "pdftotext failed")
        return proc.stdout


def read_image_ocr(path: Path) -> tuple[str, str]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        text = pytesseract.image_to_string(Image.open(path), lang="eng")
    except Exception as exc:
        return "", f"OCR不可用：{exc}"
    text = text.strip()
    if not text:
        return "", "OCR未识别到可用文字"
    return text, "OCR可用"


def read_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    result: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "suffix": suffix,
        "status": "ok",
        "method": "",
        "text": "",
        "issues": [],
    }
    try:
        if suffix in {".txt", ".md"}:
            result["text"] = read_text_file(path)
            result["method"] = "text"
        elif suffix == ".docx":
            result["text"] = read_docx(path)
            result["method"] = "docx-xml"
        elif suffix == ".pdf":
            result["text"] = read_pdf(path)
            result["method"] = "pdf-text"
        elif suffix in IMAGE_SUFFIXES:
            text, note = read_image_ocr(path)
            result["text"] = text
            result["method"] = "ocr"
            if not text:
                result["status"] = "needs_material"
                result["issues"].append(f"[OCR待确认] {note}")
            else:
                result["issues"].append(note)
        else:
            result["status"] = "needs_material"
            result["issues"].append(f"不支持的文件类型：{suffix}")
    except Exception as exc:
        result["status"] = "needs_material"
        result["issues"].append(f"读取失败：{exc}")
    if not str(result.get("text") or "").strip() and result["status"] == "ok":
        result["status"] = "needs_material"
        result["issues"].append("读取结果为空")
    return result


def first_match(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = re.compile(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", re.M)
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return ""


def split_evidence(value: str) -> list[dict[str, str]]:
    if not value:
        return []
    names = [item.strip() for item in re.split(r"[;；、,，]\s*", value) if item.strip()]
    return [{"name": name, "fact": "材料包抽取"} for name in names]


def packet_from_text(case_cause: str, doc_type: str, reads: list[dict[str, Any]]) -> dict[str, Any]:
    full_text = "\n".join(str(item.get("text") or "") for item in reads)
    source_materials = [
        {
            "name": item["name"],
            "file": item["path"],
            "type": item["suffix"].lstrip(".") or "file",
            "read_method": item["method"],
            "issues": item["issues"],
        }
        for item in reads
    ]
    packet = {
        "doc_type": doc_type,
        "case_cause": first_match(full_text, ["案由", "case_cause"]) or case_cause,
        "materials": source_materials,
        "plaintiff": {
            "type": "natural",
            "name": first_match(full_text, ["原告姓名", "plaintiff.name"]),
            "id_number": first_match(full_text, ["原告身份证号", "plaintiff.id_number"]),
            "phone": first_match(full_text, ["原告电话", "plaintiff.phone"]),
            "address": first_match(full_text, ["原告地址", "plaintiff.address"]),
        },
        "defendant": {
            "type": "natural",
            "name": first_match(full_text, ["被告姓名", "defendant.name"]),
            "id_number": first_match(full_text, ["被告身份证号", "defendant.id_number"]),
            "phone": first_match(full_text, ["被告电话", "defendant.phone"]),
            "address": first_match(full_text, ["被告地址", "defendant.address"]),
        },
        "service": {
            "type": "natural",
            "name": first_match(full_text, ["送达收件人", "service.name"]) or first_match(full_text, ["原告姓名", "plaintiff.name"]),
            "phone": first_match(full_text, ["送达电话", "service.phone"]) or first_match(full_text, ["原告电话", "plaintiff.phone"]),
            "address": first_match(full_text, ["送达地址", "service.address"]) or first_match(full_text, ["原告地址", "plaintiff.address"]),
        },
        "facts": {
            "loan_date": first_match(full_text, ["借款日期", "loan_date"]),
            "contract_date": first_match(full_text, ["合同日期", "contract_date"]),
            "principal": first_match(full_text, ["本金", "principal"]),
            "interest": first_match(full_text, ["利息", "interest"]),
            "total": first_match(full_text, ["合计", "total"]),
            "summary": first_match(full_text, ["事实摘要", "summary"]),
        },
        "evidence": split_evidence(first_match(full_text, ["证据", "evidence"])),
        "confirmations": ["使用真实文件读取结果生成结构化材料包回归测试"],
    }
    legal_name = first_match(full_text, ["法律依据", "legal_reference"])
    legal_verification = first_match(full_text, ["法规核验", "legal_verification"])
    if legal_name:
        ref: dict[str, str] = {"name": legal_name}
        if legal_verification:
            ref["verification"] = legal_verification
        packet["legal_references"] = [ref]
    return packet


def reading_report(reads: list[dict[str, Any]], packet: dict[str, Any]) -> str:
    lines = ["# 文件读取复查摘要", ""]
    for item in reads:
        lines.append(f"## {item['name']}")
        lines.append(f"- 读取方式：{item['method'] or '未读取'}")
        lines.append(f"- 状态：{item['status']}")
        lines.append(f"- 存疑项：{'；'.join(item['issues']) if item['issues'] else '无'}")
        lines.append("")
    lines.append("## 关键数据提取")
    lines.append(f"- 案由：{packet.get('case_cause') or '缺失'}")
    lines.append(f"- 原告：{packet.get('plaintiff', {}).get('name') or '缺失'}")
    lines.append(f"- 被告：{packet.get('defendant', {}).get('name') or '缺失'}")
    lines.append(f"- 金额：{packet.get('facts', {}).get('principal') or packet.get('facts', {}).get('total') or '缺失'}")
    lines.append(f"- 日期：{packet.get('facts', {}).get('loan_date') or packet.get('facts', {}).get('contract_date') or '缺失'}")
    lines.append(f"- 证据：{'；'.join(item.get('name', '') for item in packet.get('evidence', [])) or '缺失'}")
    return "\n".join(lines) + "\n"


def run_material_converter(packet_path: Path, out_dir: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(MATERIAL_TO_INPUT), "--materials", str(packet_path), "--out", str(out_dir)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Read real files into a material packet and complaint input artifacts.")
    parser.add_argument("--files", nargs="+", required=True, type=Path)
    parser.add_argument("--case-cause", required=True)
    parser.add_argument("--doc-type", default="民事起诉状")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    reads = [read_file(path.expanduser().resolve()) for path in args.files]
    packet = packet_from_text(args.case_cause, args.doc_type, reads)
    packet_path = out_dir / "materials.json"
    write_json(packet_path, packet)
    (out_dir / "file-reading-review.md").write_text(reading_report(reads, packet), encoding="utf-8")

    bad_reads = [item for item in reads if item["status"] != "ok"]
    if bad_reads and not args.allow_partial:
        result = {
            "status": "NEEDS_MATERIAL",
            "reason": "存在文件读取失败或 OCR 不可用，未生成起诉状输入。",
            "bad_reads": bad_reads,
            "material_packet": str(packet_path),
            "reading_review": str(out_dir / "file-reading-review.md"),
        }
        write_json(out_dir / "file-to-complaint-report.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    code, output = run_material_converter(packet_path, out_dir / "complaint_input")
    result = {
        "status": "PASS" if code == 0 else "FAIL",
        "material_packet": str(packet_path),
        "reading_review": str(out_dir / "file-reading-review.md"),
        "complaint_input_dir": str(out_dir / "complaint_input"),
        "converter_output": output,
    }
    write_json(out_dir / "file-to-complaint-report.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if code == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
