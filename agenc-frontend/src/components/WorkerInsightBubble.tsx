"use client";

import { useEffect, useRef, useState } from "react";

export interface InsightPayload {
  toolText: string;
  modelText: string;
  phase: string;
  bountyId?: string;
  specialty?: string;
}

function phasePretty(phase: string): string {
  switch (phase) {
    case "evaluate_claim":
      return "Evaluating claim";
    case "execute":
      return "Executing bounty";
    case "merge":
      return "Merging perspectives";
    case "tool":
      return "Tools";
    case "idle":
      return "idle";
    default:
      return phase;
  }
}

function StreamCursor({ reducedMotion }: { reducedMotion: boolean }) {
  if (reducedMotion) {
    return <span className="inline-block w-2 text-emerald-400">▍</span>;
  }
  return (
    <span className="motion-safe:inline-block motion-safe:h-3 motion-safe:w-0.5 motion-safe:animate-pulse motion-safe:bg-emerald-400/90 motion-reduce:inline-block motion-reduce:w-2 motion-reduce:text-emerald-400">
      ▍
    </span>
  );
}

/** Orbital telemetry capsule — anchored above worker node (screen coords). */
export function WorkerInsightBubble({
  open,
  anchor,
  workerLabel,
  agentStatus,
  insight,
  telemetryEnabled,
  sseConnected,
  onClose,
}: {
  open: boolean;
  anchor: { x: number; y: number } | null;
  workerLabel: string;
  agentStatus: string;
  insight: InsightPayload | null;
  /** null = still loading status from bridge */
  telemetryEnabled: boolean | null;
  sseConnected: boolean;
  onClose: () => void;
}) {
  const modelEndRef = useRef<HTMLDivElement>(null);
  const toolEndRef = useRef<HTMLDivElement>(null);
  const [reducedMotion, setReducedMotion] = useState(() =>
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const fn = () => setReducedMotion(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    modelEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [insight?.modelText]);

  useEffect(() => {
    toolEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [insight?.toolText]);

  if (!open || !anchor) return null;

  const phaseLabel = insight?.phase ?? "idle";
  const prettyPhase = phasePretty(phaseLabel);
  const toolText = insight?.toolText ?? "";
  const modelText = insight?.modelText ?? "";
  const hasTools = toolText.length > 0;
  const hasModel = modelText.length > 0;
  const bountyActive = Boolean(insight?.bountyId);
  const waitingWork =
    bountyActive &&
    telemetryEnabled === true &&
    !hasTools &&
    !hasModel &&
    phaseLabel !== "idle";

  let emptyMessage: string | null = null;
  if (telemetryEnabled === false) {
    emptyMessage =
      "Live stream disabled — set BRIDGE_TELEMETRY_SECRET on agenc-api and WORKER_TELEMETRY_SECRET on workers (same value), then restart.";
  } else if (telemetryEnabled === null) {
    emptyMessage = "Checking telemetry…";
  } else if (!bountyActive && !hasTools && !hasModel) {
    emptyMessage =
      "Idle — broadcast a bounty and select this worker during claim or execution to see the stream.";
  } else if (waitingWork) {
    emptyMessage = "Waiting for tokens…";
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close insight panel"
        className="fixed inset-0 z-[45] cursor-default bg-transparent"
        onClick={onClose}
      />
      <div
        className="pointer-events-auto fixed z-[50] w-[min(440px,calc(100vw-2rem))]"
        style={{
          left: anchor.x,
          top: anchor.y,
          transform: "translate(-50%, calc(-100% - 14px))",
        }}
      >
        <div
          className="relative overflow-hidden rounded-2xl border border-emerald-500/25 bg-zinc-950/92 shadow-[0_0_48px_-12px_rgba(16,185,129,0.35)] backdrop-blur-xl"
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-labelledby="insight-title"
        >
          <div className="pointer-events-none absolute inset-0 opacity-[0.45] bg-[linear-gradient(165deg,rgba(16,185,129,0.07),transparent_55%)]" />
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-emerald-500/40 to-transparent motion-safe:animate-pulse" />

          <div className="relative border-b border-zinc-800/60 px-4 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p
                  id="insight-title"
                  className="font-display text-sm font-semibold tracking-tight text-zinc-100"
                >
                  {workerLabel}
                </p>
                <p className="mt-0.5 text-[10px] uppercase tracking-[0.2em] text-emerald-500/80">
                  Live telemetry
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg px-2 py-1 text-[10px] text-zinc-500 transition-colors hover:bg-zinc-800/80 hover:text-zinc-300"
              >
                Esc
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
              <span
                className={`rounded-full border px-2 py-0.5 font-mono ${
                  sseConnected
                    ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-300/90"
                    : "border-amber-500/40 bg-amber-500/10 text-amber-200/90"
                }`}
              >
                {sseConnected ? "SSE live" : "SSE reconnecting…"}
              </span>
              <span className="rounded-full border border-zinc-700/80 bg-zinc-900/80 px-2 py-0.5 font-mono text-zinc-400">
                status: {agentStatus}
              </span>
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 font-mono text-emerald-400/90">
                {prettyPhase}
              </span>
              {insight?.bountyId && (
                <span className="rounded-full border border-zinc-700/80 px-2 py-0.5 font-mono text-zinc-500">
                  #{insight.bountyId}
                </span>
              )}
              {insight?.specialty && (
                <span className="rounded-full border border-zinc-700/80 px-2 py-0.5 text-zinc-500">
                  {insight.specialty}
                </span>
              )}
            </div>
            {telemetryEnabled === false && (
              <p className="mt-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2 py-1.5 text-[10px] leading-snug text-amber-200/90">
                Dashboard streaming is off until the bridge enables telemetry (
                <code className="text-amber-100/90">BRIDGE_TELEMETRY_SECRET</code>
                ).
              </p>
            )}
          </div>

          <div className="relative space-y-3 px-3 pb-3 pt-2">
            <div>
              <p className="mb-1 text-[9px] uppercase tracking-[0.18em] text-zinc-600">
                Tools
              </p>
              <div
                className="max-h-[min(120px,22vh)] overflow-y-auto rounded-xl border border-zinc-800/60 bg-[#060607]/95 px-3 py-2 font-mono text-[10px] leading-relaxed text-zinc-300 shadow-inner"
                style={{ tabSize: 2 }}
              >
                {hasTools ? (
                  <>
                    <span className="whitespace-pre-wrap break-words">{toolText}</span>
                    <StreamCursor reducedMotion={reducedMotion} />
                    <div ref={toolEndRef} />
                  </>
                ) : (
                  <span className="text-zinc-600">No tool I/O yet for this run.</span>
                )}
              </div>
            </div>

            <div>
              <p className="mb-1 text-[9px] uppercase tracking-[0.18em] text-zinc-600">
                Model stream
              </p>
              <div
                className="max-h-[min(200px,32vh)] overflow-y-auto rounded-xl border border-zinc-800/60 bg-[#050506]/90 px-3 py-2 text-[12px] leading-relaxed text-zinc-200 shadow-inner motion-safe:[box-shadow:inset_0_0_24px_rgba(16,185,129,0.06)]"
                style={{ tabSize: 2 }}
              >
                {hasModel ? (
                  <>
                    <span className="whitespace-pre-wrap break-words">{modelText}</span>
                    <StreamCursor reducedMotion={reducedMotion} />
                    <div ref={modelEndRef} />
                  </>
                ) : emptyMessage ? (
                  <span className="text-zinc-500">
                    <span className="text-emerald-500/50">▸ </span>
                    {emptyMessage}
                  </span>
                ) : (
                  <span className="text-zinc-600">
                    <span className="text-emerald-500/50">▸ </span>
                    Waiting for model output…
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
