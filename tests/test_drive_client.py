from __future__ import annotations

import re
import unittest
from typing import Any

from contract_extractor.drive_client import GoogleDriveClient


class FakeRequest:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def execute(self) -> dict[str, Any]:
        return self.payload


class FakeFilesResource:
    def __init__(self, files_by_id: dict[str, dict[str, Any]]) -> None:
        self.files_by_id = files_by_id

    def list(self, **kwargs: Any) -> FakeRequest:
        query = kwargs.get("q", "")
        parent_match = re.search(r"'([^']+)'\s+in\s+parents", query)
        parent_id = parent_match.group(1) if parent_match else ""
        children = [
            item
            for item in self.files_by_id.values()
            if parent_id in item.get("parents", []) and not item.get("trashed", False)
        ]
        return FakeRequest({"files": children})

    def get(self, **kwargs: Any) -> FakeRequest:
        return FakeRequest(self.files_by_id[kwargs["fileId"]])


class FakeDriveService:
    def __init__(self, files_by_id: dict[str, dict[str, Any]]) -> None:
        self.files_by_id = files_by_id

    def files(self) -> FakeFilesResource:
        return FakeFilesResource(self.files_by_id)


class DriveClientTests(unittest.TestCase):
    def test_lists_direct_pdf(self) -> None:
        client = GoogleDriveClient(FakeDriveService(_files("root", [_pdf("pdf-1", "A.pdf", "root")])), "root")

        result = client.sync_pdfs()

        self.assertEqual(result.visited_folders, 1)
        self.assertEqual(result.followed_shortcuts, 0)
        self.assertEqual([file.name for file in result.files], ["A.pdf"])

    def test_lists_nested_pdf_with_folder_path(self) -> None:
        files = _files(
            "root",
            [
                _folder("upt", "UPT SURABAYA", "root"),
                _folder("year", "2025", "upt"),
                _pdf("pdf-1", "Kontrak.pdf", "year"),
            ],
        )
        client = GoogleDriveClient(FakeDriveService(files), "root")

        result = client.sync_pdfs()

        self.assertEqual(result.visited_folders, 3)
        self.assertEqual(result.files[0].folder_path, "UPT SURABAYA / 2025")

    def test_follows_shortcut_to_folder(self) -> None:
        files = _files(
            "root",
            [
                _shortcut("shortcut-folder", "FILE KONTRAK UPT", "root", "target", "application/vnd.google-apps.folder"),
                _folder("target", "Target Folder", ""),
                _pdf("pdf-1", "Kontrak.pdf", "target"),
            ],
        )
        client = GoogleDriveClient(FakeDriveService(files), "root")

        result = client.sync_pdfs()

        self.assertEqual(result.followed_shortcuts, 1)
        self.assertEqual(result.files[0].folder_path, "FILE KONTRAK UPT")

    def test_follows_shortcut_to_pdf(self) -> None:
        files = _files(
            "root",
            [
                _shortcut("shortcut-pdf", "Shortcut Kontrak.pdf", "root", "pdf-target", "application/pdf"),
                _pdf("pdf-target", "Target Kontrak.pdf", ""),
            ],
        )
        client = GoogleDriveClient(FakeDriveService(files), "root")

        result = client.sync_pdfs()

        self.assertEqual(result.followed_shortcuts, 1)
        self.assertEqual(result.files[0].id, "pdf-target")
        self.assertEqual(result.files[0].name, "Target Kontrak.pdf")

    def test_shortcut_loop_does_not_revisit_folder_forever(self) -> None:
        files = _files(
            "root",
            [
                _shortcut("loop", "Loop", "root", "root", "application/vnd.google-apps.folder"),
                _pdf("pdf-1", "A.pdf", "root"),
            ],
        )
        client = GoogleDriveClient(FakeDriveService(files), "root")

        result = client.sync_pdfs(max_depth=6)

        self.assertEqual(result.visited_folders, 1)
        self.assertEqual([file.name for file in result.files], ["A.pdf"])


def _files(root_id: str, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    root = _folder(root_id, "Root", "")
    return {item["id"]: item for item in [root, *items]}


def _folder(file_id: str, name: str, parent_id: str) -> dict[str, Any]:
    return {
        "id": file_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id] if parent_id else [],
    }


def _pdf(file_id: str, name: str, parent_id: str) -> dict[str, Any]:
    return {
        "id": file_id,
        "name": name,
        "mimeType": "application/pdf",
        "parents": [parent_id] if parent_id else [],
        "size": "1234",
        "modifiedTime": "2026-05-19T00:00:00Z",
        "webViewLink": f"https://drive.google.com/file/d/{file_id}",
        "md5Checksum": f"md5-{file_id}",
    }


def _shortcut(
    file_id: str,
    name: str,
    parent_id: str,
    target_id: str,
    target_mime_type: str,
) -> dict[str, Any]:
    return {
        "id": file_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.shortcut",
        "parents": [parent_id],
        "shortcutDetails": {
            "targetId": target_id,
            "targetMimeType": target_mime_type,
        },
    }


if __name__ == "__main__":
    unittest.main()
