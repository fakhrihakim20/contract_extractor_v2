from __future__ import annotations

import unittest
from typing import Any

from contract_extractor.supabase_repo import SupabaseRepository


class SupabaseRepoTests(unittest.TestCase):
    def test_upsert_draft_uses_returned_row_when_available(self) -> None:
        draft = {"id": "draft-1", "document_id": "doc-1"}
        repo = _repo_with_client(FakeClient(upsert_data=[draft]))

        result = repo.upsert_draft("doc-1", {"contract_number": "001"})

        self.assertEqual(result, draft)
        self.assertEqual(repo._client.fetch_count, 0)
        self.assertFalse(repo._client.upsert_builder.select_called)

    def test_upsert_draft_fetches_row_when_upsert_returns_no_data(self) -> None:
        draft = {"id": "draft-1", "document_id": "doc-1"}
        repo = _repo_with_client(FakeClient(upsert_data=[], fetch_data=[draft]))

        result = repo.upsert_draft("doc-1", {"contract_number": "001"})

        self.assertEqual(result, draft)
        self.assertEqual(repo._client.fetch_count, 1)
        self.assertFalse(repo._client.upsert_builder.select_called)

    def test_upsert_draft_does_not_call_select_on_upsert_builder(self) -> None:
        repo = _repo_with_client(FakeClient(upsert_data=[], fetch_data=[]))

        with self.assertRaisesRegex(RuntimeError, "Gagal menyimpan draft kontrak"):
            repo.upsert_draft("doc-1", {"contract_number": "001"})

        self.assertFalse(repo._client.upsert_builder.select_called)


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeClient:
    def __init__(self, *, upsert_data: Any = None, fetch_data: Any = None) -> None:
        self.upsert_data = upsert_data
        self.fetch_data = fetch_data
        self.upsert_builder = FakeUpsertBuilder(upsert_data)
        self.fetch_count = 0

    def table(self, name: str) -> Any:
        if name != "contract_extraction_drafts":
            raise AssertionError(f"Unexpected table: {name}")
        return FakeTable(self)


class FakeTable:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    def upsert(self, row: dict[str, Any], *, on_conflict: str) -> "FakeUpsertBuilder":
        self.client.upsert_builder.row = row
        self.client.upsert_builder.on_conflict = on_conflict
        return self.client.upsert_builder

    def select(self, fields: str) -> "FakeSelectBuilder":
        self.client.fetch_count += 1
        return FakeSelectBuilder(self.client.fetch_data)


class FakeUpsertBuilder:
    def __init__(self, data: Any) -> None:
        self.data = data
        self.select_called = False
        self.row: dict[str, Any] | None = None
        self.on_conflict: str | None = None

    def select(self, fields: str) -> "FakeUpsertBuilder":
        self.select_called = True
        raise AttributeError("'SyncQueryRequestBuilder' object has no attribute 'select'")

    def execute(self) -> FakeResponse:
        return FakeResponse(self.data)


class FakeSelectBuilder:
    def __init__(self, data: Any) -> None:
        self.data = data

    def eq(self, field: str, value: Any) -> "FakeSelectBuilder":
        return self

    def limit(self, count: int) -> "FakeSelectBuilder":
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self.data)


def _repo_with_client(client: FakeClient) -> SupabaseRepository:
    repo = object.__new__(SupabaseRepository)
    repo._client = client
    repo._documents_pdf_link_supported = True
    return repo


if __name__ == "__main__":
    unittest.main()
