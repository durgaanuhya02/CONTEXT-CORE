"""
GitHub Real-Time Data Fetcher for ContextCore
----------------------------------------------
Fetches real data from GitHub public repos and builds knowledge_graph.json.

Usage:
    cd contextcore/scripts
    python fetch_github.py

Configure repos in backend/.env:
    GITHUB_TOKEN=ghp_your_token   (optional — raises rate limit from 60 to 5000 req/hr)
    GITHUB_REPOS=owner/repo1,owner/repo2,owner/repo3

No token needed for public repos (60 requests/hour limit).
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent.parent
ENV_FILE = ROOT / "contextcore" / "backend" / ".env"
OUT_FILE = ROOT / "dataset" / "ner_output" / "knowledge_graph.json"
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

LAMBDA = 0.02


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    # Also check real environment
    for k in ("GITHUB_TOKEN", "GITHUB_REPOS"):
        if os.getenv(k):
            env[k] = os.getenv(k)
    return env


ENV = load_env()
GITHUB_TOKEN = ENV.get("GITHUB_TOKEN", "").strip()
REPOS_RAW = ENV.get("GITHUB_REPOS", "microsoft/vscode,facebook/react,vercel/next.js")
REPOS = [r.strip() for r in REPOS_RAW.split(",") if r.strip()]

# ── GitHub API helper ─────────────────────────────────────────────────────────

def gh_get(path: str, params: dict = None) -> dict | list | None:
    url = f"https://api.github.com{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ContextCore-GraphBuilder/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            remaining = r.headers.get("X-RateLimit-Remaining", "?")
            if remaining != "?" and int(remaining) < 5:
                print(f"  ⚠ Rate limit low ({remaining} remaining) — sleeping 10s")
                time.sleep(10)
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"  ✗ Rate limited on {path} — sleeping 30s")
            time.sleep(30)
        elif e.code == 404:
            print(f"  ✗ Not found: {path}")
        else:
            print(f"  ✗ HTTP {e.code} on {path}")
        return None
    except Exception as e:
        print(f"  ✗ Error on {path}: {e}")
        return None


def decay(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        months = (datetime.now(timezone.utc) - created).days / 30.44
        return round(max(0.05, min(1.0, math.exp(-LAMBDA * months))), 4)
    except Exception:
        return 0.75


def months_old(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - created).days / 30.44, 1)
    except Exception:
        return 0.0


def safe_id(s: str) -> str:
    return s.lower().replace(" ", "_").replace("/", "_").replace("-", "_").replace(".", "_")


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph():
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_node(nid: str, label: str, ntype: str, source: str,
                 created_at: str, rationale: str = "", risk: float = 0.0,
                 url: str = "", extra: dict = None):
        if nid in nodes:
            return
        mo = months_old(created_at)
        nodes[nid] = {
            "id": nid,
            "label": label,
            "type": ntype,
            "source": source,
            "files": url,
            "created_at": created_at[:10],
            "months_old": mo,
            "is_stale": mo > 18,
            "decay_score": decay(created_at),
            "risk_score": risk,
            "rationale": rationale,
            **(extra or {}),
        }

    def add_edge(src: str, tgt: str, etype: str, weight: float, rationale: str):
        if src in nodes and tgt in nodes:
            edges.append({
                "source": src, "target": tgt,
                "type": etype, "weight": weight, "rationale": rationale,
            })

    for repo_full in REPOS:
        owner, repo_name = repo_full.split("/", 1)
        print(f"\n{'='*60}")
        print(f"  Fetching: {repo_full}")
        print(f"{'='*60}")

        # ── 1. Repo metadata ──────────────────────────────────────────────────
        repo = gh_get(f"/repos/{repo_full}")
        if not repo:
            print(f"  Skipping {repo_full} — could not fetch")
            continue

        repo_id = safe_id(repo_name)
        repo_created = repo.get("created_at", "2020-01-01")
        repo_updated = repo.get("updated_at", repo_created)
        repo_url = repo.get("html_url", f"https://github.com/{repo_full}")
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        desc = repo.get("description") or f"{repo_name} GitHub repository"
        lang = repo.get("language") or "Unknown"

        print(f"  ✓ Repo: {repo_name} | ⭐{stars} | 🍴{forks} | {lang}")

        add_node(repo_id, repo_name, "PROJECT", "github", repo_updated,
                 rationale=desc, url=repo_url,
                 extra={"stars": stars, "forks": forks, "description": desc})

        # ── 2. Languages ──────────────────────────────────────────────────────
        langs = gh_get(f"/repos/{repo_full}/languages") or {}
        for lang_name, bytes_count in list(langs.items())[:5]:
            lang_id = safe_id(lang_name)
            add_node(lang_id, lang_name, "TECHNOLOGY", "github", repo_created,
                     rationale=f"{lang_name} used in {repo_name}", url=repo_url)
            add_edge(repo_id, lang_id, "USES", 0.9,
                     f"{repo_name} is primarily written in {lang_name}")
        print(f"  ✓ Languages: {list(langs.keys())[:5]}")

        # ── 3. Top contributors ───────────────────────────────────────────────
        contributors = gh_get(f"/repos/{repo_full}/contributors",
                               {"per_page": "10", "anon": "false"}) or []
        contributor_ids = []
        for c in contributors[:8]:
            if not isinstance(c, dict) or c.get("type") == "Bot":
                continue
            login = c.get("login", "")
            if not login:
                continue
            cid = f"gh_{safe_id(login)}"
            contributions = c.get("contributions", 0)
            risk = min(0.95, contributions / max(sum(x.get("contributions", 1) for x in contributors[:8]), 1))

            # Fetch user profile for real name
            user = gh_get(f"/users/{login}") or {}
            display_name = user.get("name") or login
            joined = user.get("created_at", repo_created)

            add_node(cid, display_name, "PERSON", "github", joined,
                     rationale=f"{display_name} has {contributions} contributions to {repo_name}",
                     risk=round(risk, 2), url=f"https://github.com/{login}",
                     extra={"github_login": login, "contributions": contributions})
            contributor_ids.append(cid)
            add_edge(cid, repo_id, "OWNS", round(risk, 2),
                     f"{display_name} is a top contributor to {repo_name} ({contributions} commits)")

        print(f"  ✓ Contributors: {len(contributor_ids)}")

        # ── 4. Recent PRs ─────────────────────────────────────────────────────
        prs = gh_get(f"/repos/{repo_full}/pulls",
                     {"state": "closed", "sort": "updated", "per_page": "15"}) or []
        pr_count = 0
        for pr in prs[:12]:
            if not isinstance(pr, dict):
                continue
            pr_num = pr.get("number")
            pr_title = (pr.get("title") or "")[:80]
            pr_user = pr.get("user", {}).get("login", "unknown")
            pr_created = pr.get("created_at", repo_created)
            pr_merged = pr.get("merged_at") or pr.get("closed_at") or pr_created
            pr_url = pr.get("html_url", "")
            pr_body = (pr.get("body") or "")[:200]

            pr_id = f"pr_{repo_id}_{pr_num}"
            add_node(pr_id, f"PR #{pr_num}: {pr_title}", "DECISION", "github",
                     pr_merged, rationale=pr_body or pr_title, url=pr_url)
            add_edge(pr_id, repo_id, "SUPPORTS", 0.8,
                     f"PR #{pr_num} contributes to {repo_name}")

            # Link PR author to PR
            author_id = f"gh_{safe_id(pr_user)}"
            if author_id in nodes:
                add_edge(author_id, pr_id, "MADE_BY", 1.0,
                         f"{pr_user} opened PR #{pr_num}")
            pr_count += 1

        print(f"  ✓ PRs: {pr_count}")

        # ── 5. Recent issues / discussions ────────────────────────────────────
        issues = gh_get(f"/repos/{repo_full}/issues",
                        {"state": "closed", "sort": "updated",
                         "per_page": "15", "labels": ""}) or []
        issue_count = 0
        for issue in issues[:10]:
            if not isinstance(issue, dict):
                continue
            if issue.get("pull_request"):
                continue  # skip PRs listed as issues
            inum = issue.get("number")
            ititle = (issue.get("title") or "")[:80]
            iuser = issue.get("user", {}).get("login", "unknown")
            icreated = issue.get("created_at", repo_created)
            iurl = issue.get("html_url", "")
            ibody = (issue.get("body") or "")[:200]
            labels = [l.get("name", "") for l in issue.get("labels", [])]

            # Only include issues that look like decisions/discussions
            decision_labels = {"decision", "adr", "rfc", "design", "architecture",
                               "enhancement", "feature", "discussion"}
            is_decision = any(l.lower() in decision_labels for l in labels) or \
                          any(kw in ititle.lower() for kw in
                              ["decision", "rfc", "adr", "design", "proposal",
                               "architecture", "deprecat", "migration", "refactor"])

            itype = "DECISION" if is_decision else "CONCEPT"
            iid = f"issue_{repo_id}_{inum}"
            add_node(iid, f"Issue #{inum}: {ititle}", itype, "github",
                     icreated, rationale=ibody or ititle, url=iurl)
            add_edge(iid, repo_id, "RELATED_TO", 0.7,
                     f"Issue #{inum} relates to {repo_name}")

            author_id = f"gh_{safe_id(iuser)}"
            if author_id in nodes:
                add_edge(author_id, iid, "PARTICIPATED_IN", 0.8,
                         f"{iuser} opened issue #{inum}")
            issue_count += 1

        print(f"  ✓ Issues: {issue_count}")

        # ── 6. Releases / tags ────────────────────────────────────────────────
        releases = gh_get(f"/repos/{repo_full}/releases",
                          {"per_page": "5"}) or []
        for rel in releases[:4]:
            if not isinstance(rel, dict):
                continue
            rtag = rel.get("tag_name", "")
            rname = rel.get("name") or rtag
            rcreated = rel.get("published_at") or rel.get("created_at", repo_created)
            rurl = rel.get("html_url", "")
            rbody = (rel.get("body") or "")[:200]
            rid = f"release_{repo_id}_{safe_id(rtag)}"
            add_node(rid, f"Release {rname}", "DECISION", "github",
                     rcreated, rationale=rbody or f"Release {rname} of {repo_name}",
                     url=rurl)
            add_edge(rid, repo_id, "SUPPORTS", 0.9,
                     f"Release {rname} is a milestone of {repo_name}")

        print(f"  ✓ Releases: {len(releases[:4])}")

        # ── 7. Topics / tags as concepts ─────────────────────────────────────
        topics_data = gh_get(f"/repos/{repo_full}/topics") or {}
        topics = topics_data.get("names", [])
        for topic in topics[:6]:
            tid = safe_id(topic)
            add_node(tid, topic.replace("-", " ").title(), "CONCEPT", "github",
                     repo_created, rationale=f"{topic} is a topic of {repo_name}",
                     url=f"https://github.com/topics/{topic}")
            add_edge(repo_id, tid, "RELATED_TO", 0.6,
                     f"{repo_name} is tagged with topic: {topic}")

        print(f"  ✓ Topics: {topics[:6]}")

        # ── 8. Dependencies from package.json / requirements.txt / go.mod ────
        dep_files = [
            ("package.json", "npm"),
            ("requirements.txt", "pip"),
            ("go.mod", "go"),
            ("Cargo.toml", "cargo"),
            ("pom.xml", "maven"),
        ]
        dep_count = 0
        for dep_file, ecosystem in dep_files:
            content_data = gh_get(f"/repos/{repo_full}/contents/{dep_file}")
            if not content_data or not isinstance(content_data, dict):
                continue
            import base64
            try:
                raw = base64.b64decode(content_data.get("content", "")).decode("utf-8", errors="ignore")
            except Exception:
                continue

            deps = []
            if dep_file == "package.json":
                try:
                    pkg = json.loads(raw)
                    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    deps = list(all_deps.keys())[:8]
                except Exception:
                    pass
            elif dep_file == "requirements.txt":
                deps = [line.split("==")[0].split(">=")[0].strip()
                        for line in raw.splitlines()
                        if line.strip() and not line.startswith("#")][:8]
            elif dep_file == "go.mod":
                for line in raw.splitlines():
                    if line.strip().startswith("require") or "\t" in line:
                        parts = line.strip().split()
                        if parts and "/" in parts[0]:
                            deps.append(parts[0].split("/")[-1])
                deps = deps[:8]

            for dep in deps:
                dep_id = safe_id(dep)
                add_node(dep_id, dep, "TECHNOLOGY", "github", repo_created,
                         rationale=f"{dep} is a dependency of {repo_name} ({ecosystem})",
                         url=f"https://github.com/search?q={dep}")
                add_edge(repo_id, dep_id, "USES", 0.85,
                         f"{repo_name} depends on {dep} ({ecosystem})")
                dep_count += 1
            if deps:
                break  # found one dep file, stop

        print(f"  ✓ Dependencies: {dep_count}")

    # ── Compute degree stats ──────────────────────────────────────────────────
    in_deg: dict[str, int] = {nid: 0 for nid in nodes}
    out_deg: dict[str, int] = {nid: 0 for nid in nodes}
    for e in edges:
        out_deg[e["source"]] = out_deg.get(e["source"], 0) + 1
        in_deg[e["target"]] = in_deg.get(e["target"], 0) + 1

    node_list = []
    for nid, n in nodes.items():
        n["degree"] = in_deg.get(nid, 0) + out_deg.get(nid, 0)
        n["in_degree"] = in_deg.get(nid, 0)
        n["out_degree"] = out_deg.get(nid, 0)
        node_list.append(n)

    # ── Stats ─────────────────────────────────────────────────────────────────
    type_counts: dict[str, int] = {}
    edge_type_counts: dict[str, int] = {}
    for n in node_list:
        type_counts[n["type"]] = type_counts.get(n["type"], 0) + 1
    for e in edges:
        edge_type_counts[e["type"]] = edge_type_counts.get(e["type"], 0) + 1

    graph = {
        "nodes": node_list,
        "edges": edges,
        "stats": {
            "total_nodes": len(node_list),
            "total_edges": len(edges),
            "node_types": type_counts,
            "edge_types": edge_type_counts,
            "generated_at": datetime.now().isoformat(),
            "repos": REPOS,
        },
    }

    OUT_FILE.write_text(json.dumps(graph, indent=2))
    print(f"\n{'='*60}")
    print(f"  ✓ Graph written to {OUT_FILE}")
    print(f"  Nodes: {len(node_list)} | Edges: {len(edges)}")
    print(f"  Node types: {type_counts}")
    print(f"  Edge types: {edge_type_counts}")
    print(f"{'='*60}")
    return graph


if __name__ == "__main__":
    if not REPOS:
        print("No repos configured. Set GITHUB_REPOS in backend/.env")
        sys.exit(1)
    print(f"ContextCore GitHub Fetcher")
    print(f"Repos: {REPOS}")
    print(f"Token: {'✓ set' if GITHUB_TOKEN else '✗ not set (60 req/hr limit)'}")
    build_graph()
