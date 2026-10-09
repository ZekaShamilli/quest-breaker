"""Synthetic quest failures: every known defect must be found, and nothing else (precision == recall == 1)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from benchmark import make_graph  # noqa: E402
from engine import check, edge_cover, playthroughs  # noqa: E402
from main import app  # noqa: E402
from models import QuestGraph  # noqa: E402
from simulator import ARCHETYPES, simulate  # noqa: E402


def graph(nodes, initial=None, start="a"):
    return QuestGraph(name="t", start=start, initial_state=initial or {}, nodes=[
        {"id": i, "title": i.upper(), **spec} for i, spec in nodes.items()])


def found(g):
    return {(r.error_type, tuple(r.affected_nodes)) for r in check(g)[0]}


CASES = {
    "kill_then_require": (
        graph({"a": {"next_nodes": ["b"]},
               "b": {"state_mutations": {"smith": "dead"}, "next_nodes": ["c"]},
               "c": {"pre_conditions": {"smith": "alive"}}}, {"smith": "alive"}),
        {("StateContradiction", ("c",))},
    ),
    "one_bad_branch_of_two": (
        graph({"a": {"next_nodes": ["b1", "b2"]},
               "b1": {"state_mutations": {"faction": "betrayed"}, "next_nodes": ["c"]},
               "b2": {"state_mutations": {"faction": "joined"}, "next_nodes": ["c"]},
               "c": {"pre_conditions": {"faction": "joined"}}}),
        {("StateContradiction", ("c",))},
    ),
    "never_set_flag": (
        graph({"a": {"next_nodes": ["b"]}, "b": {"pre_conditions": {"key": True}}}, {"key": False}),
        {("StateContradiction", ("b",))},
    ),
    "requires_future_item": (
        graph({"a": {"next_nodes": ["door"]},
               "door": {"pre_conditions": {"key": "found"}, "next_nodes": ["vault"]},
               "vault": {"state_mutations": {"key": "found"}}}, {"key": "missing"}),
        {("CircularDependency", ("door",)), ("UnreachablePath", ("vault",))},
    ),
    "orphan_node": (
        graph({"a": {"next_nodes": ["b"]}, "b": {}, "orphan": {"next_nodes": ["b"]}}),
        {("UnreachablePath", ("orphan",))},
    ),
    "inescapable_loop": (
        graph({"a": {"next_nodes": ["b", "end"]}, "b": {"next_nodes": ["c"]}, "c": {"next_nodes": ["b"]}, "end": {}}),
        {("CircularDependency", ("b", "c"))},
    ),
    "self_loop_trap": (
        graph({"a": {"next_nodes": ["b", "end"]}, "b": {"next_nodes": ["b"]}, "end": {}}),
        {("CircularDependency", ("b",))},
    ),
    "locked_start": (
        graph({"a": {"pre_conditions": {"x": 1}}}, {"x": 0}),
        {("StateContradiction", ("a",))},
    ),
}

CLEAN = {
    "loop_with_exit": graph({"a": {"next_nodes": ["hub"]}, "hub": {"next_nodes": ["side", "end"]},
                             "side": {"state_mutations": {"gold": 1}, "next_nodes": ["hub"]}, "end": {}}),
    "flag_set_on_every_branch": graph({
        "a": {"next_nodes": ["x", "y"]},
        "x": {"state_mutations": {"map": "yes", "path": "x"}, "next_nodes": ["z"]},
        "y": {"state_mutations": {"map": "yes", "path": "y"}, "next_nodes": ["z"]},
        "z": {"pre_conditions": {"map": "yes"}}}),
    "kill_unrelated_npc": graph({
        "a": {"next_nodes": ["b"]}, "b": {"state_mutations": {"guard": "dead"}, "next_nodes": ["c"]},
        "c": {"pre_conditions": {"smith": "alive"}}}, {"smith": "alive", "guard": "alive"}),
    "revive_before_use": graph({
        "a": {"state_mutations": {"hero": "dead"}, "next_nodes": ["b"]},
        "b": {"state_mutations": {"hero": "alive"}, "next_nodes": ["c"]},
        "c": {"pre_conditions": {"hero": "alive"}}}),
}


@pytest.mark.parametrize("name", CASES)
def test_detects_exactly_the_known_defect(name):
    g, expected = CASES[name]
    assert found(g) == expected


@pytest.mark.parametrize("name", CLEAN)
def test_no_false_positives(name):
    assert found(CLEAN[name]) == set()


def test_precision_and_recall_are_perfect():
    tp = fp = fn = 0
    for g, expected in list(CASES.values()) + [(g, set()) for g in CLEAN.values()]:
        got = found(g)
        tp, fp, fn = tp + len(got & expected), fp + len(got - expected), fn + len(expected - got)
    assert tp > 0 and fp == 0 and fn == 0


def test_contradiction_points_at_the_killer():
    g, _ = CASES["kill_then_require"]
    (r,) = check(g)[0]
    assert r.conflict_nodes == ["b"] and r.failing_path == ["a", "b", "c"] and r.severity == "critical"


def test_gated_branch_with_alternative_is_warning_not_softlock():
    g = graph({"a": {"state_mutations": {"k": 0}, "next_nodes": ["locked", "open"]},
               "locked": {"pre_conditions": {"k": 1}}, "open": {}})
    (r,) = check(g)[0]
    assert r.severity == "warning"


def load(name):
    return QuestGraph.model_validate_json((ROOT / "data" / f"{name}.json").read_text(encoding="utf-8"))


def test_demo_corrupted_tree():
    assert found(load("corrupted_witcher_style")) == {
        ("StateContradiction", ("q5",)),       # Garrick executed, then needed to forge
        ("StateContradiction", ("q6",)),       # rebels sold out, then needed to storm the keep
        ("CircularDependency", ("q5x",)),      # archive key is inside the archive
        ("UnreachablePath", ("q5y",)),
        ("UnreachablePath", ("q_shrine",)),
    }


def test_demo_clean_tree():
    assert found(load("clean_quest_tree")) == set()


def test_archetypes():
    bad, clean = load("corrupted_witcher_style"), load("clean_quest_tree")
    hobo = simulate(bad, "murder_hobo")
    assert hobo.soft_locked and [t.node_id for t in hobo.trace][:2] == ["q1", "q2a"]
    assert simulate(bad, "contrarian").soft_locked
    assert simulate(bad, "speedrunner").outcome == "completed"
    assert "q3c" not in [t.node_id for t in simulate(bad, "speedrunner").trace]  # skipped the companion
    assert all(simulate(clean, a).outcome == "completed" for a in ARCHETYPES)


def test_api():
    c = TestClient(app)
    assert "clean_quest_tree" in c.get("/api/datasets").json()
    v = c.post("/api/validate", json={"dataset": "corrupted_witcher_style", "use_llm": False}).json()
    status = {n["id"]: n["status"] for n in v["nodes"]}
    assert status["q5"] == "broken" and status["q2a"] == "conflict" and status["q1"] == "valid"
    s = c.post("/api/simulate", json={"dataset": "corrupted_witcher_style", "archetypes": ["murder_hobo"]}).json()
    assert s["runs"][0]["soft_locked"]
    assert c.post("/api/validate", json={"dataset": "nope"}).status_code == 404


def test_llm_semantic_pass_with_stubbed_model(monkeypatch):
    import asyncio

    import llm

    async def fake_ask(prompt, schema):
        if schema is llm.StoryFix:
            return llm.StoryFix(suggested_fix="AI fix")
        issues = []
        if "[q8]" in prompt and "[q3c]" not in prompt:  # feast toast, but Lambert never recruited
            issues.append(llm.Issue(node_id="q8", conflicting_node_ids=["q3", "bogus"],
                                    explanation="Lambert was never recruited.", suggested_fix="Recruit him."))
        issues.append(llm.Issue(node_id="not_on_path", conflicting_node_ids=[], explanation="x", suggested_fix="x"))
        return llm.Issues(issues=issues)

    monkeypatch.setattr(llm, "ask", fake_ask)
    g = load("corrupted_witcher_style")
    reports, _ = check(g)
    semantic = asyncio.run(llm.semantic_check(g, edge_cover(playthroughs(g))))
    assert [(r.affected_nodes, r.source, r.conflict_nodes) for r in semantic] == [(["q8"], "llm", ["q3"])]
    assert semantic[0].failing_path[-1] == "q8"
    asyncio.run(llm.write_fixes(g, reports))
    assert all(r.suggested_fix == "AI fix" for r in reports)


def test_text_only_bugs_are_invisible_to_the_graph_checker():
    g = load("hidden_text_bugs")
    assert found(g) == set()  # this is the gap the LLM pass exists to close
    cover = edge_cover(playthroughs(g))
    assert any({"m2a", "m6"} <= set(p) for p in cover)  # dead minstrel sings at the wedding
    assert any({"m4a", "m7"} <= set(p) for p in cover)  # burned bridge is crossed


def test_edge_cover_walks_every_valid_edge():
    g = load("clean_quest_tree")
    all_edges = {e for p in playthroughs(g) for e in zip(p, p[1:])}
    assert {e for p in edge_cover(playthroughs(g)) for e in zip(p, p[1:])} == all_edges


@pytest.mark.parametrize("seed", range(32))
def test_benchmark_labels_are_consistent(seed):
    """Graph checker finds exactly the flag bugs; the LLM's path set contains every text bug's cause and symptom."""
    g, labels = make_graph(seed)
    assert found(g) == {("StateContradiction", (l["need"],)) for l in labels if l["kind"] == "flag_bug"}
    cover = edge_cover(playthroughs(g))
    for l in labels:
        if l["kind"] == "text_bug":
            assert any(l["cause"] in p and l["need"] in p for p in cover)


def test_scoring():
    import compare

    g, labels = make_graph(0)
    perfect = [(l["need"], [l["cause"]], "") for l in labels]
    s = compare.score([(g, labels, perfect + [("hub0", [], "false alarm")])])
    assert s["recall"] == 1 and s["precision"] == 2 / 3 and len(s["false_pos"]) == 1
