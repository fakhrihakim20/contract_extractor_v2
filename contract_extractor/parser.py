from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Iterable

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
    "unit",
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
        rf"\b(\d{{1,2}})\s+({month_pattern})\s+((?:19|20)\d{{2}})\b",
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
    return None, compact


def parse_contract_metadata(text: str) -> ContractMetadata:
    normalized = clean_text(text)
    contract_number = _find_first(
        normalized,
        [
            r"(?:nomor|no\.?)\s*(?:kontrak|perjanjian|spk|surat\s+perintah\s+kerja)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9./\-\s]{4,80})",
            r"(?:kontrak|perjanjian)\s*(?:nomor|no\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9./\-\s]{4,80})",
        ],
    )
    contract_number = _trim_line_value(contract_number)

    date_value = _find_first(
        normalized,
        [
            r"(?:tanggal\s+kontrak|tanggal\s+perjanjian|tgl\.?)\s*[:\-]?\s*([^\n]{6,40})",
            r"\b(\d{1,2}\s+(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+(?:19|20)\d{2})\b",
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

    vendor_name = _find_first(
        normalized,
        [
            r"(?:nama\s+penyedia|penyedia\s+jasa|penyedia|vendor|pelaksana|pihak\s+kedua)\s*[:\-]?\s*([^\n]{3,100})",
            r"(?:pt|cv)\.?\s+[A-Z0-9][^\n]{2,90}",
        ],
    )
    vendor_name = _trim_line_value(vendor_name)

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
    lines = [_normalize_boq_line(line) for line in clean_text(text).splitlines()]
    lines = [line for line in lines if line and not _is_header_line(line)]
    items: list[BoqItem] = []
    pending: str | None = None

    for line in lines:
        starts_item = bool(_item_id_match(line))
        candidate = line if pending is None else f"{pending} {line}"
        parsed = _parse_boq_line(candidate, source_page)
        if parsed:
            items.append(parsed)
            pending = None
            continue

        if starts_item:
            pending = line
        elif pending:
            pending = candidate

    if pending:
        fallback = _parse_partial_boq_line(pending, source_page)
        if fallback:
            items.append(fallback)

    return _dedupe_items(items)


def parse_extraction_pages(pages: Iterable[tuple[int, str]], warnings: list[str] | None = None) -> ExtractionResult:
    page_list = [(page, clean_text(text)) for page, text in pages]
    full_text = "\n\n".join(text for _, text in page_list)
    contract = parse_contract_metadata(full_text)

    items: list[BoqItem] = []
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


def _trim_line_value(value: str | None) -> str | None:
    if not value:
        return None
    value = re.split(r"\s{2,}|\n|(?:\s+(?:tanggal|pekerjaan|vendor|penyedia)\b)", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = value.strip(" :-\t")
    return value or None


def _find_unit_text(text: str) -> str | None:
    for unit in UNIT_OPTIONS:
        match = re.search(re.escape(unit), text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return _find_first(text, [r"(?:unit|upt|uit)\s*[:\-]?\s*([^\n]{3,80})"])


def _normalize_boq_line(line: str) -> str:
    line = line.replace("|", " ")
    line = re.sub(r"\s+", " ", line)
    return line.strip()


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

    stripped_tokens = [token for token in tokens if token.lower().strip(".") != "rp"]
    prices: list[float] = []
    price_token_count = 0
    index = len(stripped_tokens) - 1

    while index >= 0 and len(prices) < 2:
        token = stripped_tokens[index]
        parsed = parse_indonesian_currency(token)
        if parsed is None or not re.search(r"\d", token):
            break
        prices.insert(0, parsed)
        price_token_count += 1
        index -= 1

    if not prices:
        return None

    unit_index = len(stripped_tokens) - price_token_count - 1
    if unit_index < 1:
        return None

    unit = stripped_tokens[unit_index].strip(".,;:")
    if unit.lower() not in BOQ_UNIT_WORDS:
        return None

    description = " ".join(stripped_tokens[:unit_index]).strip(" :-")
    if len(description) < 3:
        return None

    material_price = prices[0] if len(prices) == 2 else prices[0]
    service_price = prices[1] if len(prices) == 2 else None
    warnings: list[str] = []
    if len(prices) == 1:
        warnings.append("Hanya satu kolom harga terbaca.")

    return BoqItem(
        item_id=item_id,
        description=description,
        unit=unit,
        material_unit_price=material_price,
        service_unit_price=service_price,
        source_page=source_page,
        source_text=line[:500],
        confidence=0.72 if warnings else 0.82,
        warnings=warnings,
    )


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
