"""Step A: deterministic, state-aware graph checker (NetworkX + BFS over (node, state))."""
from collections import deque

import networkx as nx

from models import DeadlockReport, QuestGraph, QuestNode

MAX_WITNESSES = 3  # example valid paths remembered per node


def build_graph(g: QuestGraph) -> nx.DiGraph:
    G = nx.DiGraph()
    for n in g.nodes:
        G.add_node(n.id)
        G.add_edges_from((n.id, m) for m in n.next_nodes)
    return G


def violations(node: QuestNode, state: dict) -> dict:
    """{key: (expected, actual)} for every unmet pre-condition."""
    return {k: (v, state.get(k)) for k, v in node.pre_conditions.items() if state.get(k) != v}


def apply(node: QuestNode, state: dict) -> dict:
    return {**state, **node.state_mutations}


def _freeze(state: dict) -> tuple:
    return tuple(sorted((k, repr(v)) for k, v in state.items()))


def explore(g: QuestGraph):
    """BFS over every (node, narrative state) pair reachable from the start.

    Returns (contradictions, witnesses):
      contradictions: {(target, key): {expected, actual, path, soft_lock}} - shortest failing path per (node, key)
      witnesses: {node_id: [valid paths to node]} - nodes absent here are never validly reached
    """
    # ponytail: explores distinct states, not paths; exponential only if many independent flags vary at once.
    contradictions: dict[tuple, dict] = {}
    witnesses: dict[str, list[list[str]]] = {}

    def record(target, fails, path, soft_lock):
        for key, (expected, actual) in fails.items():
            c = contradictions.setdefault((target, key), dict(expected=expected, actual=actual, path=path, soft_lock=False))
            c["soft_lock"] |= soft_lock

    start = g.node(g.start)
    if fails := violations(start, g.initial_state):
        record(start.id, fails, [start.id], True)
        return contradictions, witnesses

    queue = deque([(start.id, g.initial_state, [start.id])])
    seen = {(start.id, _freeze(g.initial_state))}
    while queue:
        nid, state, path = queue.popleft()
        node = g.node(nid)
        ws = witnesses.setdefault(nid, [])
        if len(ws) < MAX_WITNESSES:
            ws.append(path)
        after = apply(node, state)
        failed, any_ok = [], False
        for mid in node.next_nodes:
            child = g.node(mid)
            if fails := violations(child, after):
                failed.append((mid, fails))
                continue
            any_ok = True
            key = (mid, _freeze(after))
            if key not in seen:
                seen.add(key)
                queue.append((mid, after, path + [mid]))
        for mid, fails in failed:
            record(mid, fails, path + [mid], soft_lock=not any_ok)
    return contradictions, witnesses


def _label(key: str, node: QuestNode) -> str:
    actor = next((a for a in node.character_actors if key.lower() in a.lower()), None)
    return f"Actor [{actor}]" if actor else f"State [{key}]"


def _last_setter(g: QuestGraph, path: list[str], key: str) -> str | None:
    return next((nid for nid in reversed(path[:-1]) if key in g.node(nid).state_mutations), None)


def check(g: QuestGraph) -> tuple[list[DeadlockReport], dict]:
    G = build_graph(g)
    contradictions, witnesses = explore(g)
    reports: list[DeadlockReport] = []

    for (tid, key), c in contradictions.items():
        target = g.node(tid)
        expected, actual, path = c["expected"], c["actual"], c["path"]
        setters = [n.id for n in g.nodes if n.state_mutations.get(key, object()) == expected]
        downstream = nx.descendants(G, tid)
        if (g.initial_state.get(key) != expected and setters
                and all(s in downstream and not nx.has_path(G, s, tid) for s in setters)):
            names = ", ".join(f"'{g.node(s).title}'" for s in setters)
            reports.append(DeadlockReport(
                error_type="CircularDependency", affected_nodes=[tid], conflict_nodes=setters,
                failing_path=path, severity="critical",
                explanation=(f"Circular Dependency: '{target.title}' requires {key} == {expected!r}, "
                             f"but only {names} sets it - and that quest is only reachable *through* '{target.title}'."),
                suggested_fix=(f"Move the quest that grants {key}={expected!r} ({names}) before '{target.title}', "
                               f"or remove that requirement from '{target.title}'."),
            ))
            continue

        setter = _last_setter(g, path, key)
        step = len(path)
        if setter:
            s_node = g.node(setter)
            cause = f"was set to {str(actual).upper()} in Step {path.index(setter) + 1} ('{s_node.title}')"
            fix = (f"Add an alternate branch for when {key} is {actual!r} (e.g. another character fills the role, "
                   f"or '{target.title}' gets a variant without this requirement), or make '{s_node.title}' "
                   f"unable to set {key}={actual!r} on paths that lead to '{target.title}'.")
        else:
            cause = f"is {actual!r} from the start and no prior quest on this path changes it"
            fix = f"Have a quest before '{target.title}' set {key}={expected!r}, or relax the requirement."
        lock = (" No other branch is available here: the player is SOFT-LOCKED." if c["soft_lock"]
                else " Other branches remain, but this storyline is silently cut.")
        reports.append(DeadlockReport(
            error_type="StateContradiction", affected_nodes=[tid], conflict_nodes=[setter] if setter else [],
            failing_path=path, severity="critical" if c["soft_lock"] else "warning",
            explanation=(f"Deadlock Detected: {_label(key, target)} {cause}, but Step {step} "
                         f"('{target.title}') requires {key} == {expected!r}.{lock}"),
            suggested_fix=fix,
        ))

    # Loops the player can enter but never leave.
    reachable = nx.descendants(G, g.start) | {g.start}
    for scc in nx.strongly_connected_components(G):
        first = next(iter(scc))
        cyclic = len(scc) > 1 or G.has_edge(first, first)
        exits = any(m not in scc for n in scc for m in G.successors(n))
        if cyclic and not exits and scc & reachable:
            members = sorted(scc)
            entry = nx.shortest_path(G, g.start, members[0])
            reports.append(DeadlockReport(
                error_type="CircularDependency", affected_nodes=members, failing_path=entry, severity="critical",
                explanation=f"Infinite Loop: quests {members} form a cycle with no exit to any ending.",
                suggested_fix=f"Add an exit edge from one of {members} to a quest that leads to an ending.",
            ))

    flagged = {n for r in reports for n in r.affected_nodes}
    for n in g.nodes:
        if n.id in witnesses or n.id in flagged:
            continue
        if n.id not in reachable:
            why = "no chain of quests leads here from the start node"
        else:
            blockers = sorted(p for p in G.predecessors(n.id) if p not in witnesses)
            why = f"every quest leading here is itself blocked or unreachable: {blockers}"
        reports.append(DeadlockReport(
            error_type="UnreachablePath", affected_nodes=[n.id], severity="warning",
            explanation=f"Unreachable Path: no valid playthrough ever reaches '{n.title}' - {why}.",
            suggested_fix=f"Link '{n.title}' from a reachable quest whose state satisfies its pre-conditions, or cut it.",
        ))
    return reports, witnesses


def node_status(g: QuestGraph, reports: list[DeadlockReport]) -> dict[str, str]:
    status = {n.id: "valid" for n in g.nodes}
    for r in reports:
        for n in r.conflict_nodes:
            if status[n] == "valid":
                status[n] = "conflict"
    for r in reports:
        for n in r.affected_nodes:
            status[n] = "broken"
    return status


def layout(g: QuestGraph) -> dict[str, dict]:
    """Left-to-right layers by BFS depth; unreachable nodes get a trailing column."""
    G = build_graph(g)
    depth = nx.single_source_shortest_path_length(G, g.start)
    orphan_col = max(depth.values()) + 1
    cols: dict[int, list[str]] = {}
    for n in g.nodes:
        cols.setdefault(depth.get(n.id, orphan_col), []).append(n.id)
    pos = {}
    for col, ids in cols.items():
        for i, nid in enumerate(ids):
            pos[nid] = {"x": col * 300, "y": (i - (len(ids) - 1) / 2) * 140}
    return pos


def playthroughs(g: QuestGraph, cap: int = 500) -> list[list[str]]:
    """Valid, maximal playthroughs (no node repeated): each runs until an ending or a soft-lock."""
    # ponytail: DFS capped at `cap` paths; huge graphs need sampling per act instead.
    out: list[list[str]] = []
    if violations(g.node(g.start), g.initial_state):
        return out

    def dfs(nid, state, path):
        if len(out) >= cap:
            return
        after = apply(g.node(nid), state)
        nxt = [m for m in g.node(nid).next_nodes if m not in path and not violations(g.node(m), after)]
        if not nxt:
            out.append(path)
        for m in nxt:
            dfs(m, after, path + [m])

    dfs(g.start, g.initial_state, [g.start])
    return out


def edge_cover(paths: list[list[str]]) -> list[list[str]]:
    """Greedy: fewest playthroughs that together walk every validly traversable edge."""
    def edges(p):
        return set(zip(p, p[1:]))

    uncovered = set().union(*map(edges, paths)) if paths else set()
    chosen = [] if uncovered or not paths else [max(paths, key=len)]
    while uncovered:
        best = max(paths, key=lambda p: (len(edges(p) & uncovered), len(p)))
        chosen.append(best)
        uncovered -= edges(best)
    return chosen
