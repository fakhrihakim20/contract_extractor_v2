# Contract Extractor v2

Streamlit app untuk membaca PDF kontrak dari Google Drive, mengekstrak draft metadata + BoQ tanpa OpenAI API, lalu menyimpan hasil review ke database Supabase lama.

## Stack

- Streamlit Community Cloud
- Supabase Python client dengan `SUPABASE_SERVICE_ROLE_KEY` di server-side secrets
- Google Drive API service account untuk folder PDF private
- PyMuPDF untuk text-native PDF
- PaddleOCR untuk fallback OCR halaman scan, dipisah sebagai optional dependency agar app tetap bisa boot di Streamlit Cloud free tier
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

PaddleOCR akan mengunduh model OCR saat pertama kali dipakai. PDF yang sudah punya text layer akan diproses dengan PyMuPDF tanpa memuat PaddleOCR.

## OCR Dependency

`requirements.txt` sengaja dibuat ringan agar Streamlit Cloud tidak gagal saat install.
Kode OCR tetap memakai PaddleOCR, tetapi dependency beratnya ada di `requirements-ocr.txt`.

Untuk environment yang kuat:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-ocr.txt
```

Di Streamlit Cloud free tier, app tetap bisa import dan memproses PDF text-native tanpa OCR.
Jika PDF scan memerlukan OCR dan PaddleOCR belum terpasang di runtime, job akan gagal dengan pesan konfigurasi OCR yang eksplisit, bukan membuat seluruh app gagal install.

## Workflow

1. `Drive Intake`: klik `Sync Google Drive`, pilih PDF, lalu `Import + Process`.
2. `Review Draft`: koreksi metadata kontrak dan baris BoQ.
3. `Approve final`: memanggil RPC Supabase `approve_contract_document`.
4. `Data Final`: lihat kontrak approved dan download CSV BoQ.

## Supabase Mapping

Tidak ada migrasi awal. App memakai tabel lama:

- `documents.storage_bucket = "google-drive"`
- `documents.storage_path = "gdrive:<drive_file_id>"`
- `extraction_jobs.model = "local-paddleocr-regex-v1"`
- Draft disimpan ke `contract_extraction_drafts` dan `boq_extraction_draft_items`
- Approval tetap lewat `approve_contract_document`

Pastikan tabel dan RPC tersebut masih exposed di Supabase Data API. Project lama sudah menyiapkan grant/RLS; jika API settings Supabase baru mematikan exposure per tabel/function, aktifkan kembali untuk entitas di atas.

## Verification

```bash
python -m unittest discover -s tests
python -m compileall app.py contract_extractor tests
```
