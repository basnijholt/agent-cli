"""Demonstrate the summarizer on texts of varying lengths from the internet.

This script fetches content of different sizes and shows how the adaptive
summarizer automatically selects the appropriate strategy (BRIEF, STANDARD,
DETAILED, or HIERARCHICAL) based on content length.

Usage:
    python examples/summarizer_demo.py

    # Test specific levels only
    python examples/summarizer_demo.py --level brief
    python examples/summarizer_demo.py --level standard
    python examples/summarizer_demo.py --level detailed
    python examples/summarizer_demo.py --level hierarchical

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
    SummaryLevel,
    SummaryResult,
    summarize,
)

# Defaults for local AI setup (same as aijournal_poc.py)
DEFAULT_BASE_URL = "http://192.168.1.143:9292/v1"
DEFAULT_MODEL = "gpt-oss-high:20b"


@dataclass
class TextSample:
    """A sample text for testing the summarizer."""

    name: str
    description: str
    url: str
    expected_level: SummaryLevel
    content_type: str = "general"
    # If URL fetch fails, use this fallback
    fallback_content: str | None = None


# Thresholds from adaptive.py:
# NONE: < 100 tokens
# BRIEF: 100-500 tokens
# STANDARD: 500-3000 tokens
# DETAILED: 3000-15000 tokens
# HIERARCHICAL: > 15000 tokens

# Sample texts of varying lengths to demonstrate different summarization levels
SAMPLES: list[TextSample] = [
    TextSample(
        name="Brief - Short News Article",
        description="~150-400 tokens - triggers BRIEF level (100-500 token range)",
        url="https://httpbin.org/json",  # Returns small JSON we'll convert to text
        expected_level=SummaryLevel.BRIEF,
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
        name="Standard - Technology Article",
        description="~800-2000 tokens - triggers STANDARD level (500-3000 token range)",
        url="https://en.wikipedia.org/api/rest_v1/page/summary/Artificial_intelligence",
        expected_level=SummaryLevel.STANDARD,
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
        name="Detailed - Full Article",
        description="~4000-10000 tokens - triggers DETAILED level (3000-15000 token range)",
        url="https://en.wikipedia.org/api/rest_v1/page/mobile-html/Machine_learning",
        expected_level=SummaryLevel.DETAILED,
        content_type="document",
        fallback_content=None,  # We'll generate synthetic content
    ),
    TextSample(
        name="Hierarchical - Long Document",
        description="~16000+ tokens - triggers HIERARCHICAL level (>15000 tokens)",
        url="https://www.gutenberg.org/cache/epub/84/pg84.txt",  # Frankenstein (truncated)
        expected_level=SummaryLevel.HIERARCHICAL,
        content_type="document",
        fallback_content=None,  # We'll generate synthetic content (~16K tokens)
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


async def fetch_content(sample: TextSample, client: httpx.AsyncClient) -> str:  # noqa: PLR0912
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

        # Check if content is too short for expected level
        min_words_for_level = {
            SummaryLevel.BRIEF: 80,  # Need ~100 tokens
            SummaryLevel.STANDARD: 400,  # Need ~500 tokens
            SummaryLevel.DETAILED: 2500,  # Need ~3000 tokens
            SummaryLevel.HIERARCHICAL: 12000,  # Need ~15000 tokens
        }
        min_words = min_words_for_level.get(sample.expected_level, 50)

        if len(content.split()) < min_words:
            print(f"  📎 Fetched content too short ({len(content.split())} words), using fallback")
            if sample.fallback_content:
                content = sample.fallback_content
            else:
                target_tokens = {
                    SummaryLevel.BRIEF: 300,
                    SummaryLevel.STANDARD: 1500,
                    SummaryLevel.DETAILED: 8000,
                    SummaryLevel.HIERARCHICAL: 16000,  # Keep manageable for demo
                }
                content = generate_synthetic_content(
                    target_tokens.get(sample.expected_level, 1000),
                )

        # For HIERARCHICAL, truncate very long content to keep demo fast
        # but ensure we stay above 15000 tokens (~13000 words)
        if sample.expected_level == SummaryLevel.HIERARCHICAL:
            words = content.split()
            # ~16000 tokens ≈ 13500 words (need >15000 tokens for HIERARCHICAL)
            if len(words) > 13500:  # noqa: PLR2004
                content = " ".join(words[:13500])
                print("  📎 Truncated to ~13500 words for faster demo")

        return content.strip()

    except Exception as e:
        print(f"  ⚠️  Failed to fetch URL: {e}")

        if sample.fallback_content:
            return sample.fallback_content.strip()

        # Generate synthetic content for the expected level
        target_tokens = {
            SummaryLevel.BRIEF: 300,
            SummaryLevel.STANDARD: 1500,
            SummaryLevel.DETAILED: 8000,
            SummaryLevel.HIERARCHICAL: 16000,  # Keep manageable for demo
        }
        return generate_synthetic_content(target_tokens.get(sample.expected_level, 1000))


def print_result(sample: TextSample, result: SummaryResult, content: str) -> None:
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

    # Summarization result
    level_emoji = {
        SummaryLevel.NONE: "⏭️",
        SummaryLevel.BRIEF: "📝",
        SummaryLevel.STANDARD: "📄",
        SummaryLevel.DETAILED: "📚",
        SummaryLevel.HIERARCHICAL: "🏗️",
    }
    print("\n🎯 Summarization Result:")
    print(f"   Level: {level_emoji.get(result.level, '❓')} {result.level.name}")
    print(f"   Expected: {sample.expected_level.name}")
    print(f"   Match: {'✅' if result.level == sample.expected_level else '⚠️'}")
    print(f"   Output tokens: {result.output_tokens:,}")
    print(f"   Compression: {result.compression_ratio:.1%}")

    # Summary content
    if result.summary:
        print("\n📝 Summary:")
        wrapped = textwrap.fill(
            result.summary,
            width=68,
            initial_indent="   ",
            subsequent_indent="   ",
        )
        print(wrapped)

    # Hierarchical details if present
    if result.hierarchical:
        h = result.hierarchical
        print("\n🏗️  Hierarchical Structure:")
        print(f"   L1 chunks: {len(h.l1_summaries)}")
        print(f"   L2 groups: {len(h.l2_summaries)}")
        if h.l2_summaries:
            print(f"   L2 preview: {h.l2_summaries[0][:100]}...")
        print("\n   L3 Final Summary:")
        wrapped = textwrap.fill(
            h.l3_summary,
            width=68,
            initial_indent="   ",
            subsequent_indent="   ",
        )
        print(wrapped)


async def run_demo(
    level_filter: str | None = None,
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
        chunk_size=3000,
        max_concurrent_chunks=3,
        timeout=120.0,  # Longer timeout for local models
    )

    # Filter samples if requested
    samples = SAMPLES
    if level_filter:
        level_map = {
            "brief": SummaryLevel.BRIEF,
            "standard": SummaryLevel.STANDARD,
            "detailed": SummaryLevel.DETAILED,
            "hierarchical": SummaryLevel.HIERARCHICAL,
        }
        target_level = level_map.get(level_filter.lower())
        if target_level:
            samples = [s for s in SAMPLES if s.expected_level == target_level]
            print(f"\n🔍 Filtering to {level_filter.upper()} level only")

    async with httpx.AsyncClient() as client:
        for sample in samples:
            print(f"\n⏳ Processing: {sample.name}...")

            # Fetch content
            content = await fetch_content(sample, client)

            try:
                # Summarize
                result = await summarize(
                    content=content,
                    config=config,
                    content_type=sample.content_type,
                )

                # Display results
                print_result(sample, result, content)

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
          python examples/summarizer_demo.py --level standard
          python examples/summarizer_demo.py --model "llama3.1:8b" --base-url "http://localhost:11434/v1"
        """),
    )

    parser.add_argument(
        "--level",
        choices=["brief", "standard", "detailed", "hierarchical"],
        help="Only test a specific summarization level",
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

    asyncio.run(
        run_demo(
            level_filter=args.level,
            model=args.model,
            base_url=args.base_url,
        ),
    )


if __name__ == "__main__":
    main()
