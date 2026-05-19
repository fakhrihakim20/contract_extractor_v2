alter table public.documents
  add column if not exists pdf_link text;

comment on column public.documents.pdf_link
  is 'Google Drive web view URL for the source PDF.';

update public.documents
set pdf_link = 'https://drive.google.com/file/d/' || replace(storage_path, 'gdrive:', '') || '/view'
where pdf_link is null
  and storage_bucket = 'google-drive'
  and storage_path like 'gdrive:%';
