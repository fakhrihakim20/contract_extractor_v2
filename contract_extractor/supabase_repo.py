from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from contract_extractor.constants import (
    DRIVE_STORAGE_BUCKET,
    LOCAL_MODEL_NAME,
    MAX_PDF_BYTES,
)
from contract_extractor.drive_client import DrivePdfFile
from contract_extractor.parser import BoqItem, ContractMetadata, ExtractionResult


class SupabaseRepository:
    def __init__(self, url: str, service_role_key: str) -> None:
        try:
            from supabase import create_client
        except Exception as exc:  # pragma: no cover - runtime dependency.
            raise RuntimeError(
                "Supabase Python client belum tersedia. Pastikan requirements.txt terpasang."
            ) from exc

        self._client = create_client(url, service_role_key)

    def list_documents(self) -> list[dict[str, Any]]:
        data = self._execute(
            self._client.table("documents")
            .select(
                """
                id,
                original_filename,
                storage_bucket,
                storage_path,
                status,
                file_size_bytes,
                error_message,
                created_at,
                updated_at,
                extraction_jobs(status, model, completed_at),
                contract_extraction_drafts(contract_number, vendor_name, unit_name, unit_raw)
                """
            )
            .order("created_at", desc=True)
        )
        return data or []

    def list_contracts(self) -> list[dict[str, Any]]:
        data = self._execute(
            self._client.table("contracts")
            .select(
                """
                id,
                document_id,
                contract_number,
                contract_year,
                contract_date,
                vendor_name,
                unit_name,
                approved_at,
                boq_items(
                    id,
                    item_id,
                    description,
                    unit,
                    material_unit_price,
                    service_unit_price,
                    source_page,
                    source_text,
                    confidence
                )
                """
            )
            .order("approved_at", desc=True)
        )
        return data or []

    def get_document_detail(self, document_id: str) -> dict[str, Any]:
        document = self._first(
            self._execute(
                self._client.table("documents").select("*").eq("id", document_id).limit(1)
            )
        )
        if not document:
            raise ValueError("Dokumen tidak ditemukan.")

        job = self._first(
            self._execute(
                self._client.table("extraction_jobs")
                .select("*")
                .eq("document_id", document_id)
                .order("created_at", desc=True)
                .limit(1)
            )
        )
        draft = self._first(
            self._execute(
                self._client.table("contract_extraction_drafts")
                .select("*")
                .eq("document_id", document_id)
                .limit(1)
            )
        )
        items = self._execute(
            self._client.table("boq_extraction_draft_items")
            .select("*")
            .eq("document_id", document_id)
            .order("sort_order")
        )
        return {"document": document, "job": job, "draft": draft, "items": items or []}

    def find_document_by_drive_id(self, file_id: str) -> dict[str, Any] | None:
        return self._first(
            self._execute(
                self._client.table("documents")
                .select("*")
                .eq("storage_path", self.drive_storage_path(file_id))
                .limit(1)
            )
        )

    def import_drive_file(self, file: DrivePdfFile) -> dict[str, Any]:
        if file.size <= 0:
            raise ValueError(f"{file.name} tidak memiliki ukuran file PDF yang valid.")
        if file.size > MAX_PDF_BYTES:
            raise ValueError(f"{file.name} lebih besar dari batas 50MB.")

        existing = self.find_document_by_drive_id(file.id)
        if existing:
            self.ensure_job(existing["id"], status="queued")
            return existing

        row = {
            "uploaded_by": None,
            "original_filename": file.name,
            "storage_bucket": DRIVE_STORAGE_BUCKET,
            "storage_path": self.drive_storage_path(file.id),
            "mime_type": "application/pdf",
            "file_size_bytes": file.size,
            "status": "uploaded",
            "error_message": None,
        }
        document = self._first(
            self._execute(self._client.table("documents").insert(row).execute())
        )
        if not document:
            raise RuntimeError("Gagal membuat dokumen di Supabase.")
        self.ensure_job(document["id"], status="queued")
        return document

    def ensure_job(self, document_id: str, *, status: str) -> None:
        self._execute(
            self._client.table("extraction_jobs")
            .upsert(
                {
                    "document_id": document_id,
                    "status": status,
                    "model": LOCAL_MODEL_NAME,
                    "error_message": None,
                },
                on_conflict="document_id",
            )
            .execute()
        )

    def mark_processing(self, document_id: str) -> None:
        self._execute(
            self._client.table("documents")
            .update({"status": "processing", "error_message": None})
            .eq("id", document_id)
            .execute()
        )
        self._execute(
            self._client.table("extraction_jobs")
            .upsert(
                {
                    "document_id": document_id,
                    "status": "processing",
                    "model": LOCAL_MODEL_NAME,
                    "error_message": None,
                    "started_at": _utc_now(),
                },
                on_conflict="document_id",
            )
            .execute()
        )

    def mark_failed(self, document_id: str, message: str) -> None:
        self._execute(
            self._client.table("documents")
            .update({"status": "failed", "error_message": message[:2000]})
            .eq("id", document_id)
            .execute()
        )
        self._execute(
            self._client.table("extraction_jobs")
            .upsert(
                {
                    "document_id": document_id,
                    "status": "failed",
                    "model": LOCAL_MODEL_NAME,
                    "error_message": message[:2000],
                    "completed_at": _utc_now(),
                },
                on_conflict="document_id",
            )
            .execute()
        )

    def save_extraction_result(
        self,
        document_id: str,
        result: ExtractionResult,
        *,
        raw_context: dict[str, Any] | None = None,
    ) -> None:
        draft = self.upsert_draft(document_id, result.contract)
        self.replace_draft_items(document_id, draft["id"], result.boq_items)
        raw_output = result.to_raw_output()
        if raw_context:
            raw_output["context"] = raw_context

        self._execute(
            self._client.table("extraction_jobs")
            .update(
                {
                    "status": "succeeded",
                    "model": LOCAL_MODEL_NAME,
                    "raw_output": raw_output,
                    "confidence_summary": result.confidence_summary,
                    "error_message": None,
                    "completed_at": _utc_now(),
                }
            )
            .eq("document_id", document_id)
            .execute()
        )
        self._execute(
            self._client.table("documents")
            .update({"status": "needs_review", "error_message": None})
            .eq("id", document_id)
            .execute()
        )

    def upsert_draft(self, document_id: str, contract: ContractMetadata | dict[str, Any]) -> dict[str, Any]:
        payload = contract.to_supabase() if isinstance(contract, ContractMetadata) else contract
        row = {
            "document_id": document_id,
            "contract_number": _blank_to_none(payload.get("contract_number")),
            "contract_year": _clean_number(payload.get("contract_year"), as_int=True),
            "contract_date": _blank_to_none(payload.get("contract_date")),
            "vendor_name": _blank_to_none(payload.get("vendor_name")),
            "unit_name": _blank_to_none(payload.get("unit_name")),
            "unit_raw": _blank_to_none(payload.get("unit_raw")),
            "fields_confidence": payload.get("fields_confidence") or {},
            "review_notes": _blank_to_none(payload.get("review_notes")),
        }
        draft = self._first(
            self._execute(
                self._client.table("contract_extraction_drafts")
                .upsert(row, on_conflict="document_id")
                .select("*")
                .execute()
            )
        )
        if not draft:
            raise RuntimeError("Gagal menyimpan draft kontrak.")
        return draft

    def replace_draft_items(
        self,
        document_id: str,
        draft_id: str,
        items: list[BoqItem] | list[dict[str, Any]],
    ) -> None:
        self._execute(
            self._client.table("boq_extraction_draft_items")
            .delete()
            .eq("document_id", document_id)
            .execute()
        )
        rows = []
        for index, item in enumerate(items, start=1):
            payload = item.to_supabase() if isinstance(item, BoqItem) else item
            item_id = _blank_to_none(payload.get("item_id"))
            description = _blank_to_none(payload.get("description"))
            unit = _blank_to_none(payload.get("unit"))
            if not item_id and not description:
                continue
            rows.append(
                {
                    "document_id": document_id,
                    "draft_id": draft_id,
                    "sort_order": index,
                    "item_id": item_id or str(index),
                    "description": description or "Uraian belum diisi",
                    "unit": unit or "-",
                    "material_unit_price": _clean_number(payload.get("material_unit_price")),
                    "service_unit_price": _clean_number(payload.get("service_unit_price")),
                    "source_page": _clean_number(payload.get("source_page"), as_int=True),
                    "source_text": _blank_to_none(payload.get("source_text")),
                    "confidence": _clean_number(payload.get("confidence")),
                    "warnings": payload.get("warnings") or [],
                }
            )

        if rows:
            self._execute(self._client.table("boq_extraction_draft_items").insert(rows).execute())

    def save_review(
        self,
        document_id: str,
        contract: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> None:
        draft = self.upsert_draft(document_id, contract)
        self.replace_draft_items(document_id, draft["id"], items)
        self._execute(
            self._client.table("documents")
            .update({"status": "needs_review", "error_message": None})
            .eq("id", document_id)
            .execute()
        )

    def approve_document(self, document_id: str, approved_by: str | None = None) -> str | None:
        data = self._execute(
            self._client.rpc(
                "approve_contract_document",
                {"p_document_id": document_id, "p_approved_by": approved_by},
            ).execute()
        )
        return data

    @staticmethod
    def drive_storage_path(file_id: str) -> str:
        return f"gdrive:{file_id}"

    @staticmethod
    def drive_id_from_storage_path(storage_path: str | None) -> str | None:
        if storage_path and storage_path.startswith("gdrive:"):
            return storage_path.removeprefix("gdrive:")
        return None

    @staticmethod
    def _first(data: Any) -> dict[str, Any] | None:
        if isinstance(data, list):
            return data[0] if data else None
        if isinstance(data, dict):
            return data
        return None

    def _execute(self, query_or_response: Any) -> Any:
        if hasattr(query_or_response, "data"):
            return query_or_response.data
        response = query_or_response.execute()
        return getattr(response, "data", None)


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if _is_nan(value):
        return None
    return value


def _clean_number(value: Any, *, as_int: bool = False) -> int | float | None:
    if value is None or value == "" or _is_nan(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if as_int else parsed


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
