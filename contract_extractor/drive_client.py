from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any


DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


@dataclass(frozen=True)
class DrivePdfFile:
    id: str
    name: str
    size: int
    folder_path: str = ""
    modified_time: str | None = None
    web_view_link: str | None = None
    md5_checksum: str | None = None


@dataclass(frozen=True)
class DriveSyncResult:
    files: list[DrivePdfFile]
    visited_folders: int
    followed_shortcuts: int


class GoogleDriveClient:
    def __init__(self, service: Any, folder_id: str) -> None:
        self._service = service
        self._folder_id = folder_id

    @classmethod
    def from_service_account_json(
        cls,
        service_account_json: str | dict[str, Any],
        folder_id: str,
    ) -> "GoogleDriveClient":
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except Exception as exc:  # pragma: no cover - import is checked at runtime.
            raise RuntimeError(
                "Google API client belum tersedia. Pastikan requirements.txt terpasang."
            ) from exc

        payload = (
            json.loads(service_account_json)
            if isinstance(service_account_json, str)
            else service_account_json
        )
        credentials = service_account.Credentials.from_service_account_info(
            payload,
            scopes=[DRIVE_READONLY_SCOPE],
        )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return cls(service, folder_id)

    def sync_pdfs(self, *, max_depth: int = 6) -> DriveSyncResult:
        files: list[DrivePdfFile] = []
        visited: set[str] = set()
        followed_shortcuts = 0
        queue: list[tuple[str, str, int]] = [(self._folder_id, "", 0)]

        while queue:
            folder_id, folder_path, depth = queue.pop(0)
            if folder_id in visited or depth > max_depth:
                continue
            visited.add(folder_id)

            for item in self._list_children(folder_id):
                mime_type = item.get("mimeType")
                name = item.get("name") or "Untitled"

                if mime_type == "application/pdf":
                    files.append(self._to_drive_pdf_file(item, folder_path))
                    continue

                if mime_type == "application/vnd.google-apps.folder":
                    queue.append((item["id"], _join_drive_path(folder_path, name), depth + 1))
                    continue

                if mime_type == "application/vnd.google-apps.shortcut":
                    shortcut = item.get("shortcutDetails") or {}
                    target_id = shortcut.get("targetId")
                    target_mime = shortcut.get("targetMimeType")
                    if not target_id or not target_mime:
                        continue
                    followed_shortcuts += 1

                    if target_mime == "application/vnd.google-apps.folder":
                        queue.append((target_id, _join_drive_path(folder_path, name), depth + 1))
                    elif target_mime == "application/pdf":
                        target = self._get_file(target_id)
                        target["name"] = target.get("name") or name
                        files.append(self._to_drive_pdf_file(target, folder_path))

        files.sort(key=lambda file: (file.folder_path.lower(), file.name.lower()))
        return DriveSyncResult(
            files=files,
            visited_folders=len(visited),
            followed_shortcuts=followed_shortcuts,
        )

    def list_pdfs(self) -> list[DrivePdfFile]:
        return self.sync_pdfs().files

    def _list_children(self, folder_id: str) -> list[dict[str, Any]]:
        query = f"'{folder_id}' in parents and trashed=false"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = (
                self._service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields=(
                        "nextPageToken, files(id, name, size, modifiedTime, "
                        "webViewLink, md5Checksum, mimeType, "
                        "shortcutDetails(targetId, targetMimeType))"
                    ),
                    orderBy="folder,name_natural",
                    pageSize=100,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            items.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def _get_file(self, file_id: str) -> dict[str, Any]:
        return (
            self._service.files()
            .get(
                fileId=file_id,
                fields="id, name, size, modifiedTime, webViewLink, md5Checksum, mimeType",
                supportsAllDrives=True,
            )
            .execute()
        )

    @staticmethod
    def _to_drive_pdf_file(item: dict[str, Any], folder_path: str) -> DrivePdfFile:
        return DrivePdfFile(
            id=item["id"],
            name=item["name"],
            size=int(item.get("size") or 0),
            folder_path=folder_path,
            modified_time=item.get("modifiedTime"),
            web_view_link=item.get("webViewLink"),
            md5_checksum=item.get("md5Checksum"),
        )

    def download_pdf(self, file_id: str) -> bytes:
        try:
            from googleapiclient.http import MediaIoBaseDownload
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Google API download helper belum tersedia. Pastikan requirements.txt terpasang."
            ) from exc

        request = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()


def _join_drive_path(parent: str, child: str) -> str:
    return f"{parent} / {child}" if parent else child
