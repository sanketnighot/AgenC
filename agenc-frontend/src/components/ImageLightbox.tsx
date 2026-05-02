"use client";

import { useEffect } from "react";

export function ImageLightbox({
  src,
  onClose,
}: {
  src: string | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!src) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [src, onClose]);

  if (!src) return null;

  return (
    <div
      role="dialog"
      aria-modal
      aria-label="Bounty image preview"
      className="fixed inset-0 z-[200] box-border bg-black/85 p-[20%]"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- dynamic data URLs */}
        <img
          src={src}
          alt="Bounty result"
          className="max-h-full max-w-full rounded-xl border border-zinc-700/50 object-contain shadow-2xl"
        />
      </div>
      <button
        type="button"
        onClick={onClose}
        className="absolute right-[max(1rem,calc(20%-0.5rem))] top-[max(1rem,calc(20%-0.5rem))] rounded-lg border border-zinc-600 bg-zinc-900/90 px-2.5 py-1 text-xs text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-white"
      >
        Close
      </button>
    </div>
  );
}
