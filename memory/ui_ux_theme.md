---
name: AgenC UI/UX Theme
description: Frontend design language, color palette, component patterns, and tech stack
type: project
---

## Design Language

**Dark terminal / cyberpunk aesthetic:**
- Background: `neutral-950` (#0a0a0a near-black)
- Text: `green-400` primary (terminal green)
- Secondary text: `neutral-400` / `neutral-300`
- Borders: `neutral-800` / `neutral-700`
- Panels: `neutral-900` with `border-neutral-800`
- Accent/CTA: `green-500` → `green-400` on hover
- Font: Geist Mono (monospace throughout)

## Current Layout (page.tsx)

Two-column grid on md+, single column mobile:
- **Left panel**: "Mesh Network Logs" — live scrolling event feed with timestamps, 500px height, overflow-y-auto
- **Right panel**: "Post New Bounty" form — task textarea + reward input + "Broadcast to Mesh" button

## Log Entry Format

```
[HH:MM:SS] [*] Worker {8-char-id} claimed the task!
[HH:MM:SS] [+] TASK COMPLETED by {8-char-id}. Result: {result}
```

Empty state: "Waiting for network activity..." with `animate-pulse`

## Tech Stack

- Next.js 16 (App Router, `"use client"`)
- React 19
- Tailwind CSS v4
- TypeScript
- Geist font (sans + mono from next/font/google)

## Polling Pattern

Frontend uses `setInterval` (2s) to poll `/api/network-logs`. No WebSocket yet.

## Phase 4 UI Enhancements Needed

- Visual node map showing live peer connections
- Per-node status indicators (online/busy/idle)
- Multi-result aggregation view (showing chunks from different workers)
- Competitive bid visualization (which worker won the race)
