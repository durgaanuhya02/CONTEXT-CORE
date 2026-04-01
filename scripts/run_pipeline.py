"""
ContextCore Data Pipeline — run all steps in order.

Usage:
    cd contextcore/scripts
    python run_pipeline.py

Steps:
    1. preprocess.py  — spaCy NER → entities_combined.json
    2. build_graph.py — NetworkX graph → knowledge_graph.json + .graphml
    3. embed_nodes.py — ChromaDB embeddings (OpenAI or pseudo-fallback)
    4. metadata_linker.py — PostgreSQL enrichment (optional, needs DB)
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent

STEPS = [
    ("NER Preprocessing",    SCRIPTS / "preprocess.py"),
    ("Graph Construction",   SCRIPTS / "build_graph.py"),
    ("Node Embeddings",      SCRIPTS / "embed_nodes.py"),
]

OPTIONAL_STEPS = [
    ("PostgreSQL Seeding (from graph JSON)", SCRIPTS / "seed_db.py"),
    ("PostgreSQL Enrichment (requires GraphRAG)", SCRIPTS / "metadata_linker.py"),
]


def run_step(name: str, script: Path, optional: bool = False) -> bool:
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable, str(script)], capture_output=False)
    if result.returncode != 0:
        if optional:
            print(f"  [SKIP] {name} failed (optional step — continuing)")
            return False
        else:
            print(f"  [FAIL] {name} failed with exit code {result.returncode}")
            sys.exit(result.returncode)
    print(f"  [OK] {name} complete")
    return True


if __name__ == "__main__":
    print("ContextCore Pipeline Starting...")
    for name, script in STEPS:
        run_step(name, script)
    for name, script in OPTIONAL_STEPS:
        run_step(name, script, optional=True)
    print("\n" + "="*60)
    print("  Pipeline complete.")
    print("  Start the backend: cd contextcore/backend && uvicorn main:app --reload")
    print("  Start the frontend: cd contextcore/frontend && npm run dev")
    print("="*60)
