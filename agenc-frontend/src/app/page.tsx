"use client";
import { useState, useEffect, useRef } from "react";

type NodeStatus = "idle" | "busy" | "evaluating" | "claiming" | "working" | "rejected" | "completed";

interface NodeState {
  status: NodeStatus;
  label: string;
  specialty?: string;
}

interface BountyCard {
  bounty_id: string;
  task: string;
  reward: string;
  status: "PENDING" | "CLAIMED" | "EXECUTING" | "COMPLETED" | "UNCLAIMED";
  winner_specialty?: string;
  worker_id?: string;
  result?: string;
}

interface LogEntry {
  time: string;
  tag: string;
  msg: string;
}

const API = "http://127.0.0.1:8000";

function NodeCard({ id, node }: { id: string; node: NodeState }) {
  const S: Record<NodeStatus, { ring: string; glow?: string; ping?: string }> = {
    idle:       { ring: "ring-zinc-800" },
    busy:       { ring: "ring-amber-400/60",   ping: "bg-amber-400/30",   glow: "0 0 20px rgba(251,191,36,0.2)" },
    evaluating: { ring: "ring-zinc-500/60" },
    claiming:   { ring: "ring-emerald-400/60", ping: "bg-emerald-400/25", glow: "0 0 20px rgba(52,211,153,0.2)" },
    working:    { ring: "ring-emerald-400/80", ping: "bg-emerald-400/30", glow: "0 0 28px rgba(52,211,153,0.3)" },
    rejected:   { ring: "ring-red-500/60" },
    completed:  { ring: "ring-emerald-300/60" },
  };
  const DOT: Record<NodeStatus, string> = {
    idle: "bg-zinc-700", busy: "bg-amber-400", evaluating: "bg-zinc-400",
    claiming: "bg-emerald-400", working: "bg-emerald-400", rejected: "bg-red-400", completed: "bg-emerald-300",
  };
  const ICON: Record<string, string> = { emitter: "⬡", worker_1: "◈", worker_2: "◇" };

  const { ring, glow, ping } = S[node.status];

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-14 h-14">
        {ping && <span className={`absolute inset-0 rounded-full ${ping} animate-ping`} />}
        <div
          className={`w-14 h-14 rounded-full ring-2 ${ring} bg-zinc-900 flex items-center justify-center transition-all duration-500`}
          style={glow ? { boxShadow: glow } : undefined}
        >
          <span className="text-xl select-none">{ICON[id] ?? "●"}</span>
        </div>
      </div>
      <div className="text-center">
        <p className="text-xs font-medium text-zinc-300">{node.label}</p>
        {node.specialty && <p className="text-[10px] text-zinc-600 mt-0.5">{node.specialty}</p>}
        <div className="flex items-center justify-center gap-1 mt-1.5">
          <span className={`w-1 h-1 rounded-full ${DOT[node.status]}`} />
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: BountyCard["status"] }) {
  const M: Record<BountyCard["status"], string> = {
    PENDING:   "text-amber-400/80 bg-amber-500/8 border-amber-500/15",
    CLAIMED:   "text-sky-400/80 bg-sky-500/8 border-sky-500/15",
    EXECUTING: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    COMPLETED: "text-emerald-300 bg-emerald-500/10 border-emerald-500/20",
    UNCLAIMED: "text-zinc-500 bg-zinc-800/40 border-zinc-700/20",
  };
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${M[status]} uppercase tracking-wide`}>
      {status === "EXECUTING" ? "Running" : status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}

export default function Home() {
  const [task, setTask] = useState("");
  const [reward, setReward] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [bounties, setBounties] = useState<BountyCard[]>([]);
  const [nodes, setNodes] = useState<Record<string, NodeState>>({
    emitter:  { status: "idle", label: "Emitter" },
    worker_1: { status: "idle", label: "Worker 1", specialty: "Data Analyst" },
    worker_2: { status: "idle", label: "Worker 2", specialty: "Creative Strategist" },
  });
  const logsEndRef = useRef<HTMLDivElement>(null);

  const addLog = (tag: string, msg: string) =>
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), tag, msg }]);

  const setNodeStatus = (node_id: string, status: NodeStatus) =>
    setNodes(prev => ({ ...prev, [node_id]: { ...prev[node_id], status } }));

  const flashNode = (node_id: string, s: NodeStatus, ms = 2000) => {
    setNodeStatus(node_id, s);
    setTimeout(() => setNodeStatus(node_id, "idle"), ms);
  };

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  useEffect(() => {
    const es = new EventSource(`${API}/api/events`);

    es.addEventListener("node_snapshot", (e) => {
      const snap = JSON.parse(e.data) as Record<string, NodeState>;
      setNodes(prev => {
        const next = { ...prev };
        for (const [id, state] of Object.entries(snap)) next[id] = { ...prev[id], ...state };
        return next;
      });
    });
    es.addEventListener("node_status", (e) => {
      const { node_id, status } = JSON.parse(e.data);
      setNodeStatus(node_id, status as NodeStatus);
    });
    es.addEventListener("bounty_posted", (e) => {
      const { bounty_id, task, reward } = JSON.parse(e.data);
      setBounties(prev => [{ bounty_id, task, reward, status: "PENDING" }, ...prev]);
      addLog("new", `#${bounty_id} — ${task.slice(0, 60)}${task.length > 60 ? "…" : ""}`);
    });
    es.addEventListener("worker_claimed", (e) => {
      const { bounty_id, worker_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key) setNodeStatus(node_key, "claiming");
      addLog("bid", `${specialty} bid on #${bounty_id}`);
    });
    es.addEventListener("worker_awarded", (e) => {
      const { bounty_id, worker_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key) setNodeStatus(node_key, "working");
      setBounties(prev => prev.map(b =>
        b.bounty_id === bounty_id ? { ...b, status: "EXECUTING", winner_specialty: specialty, worker_id } : b
      ));
      addLog("win", `${specialty} awarded #${bounty_id}`);
    });
    es.addEventListener("worker_rejected", (e) => {
      const { bounty_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key) flashNode(node_key, "rejected", 2000);
      addLog("rej", `${specialty} stood down`);
    });
    es.addEventListener("bounty_completed", (e) => {
      const { bounty_id, result, specialty, worker_id } = JSON.parse(e.data);
      setBounties(prev => prev.map(b =>
        b.bounty_id === bounty_id ? { ...b, status: "COMPLETED", result, winner_specialty: specialty, worker_id } : b
      ));
      addLog("done", `${result.slice(0, 90)}${result.length > 90 ? "…" : ""}`);
    });
    es.addEventListener("bounty_unclaimed", (e) => {
      const { bounty_id } = JSON.parse(e.data);
      setBounties(prev => prev.map(b => b.bounty_id === bounty_id ? { ...b, status: "UNCLAIMED" } : b));
      addLog("exp", `#${bounty_id} expired`);
    });

    return () => es.close();
  }, []);

  const submitBounty = async (e: React.FormEvent, overrideTask?: string) => {
    e.preventDefault();
    const t = overrideTask ?? task;
    if (!t.trim()) return;
    await fetch(`${API}/api/bounty`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: t, reward }),
    });
    if (!overrideTask) setTask("");
  };

  const repostBounty = (b: BountyCard) =>
    submitBounty({ preventDefault: () => {} } as React.FormEvent, b.task);

  const TAG_COLOR: Record<string, string> = {
    new:  "text-amber-500",
    bid:  "text-sky-500",
    win:  "text-emerald-400",
    rej:  "text-red-400/70",
    done: "text-emerald-300",
    exp:  "text-zinc-600",
  };

  return (
    <div className="min-h-screen bg-[#0c0c0d] text-zinc-100 font-sans">

      {/* Header */}
      <header className="border-b border-zinc-800/50 px-6 h-12 flex items-center justify-between max-w-6xl mx-auto">
        <div className="flex items-center gap-2.5">
          <span className="text-emerald-500 text-sm">⬡</span>
          <span className="text-sm font-semibold tracking-tight">AgenC</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-zinc-500">live</span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">

        {/* Swarm */}
        <div className="rounded-2xl border border-zinc-800/40 bg-zinc-900/20 p-8 flex items-center justify-center gap-0">
          {Object.entries(nodes).map(([id, node], i, arr) => (
            <div key={id} className="flex items-center">
              <NodeCard id={id} node={node} />
              {i < arr.length - 1 && (
                <div className="flex items-center px-5 pb-6">
                  <div className="h-px w-10 bg-zinc-800" />
                  <div className="w-1 h-1 rounded-full bg-zinc-700 mx-1" />
                  <div className="h-px w-10 bg-zinc-800" />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">

          {/* Logs */}
          <div className="lg:col-span-2 rounded-2xl border border-zinc-800/40 bg-zinc-900/20 h-[500px] flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-zinc-800/40">
              <span className="text-xs text-zinc-500 font-medium">Activity</span>
            </div>
            {logs.length === 0 ? (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-xs text-zinc-700">Waiting for events…</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5
                [&::-webkit-scrollbar]:w-1
                [&::-webkit-scrollbar-thumb]:rounded-full
                [&::-webkit-scrollbar-thumb]:bg-zinc-800">
                {logs.map((log, i) => (
                  <div key={i} className="group flex items-start gap-2.5 px-2 py-1.5 rounded-lg hover:bg-zinc-800/30 transition-colors">
                    <span className={`text-xs font-mono shrink-0 w-8 ${TAG_COLOR[log.tag] ?? "text-zinc-500"}`}>{log.tag}</span>
                    <p className="text-xs text-zinc-400 leading-relaxed flex-1 min-w-0 break-words">{log.msg}</p>
                    <span className="text-[10px] font-mono text-zinc-700 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity pt-px">{log.time}</span>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            )}
          </div>

          {/* Right */}
          <div className="lg:col-span-3 space-y-4">

            {/* Bounties */}
            {bounties.length > 0 && (
              <div className="rounded-2xl border border-zinc-800/40 bg-zinc-900/20 overflow-hidden">
                <div className="px-4 py-3 border-b border-zinc-800/40 flex items-center justify-between">
                  <span className="text-xs text-zinc-500 font-medium">Bounties</span>
                  <button
                    onClick={async () => { await fetch(`${API}/api/bounties`, { method: "DELETE" }); setBounties([]); }}
                    className="text-[10px] text-zinc-700 hover:text-red-400 transition-colors"
                  >
                    Clear
                  </button>
                </div>
                <div className="divide-y divide-zinc-800/30 max-h-64 overflow-y-auto
                  [&::-webkit-scrollbar]:w-1
                  [&::-webkit-scrollbar-thumb]:rounded-full
                  [&::-webkit-scrollbar-thumb]:bg-zinc-800">
                  {bounties.map(b => (
                    <div key={b.bounty_id} className="px-4 py-3 space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm text-zinc-200 leading-snug flex-1 min-w-0">
                          {b.task.slice(0, 100)}{b.task.length > 100 ? "…" : ""}
                        </p>
                        <StatusBadge status={b.status} />
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] font-mono text-zinc-700">#{b.bounty_id}</span>
                        {b.reward && <span className="text-[10px] text-emerald-600/80">{b.reward}</span>}
                        {b.winner_specialty && b.status !== "UNCLAIMED" && (
                          <span className="text-[10px] text-zinc-500">{b.winner_specialty}</span>
                        )}
                        {b.status === "UNCLAIMED" && (
                          <button onClick={() => repostBounty(b)} className="text-[10px] text-amber-500 hover:text-amber-400 transition-colors">
                            ↺ Repost
                          </button>
                        )}
                      </div>
                      {b.result && (
                        <p className="text-xs text-zinc-500 leading-relaxed pt-1 border-t border-zinc-800/40">
                          {b.result.slice(0, 200)}{b.result.length > 200 ? "…" : ""}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Form */}
            <div className="rounded-2xl border border-zinc-800/40 bg-zinc-900/20 p-5">
              <form onSubmit={submitBounty} className="space-y-3">
                <textarea
                  className="w-full bg-zinc-950/60 border border-zinc-800/60 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-700
                    focus:border-zinc-600 focus:outline-none resize-none transition-colors"
                  rows={4}
                  value={task}
                  onChange={e => setTask(e.target.value)}
                  placeholder="Describe the task…"
                  required
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    className="flex-1 bg-zinc-950/60 border border-zinc-800/60 rounded-xl px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-700
                      focus:border-zinc-600 focus:outline-none transition-colors"
                    value={reward}
                    onChange={e => setReward(e.target.value)}
                    placeholder="Reward (e.g. 50 USDC)"
                    required
                  />
                  <button
                    type="submit"
                    className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:bg-emerald-600
                      text-zinc-950 font-semibold text-sm transition-colors shrink-0"
                  >
                    Broadcast
                  </button>
                </div>
              </form>
            </div>

          </div>
        </div>
      </main>
    </div>
  );
}
