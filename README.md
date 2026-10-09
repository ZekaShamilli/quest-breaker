# Quest-Breaker

Finds narrative deadlocks in branching quest graphs (JSON), runs adversarial player archetypes against them, and shows the broken paths on an interactive graph.

## Run

```bash
./run.sh            # macOS/Linux/Git Bash
```
```powershell
./run.ps1           # Windows PowerShell
```
```bash
docker build -t quest-breaker . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY quest-breaker
```

Then open http://localhost:8000. The AI semantic pass and AI-written story fixes need an LLM. Put these in `backend/.env` (gitignored), or set them as environment variables:

```
AZURE_OPENAI_ENDPOINT=https://<resource>.services.ai.azure.com/openai/v1/
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_MODEL=gpt-5.6-sol
```

Alternatively, set `ANTHROPIC_API_KEY` to use Claude. With neither, the graph checker and simulator still work and use built-in fix suggestions.

UI dev mode: run the backend on :8000, then `cd frontend && npm run dev` (it proxies `/api`).

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q     # .venv/bin/python on macOS/Linux
```

## Evaluation: graph-only vs LLM-only vs hybrid

```bash
cd backend && .venv/Scripts/python compare.py      # writes eval_results.md
```

`benchmark.py` generates 16 quest graphs with 32 labeled bugs. Half are encoded as state flags; the other half exist **only in the story text**, the way real scripts are written. There are also 32 look-alike traps that are not bugs, such as a character who is spared or is needed *before* being killed. The script scores precision and recall for each approach, plus Claude calls, cost and time, and lists every miss and false alarm. By default it runs on held-out seeds 16-31; seeds 0-15 were used to tune the prompt. Without LLM credentials, only the graph-only row runs.

Demo datasets:
- `corrupted_witcher_style`: flag bugs that the graph checker finds.
- `hidden_text_bugs`: the graph checker finds **0** issues. A dead minstrel sings at the wedding, and a burned bridge is crossed; only the AI pass catches these.
- `clean_quest_tree`: no bugs.

## How it works

| File | Role |
|---|---|
| `backend/engine.py` | **Step A, graph checker.** Runs BFS over `(node, narrative state)` pairs. Reports a `StateContradiction` when a pre-condition fails because an earlier quest set the key (critical if the player has no other branch), a `CircularDependency` when a requirement is only granted downstream or a loop has no exit, and an `UnreachablePath` when no valid playthrough reaches a node. |
| `backend/llm.py` | **Step B, semantic validator.** Picks the fewest valid playthroughs that together walk every edge (`engine.edge_cover`), sends each playthrough to Claude (`claude-opus-5-5`, structured output) and asks which steps contradict earlier ones. It also rewrites the fix suggestions. Server-side refusal fallback (`fallbacks="default"`) is on. |
| `backend/simulator.py` | Murder Hobo, Contrarian and Speedrunner: walkers that pick greedily by tag score and report soft-locks. |
| `backend/main.py` | FastAPI app: `POST /api/validate`, `POST /api/simulate`, `GET /api/datasets`. It also serves the built UI. |
| `frontend/src/App.jsx` | React Flow graph, inspector panel and top-bar actions. |

### Quest JSON

```json
{ "name": "...", "start": "q1", "initial_state": {"garrick": "alive"},
  "nodes": [{ "id": "q1", "title": "...", "description": "...", "character_actors": ["Garrick"],
              "pre_conditions": {"garrick": "alive"}, "state_mutations": {"sword": "forged"},
              "next_nodes": ["q2"], "tags": ["main", "violent", "help", "refuse", "enemy_faction", "optional", "companion"],
              "narrative_requirements": "free text checked by the LLM" }] }
```

A node with no `next_nodes` is an ending. A pre-condition is an exact-match equality on a state key.
