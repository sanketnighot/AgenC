"use client";
import { useState, useEffect, useRef, useCallback, useMemo } from "react";

import { MeshHub, type MeshWorkerView } from "@/components/MeshHub";
import {
  resolveWorkerNodeBySpecialty,
  routePath,
  schedulePacketTrain,
  type MeshNodeId,
  type MeshPacket,
  type PacketTone,
} from "@/lib/meshPackets";

type NodeStatus =
  | "idle"
  | "busy"
  | "evaluating"
  | "claiming"
  | "working"
  | "rejected"
  | "completed";

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

function StatusBadge({ status }: { status: BountyCard["status"] }) {
  const M: Record<BountyCard["status"], string> = {
    PENDING: "text-amber-400/80 bg-amber-500/8 border-amber-500/15",
    CLAIMED: "text-sky-400/80 bg-sky-500/8 border-sky-500/15",
    EXECUTING: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    COMPLETED: "text-emerald-300 bg-emerald-500/10 border-emerald-500/20",
    UNCLAIMED: "text-zinc-500 bg-zinc-800/40 border-zinc-700/20",
  };
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${M[status]}`}
    >
      {status === "EXECUTING"
        ? "Running"
        : status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}

export default function Home() {
  const [task, setTask] = useState("");
  const [reward, setReward] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [bounties, setBounties] = useState<BountyCard[]>([]);
  const [nodes, setNodes] = useState<Record<string, NodeState>>({
    emitter: { status: "idle", label: "Emitter" },
    worker_1: { status: "idle", label: "Worker 1", specialty: "Data Analyst" },
    worker_2: {
      status: "idle",
      label: "Worker 2",
      specialty: "Creative Strategist",
    },
  });
  const [meshWorkers, setMeshWorkers] = useState<MeshWorkerView[]>([]);
  const [meshPackets, setMeshPackets] = useState<MeshPacket[]>([]);

  const meshWorkersRef = useRef(meshWorkers);
  useEffect(() => {
    meshWorkersRef.current = meshWorkers;
  }, [meshWorkers]);

  const connectedWorkers = useMemo(
    () => meshWorkers.filter((w) => w.mesh_connected),
    [meshWorkers],
  );

  const nodesRef = useRef(nodes);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  const workerKeysRef = useRef<string[]>([]);
  useEffect(() => {
    workerKeysRef.current = connectedWorkers.map((w) => w.node_key);
  }, [connectedWorkers]);

  const logsEndRef = useRef<HTMLDivElement>(null);

  const spawnTrain = useCallback(
    (from: MeshNodeId, to: MeshNodeId, tone: PacketTone) => {
      const steps = routePath(from, to, workerKeysRef.current);
      if (steps.length === 0) return;
      schedulePacketTrain(
        steps,
        tone,
        (p) => setMeshPackets((prev) => [...prev, p]),
        (id) => setMeshPackets((prev) => prev.filter((x) => x.id !== id)),
      );
    },
    [],
  );

  const addLog = (tag: string, msg: string) =>
    setLogs((prev) => [
      ...prev,
      { time: new Date().toLocaleTimeString(), tag, msg },
    ]);

  const setNodeStatus = (node_id: string, status: NodeStatus) =>
    setNodes((prev) => ({
      ...prev,
      [node_id]: { ...prev[node_id], status },
    }));

  const flashNode = useCallback((node_id: string, s: NodeStatus, ms = 2000) => {
    setNodes((prev) => ({ ...prev, [node_id]: { ...prev[node_id], status: s } }));
    setTimeout(() => {
      setNodes((prev) => ({
        ...prev,
        [node_id]: { ...prev[node_id], status: "idle" },
      }));
    }, ms);
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    const es = new EventSource(`${API}/api/events`);

    es.addEventListener("mesh_state", (e) => {
      const data = JSON.parse(e.data) as { workers?: MeshWorkerView[] };
      if (Array.isArray(data.workers)) {
        setMeshWorkers(data.workers);
      }
    });

    es.addEventListener("node_snapshot", (e) => {
      const snap = JSON.parse(e.data) as Record<string, NodeState>;
      setNodes((prev) => {
        const next = { ...prev };
        for (const [id, state] of Object.entries(snap))
          next[id] = { ...prev[id], ...state };
        return next;
      });
    });
    es.addEventListener("node_status", (e) => {
      const { node_id, status } = JSON.parse(e.data);
      setNodeStatus(node_id, status as NodeStatus);
    });
    es.addEventListener("bounty_posted", (e) => {
      const { bounty_id, task: t, reward: rw } = JSON.parse(e.data);
      setBounties((prev) => [
        { bounty_id, task: t, reward: rw ?? "", status: "PENDING" },
        ...prev,
      ]);
      addLog(
        "new",
        `#${bounty_id} — ${t.slice(0, 60)}${t.length > 60 ? "…" : ""}`,
      );
      const keys = workerKeysRef.current;
      keys.forEach((wk) => spawnTrain("emitter", wk, "amber"));
    });
    es.addEventListener("worker_claimed", (e) => {
      const { bounty_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key && nodesRef.current[node_key]) {
        setNodeStatus(node_key, "claiming");
        spawnTrain(node_key, "emitter", "emerald");
      }
      addLog("bid", `${specialty} bid on #${bounty_id}`);
    });
    es.addEventListener("worker_awarded", (e) => {
      const { bounty_id, specialty, node_key, worker_id } = JSON.parse(e.data);
      if (node_key && nodesRef.current[node_key]) {
        setNodeStatus(node_key, "working");
        spawnTrain("emitter", node_key, "emeraldBright");
      }
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id
            ? {
                ...b,
                status: "EXECUTING",
                winner_specialty: specialty,
                worker_id,
              }
            : b,
        ),
      );
      addLog("win", `${specialty} awarded #${bounty_id}`);
    });
    es.addEventListener("worker_rejected", (e) => {
      const { specialty, node_key } = JSON.parse(e.data);
      if (node_key && nodesRef.current[node_key]) {
        flashNode(node_key, "rejected", 2000);
        spawnTrain("emitter", node_key, "red");
      }
      addLog("rej", `${specialty} stood down`);
    });
    es.addEventListener("bounty_completed", (e) => {
      const { bounty_id, result, specialty } = JSON.parse(e.data);
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id
            ? { ...b, status: "COMPLETED", result, winner_specialty: specialty }
            : b,
        ),
      );
      addLog(
        "done",
        `${result.slice(0, 90)}${result.length > 90 ? "…" : ""}`,
      );
      const winner = resolveWorkerNodeBySpecialty(
        specialty,
        nodesRef.current,
        meshWorkersRef.current.length > 0
          ? meshWorkersRef.current.map((w) => w.node_key)
          : Object.keys(nodesRef.current).filter((k) => k !== "emitter"),
      );
      if (
        winner &&
        workerKeysRef.current.includes(winner)
      ) {
        spawnTrain(winner, "emitter", "emeraldDim");
      }
    });
    es.addEventListener("bounty_unclaimed", (e) => {
      const { bounty_id } = JSON.parse(e.data);
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id ? { ...b, status: "UNCLAIMED" } : b,
        ),
      );
      addLog("exp", `#${bounty_id} expired`);
    });

    return () => es.close();
  }, [spawnTrain, flashNode]);

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
    new: "text-amber-500",
    bid: "text-sky-500",
    win: "text-emerald-400",
    rej: "text-red-400/70",
    done: "text-emerald-300",
    exp: "text-zinc-600",
  };

  return (
    <div className="min-h-screen bg-[#080809] text-zinc-100">
      <header className="mx-auto flex h-12 max-w-[1600px] items-center justify-between border-b border-zinc-800/40 px-6">
        <div className="flex items-center gap-2.5">
          <span className="text-sm text-emerald-500">⬡</span>
          <span className="font-display text-sm font-semibold tracking-tight">
            AgenC
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">
            live
          </span>
        </div>
      </header>

      <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-[1600px] flex-col px-4 pb-6 pt-5 lg:px-6">
        <div className="grid flex-1 grid-cols-1 gap-5 lg:grid-cols-[minmax(240px,1fr)_minmax(300px,1.45fr)_minmax(240px,1fr)] lg:items-start">
          {/* Activity */}
          <aside className="flex max-h-[min(72vh,560px)] flex-col overflow-hidden rounded-2xl border border-zinc-800/40 bg-zinc-900/25 lg:sticky lg:top-5">
            <div className="border-b border-zinc-800/40 px-4 py-3">
              <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-500">
                Activity
              </span>
            </div>
            {logs.length === 0 ? (
              <div className="flex flex-1 items-center justify-center py-16">
                <p className="text-xs text-zinc-700">Waiting for events…</p>
              </div>
            ) : (
              <div className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar]:w-1">
                {logs.map((log, i) => (
                  <div
                    key={i}
                    className="group flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-zinc-800/30"
                  >
                    <span
                      className={`w-8 shrink-0 font-mono text-xs ${TAG_COLOR[log.tag] ?? "text-zinc-500"}`}
                    >
                      {log.tag}
                    </span>
                    <p className="min-w-0 flex-1 break-words text-xs leading-relaxed text-zinc-400">
                      {log.msg}
                    </p>
                    <span className="shrink-0 pt-px font-mono text-[10px] text-zinc-700 opacity-0 transition-opacity group-hover:opacity-100">
                      {log.time}
                    </span>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            )}
          </aside>

          {/* Mesh */}
          <section className="min-w-0 lg:min-h-[480px]">
            <MeshHub
              emitter={nodes.emitter}
              workers={connectedWorkers}
              nodes={nodes}
              meshPackets={meshPackets}
            />
          </section>

          {/* Bounties */}
          <aside className="flex max-h-[min(72vh,560px)] flex-col gap-3 lg:sticky lg:top-5">
            {bounties.length > 0 && (
              <div className="flex flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-800/40 bg-zinc-900/25">
                <div className="flex items-center justify-between border-b border-zinc-800/40 px-4 py-3">
                  <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-500">
                    Bounties
                  </span>
                  <button
                    type="button"
                    onClick={async () => {
                      await fetch(`${API}/api/bounties`, { method: "DELETE" });
                      setBounties([]);
                    }}
                    className="text-[10px] text-zinc-700 transition-colors hover:text-red-400"
                  >
                    Clear
                  </button>
                </div>
                <div className="max-h-[min(52vh,420px)] flex-1 divide-y divide-zinc-800/30 overflow-y-auto [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar]:w-1">
                  {bounties.map((b) => (
                    <div key={b.bounty_id} className="space-y-2 px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <p className="min-w-0 flex-1 text-sm leading-snug text-zinc-200">
                          {b.task.slice(0, 100)}
                          {b.task.length > 100 ? "…" : ""}
                        </p>
                        <StatusBadge status={b.status} />
                      </div>
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="font-mono text-[10px] text-zinc-700">
                          #{b.bounty_id}
                        </span>
                        {b.reward && (
                          <span className="text-[10px] text-emerald-600/80">
                            {b.reward}
                          </span>
                        )}
                        {b.winner_specialty && b.status !== "UNCLAIMED" && (
                          <span className="text-[10px] text-zinc-500">
                            {b.winner_specialty}
                          </span>
                        )}
                        {b.status === "UNCLAIMED" && (
                          <button
                            type="button"
                            onClick={() => repostBounty(b)}
                            className="text-[10px] text-amber-500 transition-colors hover:text-amber-400"
                          >
                            ↺ Repost
                          </button>
                        )}
                      </div>
                      {b.result && (
                        <p className="border-t border-zinc-800/40 pt-1 text-xs leading-relaxed text-zinc-500">
                          {b.result.slice(0, 200)}
                          {b.result.length > 200 ? "…" : ""}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {bounties.length === 0 && (
              <div className="rounded-2xl border border-dashed border-zinc-800/50 bg-zinc-900/15 px-4 py-10 text-center">
                <p className="text-xs text-zinc-600">
                  No bounties yet. Post one below.
                </p>
              </div>
            )}
          </aside>
        </div>

        {/* Post bounty */}
        <footer className="mx-auto mt-8 w-full max-w-xl px-1 pb-4 pt-2">
          <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/30 p-5 shadow-[0_-20px_60px_-40px_rgba(16,185,129,0.15)]">
            <p className="mb-3 text-center text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-600">
              Broadcast bounty
            </p>
            <form onSubmit={submitBounty} className="space-y-3">
              <textarea
                className="w-full resize-none rounded-xl border border-zinc-800/60 bg-zinc-950/60 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-700 transition-colors focus:border-zinc-600 focus:outline-none"
                rows={4}
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="Describe the task…"
                required
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  className="flex-1 rounded-xl border border-zinc-800/60 bg-zinc-950/60 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-700 transition-colors focus:border-zinc-600 focus:outline-none"
                  value={reward}
                  onChange={(e) => setReward(e.target.value)}
                  placeholder="Reward (e.g. 50 USDC)"
                  required
                />
                <button
                  type="submit"
                  className="shrink-0 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-zinc-950 transition-colors hover:bg-emerald-400 active:bg-emerald-600"
                >
                  Broadcast
                </button>
              </div>
            </form>
          </div>
        </footer>
      </div>
    </div>
  );
}
