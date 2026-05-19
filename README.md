# Contract Extractor v2

Streamlit app untuk membaca PDF kontrak dari Google Drive, mengekstrak draft metadata + BoQ tanpa OpenAI API, lalu menyimpan hasil review ke database Supabase lama.

## Stack

- Streamlit Community Cloud
- Supabase Python client dengan `SUPABASE_SERVICE_ROLE_KEY` di server-side secrets
- Google Drive API service account untuk folder PDF private
- PyMuPDF untuk text-native PDF
- RapidOCR + ONNXRuntime untuk fallback OCR halaman scan di CPU Streamlit
- Taste-skill UI theme: premium operations console, `Outfit` + `JetBrains Mono`, matte neutral surfaces, and a single blue-gray accent

## Secrets

Isi secrets di Streamlit Community Cloud melalui app settings. Untuk lokal, buat `.streamlit/secrets.toml` dan jangan commit file tersebut.

```toml
SUPABASE_URL = "https://cxretrzlhzsijiegyiwl.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "replace-with-service-role-key"
GOOGLE_DRIVE_FOLDER_ID = "replace-with-folder-id"
GOOGLE_SERVICE_ACCOUNT_JSON = """{"type":"service_account", "...":"..."}"""
```

Share folder Google Drive sumber PDF ke email `client_email` dari service account.

## Local Run

Python lokal yang direkomendasikan sama dengan Streamlit Cloud, yaitu Python 3.12.
Saat deploy di Streamlit Community Cloud, pilih Python 3.12 di `Advanced settings`.
Jika app sudah dibuat dengan versi Python lain, Streamlit mewajibkan delete + redeploy untuk mengganti versi Python.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

PDF yang sudah punya text layer akan diproses dengan PyMuPDF tanpa OCR. Halaman scan akan dirender satu per satu lalu dibaca lokal dengan RapidOCR ONNXRuntime.

## RapidOCR Runtime

`requirements.txt` memasang `rapidocr` dan `onnxruntime`, jadi tidak perlu API OCR eksternal.
Streamlit Community Cloud tetap memiliki resource terbatas; proses scan besar dibuat satu dokumen per aksi dan satu halaman per iterasi.
Model ONNX RapidOCR disimpan di folder writable `~/.cache/contract_extractor_v2/rapidocr`, bukan di `site-packages`, agar tidak kena `Permission denied` di Streamlit Cloud. Jika perlu override, set environment variable `RAPIDOCR_MODEL_ROOT`.

Jika build Cloud gagal karena wheel Python, deploy ulang dengan Python 3.12 dari Advanced settings Streamlit.

## Workflow

1. `Drive Intake`: klik `Sync Google Drive`, pilih PDF, lalu `Import + Process`.
   Sync membaca PDF secara rekursif dari folder, subfolder, dan shortcut folder Google Drive.
2. `Review Draft`: koreksi metadata kontrak dan baris BoQ.
3. `Approve final`: memanggil RPC Supabase `approve_contract_document`.
4. `Data Final`: lihat kontrak approved dan download CSV BoQ.

PDF di atas 50 MB tetap tampil di daftar Drive untuk audit, tetapi tidak bisa diimport/process di Streamlit Cloud agar OCR lokal tidak kehabisan resource.

## Supabase Mapping

Tidak ada migrasi awal. App memakai tabel lama:

- `documents.storage_bucket = "google-drive"`
- `documents.storage_path = "gdrive:<drive_file_id>"`
- `documents.pdf_link = "<google_drive_web_view_link>"`
- `extraction_jobs.model = "rapidocr-onnxruntime-v1"`
- Draft disimpan ke `contract_extraction_drafts` dan `boq_extraction_draft_items`
- Approval tetap lewat `approve_contract_document`

Pastikan tabel dan RPC tersebut masih exposed di Supabase Data API. Project lama sudah menyiapkan grant/RLS; jika API settings Supabase baru mematikan exposure per tabel/function, aktifkan kembali untuk entitas di atas.

Migration tambahan untuk link PDF ada di `supabase/migrations/20260519073000_add_documents_pdf_link.sql`.
Jalankan di Supabase sebelum mengandalkan kolom `pdf_link`; app tetap menampilkan fallback link dari `storage_path` kalau migration belum terpasang.

## Verification

```bash
python -m unittest discover -s tests
python -m compileall app.py contract_extractor tests
```

## Benchmark Sample

PDF contoh `018 PJ Peremajaan GSW untuk Perbaikan sistem Pengamanan Petir.pdf`:

- Ukuran: 19.175 MB
- Halaman: 37
- Text layer native: 0 karakter
- RapidOCR 2x render CPU lokal: 37/37 halaman sukses, 0 kosong, 0 error
- Total OCR: 566.449 detik
- Rata-rata: 15.309 detik/halaman
- Rentang halaman: 7.901-29.085 detik
- Parser v2 mengenali metadata sampel sebagai `018.PJ/DAN.01.03/F34050000/2025`, tanggal `2025-10-13`, vendor `PT CITA YASA PERDANA`, unit `UPT Surabaya`, dan 16 baris BoQ dari lampiran.
