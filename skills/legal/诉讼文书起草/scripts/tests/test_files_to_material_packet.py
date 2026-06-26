#!/usr/bin/env python3
"""Tests for real file reading into complaint material packets."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "files_to_material_packet.py"


def write_docx(path: Path, paragraphs: list[str]) -> None:
    text_xml = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        for text in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{text_xml}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>')
        zf.writestr("word/document.xml", document)


def write_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(path))
    c.setFont("STSong-Light", 12)
    y = 800
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()


class FilesToMaterialPacketTests(unittest.TestCase):
    def run_script(self, root: Path, files: list[Path]) -> subprocess.CompletedProcess[str]:
        out = root / "out"
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--files",
                *[str(path) for path in files],
                "--case-cause",
                "民间借贷纠纷",
                "--out",
                str(out),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_docx_and_pdf_read_into_complaint_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = root / "当事人信息.docx"
            pdf = root / "事实证据.pdf"
            write_docx(
                docx,
                [
                    "案由：民间借贷纠纷",
                    "原告姓名：张三",
                    "原告身份证号：220102199001011234",
                    "原告电话：13800000000",
                    "原告地址：长春市净月区示例地址一",
                    "被告姓名：李四",
                    "被告身份证号：220102198812121234",
                    "被告电话：13900000000",
                    "被告地址：长春市朝阳区示例地址二",
                ],
            )
            write_pdf(
                pdf,
                [
                    "借款日期：2025年1月1日",
                    "本金：100000元",
                    "利息：5000元",
                    "合计：105000元",
                    "事实摘要：2025年1月1日张三向李四出借100000元，李四到期未还。",
                    "证据：借条；银行转账凭证",
                ],
            )
            proc = self.run_script(root, [docx, pdf])
            self.assertEqual(proc.returncode, 0, proc.stdout)
            data_path = root / "out" / "complaint_input" / "complaint-data.json"
            data = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(data["fields"]["plaintiff.natural.name"], "张三")
            self.assertEqual(data["fields"]["defendant.natural.id_number"], "220102198812121234")
            self.assertEqual(data["fields"]["claims.principal"], "100000元")
            self.assertIn("银行转账凭证", data["fields"]["evidence.summary"])
            report = (root / "out" / "file-reading-review.md").read_text(encoding="utf-8")
            self.assertIn("当事人信息.docx", report)
            self.assertIn("事实证据.pdf", report)

    def test_unreadable_image_blocks_complaint_generation(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "空白截图.png"
            Image.new("RGB", (300, 120), "white").save(image)
            proc = self.run_script(root, [image])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("NEEDS_MATERIAL", proc.stdout)
            self.assertIn("OCR", proc.stdout)
            self.assertFalse((root / "out" / "complaint_input" / "complaint-data.json").exists())


if __name__ == "__main__":
    unittest.main()
