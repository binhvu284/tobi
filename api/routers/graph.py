"""Knowledge-graph routes — /api/graph/* .

Extracted from api/dashboard.py (refactor Slice). Byte-identical handlers;
only @router.* -> @router.*. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["graph"])


class GraphNodeCreate(BaseModel):
    title: str
    summary: str | None = None
    category: str | None = None
    domain: str = "manual"


class GraphNodePatch(BaseModel):
    title: str | None = None
    summary: str | None = None
    category: str | None = None


class GraphEdgeCreate(BaseModel):
    source_id: int
    target_id: int
    edge_type: str = "manual"
    weight: float = 1.0


class GraphLayoutReq(BaseModel):
    pins: list[dict] = Field(default_factory=list)


@router.get("/api/graph")
def graph_get(domain: str | None = None, category: str | None = None,
              q: str | None = None, min_weight: float = 0.0,
              date_from: str | None = None, date_to: str | None = None):
    return graph.get_graph(domain=domain, category=category, q=q, min_weight=min_weight,
                           date_from=date_from, date_to=date_to)


@router.get("/api/graph/sources")
def graph_sources():
    return {"sources": graph.get_sources()}


@router.get("/api/graph/communities")
def graph_communities():
    return {"communities": graph.list_communities()}


@router.get("/api/graph/path")
def graph_path(a: int = Query(...), b: int = Query(...)):
    return {"path": graph.find_path(a, b)}


@router.get("/api/graph/node/{node_id}/neighbors")
def graph_neighbors(node_id: int, depth: int = 1):
    return graph.neighbors(node_id, depth=depth)


class GraphRetrieveReq(BaseModel):
    query: str
    k: int = 8
    hops: int = 1


@router.post("/api/graph/retrieve")
def graph_retrieve(payload: GraphRetrieveReq):
    """GraphRAG retrieval: seed by embedding + spreading activation across edges."""
    return {"results": graph.graph_retrieve(payload.query, k=payload.k, hops=payload.hops)}


@router.get("/api/graph/timeline")
def graph_timeline(date_from: str | None = None, date_to: str | None = None):
    return {"events": graph.timeline_events(date_from, date_to)}


@router.get("/api/graph/search")
def graph_search(q: str = Query(...), k: int = 12):
    return graph.search(q, k=k)


@router.get("/api/graph/node/{node_id}")
def graph_node(node_id: int):
    n = graph.get_node(node_id)
    if not n:
        raise HTTPException(status_code=404, detail="node not found")
    n["connections"] = graph.expand(node_id)
    return n


@router.post("/api/graph/node/{node_id}/expand")
def graph_expand(node_id: int):
    return graph.expand(node_id)


@router.post("/api/graph/nodes")
def graph_node_create(payload: GraphNodeCreate):
    return graph.create_manual_node(payload.title, payload.summary, payload.category, payload.domain)


@router.patch("/api/graph/nodes/{node_id}")
def graph_node_patch(node_id: int, payload: GraphNodePatch):
    n = graph.update_node(node_id, payload.title, payload.summary, payload.category)
    if not n:
        raise HTTPException(status_code=404, detail="node not found")
    return n


@router.delete("/api/graph/nodes/{node_id}")
def graph_node_delete(node_id: int):
    graph.delete_node(node_id)
    return {"ok": True}


@router.post("/api/graph/edges")
def graph_edge_create(payload: GraphEdgeCreate):
    eid = graph.upsert_edge(payload.source_id, payload.target_id, payload.edge_type,
                            weight=payload.weight, created_by="owner")
    if not eid:
        raise HTTPException(status_code=400, detail="invalid edge")
    graph.recompute_degree()
    return {"ok": True, "id": eid}


@router.delete("/api/graph/edges/{edge_id}")
def graph_edge_delete(edge_id: int):
    graph.delete_edge(edge_id)
    graph.recompute_degree()
    return {"ok": True}


@router.post("/api/graph/layout")
def graph_layout(payload: GraphLayoutReq):
    return {"saved": graph.save_positions(payload.pins)}


@router.post("/api/graph/sync/{source}")
def graph_sync(source: str):
    if source in ("all", "internal"):
        res = graph.rebuild(sources=["notion", "github", "google"] if source == "all" else None)
    else:
        res = {source: graph.sync_source(source)}
        res["tag_edges_purged"] = graph.clear_tag_edges()
        res["semantic_edges"] = graph.build_semantic_edges()
        graph.recompute_degree()
        res["communities"] = graph.detect_communities()
    return res


# ── Explore → News (#9) ───────────────────────────────────────────────────────
