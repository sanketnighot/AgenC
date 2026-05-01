"use client";

import "@xyflow/react/dist/style.css";

import { useCallback, useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";

import type { MeshPacket } from "@/lib/meshPackets";

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
const CX = 400;
const CY = 300;
const SPOKE_R = 230;

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
        <span className={`h-1 w-1 rounded-full ${STATUS_DOT[data.agent.status]}`} />
        <span className="text-[8px] font-mono uppercase tracking-wider text-emerald-500/90">
          live
        </span>
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

  const list: Node[] = [
    {
      id: EMITTER_ID,
      type: "emitter",
      position: { x: CX - ew / 2, y: CY - eh / 2 },
      data: { label: emitterLabel, workerCount: n },
      draggable: false,
    },
  ];

  workers.forEach((w, i) => {
    const angle = (-Math.PI / 2) + (2 * Math.PI * i) / Math.max(n, 1);
    const nw = 128;
    const nh = 148;
    const cx = CX + SPOKE_R * Math.cos(angle);
    const cy = CY + SPOKE_R * Math.sin(angle);
    const agent =
      agentStates[w.node_key] ?? ({
        status: "idle" as const,
        label: w.label,
        specialty: w.specialty,
      } satisfies AgentNodeState);

    list.push({
      id: w.node_key,
      type: "worker",
      position: { x: cx - nw / 2, y: cy - nh / 2 },
      data: {
        worker: w,
        agent,
        angleRad: angle,
        glyphIndex: i,
      },
      draggable: false,
    });
  });

  return list;
}

function buildEdges(workers: MeshWorkerView[], meshPackets: MeshPacket[]): Edge[] {
  const active = new Set(meshPackets.map((p) => p.spokeIndex));
  return workers.map((w, i) => ({
    id: `e-${w.node_key}`,
    source: EMITTER_ID,
    sourceHandle: `out-${i}`,
    target: w.node_key,
    targetHandle: "in",
    type: "smoothstep",
    animated: true,
    style: {
      stroke: active.has(i) ? "#34d399" : "#3f3f46",
      strokeWidth: active.has(i) ? 2.75 : 1.35,
    },
    className: active.has(i) ? "mesh-edge-active drop-shadow-[0_0_8px_rgba(52,211,153,0.45)]" : "",
  }));
}

function FlowInner({
  emitterLabel,
  workers,
  agentStates,
  meshPackets,
}: {
  emitterLabel: string;
  workers: MeshWorkerView[];
  agentStates: Record<string, AgentNodeState>;
  meshPackets: MeshPacket[];
}) {
  const { fitView } = useReactFlow();

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

  useEffect(() => {
    setNodes(buildNodes(emitterLabel, workers, agentStates));
  }, [emitterLabel, workers, agentStates, setNodes]);

  useEffect(() => {
    setEdges(buildEdges(workers, meshPackets));
  }, [workers, meshPackets, setEdges]);

  useEffect(() => {
    const t = requestAnimationFrame(() => {
      fitView({ padding: 0.22, duration: 280, maxZoom: 1.2 });
    });
    return () => cancelAnimationFrame(t);
  }, [workers.length, fitView]);

  const onInit = useCallback(() => {
    fitView({ padding: 0.22, maxZoom: 1.2 });
  }, [fitView]);

  const n = workers.length;

  return (
    <div className="relative flex min-h-[min(52vh,480px)] w-full flex-col rounded-2xl border border-zinc-800/50 bg-[#060607] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <div className="absolute inset-0 rounded-2xl opacity-[0.4] [background-image:radial-gradient(ellipse_at_50%_35%,rgba(16,185,129,0.06),transparent_60%),repeating-linear-gradient(-18deg,transparent,transparent_31px,rgba(63,63,70,0.05)_31px,rgba(63,63,70,0.05)_32px)]" />

      <div className="relative z-10 flex items-center justify-between px-4 pt-4">
        <span className="text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-600">
          Mesh map
        </span>
        <span className="font-mono text-[10px] text-zinc-500">
          {n} connected peer{n === 1 ? "" : "s"}
        </span>
      </div>

      <div className="relative z-10 h-[min(52vh,440px)] w-full">
        {n === 0 ? (
          <div className="flex h-full items-center justify-center px-6">
            <p className="max-w-[280px] text-center text-xs leading-relaxed text-zinc-600">
              No peers connected. Start worker nodes — they appear here with live
              edges.
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
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnScroll
            zoomOnScroll
            zoomOnPinch
            panOnDrag
            defaultEdgeOptions={{
              type: "smoothstep",
            }}
            className="!bg-transparent [&_.react-flow__edge-path]:!stroke-linecap-round"
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
            <MiniMap
              className="!m-2 !overflow-hidden !rounded-xl !border !border-zinc-800/80 !bg-zinc-950/90 [&_.react-flow__minimap-mask]:fill-black/45 [&_.react-flow__minimap-node]:!rounded-md"
              zoomable
              pannable
              nodeColor={(node) =>
                node.type === "emitter" ? "#10b981" : "#52525b"
              }
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}

export function MeshFlowMap({
  emitter,
  workers,
  agentStates,
  meshPackets,
}: {
  emitter: AgentNodeState;
  workers: MeshWorkerView[];
  agentStates: Record<string, AgentNodeState>;
  meshPackets: MeshPacket[];
}) {
  return (
    <ReactFlowProvider>
      <FlowInner
        emitterLabel={emitter.label}
        workers={workers}
        agentStates={agentStates}
        meshPackets={meshPackets}
      />
    </ReactFlowProvider>
  );
}
