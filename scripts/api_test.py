"""Full API integration test — hits every endpoint and reports pass/fail."""
import urllib.request
import json
import sys

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.status, json.loads(r.read())


def post(path, data):
    req = urllib.request.Request(
        BASE + path,
        json.dumps(data).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, json.loads(r.read())


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  {detail}")


# ── 1. Health ─────────────────────────────────────────────────────────────────
print("\n[1] GET /health")
s, r = get("/health")
check("status 200", s == 200)
check("service=ContextCore", r.get("service") == "ContextCore")
check("storage list present", "storage" in r)
print(f"     storage: {r.get('storage')}")

# ── 2. Query — pgBouncer ──────────────────────────────────────────────────────
print("\n[2] POST /query  (pgBouncer vs RDS Proxy)")
s, r = post("/query", {"question": "Why did we choose pgBouncer over RDS Proxy?", "method": "local"})
check("status 200", s == 200)
check("answer non-empty", len(r.get("answer", "")) > 50)
check("sources >= 5", len(r.get("sources", [])) >= 5)
check("confidence 0-1", 0 < r.get("confidence", 0) < 1)
check("query_id assigned", r.get("query_id", 0) > 0)
check("duration_ms present", r.get("duration_ms", 0) > 0)
check("pgBouncer in answer", "pgbouncer" in r["answer"].lower() or "pgBouncer" in r["answer"])
src = r["sources"][0]
check("source has decay_score", "decay_score" in src)
check("source has author_id", "author_id" in src)
check("source has is_stale", "is_stale" in src)
print(f"     answer[:80]: {r['answer'][:80]}")
print(f"     sources: {len(r['sources'])} | confidence: {r['confidence']} | {r['duration_ms']}ms")

# ── 3. Query — circuit breaker ────────────────────────────────────────────────
print("\n[3] POST /query  (circuit breaker)")
s, r2 = post("/query", {"question": "Why is the circuit breaker threshold 50%?"})
check("status 200", s == 200)
check("answer mentions circuit/50%", "50%" in r2.get("answer", "") or "circuit" in r2.get("answer", "").lower())
check("sources present", len(r2.get("sources", [])) > 0)
print(f"     answer[:80]: {r2['answer'][:80]}")

# ── 4. Risk health ────────────────────────────────────────────────────────────
print("\n[4] GET /risk/health")
s, r = get("/risk/health")
check("status 200", s == 200)
check("overall_score 0-100", 0 < r.get("overall_score", 0) <= 100)
check("total_nodes > 0", r.get("total_nodes", 0) > 0)
check("domains list", len(r.get("domains", [])) > 0)
check("owners list", len(r.get("owners", [])) > 0)
check("has CRITICAL domain", any(d["risk_level"] == "CRITICAL" for d in r["domains"]))
check("has HIGH domain", any(d["risk_level"] == "HIGH" for d in r["domains"]))
print(f"     score: {r['overall_score']} | nodes: {r['total_nodes']} | stale: {r['stale_nodes']}")
print(f"     domains: {[(d['domain'], d['risk_level']) for d in r['domains']]}")

# ── 5. Risk owners ────────────────────────────────────────────────────────────
print("\n[5] GET /risk/owners")
s, r = get("/risk/owners")
check("status 200", s == 200)
check("returns list", isinstance(r, list))
check("alice.chen present", any(o["author_id"] == "alice.chen" for o in r))
check("david.kim CRITICAL", any(o["author_id"] == "david.kim" and o["risk_level"] == "CRITICAL" for o in r))
print(f"     owners: {[(o['author_id'], o['risk_level']) for o in r]}")

# ── 6. Risk domains ───────────────────────────────────────────────────────────
print("\n[6] GET /risk/domains")
s, r = get("/risk/domains")
check("status 200", s == 200)
check("4 domains", len(r) == 4)
check("sole_owner flag present", any(d["sole_owner"] for d in r))
print(f"     {[(d['domain'], d['risk_score']) for d in r]}")

# ── 7. Transfer checklist ─────────────────────────────────────────────────────
print("\n[7] GET /risk/transfer/alice.chen")
s, r = get("/risk/transfer/alice.chen")
check("status 200", s == 200)
check("owner_id correct", r.get("owner_id") == "alice.chen")
check("checklist non-empty", len(r.get("checklist", [])) > 0)
check("items have decay_score", all("decay_score" in i for i in r["checklist"]))
check("items have priority", all("priority" in i for i in r["checklist"]))
print(f"     {len(r['checklist'])} items | top: {r['checklist'][0]['title'][:50]}")

# ── 8. Departure alert — alice ────────────────────────────────────────────────
print("\n[8] GET /risk/departure/alice.chen")
s, r = get("/risk/departure/alice.chen")
check("status 200", s == 200)
check("risk_level HIGH", r.get("risk_level") == "HIGH")
check("critical_nodes present", len(r.get("critical_nodes", [])) > 0)
check("recommended_actions present", len(r.get("recommended_actions", [])) > 0)
check("knowledge_loss_pct > 0", r.get("estimated_knowledge_loss_pct", 0) > 0)
check("nodes have decay_score", all("decay_score" in n for n in r["critical_nodes"]))
print(f"     risk: {r['risk_level']} | loss: {r['estimated_knowledge_loss_pct']}% | nodes: {r['node_count']}")
print(f"     actions[0]: {r['recommended_actions'][0][:70]}")

# ── 9. Departure alert — david ────────────────────────────────────────────────
print("\n[9] GET /risk/departure/david.kim")
s, r = get("/risk/departure/david.kim")
check("status 200", s == 200)
check("risk_level CRITICAL", r.get("risk_level") == "CRITICAL")
print(f"     risk: {r['risk_level']} | domains: {r['domains']}")

# ── 10. Graph ─────────────────────────────────────────────────────────────────
print("\n[10] GET /graph")
s, r = get("/graph")
check("status 200", s == 200)
check("nodes >= 40", r.get("total_nodes", 0) >= 40)
check("edges >= 50", r.get("total_edges", 0) >= 50)
check("nodes have decay_score", all("decay_score" in n for n in r["nodes"]))
check("nodes have color", all("color" in n for n in r["nodes"]))
check("nodes have author_id", all("author_id" in n for n in r["nodes"]))
check("edges have source+target", all("source" in e and "target" in e for e in r["edges"]))
print(f"     nodes: {r['total_nodes']} | edges: {r['total_edges']}")
print(f"     sample: {r['nodes'][0]['title']} decay={r['nodes'][0]['decay_score']} color={r['nodes'][0]['color']}")

# ── 11. Audit log ─────────────────────────────────────────────────────────────
print("\n[11] GET /audit-log")
s, r = get("/audit-log")
check("status 200", s == 200)
check("total_queries >= 2", r.get("total_queries", 0) >= 2)
check("entries present", len(r.get("entries", [])) > 0)
check("entries have confidence", all("confidence" in e for e in r["entries"]))
check("entries have source_nodes", all("source_nodes" in e for e in r["entries"]))
print(f"     total: {r['total_queries']} | avg_confidence: {r['avg_confidence']}")
if r["entries"]:
    print(f"     latest: {r['entries'][0]['query_text'][:60]}")

# ── 12. Compliance tags summary ───────────────────────────────────────────────
print("\n[12] GET /compliance/tags/summary")
s, r = get("/compliance/tags/summary")
check("status 200", s == 200)
check("returns list", isinstance(r, list))
check("has frameworks", len(r) > 0)
print(f"     {r}")

# ── 13. Compliance tags ───────────────────────────────────────────────────────
print("\n[13] GET /compliance/tags")
s, r = get("/compliance/tags")
check("status 200", s == 200)
check("returns list", isinstance(r, list))
check("tags have framework", all("framework" in t for t in r))
print(f"     {len(r)} tags total")

# ── 14. Compliance tags filtered ──────────────────────────────────────────────
print("\n[14] GET /compliance/tags?framework=SOX")
s, r = get("/compliance/tags?framework=SOX")
check("status 200", s == 200)
check("all SOX", all(t["framework"] == "SOX" for t in r))
print(f"     {len(r)} SOX tags: {[t['node_title'] for t in r[:3]]}")

# ── 15. Coverage gaps ─────────────────────────────────────────────────────────
print("\n[15] GET /compliance/gaps")
s, r = get("/compliance/gaps")
check("status 200", s == 200)
check("returns list", isinstance(r, list))
check("gaps tracked", len(r) > 0)
if r:
    print(f"     {len(r)} gaps | top: {r[0]['topic']} gap={r[0]['gap_score']}")

# ── 16. Auto-tag ──────────────────────────────────────────────────────────────
print("\n[16] POST /compliance/tag/auto")
s, r = post("/compliance/tag/auto", {})
check("status 200", s == 200)
check("tagged count present", "tagged" in r)
print(f"     {r}")

# ── 17. Audit chain status ────────────────────────────────────────────────────
print("\n[17] GET /compliance/audit-chain/status")
s, r = get("/compliance/audit-chain/status")
check("status 200", s == 200)
check("chain_intact True", r.get("chain_intact") == True)
check("compliance_status PASS", r.get("compliance_status") == "PASS")
print(f"     entries: {r['total_entries']} | valid: {r['valid_entries']} | intact: {r['chain_intact']}")

# ── 18. Audit chain entries ───────────────────────────────────────────────────
print("\n[18] GET /compliance/audit-chain")
s, r = get("/compliance/audit-chain")
check("status 200", s == 200)
check("returns list", isinstance(r, list))
if r:
    check("entries have entry_hash", all("entry_hash" in e for e in r))
    check("all chain_valid", all(e.get("chain_valid") for e in r))
    print(f"     {len(r)} entries | all valid: {all(e['chain_valid'] for e in r)}")
else:
    print("     (empty)")

# ── Summary ───────────────────────────────────────────────────────────────────
total = PASS + FAIL
print()
print("=" * 60)
print(f"RESULTS: {PASS}/{total} checks passed")
print("=" * 60)
if FAIL == 0:
    print("ALL APIs WORKING AND INTEGRATED SUCCESSFULLY")
else:
    print(f"{FAIL} FAILURES — see above")
    sys.exit(1)
