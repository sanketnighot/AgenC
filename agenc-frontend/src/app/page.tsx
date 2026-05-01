"use client";
import { useState, useEffect, useRef } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
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

// ── Node circle component ─────────────────────────────────────────────────────
function NodeCircle({ id, node }: { id: string; node: NodeState }) {
  const statusStyles: Record<NodeStatus, string> = {
    idle:       "bg-neutral-700",
    busy:       "bg-yellow-400 shadow-lg shadow-yellow-400/50",
    evaluating: "bg-white animate-pulse",
    claiming:   "bg-green-400 shadow-lg shadow-green-400/60",
    working:    "bg-green-400",
    rejected:   "bg-red-500",
    completed:  "bg-green-300",
  };

  const isWorking = node.status === "working";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative flex items-center justify-center w-10 h-10">
        {isWorking && (
          <span className="absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75 animate-ping" />
        )}
        <span className={`relative inline-flex rounded-full w-8 h-8 ${statusStyles[node.status] ?? "bg-neutral-700"} transition-all duration-300`} />
      </div>
      <div className="text-center">
        <p className="text-xs font-semibold text-white">{node.label}</p>
        {node.specialty && (
          <p className="text-xs text-neutral-500">{node.specialty}</p>
        )}
        <p className="text-xs text-neutral-600 capitalize">{node.status}</p>
      </div>
    </div>
  );
}

// ── Bounty status badge ───────────────────────────────────────────────────────
function StatusBadge({ status }: { status: BountyCard["status"] }) {
  const styles: Record<BountyCard["status"], string> = {
    PENDING:   "bg-yellow-900 text-yellow-300",
    CLAIMED:   "bg-blue-900 text-blue-300",
    EXECUTING: "bg-green-900 text-green-300 animate-pulse",
    COMPLETED: "bg-green-800 text-green-200",
    UNCLAIMED: "bg-neutral-800 text-neutral-400",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-mono ${styles[status]}`}>
      {status}
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
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

  const addLog = (tag: string, msg: string) => {
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), tag, msg }]);
  };

  const setNodeStatus = (node_id: string, status: NodeStatus) => {
    setNodes(prev => ({
      ...prev,
      [node_id]: { ...prev[node_id], status },
    }));
  };

  const flashNode = (node_id: string, flashStatus: NodeStatus, durationMs = 2000) => {
    setNodeStatus(node_id, flashStatus);
    setTimeout(() => setNodeStatus(node_id, "idle"), durationMs);
  };

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // SSE subscription
  useEffect(() => {
    const es = new EventSource(`${API}/api/events`);

    es.addEventListener("node_snapshot", (e) => {
      const snapshot = JSON.parse(e.data) as Record<string, NodeState>;
      setNodes(prev => {
        const next = { ...prev };
        for (const [id, state] of Object.entries(snapshot)) {
          next[id] = { ...prev[id], ...state };
        }
        return next;
      });
    });

    es.addEventListener("node_status", (e) => {
      const { node_id, status } = JSON.parse(e.data);
      setNodeStatus(node_id, status as NodeStatus);
    });

    es.addEventListener("bounty_posted", (e) => {
      const { bounty_id, task, reward } = JSON.parse(e.data);
      setBounties(prev => [
        { bounty_id, task, reward, status: "PENDING" },
        ...prev,
      ]);
      addLog("new", `Bounty #${bounty_id} broadcast: "${task.slice(0, 50)}${task.length > 50 ? "…" : ""}"`);
    });

    es.addEventListener("worker_claimed", (e) => {
      const { bounty_id, worker_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key) setNodeStatus(node_key, "claiming");
      addLog("bid", `${worker_id} (${specialty}) bid on #${bounty_id}`);
    });

    es.addEventListener("worker_awarded", (e) => {
      const { bounty_id, worker_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key) setNodeStatus(node_key, "working");
      setBounties(prev => prev.map(b =>
        b.bounty_id === bounty_id
          ? { ...b, status: "EXECUTING", winner_specialty: specialty, worker_id }
          : b
      ));
      addLog("win", `${worker_id} (${specialty}) awarded #${bounty_id} — executing`);
    });

    es.addEventListener("worker_rejected", (e) => {
      const { bounty_id, worker_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key) flashNode(node_key, "rejected", 2000);
      addLog("rej", `${worker_id} (${specialty}) stood down for #${bounty_id}`);
    });

    es.addEventListener("bounty_completed", (e) => {
      const { bounty_id, result, specialty, worker_id } = JSON.parse(e.data);
      setBounties(prev => prev.map(b =>
        b.bounty_id === bounty_id
          ? { ...b, status: "COMPLETED", result, winner_specialty: specialty, worker_id }
          : b
      ));
      addLog("✓", `${specialty}: "${result.slice(0, 80)}${result.length > 80 ? "…" : ""}"`);
    });

    es.addEventListener("bounty_unclaimed", (e) => {
      const { bounty_id } = JSON.parse(e.data);
      setBounties(prev => prev.map(b =>
        b.bounty_id === bounty_id ? { ...b, status: "UNCLAIMED" } : b
      ));
      addLog("⏳", `Bounty #${bounty_id} unclaimed — no matching specialist found`);
    });

    return () => es.close();
  }, []);

  const submitBounty = async (e: React.FormEvent, overrideTask?: string) => {
    e.preventDefault();
    const taskToSend = overrideTask ?? task;
    if (!taskToSend.trim()) return;

    await fetch(`${API}/api/bounty`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: taskToSend, reward }),
    });

    if (!overrideTask) {
      setTask("");
    }
  };

  const repostBounty = (b: BountyCard) => {
    submitBounty({ preventDefault: () => {} } as React.FormEvent, b.task);
  };

  const tagColor: Record<string, string> = {
    new: "text-yellow-400",
    bid: "text-blue-400",
    win: "text-green-400",
    rej: "text-red-400",
    "✓": "text-green-300",
    "⏳": "text-neutral-500",
  };

  return (
    <main className="min-h-screen bg-neutral-950 text-green-400 p-6 font-mono">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold text-white">AgenC</h1>
          <p className="text-neutral-400 text-sm">Decentralized P2P Agent Bounty Mesh</p>
        </div>

        {/* Node status row */}
        <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
          <p className="text-xs text-neutral-500 uppercase tracking-widest mb-4">Live Swarm</p>
          <div className="flex items-start gap-10">
            {Object.entries(nodes).map(([id, node]) => (
              <NodeCircle key={id} id={id} node={node} />
            ))}
          </div>
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

          {/* Mesh logs */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 flex flex-col h-[420px]">
            <p className="text-xs text-neutral-500 uppercase tracking-widest mb-3">Mesh Network Logs</p>
            <div className="flex-1 overflow-y-auto space-y-1 text-xs">
              {logs.length === 0 && (
                <p className="text-neutral-600 animate-pulse">Waiting for network activity...</p>
              )}
              {logs.map((log, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-neutral-600 shrink-0">[{log.time}]</span>
                  <span className={`shrink-0 w-5 ${tagColor[log.tag] ?? "text-neutral-400"}`}>[{log.tag}]</span>
                  <span className="text-neutral-300 break-all">{log.msg}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>

          {/* Bounties + form */}
          <div className="flex flex-col gap-4">

            {/* Active bounties */}
            {bounties.length > 0 && (
              <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 space-y-3 max-h-56 overflow-y-auto">
                <div className="flex items-center justify-between">
                  <p className="text-xs text-neutral-500 uppercase tracking-widest">Active Bounties</p>
                  <button
                    onClick={async () => {
                      await fetch(`${API}/api/bounties`, { method: "DELETE" });
                      setBounties([]);
                    }}
                    className="text-xs text-neutral-600 hover:text-red-400 transition-colors"
                  >
                    Clear all
                  </button>
                </div>
                {bounties.map(b => (
                  <div key={b.bounty_id} className="border border-neutral-800 rounded p-3 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-neutral-400 text-xs">#{b.bounty_id}</span>
                      <StatusBadge status={b.status} />
                    </div>
                    <p className="text-white text-xs leading-relaxed">
                      {b.task.slice(0, 80)}{b.task.length > 80 ? "…" : ""}
                    </p>
                    {b.winner_specialty && b.status !== "UNCLAIMED" && (
                      <p className="text-xs text-neutral-500">
                        Claimed by: <span className="text-green-400">{b.winner_specialty}</span>
                        {b.worker_id && <span className="text-neutral-600"> ({b.worker_id})</span>}
                      </p>
                    )}
                    {b.result && (
                      <p className="text-xs text-green-300 border-t border-neutral-800 pt-1 mt-1">
                        {b.result.slice(0, 120)}{b.result.length > 120 ? "…" : ""}
                      </p>
                    )}
                    {b.status === "UNCLAIMED" && (
                      <button
                        onClick={() => repostBounty(b)}
                        className="text-xs text-yellow-400 hover:text-yellow-300 underline mt-1"
                      >
                        Repost bounty
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Post bounty form */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
              <p className="text-xs text-neutral-500 uppercase tracking-widest mb-3">Post New Bounty</p>
              <form onSubmit={submitBounty} className="space-y-3">
                <div>
                  <label className="block text-xs text-neutral-400 mb-1">Task Description</label>
                  <textarea
                    className="w-full bg-neutral-950 border border-neutral-700 rounded p-2 text-white text-sm focus:border-green-400 focus:outline-none resize-none"
                    rows={3}
                    value={task}
                    onChange={e => setTask(e.target.value)}
                    placeholder="e.g. Analyze ETH price trends over 5 years vs CPI inflation"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-neutral-400 mb-1">Reward</label>
                  <input
                    type="text"
                    className="w-full bg-neutral-950 border border-neutral-700 rounded p-2 text-white text-sm focus:border-green-400 focus:outline-none"
                    value={reward}
                    onChange={e => setReward(e.target.value)}
                    placeholder="e.g. 50 USDC"
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="w-full bg-green-500 hover:bg-green-400 text-neutral-950 font-bold py-2 px-4 rounded transition-colors text-sm"
                >
                  Broadcast to Mesh
                </button>
              </form>
            </div>

          </div>
        </div>
      </div>
    </main>
  );
}
