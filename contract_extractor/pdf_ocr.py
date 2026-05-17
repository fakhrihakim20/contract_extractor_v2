from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from contract_extractor.constants import MIN_TEXT_CHARS_FOR_NATIVE_PAGE
from contract_extractor.parser import clean_text


PageProgressCallback = Callable[[int, int, str], None]


@dataclass
class PageText:
    page_number: int
    text: str
    method: str
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float | None = None


@dataclass
class PdfTextExtraction:
    pages: list[PageText]
    warnings: list[str]

    def as_parser_pages(self) -> list[tuple[int, str]]:
        return [(page.page_number, page.text) for page in self.pages]


class RapidOcrEngine:
    """Small wrapper around RapidOCR's ONNXRuntime backend."""

    def __init__(self, backend: Any | None = None) -> None:
        if backend is None:
            try:
                from rapidocr import RapidOCR
            except Exception as exc:  # pragma: no cover - runtime dependency.
                raise RuntimeError(
                    "RapidOCR belum tersedia. Pastikan rapidocr dan onnxruntime terpasang."
                ) from exc
            backend = RapidOCR()
        self._backend = backend

    def read_image(self, image_content: bytes) -> str:
        output = self._backend(image_content)
        return clean_text(_rapidocr_output_to_text(output))


def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    ocr_engine: RapidOcrEngine,
    min_native_chars: int = MIN_TEXT_CHARS_FOR_NATIVE_PAGE,
    render_scale: float = 2.0,
    on_page: PageProgressCallback | None = None,
) -> PdfTextExtraction:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - PyMuPDF is a runtime dependency.
        raise RuntimeError("PyMuPDF belum tersedia. Pastikan PyMuPDF terpasang.") from exc

    warnings: list[str] = []
    pages: list[PageText] = []

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
                ocr_text = ocr_engine.read_image(image_bytes)
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
                PageText(page_index, ocr_text, "rapidocr", elapsed_seconds=elapsed_seconds)
            )
            if on_page:
                on_page(page_index, total_pages, "rapidocr")

    if not pages:
        warnings.append("PDF tidak memiliki halaman yang bisa dibaca.")

    return PdfTextExtraction(pages=pages, warnings=warnings)


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
