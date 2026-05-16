from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image

from contract_extractor.constants import MIN_TEXT_CHARS_FOR_NATIVE_PAGE
from contract_extractor.parser import clean_text


DOTS_OCR_PROMPT = "Extract the text content from this image."
DOTS_IMAGE_PREFIX = "<|img|><|imgpad|><|endofimg|>"


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


class DotsOcrEngine:
    """Client for a dots.ocr/dots.mocr vLLM OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str = "rednote-hilab/dots.mocr",
        api_key: str = "0",
        temperature: float = 0.1,
        top_p: float = 0.9,
        max_completion_tokens: int = 16384,
        timeout_seconds: int = 180,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        if not normalized_base_url.endswith("/v1"):
            normalized_base_url = f"{normalized_base_url}/v1"
        self.base_url = normalized_base_url
        self.model_name = model_name
        self.api_key = api_key or "0"
        self.temperature = temperature
        self.top_p = top_p
        self.max_completion_tokens = max_completion_tokens
        self.timeout_seconds = timeout_seconds

    def read_image(self, image_path: str | Path) -> str:
        image_url = _image_file_to_data_url(image_path)
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": f"{DOTS_IMAGE_PREFIX}{DOTS_OCR_PROMPT}"},
                    ],
                }
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_completion_tokens": self.max_completion_tokens,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return clean_text(data["choices"][0]["message"]["content"])


def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    ocr_engine: DotsOcrEngine,
    min_native_chars: int = MIN_TEXT_CHARS_FOR_NATIVE_PAGE,
) -> PdfTextExtraction:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - PyMuPDF is a runtime dependency.
        raise RuntimeError("PyMuPDF belum tersedia. Pastikan PyMuPDF terpasang.") from exc

    warnings: list[str] = []
    pages: list[PageText] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        with tempfile.TemporaryDirectory(prefix="contract-dots-ocr-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            for page_index, page in enumerate(document, start=1):
                native_text = clean_text(page.get_text("text"))
                if len(native_text) >= min_native_chars:
                    pages.append(PageText(page_index, native_text, "native"))
                    continue

                image_path = tmp_path / f"page-{page_index}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(str(image_path))
                ocr_text = clean_text(ocr_engine.read_image(image_path))

                if not ocr_text:
                    warning = f"dots.ocr tidak membaca teks di halaman {page_index}."
                    warnings.append(warning)
                    pages.append(PageText(page_index, native_text, "dots-ocr-empty", [warning]))
                    continue

                pages.append(PageText(page_index, ocr_text, "dots-ocr"))

    if not pages:
        warnings.append("PDF tidak memiliki halaman yang bisa dibaca.")

    return PdfTextExtraction(pages=pages, warnings=warnings)


def _image_file_to_data_url(image_path: str | Path) -> str:
    with Image.open(image_path) as image:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def extract_texts_from_layout_response(response: object) -> list[str]:
    texts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str) and node.strip():
            texts.append(node.strip())

    walk(response)
    return texts
