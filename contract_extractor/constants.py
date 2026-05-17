from __future__ import annotations

APP_NAME = "Contract Extractor v2"
DRIVE_STORAGE_BUCKET = "google-drive"
LOCAL_MODEL_NAME = "rapidocr-onnxruntime-v1"
MAX_PDF_BYTES = 50 * 1024 * 1024
MIN_TEXT_CHARS_FOR_NATIVE_PAGE = 80

UNIT_OPTIONS = [
    "UIT JBM",
    "UPT Probolinggo",
    "UPT Surabaya",
    "UPT Gresik",
    "UPT Malang",
    "UPT Madiun",
]

DOCUMENT_STATUSES = [
    "uploaded",
    "processing",
    "needs_review",
    "approved",
    "failed",
]
