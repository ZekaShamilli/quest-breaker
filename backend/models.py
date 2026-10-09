from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class QuestNode(BaseModel):
    id: str
    title: str
    description: str = ""
    character_actors: list[str] = []
    pre_conditions: dict[str, Any] = {}   # state key -> required value
    state_mutations: dict[str, Any] = {}  # state key -> value set on completion
    next_nodes: list[str] = []            # player choices
    tags: list[str] = []                  # violent, help, refuse, enemy_faction, optional, companion, main, ending
    narrative_requirements: str = ""      # implicit, free-text conditions checked by the LLM


class QuestGraph(BaseModel):
    name: str
    start: str
    initial_state: dict[str, Any] = {}
    nodes: list[QuestNode]

    @model_validator(mode="after")
    def _check_refs(self):
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate node ids")
        known = set(ids)
        if self.start not in known:
            raise ValueError(f"start node '{self.start}' does not exist")
        for n in self.nodes:
            for m in n.next_nodes:
                if m not in known:
                    raise ValueError(f"node '{n.id}' links to unknown node '{m}'")
        return self

    def node(self, node_id: str) -> QuestNode:
        return next(n for n in self.nodes if n.id == node_id)


class NarrativeState(BaseModel):
    entities: dict[str, Any] = {}


class DeadlockReport(BaseModel):
    error_type: Literal["StateContradiction", "UnreachablePath", "CircularDependency"]
    affected_nodes: list[str]                       # broken nodes (red)
    conflict_nodes: list[str] = []                  # nodes that caused the conflict (amber)
    failing_path: list[str] = []
    explanation: str
    suggested_fix: str = ""
    severity: Literal["critical", "warning"] = "warning"
    source: Literal["symbolic", "llm"] = "symbolic"


class TraceStep(BaseModel):
    node_id: str
    title: str
    reason: str
    state: NarrativeState


class SimulationRun(BaseModel):
    archetype: str
    outcome: Literal["completed", "soft_locked", "loop"]
    soft_locked: bool
    trace: list[TraceStep]
    blocked_options: list[dict] = Field(default_factory=list)  # options rejected at the final step
    message: str
