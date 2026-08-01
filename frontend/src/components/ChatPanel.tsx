"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { money, shares } from "@/lib/format";
import type { ChatMessage, TradeAction, WatchlistChange } from "@/lib/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  pending: boolean;
  collapsed: boolean;
  onToggle: () => void;
  onSend: (message: string) => void | Promise<void>;
}

function TradeChip({ trade }: { trade: TradeAction }) {
  const failed = Boolean(trade.failed);
  const buy = trade.side === "buy";
  return (
    <div
      data-testid="trade-chip"
      className={`flex items-center gap-2 border px-2 py-1 ${
        failed
          ? "border-down/50 bg-down/10 text-down"
          : buy
            ? "border-up/50 bg-up/10 text-up"
            : "border-accent/50 bg-accent/10 text-accent"
      }`}
    >
      <span className="font-semibold tracking-widest">
        {trade.side.toUpperCase()}
      </span>
      <span className="tabular-nums">{shares(trade.quantity)}</span>
      <span className="font-semibold">{trade.ticker}</span>
      {trade.price != null && (
        <span className="tabular-nums opacity-80">@ {money(trade.price)}</span>
      )}
      {failed && (
        <span className="ml-auto opacity-90">{trade.error ?? "rejected"}</span>
      )}
    </div>
  );
}

function WatchChip({ change }: { change: WatchlistChange }) {
  return (
    <div
      data-testid="watchlist-chip"
      className="flex items-center gap-2 border border-primary/50 bg-primary/10 px-2 py-1 text-primary"
    >
      <span className="font-semibold tracking-widest">
        {change.action === "add" ? "WATCH +" : "WATCH −"}
      </span>
      <span className="font-semibold">{change.ticker}</span>
      {change.error && <span className="ml-auto text-down">{change.error}</span>}
    </div>
  );
}

export function ChatPanel({
  messages,
  pending,
  collapsed,
  onToggle,
  onSend,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, pending]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || pending) return;
    setDraft("");
    await onSend(text);
  };

  if (collapsed) {
    return (
      <button
        onClick={onToggle}
        aria-label="Open AI assistant"
        className="flex w-9 shrink-0 flex-col items-center gap-3 border border-edge bg-panel py-3 text-slate hover:text-accent"
      >
        <span className="text-accent">✦</span>
        <span
          className="panel-title"
          style={{ writingMode: "vertical-rl" }}
        >
          AI Assistant
        </span>
      </button>
    );
  }

  return (
    <section className="flex w-[360px] shrink-0 flex-col border border-edge bg-panel">
      <header className="flex h-7 shrink-0 items-center justify-between border-b border-edge px-2">
        <h2 className="panel-title">
          <span className="mr-1 text-accent">✦</span> FinAlly Assistant
        </h2>
        <button
          onClick={onToggle}
          aria-label="Collapse AI assistant"
          className="text-slate hover:text-ink"
        >
          ›
        </button>
      </header>

      <div ref={scroller} className="flex-1 space-y-2 overflow-y-auto p-2">
        {messages.length === 0 && (
          <div className="space-y-2 p-2 text-slate">
            <p>
              Ask about your portfolio, request analysis, or have FinAlly trade
              for you.
            </p>
            <ul className="space-y-1 text-slate/80">
              <li>&quot;How is my portfolio concentrated?&quot;</li>
              <li>&quot;Buy 5 shares of NVDA&quot;</li>
              <li>&quot;Add PYPL to my watchlist&quot;</li>
            </ul>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            data-testid={`chat-${message.role}`}
            className="space-y-1"
          >
            <div
              className={`whitespace-pre-wrap border px-2 py-1.5 leading-relaxed ${
                message.role === "user"
                  ? "border-edge bg-raised text-ink"
                  : message.error
                    ? "border-down/50 bg-down/10 text-down"
                    : "border-secondary/50 bg-secondary/10 text-ink"
              }`}
            >
              {message.content}
            </div>
            {message.trades?.map((trade, index) => (
              <TradeChip key={`t-${index}`} trade={trade} />
            ))}
            {message.watchlist_changes?.map((change, index) => (
              <WatchChip key={`w-${index}`} change={change} />
            ))}
          </div>
        ))}

        {pending && (
          <div
            role="status"
            data-testid="chat-loading"
            className="flex items-center gap-2 border border-edge px-2 py-1.5 text-slate"
          >
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            FinAlly is thinking…
          </div>
        )}
      </div>

      <form onSubmit={submit} className="flex gap-1 border-t border-edge p-2">
        <input
          aria-label="Chat message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask FinAlly…"
          className="min-w-0 flex-1 border border-edge bg-base px-2 py-1.5 outline-none placeholder:text-slate/60 focus:border-primary"
        />
        <button
          type="submit"
          disabled={pending}
          className="bg-secondary px-3 py-1.5 font-semibold tracking-widest text-white transition hover:brightness-125 disabled:opacity-40"
        >
          SEND
        </button>
      </form>
    </section>
  );
}
