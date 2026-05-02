import type { PanelBox } from "@/components/FloatingPanel";

/** Pixel alignment with pre-draggable layout */
export const LAYOUT_TOP = 80;
export const LAYOUT_SIDE = 16;
export const LAYOUT_BOTTOM = 32;
export const LG_BREAKPOINT = 1024;
export const BROADCAST_LG_LEFT = 320;
export const BROADCAST_LG_RIGHT_INSET = 352;

export function computePanelLayout(vp: { w: number; h: number }): {
  activityPanelBox: PanelBox;
  bountyRailBox: PanelBox;
  broadcastPanelBox: PanelBox;
  panelBounds: {
    maxPanelW: number;
    maxPanelH: number;
    sidePanelMaxW: number;
  };
} {
  const activityPanelBox: PanelBox = {
    x: LAYOUT_SIDE,
    y: LAYOUT_TOP,
    width: 288,
    height: Math.max(240, vp.h - LAYOUT_TOP - LAYOUT_BOTTOM),
  };

  const wRail = 320;
  const bountyRailBox: PanelBox = {
    x: vp.w - LAYOUT_SIDE - wRail,
    y: LAYOUT_TOP,
    width: wRail,
    height: Math.max(240, vp.h - LAYOUT_TOP - LAYOUT_BOTTOM),
  };

  const H = 280;
  const y = vp.h - LAYOUT_BOTTOM - H;
  let broadcastPanelBox: PanelBox;
  if (vp.w >= LG_BREAKPOINT) {
    const width = vp.w - BROADCAST_LG_LEFT - BROADCAST_LG_RIGHT_INSET;
    broadcastPanelBox = {
      x: BROADCAST_LG_LEFT,
      y,
      width: Math.max(280, width),
      height: H,
    };
  } else {
    broadcastPanelBox = {
      x: LAYOUT_SIDE,
      y,
      width: vp.w - 2 * LAYOUT_SIDE,
      height: H,
    };
  }

  const maxPanelW = vp.w - 2 * LAYOUT_SIDE;
  const maxPanelH = vp.h - LAYOUT_TOP - LAYOUT_BOTTOM;
  const sidePanelMaxW = Math.min(maxPanelW, Math.floor(vp.w * 0.5));

  return {
    activityPanelBox,
    bountyRailBox,
    broadcastPanelBox,
    panelBounds: {
      maxPanelW,
      maxPanelH,
      sidePanelMaxW,
    },
  };
}
