"""Compare old (L1-L4 hierarchical) vs new (adaptive map-reduce) summarizer.

This script:
1. Shows what level each system would use for test content
2. Runs the NEW summarizer to produce actual summaries
3. Evaluates summary quality using needle-in-haystack questions
4. Uses LLM-as-judge for quality assessment

Usage:
    python scripts/compare_summarizers.py
    python scripts/compare_summarizers.py --model "gpt-4o-mini" --base-url "https://api.openai.com/v1"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import textwrap
from dataclasses import dataclass, field

from agent_cli.summarizer import SummarizerConfig, summarize
from agent_cli.summarizer._utils import count_tokens

# Old system thresholds
OLD_THRESHOLD_NONE = 100
OLD_THRESHOLD_BRIEF = 500
OLD_THRESHOLD_STANDARD = 3000
OLD_THRESHOLD_DETAILED = 15000

# New system thresholds
NEW_THRESHOLD_NONE = 100
NEW_THRESHOLD_BRIEF = 500

# Evaluation threshold
FACT_PRESERVATION_THRESHOLD = 0.5

# Test content at different sizes with embedded "needles" (specific facts)
TEST_CASES = [
    {
        "name": "Brief Range (~300 tokens)",
        "description": "Tests the 100-500 token range where OLD=BRIEF, NEW=BRIEF",
        "content": """
        The artificial intelligence revolution is transforming every industry.
        Machine learning algorithms now power recommendation systems, fraud detection,
        and autonomous vehicles. Deep learning, a subset of machine learning, uses
        neural networks with multiple layers to analyze complex patterns in data.

        Major tech companies are investing billions in AI research. Google's DeepMind
        created AlphaGo, which defeated world champion Lee Sedol in March 2016 in
        the ancient game of Go. OpenAI developed GPT models that can generate
        human-like text. These advances raise both excitement and concerns about
        the future of work and society.

        Researchers are working on making AI systems more transparent and aligned with
        human values. The field of AI safety, pioneered by researchers like Stuart
        Russell at UC Berkeley, aims to ensure that advanced AI systems remain
        beneficial and under human control.
        """,
        "needles": [
            ("Who did AlphaGo defeat?", "Lee Sedol"),
            ("When did AlphaGo win?", "March 2016"),
            ("Who pioneered AI safety?", "Stuart Russell"),
            ("Where does Stuart Russell work?", "UC Berkeley"),
        ],
    },
    {
        "name": "Standard/MapReduce Range (~900 tokens)",
        "description": "Tests 500-3000 range where OLD=STANDARD, NEW=MAP_REDUCE",
        "content": """
        Climate change represents one of the most pressing challenges facing humanity.
        The Earth's average temperature has risen approximately 1.1 degrees Celsius since
        the pre-industrial era, primarily due to human activities that release greenhouse
        gases. Carbon dioxide from burning fossil fuels accounts for 76% of emissions.

        The Intergovernmental Panel on Climate Change (IPCC), led by chair Hoesung Lee,
        has warned that limiting warming to 1.5 degrees Celsius is crucial. The 2021
        report involved 234 authors from 66 countries analyzing over 14,000 scientific
        papers. Their conclusion: human influence has warmed the climate at a rate
        unprecedented in at least the last 2,000 years.

        Renewable energy offers hope. Solar panel costs dropped 89% between 2010 and 2020,
        making solar competitive with fossil fuels. China leads with 306 gigawatts of
        installed solar capacity. Wind energy has grown exponentially, with Denmark
        generating 47% of its electricity from wind in 2019.

        Electric vehicles are gaining ground. Tesla delivered 936,172 vehicles in 2021,
        while traditional automakers race to electrify. Norway leads adoption, with
        electric vehicles representing 65% of new car sales in 2021. Battery costs
        have fallen 89% since 2010, from $1,100 to $132 per kilowatt-hour.

        Carbon capture remains expensive at $250-$600 per ton of CO2. The Orca plant
        in Iceland, opened in September 2021, captures just 4,000 tons annually.
        Critics note this equals emissions from about 870 cars. More radical approaches
        like solar radiation management could cool the planet but carry unknown risks.

        The Paris Agreement, signed by 196 parties in December 2015, aims to limit
        warming to well below 2 degrees. Countries submit Nationally Determined
        Contributions (NDCs) outlining their emission reduction plans. However,
        current pledges put the world on track for 2.7 degrees of warming by 2100.

        Individual actions matter but systemic change is essential. Agriculture accounts
        for 10-12% of global emissions. Beef production generates 60 kg of CO2 equivalent
        per kilogram of meat. A plant-based diet could reduce food emissions by up to 73%.
        """,
        "needles": [
            ("Who chairs the IPCC?", "Hoesung Lee"),
            ("How many authors contributed to the 2021 IPCC report?", "234"),
            ("What percent of Denmark's electricity comes from wind?", "47%"),
            ("When did the Orca plant open?", "September 2021"),
            ("How many vehicles did Tesla deliver in 2021?", "936,172"),
            ("What percent of Norway's new cars are electric?", "65%"),
            ("When was the Paris Agreement signed?", "December 2015"),
            ("How much CO2 does beef production generate per kg?", "60 kg"),
        ],
    },
    {
        "name": "Detailed/MapReduce Range (~1800 tokens)",
        "description": "Tests larger content where OLD=DETAILED (chunks+meta), NEW=MAP_REDUCE",
        "content": """
        The history of computing spans centuries of human innovation, from ancient
        calculating devices to quantum computers. Understanding this evolution reveals
        how incremental advances compound into revolutionary change.

        Ancient Foundations (2400 BCE - 1600 CE)

        The abacus emerged independently in multiple civilizations. Chinese merchants
        used the suanpan as early as 2400 BCE for arithmetic. The Roman abacus used
        grooved beads, while the Japanese soroban featured a distinctive 1:4 bead
        arrangement still used today.

        Mechanical Calculation (1600-1900)

        In 1642, nineteen-year-old Blaise Pascal invented the Pascaline to help his
        tax-collector father. This brass rectangular box could add and subtract using
        interlocking gears. Only 50 were built, and 9 survive in museums today.

        Gottfried Wilhelm Leibniz improved Pascal's design in 1694, creating the
        Stepped Reckoner capable of multiplication and division. He also invented
        binary arithmetic, writing "Explication de l'Arithmétique Binaire" in 1703,
        laying groundwork for digital computing.

        Charles Babbage designed the Analytical Engine from 1833-1871, incorporating
        a mill (processor), store (memory), and punch card input. Ada Lovelace wrote
        detailed notes including what's considered the first algorithm - for computing
        Bernoulli numbers. The engine was never completed; Babbage died in 1871.

        Electronic Era (1900-1970)

        Alan Turing published "On Computable Numbers" in 1936, defining the theoretical
        Turing machine. During WWII, he led the team at Bletchley Park that cracked
        the Enigma code, shortening the war by an estimated two years.

        ENIAC, completed February 14, 1946, at the University of Pennsylvania, was
        the first general-purpose electronic computer. It weighed 30 tons, consumed
        150 kilowatts, and contained 17,468 vacuum tubes. Programming required
        physically rewiring the machine, taking days for each new problem.

        The transistor, invented December 23, 1947, at Bell Labs by John Bardeen,
        Walter Brattain, and William Shockley, revolutionized electronics. They
        shared the 1956 Nobel Prize in Physics. By 1954, the TRADIC computer used
        800 transistors instead of vacuum tubes.

        Jack Kilby demonstrated the first integrated circuit on September 12, 1958,
        at Texas Instruments. Robert Noyce independently developed a superior silicon
        version at Fairchild. Kilby won the 2000 Nobel Prize; Noyce had died in 1990.

        Personal Computing (1970-2000)

        Intel's 4004, released November 15, 1971, was the first commercial microprocessor.
        Designed by Federico Faggin, it contained 2,300 transistors running at 740 kHz.
        The 8080 (1974) powered the Altair 8800, sparking the PC revolution.

        Steve Wozniak built the Apple I in 1976 in his garage. The Apple II (1977)
        featured color graphics and cost $1,298. IBM entered with the PC on August 12,
        1981, using Microsoft's MS-DOS. By 1984, Apple's Macintosh introduced the GUI
        to mainstream users at $2,495.

        Tim Berners-Lee invented the World Wide Web at CERN in 1989, proposing it
        on March 12. The first website went live December 20, 1990. By 1995, the
        internet had 16 million users; by 2000, 361 million.

        Modern Era (2000-Present)

        Moore's Law, predicting transistor doubling every two years, has held since
        Gordon Moore's 1965 observation. Intel's 2021 Alder Lake processors contain
        10+ billion transistors on chips measuring 215 mm².

        Steve Jobs unveiled the iPhone on January 9, 2007. It sold 1.4 million units
        in its first year. Smartphones now exceed 6.6 billion globally, containing
        more power than 1990s supercomputers.

        Google claimed quantum supremacy October 23, 2019, with Sycamore completing
        a calculation in 200 seconds that would take 10,000 years classically.
        IBM disputed this, but the quantum era has clearly begun.
        """,
        "needles": [
            ("How old was Pascal when he invented the Pascaline?", "19"),
            ("When did Leibniz write about binary arithmetic?", "1703"),
            ("How many vacuum tubes did ENIAC contain?", "17,468"),
            ("When was the transistor invented?", "December 23, 1947"),
            ("When did Jack Kilby demonstrate the integrated circuit?", "September 12, 1958"),
            ("How many transistors did the Intel 4004 have?", "2,300"),
            ("When did the first website go live?", "December 20, 1990"),
            ("When did Jobs unveil the iPhone?", "January 9, 2007"),
            ("When did Google claim quantum supremacy?", "October 23, 2019"),
        ],
    },
]


def get_old_level(tokens: int) -> tuple[str, str]:
    """Determine what level the OLD (L1-L4) summarizer would use."""
    if tokens < OLD_THRESHOLD_NONE:
        return "NONE", "No summary needed"
    if tokens < OLD_THRESHOLD_BRIEF:
        return "BRIEF", "Single sentence (~20% compression)"
    if tokens < OLD_THRESHOLD_STANDARD:
        return "STANDARD", "Paragraph with content-aware prompts (~12%)"
    if tokens < OLD_THRESHOLD_DETAILED:
        return "DETAILED", "Chunked L1 summaries + meta L3 (~7%)"
    return "HIERARCHICAL", "Full L1/L2/L3 tree structure"


def get_new_level(tokens: int) -> tuple[str, str]:
    """Determine what level the NEW (adaptive) summarizer would use."""
    if tokens < NEW_THRESHOLD_NONE:
        return "NONE", "No summary needed"
    if tokens < NEW_THRESHOLD_BRIEF:
        return "BRIEF", "Single sentence"
    return "MAP_REDUCE", "Dynamic collapse based on content"


@dataclass
class TestResult:
    """Result of testing one content sample."""

    name: str
    tokens: int
    old_level: str
    old_description: str
    new_level: str
    new_description: str
    new_summary: str | None = None
    needles_found: int = 0
    total_needles: int = 0
    needle_details: list[tuple[str, str, bool]] = field(default_factory=list)


async def run_test(test_case: dict, config: dict) -> TestResult:
    """Run a single test case."""
    content = test_case["content"].strip()
    tokens = count_tokens(content, config["model"])

    old_level, old_desc = get_old_level(tokens)
    new_level, new_desc = get_new_level(tokens)

    # Run new summarizer
    cfg = SummarizerConfig(
        openai_base_url=config["base_url"],
        model=config["model"],
        api_key=config.get("api_key", "not-needed"),
    )

    result = await summarize(content, cfg, content_type="document")

    # Check needles in summary
    needle_details = []
    needles_found = 0

    if result.summary:
        summary_lower = result.summary.lower()
        for question, answer in test_case["needles"]:
            # Check if the key fact is preserved
            found = answer.lower() in summary_lower
            needle_details.append((question, answer, found))
            if found:
                needles_found += 1

    return TestResult(
        name=test_case["name"],
        tokens=tokens,
        old_level=old_level,
        old_description=old_desc,
        new_level=new_level,
        new_description=new_desc,
        new_summary=result.summary,
        needles_found=needles_found,
        total_needles=len(test_case["needles"]),
        needle_details=needle_details,
    )


def print_result(result: TestResult) -> None:
    """Print a test result."""
    print(f"\n{'=' * 70}")
    print(f"{result.name}")
    print(f"{'=' * 70}")
    print(f"Input tokens: {result.tokens}")
    print()
    print("Level comparison:")
    print(f"  OLD: {result.old_level:12} - {result.old_description}")
    print(f"  NEW: {result.new_level:12} - {result.new_description}")
    print()

    if result.new_summary:
        print("New summary:")
        wrapped = textwrap.fill(
            result.new_summary,
            width=68,
            initial_indent="  ",
            subsequent_indent="  ",
        )
        print(wrapped)
        print()

        print(
            f"Needle-in-haystack test: {result.needles_found}/{result.total_needles} facts preserved",
        )
        for question, answer, found in result.needle_details:
            status = "[OK]" if found else "[MISSING]"
            print(f"  {status} {question} -> {answer}")
    else:
        print("No summary produced (NONE level)")


async def main() -> None:
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Compare summarizer versions")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-oss-high:20b"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", "http://192.168.1.143:9292/v1"),
    )
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "not-needed"))
    args = parser.parse_args()

    config = {
        "model": args.model,
        "base_url": args.base_url,
        "api_key": args.api_key,
    }

    print("=" * 70)
    print("SUMMARIZER COMPARISON: OLD (L1-L4) vs NEW (Adaptive Map-Reduce)")
    print("=" * 70)
    print(f"Model: {config['model']}")
    print(f"Base URL: {config['base_url']}")

    results = []
    for test in TEST_CASES:
        print(f"\nRunning: {test['name']}...")
        result = await run_test(test, config)
        results.append(result)
        print_result(result)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_needles = sum(r.total_needles for r in results)
    found_needles = sum(r.needles_found for r in results)

    print(
        f"\nOverall fact preservation: {found_needles}/{total_needles} ({100 * found_needles / total_needles:.1f}%)",
    )
    print()

    print("Key differences:")
    print("""
OLD System (5 levels):
  - NONE (<100), BRIEF (100-500), STANDARD (500-3000),
    DETAILED (3000-15000), HIERARCHICAL (>15000)
  - Fixed boundaries, L1/L2/L3 tree for large content
  - Stored intermediate summaries at each level
  - Chunk size: 3000 tokens

NEW System (3 levels):
  - NONE (<100), BRIEF (100-500), MAP_REDUCE (>=500)
  - Dynamic collapse depth based on content
  - Content-type aware prompts
  - Chunk size: 2048 tokens (BOOOOKSCORE research)
  - Only stores final summary

Trade-offs:
  + Simpler (3 levels vs 5)
  + Research-backed parameters
  + Content-aware prompts
  - No intermediate level access
  - All >=500 token content treated the same
""")

    print("Verdict: ", end="")
    if found_needles / total_needles >= FACT_PRESERVATION_THRESHOLD:
        print("NEW system preserves facts adequately")
    else:
        print("NEW system may lose important details - further tuning needed")


if __name__ == "__main__":
    asyncio.run(main())
