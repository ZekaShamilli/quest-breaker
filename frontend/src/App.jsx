import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, Controls, Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useReactFlow } from "@xyflow/react";
import {
  AlertTriangle, Bot, CheckCircle2, CircleSlash, FileJson, GitBranch, Loader2, Lock, Repeat,
  ShieldCheck, Skull, Sparkles, Upload, Users, Wand2, Zap,
} from "lucide-react";

const STATUS = {
  valid: { ring: "border-emerald-500/70", dot: "bg-emerald-500", label: "Valid", text: "text-emerald-400" },
  conflict: { ring: "border-amber-400", dot: "bg-amber-400", label: "Conflict prerequisite", text: "text-amber-300" },
  broken: { ring: "border-red-500 glow-red", dot: "bg-red-500", label: "Broken / deadlock", text: "text-red-400" },
};
const TYPE_ICON = { StateContradiction: AlertTriangle, UnreachablePath: CircleSlash, CircularDependency: Repeat };
const ARCHETYPE = {
  murder_hobo: { label: "Murder Hobo", icon: Skull },
  contrarian: { label: "Contrarian", icon: CircleSlash },
  speedrunner: { label: "Speedrunner", icon: Zap },
};

async function api(path, body) {
  const res = await fetch(`/api/${path}`, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

function QuestNodeCard({ data }) {
  const s = STATUS[data.status];
  return (
    <div className={`relative w-56 rounded-lg border-2 bg-[#141821] px-3 py-2 text-left transition ${s.ring}
      ${data.onPath ? "ring-2 ring-sky-400 ring-offset-2 ring-offset-[#0b0d12]" : ""} ${data.dim ? "opacity-35" : ""}`}>
      <Handle type="target" position={Position.Left} className="!bg-slate-500" />
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
        <span className="truncate text-sm font-semibold text-slate-100">{data.title}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-slate-400">
        <span className="font-mono">{data.id}</span>
        {data.tags.map((t) => <span key={t} className="rounded bg-slate-700/60 px-1">{t}</span>)}
        {Object.keys(data.pre_conditions).length > 0 && <Lock size={10} className="text-amber-300" />}
        {data.narrative_requirements && <Sparkles size={10} className="text-violet-300" />}
      </div>
      {data.stepLabel && (
        <span className="absolute -top-2.5 -right-2.5 rounded-full bg-sky-500 px-1.5 text-[10px] font-bold text-white">{data.stepLabel}</span>
      )}
      <Handle type="source" position={Position.Right} className="!bg-slate-500" />
    </div>
  );
}
const nodeTypes = { quest: QuestNodeCard };

function Graph({ result, path, stepLabels, onSelectNode }) {
  const { fitView } = useReactFlow();
  const onPath = useMemo(() => new Set(path), [path]);
  const pathEdges = useMemo(() => new Set(path.slice(1).map((n, i) => `${path[i]}->${n}`)), [path]);

  const nodes = useMemo(() => result.nodes.map((n) => ({
    id: n.id, type: "quest", position: n.position,
    data: { ...n, onPath: onPath.has(n.id), dim: path.length > 0 && !onPath.has(n.id), stepLabel: stepLabels[n.id] },
  })), [result, onPath, path, stepLabels]);

  const edges = useMemo(() => result.edges.map((e) => {
    const hot = pathEdges.has(e.id);
    return {
      ...e, animated: hot,
      style: { stroke: hot ? "#38bdf8" : "#475569", strokeWidth: hot ? 3 : 1.5, opacity: path.length && !hot ? 0.35 : 1 },
    };
  }), [result, pathEdges, path]);

  useEffect(() => { setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 0); }, [result, fitView]);

  return (
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} nodesConnectable={false} minZoom={0.2}
      onNodeClick={(_, n) => onSelectNode(n.id)} onPaneClick={() => onSelectNode(null)}>
      <Background color="#1f2937" gap={22} />
      <Controls className="!border-slate-700 [&>button]:!bg-slate-800 [&>button]:!border-slate-700 [&>button]:!fill-slate-300" />
      <MiniMap pannable zoomable className="!bg-[#141821]" maskColor="rgba(11,13,18,.7)"
        nodeColor={(n) => ({ valid: "#10b981", conflict: "#fbbf24", broken: "#ef4444" })[n.data.status]} />
    </ReactFlow>
  );
}

function Report({ r, active, onClick, titles }) {
  const Icon = TYPE_ICON[r.error_type];
  return (
    <button onClick={onClick} className={`w-full rounded-lg border p-3 text-left transition
      ${active ? "border-sky-400 bg-sky-950/30" : "border-slate-700/70 bg-[#141821] hover:border-slate-500"}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Icon size={14} className={r.severity === "critical" ? "text-red-400" : "text-amber-300"} />
        <span className="font-semibold text-slate-100">{r.error_type}</span>
        <span className={`rounded px-1.5 py-0.5 uppercase ${r.severity === "critical" ? "bg-red-500/20 text-red-300" : "bg-amber-400/15 text-amber-200"}`}>{r.severity}</span>
        <span className="ml-auto flex items-center gap-1 text-slate-400">
          {r.source === "llm" ? <><Bot size={12} /> AI semantic</> : <><GitBranch size={12} /> graph</>}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-slate-300">{r.explanation}</p>
      {r.failing_path.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px]">
          {r.failing_path.map((n, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <span className="text-slate-600">→</span>}
              <span className={`rounded px-1.5 py-0.5 ${r.affected_nodes.includes(n) ? "bg-red-500/25 text-red-200" : r.conflict_nodes.includes(n) ? "bg-amber-400/20 text-amber-200" : "bg-slate-700/60 text-slate-300"}`}>
                {titles[n]}
              </span>
            </span>
          ))}
        </div>
      )}
      {r.suggested_fix && (
        <div className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/10 p-2 text-xs leading-relaxed text-violet-100">
          <div className="mb-1 flex items-center gap-1 font-semibold text-violet-300"><Wand2 size={12} /> Suggested Story Fix</div>
          {r.suggested_fix}
        </div>
      )}
    </button>
  );
}

function Run({ run, active, onClick }) {
  const A = ARCHETYPE[run.archetype];
  const ok = run.outcome === "completed";
  return (
    <button onClick={onClick} className={`w-full rounded-lg border p-3 text-left transition
      ${active ? "border-sky-400 bg-sky-950/30" : "border-slate-700/70 bg-[#141821] hover:border-slate-500"}`}>
      <div className="flex items-center gap-2 text-sm">
        <A.icon size={16} className="text-slate-300" />
        <span className="font-semibold">{A.label}</span>
        <span className={`ml-auto rounded px-1.5 py-0.5 text-xs uppercase ${ok ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"}`}>
          {ok ? "completed" : run.outcome.replace("_", "-")}
        </span>
      </div>
      <p className={`mt-2 text-xs ${ok ? "text-slate-400" : "text-red-300"}`}>{run.message}</p>
      {active && (
        <ol className="mt-3 space-y-1.5 border-l border-slate-700 pl-3 text-xs">
          {run.trace.map((t, i) => (
            <li key={i}>
              <span className="font-mono text-sky-300">{i + 1}.</span> <span className="text-slate-100">{t.title}</span>
              <span className="text-slate-500"> — {t.reason}</span>
            </li>
          ))}
          {run.blocked_options.map((b) => (
            <li key={b.node} className="text-red-300">
              <Lock size={11} className="inline" /> {b.title}: {Object.entries(b.violations).map(([k, [e, a]]) => `${k} must be ${JSON.stringify(e)}, is ${JSON.stringify(a)}`).join("; ")}
            </li>
          ))}
        </ol>
      )}
    </button>
  );
}

function KV({ label, obj }) {
  const entries = Object.entries(obj);
  if (!entries.length) return null;
  return (
    <div>
      <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="flex flex-wrap gap-1">
        {entries.map(([k, v]) => <code key={k} className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">{k} = {JSON.stringify(v)}</code>)}
      </div>
    </div>
  );
}

function NodeDetail({ node, reports, titles, onReport }) {
  const s = STATUS[node.status];
  const mine = reports.filter((r) => r.affected_nodes.includes(node.id) || r.conflict_nodes.includes(node.id));
  return (
    <div className="space-y-4">
      <div>
        <div className={`text-xs ${s.text}`}>{s.label}</div>
        <h3 className="text-lg font-semibold">{node.title}</h3>
        <p className="mt-1 text-sm text-slate-300">{node.description}</p>
      </div>
      {node.character_actors.length > 0 && <KV label="Actors" obj={Object.fromEntries(node.character_actors.map((a) => [a, "present"]))} />}
      <KV label="Pre-conditions" obj={node.pre_conditions} />
      <KV label="State mutations" obj={node.state_mutations} />
      {node.narrative_requirements && (
        <div className="text-sm"><div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Implicit narrative requirements</div>{node.narrative_requirements}</div>
      )}
      <div className="text-xs text-slate-400">Next: {node.next_nodes.map((n) => titles[n]).join(", ") || "— ending —"}</div>
      {mine.map((r, i) => <Report key={i} r={r} titles={titles} onClick={() => onReport(r)} />)}
    </div>
  );
}

const PLAIN = {
  StateContradiction: ["Broken by an earlier choice", "A quest needs something that a choice the player made earlier has made impossible (e.g. a character who was killed)."],
  CircularDependency: ["Waits on itself", "A quest needs something that can only happen after it, or a group of quests loops with no way out."],
  UnreachablePath: ["Can never be reached", "No playthrough ever gets the player to this quest. It is dead content."],
};

function Overview({ result, runs, titles, onOpen, onRuns }) {
  const reports = result.reports;
  const critical = reports.filter((r) => r.severity === "critical").length;
  const ai = reports.filter((r) => r.source === "llm").length;
  const order = [...reports.keys()].sort((a, b) => (reports[a].severity === "critical" ? 0 : 1) - (reports[b].severity === "critical" ? 0 : 1));
  const stuck = runs.filter((r) => r.soft_locked);
  const types = [...new Set(reports.map((r) => r.error_type))];
  return (
    <div className="space-y-4 text-sm">
      <div className={`rounded-lg border p-3 ${reports.length === 0 ? "border-emerald-500/40 bg-emerald-500/10" : critical ? "border-red-500/40 bg-red-500/10" : "border-amber-400/40 bg-amber-400/10"}`}>
        <div className="font-semibold text-slate-100">
          {reports.length === 0 ? "This story is consistent" : critical ? "Players can get stuck in this story" : "No dead ends, but some content is broken"}
        </div>
        <p className="mt-1 text-slate-300">
          {reports.length === 0
            ? "Every reachable storyline checks out. No quest depends on something an earlier choice removed."
            : `Found ${reports.length} problem${reports.length > 1 ? "s" : ""}: ${critical} critical (the player gets stuck), ${reports.length - critical} warning${reports.length - critical === 1 ? "" : "s"}. ${ai ? `${ai} ${ai === 1 ? "was" : "were"} found by AI reading the story text.` : ""}`}
        </p>
      </div>

      {reports.length > 0 && (
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">What to fix, most urgent first</h4>
          <ol className="space-y-2">
            {order.map((i, n) => {
              const r = reports[i];
              const where = r.affected_nodes.map((id) => titles[id]).join(", ");
              const cause = r.conflict_nodes.map((id) => titles[id]).join(", ");
              return (
                <li key={i}>
                  <button onClick={() => onOpen(i)} className="w-full rounded-lg border border-slate-700/70 bg-[#141821] p-3 text-left hover:border-slate-500">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-700 font-bold">{n + 1}</span>
                      <span className={r.severity === "critical" ? "text-red-300" : "text-amber-200"}>{PLAIN[r.error_type][0]}</span>
                      <span className="ml-auto text-slate-500">{r.source === "llm" ? "found by AI" : "found by graph check"}</span>
                    </div>
                    <p className="mt-1.5 text-slate-200"><b>{where}</b>{cause && <> is broken by <b>{cause}</b></>}.</p>
                    {r.suggested_fix && <p className="mt-1 text-xs text-violet-200"><Wand2 size={11} className="mr-1 inline" />{r.suggested_fix}</p>}
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Player test</h4>
        {runs.length === 0
          ? <p className="text-slate-400">Not run yet. <button onClick={onRuns} className="text-sky-300 underline">Run all three player types</button> to see who gets stuck.</p>
          : <p className="text-slate-300">{stuck.length ? `${stuck.length} of ${runs.length} player types got stuck: ${stuck.map((r) => ARCHETYPE[r.archetype].label).join(", ")}.` : `All ${runs.length} player types reached an ending.`}</p>}
      </section>

      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">How to read the graph</h4>
        <ul className="space-y-1.5 text-slate-300">
          <li className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Green: quest works on every path that reaches it</li>
          <li className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-red-500" /> Red: quest is broken (a deadlock lands here)</li>
          <li className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-amber-400" /> Amber: the earlier choice that causes the break</li>
          <li className="flex items-center gap-2"><span className="h-0.5 w-2.5 bg-sky-400" /> Blue line: the exact playthrough that fails. Click a problem to show it.</li>
        </ul>
        {types.length > 0 && (
          <dl className="mt-3 space-y-2 text-xs">
            {types.map((t) => <div key={t}><dt className="font-semibold text-slate-200">{t}: {PLAIN[t][0]}</dt><dd className="text-slate-400">{PLAIN[t][1]}</dd></div>)}
            {ai > 0 && <div><dt className="font-semibold text-slate-200">Found by AI</dt><dd className="text-slate-400">Contradictions that exist only in the story text (not in the game's flags), found by an AI model reading each playthrough.</dd></div>}
          </dl>
        )}
      </section>
    </div>
  );
}

function Btn({ onClick, busy, icon: Icon, children, tone = "slate" }) {
  const tones = { slate: "bg-slate-800 hover:bg-slate-700", red: "bg-red-600 hover:bg-red-500", sky: "bg-sky-600 hover:bg-sky-500" };
  return (
    <button onClick={onClick} disabled={busy} className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:opacity-60 ${tones[tone]}`}>
      {busy ? <Loader2 size={15} className="animate-spin" /> : <Icon size={15} />} {children}
    </button>
  );
}

export default function App() {
  const [datasets, setDatasets] = useState([]);
  const [dataset, setDataset] = useState("corrupted_witcher_style");
  const [custom, setCustom] = useState(null);
  const [useLlm, setUseLlm] = useState(true);
  const [result, setResult] = useState(null);
  const [runs, setRuns] = useState([]);
  const [tab, setTab] = useState("overview");
  const [active, setActive] = useState(null); // {kind: "report"|"run", idx}
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef();

  const source = custom ? { graph: custom } : { dataset };

  const audit = useCallback(async (llm = useLlm) => {
    setBusy("audit"); setError(""); setActive(null);
    try {
      setResult(await api("validate", { ...source, use_llm: llm }));
      setTab("overview");
    } catch (e) { setError(e.message); }
    setBusy("");
  }, [dataset, custom, useLlm]); // eslint-disable-line react-hooks/exhaustive-deps

  const simulate = async (archetypes, key) => {
    setBusy(key); setError("");
    try {
      const { runs } = await api("simulate", { ...source, archetypes });
      setRuns(runs); setTab("sims"); setActive({ kind: "run", idx: 0 });
    } catch (e) { setError(e.message); }
    setBusy("");
  };

  useEffect(() => { api("datasets").then(setDatasets).catch((e) => setError(e.message)); }, []);
  useEffect(() => { setRuns([]); audit(false); }, [dataset, custom]); // eslint-disable-line react-hooks/exhaustive-deps

  const onUpload = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    try { setCustom(JSON.parse(await file.text())); } catch { setError(`${file.name} is not valid JSON`); }
  };

  const titles = useMemo(() => Object.fromEntries((result?.nodes || []).map((n) => [n.id, n.title])), [result]);
  const activeReport = active?.kind === "report" ? result?.reports[active.idx] : null;
  const activeRun = active?.kind === "run" ? runs[active.idx] : null;
  const path = activeReport?.failing_path || (activeRun && [...activeRun.trace.map((t) => t.node_id), ...activeRun.blocked_options.slice(0, 1).map((b) => b.node)]) || [];
  const stepLabels = useMemo(() => {
    const out = {};
    path.forEach((n, i) => { out[n] = out[n] ? `${out[n]},${i + 1}` : `${i + 1}`; });
    return out;
  }, [path.join()]); // eslint-disable-line react-hooks/exhaustive-deps

  const counts = useMemo(() => {
    const c = { valid: 0, conflict: 0, broken: 0 };
    result?.nodes.forEach((n) => c[n.status]++);
    return c;
  }, [result]);
  const selectedNode = result?.nodes.find((n) => n.id === selected);
  const critical = result?.reports.filter((r) => r.severity === "critical").length || 0;

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-800 bg-[#0f1219] px-4 py-2.5">
        <div className="mr-2 flex items-center gap-2">
          <ShieldCheck className="text-red-400" size={22} />
          <div>
            <div className="text-sm font-bold tracking-wide">QUEST-BREAKER</div>
            <div className="text-[10px] text-slate-500">Narrative Deadlock &amp; Inconsistency Engine</div>
          </div>
        </div>
        <select value={custom ? "__custom" : dataset} onChange={(e) => { setCustom(null); setDataset(e.target.value); }}
          className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm" aria-label="Quest graph">
          {datasets.map((d) => <option key={d} value={d}>{d}.json</option>)}
          {custom && <option value="__custom">{custom.name || "uploaded"} (uploaded)</option>}
        </select>
        <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={onUpload} />
        <Btn icon={Upload} onClick={() => fileRef.current.click()}>Upload JSON</Btn>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-slate-300" title="Run Claude semantic validation and AI story fixes">
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} className="accent-violet-500" />
            <Bot size={14} /> AI semantic pass
          </label>
          <Btn icon={ShieldCheck} tone="sky" busy={busy === "audit"} onClick={() => audit()}>Run Full Integrity Audit</Btn>
          <Btn icon={Skull} tone="red" busy={busy === "hobo"} onClick={() => simulate(["murder_hobo"], "hobo")}>Run Murder Hobo Simulation</Btn>
          <Btn icon={Users} busy={busy === "all"} onClick={() => simulate(Object.keys(ARCHETYPE), "all")}>All Archetypes</Btn>
        </div>
      </header>

      {error && <div className="border-b border-red-900 bg-red-950/60 px-4 py-2 text-sm text-red-200">{error}</div>}

      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <section className="relative min-h-[420px] flex-1">
          {result ? (
            <ReactFlowProvider>
              <Graph result={result} path={path} stepLabels={stepLabels} onSelectNode={(id) => { setSelected(id); if (id) setTab("node"); }} />
            </ReactFlowProvider>
          ) : (
            <div className="flex h-full items-center justify-center text-slate-500"><Loader2 className="mr-2 animate-spin" /> Loading quest graph…</div>
          )}
          <div className="pointer-events-none absolute left-3 top-3 space-y-1 rounded-md border border-slate-800 bg-[#0f1219]/90 px-3 py-2 text-xs">
            {Object.entries(STATUS).map(([k, s]) => (
              <div key={k} className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${s.dot}`} />{s.label} <span className="text-slate-500">{counts[k]}</span></div>
            ))}
            <div className="flex items-center gap-2 text-slate-400"><span className="h-0.5 w-3 bg-sky-400" /> Selected path</div>
          </div>
        </section>

        <aside className="flex w-full flex-col border-l border-slate-800 bg-[#0f1219] lg:w-[440px]">
          <div className="border-b border-slate-800 px-4 py-3">
            <div className="text-xs text-slate-500">{result?.name}</div>
            <div className="mt-1 flex items-center gap-2 text-sm">
              {result && (result.reports.length === 0
                ? <><CheckCircle2 size={16} className="text-emerald-400" /> No deadlocks found</>
                : <><AlertTriangle size={16} className="text-red-400" /> {result.reports.length} issues · {critical} critical</>)}
            </div>
            <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-500"><Bot size={11} /> LLM: {result?.llm_status ?? "—"}</div>
          </div>
          <nav className="flex border-b border-slate-800 text-sm">
            {[["overview", "Overview"], ["issues", `Deadlocks (${result?.reports.length ?? 0})`], ["sims", `Simulations (${runs.length})`], ["node", "Node"]].map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)}
                className={`flex-1 px-3 py-2 ${tab === k ? "border-b-2 border-sky-400 text-slate-100" : "text-slate-500 hover:text-slate-300"}`}>{label}</button>
            ))}
          </nav>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            {tab === "overview" && result && (
              <Overview result={result} runs={runs} titles={titles}
                onOpen={(i) => { setActive({ kind: "report", idx: i }); setTab("issues"); }}
                onRuns={() => simulate(Object.keys(ARCHETYPE), "all")} />
            )}
            {tab === "issues" && result?.reports.map((r, i) => (
              <Report key={i} r={r} titles={titles} active={active?.kind === "report" && active.idx === i}
                onClick={() => setActive(active?.kind === "report" && active.idx === i ? null : { kind: "report", idx: i })} />
            ))}
            {tab === "issues" && result?.reports.length === 0 && (
              <p className="p-4 text-center text-sm text-slate-500">Every reachable storyline is consistent.</p>
            )}
            {tab === "sims" && (runs.length ? runs.map((run, i) => (
              <Run key={run.archetype} run={run} active={active?.kind === "run" && active.idx === i}
                onClick={() => setActive({ kind: "run", idx: i })} />
            )) : <p className="p-4 text-center text-sm text-slate-500">Run a simulation from the top bar.</p>)}
            {tab === "node" && (selectedNode
              ? <NodeDetail node={selectedNode} reports={result.reports} titles={titles}
                  onReport={(r) => { setActive({ kind: "report", idx: result.reports.indexOf(r) }); setTab("issues"); }} />
              : <p className="flex items-center justify-center gap-2 p-4 text-sm text-slate-500"><FileJson size={14} /> Click a quest node to inspect it.</p>)}
          </div>
        </aside>
      </main>
    </div>
  );
}
