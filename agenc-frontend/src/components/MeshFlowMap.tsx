"use client";

import "@xyflow/react/dist/style.css";

import type { MouseEvent } from "react";
import { useCallback, useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  useStore,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";

import type { MeshPacket } from "@/lib/meshPackets";
import { WorkerInsightBubble, type InsightPayload } from "@/components/WorkerInsightBubble";

import type { MeshWorkerView } from "@/types/mesh";

type NodeStatus =
  | "idle"
  | "busy"
  | "evaluating"
  | "claiming"
  | "working"
  | "rejected"
  | "completed";

interface AgentNodeState {
  status: NodeStatus;
  label: string;
  specialty?: string;
}

type EmitterFlowData = { label: string; workerCount: number };
type EmitterRFNode = Node<EmitterFlowData, "emitter">;

type WorkerFlowData = {
  worker: MeshWorkerView;
  agent: AgentNodeState;
  angleRad: number;
  glyphIndex: number;
};
type WorkerRFNode = Node<WorkerFlowData, "worker">;

const EMITTER_ID = "emitter";
/** Horizontal layout: emitter top-center, workers in a row below (stays above broadcast panel). */
const EMITTER_CENTER_X = 420;
const EMITTER_TOP_Y = 72;
const WORKER_ROW_Y = 252;
const WORKER_GAP = 300;

const STATUS_RING: Record<
  NodeStatus,
  { ring: string; glow?: string; ping?: string }
> = {
  idle: { ring: "ring-zinc-800" },
  busy: {
    ring: "ring-amber-400/60",
    ping: "bg-amber-400/30",
    glow: "0 0 20px rgba(251,191,36,0.2)",
  },
  evaluating: { ring: "ring-zinc-500/60" },
  claiming: {
    ring: "ring-emerald-400/60",
    ping: "bg-emerald-400/25",
    glow: "0 0 20px rgba(52,211,153,0.2)",
  },
  working: {
    ring: "ring-emerald-400/80",
    ping: "bg-emerald-400/30",
    glow: "0 0 28px rgba(52,211,153,0.3)",
  },
  rejected: { ring: "ring-red-500/60" },
  completed: { ring: "ring-emerald-300/60" },
};

const STATUS_DOT: Record<NodeStatus, string> = {
  idle: "bg-zinc-700",
  busy: "bg-amber-400",
  evaluating: "bg-zinc-400",
  claiming: "bg-emerald-400",
  working: "bg-emerald-400",
  rejected: "bg-red-400",
  completed: "bg-emerald-300",
};

const GLYPHS = ["◈", "◇", "▣", "◆", "⬢"];

function EmitterFlowNode({ data }: NodeProps<EmitterRFNode>) {
  const n = Math.max(0, data.workerCount);
  return (
    <div className="relative flex h-[128px] w-[128px] flex-col items-center justify-center rounded-full border border-zinc-800/60 bg-zinc-950/95 shadow-[0_0_40px_-12px_rgba(16,185,129,0.25)]">
      {Array.from({ length: n }).map((_, i) => {
        const a = (-Math.PI / 2) + (2 * Math.PI * i) / Math.max(n, 1);
        const hx = 50 + 42 * Math.cos(a);
        const hy = 50 + 42 * Math.sin(a);
        return (
          <Handle
            key={i}
            id={`out-${i}`}
            type="source"
            position={Position.Top}
            style={{
              left: `${hx}%`,
              top: `${hy}%`,
              transform: "translate(-50%, -50%)",
              width: 10,
              height: 10,
              borderRadius: "9999px",
              background: "#3f3f46",
              border: "2px solid #52525b",
            }}
          />
        );
      })}
      <div className="pointer-events-none flex flex-col items-center gap-1 text-center">
        <span className="text-2xl leading-none text-zinc-100 select-none">⬡</span>
        <span className="text-[11px] font-medium tracking-tight text-zinc-300">
          {data.label}
        </span>
      </div>
    </div>
  );
}

function WorkerFlowNode({ data }: NodeProps<WorkerRFNode>) {
  const { ring, glow, ping } = STATUS_RING[data.agent.status];
  const a = data.angleRad;
  const hx = 50 - 44 * Math.cos(a);
  const hy = 50 - 44 * Math.sin(a);
  const g = GLYPHS[data.glyphIndex % GLYPHS.length];

  return (
    <div className="relative flex min-w-[120px] flex-col items-center rounded-2xl border border-zinc-800/60 bg-zinc-950/95 px-2 py-3 shadow-[0_12px_40px_-20px_rgba(0,0,0,0.8)]">
      <Handle
        id="in"
        type="target"
        position={Position.Top}
        style={{
          left: `${hx}%`,
          top: `${hy}%`,
          transform: "translate(-50%, -50%)",
          width: 10,
          height: 10,
          borderRadius: "9999px",
          background: "#3f3f46",
          border: "2px solid #52525b",
        }}
      />
      <div className="relative mb-1 h-12 w-12">
        {ping && (
          <span
            className={`absolute inset-0 rounded-full ${ping} animate-ping`}
          />
        )}
        <div
          className={`flex h-12 w-12 items-center justify-center rounded-full bg-zinc-900 ring-2 transition-all duration-500 ${ring}`}
          style={glow ? { boxShadow: glow } : undefined}
        >
          <span className="select-none text-lg text-zinc-100">{g}</span>
        </div>
      </div>
      <p className="max-w-[112px] text-center text-[11px] font-medium text-zinc-200">
        {data.agent.label}
      </p>
      {data.agent.specialty && (
        <p className="mt-0.5 max-w-[112px] text-center text-[9px] text-zinc-600">
          {data.agent.specialty}
        </p>
      )}
      <p className="mt-1 font-mono text-[8px] tracking-tight text-zinc-500">
        {data.worker.short_id}…
      </p>
      <div className="mt-1 flex items-center gap-1">
        {data.worker.mesh_connected ? (
          <>
            <span className={`h-1 w-1 rounded-full ${STATUS_DOT[data.agent.status]}`} />
            <span className="text-[8px] font-mono uppercase tracking-wider text-emerald-500/90">live</span>
          </>
        ) : (
          <>
            <span className="h-1 w-1 rounded-full bg-zinc-700" />
            <span className="text-[8px] font-mono uppercase tracking-wider text-zinc-600">offline</span>
          </>
        )}
      </div>
    </div>
  );
}

const nodeTypes = {
  emitter: EmitterFlowNode,
  worker: WorkerFlowNode,
};

function buildNodes(
  emitterLabel: string,
  workers: MeshWorkerView[],
  agentStates: Record<string, AgentNodeState>,
): Node[] {
  const n = workers.length;
  const ew = 128;
  const eh = 128;
  const emCx = EMITTER_CENTER_X;
  const emCy = EMITTER_TOP_Y + eh / 2;

  const list: Node[] = [
    {
      id: EMITTER_ID,
      type: "emitter",
      position: { x: EMITTER_CENTER_X - ew / 2, y: EMITTER_TOP_Y },
      data: { label: emitterLabel, workerCount: n },
      draggable: true,
    },
  ];

  const nw = 128;
  const nh = 148;

  workers.forEach((w, i) => {
    const cxCenter =
      EMITTER_CENTER_X + (i - (n - 1) / 2) * WORKER_GAP;
    const left = cxCenter - nw / 2;
    const wx = cxCenter;
    const wy = WORKER_ROW_Y + nh / 2;
    const angle = Math.atan2(emCy - wy, emCx - wx);
    const agent =
      agentStates[w.node_key] ??
      ({
        status: "idle" as const,
        label: w.label,
        specialty: w.specialty,
      } satisfies AgentNodeState);

    list.push({
      id: w.node_key,
      type: "worker",
      position: { x: left, y: WORKER_ROW_Y },
      data: {
        worker: w,
        agent,
        angleRad: angle,
        glyphIndex: i,
      },
      draggable: true,
    });
  });

  return list;
}

const TONE_COLOR: Record<string, string> = {
  amber:        "#fbbf24",
  emerald:      "#34d399",
  emeraldBright:"#6ee7b7",
  emeraldDim:   "#065f46",
  red:          "#f87171",
  violet:       "#a78bfa",
};

function buildEdges(workers: MeshWorkerView[], meshPackets: MeshPacket[]): Edge[] {
  // Map spoke index → tone so each edge can carry its own color
  const activeMap = new Map<number, string>();
  meshPackets.forEach((p) => activeMap.set(p.spokeIndex, p.tone));

  return workers.map((w, i) => {
    const tone = activeMap.get(i);
    const color = tone ? (TONE_COLOR[tone] ?? "#34d399") : "#3f3f46";
    const isActive = Boolean(tone);
    return {
      id: `e-${w.node_key}`,
      source: EMITTER_ID,
      sourceHandle: `out-${i}`,
      target: w.node_key,
      targetHandle: "in",
      type: "smoothstep",
      animated: true,
      style: {
        stroke: color,
        strokeWidth: isActive ? 2.75 : 1.35,
      },
      className: isActive
        ? `mesh-edge-active drop-shadow-[0_0_8px_${color}66]`
        : "",
    };
  });
}

function FlowInner({
  emitterLabel,
  workers,
  agentStates,
  meshPackets,
  selectedWorkerKey,
  onWorkerSelect,
  insight,
  telemetryEnabled,
  sseConnected,
}: {
  emitterLabel: string;
  workers: MeshWorkerView[];
  agentStates: Record<string, AgentNodeState>;
  meshPackets: MeshPacket[];
  selectedWorkerKey: string | null;
  onWorkerSelect: (nodeKey: string | null) => void;
  insight: InsightPayload | null;
  telemetryEnabled: boolean | null;
  sseConnected: boolean;
}) {
  const { fitView, flowToScreenPosition, getNode } = useReactFlow();
  useStore((s) => s.transform);

  const initialNodes = useMemo(
    () => buildNodes(emitterLabel, workers, agentStates),
    [emitterLabel, workers, agentStates],
  );
  const initialEdges = useMemo(
    () => buildEdges(workers, meshPackets),
    [workers, meshPackets],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const anchor = useMemo(() => {
    if (!selectedWorkerKey) return null;
    const nd = getNode(selectedWorkerKey);
    if (!nd || nd.type !== "worker") return null;
    const nw = 128;
    return flowToScreenPosition({
      x: nd.position.x + nw / 2,
      y: nd.position.y,
    });
  }, [selectedWorkerKey, getNode, flowToScreenPosition, nodes]);

  const workerIdsKey = workers.map((w) => w.node_key).join("|");

  useEffect(() => {
    setNodes((curr) => {
      const built = buildNodes(emitterLabel, workers, agentStates);
      const posById = new Map(curr.map((node) => [node.id, node.position]));
      return built.map((node) => ({
        ...node,
        position: posById.get(node.id) ?? node.position,
      }));
    });
  }, [emitterLabel, workerIdsKey, workers, agentStates, setNodes]);

  useEffect(() => {
    setEdges(buildEdges(workers, meshPackets));
  }, [workers, meshPackets, setEdges]);

  useEffect(() => {
    const t = requestAnimationFrame(() => {
      fitView({ padding: 0.28, duration: 280, maxZoom: 1.15 });
    });
    return () => cancelAnimationFrame(t);
  }, [workerIdsKey, fitView]);

  const onInit = useCallback(() => {
    fitView({ padding: 0.28, maxZoom: 1.15 });
  }, [fitView]);

  const onNodeClick = useCallback(
    (_event: MouseEvent, node: Node) => {
      if (node.type === "worker") {
        onWorkerSelect(selectedWorkerKey === node.id ? null : node.id);
      }
    },
    [onWorkerSelect, selectedWorkerKey],
  );

  const onPaneClick = useCallback(() => {
    onWorkerSelect(null);
  }, [onWorkerSelect]);

  const selectedWorker = workers.find((w) => w.node_key === selectedWorkerKey);
  const selectedAgent =
    selectedWorkerKey && agentStates[selectedWorkerKey]
      ? agentStates[selectedWorkerKey]
      : null;

  const n = workers.length;

  return (
    <div className="fixed inset-0 z-0 bg-[#060607]">
      <div className="absolute inset-0 opacity-[0.4] bg-[radial-gradient(ellipse_at_50%_35%,rgba(16,185,129,0.06),transparent_60%),repeating-linear-gradient(-18deg,transparent,transparent_31px,rgba(63,63,70,0.05)_31px,rgba(63,63,70,0.05)_32px)]" />

      <div className="absolute inset-0">
        {n === 0 ? (
          <div className="flex h-full items-center justify-center px-6">
            <p className="max-w-[280px] text-center text-xs leading-relaxed text-zinc-600">
              No peers connected. Start worker nodes — they appear here with live edges.
            </p>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            onInit={onInit}
            fitView
            colorMode="dark"
            minZoom={0.35}
            maxZoom={1.35}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            panOnScroll
            zoomOnScroll
            zoomOnPinch
            panOnDrag
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            defaultEdgeOptions={{ type: "smoothstep" }}
            className="!bg-transparent [&_.react-flow__edge-path]:!stroke-linecap-round [&_.react-flow__attribution]:hidden!"
          >
            <Background
              id="mesh-bg"
              gap={20}
              size={1.2}
              color="#27272a"
              className="opacity-[0.65]"
            />
            <Controls
              className="!m-2 !overflow-hidden !rounded-xl !border !border-zinc-800/80 !bg-zinc-950/95 !shadow-xl [&_button]:!h-7 [&_button]:!w-7 [&_button]:!rounded-lg [&_button]:!border-zinc-800 [&_button]:!bg-zinc-900 [&_button]:!fill-zinc-400 [&_button:hover]:!bg-zinc-800"
              showInteractive={false}
            />
          </ReactFlow>
        )}
      </div>
      <WorkerInsightBubble
        open={Boolean(selectedWorkerKey && selectedWorker)}
        anchor={anchor}
        workerLabel={selectedWorker?.label ?? ""}
        agentStatus={selectedAgent?.status ?? "idle"}
        insight={insight}
        telemetryEnabled={telemetryEnabled}
        sseConnected={sseConnected}
        onClose={() => onWorkerSelect(null)}
      />
    </div>
  );
}

export function MeshFlowMap({
  emitter,
  workers,
  agentStates,
  meshPackets,
  selectedWorkerKey,
  onWorkerSelect,
  insight,
  telemetryEnabled,
  sseConnected,
}: {
  emitter: AgentNodeState;
  workers: MeshWorkerView[];
  agentStates: Record<string, AgentNodeState>;
  meshPackets: MeshPacket[];
  selectedWorkerKey: string | null;
  onWorkerSelect: (nodeKey: string | null) => void;
  insight: InsightPayload | null;
  telemetryEnabled: boolean | null;
  sseConnected: boolean;
}) {
  return (
    <ReactFlowProvider>
      <FlowInner
        emitterLabel={emitter.label}
        workers={workers}
        agentStates={agentStates}
        meshPackets={meshPackets}
        selectedWorkerKey={selectedWorkerKey}
        onWorkerSelect={onWorkerSelect}
        insight={insight}
        telemetryEnabled={telemetryEnabled}
        sseConnected={sseConnected}
      />
    </ReactFlowProvider>
  );
}
