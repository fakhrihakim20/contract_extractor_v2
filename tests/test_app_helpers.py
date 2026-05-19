from __future__ import annotations

import unittest

import pandas as pd

from app import (
    ProcessingStageError,
    backfill_drive_pdf_links,
    format_stage_error,
    is_infrastructure_failure,
    ocr_preflight_summary,
    select_all_drive_ids,
    select_processable_drive_ids,
    selected_drive_files,
    selected_ids_from_rows,
    shorten_error,
)
from contract_extractor.constants import MAX_PDF_BYTES
from contract_extractor.drive_client import DrivePdfFile
from contract_extractor.supabase_repo import document_pdf_link, drive_pdf_link


class AppHelperTests(unittest.TestCase):
    def test_selected_drive_files_only_returns_checked_processable_files(self) -> None:
        small = DrivePdfFile("small", "small.pdf", 10 * 1024 * 1024)
        large = DrivePdfFile("large", "large.pdf", MAX_PDF_BYTES + 1)
        unchecked = DrivePdfFile("unchecked", "unchecked.pdf", 10 * 1024 * 1024)
        edited = pd.DataFrame(
            [
                {"select": True, "drive_id": "small"},
                {"select": True, "drive_id": "large"},
                {"select": False, "drive_id": "unchecked"},
            ]
        )

        selected, skipped = selected_drive_files(edited, [small, large, unchecked])

        self.assertEqual(selected, [small])
        self.assertEqual(skipped, [large])

    def test_selected_drive_files_ignores_unknown_drive_ids(self) -> None:
        edited = pd.DataFrame([{"select": True, "drive_id": "missing"}])

        selected, skipped = selected_drive_files(edited, [])

        self.assertEqual(selected, [])
        self.assertEqual(skipped, [])

    def test_selected_ids_from_rows_returns_checked_ids(self) -> None:
        edited = pd.DataFrame(
            [
                {"select": True, "drive_id": "a"},
                {"select": False, "drive_id": "b"},
                {"select": True, "drive_id": "c"},
            ]
        )

        self.assertEqual(selected_ids_from_rows(edited), ["a", "c"])

    def test_select_all_drive_ids_returns_all_visible_files(self) -> None:
        files = [
            DrivePdfFile("a", "a.pdf", 1),
            DrivePdfFile("b", "b.pdf", MAX_PDF_BYTES + 1),
        ]

        self.assertEqual(select_all_drive_ids(files), ["a", "b"])

    def test_select_processable_drive_ids_excludes_large_files(self) -> None:
        files = [
            DrivePdfFile("a", "a.pdf", MAX_PDF_BYTES),
            DrivePdfFile("b", "b.pdf", MAX_PDF_BYTES + 1),
        ]

        self.assertEqual(select_processable_drive_ids(files), ["a"])

    def test_drive_pdf_link_prefers_google_web_view_link(self) -> None:
        link = drive_pdf_link("file-id", "https://drive.google.com/file/d/custom/view")

        self.assertEqual(link, "https://drive.google.com/file/d/custom/view")

    def test_drive_pdf_link_falls_back_to_file_id(self) -> None:
        link = drive_pdf_link("file-id")

        self.assertEqual(link, "https://drive.google.com/file/d/file-id/view")

    def test_document_pdf_link_falls_back_to_storage_path(self) -> None:
        link = document_pdf_link({"storage_path": "gdrive:file-id"})

        self.assertEqual(link, "https://drive.google.com/file/d/file-id/view")

    def test_backfill_drive_pdf_links_updates_existing_documents(self) -> None:
        repo = FakeRepo()
        file = DrivePdfFile(
            "file-id",
            "file.pdf",
            1234,
            web_view_link="https://drive.google.com/file/d/file-id/view",
        )
        document = {"id": "doc-id", "storage_path": "gdrive:file-id", "pdf_link": None}

        updated = backfill_drive_pdf_links(repo, [file], {"gdrive:file-id": document})

        self.assertEqual(updated, 1)
        self.assertEqual(document["pdf_link"], "https://drive.google.com/file/d/file-id/view")
        self.assertEqual(
            repo.updated,
            [("doc-id", "https://drive.google.com/file/d/file-id/view")],
        )

    def test_stage_error_marks_infrastructure_failures(self) -> None:
        ocr_error = ProcessingStageError("ocr", "onnx missing", infrastructure=True)
        parser_error = ProcessingStageError("parser", "cannot parse")

        self.assertTrue(is_infrastructure_failure(ocr_error))
        self.assertFalse(is_infrastructure_failure(parser_error))
        self.assertEqual(str(parser_error), "[parser] cannot parse")

    def test_ocr_preflight_summary_stops_batch_before_processing(self) -> None:
        calls = {"processed": 0}

        def fail_preflight() -> None:
            raise RuntimeError("onnx missing")

        summary = ocr_preflight_summary(fail_preflight)
        if summary is None:
            calls["processed"] += 1

        self.assertEqual(calls["processed"], 0)
        self.assertEqual(summary["imported"], [])
        self.assertEqual(summary["processed"], [])
        self.assertIn("[ocr] OCR runtime preflight gagal: onnx missing", summary["stopped"])

    def test_format_stage_error_does_not_duplicate_stage_prefix(self) -> None:
        self.assertEqual(format_stage_error("ocr", "[ocr] already wrapped"), "[ocr] already wrapped")

    def test_shorten_error_compacts_long_messages(self) -> None:
        message = "line one\n" + ("x" * 200)

        self.assertEqual(shorten_error(None), None)
        self.assertLessEqual(len(shorten_error(message, limit=40)), 40)


class FakeRepo:
    updated: list[tuple[str, str]]

    def __init__(self) -> None:
        self.updated = []

    @staticmethod
    def drive_storage_path(file_id: str) -> str:
        return f"gdrive:{file_id}"

    def update_document_pdf_link(self, document_id: str, pdf_link: str) -> None:
        self.updated.append((document_id, pdf_link))


if __name__ == "__main__":
    unittest.main()
