"""
Verify all graph nodes have created_at timestamps and valid decay scores.
Without created_at, confidence decay formula e^(-lambda * months) cannot work.
"""

import json
import math
from datetime import datetime
from pathlib import Path

GRAPH_JSON = Path(__file__).parent.parent.parent / "dataset" / "ner_output" / "knowledge_graph.json"
LAMBDA = 0.02  # must match build_graph.py and retrieval.py


def expected_decay(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at)
        months = (datetime.now() - created).days / 30.44
        return round(max(0.05, min(1.0, math.exp(-LAMBDA * months))), 4)
    except Exception:
        return None


def run():
    data = json.loads(GRAPH_JSON.read_text())
    nodes = data["nodes"]

    missing_ts = []
    wrong_decay = []
    correct = []

    for node in nodes:
        nid = node["id"]
        created_at = node.get("created_at")
        decay = node.get("decay_score")

        if not created_at:
            missing_ts.append(node)
            continue

        expected = expected_decay(created_at)
        months = (datetime.now() - datetime.fromisoformat(created_at)).days / 30.44

        if expected is not None and decay is not None:
            diff = abs(decay - expected)
            if diff > 0.05:  # allow small rounding tolerance
                wrong_decay.append({
                    "id": nid,
                    "created_at": created_at,
                    "months_old": round(months, 1),
                    "stored_decay": decay,
                    "expected_decay": expected,
                    "diff": round(diff, 4),
                })
            else:
                correct.append({
                    "id": nid,
                    "created_at": created_at,
                    "months_old": round(months, 1),
                    "decay_score": decay,
                })

    print("=" * 60)
    print("TIMESTAMP & DECAY VERIFICATION")
    print("=" * 60)
    print(f"Total nodes:        {len(nodes)}")
    print(f"Has created_at:     {len(nodes) - len(missing_ts)}")
    print(f"Missing created_at: {len(missing_ts)}")
    print(f"Correct decay:      {len(correct)}")
    print(f"Wrong decay:        {len(wrong_decay)}")

    if missing_ts:
        print(f"\nNODES MISSING created_at ({len(missing_ts)}):")
        for n in missing_ts:
            print(f"  [{n['type']:<10}] {n['id']:<35} decay={n.get('decay_score')}")

    if wrong_decay:
        print(f"\nNODES WITH WRONG DECAY ({len(wrong_decay)}):")
        for n in wrong_decay:
            print(f"  {n['id']:<35} stored={n['stored_decay']} expected={n['expected_decay']} diff={n['diff']}")

    print(f"\nSAMPLE — decay scores by age:")
    sample = sorted(correct, key=lambda x: x["months_old"], reverse=True)[:10]
    for n in sample:
        bar = "#" * int(n["decay_score"] * 20)
        stale = " <-- STALE (>18mo)" if n["months_old"] > 18 else ""
        print(f"  {n['id']:<35} {n['months_old']:>5.1f}mo  decay={n['decay_score']:.4f}  [{bar:<20}]{stale}")

    print()
    if not missing_ts and not wrong_decay:
        print("RESULT: PASS — all nodes have timestamps and correct decay scores")
    else:
        print(f"RESULT: FAIL — {len(missing_ts)} missing timestamps, {len(wrong_decay)} wrong decay scores")


if __name__ == "__main__":
    run()
