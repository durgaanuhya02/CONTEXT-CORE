"""Verify the three specific fixes."""
import urllib.request, json

BASE = "http://localhost:8000"

def post(path, data):
    req = urllib.request.Request(BASE + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read())

print("=" * 60)
print("FIX 1: Answer quality — no raw citation tags")
print("=" * 60)
queries = [
    "Why did we choose pgBouncer over RDS Proxy?",
    "Why is the circuit breaker threshold 50%?",
    "Who owns the most critical knowledge at AcmeCorp?",
    "What should a new engineer know before touching billing-service?",
    "Is the Istio service mesh decision still valid?",
]
for q in queries:
    r = post("/query", {"question": q})
    answer = r["answer"]
    has_raw_tags = answer.strip().endswith("]") and "Cited knowledge nodes:" in answer
    conf = r["confidence"]
    print(f"\n  Q: {q[:55]}")
    print(f"  A: {answer[:140]}...")
    print(f"  Confidence: {round(conf*100)}%  |  Raw tags appended: {has_raw_tags}  |  Sources: {len(r['sources'])}")

print()
print("=" * 60)
print("FIX 2: Stale node count")
print("=" * 60)
h = get("/risk/health")
print(f"  Total nodes: {h['total_nodes']}")
print(f"  Stale nodes: {h['stale_nodes']}  (was 48/48 before fix)")
print(f"  Fresh nodes: {h['total_nodes'] - h['stale_nodes']}")

g = get("/graph")
decays = [n["decay_score"] for n in g["nodes"]]
fresh = [d for d in decays if d >= 0.5]
stale = [d for d in decays if d < 0.5]
print(f"  Graph decay range: {min(decays):.2f} - {max(decays):.2f}")
print(f"  Fresh (>=0.5): {len(fresh)}  |  Stale (<0.5): {len(stale)}")

print()
print("=" * 60)
print("FIX 3: Confidence score variance")
print("=" * 60)
test_queries = [
    ("pgBouncer (direct match, fresh nodes)", "Why did we choose pgBouncer over RDS Proxy?"),
    ("circuit breaker (direct match)", "Why is the circuit breaker threshold 50%?"),
    ("Istio risk (fresh kubernetes nodes)", "Is the Istio service mesh decision still valid?"),
    ("Redis/recommendations (very fresh)", "Why did we choose Redis over Memcached?"),
    ("vague query (low match)", "Tell me about the company culture"),
]
confidences = []
for label, q in test_queries:
    r = post("/query", {"question": q})
    c = r["confidence"]
    confidences.append(c)
    print(f"  {label[:45]:<45} -> {round(c*100)}%")

variance = max(confidences) - min(confidences)
print(f"\n  Range: {round(min(confidences)*100)}% - {round(max(confidences)*100)}%  |  Variance: {round(variance*100)}pp  (was ~1pp before fix)")
