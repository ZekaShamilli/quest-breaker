"""Adversarial player archetypes: greedy tag-scored walkers that report soft-locks."""
import networkx as nx

from engine import apply, build_graph, violations
from models import NarrativeState, QuestGraph, SimulationRun, TraceStep

ARCHETYPES = {
    "murder_hobo": {"violent": 3, "enemy_faction": 1, "help": -2},
    "contrarian": {"refuse": 3, "enemy_faction": 3, "help": -3},
    "speedrunner": {"main": 3, "optional": -3, "companion": -3},
}
MAX_STEPS = 50


def simulate(g: QuestGraph, archetype: str) -> SimulationRun:
    weights = ARCHETYPES[archetype]
    G = build_graph(g)
    endings = [n.id for n in g.nodes if not n.next_nodes]

    def dist_to_end(nid):
        lengths = nx.single_source_shortest_path_length(G, nid)
        return min((lengths[e] for e in endings if e in lengths), default=10**6)

    def score(nid):
        return sum(weights.get(t, 0) for t in g.node(nid).tags)

    state = dict(g.initial_state)
    node = g.node(g.start)
    trace: list[TraceStep] = []
    if fails := violations(node, state):
        return SimulationRun(archetype=archetype, outcome="soft_locked", soft_locked=True, trace=[],
                             blocked_options=[{"node": node.id, "title": node.title, "violations": fails}],
                             message=f"Start quest '{node.title}' is already locked: {fails}")
    reason = "start"
    for _ in range(MAX_STEPS):
        state = apply(node, state)
        trace.append(TraceStep(node_id=node.id, title=node.title, reason=reason, state=NarrativeState(entities=state)))
        if not node.next_nodes:
            return SimulationRun(archetype=archetype, outcome="completed", soft_locked=False, trace=trace,
                                 message=f"Reached ending '{node.title}' in {len(trace)} steps.")
        options = [(m, violations(g.node(m), state)) for m in node.next_nodes]
        available = [m for m, f in options if not f]
        if not available:
            blocked = [{"node": m, "title": g.node(m).title, "violations": f} for m, f in options]
            why = "; ".join(f"'{b['title']}' needs " + ", ".join(f"{k}={e!r} (is {a!r})" for k, (e, a) in b["violations"].items())
                            for b in blocked)
            return SimulationRun(archetype=archetype, outcome="soft_locked", soft_locked=True, trace=trace,
                                 blocked_options=blocked, message=f"SOFT-LOCKED after '{node.title}': {why}")
        # Highest archetype score wins; ties go to the option closest to an ending, then authoring order.
        best = max(available, key=lambda m: (score(m), -dist_to_end(m), -node.next_nodes.index(m)))
        tags = [t for t in g.node(best).tags if t in weights]
        reason = f"score {score(best)}" + (f" (tags: {', '.join(tags)})" if tags else " (shortest route)")
        node = g.node(best)
    return SimulationRun(archetype=archetype, outcome="loop", soft_locked=True, trace=trace,
                         message=f"Stuck in a loop: no ending after {MAX_STEPS} steps.")
