"""Tests for memory filter conversion utilities."""

from agent_cli.memory._filters import to_chroma_where


def test_none_input() -> None:
    """Return None for None input."""
    assert to_chroma_where(None) is None


def test_empty_dict() -> None:
    """Return None for empty dict."""
    assert to_chroma_where({}) is None


def test_simple_equality() -> None:
    """Convert simple equality to $eq operator."""
    result = to_chroma_where({"role": "user"})
    assert result == {"role": {"$eq": "user"}}


def test_multiple_equalities() -> None:
    """Combine multiple equalities with $and."""
    result = to_chroma_where({"role": "user", "conversation_id": "test"})
    assert result == {
        "$and": [
            {"role": {"$eq": "user"}},
            {"conversation_id": {"$eq": "test"}},
        ],
    }


def test_operator_eq() -> None:
    """Handle explicit eq operator."""
    result = to_chroma_where({"role": {"eq": "user"}})
    assert result == {"role": {"$eq": "user"}}


def test_operator_ne() -> None:
    """Handle ne (not equal) operator."""
    result = to_chroma_where({"role": {"ne": "summary"}})
    assert result == {"role": {"$ne": "summary"}}


def test_operator_gt() -> None:
    """Handle gt (greater than) operator."""
    result = to_chroma_where({"score": {"gt": 0.5}})
    assert result == {"score": {"$gt": 0.5}}


def test_operator_gte() -> None:
    """Handle gte (greater than or equal) operator."""
    result = to_chroma_where({"created_at": {"gte": "2024-01-01"}})
    assert result == {"created_at": {"$gte": "2024-01-01"}}


def test_operator_lt() -> None:
    """Handle lt (less than) operator."""
    result = to_chroma_where({"score": {"lt": 0.5}})
    assert result == {"score": {"$lt": 0.5}}


def test_operator_lte() -> None:
    """Handle lte (less than or equal) operator."""
    result = to_chroma_where({"created_at": {"lte": "2024-12-31"}})
    assert result == {"created_at": {"$lte": "2024-12-31"}}


def test_operator_in() -> None:
    """Handle in operator."""
    result = to_chroma_where({"role": {"in": ["user", "assistant"]}})
    assert result == {"role": {"$in": ["user", "assistant"]}}


def test_operator_nin() -> None:
    """Handle nin (not in) operator."""
    result = to_chroma_where({"role": {"nin": ["summary", "system"]}})
    assert result == {"role": {"$nin": ["summary", "system"]}}


def test_operator_already_prefixed() -> None:
    """Handle operators that already have $ prefix."""
    result = to_chroma_where({"role": {"$ne": "summary"}})
    assert result == {"role": {"$ne": "summary"}}


def test_or_single_condition() -> None:
    """Handle $or with single condition (simplify to no $or)."""
    result = to_chroma_where({"$or": [{"role": "user"}]})
    assert result == {"role": {"$eq": "user"}}


def test_or_multiple_conditions() -> None:
    """Handle $or with multiple conditions."""
    result = to_chroma_where({"$or": [{"role": "user"}, {"role": "assistant"}]})
    assert result == {
        "$or": [
            {"role": {"$eq": "user"}},
            {"role": {"$eq": "assistant"}},
        ],
    }


def test_or_with_operators() -> None:
    """Handle $or with operator conditions."""
    result = to_chroma_where(
        {
            "$or": [
                {"score": {"gte": 0.8}},
                {"role": "system"},
            ],
        },
    )
    assert result == {
        "$or": [
            {"score": {"$gte": 0.8}},
            {"role": {"$eq": "system"}},
        ],
    }


def test_combined_or_and_regular() -> None:
    """Handle $or combined with regular conditions."""
    result = to_chroma_where(
        {
            "conversation_id": "test",
            "$or": [{"role": "user"}, {"role": "assistant"}],
        },
    )
    assert result == {
        "$and": [
            {"conversation_id": {"$eq": "test"}},
            {"$or": [{"role": {"$eq": "user"}}, {"role": {"$eq": "assistant"}}]},
        ],
    }


def test_skip_unsupported_operators() -> None:
    """Skip unsupported logical operators like $not."""
    result = to_chroma_where({"$not": {"role": "summary"}, "conversation_id": "test"})
    assert result == {"conversation_id": {"$eq": "test"}}


def test_empty_or() -> None:
    """Handle empty $or list."""
    result = to_chroma_where({"$or": []})
    assert result is None
