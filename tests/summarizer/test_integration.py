"""Integration tests for the summarizer with memory system."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from agent_cli.memory._ingest import summarize_content
from agent_cli.memory._persistence import persist_hierarchical_summary
from agent_cli.memory._store import (
    get_final_summary,
    get_summary_at_level,
    upsert_hierarchical_summary,
)
from agent_cli.summarizer import AdaptiveSummarizer, SummaryLevel, SummaryResult
from agent_cli.summarizer.models import ChunkSummary, HierarchicalSummary

if TYPE_CHECKING:
    from pathlib import Path


class _FakeCollection:
    """Minimal Chroma-like collection for testing."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, dict[str, Any]]] = {}

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        for doc_id, doc, meta in zip(ids, documents, metadatas, strict=False):
            self._store[doc_id] = (doc, meta)

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        if where is None:
            return {"documents": [], "metadatas": [], "ids": []}

        results: list[tuple[str, tuple[str, dict[str, Any]]]] = []
        for doc_id, (doc, meta) in self._store.items():
            # Check all conditions in $and clause
            conditions = where.get("$and", [where])
            match = True
            for clause in conditions:
                for k, v in clause.items():
                    if k == "$and":
                        continue
                    if isinstance(v, dict):
                        if "$in" in v and meta.get(k) not in v["$in"]:
                            match = False
                        if "$ne" in v and meta.get(k) == v["$ne"]:
                            match = False
                    elif meta.get(k) != v:
                        match = False
            if match:
                results.append((doc_id, (doc, meta)))

        docs = [doc for _, (doc, _) in results]
        metas = [meta for _, (_, meta) in results]
        ids = [doc_id for doc_id, _ in results]
        return {"documents": docs, "metadatas": metas, "ids": ids}

    def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> None:
        if ids:
            for doc_id in ids:
                self._store.pop(doc_id, None)


@pytest.fixture
def fake_collection() -> _FakeCollection:
    """Create a fake ChromaDB collection."""
    return _FakeCollection()


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    """Create a temporary memory root directory."""
    return tmp_path / "memory"


class TestSummaryResultStorageMetadata:
    """Test SummaryResult.to_storage_metadata for various levels."""

    def test_standard_summary_produces_single_entry(self) -> None:
        """Test that STANDARD level produces a single L3 entry."""
        result = SummaryResult(
            level=SummaryLevel.STANDARD,
            summary="A paragraph summary of the content.",
            hierarchical=None,
            input_tokens=1000,
            output_tokens=50,
            compression_ratio=0.05,
        )

        entries = result.to_storage_metadata("conv-123")

        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"] == "conv-123:summary:L3:final"
        assert entry["content"] == "A paragraph summary of the content."
        assert entry["metadata"]["level"] == 3
        assert entry["metadata"]["is_final"] is True
        assert entry["metadata"]["summary_level"] == "STANDARD"

    def test_hierarchical_summary_produces_multiple_entries(self) -> None:
        """Test that HIERARCHICAL level produces L1, L2, L3 entries."""
        l1_summaries = [
            ChunkSummary(
                chunk_index=0,
                content="Chunk 0",
                token_count=10,
                source_tokens=100,
                parent_group=0,
            ),
            ChunkSummary(
                chunk_index=1,
                content="Chunk 1",
                token_count=10,
                source_tokens=100,
                parent_group=0,
            ),
            ChunkSummary(
                chunk_index=2,
                content="Chunk 2",
                token_count=10,
                source_tokens=100,
                parent_group=0,
            ),
        ]
        hierarchical = HierarchicalSummary(
            l1_summaries=l1_summaries,
            l2_summaries=["Group 0 summary"],
            l3_summary="Final hierarchical synthesis.",
        )
        result = SummaryResult(
            level=SummaryLevel.HIERARCHICAL,
            summary="Final hierarchical synthesis.",
            hierarchical=hierarchical,
            input_tokens=20000,
            output_tokens=200,
            compression_ratio=0.01,
        )

        entries = result.to_storage_metadata("conv-456")

        # Should have 3 L1 + 1 L2 + 1 L3 = 5 entries
        assert len(entries) == 5

        # Check L1 entries
        l1_entries = [e for e in entries if e["metadata"]["level"] == 1]
        assert len(l1_entries) == 3

        # Check L2 entries
        l2_entries = [e for e in entries if e["metadata"]["level"] == 2]
        assert len(l2_entries) == 1

        # Check L3 entry
        l3_entries = [e for e in entries if e["metadata"]["level"] == 3]
        assert len(l3_entries) == 1


class TestHierarchicalSummaryStorage:
    """Test storing hierarchical summaries to ChromaDB."""

    def test_store_simple_summary(self, fake_collection: _FakeCollection) -> None:
        """Test storing a simple (non-hierarchical) summary."""
        result = SummaryResult(
            level=SummaryLevel.STANDARD,
            summary="A standard summary.",
            hierarchical=None,
            input_tokens=1000,
            output_tokens=50,
            compression_ratio=0.05,
        )

        ids = upsert_hierarchical_summary(fake_collection, "conv-123", result)

        assert len(ids) == 1
        assert "conv-123:summary:L3:final" in ids

        # Verify retrieval
        stored = get_final_summary(fake_collection, "conv-123")
        assert stored is not None
        assert stored.content == "A standard summary."

    def test_store_hierarchical_summary(self, fake_collection: _FakeCollection) -> None:
        """Test storing a hierarchical summary with all levels."""
        l1_summaries = [
            ChunkSummary(
                chunk_index=0,
                content="Chunk 0 summary",
                token_count=10,
                source_tokens=100,
            ),
            ChunkSummary(
                chunk_index=1,
                content="Chunk 1 summary",
                token_count=10,
                source_tokens=100,
            ),
        ]
        hierarchical = HierarchicalSummary(
            l1_summaries=l1_summaries,
            l2_summaries=[],
            l3_summary="Final summary",
        )
        result = SummaryResult(
            level=SummaryLevel.DETAILED,
            summary="Final summary",
            hierarchical=hierarchical,
            input_tokens=5000,
            output_tokens=100,
            compression_ratio=0.02,
        )

        ids = upsert_hierarchical_summary(fake_collection, "conv-789", result)

        assert len(ids) == 3  # 2 L1 + 1 L3

        # Verify L1 retrieval
        l1_stored = get_summary_at_level(fake_collection, "conv-789", level=1)
        assert len(l1_stored) == 2

        # Verify L3 retrieval
        final = get_final_summary(fake_collection, "conv-789")
        assert final is not None
        assert final.content == "Final summary"


class TestFilePersistence:
    """Test hierarchical summary file persistence."""

    def test_persist_hierarchical_creates_files(
        self,
        fake_collection: _FakeCollection,
        memory_root: Path,
    ) -> None:
        """Test that persist_hierarchical_summary creates correct file structure."""
        l1_summaries = [
            ChunkSummary(
                chunk_index=0,
                content="Chunk 0 content",
                token_count=10,
                source_tokens=100,
                parent_group=0,
            ),
            ChunkSummary(
                chunk_index=1,
                content="Chunk 1 content",
                token_count=10,
                source_tokens=100,
                parent_group=0,
            ),
        ]
        hierarchical = HierarchicalSummary(
            l1_summaries=l1_summaries,
            l2_summaries=["Group 0 summary"],
            l3_summary="Final synthesis",
        )
        result = SummaryResult(
            level=SummaryLevel.HIERARCHICAL,
            summary="Final synthesis",
            hierarchical=hierarchical,
            input_tokens=20000,
            output_tokens=200,
            compression_ratio=0.01,
        )

        ids = persist_hierarchical_summary(
            fake_collection,
            memory_root=memory_root,
            conversation_id="test-conv",
            summary_result=result,
        )

        assert len(ids) == 4  # 2 L1 + 1 L2 + 1 L3

        # Check file structure (note: _slugify converts - to - not _)
        entries_dir = memory_root / "entries" / "test-conv"
        l1_dir = entries_dir / "summaries" / "L1"
        l2_dir = entries_dir / "summaries" / "L2"
        l3_dir = entries_dir / "summaries" / "L3"

        assert l1_dir.exists()
        assert l2_dir.exists()
        assert l3_dir.exists()

        # Check L1 files
        l1_files = list(l1_dir.glob("*.md"))
        assert len(l1_files) == 2

        # Check L2 files
        l2_files = list(l2_dir.glob("*.md"))
        assert len(l2_files) == 1

        # Check L3 files
        l3_files = list(l3_dir.glob("*.md"))
        assert len(l3_files) == 1
        assert (l3_dir / "final.md").exists()

    def test_persist_simple_summary_creates_l3_file(
        self,
        fake_collection: _FakeCollection,
        memory_root: Path,
    ) -> None:
        """Test that a simple summary creates just L3/final.md."""
        result = SummaryResult(
            level=SummaryLevel.STANDARD,
            summary="A standard paragraph summary.",
            hierarchical=None,
            input_tokens=1000,
            output_tokens=50,
            compression_ratio=0.05,
        )

        ids = persist_hierarchical_summary(
            fake_collection,
            memory_root=memory_root,
            conversation_id="simple-conv",
            summary_result=result,
        )

        assert len(ids) == 1

        # Check file exists (note: _slugify converts - to - not _)
        entries_dir = memory_root / "entries" / "simple-conv"
        l3_file = entries_dir / "summaries" / "L3" / "final.md"
        assert l3_file.exists()

        # Check content has YAML front matter
        content = l3_file.read_text(encoding="utf-8")
        assert "---" in content
        assert "level: 3" in content
        assert "A standard paragraph summary." in content

    def test_persist_deletes_old_summaries(
        self,
        fake_collection: _FakeCollection,
        memory_root: Path,
    ) -> None:
        """Test that persisting new summary deletes old summary files."""
        # Create first summary
        result1 = SummaryResult(
            level=SummaryLevel.STANDARD,
            summary="First summary.",
            hierarchical=None,
            input_tokens=1000,
            output_tokens=50,
            compression_ratio=0.05,
        )

        persist_hierarchical_summary(
            fake_collection,
            memory_root=memory_root,
            conversation_id="conv",
            summary_result=result1,
        )

        entries_dir = memory_root / "entries" / "conv"
        first_file = entries_dir / "summaries" / "L3" / "final.md"
        assert first_file.exists()
        assert "First summary." in first_file.read_text()

        # Create second summary (should replace first)
        result2 = SummaryResult(
            level=SummaryLevel.STANDARD,
            summary="Second summary.",
            hierarchical=None,
            input_tokens=1000,
            output_tokens=50,
            compression_ratio=0.05,
        )

        persist_hierarchical_summary(
            fake_collection,
            memory_root=memory_root,
            conversation_id="conv",
            summary_result=result2,
        )

        # First summary should be moved to deleted
        assert first_file.exists()
        assert "Second summary." in first_file.read_text()

        # Old summary should be in deleted folder
        deleted_dir = memory_root / "entries" / "deleted" / "conv" / "summaries"
        assert deleted_dir.exists()


class TestAdaptiveSummarizerLevelDetermination:
    """Test that AdaptiveSummarizer correctly determines summary levels."""

    @pytest.fixture
    def summarizer(self) -> AdaptiveSummarizer:
        """Create an AdaptiveSummarizer instance."""
        return AdaptiveSummarizer(
            openai_base_url="http://localhost:8000/v1",
            model="test-model",
        )

    def test_very_short_content_is_none(self, summarizer: AdaptiveSummarizer) -> None:
        """Test that content under 100 tokens gets NONE level."""
        level = summarizer.determine_level(50)
        assert level == SummaryLevel.NONE

    def test_short_content_is_brief(self, summarizer: AdaptiveSummarizer) -> None:
        """Test that 100-500 token content gets BRIEF level."""
        level = summarizer.determine_level(300)
        assert level == SummaryLevel.BRIEF

    def test_medium_content_is_standard(self, summarizer: AdaptiveSummarizer) -> None:
        """Test that 500-3000 token content gets STANDARD level."""
        level = summarizer.determine_level(1500)
        assert level == SummaryLevel.STANDARD

    def test_long_content_is_detailed(self, summarizer: AdaptiveSummarizer) -> None:
        """Test that 3000-15000 token content gets DETAILED level."""
        level = summarizer.determine_level(8000)
        assert level == SummaryLevel.DETAILED

    def test_very_long_content_is_hierarchical(self, summarizer: AdaptiveSummarizer) -> None:
        """Test that content over 15000 tokens gets HIERARCHICAL level."""
        level = summarizer.determine_level(25000)
        assert level == SummaryLevel.HIERARCHICAL


class TestSummarizeContentFunction:
    """Test the summarize_content function from _ingest."""

    @pytest.mark.asyncio
    async def test_summarize_content_creates_result(self) -> None:
        """Test that summarize_content returns a valid SummaryResult."""
        with patch.object(AdaptiveSummarizer, "summarize") as mock_summarize:
            mock_result = SummaryResult(
                level=SummaryLevel.STANDARD,
                summary="Mocked summary.",
                hierarchical=None,
                input_tokens=1000,
                output_tokens=50,
                compression_ratio=0.05,
            )
            mock_summarize.return_value = mock_result

            result = await summarize_content(
                content="Some content to summarize " * 100,
                openai_base_url="http://localhost:8000/v1",
                api_key=None,
                model="test-model",
            )

            assert result.level == SummaryLevel.STANDARD
            assert result.summary == "Mocked summary."
