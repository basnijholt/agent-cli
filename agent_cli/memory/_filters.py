"""Filter conversion utilities for ChromaDB."""

from __future__ import annotations

from typing import Any


def _convert_condition(key: str, value: Any) -> dict[str, Any] | None:
    """Convert a single filter condition to ChromaDB format."""
    if isinstance(value, dict):
        # Operator dict: {"gte": 10} → {"$gte": 10}
        for op, val in value.items():
            chroma_op = f"${op}" if not op.startswith("$") else op
            return {key: {chroma_op: val}}
        return None
    # Simple equality
    return {key: {"$eq": value}}


def _process_or(conditions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Process $or conditions."""
    or_conditions = []
    for cond in conditions:
        for sub_key, sub_val in cond.items():
            converted = _convert_condition(sub_key, sub_val)
            if converted:
                or_conditions.append(converted)
    if len(or_conditions) > 1:
        return {"$or": or_conditions}
    if or_conditions:
        return or_conditions[0]
    return None


def to_chroma_where(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert universal filter format to ChromaDB WHERE clause.

    Supports:
    - Simple equality: {"role": "user"} → {"role": {"$eq": "user"}}
    - Operators: {"created_at": {"gte": "2024-01-01"}} → {"created_at": {"$gte": "2024-01-01"}}
    - Logical OR: {"$or": [{"role": "user"}, {"role": "assistant"}]}

    Operators: eq, ne, gt, gte, lt, lte, in, nin
    """
    if not filters:
        return None

    processed: list[dict[str, Any]] = []
    for key, value in filters.items():
        if key == "$or":
            or_result = _process_or(value)
            if or_result:
                processed.append(or_result)
        elif not key.startswith("$"):
            converted = _convert_condition(key, value)
            if converted:
                processed.append(converted)

    if not processed:
        return None
    if len(processed) == 1:
        return processed[0]
    return {"$and": processed}
