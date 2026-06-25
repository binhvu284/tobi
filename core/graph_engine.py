"""Graph engine — the unified second-brain knowledge graph.

One node/edge store (see core/database._ensure_graph_schema) unifies internal domains
(memory / task / project) and read-only integration mirrors (notion / github / gdrive /
local). This module owns all graph DB operations plus the build logic: internal sync,
semantic + tag + ref edges, degree, filtered retrieval, expand, and search.

Embeddings are reused from the Brain (core/embeddings, local fastembed). Every node gets
an embedding so cross-domain semantic edges = top-k cosine above a threshold, capped per
node to avoid a hairball. Everything degrades gracefully: no embeddings → no semantic
edges (ref/tag still work); no integration key → that source is simply skipped.
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from core.database import get_connection
from core import embeddings as emb

logger = logging.getLogger(__name__)

# ── Tunables ──────────────────────────────────────────────────────────────────
# Anti-hairball: graphify runs ~2 edges/node. We keep edges sparse + meaningful
# (ref + a few strong semantic links) and let community clustering + a centroid
# force convey grouping — NOT dense all-pairs tag edges (that is what hairballs).
SEM_THRESHOLD = 0.70      # min cosine for a semantic edge — tuned so homogeneous personal
SEM_TOPK = 4              # facts split into distinct communities (not one dense blob)
COMMUNITY_ITERS = 8       # label-propagation passes

INTERNAL_DOMAINS = ("memory", "task", "project")

# Tableau-10 palette (graphify's), cycled by community id → the multi-cluster look.
COMMUNITY_PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

# Domain → default visual (color + lucide icon). Memory/project may override color
# from their own category/accent. Frontend reads these straight through.
DOMAIN_META = {
    "memory":  {"color": "#a78bfa", "icon": "Brain"},
    "task":    {"color": "#58a6ff", "icon": "CheckSquare"},
    "project": {"color": "#22d3ee", "icon": "Briefcase"},
    "notion":  {"color": "#e5e7eb", "icon": "FileText"},
    "github":  {"color": "#8b949e", "icon": "Github"},
    "gdrive":  {"color": "#34d399", "icon": "HardDrive"},
    "local":   {"color": "#f59e0b", "icon": "Folder"},
    "manual":  {"color": "#f472b6", "icon": "Sparkles"},
}


# ── low-level node/edge ops ───────────────────────────────────────────────────
def upsert_node(domain: str, ref_id, title: str, *, ref_kind: Optional[str] = None,
                summary: Optional[str] = None, category: Optional[str] = None,
                color: Optional[str] = None, icon: Optional[str] = None,
                source_url: Optional[str] = None, embedding: Optional[bytes] = "__auto__") -> int:
    """Insert or update a node keyed on (domain, ref_id). Returns the node id.
    `embedding='__auto__'` (default) embeds title+summary; pass a BLOB to reuse one
    (e.g. a memory's existing vector), or None to skip embedding."""
    meta = DOMAIN_META.get(domain, {})
    color = color or meta.get("color")
    icon = icon or meta.get("icon")
    if embedding == "__auto__":
        text = f"{title}\n{summary or ''}".strip()
        embedding = emb.to_blob(emb.embed_one(text)) if text else None
    model = emb.MODEL_NAME if embedding else None
    ref_id = str(ref_id)
    conn = get_connection()
    conn.execute(
        """INSERT INTO graph_nodes
              (domain, ref_kind, ref_id, title, summary, category, color, icon,
               source_url, embedding, embed_model, updated_at, deleted_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,NULL)
           ON CONFLICT(domain, ref_id) DO UPDATE SET
              ref_kind=excluded.ref_kind, title=excluded.title, summary=excluded.summary,
              category=excluded.category, color=excluded.color, icon=excluded.icon,
              source_url=excluded.source_url, embedding=excluded.embedding,
              embed_model=excluded.embed_model, updated_at=CURRENT_TIMESTAMP, deleted_at=NULL""",
        (domain, ref_kind, ref_id, title, summary, category, color, icon,
         source_url, embedding, model),
    )
    row = conn.execute("SELECT id FROM graph_nodes WHERE domain=? AND ref_id=?",
                       (domain, ref_id)).fetchone()
    conn.commit()
    conn.close()
    return row["id"]


def upsert_edge(source_id: int, target_id: int, edge_type: str = "ref",
                weight: float = 1.0, directed: int = 0, created_by: str = "system") -> Optional[int]:
    if not source_id or not target_id or source_id == target_id:
        return None
    # Undirected edges are stored with a stable orientation so (a,b)==(b,a) dedupes.
    if not directed and source_id > target_id:
        source_id, target_id = target_id, source_id
    conn = get_connection()
    conn.execute(
        """INSERT INTO graph_edges (source_id, target_id, edge_type, weight, directed, created_by, deleted_at)
           VALUES (?,?,?,?,?,?,NULL)
           ON CONFLICT(source_id, target_id, edge_type) DO UPDATE SET
              weight=excluded.weight, directed=excluded.directed, deleted_at=NULL""",
        (source_id, target_id, edge_type, weight, directed, created_by),
    )
    row = conn.execute(
        "SELECT id FROM graph_edges WHERE source_id=? AND target_id=? AND edge_type=?",
        (source_id, target_id, edge_type)).fetchone()
    conn.commit()
    conn.close()
    return row["id"] if row else None


def create_manual_node(title: str, summary: Optional[str] = None,
                       category: Optional[str] = None, domain: str = "manual") -> dict:
    """Owner-created node from the graph UI. Gets a unique ref_id + an embedding."""
    import uuid
    nid = upsert_node(domain, uuid.uuid4().hex, title, summary=summary, category=category)
    return get_node(nid)


def update_node(node_id: int, title: Optional[str] = None, summary: Optional[str] = None,
                category: Optional[str] = None) -> Optional[dict]:
    """Edit a node's content from the graph. Re-embeds when text changes."""
    cur = get_node(node_id)
    if not cur:
        return None
    title = title if title is not None else cur["title"]
    summary = summary if summary is not None else cur.get("summary")
    category = category if category is not None else cur.get("category")
    blob = emb.to_blob(emb.embed_one(f"{title}\n{summary or ''}".strip()))
    conn = get_connection()
    conn.execute(
        """UPDATE graph_nodes SET title=?, summary=?, category=?, embedding=?, embed_model=?,
              updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (title, summary, category, blob, emb.MODEL_NAME if blob else None, node_id),
    )
    conn.commit()
    conn.close()
    return get_node(node_id)


def delete_node(node_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE graph_nodes SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", (node_id,))
    conn.execute("UPDATE graph_edges SET deleted_at=CURRENT_TIMESTAMP WHERE source_id=? OR target_id=?",
                 (node_id, node_id))
    conn.commit()
    conn.close()


def delete_edge(edge_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE graph_edges SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", (edge_id,))
    conn.commit()
    conn.close()


def get_node(node_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM graph_nodes WHERE id=? AND deleted_at IS NULL", (node_id,)).fetchone()
    conn.close()
    return _node_dict(row) if row else None


def _node_dict(r) -> dict:
    d = dict(r)
    d.pop("embedding", None)
    d["has_embedding"] = bool(r["embedding"]) if "embedding" in r.keys() else False
    return d


def _edge_dict(r) -> dict:
    return {"id": r["id"], "source": r["source_id"], "target": r["target_id"],
            "type": r["edge_type"], "weight": r["weight"], "directed": r["directed"],
            "created_by": r["created_by"]}


# ── degree ────────────────────────────────────────────────────────────────────
def recompute_degree() -> None:
    conn = get_connection()
    conn.execute("UPDATE graph_nodes SET degree=0 WHERE deleted_at IS NULL")
    conn.execute("""
        UPDATE graph_nodes SET degree = (
            SELECT COUNT(*) FROM graph_edges e
            WHERE e.deleted_at IS NULL
              AND (e.source_id = graph_nodes.id OR e.target_id = graph_nodes.id)
        ) WHERE deleted_at IS NULL
    """)
    conn.commit()
    conn.close()


# ── internal sync (memory / task / project) ──────────────────────────────────
def _brain_category_colors() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT id, color FROM brain_categories").fetchall()
    conn.close()
    return {r["id"]: r["color"] for r in rows}


def sync_internal() -> dict:
    """Register/refresh memory/task/project nodes from existing tables + ref edges.
    Prunes internal nodes whose source row vanished. Returns per-domain counts."""
    cat_colors = _brain_category_colors()
    counts = {"memory": 0, "task": 0, "project": 0}
    seen: dict[str, set] = {"memory": set(), "task": set(), "project": set()}

    # Read EVERYTHING up front, then close the connection BEFORE any upsert. upsert_node/
    # upsert_edge each open their own short-lived connection, so we must never hold a read
    # connection open across them (that nesting is what triggers "database is locked").
    conn = get_connection()
    projects = conn.execute(
        "SELECT id, name, description, category, accent_color FROM pm_projects").fetchall()
    memories = conn.execute(
        "SELECT id, content, category, embedding FROM brain_memories "
        "WHERE status='active' AND deleted_at IS NULL").fetchall()
    tasks = conn.execute(
        "SELECT id, title, objective, description, status_v1, status, pm_project_id "
        "FROM tasks WHERE deleted_at IS NULL").fetchall()
    conn.close()

    # Projects first (so tasks can ref them) → map pm_project_id → graph node id
    proj_node: dict[str, int] = {}
    for r in projects:
        nid = upsert_node("project", r["id"], r["name"] or f"Project {r['id']}",
                          summary=r["description"], category=r["category"],
                          color=r["accent_color"])
        proj_node[str(r["id"])] = nid
        seen["project"].add(str(r["id"])); counts["project"] += 1

    # Memories — reuse the stored embedding; if missing (created before embeddings were
    # available), re-embed now so semantic edges can form (collect for a Brain backfill).
    backfill: dict[int, bytes] = {}
    for r in memories:
        content = r["content"] or ""
        blob = r["embedding"]
        if not blob and content and emb.is_available():
            blob = emb.to_blob(emb.embed_one(content))
            if blob:
                backfill[r["id"]] = blob
        upsert_node("memory", r["id"], content[:80] or f"Memory {r['id']}",
                    summary=content, category=r["category"],
                    color=cat_colors.get(r["category"]), embedding=blob if blob else "__auto__")
        seen["memory"].add(str(r["id"])); counts["memory"] += 1

    # Tasks — ref edge to its PM project
    for r in tasks:
        summary = r["objective"] or r["description"] or ""
        nid = upsert_node("task", r["id"], r["title"] or f"Task {r['id']}",
                          summary=summary, category=(r["status_v1"] or r["status"]))
        seen["task"].add(str(r["id"])); counts["task"] += 1
        pmid = r["pm_project_id"]
        if pmid is not None and str(pmid) in proj_node:
            upsert_edge(nid, proj_node[str(pmid)], "ref", weight=1.0)

    # Prune internal nodes whose source row disappeared
    pruned = 0
    conn = get_connection()
    for dom in INTERNAL_DOMAINS:
        rows = conn.execute(
            "SELECT id, ref_id FROM graph_nodes WHERE domain=? AND deleted_at IS NULL", (dom,)
        ).fetchall()
        for row in rows:
            if row["ref_id"] not in seen[dom]:
                conn.execute("UPDATE graph_nodes SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
                conn.execute("UPDATE graph_edges SET deleted_at=CURRENT_TIMESTAMP "
                             "WHERE source_id=? OR target_id=?", (row["id"], row["id"]))
                pruned += 1
    conn.commit()
    conn.close()
    counts["pruned"] = pruned

    # Brain embedding backfill (separate connection → no lock with the read pass above).
    if backfill:
        bc = get_connection()
        for mid, blob in backfill.items():
            bc.execute("UPDATE brain_memories SET embedding=?, embed_model=? WHERE id=?",
                       (blob, emb.MODEL_NAME, mid))
        bc.commit(); bc.close()
        counts["embedded"] = len(backfill)
    return counts


# ── derived edges ─────────────────────────────────────────────────────────────
def _active_node_vectors() -> list[tuple[int, object]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, embedding FROM graph_nodes WHERE deleted_at IS NULL AND embedding IS NOT NULL"
    ).fetchall()
    conn.close()
    return [(r["id"], emb.from_blob(r["embedding"])) for r in rows]


def build_semantic_edges() -> int:
    """Top-k cosine per node (capped, thresholded) → undirected 'semantic' edges.
    Clears prior semantic edges first so it stays idempotent."""
    if not emb.is_available():
        return 0
    cands = _active_node_vectors()
    if len(cands) < 2:
        return 0
    conn = get_connection()
    conn.execute("UPDATE graph_edges SET deleted_at=CURRENT_TIMESTAMP WHERE edge_type='semantic'")
    conn.commit()
    conn.close()
    made = 0
    for nid, vec in cands:
        if vec is None:
            continue
        others = [(oid, ov) for (oid, ov) in cands if oid != nid]
        top = emb.cosine_topk(vec, others, k=SEM_TOPK, min_score=SEM_THRESHOLD)
        for oid, score in top:
            if upsert_edge(nid, oid, "semantic", weight=round(float(score), 3)):
                made += 1
    return made


def clear_tag_edges() -> int:
    """Remove the legacy all-pairs 'tag' edges — they create hairballs. Category grouping
    is now conveyed by community color + hull + the frontend centroid force instead."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE graph_edges SET deleted_at=CURRENT_TIMESTAMP WHERE edge_type='tag' AND deleted_at IS NULL")
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


# ── community detection (label propagation) ──────────────────────────────────
def detect_communities() -> dict:
    """Assign each node a community via label propagation over ref+semantic edges
    (isolated nodes fall back to their domain+category). Communities are renumbered
    by size, given a Tableau color + a derived label, and the color is written onto
    the node so the frontend renders the graphify-style multi-cluster look."""
    conn = get_connection()
    nodes = conn.execute(
        "SELECT id, domain, category, title, degree FROM graph_nodes WHERE deleted_at IS NULL").fetchall()
    edges = conn.execute(
        "SELECT source_id, target_id FROM graph_edges "
        "WHERE deleted_at IS NULL AND edge_type IN ('ref','semantic','manual')").fetchall()
    conn.close()
    if not nodes:
        return {"communities": 0, "nodes": 0}

    adj: dict[int, list[int]] = {n["id"]: [] for n in nodes}
    for e in edges:
        if e["source_id"] in adj and e["target_id"] in adj:
            adj[e["source_id"]].append(e["target_id"])
            adj[e["target_id"]].append(e["source_id"])

    # seed label: own id; isolated nodes seed by domain:category so they still group
    label: dict[int, str] = {}
    fallback: dict[int, str] = {}
    for n in nodes:
        fb = f"{n['domain']}:{n['category'] or n['domain']}"
        fallback[n["id"]] = fb
        label[n["id"]] = fb if not adj[n["id"]] else f"n{n['id']}"

    import random
    ids = [n["id"] for n in nodes]
    for _ in range(COMMUNITY_ITERS):
        random.shuffle(ids)
        changed = False
        for nid in ids:
            neigh = adj[nid]
            if not neigh:
                continue
            counts: dict[str, int] = {}
            for m in neigh:
                counts[label[m]] = counts.get(label[m], 0) + 1
            best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if best != label[nid]:
                label[nid] = best; changed = True
        if not changed:
            break

    # group → renumber by size desc
    groups: dict[str, list[int]] = {}
    for nid, lab in label.items():
        groups.setdefault(lab, []).append(nid)
    ordered = sorted(groups.values(), key=len, reverse=True)

    title_by = {n["id"]: n["title"] for n in nodes}
    cat_by = {n["id"]: (n["category"] or n["domain"]) for n in nodes}
    deg_by = {n["id"]: (n["degree"] or 0) for n in nodes}

    conn = get_connection()
    for cid, members in enumerate(ordered):
        color = COMMUNITY_PALETTE[cid % len(COMMUNITY_PALETTE)]
        # label = dominant category + the highest-degree member's title (a "god node")
        cats: dict[str, int] = {}
        for m in members:
            cats[cat_by[m]] = cats.get(cat_by[m], 0) + 1
        dom_cat = max(cats.items(), key=lambda kv: kv[1])[0]
        hub = max(members, key=lambda m: deg_by[m])
        clabel = f"{dom_cat} · {title_by[hub][:24]}" if len(members) > 1 else (title_by[hub][:28] or dom_cat)
        for m in members:
            conn.execute(
                "UPDATE graph_nodes SET community=?, community_label=?, color=? WHERE id=?",
                (cid, clabel, color, m))
    conn.commit()
    conn.close()
    return {"communities": len(ordered), "nodes": len(nodes)}


def list_communities() -> list[dict]:
    """Legend data: community id, label, color, size — ordered by size (graphify style)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT community AS cid, community_label AS label, color, COUNT(*) AS count
           FROM graph_nodes WHERE deleted_at IS NULL AND community IS NOT NULL
           GROUP BY community ORDER BY count DESC""").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── retrieval ─────────────────────────────────────────────────────────────────
def get_graph(domain: Optional[str] = None, category: Optional[str] = None,
              q: Optional[str] = None, min_weight: float = 0.0,
              date_from: Optional[str] = None, date_to: Optional[str] = None,
              limit: int = 4000) -> dict:
    """Filtered {nodes, edges}. 'domain' may be a single domain or None/'all'. Edges are
    those whose both endpoints survive the node filter and weight >= min_weight."""
    conn = get_connection()
    where = ["deleted_at IS NULL"]
    params: list = []
    if domain and domain != "all":
        where.append("domain = ?"); params.append(domain)
    if category:
        where.append("category = ?"); params.append(category)
    if q:
        where.append("(title LIKE ? OR summary LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if date_from:
        where.append("created_at >= ?"); params.append(date_from)
    if date_to:
        where.append("created_at <= ?"); params.append(date_to)
    node_rows = conn.execute(
        f"SELECT * FROM graph_nodes WHERE {' AND '.join(where)} ORDER BY degree DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    nodes = [_node_dict(r) for r in node_rows]
    ids = {n["id"] for n in nodes}
    edges = []
    if ids:
        placeholders = ",".join("?" for _ in ids)
        edge_rows = conn.execute(
            f"""SELECT * FROM graph_edges
                WHERE deleted_at IS NULL AND weight >= ?
                  AND source_id IN ({placeholders}) AND target_id IN ({placeholders})""",
            (min_weight, *ids, *ids),
        ).fetchall()
        edges = [_edge_dict(r) for r in edge_rows]
    conn.close()
    return {"nodes": nodes, "edges": edges}


def expand(node_id: int) -> dict:
    """Immediate neighbourhood of a node (for progressive load)."""
    conn = get_connection()
    edge_rows = conn.execute(
        "SELECT * FROM graph_edges WHERE deleted_at IS NULL AND (source_id=? OR target_id=?)",
        (node_id, node_id),
    ).fetchall()
    neighbour_ids = set()
    for e in edge_rows:
        neighbour_ids.add(e["source_id"]); neighbour_ids.add(e["target_id"])
    neighbour_ids.add(node_id)
    nodes = []
    if neighbour_ids:
        placeholders = ",".join("?" for _ in neighbour_ids)
        rows = conn.execute(
            f"SELECT * FROM graph_nodes WHERE id IN ({placeholders}) AND deleted_at IS NULL",
            tuple(neighbour_ids),
        ).fetchall()
        nodes = [_node_dict(r) for r in rows]
    conn.close()
    return {"nodes": nodes, "edges": [_edge_dict(e) for e in edge_rows]}


def search(q: str, k: int = 12) -> dict:
    """Keyword + semantic search → ranked node ids (for highlight + fly-to)."""
    q = (q or "").strip()
    if not q:
        return {"results": [], "mode": "none"}
    conn = get_connection()
    kw_rows = conn.execute(
        "SELECT id, title, domain FROM graph_nodes WHERE deleted_at IS NULL "
        "AND (title LIKE ? OR summary LIKE ?) LIMIT ?",
        (f"%{q}%", f"%{q}%", k),
    ).fetchall()
    results = [{"id": r["id"], "title": r["title"], "domain": r["domain"], "score": 1.0}
               for r in kw_rows]
    mode = "keyword"
    if emb.is_available():
        qv = emb.embed_one(q)
        if qv is not None:
            cands = _active_node_vectors()
            top = emb.cosine_topk(qv, cands, k=k, min_score=0.4)
            have = {r["id"] for r in results}
            id_meta = {r["id"]: (r["title"], r["domain"]) for r in conn.execute(
                "SELECT id, title, domain FROM graph_nodes WHERE deleted_at IS NULL").fetchall()}
            for nid, score in top:
                if nid in have or nid not in id_meta:
                    continue
                t, d = id_meta[nid]
                results.append({"id": nid, "title": t, "domain": d, "score": round(float(score), 3)})
            mode = "semantic+keyword"
    conn.close()
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"results": results[:k], "mode": mode}


# ── GraphRAG: graph-aware retrieval for the AI brain ─────────────────────────
def _adjacency(weighted: bool = True) -> dict[int, list[tuple[int, float]]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT source_id, target_id, weight FROM graph_edges WHERE deleted_at IS NULL").fetchall()
    conn.close()
    adj: dict[int, list[tuple[int, float]]] = {}
    for r in rows:
        w = (r["weight"] or 1.0) if weighted else 1.0
        adj.setdefault(r["source_id"], []).append((r["target_id"], w))
        adj.setdefault(r["target_id"], []).append((r["source_id"], w))
    return adj


def neighbors(node_id: int, depth: int = 1, limit: int = 60) -> dict:
    """Multi-hop neighbourhood (BFS to `depth`) — the local subgraph around a node."""
    adj = _adjacency()
    seen = {node_id}
    frontier = [node_id]
    for _ in range(max(1, depth)):
        nxt = []
        for n in frontier:
            for m, _w in adj.get(n, []):
                if m not in seen:
                    seen.add(m); nxt.append(m)
                    if len(seen) >= limit:
                        break
            if len(seen) >= limit:
                break
        frontier = nxt
        if not frontier or len(seen) >= limit:
            break
    conn = get_connection()
    ph = ",".join("?" for _ in seen)
    nodes = [_node_dict(r) for r in conn.execute(
        f"SELECT * FROM graph_nodes WHERE id IN ({ph}) AND deleted_at IS NULL", tuple(seen)).fetchall()]
    edges = [_edge_dict(r) for r in conn.execute(
        f"SELECT * FROM graph_edges WHERE deleted_at IS NULL AND source_id IN ({ph}) AND target_id IN ({ph})",
        (*seen, *seen)).fetchall()]
    conn.close()
    return {"nodes": nodes, "edges": edges}


def find_path(a: int, b: int, max_depth: int = 7) -> list[dict]:
    """Shortest path between two nodes (BFS) → ordered node dicts. The 'how are X and Y
    connected?' query that flat vector search can't answer."""
    if a == b:
        n = get_node(a); return [n] if n else []
    adj = _adjacency(weighted=False)
    from collections import deque
    prev: dict[int, int] = {a: a}
    q = deque([a]); depth = {a: 0}
    found = False
    while q:
        cur = q.popleft()
        if depth[cur] >= max_depth:
            continue
        for m, _w in adj.get(cur, []):
            if m not in prev:
                prev[m] = cur; depth[m] = depth[cur] + 1
                if m == b:
                    found = True; q.clear(); break
                q.append(m)
        if found:
            break
    if b not in prev:
        return []
    chain = [b]
    while chain[-1] != a:
        chain.append(prev[chain[-1]])
    chain.reverse()
    conn = get_connection()
    out = []
    for nid in chain:
        r = conn.execute("SELECT * FROM graph_nodes WHERE id=?", (nid,)).fetchone()
        if r:
            out.append(_node_dict(r))
    conn.close()
    return out


def graph_retrieve(query: str, k: int = 8, hops: int = 1, spread: float = 0.5) -> list[dict]:
    """GraphRAG retrieval: seed by embedding similarity, then **spreading activation** —
    propagate relevance across edges (weighted) for `hops`. Final score blends semantic
    similarity with graph proximity, so the agent surfaces *connected* context a flat
    top-k cosine would miss. Falls back to plain semantic/keyword when embeddings are off.
    """
    query = (query or "").strip()
    if not query:
        return []
    seeds = search(query, k=max(4, k))["results"][:max(3, k // 2)]
    if not seeds:
        return []
    activation: dict[int, float] = {}
    for s in seeds:
        activation[s["id"]] = max(activation.get(s["id"], 0.0), float(s.get("score", 0.5)))
    adj = _adjacency()
    # spreading activation: each hop pushes a fraction of activation to neighbours
    frontier = dict(activation)
    for _ in range(max(0, hops)):
        nxt: dict[int, float] = {}
        for nid, act in frontier.items():
            nbrs = adj.get(nid, [])
            if not nbrs:
                continue
            total = sum(w for _m, w in nbrs) or 1.0
            for m, w in nbrs:
                add = act * spread * (w / total)
                if add > 0.02:
                    nxt[m] = max(nxt.get(m, 0.0), add)
        for m, a in nxt.items():
            activation[m] = activation.get(m, 0.0) + a
        frontier = nxt
        if not frontier:
            break
    top = sorted(activation.items(), key=lambda kv: kv[1], reverse=True)[:k]
    if not top:
        return []
    conn = get_connection()
    ph = ",".join("?" for _ in top)
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT * FROM graph_nodes WHERE id IN ({ph}) AND deleted_at IS NULL", tuple(t[0] for t in top)).fetchall()}
    conn.close()
    out = []
    for nid, score in top:
        if nid in rows:
            d = _node_dict(rows[nid]); d["score"] = round(score, 3); out.append(d)
    return out


def graph_context(query: str, k: int = 6) -> str:
    """Compact, prompt-ready block of graph-connected facts for the AI brain. Empty string
    when the graph is empty so callers can inject unconditionally."""
    hits = graph_retrieve(query, k=k, hops=1)
    if not hits:
        return ""
    lines = []
    for h in hits:
        label = h.get("community_label") or h.get("domain", "")
        lines.append(f"- ({label}) {h.get('title','')}: {(h.get('summary') or '')[:160]}".rstrip())
    return "Connected knowledge (graph):\n" + "\n".join(lines)


# ── positions / pins ──────────────────────────────────────────────────────────
def save_positions(pins: list[dict]) -> int:
    """pins = [{id, x, y, pinned}]. Persists manual pin positions; the rest auto-layout."""
    conn = get_connection()
    n = 0
    for p in pins:
        conn.execute(
            "UPDATE graph_nodes SET x=?, y=?, pinned=? WHERE id=?",
            (p.get("x"), p.get("y"), 1 if p.get("pinned") else 0, p["id"]),
        )
        n += 1
    conn.commit()
    conn.close()
    return n


# ── timeline ──────────────────────────────────────────────────────────────────
def timeline_events(date_from: Optional[str] = None, date_to: Optional[str] = None) -> list[dict]:
    """Node-creation events (ts, id, domain) for the growth scrubber, oldest first."""
    conn = get_connection()
    where = ["deleted_at IS NULL"]
    params: list = []
    if date_from:
        where.append("created_at >= ?"); params.append(date_from)
    if date_to:
        where.append("created_at <= ?"); params.append(date_to)
    rows = conn.execute(
        f"SELECT id, domain, created_at FROM graph_nodes WHERE {' AND '.join(where)} ORDER BY created_at ASC",
        params,
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "domain": r["domain"], "ts": r["created_at"]} for r in rows]


# ── sync-state ────────────────────────────────────────────────────────────────
def get_sources() -> list[dict]:
    """Per-source sync status + availability (for the UI source list)."""
    from core.integrations import check_all
    avail = {}
    try:
        avail = check_all()
    except Exception:
        pass
    conn = get_connection()
    state = {r["source"]: dict(r) for r in conn.execute("SELECT * FROM graph_sync_state").fetchall()}
    counts = {r["domain"]: r["c"] for r in conn.execute(
        "SELECT domain, COUNT(*) c FROM graph_nodes WHERE deleted_at IS NULL GROUP BY domain").fetchall()}
    conn.close()
    # map integration name → graph domain
    src_domain = {"notion": "notion", "github": "github", "google": "gdrive"}
    out = [{"source": "internal", "domain": "internal", "available": True,
            "nodes": sum(counts.get(d, 0) for d in INTERNAL_DOMAINS),
            **state.get("internal", {})}]
    for name, dom in src_domain.items():
        out.append({"source": name, "domain": dom, "available": bool(avail.get(name)),
                    "nodes": counts.get(dom, 0), **state.get(name, {})})
    out.append({"source": "local", "domain": "local", "available": True,
                "nodes": counts.get("local", 0), **state.get("local", {})})
    return out


def _set_sync_state(source: str, item_count: int, cursor: Optional[str] = None) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO graph_sync_state (source, last_synced_at, cursor, item_count)
           VALUES (?, CURRENT_TIMESTAMP, ?, ?)
           ON CONFLICT(source) DO UPDATE SET
              last_synced_at=CURRENT_TIMESTAMP, cursor=excluded.cursor, item_count=excluded.item_count""",
        (source, cursor, item_count),
    )
    conn.commit()
    conn.close()


# ── integration sync (M3 — rich read-only mirrors) ───────────────────────────
def _notion_title(page: dict) -> str:
    props = page.get("properties", {}) or {}
    for p in props.values():
        if isinstance(p, dict) and p.get("type") == "title":
            parts = p.get("title", []) or []
            text = "".join(t.get("plain_text", "") for t in parts).strip()
            if text:
                return text
    return page.get("url", "Untitled").rsplit("/", 1)[-1].replace("-", " ")[:80] or "Untitled"


def _sync_notion() -> int:
    from core.integrations import get_integration
    conn_i = get_integration("notion")
    if not conn_i or not conn_i.is_available():
        return 0
    pages = conn_i.search_pages("")  # broad search → recent/all accessible pages
    seen: dict[str, int] = {}
    for pg in pages[:300]:
        pid = pg.get("id")
        if not pid:
            continue
        title = _notion_title(pg)
        nid = upsert_node("notion", pid, title, ref_kind="page",
                          summary=title, source_url=pg.get("url"))
        seen[pid] = nid
    # parent→child ref edges where both sides were synced
    for pg in pages[:300]:
        pid = pg.get("id")
        parent = (pg.get("parent") or {})
        par_id = parent.get("page_id") or parent.get("database_id")
        if pid in seen and par_id in seen:
            upsert_edge(seen[par_id], seen[pid], "ref", weight=1.0)
    return len(seen)


def _sync_github() -> int:
    from core.integrations import get_integration
    conn_i = get_integration("github")
    if not conn_i or not conn_i.is_available():
        return 0
    repos = [r.strip() for r in os.getenv("GRAPH_GITHUB_REPOS", "").split(",") if r.strip()]
    if not repos:
        return 0
    total = 0
    for repo in repos[:10]:
        info = conn_i.get_repo_info(repo)
        if not info:
            continue
        repo_nid = upsert_node("github", info.get("full_name", repo), info.get("full_name", repo),
                               ref_kind="repo", summary=info.get("description"),
                               source_url=info.get("html_url"))
        total += 1
        for iss in conn_i.list_issues(repo, limit=20) or []:
            if "pull_request" in iss:  # issues endpoint returns PRs too
                continue
            iid = f"{repo}#{iss.get('number')}"
            nid = upsert_node("github", iid, f"#{iss.get('number')} {iss.get('title','')}"[:80],
                              ref_kind="issue", summary=(iss.get("body") or "")[:500],
                              source_url=iss.get("html_url"))
            upsert_edge(repo_nid, nid, "ref", weight=1.0)
            total += 1
        for cm in conn_i.get_recent_commits(repo, limit=15) or []:
            sha = cm.get("sha", "")[:10]
            msg = ((cm.get("commit") or {}).get("message") or "").splitlines()[0][:80]
            if not sha:
                continue
            nid = upsert_node("github", f"{repo}@{sha}", msg or sha, ref_kind="commit",
                              summary=msg, source_url=cm.get("html_url"))
            upsert_edge(repo_nid, nid, "ref", weight=0.7)
            total += 1
    return total


_WIKILINK_RE = None


def _sync_local() -> int:
    import re
    import glob
    global _WIKILINK_RE
    if _WIKILINK_RE is None:
        _WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
    dirs = [d.strip() for d in (os.getenv("GRAPH_LOCAL_DIRS") or os.getenv("OBSIDIAN_VAULT") or "").split(",") if d.strip()]
    if not dirs:
        return 0
    stem_to_node: dict[str, int] = {}
    links: list[tuple[str, list[str]]] = []
    count = 0
    for base in dirs:
        if not os.path.isdir(base):
            continue
        for path in glob.glob(os.path.join(base, "**", "*.md"), recursive=True)[:500]:
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    body = f.read()
            except Exception:
                continue
            stem = os.path.splitext(os.path.basename(path))[0]
            rel = os.path.relpath(path, base)
            nid = upsert_node("local", rel, stem, ref_kind="note",
                              summary=body[:500], source_url=f"file:///{path.replace(os.sep, '/')}")
            stem_to_node[stem.lower()] = nid
            links.append((stem.lower(), [m.strip().lower() for m in _WIKILINK_RE.findall(body)]))
            count += 1
    # wikilink → ref edges between local notes
    for src_stem, targets in links:
        src = stem_to_node.get(src_stem)
        for t in targets:
            tgt = stem_to_node.get(t)
            if src and tgt:
                upsert_edge(src, tgt, "ref", weight=1.0)
    return count


def sync_source(name: str) -> dict:
    """Pull rich read-only sub-nodes from an integration into the graph. Best-effort per
    source; missing keys/dirs → 0 synced (never raises). google/gdrive is a placeholder
    connector (no data API yet) so it no-ops with a note."""
    name = (name or "").lower()
    try:
        if name == "notion":
            return {"source": name, "synced": _sync_notion()}
        if name == "github":
            return {"source": name, "synced": _sync_github()}
        if name == "local":
            return {"source": name, "synced": _sync_local()}
        if name in ("google", "gdrive"):
            return {"source": name, "synced": 0, "note": "Google connector is a placeholder (no data API yet)"}
    except Exception as e:
        logger.warning("graph sync_source(%s) failed: %s", name, e)
        return {"source": name, "synced": 0, "error": str(e)[:120]}
    return {"source": name, "synced": 0, "note": "unknown source"}


# ── full rebuild ──────────────────────────────────────────────────────────────
def rebuild(sources: Optional[list[str]] = None) -> dict:
    """End-to-end refresh: internal + requested sources + sparse semantic edges +
    degree + community detection. Legacy all-pairs tag edges are purged (anti-hairball)."""
    res = {"internal": sync_internal()}
    for s in (sources or []):
        try:
            res[s] = sync_source(s)
        except Exception as e:
            logger.warning("sync_source(%s) failed: %s", s, e)
            res[s] = {"error": str(e)[:120]}
    res["tag_edges_purged"] = clear_tag_edges()
    res["semantic_edges"] = build_semantic_edges()
    recompute_degree()
    res["communities"] = detect_communities()
    return res
