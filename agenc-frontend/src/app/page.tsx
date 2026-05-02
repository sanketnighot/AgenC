"use client";
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useAccount, useConnect, useDisconnect, useBalance, useWriteContract, useWaitForTransactionReceipt, usePublicClient } from "wagmi";
import { injected } from "wagmi/connectors";
import { parseEther, keccak256, toBytes } from "viem";

import { MeshFlowMap } from "@/components/MeshFlowMap";
import type { InsightPayload } from "@/components/WorkerInsightBubble";
import type { MeshWorkerView } from "@/types/mesh";
import {
  resolveWorkerNodeBySpecialty,
  routePath,
  schedulePacketTrain,
  type MeshNodeId,
  type MeshPacket,
  type PacketTone,
} from "@/lib/meshPackets";
import { BOUNTY_ESCROW_ABI } from "@/lib/abi";

const CONTRACT_ADDRESS = (process.env.NEXT_PUBLIC_CONTRACT_ADDRESS ?? "") as `0x${string}`;

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

interface BidEntry {
  node_key: string;
  specialty: string;
  outcome: "bid" | "awarded" | "rejected";
}

interface BountyImage {
  mime: string;
  data_base64: string;
}

interface BountyCard {
  bounty_id: string;
  task: string;
  reward: string;
  status: "PENDING" | "CLAIMED" | "EXECUTING" | "COLLABORATING" | "COMPLETED" | "UNCLAIMED";
  winner_specialty?: string;
  worker_id?: string;
  result?: string;
  images?: BountyImage[];
  collaborating_workers?: string[];
  collaboration?: boolean;
  bids: BidEntry[];
  deposit_tx?: string;
  payment_tx?: string;
}

interface LogEntry {
  time: string;
  tag: string;
  msg: string;
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";


// ── ActivityTimeline ──────────────────────────────────────────────────────────

const TIMELINE_DOT: Record<string, string> = {
  new:     "bg-amber-400",
  bid:     "bg-sky-400",
  win:     "bg-emerald-400",
  rej:     "bg-red-400/70",
  done:    "bg-emerald-300",
  exp:     "bg-zinc-600",
  resolve: "bg-zinc-500",
  arb:     "bg-cyan-400/80",
  collab:  "bg-violet-400",
  p2p:     "bg-violet-300",
};

const TIMELINE_PILL: Record<string, string> = {
  new:     "bg-amber-500/10 text-amber-400 border-amber-500/20",
  bid:     "bg-sky-500/10 text-sky-400 border-sky-500/20",
  win:     "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  rej:     "bg-red-500/10 text-red-400/70 border-red-500/20",
  done:    "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
  exp:     "bg-zinc-800/40 text-zinc-500 border-zinc-700/20",
  resolve: "bg-zinc-800/40 text-zinc-500 border-zinc-700/20",
  arb:     "bg-cyan-500/10 text-cyan-400/80 border-cyan-500/20",
  collab:  "bg-violet-500/10 text-violet-400 border-violet-500/20",
  p2p:     "bg-violet-500/10 text-violet-300 border-violet-500/20",
};

function ActivityTimeline({ logs, logsEndRef }: {
  logs: LogEntry[];
  logsEndRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <aside className="fixed left-4 top-16 bottom-8 z-10 w-72 flex flex-col overflow-hidden rounded-2xl border border-zinc-800/40 backdrop-blur-md bg-zinc-950/70">
      <div className="border-b border-zinc-800/40 px-4 py-2.5 shrink-0">
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-500">
          Activity
        </span>
      </div>

      {logs.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-700" />
            <p className="text-xs text-zinc-700">Awaiting events…</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-3 py-3 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar]:w-1">
          <div className="relative border-l-2 border-zinc-800/60 pl-4 space-y-0">
            {logs.map((log, i) => (
              <div key={i} className="group relative pb-3">
                <span
                  className={`absolute -left-5.25 top-1 h-2.5 w-2.5 rounded-full ring-2 ring-zinc-950 ${TIMELINE_DOT[log.tag] ?? "bg-zinc-600"}`}
                />
                <div className="flex items-start gap-2 flex-wrap">
                  <span
                    className={`shrink-0 rounded-full border px-1.5 py-0.5 font-mono text-[9px] ${TIMELINE_PILL[log.tag] ?? "bg-zinc-800/40 text-zinc-500 border-zinc-700/20"}`}
                  >
                    {log.tag}
                  </span>
                  <p className="min-w-0 flex-1 text-xs leading-relaxed text-zinc-300 line-clamp-2">
                    {log.msg}
                  </p>
                </div>
                <span className="mt-0.5 block font-mono text-[10px] text-zinc-700 opacity-0 transition-opacity group-hover:opacity-100">
                  {log.time}
                </span>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}
    </aside>
  );
}

// ── AuctionBountyCard + AuctionBountyRail ─────────────────────────────────────

const STAMP_STYLE: Record<BountyCard["status"], string> = {
  PENDING:       "border-amber-500/40 text-amber-400/80 bg-amber-500/5",
  CLAIMED:       "border-sky-500/40 text-sky-400/80 bg-sky-500/5",
  EXECUTING:     "border-emerald-500/40 text-emerald-400 bg-emerald-500/5",
  COLLABORATING: "border-violet-500/40 text-violet-400/80 bg-violet-500/5",
  COMPLETED:     "border-emerald-400/60 text-emerald-300 bg-emerald-500/8",
  UNCLAIMED:     "border-zinc-600/40 text-zinc-500 bg-zinc-800/20",
};

const GLYPH_LIST = ["◈", "◇", "▣", "◆", "⬢"];

function AuctionBountyCard({
  b,
  expanded,
  onToggle,
  onRepost,
}: {
  b: BountyCard;
  expanded: boolean;
  onToggle: () => void;
  onRepost: (b: BountyCard) => void;
}) {
  const bidSummary =
    b.bids.length === 0
      ? "No bids yet"
      : `${b.bids.length} bid${b.bids.length === 1 ? "" : "s"}`;

  return (
    <div className="group border-b border-zinc-800/30 last:border-0 transition-colors hover:bg-zinc-800/10">
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-4 py-3 text-left"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <span className="font-mono text-[10px] text-zinc-600">#{b.bounty_id}</span>
            {b.reward && (
              <span className="text-[10px] text-emerald-500/80">{b.reward}</span>
            )}
            <span className="text-[10px] text-zinc-600">{bidSummary}</span>
            {b.deposit_tx && (
              <a
                href={`https://sepolia.basescan.org/tx/${b.deposit_tx}`}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="font-mono text-[9px] text-sky-500/70 hover:text-sky-400 underline"
              >
                ↗ deposit
              </a>
            )}
            {b.payment_tx && (
              <a
                href={b.payment_tx}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="font-mono text-[9px] text-emerald-500/70 hover:text-emerald-400 underline"
              >
                ↗ paid
              </a>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span
              className={`rotate-[-8deg] rounded border-2 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${STAMP_STYLE[b.status]}`}
            >
              {b.status}
            </span>
            <span className="text-zinc-600 text-[10px]">{expanded ? "▼" : "▶"}</span>
          </div>
        </div>

        <p
          className={`mt-2 text-sm text-zinc-200 leading-snug ${
            expanded ? "" : "line-clamp-2"
          }`}
        >
          {b.task}
        </p>
      </button>

      {expanded && (
        <div className="space-y-2 px-4 pb-3">
          {b.bids.length > 0 && (
            <div>
              <p className="text-[9px] uppercase tracking-[0.18em] text-zinc-600 mb-1">Bids</p>
              <div className="space-y-0.5">
                {b.bids.map((bid, i) => (
                  <div key={bid.node_key} className="flex items-center justify-between">
                    <span
                      className={`flex items-center gap-1.5 text-xs ${bid.outcome === "rejected" ? "line-through text-zinc-600" : "text-zinc-300"}`}
                    >
                      <span className="text-zinc-500">{GLYPH_LIST[i % GLYPH_LIST.length]}</span>
                      {bid.specialty}
                    </span>
                    <span
                      className={`font-mono text-[9px] ${
                        bid.outcome === "awarded"
                          ? "text-emerald-400"
                          : bid.outcome === "rejected"
                          ? "text-zinc-600"
                          : "text-sky-400/70"
                      }`}
                    >
                      {bid.outcome === "awarded"
                        ? "awarded"
                        : bid.outcome === "rejected"
                        ? "stood down"
                        : "bid"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(b.result || (b.images && b.images.length > 0)) && (
            <div className="bg-zinc-950/60 rounded-xl border border-zinc-800/40 p-2.5 space-y-1.5">
              {b.collaboration && (
                <span className="inline-flex items-center gap-1 rounded-full border border-violet-500/20 bg-violet-500/8 px-2 py-0.5 text-[9px] font-medium text-violet-400/80">
                  ⬡ collaborative result
                </span>
              )}
              {b.images && b.images.length > 0 && (
                <div className="flex flex-col gap-2">
                  {b.images.map((img, idx) => (
                    // eslint-disable-next-line @next/next/no-img-element -- data URLs from worker
                    <img
                      key={idx}
                      src={`data:${img.mime};base64,${img.data_base64}`}
                      alt=""
                      className="max-h-72 w-full rounded-lg border border-zinc-700/50 object-contain bg-zinc-900/40"
                    />
                  ))}
                </div>
              )}
              {b.result && (
                <p className="text-xs leading-relaxed text-zinc-400 whitespace-pre-wrap">{b.result}</p>
              )}
            </div>
          )}

          {b.status === "UNCLAIMED" && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRepost(b);
              }}
              className="text-[10px] text-amber-500 transition-colors hover:text-amber-400"
            >
              ↺ Repost
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function AuctionBountyRail({
  bounties,
  onRepost,
  onClear,
}: {
  bounties: BountyCard[];
  onRepost: (b: BountyCard) => void;
  onClear: () => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <aside className="fixed right-4 top-16 bottom-8 z-10 w-80 flex flex-col overflow-hidden rounded-2xl border border-zinc-800/40 backdrop-blur-md bg-zinc-950/70">
      <div className="flex items-center justify-between border-b border-zinc-800/40 px-4 py-2.5 shrink-0">
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-500">
          Bounties
        </span>
        {bounties.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="text-[10px] text-zinc-700 transition-colors hover:text-red-400"
          >
            Clear
          </button>
        )}
      </div>

      {bounties.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-4">
          <p className="text-xs text-zinc-600 text-center">No bounties yet. Post one below.</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar]:w-1">
          {bounties.map((b) => (
            <AuctionBountyCard
              key={b.bounty_id}
              b={b}
              expanded={expandedId === b.bounty_id}
              onToggle={() =>
                setExpandedId((id) => (id === b.bounty_id ? null : b.bounty_id))
              }
              onRepost={onRepost}
            />
          ))}
        </div>
      )}
    </aside>
  );
}

const INSIGHT_MODEL_CAP = 24000;
const INSIGHT_TOOL_CAP = 8000;

function capInsightTail(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(-max);
}

/** Reset tool/model buffers when SSE carries a different bounty_id for this worker. */
function shouldResetInsightForBounty(
  prevBountyId: string | undefined,
  incomingBountyId: string | null | undefined,
): boolean {
  if (incomingBountyId == null || incomingBountyId === "") return false;
  if (prevBountyId == null || prevBountyId === "") return false;
  return incomingBountyId !== prevBountyId;
}

interface WorkerInsightBuf {
  toolText: string;
  modelText: string;
  phase: string;
  bountyId?: string;
  specialty?: string;
}

// ── Home ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const [task, setTask] = useState("");
  const [rewardEth, setRewardEth] = useState("0.01");
  const [submitting, setSubmitting] = useState(false);

  // ── Wallet ────────────────────────────────────────────────────────────────
  const { address, isConnected } = useAccount();
  const { connect, error: connectError } = useConnect();
  const { disconnect } = useDisconnect();
  const { data: balance } = useBalance({ address });
  const { writeContractAsync } = useWriteContract();
  const publicClient = usePublicClient();
  const [pendingTxHash, setPendingTxHash] = useState<`0x${string}` | undefined>();
  const { isLoading: isTxConfirming } = useWaitForTransactionReceipt({ hash: pendingTxHash });
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
  const [workerInsights, setWorkerInsights] = useState<
    Record<string, WorkerInsightBuf>
  >({});
  const [selectedInsightWorker, setSelectedInsightWorker] = useState<
    string | null
  >(null);
  const [telemetryEnabled, setTelemetryEnabled] = useState<boolean | null>(null);
  const [sseConnected, setSseConnected] = useState(false);

  const panelInsight: InsightPayload | null = useMemo(() => {
    if (!selectedInsightWorker) return null;
    const x = workerInsights[selectedInsightWorker];
    return {
      toolText: x?.toolText ?? "",
      modelText: x?.modelText ?? "",
      phase: x?.phase ?? "idle",
      bountyId: x?.bountyId,
      specialty: x?.specialty,
    };
  }, [selectedInsightWorker, workerInsights]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/api/telemetry/status`)
      .then((r) => r.json())
      .then((body: { enabled?: boolean }) => {
        if (!cancelled) setTelemetryEnabled(Boolean(body.enabled));
      })
      .catch(() => {
        if (!cancelled) setTelemetryEnabled(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  const addLog = (tag: string, msg: string) => {
    setLogs((prev) => [
      ...prev,
      { time: new Date().toLocaleTimeString(), tag, msg },
    ]);
  };

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

    es.onopen = () => setSseConnected(true);
    es.onerror = () => setSseConnected(false);

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
    es.addEventListener("worker_llm_delta", (e) => {
      const d = JSON.parse(e.data) as {
        node_key: string;
        phase: string;
        bounty_id?: string | null;
        delta: string;
        specialty?: string;
      };
      const k = d.node_key;
      setWorkerInsights((prev) => {
        const cur = prev[k] ?? {
          toolText: "",
          modelText: "",
          phase: "idle",
          specialty: d.specialty,
        };
        const reset = shouldResetInsightForBounty(
          cur.bountyId,
          d.bounty_id,
        );
        let toolText = reset ? "" : cur.toolText;
        let modelText = reset ? "" : cur.modelText;
        const bountyId = reset
          ? (d.bounty_id ?? undefined)
          : (d.bounty_id ?? cur.bountyId);
        const chunk = d.delta || "";
        if (d.phase === "tool") {
          toolText = capInsightTail(toolText + chunk, INSIGHT_TOOL_CAP);
        } else {
          modelText = capInsightTail(modelText + chunk, INSIGHT_MODEL_CAP);
        }
        return {
          ...prev,
          [k]: {
            toolText,
            modelText,
            phase: d.phase,
            bountyId,
            specialty: d.specialty ?? cur.specialty,
          },
        };
      });
    });
    es.addEventListener("worker_phase", (e) => {
      const d = JSON.parse(e.data) as {
        node_key: string;
        phase: string;
        bounty_id?: string | null;
      };
      const k = d.node_key;
      setWorkerInsights((prev) => {
        const cur = prev[k] ?? {
          toolText: "",
          modelText: "",
          phase: "idle",
        };
        const reset = shouldResetInsightForBounty(cur.bountyId, d.bounty_id);
        return {
          ...prev,
          [k]: {
            ...cur,
            toolText: reset ? "" : cur.toolText,
            modelText: reset ? "" : cur.modelText,
            phase: d.phase,
            bountyId: reset
              ? (d.bounty_id ?? undefined)
              : (d.bounty_id ?? cur.bountyId),
          },
        };
      });
    });
    es.addEventListener("bounty_resolving", (e) => {
      const { bounty_id } = JSON.parse(e.data);
      addLog("resolve", `Claim window closed — resolving #${bounty_id}`);
    });
    es.addEventListener("arbiter_result", (e) => {
      const { bounty_id, winner_node_key, reason, source } = JSON.parse(e.data);
      addLog(
        "arb",
        `#${bounty_id} → ${winner_node_key} (${source}) ${(reason || "").slice(0, 100)}`,
      );
    });
    es.addEventListener("bounty_posted", (e) => {
      const { bounty_id, task: t, reward: rw, deposit_tx } = JSON.parse(e.data);
      setBounties((prev) => [
        { bounty_id, task: t, reward: rw ?? "", status: "PENDING", bids: [], deposit_tx: deposit_tx || undefined },
        ...prev,
      ]);
      addLog(
        "new",
        `#${bounty_id} — ${t.slice(0, 60)}${t.length > 60 ? "…" : ""}`,
      );
      const keys = workerKeysRef.current;
      keys.forEach((wk) => spawnTrain("emitter", wk, "amber"));
    });
    es.addEventListener("payment_tx", (e) => {
      const { bounty_id, tx_url, refund } = JSON.parse(e.data) as {
        bounty_id: string;
        tx_url: string;
        refund?: boolean;
      };
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id ? { ...b, payment_tx: tx_url } : b,
        ),
      );
      addLog(refund ? "exp" : "done", `⛓ ${refund ? "Refund" : "Payment"} TX: ${tx_url.slice(-16)}…`);
    });
    es.addEventListener("worker_claimed", (e) => {
      const { bounty_id, specialty, node_key } = JSON.parse(e.data);
      if (node_key && nodesRef.current[node_key]) {
        setNodeStatus(node_key, "claiming");
        spawnTrain(node_key, "emitter", "emerald");
      }
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id
            ? {
                ...b,
                bids: [
                  ...b.bids.filter((bd) => bd.node_key !== node_key),
                  { node_key, specialty, outcome: "bid" as const },
                ],
              }
            : b,
        ),
      );
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
                bids: b.bids.map((bd) =>
                  bd.node_key === node_key ? { ...bd, outcome: "awarded" as const } : bd,
                ),
              }
            : b,
        ),
      );
      addLog("win", `${specialty} awarded #${bounty_id}`);
    });
    es.addEventListener("worker_rejected", (e) => {
      const { specialty, node_key, bounty_id } = JSON.parse(e.data);
      if (node_key && nodesRef.current[node_key]) {
        flashNode(node_key, "rejected", 2000);
        spawnTrain("emitter", node_key, "red");
      }
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id
            ? {
                ...b,
                bids: b.bids.map((bd) =>
                  bd.node_key === node_key ? { ...bd, outcome: "rejected" as const } : bd,
                ),
              }
            : b,
        ),
      );
      addLog("rej", `${specialty} stood down`);
    });
    es.addEventListener("bounty_collaborating", (e) => {
      const { bounty_id, workers } = JSON.parse(e.data) as {
        bounty_id: string;
        workers: { node_key: string; specialty: string; is_lead: boolean }[];
      };
      workers.forEach(({ node_key }) => {
        if (nodesRef.current[node_key]) setNodeStatus(node_key, "working");
      });
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id
            ? {
                ...b,
                status: "COLLABORATING",
                collaborating_workers: workers.map((w) => w.node_key),
                winner_specialty: workers.map((w) => w.specialty).join(" + "),
              }
            : b,
        ),
      );
      const specialties = workers.map((w) => w.specialty).join(" & ");
      addLog("collab", `${specialties} collaborating on #${bounty_id}`);
    });

    es.addEventListener("worker_direct_message", (e) => {
      const { from_node_key, to_node_key } = JSON.parse(e.data) as {
        bounty_id: string;
        from_node_key: string;
        to_node_key: string;
        msg_type: string;
      };
      spawnTrain(from_node_key, to_node_key, "violet");
      const fromLabel = nodesRef.current[from_node_key]?.label ?? from_node_key;
      const toLabel   = nodesRef.current[to_node_key]?.label   ?? to_node_key;
      addLog("p2p", `Direct: ${fromLabel} → ${toLabel}`);
    });

    es.addEventListener("bounty_completed", (e) => {
      const {
        bounty_id,
        result,
        specialty,
        collaboration,
        node_key: completingNodeKey,
        images,
      } = JSON.parse(e.data) as {
        bounty_id: string;
        result: string;
        specialty: string;
        collaboration?: boolean;
        node_key?: string;
        images?: BountyImage[];
      };
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id
            ? {
                ...b,
                status: "COMPLETED",
                result,
                images: images && images.length ? images : undefined,
                winner_specialty: specialty,
                collaboration,
              }
            : b,
        ),
      );
      const label = collaboration ? `${specialty} (collaborative)` : specialty;
      addLog(
        "done",
        `${label}: ${result.slice(0, 80)}${result.length > 80 ? "…" : ""}`,
      );
      // Bridge now sends node_key directly; fall back to specialty lookup for non-collab
      if (completingNodeKey && workerKeysRef.current.includes(completingNodeKey)) {
        spawnTrain(completingNodeKey, "emitter", "emeraldDim");
      } else if (!collaboration) {
        const allWorkerKeys = meshWorkersRef.current.length > 0
          ? meshWorkersRef.current.map((w) => w.node_key)
          : Object.keys(nodesRef.current).filter((k) => k !== "emitter");
        const winner = resolveWorkerNodeBySpecialty(specialty, nodesRef.current, allWorkerKeys);
        if (winner && workerKeysRef.current.includes(winner)) {
          spawnTrain(winner, "emitter", "emeraldDim");
        }
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

  const submitBounty = async (e: React.FormEvent, overrideTask?: string, overrideRewardEth?: string) => {
    e.preventDefault();
    const t = overrideTask ?? task;
    const ethAmount = overrideRewardEth ?? rewardEth;
    if (!t.trim() || !isConnected || !address) return;
    setSubmitting(true);
    try {
      const bountyId = crypto.randomUUID().replace(/-/g, "").slice(0, 8);
      const bountyIdBytes32 = keccak256(toBytes(bountyId));
      const rewardWei = parseEther(ethAmount || "0");

      // Step 1: send escrow deposit — MetaMask will pop up
      const hash = await writeContractAsync({
        address: CONTRACT_ADDRESS,
        abi: BOUNTY_ESCROW_ABI,
        functionName: "postBounty",
        args: [bountyIdBytes32],
        value: rewardWei,
      });
      setPendingTxHash(hash);

      // Step 2: wait for on-chain confirmation before notifying the backend
      if (publicClient) {
        await publicClient.waitForTransactionReceipt({ hash, confirmations: 1 });
      }

      // Step 3: notify backend — bounty is now funded on-chain
      await fetch(`${API}/api/bounty`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task: t,
          reward: `${ethAmount} ETH`,
          reward_wei: Number(rewardWei),
          tx_hash: hash,
          poster_address: address,
          bounty_id: bountyId,
        }),
      });
      if (!overrideTask) setTask("");
    } catch (err) {
      console.error("submitBounty error:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const repostBounty = (b: BountyCard) =>
    submitBounty({ preventDefault: () => {} } as React.FormEvent, b.task, rewardEth);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#080809] text-zinc-100">
      {/* Layer 0: Full-screen mesh canvas */}
      <MeshFlowMap
        emitter={nodes.emitter}
        workers={connectedWorkers}
        agentStates={nodes}
        meshPackets={meshPackets}
        selectedWorkerKey={selectedInsightWorker}
        onWorkerSelect={setSelectedInsightWorker}
        insight={panelInsight}
        telemetryEnabled={telemetryEnabled}
        sseConnected={sseConnected}
      />

      {/* Layer z-10: Header */}
      <header className="fixed top-0 left-0 right-0 z-10 flex h-12 items-center justify-between border-b border-zinc-800/40 px-6 backdrop-blur-md bg-zinc-950/60">
        <div className="flex items-center gap-2.5">
          <span className="text-sm text-emerald-500">⬡</span>
          <span className="font-display text-sm font-semibold tracking-tight">AgenC</span>
        </div>
        <div className="flex items-center gap-3">
          {isConnected && address ? (
            <button
              type="button"
              onClick={() => disconnect()}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-800/60 bg-zinc-900/80 px-3 py-1 text-[10px] font-mono text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              {address.slice(0, 6)}…{address.slice(-4)}
              {balance && (
                <span className="text-zinc-500">· {parseFloat(balance.formatted).toFixed(4)} ETH</span>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => connect({ connector: injected() })}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-700/60 bg-zinc-900/80 px-3 py-1 text-[10px] font-mono text-zinc-400 transition-colors hover:border-emerald-500/40 hover:text-emerald-400"
              title={connectError?.message}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-zinc-600" />
              {connectError ? "⚠ " + connectError.message.slice(0, 30) : "Connect Wallet"}
            </button>
          )}
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
            <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">live</span>
          </div>
        </div>
      </header>

      {/* Layer z-10: Activity timeline (left) */}
      <ActivityTimeline logs={logs} logsEndRef={logsEndRef} />

      {/* Layer z-10: Bounty rail (right) */}
      <AuctionBountyRail
        bounties={bounties}
        onRepost={repostBounty}
        onClear={async () => {
          await fetch(`${API}/api/bounties`, { method: "DELETE" });
          setBounties([]);
        }}
      />

      {/* Layer z-30: Broadcast form */}
      <div className="fixed bottom-10 left-1/2 z-30 w-[520px] -translate-x-1/2">
        <div className="rounded-2xl border border-zinc-800/50 backdrop-blur-md bg-zinc-950/80 p-4 shadow-[0_-20px_60px_-40px_rgba(16,185,129,0.15)]">
          <p className="mb-3 text-center text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-600">
            Broadcast bounty
          </p>
          <form onSubmit={submitBounty} className="space-y-3">
            <textarea
              className="w-full resize-none rounded-xl border border-zinc-800/60 bg-zinc-950/60 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-700 transition-colors focus:border-zinc-600 focus:outline-none"
              rows={3}
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Describe the task…"
              required
            />
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type="number"
                  step="0.001"
                  min="0.001"
                  className="w-full rounded-xl border border-zinc-800/60 bg-zinc-950/60 px-4 py-2.5 pr-14 text-sm text-zinc-100 placeholder-zinc-700 transition-colors focus:border-zinc-600 focus:outline-none"
                  value={rewardEth}
                  onChange={(e) => setRewardEth(e.target.value)}
                  placeholder="0.01"
                  required
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] text-zinc-500">
                  ETH
                </span>
              </div>
              <button
                type="submit"
                disabled={submitting || isTxConfirming || !isConnected}
                className="shrink-0 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-zinc-950 transition-colors hover:bg-emerald-400 active:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? "Sending…" : isTxConfirming ? "Confirming…" : "⛓ Broadcast"}
              </button>
            </div>
            {!isConnected && (
              <p className="text-center text-[10px] text-amber-600/80">
                Connect your wallet first to post a bounty
              </p>
            )}
          </form>
        </div>
      </div>

    </div>
  );
}
