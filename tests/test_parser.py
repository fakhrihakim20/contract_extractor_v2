from __future__ import annotations

import unittest
from types import SimpleNamespace

from contract_extractor.parser import (
    format_date_iso,
    normalize_unit_name,
    parse_boq_items,
    parse_boq_items_from_tokens,
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
        self.assertEqual(format_date_iso("130ktober2025"), "2025-10-13")
        self.assertEqual(format_date_iso("13 Okdober 2025"), "2025-10-13")
        self.assertIsNone(format_date_iso("31/02/2026"))

    def test_normalize_unit_name(self) -> None:
        self.assertEqual(normalize_unit_name("UPT Surabaya"), ("UPT Surabaya", "UPT Surabaya"))
        self.assertEqual(normalize_unit_name("Unit Pelaksana UPT Gresik"), ("UPT Gresik", "Unit Pelaksana UPT Gresik"))
        self.assertEqual(
            normalize_unit_name("UnitIndukTransmisiJawaBagianTimurDanBali UnitPelaksanaTransmisiSurabaya")[0],
            "UPT Surabaya",
        )
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

    def test_parse_metadata_from_rapidocr_cover_text(self) -> None:
        metadata = parse_contract_metadata(
            """
            PT.PLN (Persero)
            UNITINDUKTRANSMISIJAWABAGIANTIMURDANBALI
            UNITPELAKSANATRANSMISISURABAYA
            SURATPERJANJIAN
            Nomor ：018.PJ/DAN.01.03/F34050000/2025
            Tanggal :130ktober2025
            Perihal :PeremajaanGswuntukperbaikansistem
            pengaman Petir diUPT Surabaya
            NoSKI 2025.TJTB.4.003
            Perusahaan PTCITAYASAPERDANA
            """
        )
        self.assertEqual(metadata.contract_number, "018.PJ/DAN.01.03/F34050000/2025")
        self.assertEqual(metadata.contract_date, "2025-10-13")
        self.assertEqual(metadata.contract_year, 2025)
        self.assertEqual(metadata.vendor_name, "PT CITA YASA PERDANA")
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

    def test_parse_boq_items_from_rapidocr_table(self) -> None:
        items = parse_boq_items(
            """
            BILLof QUANTITY
            M URAIAN PEKERJAAN VOLUME HARGA SATUAN JUMLAH HARGA
            1 Material
            1 AS55mm 41.679.230meler 21.975 915.918.792 915.918.792
            2 ShockDumperAS55mm 90.000bh 387.754 34.897.883 34.897.883
            5 Dead end singletension(deadend press)galvanizedAS55mm 46.000bh 1.114.526 51.268.173 51.268.173
            II Jasa
            1 Bongkardanpasang GSW(include sagging) 41.679.230meter 15.902 662.770.611 662.770.611
            4 Pengangkutanmaterial dari gudangPLN UPTkelokasi 1,000ls 62.606.800 62.606.800 62.606.800
            """,
            source_page=37,
        )
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0].description, "AS55mm")
        self.assertEqual(items[0].unit, "meter")
        self.assertEqual(items[0].material_unit_price, 21975.0)
        self.assertIsNone(items[0].service_unit_price)
        self.assertEqual(items[3].description, "Bongkar dan pasang GSW(include sagging)")
        self.assertEqual(items[3].service_unit_price, 15902.0)
        self.assertEqual(items[4].unit, "ls")
        self.assertEqual(items[4].service_unit_price, 62606800.0)

    def test_parse_boq_items_with_na_columns(self) -> None:
        items = parse_boq_items(
            """
            BILL OF QUANTITY
            Uraian Pekerjaan Volume Satuan Harga Satuan Jumlah Harga
            1.3.6 KOMUNIKASI 0,25 bulan N/A 3.123.250,00 N/A 780.812,50 780.812,50
            1.7.3 SEWAKANTORPROYEK 1,00 lot N/A 7.500.000,00 N/A 7.500.000,00 7.500.000,00
            """,
            source_page=37,
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].unit, "bulan")
        self.assertEqual(items[0].material_unit_price, 3123250.0)
        self.assertEqual(items[0].service_unit_price, 780812.5)
        self.assertEqual(items[1].description, "SEWA KANTOR PROYEK")

    def test_parse_boq_items_from_ocr_token_columns(self) -> None:
        tokens = [
            _token("URAIAN PEKERJAAN", 100, 10),
            _token("VOLUME", 450, 10),
            _token("HARGA SATUAN", 640, 10),
            _token("JUMLAH HARGA", 840, 10),
            _token("1.3.6", 40, 50),
            _token("KOMUNIKASI", 120, 50),
            _token("0,25", 430, 50),
            _token("bulan", 500, 50),
            _token("N/A", 610, 50),
            _token("3.123.250,00", 670, 50),
            _token("N/A", 780, 50),
            _token("780.812,50", 850, 50),
            _token("780.812,50", 960, 50),
        ]
        items = parse_boq_items_from_tokens(tokens, source_page=37)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].item_id, "1.3.6")
        self.assertEqual(items[0].description, "KOMUNIKASI")
        self.assertEqual(items[0].unit, "bulan")
        self.assertEqual(items[0].material_unit_price, 3123250.0)
        self.assertEqual(items[0].service_unit_price, 780812.5)
        self.assertGreater(items[0].confidence, 0.35)

    def test_parse_extraction_ignores_numbered_contract_clauses(self) -> None:
        items = parse_boq_items(
            """
            8) Berita Acara Penyerahan Akhir adalah berita acara yang dibuat untuk menyatakan hak.
            9) Gambar-gambar apabila ada.
            10) Daftar kuantitas dan harga.
            PASAL 3 LINGKUP PEKERJAAN
            """
        )
        self.assertEqual(items, [])

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


def _token(text: str, left: float, top: float) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        score=0.96,
        box=[
            [left, top],
            [left + max(20, len(text) * 7), top],
            [left + max(20, len(text) * 7), top + 18],
            [left, top + 18],
        ],
    )
