import asyncio
from pathlib import Path

import anthropic
import openai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import llm
from engine import build_graph, check, edge_cover, layout, node_status, playthroughs
from models import QuestGraph
from simulator import ARCHETYPES, simulate

DATA = Path(__file__).parent / "data"
DIST = Path(__file__).parent.parent / "frontend" / "dist"

app = FastAPI(title="Quest-Breaker")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


class GraphRequest(BaseModel):
    dataset: str | None = None
    graph: QuestGraph | None = None
    use_llm: bool = True


class SimulateRequest(GraphRequest):
    archetypes: list[str] = list(ARCHETYPES)


def load(req: GraphRequest) -> QuestGraph:
    if req.graph:
        return req.graph
    names = {p.stem for p in DATA.glob("*.json")}
    if req.dataset not in names:
        raise HTTPException(404, f"unknown dataset; choose one of {sorted(names)}")
    return QuestGraph.model_validate_json((DATA / f"{req.dataset}.json").read_text(encoding="utf-8"))


@app.get("/api/datasets")
def datasets():
    return sorted(p.stem for p in DATA.glob("*.json"))


@app.post("/api/validate")
async def validate(req: GraphRequest):
    g = load(req)
    reports, _ = check(g)
    llm_status = "disabled (set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY or ANTHROPIC_API_KEY)"
    if req.use_llm and llm.enabled():
        try:
            flagged = {n for r in reports for n in r.affected_nodes}
            semantic, _ = await asyncio.gather(llm.semantic_check(g, edge_cover(playthroughs(g))), llm.write_fixes(g, reports))
            reports += [r for r in semantic if r.affected_nodes[0] not in flagged]
            llm_status = f"ok ({llm.MODEL})"
        except (anthropic.APIError, openai.APIError) as e:
            llm_status = f"error: {e.__class__.__name__}: {e}"
    elif not req.use_llm:
        llm_status = "skipped"
    status = node_status(g, reports)
    pos = layout(g)
    G = build_graph(g)
    return {
        "name": g.name,
        "llm_status": llm_status,
        "reports": [r.model_dump() for r in reports],
        "nodes": [{**n.model_dump(), "status": status[n.id], "position": pos[n.id]} for n in g.nodes],
        "edges": [{"id": f"{a}->{b}", "source": a, "target": b} for a, b in G.edges],
        "graph": g.model_dump(),
    }


@app.post("/api/simulate")
def simulate_endpoint(req: SimulateRequest):
    g = load(req)
    unknown = set(req.archetypes) - set(ARCHETYPES)
    if unknown:
        raise HTTPException(422, f"unknown archetypes {sorted(unknown)}; choose from {list(ARCHETYPES)}")
    return {"runs": [simulate(g, a).model_dump() for a in req.archetypes]}


if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
