from __future__ import annotations

import unittest

from contract_extractor.parser import (
    format_date_iso,
    normalize_unit_name,
    parse_boq_items,
    parse_contract_metadata,
    parse_extraction_pages,
    parse_indonesian_currency,
)


class ParserTests(unittest.TestCase):
    def test_parse_indonesian_currency(self) -> None:
        cases = {
            "Rp 1.250.000": 1250000.0,
            "1.250.000,50": 1250000.50,
            "2,500,000": 2500000.0,
            "750000": 750000.0,
            "Rp 12.500,-": 12500.0,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_indonesian_currency(raw), expected)

    def test_format_date_iso(self) -> None:
        self.assertEqual(format_date_iso("16 Mei 2026"), "2026-05-16")
        self.assertEqual(format_date_iso("16/05/2026"), "2026-05-16")
        self.assertEqual(format_date_iso("2026-05-16"), "2026-05-16")
        self.assertIsNone(format_date_iso("31/02/2026"))

    def test_normalize_unit_name(self) -> None:
        self.assertEqual(normalize_unit_name("UPT Surabaya"), ("UPT Surabaya", "UPT Surabaya"))
        self.assertEqual(normalize_unit_name("Unit Pelaksana UPT Gresik"), ("UPT Gresik", "Unit Pelaksana UPT Gresik"))
        self.assertEqual(normalize_unit_name("Area Lain"), (None, "Area Lain"))

    def test_parse_metadata_empty(self) -> None:
        metadata = parse_contract_metadata("")
        self.assertIsNone(metadata.contract_number)
        self.assertIsNone(metadata.vendor_name)
        self.assertIsNone(metadata.unit_name)

    def test_parse_metadata_from_contract_text(self) -> None:
        metadata = parse_contract_metadata(
            """
            Nomor Kontrak: 001/SPK/JBM/2026
            Tanggal Kontrak: 16 Mei 2026
            Nama Penyedia: PT Contoh Energi Nusantara
            Unit: UPT Surabaya
            """
        )
        self.assertEqual(metadata.contract_number, "001/SPK/JBM/2026")
        self.assertEqual(metadata.contract_date, "2026-05-16")
        self.assertEqual(metadata.contract_year, 2026)
        self.assertEqual(metadata.vendor_name, "PT Contoh Energi Nusantara")
        self.assertEqual(metadata.unit_name, "UPT Surabaya")

    def test_parse_boq_items_multiline(self) -> None:
        items = parse_boq_items(
            """
            No Uraian Satuan Harga Material Harga Jasa
            1.1 Penggantian isolator
            gantung polymer Set 1.200.000 350.000
            1.2 Pengujian tahanan kontak Unit Rp 250.000 Rp 125.000
            """,
            source_page=3,
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].item_id, "1.1")
        self.assertEqual(items[0].description, "Penggantian isolator gantung polymer")
        self.assertEqual(items[0].unit, "Set")
        self.assertEqual(items[0].material_unit_price, 1200000.0)
        self.assertEqual(items[0].service_unit_price, 350000.0)
        self.assertEqual(items[0].source_page, 3)

    def test_parse_extraction_pages_with_no_boq(self) -> None:
        result = parse_extraction_pages(
            [
                (
                    1,
                    """
                    Nomor Kontrak: 010/SPK/2026
                    Tanggal Kontrak: 17 Mei 2026
                    Vendor: CV Daya Jaya
                    Unit: UPT Malang
                    """,
                )
            ]
        )
        self.assertEqual(result.contract.contract_number, "010/SPK/2026")
        self.assertEqual(result.boq_items, [])
        self.assertIn("BoQ belum terbaca otomatis", " ".join(result.warnings))


if __name__ == "__main__":
    unittest.main()
