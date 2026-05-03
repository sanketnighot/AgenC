# AgenC frontend

Next.js **14** dashboard for the AgenC bounty mesh: compose tasks, watch **SSE** live updates, visualize mesh traffic, and (optionally) deposit escrow via **wagmi** / **viem**.

## Requirements

- [Bun](https://bun.sh) (used in this repo) or Node compatible with Next 14

## Setup

```bash
bun install
```

## Configuration

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | FastAPI bridge base URL (default `http://127.0.0.1:8000`) |
| `NEXT_PUBLIC_CONTRACT_ADDRESS` | Bounty escrow contract (`0x…`) when using on-chain deposit UI |

## Development

```bash
bun dev
```

Open [http://localhost:3000](http://localhost:3000).

## Production build

```bash
bun run build
bun run start
# or: npx next start -p 3000
```

See **`docs/deployment.md`** for **systemd** (`deploy/agenc-frontend.service`) and reverse-proxy notes (`deploy/nginx.conf` example).

## Features (UI)

- Bounty templates, category filters, floating panels
- **MeshFlowMap** + packet animation (`useMeshAnimation`)
- **SSE** subscription to `/api/events` (`useBountyStream`) — bounties, node status, worker LLM/tool streams
- Markdown results, image lightbox for generated assets
- Wallet connect + escrow flows when contract env is set

Product and protocol details: **[`../docs/agenc.md`](../docs/agenc.md)**.
