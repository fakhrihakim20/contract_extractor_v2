from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from contract_extractor.constants import MIN_TEXT_CHARS_FOR_NATIVE_PAGE
from contract_extractor.parser import clean_text


PageProgressCallback = Callable[[int, int, str], None]

DEFAULT_OCR_PROFILE = "ppocrv5_latin_onnx"
OCR_PROFILE_OPTIONS = ("ppocrv5_latin_onnx", "ppocrv5_english_onnx", "rapidocr_default")


@dataclass(frozen=True)
class OcrModelProfile:
    key: str
    label: str
    language_folder: str | None = None
    render_scale: float = 2.0
    preprocessing: str = "standard"


OCR_PROFILES = {
    "rapidocr_default": OcrModelProfile(
        key="rapidocr_default",
        label="RapidOCR default ONNX",
        render_scale=2.0,
        preprocessing="standard",
    ),
    "ppocrv5_latin_onnx": OcrModelProfile(
        key="ppocrv5_latin_onnx",
        label="PP-OCRv5 Latin ONNX",
        language_folder="latin",
        render_scale=2.5,
        preprocessing="table_boost",
    ),
    "ppocrv5_english_onnx": OcrModelProfile(
        key="ppocrv5_english_onnx",
        label="PP-OCRv5 English ONNX",
        language_folder="english",
        render_scale=2.35,
        preprocessing="table_boost",
    ),
}


@dataclass
class OcrToken:
    text: str
    box: list[list[float]]
    score: float | None
    page_number: int

    def to_preview(self) -> dict[str, object]:
        props = _box_properties(self.box) or {}
        return {
            "text": self.text,
            "score": self.score,
            "left": round(float(props.get("left", 0)), 2),
            "top": round(float(props.get("top", 0)), 2),
        }


@dataclass
class OcrPageResult:
    text: str
    tokens: list[OcrToken] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PageText:
    page_number: int
    text: str
    method: str
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float | None = None
    tokens: list[OcrToken] = field(default_factory=list)


@dataclass
class PdfTextExtraction:
    pages: list[PageText]
    warnings: list[str]

    def as_parser_pages(self) -> list[tuple[int, str]]:
        return [(page.page_number, page.text) for page in self.pages]

    def as_token_pages(self) -> list[tuple[int, list[OcrToken]]]:
        return [(page.page_number, page.tokens) for page in self.pages if page.tokens]

    def page_previews(self, limit_chars: int = 1400, limit_tokens: int = 80) -> list[dict[str, object]]:
        previews = []
        for page in self.pages:
            previews.append(
                {
                    "page_number": page.page_number,
                    "method": page.method,
                    "elapsed_seconds": round(page.elapsed_seconds or 0, 3),
                    "text_preview": page.text[:limit_chars],
                    "token_count": len(page.tokens),
                    "tokens": [token.to_preview() for token in page.tokens[:limit_tokens]],
                    "warnings": page.warnings,
                }
            )
        return previews


class RapidOcrEngine:
    """Small wrapper around RapidOCR's ONNXRuntime backend."""

    def __init__(
        self,
        backend: Any | None = None,
        model_root_dir: str | Path | None = None,
        profile: str = DEFAULT_OCR_PROFILE,
    ) -> None:
        self.profile = normalize_ocr_profile(profile)
        self.label = OCR_PROFILES[self.profile].label
        self.model_paths: dict[str, str] = {}
        self.warnings: list[str] = []
        if backend is None:
            try:
                from rapidocr import RapidOCR
            except Exception as exc:  # pragma: no cover - runtime dependency.
                raise RuntimeError(
                    "RapidOCR belum tersedia. Pastikan rapidocr dan onnxruntime terpasang."
                ) from exc
            model_dir = ensure_writable_rapidocr_model_dir(model_root_dir)
            params = build_rapidocr_params(self.profile, model_dir)
            self.model_paths = {
                key: value
                for key, value in params.items()
                if key.endswith("model_path") or key.endswith("rec_keys_path")
            }
            backend = RapidOCR(params=params)
        self._backend = backend

    def read_image(self, image_content: bytes) -> str:
        return self.read_image_result(image_content).text

    def read_image_result(self, image_content: bytes, page_number: int = 0) -> OcrPageResult:
        output = self._backend(image_content)
        tokens = _rapidocr_output_to_tokens(output, page_number)
        text = clean_text(_tokens_to_text(tokens))
        if not text:
            text = clean_text(_rapidocr_output_to_text(output))
        return OcrPageResult(text=text, tokens=tokens)


def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    ocr_engine: RapidOcrEngine,
    min_native_chars: int = MIN_TEXT_CHARS_FOR_NATIVE_PAGE,
    render_scale: float | None = None,
    preprocessing: str | None = None,
    on_page: PageProgressCallback | None = None,
) -> PdfTextExtraction:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - PyMuPDF is a runtime dependency.
        raise RuntimeError("PyMuPDF belum tersedia. Pastikan PyMuPDF terpasang.") from exc

    warnings: list[str] = []
    pages: list[PageText] = []
    render_scale = render_scale or OCR_PROFILES[ocr_engine.profile].render_scale
    preprocessing = preprocessing or OCR_PROFILES[ocr_engine.profile].preprocessing

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        total_pages = document.page_count
        for page_index, page in enumerate(document, start=1):
            native_text = clean_text(page.get_text("text"))
            if len(native_text) >= min_native_chars:
                pages.append(PageText(page_index, native_text, "native", elapsed_seconds=0.0))
                if on_page:
                    on_page(page_index, total_pages, "native")
                continue

            started = time.perf_counter()
            try:
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(render_scale, render_scale),
                    alpha=False,
                )
                image_bytes = pixmap.tobytes("png")
                image_bytes = preprocess_image(image_bytes, preprocessing)
                ocr_result = ocr_engine.read_image_result(image_bytes, page_index)
                ocr_text = ocr_result.text
                elapsed_seconds = time.perf_counter() - started
            except Exception as exc:
                elapsed_seconds = time.perf_counter() - started
                warning = f"RapidOCR gagal membaca halaman {page_index}: {exc}"
                warnings.append(warning)
                pages.append(
                    PageText(
                        page_index,
                        native_text,
                        "rapidocr-error",
                        [warning],
                        elapsed_seconds=elapsed_seconds,
                    )
                )
                if on_page:
                    on_page(page_index, total_pages, "rapidocr-error")
                continue

            if not ocr_text:
                warning = f"RapidOCR tidak membaca teks di halaman {page_index}."
                warnings.append(warning)
                pages.append(
                    PageText(
                        page_index,
                        native_text,
                        "rapidocr-empty",
                        [warning],
                        elapsed_seconds=elapsed_seconds,
                    )
                )
                if on_page:
                    on_page(page_index, total_pages, "rapidocr-empty")
                continue

            pages.append(
                PageText(
                    page_index,
                    ocr_text,
                    "rapidocr",
                    warnings=ocr_result.warnings,
                    elapsed_seconds=elapsed_seconds,
                    tokens=ocr_result.tokens,
                )
            )
            if on_page:
                on_page(page_index, total_pages, "rapidocr")

    if not pages:
        warnings.append("PDF tidak memiliki halaman yang bisa dibaca.")

    return PdfTextExtraction(pages=pages, warnings=warnings)


def normalize_ocr_profile(profile: str | None) -> str:
    value = (profile or DEFAULT_OCR_PROFILE).strip()
    if value not in OCR_PROFILES:
        return DEFAULT_OCR_PROFILE
    return value


def build_rapidocr_params(profile: str, model_root_dir: Path) -> dict[str, Any]:
    params: dict[str, Any] = {
        "Global.model_root_dir": str(model_root_dir),
        "Global.log_level": "warning",
        "Global.text_score": 0.35,
        "Det.engine_type": "onnxruntime",
        "Rec.engine_type": "onnxruntime",
        "Det.limit_side_len": 1280,
        "Det.limit_type": "max",
    }
    profile_config = OCR_PROFILES[normalize_ocr_profile(profile)]
    if not profile_config.language_folder:
        return params

    model_paths = download_ppocrv5_onnx_models(profile_config.language_folder, model_root_dir)
    params.update(
        {
            "Det.model_path": str(model_paths["det_model"]),
            "Rec.model_path": str(model_paths["rec_model"]),
            "Rec.rec_keys_path": str(model_paths["rec_keys"]),
            "Det.ocr_version": "PP-OCRv5",
            "Rec.ocr_version": "PP-OCRv5",
            "Det.lang_type": "multi",
            "Rec.lang_type": "en",
        }
    )
    return params


def download_ppocrv5_onnx_models(language_folder: str, cache_root: Path) -> dict[str, Path]:
    try:
        from huggingface_hub import hf_hub_download
    except Exception as exc:  # pragma: no cover - runtime dependency.
        raise RuntimeError(
            "huggingface_hub belum tersedia untuk mengunduh model PP-OCRv5 ONNX."
        ) from exc

    repo_id = "monkt/paddleocr-onnx"
    cache_dir = cache_root / "hf"
    det_model = Path(
        hf_hub_download(
            repo_id,
            "detection/v5/det.onnx",
            cache_dir=str(cache_dir),
        )
    )
    rec_model = Path(
        hf_hub_download(
            repo_id,
            f"languages/{language_folder}/rec.onnx",
            cache_dir=str(cache_dir),
        )
    )
    rec_keys = Path(
        hf_hub_download(
            repo_id,
            f"languages/{language_folder}/dict.txt",
            cache_dir=str(cache_dir),
        )
    )
    return {"det_model": det_model, "rec_model": rec_model, "rec_keys": rec_keys}


def preprocess_image(image_content: bytes, profile: str) -> bytes:
    if profile not in {"table_boost", "accurate"}:
        return image_content
    try:
        import cv2
        import numpy as np
    except Exception:
        return image_content

    data = np.frombuffer(image_content, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return image_content
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 7, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    boosted = clahe.apply(gray)
    sharpened = cv2.addWeighted(boosted, 1.35, cv2.GaussianBlur(boosted, (0, 0), 1.0), -0.35, 0)
    encoded_ok, buffer = cv2.imencode(".png", sharpened)
    return buffer.tobytes() if encoded_ok else image_content


def _rapidocr_output_to_text(output: Any) -> str:
    boxes = getattr(output, "boxes", None)
    txts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)

    if boxes is not None and txts is not None:
        return _lines_from_boxes(boxes, txts, scores)

    if isinstance(output, tuple) and len(output) >= 2:
        return _lines_from_legacy_items(output[0])
    if isinstance(output, list):
        return _lines_from_legacy_items(output)

    to_markdown = getattr(output, "to_markdown", None)
    if callable(to_markdown):
        return str(to_markdown() or "")

    return ""


def _rapidocr_output_to_tokens(output: Any, page_number: int) -> list[OcrToken]:
    boxes = getattr(output, "boxes", None)
    txts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)

    if boxes is not None and txts is not None:
        score_values = scores if scores is not None else [None] * len(txts)
        return [
            token
            for box, text, score in zip(boxes, txts, score_values)
            if (token := _make_token(box, text, score, page_number)) is not None
        ]

    if isinstance(output, tuple) and len(output) >= 1:
        return _legacy_items_to_tokens(output[0], page_number)
    if isinstance(output, list):
        return _legacy_items_to_tokens(output, page_number)
    return []


def _legacy_items_to_tokens(items: Any, page_number: int) -> list[OcrToken]:
    tokens: list[OcrToken] = []
    if not isinstance(items, list):
        return tokens
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        box = item[0]
        value = item[1]
        score = item[2] if len(item) > 2 and isinstance(item[2], (int, float)) else None
        text = value
        if isinstance(value, (list, tuple)) and value:
            text = value[0]
            if len(value) > 1 and isinstance(value[1], (int, float)):
                score = value[1]
        token = _make_token(box, text, score, page_number)
        if token:
            tokens.append(token)
    return tokens


def _make_token(box: Any, text: Any, score: Any, page_number: int) -> OcrToken | None:
    if not isinstance(text, str) or not text.strip():
        return None
    score_value = float(score) if isinstance(score, (int, float)) else None
    if score_value is not None and score_value < 0.25:
        return None
    normalized_box = _normalize_box(box)
    if normalized_box is None:
        return None
    return OcrToken(text=text.strip(), box=normalized_box, score=score_value, page_number=page_number)


def _normalize_box(box: Any) -> list[list[float]] | None:
    try:
        points = [tuple(point) for point in box]
        if len(points) < 4:
            return None
        return [[float(point[0]), float(point[1])] for point in points[:4]]
    except Exception:
        return None


def _tokens_to_text(tokens: list[OcrToken]) -> str:
    return _join_box_rows([(token.box, token.text, token.score) for token in tokens])


def _lines_from_legacy_items(items: Any) -> str:
    rows: list[tuple[Any, str, float | None]] = []
    if not isinstance(items, list):
        return ""
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        box = item[0]
        text = item[1]
        score = item[2] if len(item) > 2 and isinstance(item[2], (int, float)) else None
        if isinstance(text, str) and text.strip():
            rows.append((box, text, score))
    return _join_box_rows(rows)


def _lines_from_boxes(boxes: Any, txts: Any, scores: Any = None) -> str:
    rows: list[tuple[Any, str, float | None]] = []
    score_values = scores if scores is not None else [None] * len(txts)
    for box, text, score in zip(boxes, txts, score_values):
        if isinstance(text, str) and text.strip():
            rows.append((box, text, score if isinstance(score, (int, float)) else None))
    return _join_box_rows(rows)


def _join_box_rows(rows: list[tuple[Any, str, float | None]]) -> str:
    positioned = []
    for box, text, score in rows:
        if score is not None and score < 0.3:
            continue
        props = _box_properties(box)
        if props is None:
            continue
        positioned.append((props["center_y"], props["top"], props["left"], props["height"], text))

    if not positioned:
        return ""

    positioned.sort(key=lambda item: (item[0], item[2]))
    lines: list[list[tuple[float, str]]] = []
    line_centers: list[float] = []
    line_heights: list[float] = []

    for center_y, _top, left, height, text in positioned:
        if not lines:
            lines.append([(left, text)])
            line_centers.append(center_y)
            line_heights.append(height)
            continue

        threshold = max(8.0, min(line_heights[-1], height) * 0.65)
        if abs(center_y - line_centers[-1]) <= threshold:
            lines[-1].append((left, text))
            line_centers[-1] = (line_centers[-1] + center_y) / 2
            line_heights[-1] = max(line_heights[-1], height)
        else:
            lines.append([(left, text)])
            line_centers.append(center_y)
            line_heights.append(height)

    return "\n".join(" ".join(text for _left, text in sorted(line)) for line in lines)


def _box_properties(box: Any) -> dict[str, float] | None:
    try:
        points = [tuple(point) for point in box]
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except Exception:
        return None
    if not xs or not ys:
        return None

    top = min(ys)
    bottom = max(ys)
    return {
        "top": top,
        "left": min(xs),
        "height": max(1.0, bottom - top),
        "center_y": top + ((bottom - top) / 2),
    }


def ensure_writable_rapidocr_model_dir(model_root_dir: str | Path | None = None) -> Path:
    candidates = []
    if model_root_dir:
        candidates.append(Path(model_root_dir))

    env_root = os.environ.get("RAPIDOCR_MODEL_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    candidates.extend(
        [
            Path.home() / ".cache" / "contract_extractor_v2" / "rapidocr",
            Path(tempfile.gettempdir()) / "contract_extractor_v2" / "rapidocr",
        ]
    )

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue

    raise RuntimeError("Tidak ada folder cache writable untuk model RapidOCR.")
