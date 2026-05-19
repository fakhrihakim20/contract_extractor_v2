from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Iterable

from contract_extractor.constants import UNIT_OPTIONS


MONTHS_ID = {
    "januari": 1,
    "jan": 1,
    "februari": 2,
    "feb": 2,
    "maret": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "mei": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "agustus": 8,
    "agu": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "oktober": 10,
    "0ktober": 10,
    "okdober": 10,
    "0kdober": 10,
    "okt": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "desember": 12,
    "des": 12,
    "dec": 12,
}

BOQ_UNIT_WORDS = {
    "bh",
    "buah",
    "ea",
    "hari",
    "jam",
    "kg",
    "km",
    "ls",
    "lot",
    "m",
    "m1",
    "m2",
    "m3",
    "meter",
    "oh",
    "org",
    "paket",
    "panel",
    "pcs",
    "set",
    "titik",
    "tower",
    "unit",
    "meler",
    "mtr",
    "bulan",
    "buan",
    "bln",
    "lembar",
    "orang",
    "tks",
    "tk",
}

BOQ_UNIT_ALIASES = {
    "bh": "bh",
    "buah": "bh",
    "ea": "ea",
    "ls": "ls",
    "s": "ls",
    "lot": "lot",
    "meter": "meter",
    "meler": "meter",
    "mtr": "meter",
    "m": "m",
    "titik": "titik",
    "tower": "tower",
    "unit": "unit",
    "set": "set",
    "bulan": "bulan",
    "buan": "bulan",
    "bln": "bulan",
    "lembar": "lembar",
    "orang": "orang",
    "tks": "tks",
    "tk": "tks",
}


@dataclass
class ContractMetadata:
    contract_number: str | None = None
    contract_year: int | None = None
    contract_date: str | None = None
    vendor_name: str | None = None
    unit_name: str | None = None
    unit_raw: str | None = None
    fields_confidence: dict[str, float | None] = field(default_factory=dict)
    review_notes: str | None = None

    def to_supabase(self) -> dict[str, object]:
        return {
            "contract_number": self.contract_number,
            "contract_year": self.contract_year,
            "contract_date": self.contract_date,
            "vendor_name": self.vendor_name,
            "unit_name": self.unit_name,
            "unit_raw": self.unit_raw,
            "fields_confidence": self.fields_confidence,
            "review_notes": self.review_notes,
        }


@dataclass
class BoqItem:
    item_id: str
    description: str
    unit: str
    material_unit_price: float | None = None
    service_unit_price: float | None = None
    source_page: int | None = None
    source_text: str | None = None
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_supabase(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ExtractionResult:
    contract: ContractMetadata
    boq_items: list[BoqItem]
    confidence_summary: dict[str, object]
    warnings: list[str] = field(default_factory=list)

    def to_raw_output(self) -> dict[str, object]:
        return {
            "contract": self.contract.to_supabase(),
            "boq_items": [item.to_supabase() for item in self.boq_items],
            "confidence_summary": self.confidence_summary,
            "warnings": self.warnings,
        }


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\u00a0", " ")
    value = value.translate(
        str.maketrans(
            {
                "：": ":",
                "，": ",",
                "（": "(",
                "）": ")",
                "“": '"',
                "”": '"',
                "’": "'",
                "–": "-",
                "—": "-",
            }
        )
    )
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_indonesian_currency(value: str | int | float | None) -> float | None:
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if parsed >= 0 else None
    if not value:
        return None

    cleaned = str(value).lower()
    cleaned = re.sub(r"\brp\.?", "", cleaned)
    cleaned = cleaned.replace(",-", "")
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[^\d,.-]", "", cleaned)
    cleaned = cleaned.strip(".,-")
    if not cleaned:
        return None

    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")
    decimal_pos = max(last_comma, last_dot)
    has_decimal = decimal_pos != -1 and decimal_pos > len(cleaned) - 4

    if has_decimal and last_comma > last_dot:
        normalized = cleaned.replace(".", "").replace(",", ".")
    elif has_decimal and last_dot > last_comma and "," in cleaned:
        normalized = cleaned.replace(",", "")
    else:
        normalized = re.sub(r"[,.]", "", cleaned)

    try:
        parsed = float(normalized)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def format_date_iso(value: str | None) -> str | None:
    if not value:
        return None
    text = clean_text(value).lower()
    text = re.sub(r"(?<=\d)o(?=ktober|kdober)", "0", text)

    iso_match = re.search(r"\b(20\d{2}|19\d{2})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        return _safe_date(
            int(iso_match.group(1)),
            int(iso_match.group(2)),
            int(iso_match.group(3)),
        )

    numeric_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})\b", text)
    if numeric_match:
        return _safe_date(
            int(numeric_match.group(3)),
            int(numeric_match.group(2)),
            int(numeric_match.group(1)),
        )

    month_pattern = "|".join(sorted(MONTHS_ID, key=len, reverse=True))
    named_match = re.search(
        rf"\b(\d{{1,2}})\s*({month_pattern})\s*((?:19|20)\d{{2}})\b",
        text,
    )
    if named_match:
        return _safe_date(
            int(named_match.group(3)),
            MONTHS_ID[named_match.group(2)],
            int(named_match.group(1)),
        )

    return None


def normalize_unit_name(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    compact = re.sub(r"\s+", " ", value.strip())
    lowered = compact.lower()
    for unit in UNIT_OPTIONS:
        if lowered == unit.lower():
            return unit, unit
        if unit.lower() in lowered:
            return unit, compact
    compact_key = re.sub(r"[^a-z0-9]", "", lowered)
    unit_hints = {
        "unitpelaksanatransmisisurabaya": "UPT Surabaya",
        "uptsurabaya": "UPT Surabaya",
        "transmisisurabaya": "UPT Surabaya",
        "unitpelaksanatransmisigresik": "UPT Gresik",
        "uptgresik": "UPT Gresik",
        "transmisigresik": "UPT Gresik",
        "unitpelaksanatransmisimalang": "UPT Malang",
        "uptmalang": "UPT Malang",
        "transmisimalang": "UPT Malang",
        "unitpelaksanatransmisimadiun": "UPT Madiun",
        "uptmadiun": "UPT Madiun",
        "transmisimadiun": "UPT Madiun",
        "unitpelaksanatransmisiprobolinggo": "UPT Probolinggo",
        "uptprobolinggo": "UPT Probolinggo",
        "transmisiprobolinggo": "UPT Probolinggo",
    }
    for token, unit in unit_hints.items():
        if token in compact_key:
            return unit, compact
    return None, compact


def parse_contract_metadata(text: str) -> ContractMetadata:
    normalized = clean_text(text)
    contract_number = _find_contract_number(normalized)

    date_value = _find_first(
        normalized,
        [
            r"(?:tanggal(?:\s+kontrak|\s+perjanjian)?|tgl\.?)\s*[:\-]?\s*([^\n]{4,40})",
            r"\b(\d{1,2}\s*(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|0ktober|okdober|0kdober|november|desember)\s*(?:19|20)\d{2})\b",
            r"\b(\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2})\b",
        ],
    )
    contract_date = format_date_iso(date_value)

    year = None
    if contract_date:
        year = int(contract_date[:4])
    else:
        year_value = _find_first(normalized, [r"(?:tahun|ta\.?)\s*[:\-]?\s*((?:19|20)\d{2})"])
        if year_value:
            year = int(year_value)

    vendor_name = _find_vendor_name(normalized)

    unit_raw = _find_unit_text(normalized)
    unit_name, normalized_unit_raw = normalize_unit_name(unit_raw)

    fields_confidence = {
        "contract_number": 0.85 if contract_number else None,
        "contract_year": 0.8 if year else None,
        "contract_date": 0.8 if contract_date else None,
        "vendor_name": 0.7 if vendor_name else None,
        "unit_name": 0.9 if unit_name else None,
    }

    return ContractMetadata(
        contract_number=contract_number,
        contract_year=year,
        contract_date=contract_date,
        vendor_name=vendor_name,
        unit_name=unit_name,
        unit_raw=normalized_unit_raw,
        fields_confidence=fields_confidence,
    )


def parse_boq_items(text: str, source_page: int | None = None) -> list[BoqItem]:
    raw_lines = [_normalize_boq_line(line) for line in clean_text(text).splitlines()]
    has_boq_context = _has_boq_context(raw_lines)
    lines = [line for line in raw_lines if line and not _is_header_line(line)]
    items: list[BoqItem] = []
    pending: str | None = None
    section: str | None = None

    for line in lines:
        section = _update_boq_section(line, section)
        if has_boq_context:
            table_item = _parse_boq_table_line(line, source_page, section)
            if table_item:
                items.append(table_item)
                pending = None
                continue

        starts_item = bool(_item_id_match(line))
        candidate = line if pending is None else f"{pending} {line}"
        parsed = _parse_boq_line(candidate, source_page)
        if parsed:
            items.append(parsed)
            pending = None
            continue

        if starts_item and has_boq_context:
            pending = line
        elif pending and has_boq_context:
            pending = candidate

    if pending and has_boq_context:
        fallback = _parse_partial_boq_line(pending, source_page)
        if fallback:
            items.append(fallback)

    return _dedupe_items(items)


def parse_extraction_pages(
    pages: Iterable[tuple[int, str]],
    warnings: list[str] | None = None,
    token_pages: Iterable[tuple[int, list[Any]]] | None = None,
) -> ExtractionResult:
    page_list = [(page, clean_text(text)) for page, text in pages]
    full_text = "\n\n".join(text for _, text in page_list)
    contract = parse_contract_metadata(full_text)

    items: list[BoqItem] = []
    for page_number, tokens in token_pages or []:
        items.extend(parse_boq_items_from_tokens(tokens, page_number))

    for page_number, page_text in page_list:
        items.extend(parse_boq_items(page_text, page_number))

    items = _dedupe_items(items)
    notes = list(warnings or [])
    missing_fields = [
        field_name
        for field_name, value in {
            "nomor kontrak": contract.contract_number,
            "tanggal kontrak": contract.contract_date,
            "vendor": contract.vendor_name,
            "unit": contract.unit_name,
        }.items()
        if not value
    ]
    if missing_fields:
        notes.append("Field perlu review: " + ", ".join(missing_fields))
    if not items:
        notes.append("BoQ belum terbaca otomatis; tambahkan baris manual saat review.")

    populated = 5 - len(missing_fields)
    item_score = min(len(items), 5) / 5
    overall = round((populated / 5 * 0.55) + (item_score * 0.45), 3)

    return ExtractionResult(
        contract=contract,
        boq_items=items,
        confidence_summary={"overall": overall, "notes": notes},
        warnings=notes,
    )


def parse_boq_items_from_tokens(tokens: list[Any], source_page: int | None = None) -> list[BoqItem]:
    if not tokens:
        return []
    lines = _ocr_tokens_to_lines(tokens)
    if not _has_boq_context([" ".join(token["text"] for token in line) for line in lines]):
        return []

    items: list[BoqItem] = []
    current_section: str | None = None
    pending: BoqItem | None = None

    for line in lines:
        line_text = _normalize_boq_line(" ".join(token["text"] for token in line))
        current_section = _update_boq_section(line_text, current_section)
        if _is_header_line(line_text) or _looks_like_non_boq_description(line_text):
            continue

        item = _parse_boq_token_line(line, source_page, current_section)
        if item:
            if pending:
                items.append(pending)
            pending = item
            continue

        if pending and _looks_like_continuation_line(line_text):
            pending.description = _repair_boq_description(f"{pending.description} {line_text}")
            pending.source_text = f"{pending.source_text or ''} {line_text}"[:500]

    if pending:
        items.append(pending)
    return _dedupe_items(items)


def _ocr_tokens_to_lines(tokens: list[Any]) -> list[list[dict[str, Any]]]:
    positioned = []
    for token in tokens:
        props = _token_box_props(token)
        text = clean_text(str(getattr(token, "text", "") or ""))
        if not props or not text:
            continue
        score = getattr(token, "score", None)
        if isinstance(score, (int, float)) and score < 0.25:
            continue
        positioned.append({**props, "text": text, "score": score})

    positioned.sort(key=lambda item: (item["center_y"], item["left"]))
    lines: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    heights: list[float] = []
    for token in positioned:
        if not lines:
            lines.append([token])
            centers.append(token["center_y"])
            heights.append(token["height"])
            continue
        threshold = max(8.0, min(heights[-1], token["height"]) * 0.7)
        if abs(token["center_y"] - centers[-1]) <= threshold:
            lines[-1].append(token)
            centers[-1] = (centers[-1] + token["center_y"]) / 2
            heights[-1] = max(heights[-1], token["height"])
        else:
            lines.append([token])
            centers.append(token["center_y"])
            heights.append(token["height"])

    return [sorted(line, key=lambda item: item["left"]) for line in lines]


def _token_box_props(token: Any) -> dict[str, float] | None:
    box = getattr(token, "box", None)
    try:
        points = [tuple(point) for point in box]
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except Exception:
        return None
    if not xs or not ys:
        return None
    left = min(xs)
    right = max(xs)
    top = min(ys)
    bottom = max(ys)
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "center_x": left + ((right - left) / 2),
        "center_y": top + ((bottom - top) / 2),
        "height": max(1.0, bottom - top),
    }


def _parse_boq_token_line(
    line: list[dict[str, Any]],
    source_page: int | None,
    section: str | None,
) -> BoqItem | None:
    if len(line) < 3:
        return None
    first_text = line[0]["text"].strip()
    first_match = re.match(r"^((?:\d+[.\-])*\d+)[.)]?$", first_text)
    if not first_match:
        merged_match = re.match(r"^((?:\d+[.\-])*\d+)[.)]?\s+(.+)$", first_text)
        if not merged_match:
            return None
        line = [{**line[0], "text": merged_match.group(1)}, {**line[0], "text": merged_match.group(2)}, *line[1:]]

    item_id = re.sub(r"[.)]+$", "", line[0]["text"].strip())
    token_texts = [token["text"] for token in line[1:]]
    quantity = _find_quantity_unit(token_texts)
    if quantity is None:
        return None
    unit_index, unit = quantity
    description_end = _description_end_before_quantity(token_texts, unit_index)
    description = _repair_boq_description(" ".join(token_texts[:description_end]).strip(" :-"))
    if len(description) < 3 or _looks_like_non_boq_description(description):
        return None

    price_tokens = token_texts[unit_index + 1 :]
    prices = _extract_price_values(price_tokens)
    if not prices:
        return None

    material_price, service_price = _assign_column_prices(prices, section)
    warnings = ["parsed_by_columns"]
    if len(prices) == 1:
        warnings.append("ambiguous_prices")
    if "n/a" in " ".join(token_texts).lower():
        warnings.append("na_columns_ignored")

    return BoqItem(
        item_id=item_id,
        description=description,
        unit=unit,
        material_unit_price=material_price,
        service_unit_price=service_price,
        source_page=source_page,
        source_text=_normalize_boq_line(" ".join([token["text"] for token in line]))[:500],
        confidence=0.88 if len(prices) >= 2 else 0.78,
        warnings=warnings,
    )


def _assign_column_prices(prices: list[float], section: str | None) -> tuple[float | None, float | None]:
    if section == "material":
        return prices[0], None
    if section == "jasa":
        return None, prices[0]
    if len(prices) >= 2:
        return prices[0], prices[1]
    return prices[0], None


def _looks_like_continuation_line(line: str) -> bool:
    if not line:
        return False
    if _item_id_match(line):
        return False
    lowered = line.lower()
    blocked = ["jumlah", "total", "harga satuan", "uraian pekerjaan", "bill of quantity"]
    return not any(token in lowered for token in blocked)


def _safe_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _find_first(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1) if match.lastindex else match.group(0)
        return value.strip()
    return None


def _find_contract_number(text: str) -> str | None:
    patterns = [
        r"\b(?:nomor|no\.?)\s*[:\-]?\s*((?:\d{2,4}\s*\.?\s*)?PJ/[A-Z0-9./\-\s]+/(?:19|20)\d{2})",
        r"\b((?:\d{2,4})\s*\.?\s*PJ/[A-Z0-9./\-\s]+/(?:19|20)\d{2})\b",
        r"(?:nomor\s+kontrak|nomor\s+perjanjian|kontrak\s+nomor|perjanjian\s+nomor)\s*[:\-]?\s*([A-Z0-9][A-Z0-9./\-\s]{4,80})",
        r"\b(?:nomor|no\.?)\s*(?!ski\b)(?:kontrak|perjanjian|spk|surat\s+perintah\s+kerja)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9./\-\s]{4,80})",
    ]
    value = _find_first(text, patterns)
    value = _trim_line_value(value)
    if not value:
        return None
    return re.sub(r"\s+", "", value.upper())


def _find_vendor_name(text: str) -> str | None:
    labeled = _find_first(
        text,
        [
            r"(?:perusahaan|nama\s+penyedia|penyedia\s+jasa|penyedia|vendor|pelaksana)\s*[:\-]?\s*((?:PT|CV)\.?\s*[A-Z0-9][^\n]{2,100})",
            r"(?:pihak\s+kedua)\s*[:\-]?\s*((?:PT|CV)\.?\s*[A-Z0-9][^\n]{2,100})",
        ],
    )
    if labeled:
        return _normalize_vendor_name(labeled)

    candidates = []
    for match in re.finditer(r"\b(?:PT|CV)\.?\s*[A-Z0-9][^\n]{2,80}", text, flags=re.IGNORECASE):
        candidate = _normalize_vendor_name(match.group(0))
        if candidate and not _is_pln_vendor_candidate(candidate):
            candidates.append(candidate)

    if not candidates:
        return None

    spaced = [candidate for candidate in candidates if len(candidate.split()) >= 3]
    return max(spaced or candidates, key=len)


def _trim_line_value(value: str | None) -> str | None:
    if not value:
        return None
    value = re.split(r"\s{2,}|\n|(?:\s+(?:tanggal|pekerjaan|vendor|penyedia)\b)", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = value.strip(" :-\t")
    return value or None


def _normalize_vendor_name(value: str | None) -> str | None:
    if not value:
        return None
    value = clean_text(value)
    value = re.split(
        r"\s+(?:PT\.?\s*PLN|PTPLN|PIHAK\s+PERTAMA|UNIT\s+INDUK|UNIT\s+PELAKSANA)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = value.strip(" .,:;-")
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())

    known_companies = {
        "PTCITAYASAPERDANA": "PT CITA YASA PERDANA",
        "CITAYASAPERDANA": "PT CITA YASA PERDANA",
    }
    if compact in known_companies:
        return known_companies[compact]

    value = re.sub(r"^(PT|CV)(?=[A-Z0-9])", r"\1 ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bPT\.?\b", "PT", value, flags=re.IGNORECASE)
    value = re.sub(r"\bCV\.?\b", "CV", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _is_pln_vendor_candidate(value: str) -> bool:
    compact = re.sub(r"[^A-Z]", "", value.upper())
    return any(token in compact for token in ["PLN", "PERSERO", "TRANSMISI", "UNITINDUK"])


def _find_unit_text(text: str) -> str | None:
    for unit in UNIT_OPTIONS:
        match = re.search(re.escape(unit), text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return _find_first(text, [r"(?:unit|upt|uit)\s*[:\-]?\s*([^\n]{3,80})"])


def _normalize_boq_line(line: str) -> str:
    line = line.replace("|", " ")
    line = re.sub(r"(?i)\bn\s*/\s*a\b", " N/A ", line)
    line = re.sub(r"([A-Za-z])(\d+[,.]\d{2,})", r"\1 \2", line)
    line = re.sub(r"(\d)([A-Za-z]{2,})(?=\s|$)", r"\1 \2", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def _has_boq_context(lines: list[str]) -> bool:
    text = " ".join(lines).lower()
    compact = re.sub(r"\s+", "", text)
    return (
        "billofquantity" in compact
        or "billofquantity" in text
        or ("uraian pekerjaan" in text and "volume" in text and "harga satuan" in text)
        or ("uraian" in text and "satuan" in text and "harga" in text)
    )


def _update_boq_section(line: str, current: str | None) -> str | None:
    lowered = line.lower().strip()
    if re.match(r"^(?:i|1)\s+material\b", lowered):
        return "material"
    if re.match(r"^(?:ii|2)\s+jasa\b", lowered):
        return "jasa"
    return current


def _is_header_line(line: str) -> bool:
    lowered = line.lower()
    header_words = ["uraian", "satuan", "harga", "material", "jasa"]
    return sum(word in lowered for word in header_words) >= 3


def _item_id_match(line: str) -> re.Match[str] | None:
    return re.match(
        r"^\s*((?:[A-Z]{1,3}\.?)?\d+(?:[.\-]\d+)*[.)]?|[IVXLC]{1,6}[.)])\s+(.+)$",
        line,
        flags=re.IGNORECASE,
    )


def _parse_boq_line(line: str, source_page: int | None) -> BoqItem | None:
    match = _item_id_match(line)
    if not match:
        return None

    item_id = match.group(1).strip().rstrip(".)")
    body = match.group(2).strip()
    tokens = body.split()
    if len(tokens) < 4:
        return None

    stripped_tokens = [
        token
        for token in tokens
        if token.lower().strip(".,") not in {"rp", "n/a", "na", "-"}
    ]
    quantity = _find_quantity_unit(stripped_tokens)
    if quantity is None:
        unit_index, unit, prices = _find_unit_then_prices(stripped_tokens)
    else:
        unit_index, unit = quantity
        prices = _extract_price_values(stripped_tokens[unit_index + 1 :])
    if not prices:
        return None

    description_end = _description_end_before_quantity(stripped_tokens, unit_index)
    description = _repair_boq_description(" ".join(stripped_tokens[:description_end]).strip(" :-"))
    if len(description) < 3:
        return None

    material_price = prices[0] if len(prices) == 2 else prices[0]
    service_price = prices[1] if len(prices) == 2 else None
    warnings: list[str] = []
    if len(prices) == 1:
        warnings.append("Hanya satu kolom harga terbaca.")
    if len(prices) > 2:
        warnings.append("Harga total terdeteksi dan diabaikan.")

    return BoqItem(
        item_id=item_id,
        description=description,
        unit=unit,
        material_unit_price=material_price,
        service_unit_price=service_price,
        source_page=source_page,
        source_text=line[:500],
        confidence=0.76 if warnings else 0.84,
        warnings=warnings,
    )


def _parse_boq_table_line(
    line: str,
    source_page: int | None,
    section: str | None,
) -> BoqItem | None:
    if section not in {"material", "jasa"}:
        return None

    match = re.match(r"^\s*(\d{1,3})\s+(.+)$", line)
    if not match:
        return None

    item_id = match.group(1)
    body = match.group(2).strip()
    if body.lower() in {"material", "jasa"}:
        return None

    tokens = body.split()
    quantity = _find_quantity_unit(tokens)
    if quantity is None:
        return None

    quantity_index, unit = quantity
    if quantity_index < 1:
        return None

    price_tokens = tokens[quantity_index + 1 :]
    prices = [parse_indonesian_currency(token) for token in price_tokens]
    prices = [price for price in prices if price is not None]
    if not prices:
        return None

    description = _repair_boq_description(" ".join(tokens[: _description_end_before_quantity(tokens, quantity_index)]))
    if len(description) < 3 or _looks_like_non_boq_description(description):
        return None

    material_price = prices[0] if section == "material" else None
    service_price = prices[0] if section == "jasa" else None

    return BoqItem(
        item_id=item_id,
        description=description,
        unit=unit,
        material_unit_price=material_price,
        service_unit_price=service_price,
        source_page=source_page,
        source_text=line[:500],
        confidence=0.86,
        warnings=[],
    )


def _find_quantity_unit(tokens: list[str]) -> tuple[int, str] | None:
    for index, token in enumerate(tokens):
        merged = re.match(r"^(\d[\d.,]*)([A-Za-z]{1,12})$", token)
        if merged:
            unit = _normalize_boq_unit(merged.group(2))
            if unit and any(parse_indonesian_currency(candidate) is not None for candidate in tokens[index + 1 :]):
                return index, unit

        if index + 1 < len(tokens) and re.fullmatch(r"\d[\d.,]*", token):
            unit = _normalize_boq_unit(tokens[index + 1])
            if unit and any(parse_indonesian_currency(candidate) is not None for candidate in tokens[index + 2 :]):
                return index + 1, unit

    return None


def _description_end_before_quantity(tokens: list[str], unit_index: int) -> int:
    if unit_index > 0 and re.fullmatch(r"\d[\d.,]*", tokens[unit_index - 1]):
        return unit_index - 1
    return unit_index


def _find_unit_then_prices(tokens: list[str]) -> tuple[int, str, list[float]]:
    for index in range(len(tokens) - 1, -1, -1):
        unit = _normalize_boq_unit(tokens[index])
        if not unit:
            continue
        prices = _extract_price_values(tokens[index + 1 :])
        if prices:
            return index, tokens[index].strip(".,;:"), prices
    return -1, "", []


def _extract_price_values(tokens: list[str]) -> list[float]:
    prices = []
    for token in tokens:
        normalized = token.lower().strip(".,;:")
        if normalized in {"rp", "n/a", "na", "-"}:
            continue
        if not re.search(r"\d", token):
            continue
        value = parse_indonesian_currency(token)
        if value is not None:
            prices.append(value)
    if len(prices) >= 4:
        return [prices[0], prices[2]]
    if len(prices) == 3:
        return prices[:2]
    return prices[:2]


def _normalize_boq_unit(value: str) -> str | None:
    normalized = value.lower().strip(".,;:()")
    return BOQ_UNIT_ALIASES.get(normalized)


def _looks_like_non_boq_description(value: str) -> bool:
    lowered = value.lower()
    blocked = ["berita acara", "pasal", "pihak pertama", "pihak kedua", "dokumen tender"]
    return any(token in lowered for token in blocked)


def _repair_boq_description(value: str) -> str:
    replacements = [
        (r"\bShockDumper", "Shock Dumper"),
        (r"\bAS55 mm\b", "AS55mm"),
        (r"DumperAS", "Dumper AS"),
        (r"\bArmourroduntuk", "Armour rod untuk "),
        (r"SuspensionClamp", "Suspension Clamp"),
        (r"Suspensionclamp", "Suspension clamp"),
        (r"ClampAS", "Clamp AS"),
        (r"clampgalvanized", "clamp galvanized"),
        (r"galvanizedAS", "galvanized AS"),
        (r"55mm2Galvanized", "55mm2 Galvanized"),
        (r"PGKemuntuk", "PG Klem untuk "),
        (r"SkunAL", "Skun AL"),
        (r"ASUk", "AS Uk"),
        (r"\bSackle120kN", "Sackle 120kN"),
        (r"\bsingletension", "single tension"),
        (r"\bPekeraanpasang", "Pekerjaan pasang"),
        (r"steggeruntuk", "stegger untuk"),
        (r"\bPengangkutanmaterial", "Pengangkutan material"),
        (r"\bRetummaterial", "Return material"),
        (r"\blokasikegudang", "lokasi ke gudang"),
        (r"\bgudangPLN", "gudang PLN"),
        (r"\bPLNUPT", "PLN UPT"),
        (r"UPTkelokasi", "UPT ke lokasi"),
        (r"\bkelokasi", "ke lokasi"),
        (r"\bBongkardanpasang", "Bongkar dan pasang"),
        (r"\bSEWAKANTORPROYEK\b", "SEWA KANTOR PROYEK"),
        (r"\bSEWALAPTOP\b", "SEWA LAPTOP"),
        (r"\bSOFTCOPY\b", "SOFT COPY"),
        (r"\bKOMUNIKASI\b", "KOMUNIKASI"),
        (r"\bPeremajaanGsw", "Peremajaan GSW"),
        (r"\bpengamanPetir", "pengaman Petir"),
        (r"danpasang", "dan pasang"),
        (r"PengamananPetir", "Pengamanan Petir"),
    ]
    repaired = value
    for pattern, replacement in replacements:
        repaired = re.sub(pattern, replacement, repaired)
    repaired = re.sub(r"\s+", " ", repaired)
    return repaired.strip(" :-")


def _parse_partial_boq_line(line: str, source_page: int | None) -> BoqItem | None:
    match = _item_id_match(line)
    if not match:
        return None
    description = match.group(2).strip()
    if len(description) < 6:
        return None
    return BoqItem(
        item_id=match.group(1).strip().rstrip(".)"),
        description=description,
        unit="-",
        source_page=source_page,
        source_text=line[:500],
        confidence=0.35,
        warnings=["Baris BoQ parsial; satuan/harga perlu dilengkapi."],
    )


def _dedupe_items(items: list[BoqItem]) -> list[BoqItem]:
    seen: set[tuple[str, str]] = set()
    deduped: list[BoqItem] = []
    for item in items:
        key = (item.item_id.lower(), re.sub(r"\W+", "", item.description.lower())[:48])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
