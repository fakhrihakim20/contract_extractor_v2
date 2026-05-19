from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from contract_extractor.pdf_ocr import (
    RapidOcrEngine,
    ensure_writable_rapidocr_model_dir,
    extract_pdf_text,
)


class FakeRapidOutput:
    def __init__(self, boxes=None, txts=None, scores=None) -> None:
        self.boxes = boxes
        self.txts = txts
        self.scores = scores


class FakeRapidBackend:
    def __init__(self, output=None, *, fail: bool = False) -> None:
        self.output = output or FakeRapidOutput()
        self.fail = fail
        self.calls = 0

    def __call__(self, image_content: bytes) -> FakeRapidOutput:
        self.calls += 1
        self.last_image_size = len(image_content)
        if self.fail:
            raise RuntimeError("ocr offline")
        return self.output


class FakeRapidOCRFactory:
    last_params = None

    def __init__(self, *, params=None) -> None:
        FakeRapidOCRFactory.last_params = params

    def __call__(self, image_content: bytes) -> FakeRapidOutput:
        return FakeRapidOutput()


class PdfOcrTests(unittest.TestCase):
    def test_native_text_page_does_not_call_rapidocr(self) -> None:
        backend = FakeRapidBackend()
        extraction = extract_pdf_text(_native_pdf(), ocr_engine=RapidOcrEngine(backend))

        self.assertEqual(backend.calls, 0)
        self.assertEqual(extraction.pages[0].method, "native")
        self.assertIn("Nomor Kontrak", extraction.pages[0].text)

    def test_scan_page_uses_rapidocr_and_orders_text_by_coordinates(self) -> None:
        output = FakeRapidOutput(
            boxes=[
                [[10, 50], [60, 50], [60, 70], [10, 70]],
                [[70, 10], [130, 10], [130, 30], [70, 30]],
                [[10, 10], [60, 10], [60, 30], [10, 30]],
            ],
            txts=("baris dua", "kanan", "kiri"),
            scores=(0.98, 0.96, 0.97),
        )
        backend = FakeRapidBackend(output)

        extraction = extract_pdf_text(_blank_scan_pdf(), ocr_engine=RapidOcrEngine(backend))

        self.assertEqual(backend.calls, 1)
        self.assertGreater(backend.last_image_size, 0)
        self.assertEqual(extraction.pages[0].method, "rapidocr")
        self.assertEqual(extraction.pages[0].text, "kiri kanan\nbaris dua")

    def test_scan_page_with_empty_ocr_adds_warning(self) -> None:
        backend = FakeRapidBackend(FakeRapidOutput(boxes=[], txts=(), scores=()))

        extraction = extract_pdf_text(_blank_scan_pdf(), ocr_engine=RapidOcrEngine(backend))

        self.assertEqual(extraction.pages[0].method, "rapidocr-empty")
        self.assertIn("RapidOCR tidak membaca teks", extraction.warnings[0])

    def test_scan_page_ocr_error_keeps_partial_draft_flow(self) -> None:
        backend = FakeRapidBackend(fail=True)

        extraction = extract_pdf_text(_blank_scan_pdf(), ocr_engine=RapidOcrEngine(backend))

        self.assertEqual(extraction.pages[0].method, "rapidocr-error")
        self.assertEqual(extraction.pages[0].text, "")
        self.assertIn("RapidOCR gagal membaca halaman 1", extraction.warnings[0])

    def test_rapidocr_model_dir_can_be_overridden_with_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / "rapidocr-cache"
            with patch.dict(os.environ, {"RAPIDOCR_MODEL_ROOT": str(model_dir)}):
                selected = ensure_writable_rapidocr_model_dir()

        self.assertEqual(selected, model_dir)

    def test_rapidocr_initializes_with_writable_model_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            FakeRapidOCRFactory.last_params = None
            fake_module = types.SimpleNamespace(RapidOCR=FakeRapidOCRFactory)
            with patch.dict(sys.modules, {"rapidocr": fake_module}):
                RapidOcrEngine(model_root_dir=temp_dir)

        self.assertEqual(
            FakeRapidOCRFactory.last_params["Global.model_root_dir"],
            temp_dir,
        )
        self.assertEqual(FakeRapidOCRFactory.last_params["Global.log_level"], "warning")


def _native_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Nomor Kontrak: 001/SPK/JBM/2026 Tanggal Kontrak: 16 Mei 2026 Vendor: PT Contoh Energi "
        "Unit: UPT Surabaya Uraian pekerjaan peremajaan sistem pengamanan petir.",
    )
    return document.tobytes()


def _blank_scan_pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=240, height=160)
    return document.tobytes()


if __name__ == "__main__":
    unittest.main()
