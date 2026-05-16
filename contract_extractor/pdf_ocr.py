from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, Iterable

from contract_extractor.constants import MIN_TEXT_CHARS_FOR_NATIVE_PAGE
from contract_extractor.parser import clean_text


@dataclass
class PageText:
    page_number: int
    text: str
    method: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class PdfTextExtraction:
    pages: list[PageText]
    warnings: list[str]

    def as_parser_pages(self) -> list[tuple[int, str]]:
        return [(page.page_number, page.text) for page in self.pages]


class PaddleOcrEngine:
    def __init__(self, lang: str = "id") -> None:
        try:
            from paddleocr import PaddleOCR
        except Exception as exc:  # pragma: no cover - only exercised without PaddleOCR installed.
            raise RuntimeError(
                "PaddleOCR belum tersedia. Pastikan paddlepaddle dan paddleocr "
                "terpasang sesuai requirements.txt."
            ) from exc

        self.lang = lang
        try:
            self._ocr = PaddleOCR(
                lang=lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            # Compatibility fallback for PaddleOCR 2.x style constructors.
            self._ocr = PaddleOCR(lang=lang, use_angle_cls=True)

    def read_image(self, image_path: str | Path) -> str:
        path = str(image_path)
        if hasattr(self._ocr, "predict"):
            result = self._ocr.predict(path)
        else:
            result = self._ocr.ocr(path, cls=True)
        return "\n".join(_extract_texts_from_paddle_result(result))


def paddleocr_available() -> bool:
    return find_spec("paddleocr") is not None and find_spec("paddle") is not None


def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    ocr_factory: Callable[[], PaddleOcrEngine] | None = None,
    min_native_chars: int = MIN_TEXT_CHARS_FOR_NATIVE_PAGE,
) -> PdfTextExtraction:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - PyMuPDF is a runtime dependency.
        raise RuntimeError("PyMuPDF belum tersedia. Pastikan PyMuPDF terpasang.") from exc

    warnings: list[str] = []
    pages: list[PageText] = []
    ocr_engine: PaddleOcrEngine | None = None

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        with tempfile.TemporaryDirectory(prefix="contract-paddleocr-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            for page_index, page in enumerate(document, start=1):
                native_text = clean_text(page.get_text("text"))
                if len(native_text) >= min_native_chars:
                    pages.append(PageText(page_index, native_text, "native"))
                    continue

                if ocr_factory is None:
                    warning = f"Halaman {page_index} minim text layer dan OCR tidak tersedia."
                    warnings.append(warning)
                    pages.append(PageText(page_index, native_text, "native-empty", [warning]))
                    continue

                ocr_engine = ocr_engine or ocr_factory()
                image_path = tmp_path / f"page-{page_index}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(str(image_path))
                ocr_text = clean_text(ocr_engine.read_image(image_path))

                if not ocr_text:
                    warning = f"PaddleOCR tidak membaca teks di halaman {page_index}."
                    warnings.append(warning)
                    pages.append(PageText(page_index, native_text, "paddleocr-empty", [warning]))
                    continue

                pages.append(PageText(page_index, ocr_text, "paddleocr"))

    if not pages:
        warnings.append("PDF tidak memiliki halaman yang bisa dibaca.")

    return PdfTextExtraction(pages=pages, warnings=warnings)


def _extract_texts_from_paddle_result(result: object) -> list[str]:
    texts: list[str] = []

    def walk(node: object) -> None:
        if node is None:
            return

        for key in ("rec_texts", "texts", "text"):
            try:
                value = node[key]  # type: ignore[index]
            except Exception:
                value = None
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, Iterable) and not isinstance(value, (bytes, str, dict)):
                for item in value:
                    if item is not None:
                        texts.append(str(item))
                return

        if isinstance(node, dict):
            for key in ("rec_texts", "texts"):
                value = node.get(key)
                if isinstance(value, list):
                    texts.extend(str(item) for item in value if item is not None)
                    return
            for value in node.values():
                walk(value)
            return

        if isinstance(node, tuple) and len(node) == 2:
            second = node[1]
            if isinstance(second, (tuple, list)) and second and isinstance(second[0], str):
                texts.append(second[0])
                return

        if isinstance(node, list):
            if len(node) == 2 and isinstance(node[1], (tuple, list)) and node[1] and isinstance(node[1][0], str):
                texts.append(node[1][0])
                return
            for item in node:
                walk(item)

    walk(result)
    return [text.strip() for text in texts if str(text).strip()]
