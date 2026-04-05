#!/usr/bin/env python3
"""
literature_scan.py — Periodic arXiv scan for ARC-AGI / program synthesis techniques.

Queries arXiv's public Atom API for recent papers, extracts technique summaries
via Ollama, and writes evolution_results/literature_hints.json for the evolution
loop to consume during HYPOTHESIZE when stagnation is detected.

Usage:
  python literature_scan.py                  # scan + summarize, write hints file
  python literature_scan.py --query "DSL"    # custom query
  python literature_scan.py --list           # just list papers, no summarization
  python literature_scan.py --max-papers 10  # limit papers to process

No API key required. ArXiv Atom feed is free and rate-limit-friendly.
"""

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).parent
RESULTS_DIR = WORKSPACE / "evolution_results"
HINTS_FILE = RESULTS_DIR / "literature_hints.json"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-coder-v2")

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Queries targeting ARC-AGI-relevant research
DEFAULT_QUERIES = [
    '"Abstraction and Reasoning Corpus"',
    '"ARC-AGI"',
    '"program synthesis" AND "grid"',
    '"inductive logic programming" AND "visual"',
    '"domain specific language" AND "program induction"',
]

MAX_RESULTS_PER_QUERY = 5
MAX_PAPERS_TOTAL = 15
DAYS_LOOKBACK = 90  # only consider papers from the last N days


# ---------------------------------------------------------------------------
# ARXIV FETCH
# ---------------------------------------------------------------------------

def fetch_arxiv(query: str, max_results: int = 5) -> list[dict]:
    """Query arXiv Atom API and return list of paper dicts."""
    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "arc-agi-literature-scan/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"  [arxiv] fetch error for '{query}': {e}")
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f"  [arxiv] XML parse error: {e}")
        return []

    papers = []
    for entry in root.findall("atom:entry", ARXIV_NS):
        title_el = entry.find("atom:title", ARXIV_NS)
        summary_el = entry.find("atom:summary", ARXIV_NS)
        published_el = entry.find("atom:published", ARXIV_NS)
        id_el = entry.find("atom:id", ARXIV_NS)

        if title_el is None or summary_el is None:
            continue

        title = " ".join(title_el.text.strip().split())
        abstract = " ".join(summary_el.text.strip().split())
        published = published_el.text.strip() if published_el is not None else ""
        arxiv_id = id_el.text.strip() if id_el is not None else ""

        # Extract arXiv ID from URL
        if "/" in arxiv_id:
            arxiv_id = arxiv_id.rsplit("/", 1)[-1]

        # Filter by recency
        if published:
            try:
                pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
                cutoff = datetime.now(pub_date.tzinfo) - timedelta(days=DAYS_LOOKBACK)
                if pub_date < cutoff:
                    continue
            except (ValueError, TypeError):
                pass

        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": abstract,
            "published": published[:10],  # YYYY-MM-DD
        })

    return papers


def fetch_all_queries(queries: list[str], max_total: int = MAX_PAPERS_TOTAL) -> list[dict]:
    """Run multiple queries, deduplicate by arxiv_id, return up to max_total papers."""
    seen_ids = set()
    all_papers = []

    for query in queries:
        print(f"  [arxiv] Searching: '{query}'...")
        papers = fetch_arxiv(query, max_results=MAX_RESULTS_PER_QUERY)
        for p in papers:
            if p["arxiv_id"] not in seen_ids:
                seen_ids.add(p["arxiv_id"])
                all_papers.append(p)
                if len(all_papers) >= max_total:
                    return all_papers
        # Be polite to arXiv
        time.sleep(3)

    return all_papers


# ---------------------------------------------------------------------------
# TECHNIQUE EXTRACTION VIA OLLAMA
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """/no_think
You are extracting ARC-AGI helper function ideas from a research paper.

ARC-AGI tasks: a 2D grid (list[list[int]], values 0-9) is transformed to an output grid.
Helper functions take a grid and return a transformed grid or extracted information.
Examples of useful helpers: flood_fill, connected_components, detect_symmetry, extract_objects, scale_pattern, gravity_drop.

Paper title: {title}
Abstract: {abstract}

Extract 1-3 CONCRETE Python function ideas inspired by this paper. Each must be:
- A pure function: def name(grid: list[list[int]]) -> list[list[int]] (or -> dict/list)
- Implementable with only stdlib + numpy
- Useful for 2D grid pattern recognition or transformation

Even if the paper is theoretical, extract the CORE ALGORITHMIC IDEA and describe how to implement it as a grid function.

IMPORTANT: Do NOT output generic names like "flood_fill", "detect_symmetry", "extract_objects", "connected_components", "scale_pattern" — these already exist. Instead, name functions after the SPECIFIC technique from the paper (e.g., "abductive_rule_match", "vsa_encode_grid", "reasoning_chain_decompose").

Output as JSON array:
```json
[{{"name": "specific_unique_name", "description": "What this function does on a grid", "implementation_hint": "Step-by-step: 1) iterate rows, 2) find connected pixels, 3) return transformed grid"}}]
```

If the paper has ZERO relevance to 2D grids, patterns, or spatial reasoning, output: NOT_RELEVANT"""


def extract_techniques(paper: dict) -> list[dict]:
    """Use Ollama to extract implementable techniques from a paper abstract."""
    import requests

    prompt = EXTRACT_PROMPT.format(title=paper["title"], abstract=paper["abstract"])

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.1, "num_predict": 1024},
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
    except Exception as e:
        print(f"    [ollama] Error extracting from '{paper['title'][:50]}': {e}")
        return []

    if "NOT_RELEVANT" in content:
        return []

    # Parse JSON from response
    json_match = re.search(r"```json\s*(.*?)```", content, re.DOTALL)
    if not json_match:
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if json_match:
            raw = json_match.group(0)
        else:
            return []
    else:
        raw = json_match.group(1)

    try:
        techniques = json.loads(raw)
        if not isinstance(techniques, list):
            return []
        # Tag each technique with its source paper
        for t in techniques:
            t["source_paper"] = paper["title"]
            t["arxiv_id"] = paper["arxiv_id"]
            t["published"] = paper["published"]
        return techniques
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def scan_and_extract(queries: list[str] | None = None,
                     max_papers: int = MAX_PAPERS_TOTAL,
                     list_only: bool = False) -> list[dict]:
    """Full pipeline: fetch papers, extract techniques, write hints file."""
    if queries is None:
        queries = DEFAULT_QUERIES

    print(f"[literature] Scanning arXiv ({len(queries)} queries, last {DAYS_LOOKBACK} days)...")
    papers = fetch_all_queries(queries, max_total=max_papers)
    print(f"[literature] Found {len(papers)} papers")

    if not papers:
        return []

    if list_only:
        for p in papers:
            print(f"  {p['published']} | {p['arxiv_id']} | {p['title'][:80]}")
        return []

    # Extract techniques from each paper
    all_techniques = []
    for i, paper in enumerate(papers):
        print(f"  [{i+1}/{len(papers)}] Extracting from: {paper['title'][:70]}...")
        techniques = extract_techniques(paper)
        if techniques:
            print(f"    → {len(techniques)} techniques found")
            all_techniques.extend(techniques)
        else:
            print(f"    → not relevant or extraction failed")

    print(f"\n[literature] Total techniques extracted: {len(all_techniques)}")

    # Write hints file
    if all_techniques:
        RESULTS_DIR.mkdir(exist_ok=True)

        # Merge with existing hints (keep old ones, add new)
        existing = []
        if HINTS_FILE.exists():
            try:
                existing = json.loads(HINTS_FILE.read_text())
            except (json.JSONDecodeError, IOError):
                pass

        # Deduplicate by (name, arxiv_id) — same technique from different papers is kept
        seen_keys = {(t["name"], t.get("arxiv_id", "")) for t in existing}
        for t in all_techniques:
            key = (t["name"], t.get("arxiv_id", ""))
            if key not in seen_keys:
                existing.append(t)
                seen_keys.add(key)

        # Add scan metadata
        result = {
            "last_scan": datetime.now().isoformat(),
            "techniques": existing,
        }

        HINTS_FILE.write_text(json.dumps(result, indent=2))
        print(f"[literature] Wrote {len(existing)} techniques to {HINTS_FILE}")

    return all_techniques


def load_hints(max_hints: int = 5) -> str:
    """Load literature hints and format as text for injection into hypothesis prompts.

    Called by evolve_qwen_arc.py during HYPOTHESIZE when stagnation is high.
    Returns empty string if no hints file exists.
    """
    if not HINTS_FILE.exists():
        return ""

    try:
        data = json.loads(HINTS_FILE.read_text())
        techniques = data.get("techniques", [])
    except (json.JSONDecodeError, IOError):
        return ""

    if not techniques:
        return ""

    # Rotate through techniques based on current time to vary suggestions
    import random
    random.seed(int(time.time()) // 3600)  # change every hour
    random.shuffle(techniques)
    selected = techniques[:max_hints]

    lines = ["## Literature-Suggested Techniques (from recent arXiv papers)",
             "Try implementing functions inspired by these research findings:\n"]

    for t in selected:
        lines.append(f"**{t['name']}** (from: {t.get('source_paper', 'unknown')[:60]})")
        lines.append(f"  {t['description']}")
        lines.append(f"  Implementation: {t['implementation_hint']}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ArXiv literature scan for ARC-AGI evolution")
    parser.add_argument("--query", type=str, nargs="+", help="Custom search queries")
    parser.add_argument("--max-papers", type=int, default=MAX_PAPERS_TOTAL)
    parser.add_argument("--list", action="store_true", help="Just list papers, no extraction")
    parser.add_argument("--days", type=int, default=DAYS_LOOKBACK, help="Lookback period in days")
    args = parser.parse_args()

    DAYS_LOOKBACK = args.days
    queries = args.query if args.query else None
    scan_and_extract(queries=queries, max_papers=args.max_papers, list_only=args.list)
