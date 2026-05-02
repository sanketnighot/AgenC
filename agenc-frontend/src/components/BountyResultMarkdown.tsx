"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

function safeImageSrc(src: string | undefined): string | null {
  if (!src?.trim()) return null;
  const s = src.trim();
  if (s.startsWith("data:image/")) return s;
  try {
    const u = new URL(s);
    if (u.protocol === "https:" || u.protocol === "http:") return s;
  } catch {
    return null;
  }
  return null;
}

export function BountyResultMarkdown({
  text,
  onImageClick,
}: {
  text: string;
  onImageClick?: (src: string) => void;
}) {
  const components: Components = {
    h1: ({ children }) => (
      <h1 className="mt-3 border-b border-zinc-800/60 pb-1 text-[15px] font-bold leading-snug text-zinc-100 first:mt-0">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="mt-3 text-[14px] font-semibold leading-snug text-zinc-100 first:mt-0">
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="mt-2 text-[13px] font-semibold leading-snug text-zinc-200 first:mt-0">
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="mt-2 text-xs font-semibold text-zinc-200">{children}</h4>
    ),
    p: ({ children }) => (
      <p className="my-2 text-xs leading-relaxed text-zinc-400 first:mt-0 last:mb-0">{children}</p>
    ),
    ul: ({ children }) => (
      <ul className="my-2 list-disc space-y-1 pl-4 text-xs text-zinc-400">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="my-2 list-decimal space-y-1 pl-4 text-xs text-zinc-400">{children}</ol>
    ),
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-2 border-emerald-500/35 bg-zinc-900/40 py-1 pl-3 text-zinc-500">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-3 border-zinc-800/80" />,
    strong: ({ children }) => (
      <strong className="font-semibold text-zinc-200">{children}</strong>
    ),
    em: ({ children }) => <em className="italic text-zinc-300">{children}</em>,
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all text-sky-400 underline decoration-sky-500/40 underline-offset-2 hover:text-sky-300"
      >
        {children}
      </a>
    ),
    table: ({ children }) => (
      <div className="my-2 overflow-x-auto rounded-lg border border-zinc-800/60">
        <table className="w-full border-collapse text-left text-[11px] text-zinc-400">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-zinc-900/80 text-zinc-300">{children}</thead>,
    tbody: ({ children }) => <tbody>{children}</tbody>,
    tr: ({ children }) => <tr className="border-t border-zinc-800/50">{children}</tr>,
    th: ({ children }) => (
      <th className="border border-zinc-800/40 px-2 py-1.5 font-medium">{children}</th>
    ),
    td: ({ children }) => <td className="border border-zinc-800/40 px-2 py-1.5">{children}</td>,
    pre: ({ children }) => (
      <pre className="my-2 overflow-x-auto rounded-lg border border-zinc-800/60 bg-zinc-950/90 p-3 font-mono text-[11px] leading-relaxed text-zinc-300">
        {children}
      </pre>
    ),
    code: ({ className, children }) => {
      const isFence = Boolean(className?.startsWith("language-"));
      if (isFence) {
        return (
          <code className={`${className ?? ""} block whitespace-pre text-[11px]`}>{children}</code>
        );
      }
      return (
        <code className="rounded bg-zinc-800/80 px-1 py-0.5 font-mono text-[11px] text-emerald-200/90">
          {children}
        </code>
      );
    },
    img: ({ src, alt }) => {
      const safe = typeof src === "string" ? safeImageSrc(src) : null;
      if (!safe) {
        return (
          <span className="my-2 block rounded-lg border border-zinc-700/50 bg-zinc-900/50 px-2 py-2 text-[10px] italic text-zinc-500">
            {alt?.trim() ? alt : "[Image URL missing or invalid — paste https or data:image URL in markdown]"}
          </span>
        );
      }
      /* eslint-disable-next-line @next/next/no-img-element -- worker URLs + data URLs */
      const imgEl = (
        <img
          src={safe}
          alt={alt ?? ""}
          className="max-h-[min(38vh,14rem)] w-full rounded-lg border border-zinc-700/50 object-contain transition group-hover/mdimg:brightness-105"
        />
      );
      if (onImageClick) {
        return (
          <button
            type="button"
            className="group/mdimg my-2 block w-full overflow-hidden rounded-xl border border-zinc-700/50 bg-zinc-900/40 text-left transition hover:border-emerald-500/35 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40"
            onClick={(e) => {
              e.stopPropagation();
              onImageClick(safe);
            }}
          >
            {imgEl}
          </button>
        );
      }
      return <span className="my-2 block">{imgEl}</span>;
    },
  };

  return (
    <div className="min-w-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
