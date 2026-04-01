"""
Step 2 — spaCy NER Preprocessing Pipeline

Reads all 5 input files, extracts entities (people, projects, dates,
decisions, technologies) using spaCy, outputs structured JSON per file
and a combined entities.json for the graph builder.

Install:
    pip install spacy
    python -m spacy download en_core_web_lg
"""

import json
import re
from datetime import datetime
from pathlib import Path

try:
    import spacy
except ImportError:
    spacy = None  # type: ignore — handled gracefully in run()

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
DATASET_DIR = SCRIPT_DIR.parent.parent / "dataset"
INPUT_DIR = DATASET_DIR / "input"
OUTPUT_DIR = DATASET_DIR / "ner_output"
OUTPUT_DIR.mkdir(exist_ok=True)

INPUT_FILES = [
    "slack_architecture_decisions.txt",
    "confluence_adrs.txt",
    "github_prs.txt",
    "zoom_transcripts.txt",
    "onboarding_docs.txt",
]

SOURCE_MAP = {
    "slack_architecture_decisions.txt": "slack",
    "confluence_adrs.txt": "confluence",
    "github_prs.txt": "github",
    "zoom_transcripts.txt": "zoom",
    "onboarding_docs.txt": "confluence",
}

# ── Domain-specific entity lists (supplement spaCy) ──────────────────────────

KNOWN_PEOPLE = {
    "alice chen": {"id": "alice.chen", "role": "Senior Engineer"},
    "bob martinez": {"id": "bob.martinez", "role": "Engineer"},
    "carol singh": {"id": "carol.singh", "role": "Engineer"},
    "david kim": {"id": "david.kim", "role": "Infrastructure Engineer"},
    "priya nair": {"id": "priya.nair", "role": "CTO"},
}

KNOWN_TECHNOLOGIES = {
    "postgresql", "postgres", "mongodb", "redis", "memcached",
    "pgbouncer", "rds proxy", "kubernetes", "istio", "linkerd",
    "kafka", "sqs", "launchdarkly", "docker", "aws", "rds",
    "oauth2", "jwt", "bm25", "whisper",
}

KNOWN_PROJECTS = {
    "billing-service", "billing service",
    "notifications-service", "notifications service", "notifications module",
    "recommendations-engine", "recommendations engine",
    "monolith", "platform team", "acmecorp",
}

KNOWN_DECISIONS = {
    "adr-001", "adr-002", "adr-003", "adr-004", "adr-007",
    "pr #142", "pr #178", "pr #203", "pr #267", "pr #289",
    "pr 289",
}

KNOWN_CONCEPTS = {
    "strangler fig", "acid compliance", "acid",
    "connection pooling", "connection pool",
    "circuit breaker",
    "transaction pooling", "session pooling", "service mesh", "microservices",
    "knowledge transfer", "departure risk", "single point of failure",
    "api versioning", "semantic versioning", "versioning",
    "url path versioning", "v2 api", "v2",
}

# ── Decision pattern: lines containing "decision", "chose", "decided", "ADR" ─

DECISION_PATTERNS = [
    r"(?i)(decision|decided|chose|choosing|going with|locked in|confirmed)[:\s]+(.{10,120})",
    r"(?i)(ADR-\d+)[:\s]+(.{10,120})",
    r"(?i)we will (use|adopt|deploy|implement)\s+(.{5,80})",
]


def extract_decisions(text: str) -> list[dict]:
    decisions = []
    for pattern in DECISION_PATTERNS:
        for match in re.finditer(pattern, text):
            raw = match.group(0).strip()
            if len(raw) > 20:
                decisions.append({
                    "text": raw[:200],
                    "type": "DECISION",
                })
    return decisions


def extract_dates(text: str) -> list[str]:
    date_patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
        r"\bQ[1-4]\s+\d{4}\b",
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b",
    ]
    found = []
    for pattern in date_patterns:
        found.extend(re.findall(pattern, text, re.IGNORECASE))
    return list(set(str(d) for d in found))


def classify_entity(text: str, label: str) -> tuple[str, str]:
    """
    Returns (entity_type, canonical_id).
    Priority: domain lists > spaCy label.
    """
    t = text.lower().strip()

    if t in KNOWN_PEOPLE:
        return "PERSON", KNOWN_PEOPLE[t]["id"]
    for name, info in KNOWN_PEOPLE.items():
        if name in t:
            return "PERSON", info["id"]

    if any(tech in t for tech in KNOWN_TECHNOLOGIES):
        matched = next(tech for tech in KNOWN_TECHNOLOGIES if tech in t)
        return "TECHNOLOGY", matched.replace(" ", "_")

    if any(proj in t for proj in KNOWN_PROJECTS):
        matched = next(proj for proj in KNOWN_PROJECTS if proj in t)
        return "PROJECT", matched.replace(" ", "_")

    if any(dec in t for dec in KNOWN_DECISIONS):
        matched = next(dec for dec in KNOWN_DECISIONS if dec in t)
        return "DECISION", matched.upper()

    if any(concept in t for concept in KNOWN_CONCEPTS):
        matched = next(concept for concept in KNOWN_CONCEPTS if concept in t)
        return "CONCEPT", matched.replace(" ", "_")

    # Fall back to spaCy label
    spacy_map = {
        "PERSON": "PERSON",
        "ORG": "ORGANIZATION",
        "PRODUCT": "TECHNOLOGY",
        "DATE": "DATE",
        "GPE": "LOCATION",
        "EVENT": "EVENT",
    }
    return spacy_map.get(label, "OTHER"), text.lower().replace(" ", "_")


def process_file(nlp, filepath: Path, source_system: str) -> dict:
    text = filepath.read_text(encoding="utf-8")
    doc = nlp(text)

    entities: list[dict] = []
    seen: set[str] = set()

    # spaCy NER entities
    for ent in doc.ents:
        if ent.label_ not in ("PERSON", "ORG", "PRODUCT", "DATE", "GPE", "EVENT", "WORK_OF_ART"):
            continue
        raw = ent.text.strip()
        if len(raw) < 2 or raw.lower() in seen:
            continue
        seen.add(raw.lower())
        etype, eid = classify_entity(raw, ent.label_)
        if etype == "OTHER":
            continue
        entities.append({
            "id": eid,
            "text": raw,
            "type": etype,
            "spacy_label": ent.label_,
            "source": source_system,
            "file": filepath.name,
        })

    # Domain-specific entity injection (things spaCy misses)
    text_lower = text.lower()

    for name, info in KNOWN_PEOPLE.items():
        if name in text_lower and info["id"] not in seen:
            seen.add(info["id"])
            entities.append({
                "id": info["id"],
                "text": name.title(),
                "type": "PERSON",
                "role": info["role"],
                "spacy_label": "DOMAIN",
                "source": source_system,
                "file": filepath.name,
            })

    for tech in KNOWN_TECHNOLOGIES:
        if tech in text_lower and tech not in seen:
            seen.add(tech)
            entities.append({
                "id": tech.replace(" ", "_"),
                "text": tech,
                "type": "TECHNOLOGY",
                "spacy_label": "DOMAIN",
                "source": source_system,
                "file": filepath.name,
            })

    for proj in KNOWN_PROJECTS:
        if proj in text_lower and proj not in seen:
            seen.add(proj)
            entities.append({
                "id": proj.replace(" ", "_"),
                "text": proj,
                "type": "PROJECT",
                "spacy_label": "DOMAIN",
                "source": source_system,
                "file": filepath.name,
            })

    for dec in KNOWN_DECISIONS:
        if dec in text_lower and dec not in seen:
            seen.add(dec)
            entities.append({
                "id": dec.upper().replace(" ", "_"),
                "text": dec.upper(),
                "type": "DECISION",
                "spacy_label": "DOMAIN",
                "source": source_system,
                "file": filepath.name,
            })

    for concept in KNOWN_CONCEPTS:
        if concept in text_lower and concept not in seen:
            seen.add(concept)
            entities.append({
                "id": concept.replace(" ", "_"),
                "text": concept,
                "type": "CONCEPT",
                "spacy_label": "DOMAIN",
                "source": source_system,
                "file": filepath.name,
            })

    decisions = extract_decisions(text)
    dates = extract_dates(text)

    return {
        "file": filepath.name,
        "source_system": source_system,
        "char_count": len(text),
        "entity_count": len(entities),
        "entities": entities,
        "decisions_extracted": decisions[:20],
        "dates_found": dates,
        "processed_at": datetime.now().isoformat(),
    }


def run():
    print("Loading spaCy model (en_core_web_lg)...")
    nlp = None
    try:
        import spacy as _spacy
        try:
            nlp = _spacy.load("en_core_web_lg")
            print("  Using en_core_web_lg")
        except OSError:
            try:
                nlp = _spacy.load("en_core_web_sm")
                print("  Using en_core_web_sm (fallback)")
            except OSError:
                print("  No spaCy model found — running domain-only extraction (no spaCy NER)")
    except ImportError:
        print("  spaCy not installed — running domain-only extraction")

    # Create a minimal stub if spaCy unavailable
    if nlp is None:
        class _FakeDoc:
            ents = []
        class _FakeNLP:
            def __call__(self, text):
                return _FakeDoc()
        nlp = _FakeNLP()

    all_entities: dict[str, dict] = {}  # id → entity (deduplicated across files)
    file_results = []

    for fname in INPUT_FILES:
        fpath = INPUT_DIR / fname
        if not fpath.exists():
            print(f"  SKIP: {fname} not found")
            continue

        print(f"  Processing {fname}...")
        result = process_file(nlp, fpath, SOURCE_MAP[fname])
        file_results.append(result)

        # Merge into global entity map
        for ent in result["entities"]:
            eid = ent["id"]
            if eid not in all_entities:
                all_entities[eid] = {**ent, "files": [ent["file"]]}
            else:
                # Entity appears in multiple files — add file reference
                if ent["file"] not in all_entities[eid]["files"]:
                    all_entities[eid]["files"].append(ent["file"])

        # Write per-file output
        out_path = OUTPUT_DIR / fname.replace(".txt", "_ner.json")
        out_path.write_text(json.dumps(result, indent=2))
        print(f"    → {result['entity_count']} entities extracted")

    # Write combined entities
    combined = {
        "total_entities": len(all_entities),
        "entity_types": {},
        "entities": list(all_entities.values()),
        "processed_at": datetime.now().isoformat(),
    }

    # Count by type
    for ent in all_entities.values():
        t = ent["type"]
        combined["entity_types"][t] = combined["entity_types"].get(t, 0) + 1

    combined_path = OUTPUT_DIR / "entities_combined.json"
    combined_path.write_text(json.dumps(combined, indent=2))

    print(f"\nDone. {len(all_entities)} unique entities across {len(file_results)} files.")
    print(f"Entity types: {combined['entity_types']}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
