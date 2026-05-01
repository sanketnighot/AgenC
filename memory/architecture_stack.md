---
name: AgenC Architecture & Stack
description: Full system architecture, file layout, port map, and how components connect
type: project
---

## Components

```
User Browser
    ↓ http://localhost:3000
Next.js Frontend (agenc-frontend/)
    ↓ http://127.0.0.1:8000/api/*
FastAPI Bridge (agenc-api/main.py)  ← port 8000
    ↓ http://127.0.0.1:8001/send|recv|topology
Emitter AXL Node (emitter-config.json) ← api_port:8001, tcp_port:7001
    ↓ TLS/TCP on 127.0.0.1:9001
Worker 1 AXL Node (worker1-config.json) ← api_port:8002, tcp_port:7001
Worker 2 AXL Node (worker2-config.json) ← api_port:8003, tcp_port:7001
    ↓ http://127.0.0.1:800[2|3]/send|recv
worker1.py / worker2.py (OpenAI gpt-4o-mini processors)
```

## File Layout

| Path | Role |
|------|------|
| `cmd/node/`, `api/`, `internal/` | Go AXL node binary (build with `make build`) |
| `agenc-api/main.py` | FastAPI bridge; translates UI ↔ AXL /send /recv |
| `agenc-frontend/src/app/page.tsx` | Next.js single-page dashboard |
| `worker1.py` | Worker 1 process: polls /recv, calls OpenAI, sends result |
| `worker2.py` | Worker 2 process: same, different port (8003) |
| `emitter.py` | Standalone emitter script (used for CLI testing) |
| `emitter-config.json` | Emitter AXL config: api_port=8001, Listen=9001 |
| `worker1-config.json` | Worker 1 config: api_port=8002, Peers=[127.0.0.1:9001] |
| `worker2-config.json` | Worker 2 config: api_port=8003, Peers=[127.0.0.1:9001] |
| `emitter.pem` / `worker1.pem` / `worker2.pem` | ed25519 keys for persistent peer identity |
| `.env` | OPENAI_API_KEY |

## Known Worker Public Keys (from scratchpad)

- Emitter: `50f88b3ab17f33433fbb0b06d15b4814e095d281428541e9abd3d271c69ac425`
- Worker 1: `7f735488b692e04fbb3071c4ad6a2774bd0ec3bb7b5508e09a0d00a31af0e5f4`
- Worker 2: `68ed6920e3d1b7b8ceaf8519006ab614f76cb23738ebf06f364426b8000fe8c0`

## Stack Versions

- Next.js 16.2.4, React 19.2.4, TypeScript 5, Tailwind CSS 4
- FastAPI 0.136.1+, Python 3.13+, OpenAI SDK
- Go with gVisor + Yggdrasil (see go.mod)

## Build Commands

```bash
make build              # Go node binary
cd agenc-api && uvicorn main:app --port 8000
cd agenc-frontend && npm run dev
python worker1.py       # in one terminal
python worker2.py       # in another terminal
```
