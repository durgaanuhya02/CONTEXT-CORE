from pathlib import Path

checks = [
    ("dataset/input/slack_architecture_decisions.txt", ["postgresql", "connection pool", "connection pooling"]),
    ("dataset/input/confluence_adrs.txt", ["notifications-service", "notifications service", "notifications module"]),
    ("dataset/input/zoom_transcripts.txt", ["adr-002", "adr 002", "pr 289", "pr #289"]),
    ("dataset/input/onboarding_docs.txt", ["api versioning", "versioning", "semantic versioning"]),
]

for fpath, terms in checks:
    text = Path(fpath).read_text(encoding="utf-8").lower()
    print(fpath.split("/")[-1])
    for term in terms:
        found = term in text
        status = "FOUND" if found else "MISS "
        print(f"  [{status}] {repr(term)}")
    print()
