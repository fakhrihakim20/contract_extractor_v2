from __future__ import annotations

import unittest

import pandas as pd

from app import (
    select_all_drive_ids,
    select_processable_drive_ids,
    selected_drive_files,
    selected_ids_from_rows,
)
from contract_extractor.constants import MAX_PDF_BYTES
from contract_extractor.drive_client import DrivePdfFile


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


if __name__ == "__main__":
    unittest.main()
