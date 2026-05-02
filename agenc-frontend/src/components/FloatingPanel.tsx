"use client";

import type { ReactNode } from "react";
import { Rnd } from "react-rnd";

export interface PanelBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function FloatingPanel({
  defaultBox,
  minWidth = 200,
  minHeight = 120,
  maxWidth,
  maxHeight,
  zIndex = 10,
  dragHeader,
  children,
}: {
  defaultBox: PanelBox;
  minWidth?: number;
  minHeight?: number;
  /** Keeps resize within window; omit for no cap */
  maxWidth?: number;
  maxHeight?: number;
  zIndex?: number;
  dragHeader: ReactNode;
  children: ReactNode;
}) {
  return (
    <Rnd
      default={defaultBox}
      minWidth={minWidth}
      minHeight={minHeight}
      maxWidth={maxWidth}
      maxHeight={maxHeight}
      resizeGrid={[8, 8]}
      bounds="window"
      dragHandleClassName="floating-panel-drag"
      style={{ zIndex }}
      enableResizing={{
        top: true,
        right: true,
        bottom: true,
        left: true,
        topRight: true,
        bottomRight: true,
        bottomLeft: true,
        topLeft: true,
      }}
      resizeHandleStyles={{
        bottomRight: { width: 14, height: 14, bottom: 4, right: 4 },
        bottomLeft: { width: 14, height: 14, bottom: 4, left: 4 },
        topRight: { width: 14, height: 14, top: 4, right: 4 },
        topLeft: { width: 14, height: 14, top: 4, left: 4 },
      }}
      className="floating-panel-rnd"
    >
      <div className="flex h-full max-h-full flex-col overflow-hidden rounded-2xl border border-zinc-800/40 bg-zinc-950/70 shadow-xl backdrop-blur-md">
        <div className="floating-panel-drag flex shrink-0 cursor-grab items-center justify-between gap-2 border-b border-zinc-800/40 px-3 py-2 select-none active:cursor-grabbing">
          <div className="min-w-0 flex-1">{dragHeader}</div>
          <span
            className="shrink-0 font-mono text-[10px] text-zinc-600"
            aria-hidden
            title="Drag to move · drag edges to resize"
          >
            ⠿
          </span>
        </div>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      </div>
    </Rnd>
  );
}
