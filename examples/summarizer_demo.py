"""Demonstrate the simplified summarizer on texts of varying lengths.

This script fetches content of different sizes and shows how the adaptive
summarizer compresses content to fit different target token counts or ratios.

Usage:
    python examples/summarizer_demo.py

    # Test with specific target ratio
    python examples/summarizer_demo.py --target-ratio 0.2

    # Test with specific target token count
    python examples/summarizer_demo.py --target-tokens 500

    # Use a different model
    python examples/summarizer_demo.py --model "gpt-4o-mini"
"""  # noqa: INP001

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import textwrap
import traceback
from dataclasses import dataclass

import httpx

from agent_cli.summarizer import (
    SummarizerConfig,
    SummaryResult,
    summarize,
)

# Defaults for local AI setup
DEFAULT_BASE_URL = "http://192.168.1.143:9292/v1"
DEFAULT_MODEL = "gpt-oss-high:20b"


@dataclass
class TextSample:
    """A sample text for testing the summarizer."""

    name: str
    description: str
    url: str
    content_type: str = "general"
    # If URL fetch fails, use this fallback
    fallback_content: str | None = None


# Sample texts of varying lengths to demonstrate summarization
SAMPLES: list[TextSample] = [
    TextSample(
        name="Short News Article",
        description="~150-400 tokens - demonstrates small content handling",
        url="https://httpbin.org/json",  # Returns small JSON we'll convert to text
        fallback_content="""
        Breaking News: Scientists at the Marine Biology Institute have made a
        groundbreaking discovery in the Mariana Trench. A new species of deep-sea
        fish, dubbed "Pseudoliparis swirei," has been found surviving at depths
        exceeding 8,000 meters, making it one of the deepest-living fish ever
        documented.

        The research team, led by Dr. Sarah Chen from the University of Washington,
        used advanced unmanned submersibles equipped with high-resolution cameras
        and collection apparatus. The expedition lasted three months and covered
        multiple dive sites across the western Pacific.

        "This discovery fundamentally changes our understanding of life in extreme
        environments," Dr. Chen stated in a press conference. "The adaptations
        these fish have developed to survive crushing pressures and near-freezing
        temperatures are remarkable."

        The fish displays several unique characteristics including translucent skin,
        specialized proteins that prevent cellular damage under pressure, and an
        unusual metabolism that allows survival with minimal oxygen. Scientists
        believe studying these adaptations could lead to breakthroughs in medicine
        and materials science.

        The finding has been published in the journal Nature and has already
        generated significant interest from the scientific community worldwide.
        Further expeditions are planned to study the species in its natural habitat.
        """,
    ),
    TextSample(
        name="Technology Article",
        description="~800-2000 tokens - demonstrates medium content",
        url="https://en.wikipedia.org/api/rest_v1/page/summary/Artificial_intelligence",
        content_type="document",
        fallback_content="""
        Artificial intelligence (AI) is the intelligence of machines or software,
        as opposed to the intelligence of humans or other animals. It is a field
        of computer science that develops and studies intelligent machines. The
        field encompasses a wide range of approaches and technologies.

        AI research has been defined as the field of study of intelligent agents,
        which refers to any system that perceives its environment and takes actions
        that maximize its chances of achieving its goals. This definition emphasizes
        the practical aspects of building systems that can operate effectively.

        The term "artificial intelligence" has been used to describe machines that
        mimic cognitive functions that humans associate with the human mind, such
        as learning and problem solving. As machines become increasingly capable,
        tasks considered to require "intelligence" are often removed from the
        definition of AI, a phenomenon known as the AI effect.

        History of Artificial Intelligence

        The field of AI research was founded at a workshop held on the campus of
        Dartmouth College during the summer of 1956. The attendees became the
        founders and leaders of AI research. They and their students produced
        programs that the press described as astonishing.

        Early AI research in the 1950s explored topics like problem solving and
        symbolic methods. In the 1960s, the US Department of Defense took interest
        and began training computers to mimic basic human reasoning. DARPA completed
        street mapping projects in the 1970s and produced intelligent personal
        assistants in 2003, long before Siri, Alexa or Cortana.

        Modern AI Approaches

        Modern AI techniques have become pervasive and include machine learning,
        deep learning, natural language processing, computer vision, robotics,
        and autonomous systems. These technologies power everything from search
        engines to self-driving cars.

        Machine learning is a subset of AI that enables systems to learn and improve
        from experience without being explicitly programmed. Deep learning uses
        neural networks with many layers to analyze various factors of data.

        Neural networks are computing systems inspired by biological neural networks.
        They consist of interconnected nodes that process information using
        connectionist approaches to computation. Modern neural networks can have
        millions or billions of parameters.

        Applications of AI

        AI applications are transforming industries including healthcare, finance,
        transportation, and entertainment. In healthcare, AI helps diagnose diseases
        and develop new treatments. In finance, AI powers fraud detection and
        algorithmic trading.

        Autonomous vehicles use AI to perceive their environment and make driving
        decisions. Virtual assistants use natural language processing to understand
        and respond to user queries. Recommendation systems use AI to suggest
        content based on user preferences.

        Ethical Considerations

        The field was founded on the assumption that human intelligence can be
        so precisely described that a machine can be made to simulate it. This
        raised philosophical arguments about the mind and the ethical consequences
        of creating artificial beings endowed with human-like intelligence.

        Major concerns include job displacement, algorithmic bias, privacy violations,
        and the potential for misuse. Researchers and policymakers are working to
        develop frameworks for responsible AI development and deployment.

        The future of AI holds both tremendous promise and significant challenges.
        As these systems become more capable, society must grapple with questions
        about control, accountability, and the nature of intelligence itself.
        """,
    ),
    TextSample(
        name="Full Article",
        description="~4000-10000 tokens - demonstrates large content with chunking",
        url="https://en.wikipedia.org/api/rest_v1/page/mobile-html/Machine_learning",
        content_type="document",
        fallback_content=None,  # We'll generate synthetic content
    ),
]


def generate_synthetic_content(target_tokens: int, topic: str = "technology") -> str:
    """Generate synthetic content for testing when URLs fail."""
    # Each paragraph is roughly 50-100 tokens
    paragraphs = [
        f"Section on {topic} - Part {{i}}: This section explores various aspects "
        f"of {topic} and its implications for modern society. The development of "
        f"new technologies continues to reshape how we live and work. Researchers "
        f"have made significant progress in understanding the fundamentals.",
        f"The history of {topic} spans many decades of innovation. Early pioneers "
        f"laid the groundwork for current advancements. Their contributions remain "
        f"relevant today as we build upon established foundations.",
        f"Current applications of {topic} include healthcare, transportation, and "
        f"communication. These sectors have seen dramatic improvements in efficiency "
        f"and capability. Future developments promise even greater transformations.",
        f"Challenges in {topic} include ethical considerations, resource constraints, "
        f"and technical limitations. Addressing these requires collaboration across "
        f"disciplines. Solutions often emerge from unexpected directions.",
        f"The future of {topic} looks promising with continued investment and research. "
        f"Emerging trends suggest new possibilities. Stakeholders must prepare for "
        f"rapid change while maintaining focus on beneficial outcomes.",
    ]

    result = []
    tokens_per_para = 75  # approximate
    needed_paragraphs = target_tokens // tokens_per_para + 1

    for i in range(needed_paragraphs):
        para = paragraphs[i % len(paragraphs)].format(i=i + 1)
        result.append(para)

    return "\n\n".join(result)


async def fetch_content(sample: TextSample, client: httpx.AsyncClient) -> str:
    """Fetch content from URL or use fallback."""
    try:
        # Add User-Agent header to avoid 403 errors from some sites
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; SummarizerDemo/1.0)",
        }
        response = await client.get(
            sample.url,
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        )
        response.raise_for_status()

        content = response.text

        # Handle Wikipedia API JSON responses
        if "wikipedia.org/api" in sample.url:
            try:
                data = json.loads(content)
                if "extract" in data:
                    content = data["extract"]
                elif "text" in data:
                    content = data["text"]
            except json.JSONDecodeError:
                pass

        # For httpbin JSON, create a readable summary
        if "httpbin.org/json" in sample.url:
            content = sample.fallback_content or ""

        # Strip HTML tags if present
        if "<" in content and ">" in content:
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

        # Check if content is too short
        min_words = 80
        if len(content.split()) < min_words:
            print(f"  📎 Fetched content too short ({len(content.split())} words), using fallback")
            content = sample.fallback_content or generate_synthetic_content(1500)

        # For very long content, truncate to keep demo fast
        words = content.split()
        if len(words) > 13500:  # noqa: PLR2004
            content = " ".join(words[:13500])
            print("  📎 Truncated to ~13500 words for faster demo")

        return content.strip()

    except Exception as e:
        print(f"  ⚠️  Failed to fetch URL: {e}")

        if sample.fallback_content:
            return sample.fallback_content.strip()

        # Generate synthetic content
        return generate_synthetic_content(1500)


def print_result(
    sample: TextSample,
    result: SummaryResult,
    content: str,
    target_tokens: int | None,
    target_ratio: float | None,
) -> None:
    """Print a formatted summary result."""
    print("\n" + "=" * 70)
    print(f"📄 {sample.name}")
    print(f"   {sample.description}")
    print("=" * 70)

    # Input stats
    word_count = len(content.split())
    print("\n📊 Input Statistics:")
    print(f"   Words: {word_count:,}")
    print(f"   Tokens: {result.input_tokens:,}")
    print(f"   Content type: {sample.content_type}")

    # Target info
    print("\n🎯 Target:")
    if target_ratio is not None:
        print(f"   Ratio: {target_ratio:.0%} of input")
        print(f"   Calculated target: ~{int(result.input_tokens * target_ratio):,} tokens")
    elif target_tokens is not None:
        print(f"   Tokens: {target_tokens:,}")
    else:
        print("   Default: 3000 tokens (LangChain default)")

    # Result info
    print("\n📝 Result:")
    if result.summary == content:
        print("   Status: ⏭️  Content already fits target (returned as-is)")
    elif result.collapse_depth > 0:
        print(f"   Status: 🔄 Map-reduce summarization (collapse depth: {result.collapse_depth})")
    else:
        print("   Status: 📝 Single-pass summarization")

    print(f"   Output tokens: {result.output_tokens:,}")
    print(f"   Compression: {result.compression_ratio:.1%}")

    # Summary content
    if result.summary and result.summary != content:
        print("\n📝 Summary:")
        wrapped = textwrap.fill(
            result.summary,
            width=68,
            initial_indent="   ",
            subsequent_indent="   ",
        )
        # Only show first ~500 chars of summary
        if len(wrapped) > 600:  # noqa: PLR2004
            wrapped = wrapped[:600] + "..."
        print(wrapped)


async def run_demo(
    target_tokens: int | None = None,
    target_ratio: float | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> None:
    """Run the summarizer demo."""
    # Configuration
    actual_base_url = base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    actual_model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    api_key = os.environ.get("OPENAI_API_KEY", "not-needed-for-local")

    print("🔧 Configuration:")
    print(f"   Base URL: {actual_base_url}")
    print(f"   Model: {actual_model}")

    config = SummarizerConfig(
        openai_base_url=actual_base_url,
        model=actual_model,
        api_key=api_key,
        chunk_size=2048,  # BOOOOKSCORE default
        max_concurrent_chunks=3,
        timeout=120.0,  # Longer timeout for local models
    )

    async with httpx.AsyncClient() as client:
        for sample in SAMPLES:
            print(f"\n⏳ Processing: {sample.name}...")

            # Fetch content
            content = await fetch_content(sample, client)

            try:
                # Summarize with specified target
                result = await summarize(
                    content=content,
                    config=config,
                    target_tokens=target_tokens,
                    target_ratio=target_ratio,
                    content_type=sample.content_type,
                )

                # Display results
                print_result(sample, result, content, target_tokens, target_ratio)

            except Exception as e:
                print(f"\n❌ Error summarizing {sample.name}: {e}")
                traceback.print_exc()

    print("\n" + "=" * 70)
    print("✅ Demo complete!")
    print("=" * 70)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Demonstrate adaptive summarization on texts of varying lengths",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python examples/summarizer_demo.py
          python examples/summarizer_demo.py --target-ratio 0.2
          python examples/summarizer_demo.py --target-tokens 500
          python examples/summarizer_demo.py --model "llama3.1:8b" --base-url "http://localhost:11434/v1"
        """),
    )

    parser.add_argument(
        "--target-ratio",
        type=float,
        help="Target ratio for compression (e.g., 0.2 = compress to 20%%)",
    )
    parser.add_argument(
        "--target-tokens",
        type=int,
        help="Target token count for summary",
    )
    parser.add_argument(
        "--model",
        help=f"Model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--base-url",
        help=f"OpenAI-compatible API base URL (default: {DEFAULT_BASE_URL})",
    )

    args = parser.parse_args()

    if args.target_ratio is not None and args.target_tokens is not None:
        parser.error("Cannot specify both --target-ratio and --target-tokens")

    asyncio.run(
        run_demo(
            target_tokens=args.target_tokens,
            target_ratio=args.target_ratio,
            model=args.model,
            base_url=args.base_url,
        ),
    )


if __name__ == "__main__":
    main()
