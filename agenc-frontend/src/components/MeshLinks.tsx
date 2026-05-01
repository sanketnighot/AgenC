"use client";

import type { MeshPacket, PacketTone } from "@/lib/meshPackets";

const TONE_CLASS: Record<PacketTone, string> = {
  amber:
    "bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.85),0_0_4px_rgba(251,191,36,0.5)]",
  emerald:
    "bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.65),0_0_4px_rgba(52,211,153,0.45)]",
  emeraldBright:
    "bg-emerald-200 shadow-[0_0_16px_rgba(167,243,208,0.95),0_0_6px_rgba(110,231,183,0.8)] ring-1 ring-emerald-300/40",
  red: "bg-red-500 shadow-[0_0_12px_rgba(248,113,113,0.75),0_0_4px_rgba(239,68,68,0.5)]",
  emeraldDim:
    "bg-emerald-600/95 opacity-90 shadow-[0_0_8px_rgba(52,211,153,0.35)]",
};

function PacketDot({ packet }: { packet: MeshPacket }) {
  "use no memo";
  const anim =
    packet.dir === "ltr" ? "animate-packet-ltr" : "animate-packet-rtl";
  return (
    <span
      className={`packet-dot pointer-events-none absolute top-1/2 left-0 z-20 h-2.5 w-2.5 rounded-full ${TONE_CLASS[packet.tone]} ${anim}`}
      aria-hidden
    />
  );
}

/** One radial spoke track (emitter → worker); packets animate along the line. */
export function SpokeTrack({
  spokeIndex,
  packets,
}: {
  spokeIndex: number;
  packets: MeshPacket[];
}) {
  "use no memo";
  const visible = packets.filter((p) => p.spokeIndex === spokeIndex);

  return (
    <div className="relative flex h-10 min-w-[72px] max-w-[120px] shrink-0 flex-1 items-center overflow-visible pb-6">
      <div className="relative min-h-[18px] w-full overflow-visible">
        <div className="pointer-events-none absolute inset-x-0 top-1/2 z-0 h-px -translate-y-1/2 bg-gradient-to-r from-zinc-800 via-zinc-700/90 to-zinc-800" />
        {visible.map((p) => (
          <PacketDot key={p.id} packet={p} />
        ))}
      </div>
    </div>
  );
}
