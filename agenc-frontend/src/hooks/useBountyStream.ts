"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type RefObject,
  type SetStateAction,
} from "react";
import type { MeshWorkerView } from "@/types/mesh";
import {
  type MeshNodeId,
  type PacketTone,
  resolveWorkerNodeBySpecialty,
} from "@/lib/meshPackets";

export type NodeStatus =
  | "idle"
  | "busy"
  | "evaluating"
  | "claiming"
  | "working"
  | "rejected"
  | "completed";

export interface NodeState {
  status: NodeStatus;
  label: string;
  specialty?: string;
}

export interface BidEntry {
  node_key: string;
  specialty: string;
  outcome: "bid" | "awarded" | "rejected";
}

export interface BountyImage {
  mime: string;
  data_base64: string;
}

export interface BountyCard {
  bounty_id: string;
  task: string;
  reward: string;
  status: "PENDING" | "EXECUTING" | "COLLABORATING" | "COMPLETED" | "UNCLAIMED";
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

export interface LogEntry {
  time: string;
  tag: string;
  msg: string;
}

export interface WorkerInsightBuf {
  toolText: string;
  modelText: string;
  phase: string;
  bountyId?: string;
  specialty?: string;
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

export function useBountyStream(
  apiBase: string,
  spawnTrain: (from: MeshNodeId, to: MeshNodeId, tone: PacketTone) => void,
  setExpandedId: Dispatch<SetStateAction<string | null>>,
  workerKeysRef: MutableRefObject<string[]>,
): {
  bounties: BountyCard[];
  setBounties: Dispatch<SetStateAction<BountyCard[]>>;
  nodes: Record<string, NodeState>;
  setNodes: Dispatch<SetStateAction<Record<string, NodeState>>>;
  logs: LogEntry[];
  meshWorkers: MeshWorkerView[];
  sseConnected: boolean;
  workerInsights: Record<string, WorkerInsightBuf>;
  connectedWorkers: MeshWorkerView[];
  repRefreshTick: number;
  setRepRefreshTick: Dispatch<SetStateAction<number>>;
  logsEndRef: RefObject<HTMLDivElement | null>;
} {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [bounties, setBounties] = useState<BountyCard[]>([]);
  const [nodes, setNodes] = useState<Record<string, NodeState>>({
    emitter: { status: "idle", label: "Emitter" },
    worker_1: { status: "idle", label: "Worker 1", specialty: "Data Analyst" },
    worker_2: { status: "idle", label: "Worker 2", specialty: "Creative Strategist" },
    worker_3: { status: "idle", label: "Worker 3", specialty: "Sentiment Analyst" },
    worker_4: { status: "idle", label: "Worker 4", specialty: "Yield Scout" },
  });
  const [meshWorkers, setMeshWorkers] = useState<MeshWorkerView[]>([]);
  const [workerInsights, setWorkerInsights] = useState<
    Record<string, WorkerInsightBuf>
  >({});
  const [sseConnected, setSseConnected] = useState(false);
  const [repRefreshTick, setRepRefreshTick] = useState(0);

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

  useEffect(() => {
    workerKeysRef.current = connectedWorkers.map((w) => w.node_key);
  }, [connectedWorkers, workerKeysRef]);

  const logsEndRef = useRef<HTMLDivElement>(null);

  const addLog = useCallback((tag: string, msg: string) => {
    setLogs((prev) => [
      ...prev,
      { time: new Date().toLocaleTimeString(), tag, msg },
    ]);
  }, []);

  const setNodeStatus = useCallback((node_id: string, status: NodeStatus) =>
    setNodes((prev) => ({
      ...prev,
      [node_id]: { ...prev[node_id], status },
    })), []);

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
    const params = new URLSearchParams(window.location.search);
    const bid = params.get("bounty");
    if (!bid) return;
    fetch(`${apiBase}/api/bounties/${bid}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: Record<string, unknown> | null) => {
        if (!data || typeof data.task !== "string") return;
        const raw =
          typeof data.status === "string"
            ? data.status
            : "PENDING";
        const status =
          raw === "CLAIMED" ? "EXECUTING" : raw;
        const card: BountyCard = {
          bounty_id: bid,
          task: data.task as string,
          reward: typeof data.reward === "string" ? data.reward : "",
          status: status as BountyCard["status"],
          result: typeof data.result === "string" ? data.result : undefined,
          images: Array.isArray(data.images) ? (data.images as BountyImage[]) : undefined,
          bids: [],
          deposit_tx:
            typeof data.deposit_tx === "string" ? data.deposit_tx : undefined,
          collaboration: Boolean(data.collaboration_mode),
        };
        setBounties((prev) => {
          if (prev.some((b) => b.bounty_id === bid)) return prev;
          return [card, ...prev];
        });
        setExpandedId(bid);
      })
      .catch(() => {});
  }, [apiBase, setExpandedId]);

  useEffect(() => {
    const es = new EventSource(`${apiBase}/api/events`);

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
      if (!refund) setRepRefreshTick((t) => t + 1);
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
      setExpandedId(bounty_id);
      setRepRefreshTick((t) => t + 1);
      const label = collaboration ? `${specialty} (collaborative)` : specialty;
      addLog(
        "done",
        `${label}: ${result.slice(0, 80)}${result.length > 80 ? "…" : ""}`,
      );
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

    es.addEventListener("bounty_images_updated", (e) => {
      const { bounty_id, images } = JSON.parse(e.data) as {
        bounty_id: string;
        images?: BountyImage[];
      };
      if (!images?.length) return;
      setBounties((prev) =>
        prev.map((b) =>
          b.bounty_id === bounty_id ? { ...b, images } : b,
        ),
      );
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
  }, [apiBase, spawnTrain, flashNode, setExpandedId, addLog, setNodeStatus, workerKeysRef]);

  return {
    bounties,
    setBounties,
    nodes,
    setNodes,
    logs,
    meshWorkers,
    sseConnected,
    workerInsights,
    connectedWorkers,
    repRefreshTick,
    setRepRefreshTick,
    logsEndRef,
  };
}
