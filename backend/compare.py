"""Graph-only vs LLM-only vs Hybrid on the labeled benchmark. Writes eval_results.md.

    python compare.py              # 16 held-out graphs (seeds 16-31), ~64 LLM calls
    python compare.py --offset 0   # the graphs used while tuning the prompt
"""
import argparse
import asyncio
import inspect
import time
from pathlib import Path

import llm
from benchmark import benchmark
from engine import check, edge_cover, playthroughs

OUT = Path(__file__).parent / "eval_results.md"


def graph_only(g):
    return [(r.affected_nodes[0], r.conflict_nodes, r.explanation) for r in check(g)[0]]


async def llm_only(g):
    """Baseline: hand Claude the whole graph JSON in one call and ask it to find everything."""
    prompt = ("Here is a branching quest graph. Players start at the start node and at every node choose one of "
              "next_nodes; a node is only enterable when its pre_conditions match the current state, and "
              "state_mutations apply on completion.\n\n" + g.model_dump_json() + "\n\nFind every node where, on "
              "some playthrough, the quest's content or requirements contradict something that happened earlier "
              "on that playthrough. node_id = where the contradiction shows up, conflicting_node_ids = the causes.")
    v = await llm.ask(prompt, llm.Issues)
    return [(i.node_id, i.conflicting_node_ids, i.explanation) for i in (v.issues if v else [])]


async def hybrid(g):
    preds = graph_only(g)
    flagged = {p[0] for p in preds}
    semantic = await llm.semantic_check(g, edge_cover(playthroughs(g)))
    return preds + [(r.affected_nodes[0], r.conflict_nodes, r.explanation) for r in semantic if r.affected_nodes[0] not in flagged]


def matches(pred, label):
    node, causes, _ = pred
    return node == label["need"] or (node == label["cause"] and label["need"] in causes)


def score(results):
    """results: [(graph, labels, preds)] -> metrics + failure examples."""
    tp_preds = n_preds = 0
    found = {"flag_bug": [0, 0], "text_bug": [0, 0]}
    misses, false_pos = [], []
    for g, labels, preds in results:
        preds = list({p[0]: p for p in preds}.values())  # one prediction per node
        n_preds += len(preds)
        for p in preds:
            if any(matches(p, l) for l in labels):
                tp_preds += 1
            else:
                false_pos.append((g.name, p))
        for l in labels:
            hit = any(matches(p, l) for p in preds)
            found[l["kind"]][0] += hit
            found[l["kind"]][1] += 1
            if not hit:
                misses.append((g.name, l))
    total = sum(t for _, t in found.values())
    return dict(
        precision=tp_preds / n_preds if n_preds else 1.0,
        recall=sum(h for h, _ in found.values()) / total,
        flag_recall=found["flag_bug"][0] / found["flag_bug"][1],
        text_recall=found["text_bug"][0] / found["text_bug"][1],
        misses=misses, false_pos=false_pos, labels=total,
    )


async def run(name, fn, bench):
    before = dict(llm.usage)
    t0 = time.perf_counter()
    if inspect.iscoroutinefunction(fn):
        preds = await asyncio.gather(*(fn(g) for g, _ in bench))
    else:
        preds = [fn(g) for g, _ in bench]
    elapsed = time.perf_counter() - t0
    calls = llm.usage["calls"] - before["calls"]
    tin = llm.usage["input_tokens"] - before["input_tokens"]
    tout = llm.usage["output_tokens"] - before["output_tokens"]
    cost = (tin * llm.PRICE_PER_MTOK["input"] + tout * llm.PRICE_PER_MTOK["output"]) / 1e6
    return dict(name=name, calls=calls, tokens=(tin, tout), cost=cost, seconds=elapsed,
                **score([(g, labels, p) for (g, labels), p in zip(bench, preds)]))


def pct(x):
    return f"{x * 100:.0f}%"


def money(r):
    return "n/a (set QB_PRICE_IN/OUT)" if r["calls"] and not r["cost"] else f"${r['cost']:.2f}"


def report(rows, n_graphs, offset, skipped):
    lines = [f"# Quest-Breaker evaluation\n",
             f"{n_graphs} held-out generated quest graphs (seeds {offset}-{offset + n_graphs - 1}; seeds 0-15 were used to tune the prompt), {rows[0]['labels']} planted bugs (half encoded as state flags, half only in "
             f"the story text), plus {2 * n_graphs} look-alike traps that are *not* bugs. Model: `{llm.MODEL}`.\n",
             "| Approach | Precision | Recall | Flag-bug recall | Text-only-bug recall | LLM calls | Tokens in / out | Cost | Time |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {pct(r['precision'])} | {pct(r['recall'])} | {pct(r['flag_recall'])} | "
                     f"{pct(r['text_recall'])} | {r['calls']} | {r['tokens'][0]:,} / {r['tokens'][1]:,} | "
                     f"{money(r)} | {r['seconds']:.1f}s |")
    for name in skipped:
        lines.append(f"| {name} | skipped: no LLM credentials | | | | | | | |")
    for r in rows:
        if r["misses"] or r["false_pos"]:
            lines.append(f"\n## Failures: {r['name']}\n")
            lines += [f"- **missed** `{gname}` {l['kind']} {l['entity']}: caused at `{l['cause']}`, shows up at `{l['need']}`"
                      for gname, l in r["misses"][:10]]
            lines += [f"- **false alarm** `{gname}` at `{p[0]}`: {p[2][:160]}" for gname, p in r["false_pos"][:10]]
    return "\n".join(lines) + "\n"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graphs", type=int, default=16)
    ap.add_argument("--offset", type=int, default=16, help="first seed; 0-15 were used while tuning the prompt")
    args = ap.parse_args()
    bench = benchmark(args.graphs, args.offset)
    rows = [await run("Graph-only (NetworkX)", graph_only, bench)]
    skipped = []
    if llm.enabled():
        rows.append(await run("LLM-only (whole graph, 1 call)", llm_only, bench))
        rows.append(await run("**Hybrid (Quest-Breaker)**", hybrid, bench))
    else:
        skipped = ["LLM-only (whole graph, 1 call)", "Hybrid (Quest-Breaker)"]
    md = report(rows, args.graphs, args.offset, skipped)
    OUT.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    asyncio.run(main())
