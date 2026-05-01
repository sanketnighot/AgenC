"use client";

import { SpokeTrack } from "@/components/MeshLinks";
import type { MeshPacket } from "@/lib/meshPackets";

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

export interface MeshWorkerView {
  node_key: string;
  label: string;
  specialty: string;
  short_id: string;
  peer_id: string;
  mesh_connected: boolean;
}

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

const WORKER_GLYPH = ["◈", "◇", "▣", "◆", "⬢"];

function HubNode({
  variant,
  node,
  glyph,
  shortId,
}: {
  variant: "emitter" | "worker";
  node: NodeState;
  glyph: string;
  shortId?: string;
}) {
  const { ring, glow, ping } = STATUS_RING[node.status];

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-14 w-14">
        {ping && (
          <span
            className={`absolute inset-0 rounded-full ${ping} animate-ping`}
          />
        )}
        <div
          className={`flex h-14 w-14 items-center justify-center rounded-full bg-zinc-900 ring-2 transition-all duration-500 ${ring}`}
          style={glow ? { boxShadow: glow } : undefined}
        >
          <span className="select-none text-xl">{glyph}</span>
        </div>
      </div>
      <div className="max-w-[140px] text-center">
        <p className="text-xs font-medium text-zinc-300">{node.label}</p>
        {node.specialty && (
          <p className="mt-0.5 text-[10px] text-zinc-600">{node.specialty}</p>
        )}
        {variant === "worker" && shortId && (
          <p className="mt-1 font-mono text-[9px] tracking-tight text-zinc-500">
            {shortId}…
          </p>
        )}
        <div className="mt-1.5 flex items-center justify-center gap-1.5">
          <span
            className={`h-1 w-1 rounded-full ${STATUS_DOT[node.status]}`}
            title="Task state"
          />
          {variant === "worker" && (
            <span
              className="text-[9px] font-mono uppercase tracking-wider text-emerald-500/90"
              title="Mesh peer connected"
            >
              live
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function MeshHub({
  emitter,
  workers,
  nodes,
  meshPackets,
}: {
  emitter: NodeState;
  workers: MeshWorkerView[];
  nodes: Record<string, NodeState>;
  meshPackets: MeshPacket[];
}) {
  const n = workers.length;

  return (
    <div className="relative mx-auto flex min-h-[min(52vh,440px)] w-full max-w-[640px] flex-col items-center justify-center overflow-visible rounded-2xl border border-zinc-800/50 bg-zinc-950/40 px-4 py-10">
      <div className="absolute inset-0 rounded-2xl opacity-[0.35] [background-image:radial-gradient(ellipse_at_50%_30%,rgba(16,185,129,0.07),transparent_55%),repeating-linear-gradient(-18deg,transparent,transparent_31px,rgba(63,63,70,0.04)_31px,rgba(63,63,70,0.04)_32px)]" />

      <div className="relative mb-2 flex w-full items-center justify-between px-1">
        <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-600">
          Mesh map
        </span>
        <span className="font-mono text-[10px] text-zinc-600">
          {n} connected peer{n === 1 ? "" : "s"}
        </span>
      </div>

      <div className="relative isolate aspect-square w-full max-w-[420px]">
        {/* Emitter */}
        <div className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2">
          <HubNode variant="emitter" node={emitter} glyph="⬡" />
        </div>

        {n === 0 && (
          <p className="absolute bottom-2 left-1/2 z-10 max-w-[240px] -translate-x-1/2 text-center text-xs leading-relaxed text-zinc-600">
            No peers connected. Start worker nodes to see them join the map.
          </p>
        )}

        {workers.map((w, i) => {
          const deg = -90 + (360 / n) * i;
          const nid = w.node_key;
          const nodeState = nodes[nid] ?? {
            status: "idle" as const,
            label: w.label,
            specialty: w.specialty,
          };
          const glyph = WORKER_GLYPH[i % WORKER_GLYPH.length];

          return (
            <div
              key={w.node_key}
              className="absolute left-1/2 top-1/2 z-10 flex items-center"
              style={{
                left: "50%",
                top: "50%",
                transform: `translateY(-50%) rotate(${deg}deg)`,
                transformOrigin: "0 50%",
              }}
            >
              <div className="h-14 w-7 shrink-0" aria-hidden />
              <SpokeTrack spokeIndex={i} packets={meshPackets} />
              <div className="w-3 shrink-0" aria-hidden />
              <div
                className="shrink-0"
                style={{ transform: `rotate(${-deg}deg)` }}
              >
                <HubNode
                  variant="worker"
                  node={nodeState}
                  glyph={glyph}
                  shortId={w.short_id}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
