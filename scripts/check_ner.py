"""Manual NER verification — checks all 5 documents against expected entities."""
import json
from pathlib import Path

NER_DIR = Path(__file__).parent.parent.parent / "dataset" / "ner_output"

# Ground truth: what SHOULD be in each file
EXPECTED = {
    "slack_architecture_decisions_ner.json": {
        "people": ["Alice Chen", "Bob Martinez", "Carol Singh", "David Kim"],
        "projects": ["billing-service", "notifications-service"],
        "technologies": ["postgres", "mongodb", "redis", "pgbouncer"],  # file uses "Postgres" not "postgresql"
        "decisions": ["ADR-001", "ADR-002", "ADR-007"],
        "concepts": ["strangler fig", "connection pool", "circuit breaker"],  # file uses "connection pool"
        "dates": ["2022-03-14", "2022-07-08", "2023-04-03", "2024-01-15"],
    },
    "confluence_adrs_ner.json": {
        "people": ["Alice Chen", "Carol Singh", "Bob Martinez"],
        "projects": ["billing-service", "notifications module"],  # file uses "notifications module"
        "technologies": ["postgresql", "pgbouncer", "redis", "kubernetes", "istio"],
        "decisions": ["ADR-001", "ADR-002", "ADR-003", "ADR-004", "ADR-007"],
        "concepts": ["acid compliance", "strangler fig", "transaction pooling", "connection pooling"],
        "dates": ["2022-03-15", "2022-07-10", "2022-11-22", "2023-04-10", "2024-01-16"],
    },
    "github_prs_ner.json": {
        "people": ["Alice Chen", "Bob Martinez", "Carol Singh", "David Kim"],
        "projects": ["billing-service", "notifications-service"],
        "technologies": ["pgbouncer", "launchdarkly", "redis", "sqs"],
        "decisions": ["ADR-004", "ADR-002", "PR #142", "PR #178", "PR #289"],
        "concepts": ["transaction pooling", "knowledge transfer"],
        "dates": ["2023-04-08", "2023-11-14", "2023-01-10", "2024-01-22", "2023-10-05"],
    },
    "zoom_transcripts_ner.json": {
        "people": ["Alice Chen", "Bob Martinez", "Carol Singh", "David Kim", "Priya Nair"],
        "projects": ["billing-service", "notifications-service"],
        "technologies": ["kubernetes", "istio"],
        "decisions": ["PR 289"],  # zoom uses "PR 289" not "ADR-002" directly
        "concepts": ["strangler fig", "single point of failure", "knowledge transfer"],
        "dates": ["2022-07-20", "2023-04-05", "2023-10-15", "2024-03-10"],
    },
    "onboarding_docs_ner.json": {
        "people": ["Alice Chen", "Bob Martinez", "Carol Singh", "David Kim"],
        "projects": ["billing-service", "notifications-service", "recommendations-engine", "monolith"],
        "technologies": ["postgresql", "pgbouncer", "redis", "kubernetes", "istio"],
        "decisions": ["ADR-001", "ADR-002", "ADR-004", "ADR-007"],
        "concepts": ["transaction pooling", "single point of failure", "v2"],  # file uses "v2 (OAuth2 + JWT)"
        "dates": ["2024-01-08", "2023-10-05"],
    },
}

PASS = 0
FAIL = 0
MISSING_TOTAL = []

for fname, expected in EXPECTED.items():
    path = NER_DIR / fname
    if not path.exists():
        print(f"MISSING FILE: {fname}")
        continue

    data = json.loads(path.read_text())
    entities = data["entities"]
    dates = data["dates_found"]

    extracted_people = [e["text"].lower() for e in entities if e["type"] == "PERSON"]
    extracted_projects = [e["text"].lower() for e in entities if e["type"] == "PROJECT"]
    extracted_techs = [e["text"].lower() for e in entities if e["type"] == "TECHNOLOGY"]
    extracted_decisions = [e["text"].lower() for e in entities if e["type"] == "DECISION"]
    extracted_concepts = [e["text"].lower() for e in entities if e["type"] == "CONCEPT"]
    extracted_dates = [str(d).lower() for d in dates]

    print(f"\n{'='*60}")
    print(f"FILE: {fname}")
    print(f"{'='*60}")

    checks = [
        ("PEOPLE",    expected["people"],    extracted_people),
        ("PROJECTS",  expected["projects"],  extracted_projects),
        ("TECH",      expected["technologies"], extracted_techs),
        ("DECISIONS", expected["decisions"], extracted_decisions),
        ("CONCEPTS",  expected["concepts"],  extracted_concepts),
        ("DATES",     expected["dates"],     extracted_dates),
    ]

    file_pass = 0
    file_fail = 0

    for category, expected_items, extracted_items in checks:
        found = []
        missing = []
        for item in expected_items:
            if any(item.lower() in e for e in extracted_items):
                found.append(item)
                file_pass += 1
                PASS += 1
            else:
                missing.append(item)
                file_fail += 1
                FAIL += 1
                MISSING_TOTAL.append(f"{fname} / {category} / {item}")

        status = "OK" if not missing else "PARTIAL" if found else "FAIL"
        symbol = "v" if status == "OK" else "!" if status == "PARTIAL" else "X"
        print(f"  [{symbol}] {category:<12} found={len(found)}/{len(expected_items)}  "
              f"extracted={len(extracted_items)}")
        if missing:
            print(f"       MISSING: {missing}")

    print(f"  File score: {file_pass}/{file_pass+file_fail}")

total = PASS + FAIL
print(f"\n{'='*60}")
print(f"OVERALL: {PASS}/{total} checks passed ({round(PASS/total*100)}%)")
if MISSING_TOTAL:
    print(f"\nAll missing items ({len(MISSING_TOTAL)}):")
    for m in MISSING_TOTAL:
        print(f"  - {m}")
else:
    print("No missing items — full coverage.")
