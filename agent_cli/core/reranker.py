"""Shared ONNX Cross-Encoder for reranking (used by both RAG and Memory)."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def _download_onnx_model(model_name: str, onnx_filename: str) -> str:
    """Download the ONNX model, favoring the common `onnx/` folder layout."""
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    if "/" in onnx_filename:
        return hf_hub_download(repo_id=model_name, filename=onnx_filename)

    try:
        return hf_hub_download(repo_id=model_name, filename=onnx_filename, subfolder="onnx")
    except Exception as first_error:
        LOGGER.debug(
            "ONNX file not found under onnx/ for %s: %s. Falling back to repo root.",
            model_name,
            first_error,
        )
        try:
            return hf_hub_download(repo_id=model_name, filename=onnx_filename)
        except Exception as second_error:
            LOGGER.exception(
                "Failed to download ONNX model %s (filename=%s)",
                model_name,
                onnx_filename,
                exc_info=second_error,
            )
            raise


class OnnxCrossEncoder:
    """A lightweight CrossEncoder using ONNX Runtime."""

    def __init__(
        self,
        model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2",
        onnx_filename: str = "model.onnx",
    ) -> None:
        """Initialize the ONNX CrossEncoder."""
        from onnxruntime import InferenceSession  # noqa: PLC0415
        from transformers import AutoTokenizer  # noqa: PLC0415

        self.model_name = model_name

        # Download model if needed
        LOGGER.info("Loading ONNX model: %s", model_name)
        model_path = _download_onnx_model(model_name, onnx_filename)

        self.session = InferenceSession(model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def predict(
        self,
        pairs: list[tuple[str, str]],
        batch_size: int = 32,
    ) -> list[float]:
        """Predict relevance scores for query-document pairs."""
        import numpy as np  # noqa: PLC0415

        if not pairs:
            return []

        all_scores = []

        # Process in batches
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            queries = [q for q, d in batch]
            docs = [d for q, d in batch]

            # Tokenize
            inputs = self.tokenizer(
                queries,
                docs,
                padding=True,
                truncation=True,
                return_tensors="np",
                max_length=512,
            )

            # ONNX Input
            # Check what inputs the model expects. usually input_ids, attention_mask, token_type_ids
            # specific models might not need token_type_ids
            ort_inputs = {
                "input_ids": inputs["input_ids"].astype(np.int64),
                "attention_mask": inputs["attention_mask"].astype(np.int64),
            }
            if "token_type_ids" in inputs:
                ort_inputs["token_type_ids"] = inputs["token_type_ids"].astype(np.int64)

            # Run inference
            logits = self.session.run(None, ort_inputs)[0]

            # Extract scores (usually shape [batch, 1] or [batch])
            batch_scores = logits.flatten() if logits.ndim > 1 else logits

            all_scores.extend(batch_scores.tolist())

        return all_scores


def get_reranker_model(
    model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2",
) -> OnnxCrossEncoder:
    """Load the CrossEncoder model."""
    return OnnxCrossEncoder(model_name)


def predict_relevance(
    model: OnnxCrossEncoder,
    pairs: list[tuple[str, str]],
) -> list[float]:
    """Predict relevance scores for query-document pairs."""
    return model.predict(pairs)
