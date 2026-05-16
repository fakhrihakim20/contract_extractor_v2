from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import pandas as pd
import streamlit as st

from contract_extractor.constants import APP_NAME, DRIVE_STORAGE_BUCKET, LOCAL_MODEL_NAME, UNIT_OPTIONS
from contract_extractor.drive_client import DrivePdfFile, GoogleDriveClient
from contract_extractor.parser import parse_extraction_pages
from contract_extractor.pdf_ocr import PaddleOcrEngine, extract_pdf_text, paddleocr_available
from contract_extractor.supabase_repo import SupabaseRepository
from contract_extractor.ui_style import (
    empty_panel,
    inject_clean_ui,
    metric_strip,
    render_app_header,
    section_intro,
)


REQUIRED_SECRETS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GOOGLE_DRIVE_FOLDER_ID",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
]


def main() -> None:
    st.set_page_config(page_title=APP_NAME, layout="wide")
    inject_clean_ui()
    render_app_header()

    missing = missing_secrets()
    if missing:
        render_missing_config(missing)
        return

    repo = get_repo(secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_ROLE_KEY"))
    drive = get_drive_client(
        secret("GOOGLE_SERVICE_ACCOUNT_JSON"),
        secret("GOOGLE_DRIVE_FOLDER_ID"),
    )

    try:
        documents = repo.list_documents()
        contracts = repo.list_contracts()
    except Exception as exc:
        st.error(f"Gagal membaca Supabase: {exc}")
        return

    metric_strip(
        [
            ("Dokumen", str(len(documents))),
            ("Needs review", str(sum(1 for doc in documents if doc.get("status") == "needs_review"))),
            ("Approved", str(len(contracts))),
            ("OCR engine", "PaddleOCR ready" if paddleocr_available() else "Text-only runtime"),
        ]
    )

    intake_tab, review_tab, final_tab = st.tabs(["Drive Intake", "Review Draft", "Data Final"])
    with intake_tab:
        render_drive_intake(repo, drive, documents)
    with review_tab:
        render_review(repo, documents)
    with final_tab:
        render_final_data(contracts)


@st.cache_resource(show_spinner=False)
def get_repo(url: str, service_role_key: str) -> SupabaseRepository:
    return SupabaseRepository(url, service_role_key)


@st.cache_resource(show_spinner=False)
def get_drive_client(service_account_json: str, folder_id: str) -> GoogleDriveClient:
    return GoogleDriveClient.from_service_account_json(parse_service_account(service_account_json), folder_id)


@st.cache_resource(show_spinner="Memuat PaddleOCR model...")
def get_ocr_engine() -> PaddleOcrEngine:
    return PaddleOcrEngine(lang="id")


def render_drive_intake(
    repo: SupabaseRepository,
    drive: GoogleDriveClient,
    documents: list[dict[str, Any]],
) -> None:
    section_intro(
        "Drive Intake",
        "Read PDFs from the shared folder, import only the files you need, then process one document at a time so PaddleOCR stays predictable on Streamlit Cloud.",
        "manual sync",
    )
    if not paddleocr_available():
        st.warning(
            "PaddleOCR belum terpasang di runtime ini. PDF dengan text layer tetap bisa diproses; "
            "PDF scan akan butuh environment dengan requirements-ocr.txt."
        )

    col_a, col_b = st.columns([1, 1], vertical_alignment="bottom")
    with col_a:
        if st.button("Sync Google Drive", type="primary", use_container_width=True):
            with st.spinner("Membaca folder Google Drive..."):
                st.session_state["drive_files"] = [asdict(file) for file in drive.list_pdfs()]
    with col_b:
        st.caption(f"Model ekstraksi: `{LOCAL_MODEL_NAME}`")

    files = [DrivePdfFile(**item) for item in st.session_state.get("drive_files", [])]
    existing_by_path = {doc.get("storage_path"): doc for doc in documents}

    if files:
        rows = []
        for file in files:
            doc = existing_by_path.get(repo.drive_storage_path(file.id))
            rows.append(
                {
                    "name": file.name,
                    "size_mb": round(file.size / 1024 / 1024, 2),
                    "modified_time": file.modified_time,
                    "status": doc.get("status") if doc else "not_imported",
                    "drive_id": file.id,
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        selected = st.selectbox(
            "PDF Drive",
            files,
            format_func=lambda file: f"{file.name} ({file.size / 1024 / 1024:.2f} MB)",
        )
        action_a, action_b, action_c = st.columns(3)
        with action_a:
            if st.button("Import", use_container_width=True):
                try:
                    repo.import_drive_file(selected)
                    st.success("Dokumen berhasil diimport.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Import gagal: {exc}")
        with action_b:
            if st.button("Import + Process", type="primary", use_container_width=True):
                try:
                    document = repo.import_drive_file(selected)
                    process_document(repo, drive, document["id"], selected.id)
                    st.success("Draft ekstraksi siap direview.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Proses gagal: {exc}")
        with action_c:
            if selected.web_view_link:
                st.link_button("Buka PDF", selected.web_view_link, use_container_width=True)
    else:
        empty_panel(
            "Folder belum disync",
            "Klik Sync Google Drive untuk membaca daftar PDF dari folder service account.",
        )

    st.divider()
    section_intro(
        "Dokumen Drive",
        "Imported files are tracked through the old Supabase document tables with a Google Drive storage path.",
        "gdrive source",
    )
    drive_documents = [
        doc for doc in documents if doc.get("storage_bucket") == DRIVE_STORAGE_BUCKET
    ]
    if not drive_documents:
        empty_panel("Belum ada dokumen", "Import PDF dari daftar Drive untuk mulai membuat draft.")
        return

    st.dataframe(document_summary_frame(drive_documents), use_container_width=True, hide_index=True)
    selected_doc = st.selectbox(
        "Reprocess dokumen",
        drive_documents,
        format_func=format_document_label,
        key="intake_reprocess_doc",
    )
    if st.button("Reprocess selected", use_container_width=True):
        drive_file_id = repo.drive_id_from_storage_path(selected_doc.get("storage_path"))
        if not drive_file_id:
            st.error("Dokumen ini tidak memiliki Drive file id.")
            return
        try:
            process_document(repo, drive, selected_doc["id"], drive_file_id)
            st.success("Reprocess selesai. Draft terbaru siap direview.")
            st.rerun()
        except Exception as exc:
            st.error(f"Reprocess gagal: {exc}")


def render_review(repo: SupabaseRepository, documents: list[dict[str, Any]]) -> None:
    section_intro(
        "Review Draft",
        "Validate the extracted contract metadata and BoQ rows before sending the record to the final Supabase tables.",
        "human gate",
    )
    if not documents:
        empty_panel("Belum ada dokumen", "Import dokumen dari tab Drive Intake terlebih dahulu.")
        return

    selected_doc = st.selectbox(
        "Dokumen",
        documents,
        format_func=format_document_label,
        key="review_doc",
    )
    try:
        detail = repo.get_document_detail(selected_doc["id"])
    except Exception as exc:
        st.error(f"Gagal membuka detail dokumen: {exc}")
        return

    document = detail["document"]
    job = detail.get("job")
    draft = detail.get("draft") or {}
    items = detail.get("items") or []

    status_cols = st.columns(4)
    status_cols[0].metric("Status", document.get("status", "-"))
    status_cols[1].metric("File", document.get("original_filename", "-"))
    status_cols[2].metric("Job", (job or {}).get("status", "-"))
    status_cols[3].metric("Items", str(len(items)))

    if document.get("error_message"):
        st.error(document["error_message"])

    contract_payload = render_contract_form(draft)
    edited_items = render_items_editor(items)

    action_a, action_b = st.columns([1, 1])
    with action_a:
        if st.button("Simpan draft", type="primary", use_container_width=True):
            try:
                repo.save_review(document["id"], contract_payload, edited_items)
                st.success("Draft tersimpan.")
                st.rerun()
            except Exception as exc:
                st.error(f"Gagal menyimpan draft: {exc}")
    with action_b:
        if st.button("Approve final", use_container_width=True):
            try:
                repo.save_review(document["id"], contract_payload, edited_items)
                contract_id = repo.approve_document(document["id"])
                st.success(f"Kontrak masuk data final: {contract_id or 'approved'}.")
                st.rerun()
            except Exception as exc:
                st.error(f"Approval gagal: {exc}")


def render_contract_form(draft: dict[str, Any]) -> dict[str, Any]:
    with st.expander("Metadata kontrak", expanded=True):
        col1, col2, col3 = st.columns(3)
        contract_number = col1.text_input("Nomor Kontrak", value=draft.get("contract_number") or "")
        contract_year_text = col2.text_input("Tahun Kontrak", value=str(draft.get("contract_year") or ""))
        contract_date = col3.text_input("Tanggal Kontrak", value=draft.get("contract_date") or "")

        col4, col5, col6 = st.columns(3)
        vendor_name = col4.text_input("Nama Vendor", value=draft.get("vendor_name") or "")
        unit_options = ["", *UNIT_OPTIONS]
        current_unit = draft.get("unit_name") or ""
        unit_index = unit_options.index(current_unit) if current_unit in unit_options else 0
        unit_name = col5.selectbox("Nama Unit", unit_options, index=unit_index)
        unit_raw = col6.text_input("Unit Raw", value=draft.get("unit_raw") or "")

        review_notes = st.text_area("Review Notes", value=draft.get("review_notes") or "", height=80)

    return {
        "contract_number": contract_number,
        "contract_year": int(contract_year_text) if contract_year_text.strip().isdigit() else None,
        "contract_date": contract_date,
        "vendor_name": vendor_name,
        "unit_name": unit_name or None,
        "unit_raw": unit_raw,
        "fields_confidence": draft.get("fields_confidence") or {},
        "review_notes": review_notes,
    }


def render_items_editor(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section_intro(
        "Draft BoQ",
        "Edit rows directly in the grid. Add rows manually when OCR can only recover partial content.",
    )
    frame = pd.DataFrame(
        [
            {
                "item_id": item.get("item_id") or "",
                "description": item.get("description") or "",
                "unit": item.get("unit") or "",
                "material_unit_price": item.get("material_unit_price"),
                "service_unit_price": item.get("service_unit_price"),
                "source_page": item.get("source_page"),
                "source_text": item.get("source_text") or "",
                "confidence": item.get("confidence"),
                "warnings": ", ".join(item.get("warnings") or []),
            }
            for item in items
        ]
    )
    if frame.empty:
        frame = pd.DataFrame(
            columns=[
                "item_id",
                "description",
                "unit",
                "material_unit_price",
                "service_unit_price",
                "source_page",
                "source_text",
                "confidence",
                "warnings",
            ]
        )

    edited = st.data_editor(
        frame,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "item_id": st.column_config.TextColumn("ID", width="small"),
            "description": st.column_config.TextColumn("Uraian Pekerjaan", width="large"),
            "unit": st.column_config.TextColumn("Satuan", width="small"),
            "material_unit_price": st.column_config.NumberColumn("Harga Material", format="%.2f"),
            "service_unit_price": st.column_config.NumberColumn("Harga Jasa", format="%.2f"),
            "source_page": st.column_config.NumberColumn("Hal.", step=1),
            "source_text": st.column_config.TextColumn("Source Text", width="medium"),
            "confidence": st.column_config.NumberColumn("Conf.", min_value=0, max_value=1, format="%.3f"),
            "warnings": st.column_config.TextColumn("Warnings", width="medium"),
        },
    )

    rows = []
    for row in edited.to_dict("records"):
        if not str(row.get("item_id") or "").strip() and not str(row.get("description") or "").strip():
            continue
        warnings = row.get("warnings")
        rows.append(
            {
                "item_id": row.get("item_id"),
                "description": row.get("description"),
                "unit": row.get("unit"),
                "material_unit_price": row.get("material_unit_price"),
                "service_unit_price": row.get("service_unit_price"),
                "source_page": row.get("source_page"),
                "source_text": row.get("source_text"),
                "confidence": row.get("confidence"),
                "warnings": [part.strip() for part in str(warnings or "").split(",") if part.strip()],
            }
        )
    return rows


def render_final_data(contracts: list[dict[str, Any]]) -> None:
    section_intro(
        "Data Final",
        "Approved contracts and BoQ items copied by the existing approval RPC.",
        "approved",
    )
    if not contracts:
        empty_panel("Belum ada data final", "Kontrak yang diapprove dari tab Review Draft akan muncul di sini.")
        return

    summary_rows = []
    item_rows = []
    for contract in contracts:
        items = contract.get("boq_items") or []
        summary_rows.append(
            {
                "contract_number": contract.get("contract_number"),
                "vendor_name": contract.get("vendor_name"),
                "unit_name": contract.get("unit_name"),
                "contract_date": contract.get("contract_date"),
                "items": len(items),
                "approved_at": contract.get("approved_at"),
            }
        )
        for item in items:
            item_rows.append(
                {
                    "contract_number": contract.get("contract_number"),
                    "vendor_name": contract.get("vendor_name"),
                    "unit_name": contract.get("unit_name"),
                    **item,
                }
            )

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    selected = st.selectbox(
        "Kontrak",
        contracts,
        format_func=lambda contract: f"{contract.get('contract_number')} - {contract.get('vendor_name')}",
    )
    st.dataframe(pd.DataFrame(selected.get("boq_items") or []), use_container_width=True, hide_index=True)
    st.download_button(
        "Download CSV BoQ Final",
        pd.DataFrame(item_rows).to_csv(index=False).encode("utf-8"),
        file_name="contract_boq_final.csv",
        mime="text/csv",
        use_container_width=True,
    )


def process_document(
    repo: SupabaseRepository,
    drive: GoogleDriveClient,
    document_id: str,
    drive_file_id: str,
) -> None:
    repo.mark_processing(document_id)
    try:
        with st.spinner("Download PDF dari Google Drive..."):
            pdf_bytes = drive.download_pdf(drive_file_id)
        with st.spinner("Membaca PDF dan menjalankan PaddleOCR bila diperlukan..."):
            pdf_text = extract_pdf_text(pdf_bytes, ocr_factory=get_ocr_engine)
            result = parse_extraction_pages(
                pdf_text.as_parser_pages(),
                warnings=pdf_text.warnings,
            )
        repo.save_extraction_result(
            document_id,
            result,
            raw_context={
                "page_count": len(pdf_text.pages),
                "ocr_pages": [
                    page.page_number for page in pdf_text.pages if page.method == "paddleocr"
                ],
                "methods": [page.method for page in pdf_text.pages],
            },
        )
    except Exception as exc:
        repo.mark_failed(document_id, str(exc))
        raise


def document_summary_frame(documents: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for doc in documents:
        draft = embedded_first(doc.get("contract_extraction_drafts"))
        job = embedded_first(doc.get("extraction_jobs"))
        rows.append(
            {
                "filename": doc.get("original_filename"),
                "status": doc.get("status"),
                "job": (job or {}).get("status"),
                "contract_number": (draft or {}).get("contract_number"),
                "vendor": (draft or {}).get("vendor_name"),
                "unit": (draft or {}).get("unit_name") or (draft or {}).get("unit_raw"),
                "size_mb": round((doc.get("file_size_bytes") or 0) / 1024 / 1024, 2),
                "created_at": doc.get("created_at"),
            }
        )
    return pd.DataFrame(rows)


def format_document_label(document: dict[str, Any]) -> str:
    draft = embedded_first(document.get("contract_extraction_drafts"))
    contract_number = (draft or {}).get("contract_number")
    suffix = f" - {contract_number}" if contract_number else ""
    return f"{document.get('original_filename')} [{document.get('status')}]{suffix}"


def embedded_first(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        return value[0] if value else None
    if isinstance(value, dict):
        return value
    return None


def missing_secrets() -> list[str]:
    return [key for key in REQUIRED_SECRETS if not secret(key)]


def secret(key: str) -> str:
    try:
        value = st.secrets[key]
    except Exception:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(dict(value))


def parse_service_account(value: str) -> dict[str, Any]:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON harus berupa JSON service account.") from exc


def render_missing_config(missing: list[str]) -> None:
    st.error("Konfigurasi secrets Streamlit belum lengkap.")
    st.code(
        "\n".join(
            [
                'SUPABASE_URL = "https://cxretrzlhzsijiegyiwl.supabase.co"',
                'SUPABASE_SERVICE_ROLE_KEY = "..."',
                'GOOGLE_DRIVE_FOLDER_ID = "..."',
                'GOOGLE_SERVICE_ACCOUNT_JSON = """{...}"""',
            ]
        ),
        language="toml",
    )
    st.caption("Missing: " + ", ".join(missing))


if __name__ == "__main__":
    main()
