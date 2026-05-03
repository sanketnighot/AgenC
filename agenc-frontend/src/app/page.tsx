"use client";
import {
  useState,
  useEffect,
  useLayoutEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { useAccount, useConnect, useDisconnect, useBalance, useWriteContract, useWaitForTransactionReceipt, usePublicClient } from "wagmi";
import { injected } from "wagmi/connectors";
import { parseEther, keccak256, toBytes } from "viem";

import { MeshFlowMap } from "@/components/MeshFlowMap";
import { FloatingPanel, type PanelBox } from "@/components/FloatingPanel";
import { ImageLightbox } from "@/components/ImageLightbox";
import { BountyResultMarkdown } from "@/components/BountyResultMarkdown";
import type { InsightPayload } from "@/components/WorkerInsightBubble";
import { BOUNTY_ESCROW_ABI } from "@/lib/abi";
import { computePanelLayout } from "@/lib/panelLayout";
import { useMeshAnimation } from "@/hooks/useMeshAnimation";
import {
  useBountyStream,
  type BountyCard,
  type BountyImage,
  type LogEntry,
  type NodeState,
  type WorkerInsightBuf,
} from "@/hooks/useBountyStream";

const CONTRACT_ADDRESS = (process.env.NEXT_PUBLIC_CONTRACT_ADDRESS ?? "") as `0x${string}`;

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function useViewport() {
  const [vp, setVp] = useState({ w: 1280, h: 800 });

  useLayoutEffect(() => {
    setVp({ w: window.innerWidth, h: window.innerHeight });
  }, []);

  useEffect(() => {
    const read = () =>
      setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", read);
    return () => window.removeEventListener("resize", read);
  }, []);

  return vp;
}

const TAG_COLORS: Record<string, string> = {
  collab: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  img: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  uniswap: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  data: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  tool: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  web: "bg-teal-500/10 text-teal-400 border-teal-500/20",
  price: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  creative: "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20",
  sentiment: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  yield: "bg-lime-500/10 text-lime-400 border-lime-500/20",
};

const TEMPLATE_CATS = [
  { id: "all", label: "All" },
  { id: "data", label: "Data" },
  { id: "sentiment", label: "Mood" },
  { id: "yield", label: "Yield" },
  { id: "img", label: "Art" },
  { id: "collab", label: "Collab" },
] as const;

const TEMPLATES = [
  {
    icon: "📊",
    label: "DeFi Report",
    reward: "0.008",
    tags: ["collab", "uniswap", "web", "data"],
    task:
      "Analyze the top 5 DeFi protocols by TVL using live Uniswap V3 pool data. Compare risk/reward profiles and write a 3-bullet summary for a DeFi investor.",
  },
  {
    icon: "🎨",
    label: "Market Visual",
    reward: "0.005",
    tags: ["img", "creative"],
    task:
      "Generate a bold infographic-style image showing ETH price performance vs BTC over the past month. Include vibrant colors, clear labels, and a compelling headline.",
  },
  {
    icon: "💎",
    label: "ETH Price Brief",
    reward: "0.002",
    tags: ["data", "tool", "price"],
    task:
      "Fetch the current ETH/USD price using live market data. Calculate 7-day percentage change and explain the top 2 catalysts driving recent movement.",
  },
  {
    icon: "🦄",
    label: "Uniswap Snapshot",
    reward: "0.004",
    tags: ["uniswap", "data", "tool"],
    task:
      "Pull current TVL and fee APR for the top 3 ETH/USDC Uniswap V3 pools. Rank them by yield and recommend which is best for a passive liquidity provider.",
  },
  {
    icon: "😱",
    label: "Fear & Greed",
    reward: "0.002",
    tags: ["sentiment", "data", "tool"],
    task:
      "Check today's Crypto Fear & Greed Index and identify the top trending coins on CoinGecko right now. Explain what the current sentiment reading means for short-term ETH price action.",
  },
  {
    icon: "🌾",
    label: "Yield Hunt",
    reward: "0.003",
    tags: ["yield", "data", "tool"],
    task:
      "Find the top 5 highest-yield DeFi pools on Ethereum right now using live DeFiLlama data. Filter for pools with at least $1M TVL and rank by total APY. Flag any with high impermanent loss risk.",
  },
  {
    icon: "🏦",
    label: "Aave Rates",
    reward: "0.002",
    tags: ["yield", "tool"],
    task:
      "Compare current Aave V3 supply APY for USDC, DAI, and WETH on Ethereum and Arbitrum. Recommend the single best passive lending position for a risk-averse stablecoin holder.",
  },
  {
    icon: "🧠",
    label: "Sentiment Report",
    reward: "0.006",
    tags: ["sentiment", "collab", "data", "tool"],
    task:
      "Combine live Fear & Greed Index, top trending coins, and ETH/BTC price data to write a 3-bullet market sentiment brief. Rate current conditions as Risk-On, Neutral, or Risk-Off with supporting evidence.",
  },
  {
    icon: "🔍",
    label: "DeFi Intel",
    reward: "0.009",
    tags: ["yield", "sentiment", "collab", "data"],
    task:
      "Comprehensive DeFi opportunity scan: find the top 3 yield pools on DeFiLlama AND assess market sentiment via Fear & Greed Index. Determine whether current crowd psychology supports or undermines entering these positions now.",
  },
  {
    icon: "🚀",
    label: "Crypto Strategy",
    reward: "0.012",
    tags: ["collab", "img", "sentiment", "yield"],
    task:
      "Create a full crypto investor brief: generate a market overview image, pull current Fear & Greed sentiment, and identify the top 2 yield opportunities on DeFi. Combine into a single actionable recommendation for a DeFi investor.",
  },
];


// ── ActivityTimeline ──────────────────────────────────────────────────────────

const TIMELINE_DOT: Record<string, string> = {
  new:     "bg-amber-400",
  bid:     "bg-sky-400",
  win:     "bg-emerald-400",
  rej:     "bg-red-400/70",
  done:    "bg-emerald-300",
  exp:     "bg-zinc-600",
  resolve: "bg-zinc-500",
  arb:     "bg-cyan-400/80",
  collab:  "bg-violet-400",
  p2p:     "bg-violet-300",
};

const TIMELINE_PILL: Record<string, string> = {
  new:     "bg-amber-500/10 text-amber-400 border-amber-500/20",
  bid:     "bg-sky-500/10 text-sky-400 border-sky-500/20",
  win:     "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  rej:     "bg-red-500/10 text-red-400/70 border-red-500/20",
  done:    "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
  exp:     "bg-zinc-800/40 text-zinc-500 border-zinc-700/20",
  resolve: "bg-zinc-800/40 text-zinc-500 border-zinc-700/20",
  arb:     "bg-cyan-500/10 text-cyan-400/80 border-cyan-500/20",
  collab:  "bg-violet-500/10 text-violet-400 border-violet-500/20",
  p2p:     "bg-violet-500/10 text-violet-300 border-violet-500/20",
};

function ActivityTimeline({ logs, logsEndRef }: {
  logs: LogEntry[];
  logsEndRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {logs.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-3 py-6">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-700" />
            <p className="text-xs text-zinc-700">Awaiting events…</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-3 py-3 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar]:w-1">
          <div className="relative border-l-2 border-zinc-800/60 pl-4 space-y-0">
            {logs.map((log, i) => (
              <div key={i} className="group relative pb-3">
                <span
                  className={`absolute -left-5.25 top-1 h-2.5 w-2.5 rounded-full ring-2 ring-zinc-950 ${TIMELINE_DOT[log.tag] ?? "bg-zinc-600"}`}
                />
                <div className="flex items-start gap-2 flex-wrap">
                  <span
                    className={`shrink-0 rounded-full border px-1.5 py-0.5 font-mono text-[9px] ${TIMELINE_PILL[log.tag] ?? "bg-zinc-800/40 text-zinc-500 border-zinc-700/20"}`}
                  >
                    {log.tag}
                  </span>
                  <p className="min-w-0 flex-1 text-xs leading-relaxed text-zinc-300 line-clamp-2">
                    {log.msg}
                  </p>
                </div>
                <span className="mt-0.5 block font-mono text-[10px] text-zinc-700 opacity-0 transition-opacity group-hover:opacity-100">
                  {log.time}
                </span>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── AuctionBountyCard + AuctionBountyRail ─────────────────────────────────────

const STAMP_STYLE: Record<BountyCard["status"], string> = {
  PENDING:       "border-amber-500/40 text-amber-400/80 bg-amber-500/5",
  EXECUTING:     "border-emerald-500/40 text-emerald-400 bg-emerald-500/5",
  COLLABORATING: "border-violet-500/40 text-violet-400/80 bg-violet-500/5",
  COMPLETED:     "border-emerald-400/60 text-emerald-300 bg-emerald-500/8",
  UNCLAIMED:     "border-zinc-600/40 text-zinc-500 bg-zinc-800/20",
};

const GLYPH_LIST = ["◈", "◇", "▣", "◆", "⬢"];

async function shareBountyLink(b: BountyCard) {
  const url = `${window.location.origin}${window.location.pathname}?bounty=${b.bounty_id}`;
  const title = `AgenC · #${b.bounty_id}`;
  const text =
    b.task.length > 160 ? `${b.task.slice(0, 160)}…` : b.task;
  if (typeof navigator !== "undefined" && navigator.share) {
    try {
      await navigator.share({ title, text, url });
      return;
    } catch (err) {
      if ((err as { name?: string })?.name === "AbortError") return;
    }
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
  }
}

function AuctionBountyCard({
  b,
  expanded,
  onToggle,
  onRepost,
  onImageClick,
}: {
  b: BountyCard;
  expanded: boolean;
  onToggle: () => void;
  onRepost: (b: BountyCard) => void;
  onImageClick?: (dataUrl: string) => void;
}) {
  const bidSummary =
    b.bids.length === 0
      ? "No bids yet"
      : `${b.bids.length} bid${b.bids.length === 1 ? "" : "s"}`;

  return (
    <div className="min-w-0 border-b border-zinc-800/30 last:border-0 transition-colors hover:bg-zinc-800/10">
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-3 py-2.5 text-left sm:px-4 sm:py-3"
      >
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-nowrap items-center gap-x-2 gap-y-0 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              <span className="shrink-0 font-mono text-[10px] text-zinc-600">
                #{b.bounty_id}
              </span>
              {b.reward && (
                <span className="shrink-0 whitespace-nowrap text-[10px] text-emerald-500/80 tabular-nums">
                  {b.reward}
                </span>
              )}
              <span className="shrink-0 whitespace-nowrap text-[10px] text-zinc-600">{bidSummary}</span>
              {b.deposit_tx && (
                <a
                  href={`https://sepolia.basescan.org/tx/${b.deposit_tx}`}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0 font-mono text-[9px] text-sky-500/70 underline hover:text-sky-400"
                >
                  ↗ deposit
                </a>
              )}
              {b.payment_tx && (
                <a
                  href={b.payment_tx}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0 font-mono text-[9px] text-emerald-500/70 underline hover:text-emerald-400"
                >
                  ↗ paid
                </a>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            <span
              className={`shrink-0 rotate-[-8deg] whitespace-nowrap rounded border-2 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider sm:text-[9px] ${STAMP_STYLE[b.status]}`}
            >
              {b.status}
            </span>
            <span className="shrink-0 text-[10px] text-zinc-600">{expanded ? "▼" : "▶"}</span>
          </div>
        </div>

        <p
          className={`mt-2 text-sm leading-snug text-zinc-200 ${
            expanded ? "" : "line-clamp-2"
          }`}
        >
          {b.task}
        </p>
      </button>

      {expanded && (
        <div className="space-y-2 px-3 pb-3 sm:px-4">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void shareBountyLink(b)}
              className="rounded-md border border-zinc-700/60 bg-zinc-900/50 px-2.5 py-1 text-[10px] text-zinc-400 transition-colors hover:border-emerald-500/30 hover:text-emerald-300"
            >
              Share
            </button>
          </div>
          {b.bids.length > 0 && (
            <div>
              <p className="text-[9px] uppercase tracking-[0.18em] text-zinc-600 mb-1">Bids</p>
              <div className="space-y-0.5">
                {b.bids.map((bid, i) => (
                  <div key={bid.node_key} className="flex items-center justify-between">
                    <span
                      className={`flex items-center gap-1.5 text-xs ${bid.outcome === "rejected" ? "line-through text-zinc-600" : "text-zinc-300"}`}
                    >
                      <span className="text-zinc-500">{GLYPH_LIST[i % GLYPH_LIST.length]}</span>
                      {bid.specialty}
                    </span>
                    <span
                      className={`font-mono text-[9px] ${
                        bid.outcome === "awarded"
                          ? "text-emerald-400"
                          : bid.outcome === "rejected"
                          ? "text-zinc-600"
                          : "text-sky-400/70"
                      }`}
                    >
                      {bid.outcome === "awarded"
                        ? "awarded"
                        : bid.outcome === "rejected"
                        ? "stood down"
                        : "bid"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(b.result || (b.images && b.images.length > 0)) && (
            <div className="bg-zinc-950/60 rounded-xl border border-zinc-800/40 p-2.5 space-y-1.5">
              {b.collaboration && (
                <span className="inline-flex items-center gap-1 rounded-full border border-violet-500/20 bg-violet-500/8 px-2 py-0.5 text-[9px] font-medium text-violet-400/80">
                  ⬡ collaborative result
                </span>
              )}
              {b.images && b.images.length > 0 && (
                <div className="flex flex-col gap-2">
                  {b.images.map((img, idx) => {
                    const src = `data:${img.mime};base64,${img.data_base64}`;
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onImageClick?.(src);
                        }}
                        className="group/img block w-full overflow-hidden rounded-xl border border-zinc-700/50 bg-zinc-900/40 text-left transition hover:border-emerald-500/35 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element -- data URLs from worker */}
                        <img
                          src={src}
                          alt=""
                          className="max-h-[min(38vh,14rem)] w-full object-contain transition group-hover/img:brightness-105"
                        />
                      </button>
                    );
                  })}
                </div>
              )}
              {b.result && (
                <BountyResultMarkdown text={b.result} onImageClick={onImageClick} />
              )}
            </div>
          )}

          {b.status === "UNCLAIMED" && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRepost(b);
              }}
              className="text-[10px] text-amber-500 transition-colors hover:text-amber-400"
            >
              ↺ Repost
            </button>
          )}
        </div>
      )}
    </div>
  );
}

type RailTab = "bounties" | "leaderboard";

interface ReputationRow {
  label: string;
  specialty: string;
  eth_address: string;
  completed_onchain: number;
  total_eth_wei: number;
  session_reward_wei: number;
  session_completed: number;
  session_claimed: number;
}

function LeaderboardWorkerCard({ w }: { w: ReputationRow }) {
  const chainWei = Number(w.total_eth_wei);
  const sessionWei = Number(w.session_reward_wei ?? 0);
  const displayWei = chainWei > 0 ? chainWei : sessionWei;
  return (
    <div className="flex min-h-0 min-w-0 flex-col rounded-xl border border-zinc-800/45 bg-zinc-900/40 p-2.5 shadow-sm transition-colors hover:border-zinc-700/50">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="line-clamp-1 text-xs font-medium leading-tight text-zinc-200">{w.label}</p>
          <p className="mt-0.5 line-clamp-1 text-[10px] leading-snug text-zinc-500">{w.specialty}</p>
        </div>
        <span className="shrink-0 text-right font-mono text-[10px] tabular-nums text-emerald-400">
          <span>{(displayWei / 1e18).toFixed(4)}</span>
          <span className="text-zinc-600"> ETH</span>
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-2 gap-y-0.5 font-mono text-[9px] text-zinc-500">
        <span>{w.completed_onchain} chain</span>
        <span>{w.session_completed} session</span>
        {w.session_claimed > 0 && (
          <span>{Math.round((w.session_completed / w.session_claimed) * 100)}% wins</span>
        )}
      </div>
      <p className="mt-1 truncate font-mono text-[8px] text-zinc-700">{w.eth_address || "—"}</p>
    </div>
  );
}

function AuctionBountyRail({
  defaultBox,
  maxPanelWidth,
  maxPanelHeight,
  bounties,
  onRepost,
  onClear,
  expandedId,
  setExpandedId,
  repRefreshTick,
  onImageClick,
}: {
  defaultBox: PanelBox;
  maxPanelWidth: number;
  maxPanelHeight: number;
  bounties: BountyCard[];
  onRepost: (b: BountyCard) => void;
  onClear: () => void;
  expandedId: string | null;
  setExpandedId: React.Dispatch<React.SetStateAction<string | null>>;
  repRefreshTick: number;
  onImageClick: (dataUrl: string) => void;
}) {
  const [railTab, setRailTab] = useState<RailTab>("bounties");
  const [repByNode, setRepByNode] = useState<Record<string, ReputationRow>>({});
  const [repLoading, setRepLoading] = useState(false);

  const loadReputation = useCallback(() => {
    setRepLoading(true);
    fetch(`${API}/api/reputation`)
      .then((r) => r.json())
      .then((data: Record<string, ReputationRow>) => setRepByNode(data || {}))
      .catch(() => setRepByNode({}))
      .finally(() => setRepLoading(false));
  }, []);

  useEffect(() => {
    if (!repRefreshTick) return;
    queueMicrotask(() => {
      loadReputation();
    });
  }, [repRefreshTick, loadReputation]);

  const repEntries = Object.entries(repByNode);

  return (
    <FloatingPanel
      defaultBox={defaultBox}
      minWidth={260}
      minHeight={200}
      maxWidth={maxPanelWidth}
      maxHeight={maxPanelHeight}
      zIndex={10}
      dragHeader={
        <div className="flex w-full flex-col gap-2">
          <div className="flex rounded-lg border border-zinc-800/60 bg-zinc-950/80 p-0.5">
            <button
              type="button"
              onClick={() => setRailTab("bounties")}
              className={`flex-1 rounded-md px-2 py-1 text-[10px] font-medium uppercase tracking-wider transition-colors ${
                railTab === "bounties"
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              Bounties
            </button>
            <button
              type="button"
              onClick={() => {
                setRailTab("leaderboard");
                loadReputation();
              }}
              className={`flex-1 rounded-md px-2 py-1 text-[10px] font-medium uppercase tracking-wider transition-colors ${
                railTab === "leaderboard"
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              Leaderboard
            </button>
          </div>
          {railTab === "bounties" && bounties.length > 0 && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClear}
                className="text-[10px] text-zinc-700 transition-colors hover:text-red-400"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      }
    >
      {railTab === "bounties" ? (
        bounties.length === 0 ? (
          <div className="flex flex-1 items-center justify-center px-4 py-6">
            <p className="text-xs text-zinc-600 text-center">
              No bounties yet. Post one below.
            </p>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar]:w-1">
            {bounties.map((b) => (
              <AuctionBountyCard
                key={b.bounty_id}
                b={b}
                expanded={expandedId === b.bounty_id}
                onToggle={() =>
                  setExpandedId((id) => (id === b.bounty_id ? null : b.bounty_id))
                }
                onRepost={onRepost}
                onImageClick={onImageClick}
              />
            ))}
          </div>
        )
      ) : repLoading ? (
        <div className="flex flex-1 items-center justify-center px-4 py-6">
          <p className="text-xs text-zinc-600">Loading reputation…</p>
        </div>
      ) : repEntries.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-4 py-6">
          <p className="text-xs text-zinc-600 text-center">
            No on-chain data yet.
          </p>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 auto-rows-max grid-cols-[repeat(auto-fill,minmax(min(100%,11.5rem),1fr))] gap-2 overflow-y-auto p-2 content-start [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar]:w-1">
          {repEntries.map(([nodeKey, w]) => (
            <LeaderboardWorkerCard key={nodeKey} w={w} />
          ))}
        </div>
      )}
    </FloatingPanel>
  );
}

// ── Home ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const [task, setTask] = useState("");
  const [rewardEth, setRewardEth] = useState("0.01");
  const [submitting, setSubmitting] = useState(false);
  const [selectedTpl, setSelectedTpl] = useState<string | null>(null);
  const [catFilter, setCatFilter] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // ── Wallet ────────────────────────────────────────────────────────────────
  const { address, isConnected } = useAccount();
  const { connect, error: connectError } = useConnect();
  const { disconnect } = useDisconnect();
  const { data: balance } = useBalance({ address });
  const { writeContractAsync } = useWriteContract();
  const publicClient = usePublicClient();
  const [pendingTxHash, setPendingTxHash] = useState<`0x${string}` | undefined>();
  const { isLoading: isTxConfirming } = useWaitForTransactionReceipt({ hash: pendingTxHash });
  const [selectedInsightWorker, setSelectedInsightWorker] = useState<
    string | null
  >(null);
  const [telemetryEnabled, setTelemetryEnabled] = useState<boolean | null>(null);
  const [walletUiReady, setWalletUiReady] = useState(false);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  /** Remount `react-rnd` once real viewport is known (`default` only applies on mount). */
  const [panelMountKey, setPanelMountKey] = useState(0);

  const vp = useViewport();

  const workerKeysRef = useRef<string[]>([]);
  const { meshPackets, spawnTrain } = useMeshAnimation(workerKeysRef);

  const {
    bounties,
    setBounties,
    nodes,
    logs,
    sseConnected,
    workerInsights,
    meshWorkers,
    connectedWorkers,
    repRefreshTick,
    setRepRefreshTick,
    logsEndRef,
  } = useBountyStream(API, spawnTrain, setExpandedId, workerKeysRef);

  useLayoutEffect(() => {
    setPanelMountKey(1);
  }, []);

  const {
    activityPanelBox,
    bountyRailBox,
    broadcastPanelBox,
    panelBounds,
  } = useMemo(() => computePanelLayout(vp), [vp.w, vp.h]);

  useEffect(() => {
    queueMicrotask(() => setWalletUiReady(true));
  }, []);

  const panelInsight: InsightPayload | null = useMemo(() => {
    if (!selectedInsightWorker) return null;
    const x = workerInsights[selectedInsightWorker];
    return {
      toolText: x?.toolText ?? "",
      modelText: x?.modelText ?? "",
      phase: x?.phase ?? "idle",
      bountyId: x?.bountyId,
      specialty: x?.specialty,
    };
  }, [selectedInsightWorker, workerInsights]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/api/telemetry/status`)
      .then((r) => r.json())
      .then((body: { enabled?: boolean }) => {
        if (!cancelled) setTelemetryEnabled(Boolean(body.enabled));
      })
      .catch(() => {
        if (!cancelled) setTelemetryEnabled(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const submitBounty = async (e: React.FormEvent, overrideTask?: string, overrideRewardEth?: string) => {
    e.preventDefault();
    const t = overrideTask ?? task;
    const ethAmount = overrideRewardEth ?? rewardEth;
    if (!t.trim() || !isConnected || !address) return;
    setSubmitting(true);
    try {
      const bountyId = crypto.randomUUID().replace(/-/g, "").slice(0, 8);
      const bountyIdBytes32 = keccak256(toBytes(bountyId));
      const rewardWei = parseEther(ethAmount || "0");

      // Step 1: send escrow deposit — MetaMask will pop up
      const hash = await writeContractAsync({
        address: CONTRACT_ADDRESS,
        abi: BOUNTY_ESCROW_ABI,
        functionName: "postBounty",
        args: [bountyIdBytes32],
        value: rewardWei,
      });
      setPendingTxHash(hash);

      // Step 2: wait for on-chain confirmation before notifying the backend
      if (publicClient) {
        await publicClient.waitForTransactionReceipt({ hash, confirmations: 1 });
      }

      // Step 3: notify backend — bounty is now funded on-chain
      await fetch(`${API}/api/bounty`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task: t,
          reward: `${ethAmount} ETH`,
          reward_wei: Number(rewardWei),
          tx_hash: hash,
          poster_address: address,
          bounty_id: bountyId,
        }),
      });
      if (!overrideTask) setTask("");
    } catch (err) {
      console.error("submitBounty error:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const repostBounty = (b: BountyCard) =>
    submitBounty({ preventDefault: () => {} } as React.FormEvent, b.task, rewardEth);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#080809] text-zinc-100">
      {/* Layer 0: Full-screen mesh canvas */}
      <MeshFlowMap
        emitter={nodes.emitter}
        workers={meshWorkers}
        agentStates={nodes}
        meshPackets={meshPackets}
        selectedWorkerKey={selectedInsightWorker}
        onWorkerSelect={setSelectedInsightWorker}
        insight={panelInsight}
        telemetryEnabled={telemetryEnabled}
        sseConnected={sseConnected}
      />

      {/* Layer z-10: Header */}
      <header className="fixed top-0 left-0 right-0 z-10 flex min-h-[4.25rem] items-center justify-between border-b border-emerald-950/30 px-5 py-3 sm:px-8 backdrop-blur-md bg-zinc-950/75 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.65)]">
        <div className="flex items-center gap-3 sm:gap-4">
          <span
            className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-emerald-400/40 bg-gradient-to-br from-emerald-500/25 to-teal-600/10 text-xl text-emerald-300 shadow-[0_0_28px_-6px_rgba(52,211,153,0.55)] ring-1 ring-emerald-400/15"
            aria-hidden
          >
            ⬡
          </span>
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="font-display text-2xl font-bold leading-none tracking-tight sm:text-3xl md:text-[2.125rem] bg-gradient-to-r from-emerald-100 via-teal-100 to-emerald-300 bg-clip-text text-transparent [text-shadow:0_0_40px_rgba(52,211,153,0.18)]">
              AgenC
            </span>
            <span className="max-w-[min(100vw-10rem,26rem)] text-[11px] font-medium leading-snug tracking-wide text-zinc-400 sm:text-xs md:text-[13px]">
              AI agents bid, collaborate &amp; get paid on-chain
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {!walletUiReady ? (
            <div
              className="h-[34px] min-w-[152px] rounded-lg border border-zinc-800/40 bg-zinc-900/60"
              aria-hidden
            />
          ) : isConnected && address ? (
            <button
              type="button"
              onClick={() => disconnect()}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-800/60 bg-zinc-900/80 px-3 py-1 text-[10px] font-mono text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              {address.slice(0, 6)}…{address.slice(-4)}
              {balance && (
                <span className="text-zinc-500">· {parseFloat(balance.formatted).toFixed(4)} ETH</span>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => connect({ connector: injected() })}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-700/60 bg-zinc-900/80 px-3 py-1 text-[10px] font-mono text-zinc-400 transition-colors hover:border-emerald-500/40 hover:text-emerald-400"
              title={connectError?.message}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-zinc-600" />
              {connectError ? "⚠ " + connectError.message.slice(0, 30) : "Connect Wallet"}
            </button>
          )}
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
            <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">live</span>
          </div>
        </div>
      </header>

      {/* Layer z-10: Activity timeline (left) */}
      <FloatingPanel
        key={`activity-${panelMountKey}`}
        defaultBox={activityPanelBox}
        minWidth={220}
        minHeight={180}
        maxWidth={panelBounds.sidePanelMaxW}
        maxHeight={panelBounds.maxPanelH}
        zIndex={10}
        dragHeader={
          <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-500">
            Activity
          </span>
        }
      >
        <ActivityTimeline logs={logs} logsEndRef={logsEndRef} />
      </FloatingPanel>

      {/* Layer z-10: Bounty rail (right) */}
      <AuctionBountyRail
        key={`rail-${panelMountKey}`}
        defaultBox={bountyRailBox}
        maxPanelWidth={panelBounds.sidePanelMaxW}
        maxPanelHeight={panelBounds.maxPanelH}
        bounties={bounties}
        expandedId={expandedId}
        setExpandedId={setExpandedId}
        onRepost={repostBounty}
        repRefreshTick={repRefreshTick}
        onImageClick={setLightboxSrc}
        onClear={async () => {
          await fetch(`${API}/api/bounties`, { method: "DELETE" });
          setBounties([]);
        }}
      />

      {/* Layer z-30: Broadcast — draggable / resizable */}
      <FloatingPanel
        key={`broadcast-${panelMountKey}`}
        defaultBox={broadcastPanelBox}
        minWidth={320}
        minHeight={200}
        maxWidth={panelBounds.maxPanelW}
        maxHeight={panelBounds.maxPanelH}
        zIndex={30}
        dragHeader={
          <div className="flex w-full min-w-0 items-start justify-between gap-2">
            <p className="text-[9px] font-medium uppercase tracking-[0.2em] text-zinc-500">
              Broadcast
            </p>
            <p className="hidden text-[9px] text-zinc-600 sm:block sm:truncate">
              Base Sepolia · pick a template or write below
            </p>
          </div>
        }
      >
        <div className="@container flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3 pt-0">
          <form onSubmit={submitBounty} className="flex min-h-0 flex-1 flex-col gap-2.5">

            {/* Category filter pills */}
            <div className="flex gap-1 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {TEMPLATE_CATS.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setCatFilter(cat.id)}
                  className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[10px] font-medium transition-colors ${
                    catFilter === cat.id
                      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                      : "border-zinc-800/60 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                  }`}
                >
                  {cat.label}
                </button>
              ))}
            </div>

            {/* Template strip — single horizontal scrollable row */}
            <div className="flex gap-1.5 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {TEMPLATES.filter(
                (t) => catFilter === "all" || t.tags.includes(catFilter),
              ).map((tpl) => {
                const active = selectedTpl === tpl.label;
                return (
                  <button
                    key={tpl.label}
                    type="button"
                    title={tpl.task}
                    onClick={() => {
                      setTask(tpl.task);
                      setRewardEth(tpl.reward);
                      setSelectedTpl(tpl.label);
                    }}
                    className={`group flex w-32 shrink-0 flex-col gap-1.5 rounded-xl border px-2.5 py-2 text-left transition-all ${
                      active
                        ? "border-emerald-500/40 bg-emerald-500/5 shadow-[0_0_14px_-6px_rgba(16,185,129,0.35)]"
                        : "border-zinc-800/60 bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-1">
                      <span className="text-[11px] font-semibold leading-tight text-zinc-100">
                        {tpl.label}
                      </span>
                    </div>
                    <div className="mt-auto flex items-center justify-between gap-1">
                      <div className="flex flex-wrap gap-1">
                        {tpl.tags.slice(0, 2).map((tag) => (
                          <span
                            key={tag}
                            className={`rounded border px-1 py-0.5 text-[8px] font-medium leading-none ${TAG_COLORS[tag] ?? ""}`}
                          >
                            {tag}
                          </span>
                        ))}
                        {tpl.tags.length > 2 && (
                          <span className="text-[8px] text-zinc-600">+{tpl.tags.length - 2}</span>
                        )}
                      </div>
                      <span className="shrink-0 font-mono text-[9px] text-zinc-500">
                        {tpl.reward}Ξ
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Divider */}
            <div className="relative flex items-center gap-2">
              <div className="h-px flex-1 bg-zinc-800/60" />
              <span className="text-[9px] text-zinc-600">or describe your own</span>
              <div className="h-px flex-1 bg-zinc-800/60" />
            </div>

            {/* Task textarea */}
            <textarea
              className="max-h-[min(40vh,10rem)] min-h-[3rem] w-full flex-1 resize-y rounded-lg border border-zinc-800/60 bg-zinc-950/60 px-3 py-2 text-sm leading-snug text-zinc-100 placeholder-zinc-600 transition-colors focus:border-zinc-600 focus:outline-none"
              rows={2}
              value={task}
              onChange={(e) => {
                setTask(e.target.value);
                if (selectedTpl) setSelectedTpl(null);
              }}
              placeholder="Describe the task…"
              required
            />

            {/* Bottom row: reward + submit */}
            <div className="flex shrink-0 items-center gap-2">
              <div className="relative w-28 shrink-0">
                <input
                  type="number"
                  step="0.001"
                  min="0.001"
                  className="w-full rounded-lg border border-zinc-800/60 bg-zinc-950/60 px-3 py-1.5 pr-9 text-sm text-zinc-100 transition-colors focus:border-zinc-600 focus:outline-none"
                  value={rewardEth}
                  onChange={(e) => setRewardEth(e.target.value)}
                  placeholder="0.01"
                  required
                />
                <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 font-mono text-[9px] text-zinc-500">
                  Ξ
                </span>
              </div>
              <button
                type="submit"
                disabled={submitting || isTxConfirming || !walletUiReady || !isConnected}
                className="ml-auto w-full shrink-0 rounded-lg bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-zinc-950 transition-colors hover:bg-emerald-400 active:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50 @[380px]:w-auto"
              >
                {submitting ? "Sending…" : isTxConfirming ? "Confirming…" : "⛓ Broadcast"}
              </button>
            </div>

            {(!walletUiReady || !isConnected) && (
              <p className="text-[9px] leading-tight text-amber-600/80">
                Connect wallet to broadcast
              </p>
            )}
          </form>
        </div>
      </FloatingPanel>

      <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />

    </div>
  );
}
