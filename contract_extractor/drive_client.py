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
    modified_time: str | None = None
    web_view_link: str | None = None
    md5_checksum: str | None = None


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

    def list_pdfs(self) -> list[DrivePdfFile]:
        query = (
            f"'{self._folder_id}' in parents and "
            "mimeType='application/pdf' and trashed=false"
        )
        files: list[DrivePdfFile] = []
        page_token: str | None = None

        while True:
            response = (
                self._service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields=(
                        "nextPageToken, files(id, name, size, modifiedTime, "
                        "webViewLink, md5Checksum)"
                    ),
                    orderBy="modifiedTime desc",
                    pageSize=100,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for item in response.get("files", []):
                files.append(
                    DrivePdfFile(
                        id=item["id"],
                        name=item["name"],
                        size=int(item.get("size") or 0),
                        modified_time=item.get("modifiedTime"),
                        web_view_link=item.get("webViewLink"),
                        md5_checksum=item.get("md5Checksum"),
                    )
                )
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return files

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
