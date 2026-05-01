"use client";

import { useEffect, useRef } from "react";

export interface InsightPayload {
  text: string;
  phase: string;
  bountyId?: string;
  specialty?: string;
}

/** Orbital telemetry capsule — anchored above worker node (screen coords). */
export function WorkerInsightBubble({
  open,
  anchor,
  workerLabel,
  agentStatus,
  insight,
  onClose,
}: {
  open: boolean;
  anchor: { x: number; y: number } | null;
  workerLabel: string;
  agentStatus: string;
  insight: InsightPayload | null;
  onClose: () => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [insight?.text]);

  if (!open || !anchor) return null;

  const phaseLabel = insight?.phase ?? "idle";
  const phasePretty =
    phaseLabel === "evaluate_claim"
      ? "Evaluating claim"
      : phaseLabel === "execute"
        ? "Executing bounty"
        : phaseLabel === "merge"
          ? "Merging perspectives"
          : phaseLabel;

  return (
    <>
      <button
        type="button"
        aria-label="Close insight panel"
        className="fixed inset-0 z-[45] cursor-default bg-transparent"
        onClick={onClose}
      />
      <div
        className="pointer-events-auto fixed z-[50] w-[min(420px,calc(100vw-2rem))]"
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
              <span className="rounded-full border border-zinc-700/80 bg-zinc-900/80 px-2 py-0.5 font-mono text-zinc-400">
                status: {agentStatus}
              </span>
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 font-mono text-emerald-400/90">
                {phasePretty}
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
          </div>

          <div className="relative px-3 pb-3 pt-2">
            <p className="mb-1.5 text-[9px] uppercase tracking-[0.18em] text-zinc-600">
              Model stream
            </p>
            <div
              className="max-h-[min(220px,40vh)] overflow-y-auto rounded-xl border border-zinc-800/60 bg-[#050506]/90 px-3 py-2 font-mono text-[11px] leading-relaxed text-emerald-100/90 shadow-inner motion-safe:[box-shadow:inset_0_0_24px_rgba(16,185,129,0.06)]"
              style={{ tabSize: 2 }}
            >
              <span className="motion-safe:animate-[pulse_3s_ease-in-out_infinite] text-emerald-500/50">
                ▸{" "}
              </span>
              {insight?.text ? (
                <span className="whitespace-pre-wrap break-words">{insight.text}</span>
              ) : (
                <span className="text-zinc-600">
                  Waiting for tokens… select during an active bounty.
                </span>
              )}
              <div ref={endRef} />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
