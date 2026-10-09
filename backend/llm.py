"""Step B: LLM semantic validator + AI story-fix writer (Claude). Degrades to no-op without credentials.

The graph checker only understands explicit flags. Claude reads the *text* of each playthrough in a small
edge-covering set and reports steps that contradict earlier steps (a character who died only in prose, etc.).
"""
import asyncio
import json
import os

from pathlib import Path

import anthropic
import openai
from pydantic import BaseModel

from models import DeadlockReport, QuestGraph

# backend/.env (gitignored): KEY=value lines; real environment variables win.
_env = Path(__file__).parent / ".env"
for _line in _env.read_text(encoding="utf-8").splitlines() if _env.exists() else []:
    if "=" in _line and not _line.lstrip().startswith("#"):
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

# Provider: Azure OpenAI (Foundry) when AZURE_OPENAI_ENDPOINT is set, otherwise Claude.
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").removesuffix("responses").removesuffix("/")
AZURE = bool(AZURE_ENDPOINT and os.environ.get("AZURE_OPENAI_API_KEY"))
MODEL = os.environ.get("AZURE_OPENAI_MODEL", "gpt-5.6-sol") if AZURE else "claude-opus-5-5"
if AZURE:  # USD per million tokens; set QB_PRICE_IN / QB_PRICE_OUT from your Azure price sheet
    PRICE_PER_MTOK = {"input": float(os.environ.get("QB_PRICE_IN", 0)), "output": float(os.environ.get("QB_PRICE_OUT", 0))}
else:
    PRICE_PER_MTOK = {"input": 4.00, "output": 20.00}  # claude-opus-5-5
SYSTEM = ("You are a narrative QA lead for branching RPGs. You find genuine logical contradictions in "
          "quest storylines: dead or departed characters appearing, destroyed places or items being used, "
          "betrayed factions acting friendly, events referenced that never happened on this path. A step only "
          "conflicts with steps that came BEFORE it in the same playthrough. Characters, places, items and groups "
          "may be introduced for the first time at any step - a first appearance is NOT a contradiction. Only flag "
          "a step when an earlier step explicitly killed, destroyed, removed, or turned against something that this "
          "step relies on. Ignore tone, style, and anything merely unlikely; report nothing if the story is consistent.")

usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}  # ponytail: process-wide counter, fine for one eval run


class Issue(BaseModel):
    node_id: str                     # the step where the contradiction shows up
    conflicting_node_ids: list[str]  # earlier steps that caused it
    explanation: str
    suggested_fix: str


class Issues(BaseModel):
    issues: list[Issue]


class StoryFix(BaseModel):
    suggested_fix: str


def enabled() -> bool:
    # ponytail: env-var check only; an `ant auth login` profile also works if you set QB_LLM=1.
    return AZURE or bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("QB_LLM"))


def cost_usd() -> float:
    return (usage["input_tokens"] * PRICE_PER_MTOK["input"] + usage["output_tokens"] * PRICE_PER_MTOK["output"]) / 1e6


async def ask(prompt: str, schema: type[BaseModel]):
    # A fresh client per call: a cached async client breaks once its event loop closes.
    if AZURE:
        async with openai.AsyncOpenAI(base_url=AZURE_ENDPOINT + "/", api_key=os.environ["AZURE_OPENAI_API_KEY"]) as client:
            resp = await client.responses.parse(model=MODEL, instructions=SYSTEM, input=prompt, text_format=schema)
        usage["calls"] += 1
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        return resp.output_parsed
    async with anthropic.AsyncAnthropic() as client:
        resp = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # reroute safety-classifier refusals to a fallback model instead of failing
        )
    usage["calls"] += 1
    usage["input_tokens"] += resp.usage.input_tokens
    usage["output_tokens"] += resp.usage.output_tokens
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return None
    return resp.parsed_output


def _story(g: QuestGraph, path: list[str]) -> str:
    state, lines = dict(g.initial_state), []
    for i, nid in enumerate(path, 1):
        n = g.node(nid)
        state = {**state, **n.state_mutations}
        extra = f" | implicit requirements: {n.narrative_requirements}" if n.narrative_requirements else ""
        lines.append(f"Step {i} [{n.id}] {n.title}: {n.description} | actors={n.character_actors}{extra} | state after={json.dumps(state)}")
    return "\n".join(lines)


async def _check_path(g: QuestGraph, path: list[str]) -> list[DeadlockReport]:
    prompt = (f"Initial world state: {json.dumps(g.initial_state)}\n\nOne complete playthrough, in order:\n{_story(g, path)}\n\n"
              "List every step whose content contradicts what happened in earlier steps of this playthrough. "
              "Use the bracketed ids. Return an empty list if the playthrough is consistent.")
    verdict = await ask(prompt, Issues)
    out = []
    for i in verdict.issues if verdict else []:
        if i.node_id not in path:
            continue
        upto = path[: path.index(i.node_id) + 1]
        out.append(DeadlockReport(
            error_type="StateContradiction", affected_nodes=[i.node_id],
            conflict_nodes=[c for c in i.conflicting_node_ids if c in upto[:-1]],
            failing_path=upto, explanation=f"Semantic Conflict: {i.explanation}",
            suggested_fix=i.suggested_fix, severity="warning", source="llm",
        ))
    return out


async def semantic_check(g: QuestGraph, paths: list[list[str]]) -> list[DeadlockReport]:
    results = await asyncio.gather(*(_check_path(g, p) for p in paths))
    out, seen = [], set()
    for r in sorted((r for rs in results for r in rs), key=lambda r: len(r.failing_path)):
        if r.affected_nodes[0] not in seen:  # one report per node: the shortest conflicting path
            seen.add(r.affected_nodes[0])
            out.append(r)
    return out


async def _fix(g: QuestGraph, r: DeadlockReport) -> None:
    nodes = {nid: g.node(nid).model_dump(include={"title", "description", "character_actors", "pre_conditions", "state_mutations"})
             for nid in dict.fromkeys(r.failing_path + r.affected_nodes + r.conflict_nodes)}
    prompt = (f"A quest-graph validator found this defect:\n{r.explanation}\n\nRelevant quests: {json.dumps(nodes)}\n\n"
              f"Mechanical fix proposed: {r.suggested_fix}\n\nWrite a better 'Suggested Story Fix' (2-3 sentences) "
              "that resolves the defect in a way that feels natural in-world - e.g. a new character, item, or "
              "branch - and names the exact quest/state change to make.")
    fix = await ask(prompt, StoryFix)
    if fix:
        r.suggested_fix = fix.suggested_fix


async def write_fixes(g: QuestGraph, reports: list[DeadlockReport]) -> None:
    await asyncio.gather(*(_fix(g, r) for r in reports))
