"""Run all verification scripts and print a final summary."""
import subprocess, sys
from pathlib import Path

scripts = [
    ("Dataset + Graph",    "check_graph.py",    "RESULT"),
    ("NER Extraction",     "check_ner.py",      "OVERALL"),
    ("Hybrid Retrieval",   "test_retrieval.py", "RESULT"),
    ("Decay Verification", "test_decay.py",     "RESULT"),
    ("Demo Scenario",      "demo_scenario.py",  "RESULT|DEMO READY"),
]

SCRIPTS_DIR = Path(__file__).parent
results = []

for label, script, grep in scripts:
    r = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script)],
        capture_output=True, text=True, timeout=60
    )
    output = r.stdout + r.stderr
    # Find the result line
    result_line = next(
        (line.strip() for line in output.splitlines()
         if any(g in line for g in grep.split("|"))),
        "No result line found"
    )
    passed = r.returncode == 0 and ("PASS" in result_line or "100%" in result_line or "READY" in result_line)
    results.append((label, passed, result_line))
    symbol = "v" if passed else "X"
    print(f"[{symbol}] {label:<22} {result_line}")

print()
total = len(results)
passed = sum(1 for _, p, _ in results if p)
print(f"{'='*55}")
print(f"FINAL: {passed}/{total} suites passed")
if passed == total:
    print("All 5 priorities verified. Demo ready.")
else:
    failed = [label for label, p, _ in results if not p]
    print(f"Fix before demo: {failed}")
print(f"{'='*55}")
