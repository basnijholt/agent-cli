"""Tests for RAG retriever."""

from unittest.mock import MagicMock, patch

from agent_cli.core import reranker
from agent_cli.rag import _retriever


def test_get_reranker_model_installed() -> None:
    """Test loading reranker when installed."""
    with patch("agent_cli.core.reranker.OnnxCrossEncoder") as mock_ce:
        reranker.get_reranker_model()
        mock_ce.assert_called_once()


def test_search_context() -> None:
    """Test searching context."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()

    # Mock query results
    mock_collection.query.return_value = {
        "documents": [["doc1", "doc2"]],
        "metadatas": [
            [
                {"source": "s1", "file_path": "p1", "chunk_id": 0},
                {"source": "s2", "file_path": "p2", "chunk_id": 1},
            ],
        ],
    }

    # Mock reranker scores
    mock_reranker.predict.return_value = [-1.0, 5.0]

    result = _retriever.search_context(mock_collection, mock_reranker, "query", top_k=1)

    # Should return doc2 because it has higher score
    assert "doc2" in result.context
    assert "doc1" not in result.context
    assert len(result.sources) == 1
    assert result.sources[0].path == "p2"


def test_search_context_empty() -> None:
    """Test search with no results."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()

    mock_collection.query.return_value = {"documents": []}

    result = _retriever.search_context(mock_collection, mock_reranker, "query")

    assert result.context == ""
    assert result.sources == []
