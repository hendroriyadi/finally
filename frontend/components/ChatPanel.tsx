"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, PanelRightClose, PanelRightOpen, Send } from "lucide-react";
import { ApiError, fetchChatHistory, sendChatMessage } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { usePortfolioContext } from "@/components/PortfolioProvider";
import { ChatActionCard } from "@/components/ChatActionCard";

const SKELETON_ROW_COUNT = 3;
// Roughly four lines of the body scale before the textarea scrolls
// internally — a long pasted draft must never push the send control off
// the panel.
const MAX_INPUT_HEIGHT_PX = 96;

const HISTORY_ERROR = "Couldn't load your conversation — check your connection and reload.";
const SEND_ERROR = "Couldn't reach FinAlly — check your connection and try again.";

/**
 * The docked, collapsible AI Copilot panel.
 *
 * All state is component-local and there is deliberately NO chat context or
 * provider (D-13): this panel is a single subtree with no sibling that needs
 * its data, unlike PortfolioProvider/PriceStreamProvider which each serve
 * several independent consumers spanning the layout and the page. Do not
 * "fix" this by adding a provider.
 *
 * The panel opens no portfolio fetch of its own — after a reply that
 * executed at least one successful action it calls the shared portfolio
 * context's refresh(), so the header, positions table, heatmap, and this
 * transcript all move from one source.
 */
export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const { refresh } = usePortfolioContext();
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchChatHistory()
      .then((history) => {
        if (!cancelled) {
          setMessages(history);
          setHistoryError(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("ChatPanel: failed to load conversation", err);
          setHistoryError(true);
        }
      });

    return () => {
      cancelled = true;
    };
    // Fetch-on-mount, intentionally run once. No lint-disable needed here:
    // this effect closes over no prop or state value, unlike
    // WatchlistPanel's, which does.
  }, []);

  // Keyed on exactly the two moments new content enters the bottom of the
  // transcript — a reply arriving and the thinking row appearing. Scrolling
  // on every render would yank a user who scrolled up to re-read an answer.
  useEffect(() => {
    if (collapsed) {
      return;
    }
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, collapsed]);

  async function submit() {
    const trimmed = draft.trim();
    if (!trimmed || sending) {
      return;
    }

    const userMessage: ChatMessage = {
      role: "user",
      content: trimmed,
      actions: null,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...(current ?? []), userMessage]);
    setDraft("");
    setSendError(null);
    setSending(true);

    try {
      const reply = await sendChatMessage(trimmed);
      setMessages((current) => [
        ...(current ?? []),
        {
          role: "assistant",
          content: reply.message,
          actions: reply.actions,
          created_at: new Date().toISOString(),
        },
      ]);
      if (reply.actions.some((a) => a.status === "success")) {
        await refresh();
      }
    } catch (err) {
      // A failed send never rolls back what the person typed — a message
      // that vanishes reads as data loss rather than as a failed request.
      // The non-ApiError branch matters as much as the ApiError one: an
      // unhandled rejection from a submit handler leaves the spinner
      // stopped and the user with no explanation.
      if (err instanceof ApiError) {
        console.error("ChatPanel: send failed", err.status, err.message);
      } else {
        console.error("ChatPanel: send failed", err);
      }
      setSendError(SEND_ERROR);
    } finally {
      setSending(false);
    }
  }

  function handleInput(event: React.ChangeEvent<HTMLTextAreaElement>) {
    setDraft(event.target.value);
    const el = event.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_HEIGHT_PX)}px`;
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  if (collapsed) {
    // Visually hidden, never unmounted: the message list, the draft, and the
    // scroll position all live in this same component, so re-expanding shows
    // exactly what was there including an unsent draft.
    return (
      <aside className="w-full mx-8 mb-6 shrink-0 rounded-md border border-edge bg-panel transition-all xl:mt-6 xl:mr-8 xl:ml-0 xl:w-14">
        <div className="flex items-center justify-center px-4 py-3">
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            aria-label="Expand chat panel"
            className="rounded p-1 text-[#8b949e] hover:text-[#e6edf3] focus:ring-2 focus:ring-accent focus:outline-none"
          >
            <PanelRightOpen className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex w-full shrink-0 flex-col rounded-md border border-edge bg-panel transition-all xl:w-96">
      <div className="flex items-center justify-between border-b border-edge px-4 py-3">
        <h2 className="text-xl font-semibold leading-tight">AI Copilot</h2>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse chat panel"
          className="rounded p-1 text-[#8b949e] hover:text-[#e6edf3] focus:ring-2 focus:ring-accent focus:outline-none"
        >
          <PanelRightClose className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {historyError ? (
          <div className="text-sm font-normal leading-normal text-destructive">{HISTORY_ERROR}</div>
        ) : messages === null ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: SKELETON_ROW_COUNT }).map((_, index) => (
              <div key={index} className="h-10 w-full animate-pulse rounded bg-edge" />
            ))}
          </div>
        ) : messages.length === 0 ? (
          <div className="py-6">
            <h3 className="text-xl font-semibold leading-tight">Start chatting with FinAlly</h3>
            <p className="mt-1 text-sm font-normal leading-normal text-[#8b949e]">
              Ask about your portfolio, or tell FinAlly to buy, sell, or update your watchlist.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {messages.map((message, index) => {
              const isUser = message.role === "user";
              return (
                <div
                  key={`${message.created_at}-${index}`}
                  className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}
                >
                  <span className="text-xs font-semibold leading-tight text-[#8b949e]">
                    {isUser ? "YOU" : "FINALLY"}
                  </span>
                  <div
                    className={`max-w-[90%] rounded-md border px-3 py-2 text-sm font-normal leading-normal break-words whitespace-pre-wrap ${
                      isUser ? "border-primary/30 bg-primary/15" : "border-edge bg-canvas"
                    }`}
                  >
                    {message.content}
                  </div>
                  {message.actions && message.actions.length > 0 && (
                    <div className="flex w-full flex-col gap-1">
                      {message.actions.map((action, actionIndex) => (
                        <ChatActionCard key={actionIndex} action={action} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {sending && (
          // A status indicator, not a message — never an assistant bubble,
          // and no assistant content is rendered before the real reply.
          <div className="mt-2 flex items-center gap-2 text-xs font-semibold leading-tight text-[#8b949e]">
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
            <span>FinAlly is thinking…</span>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="border-t border-edge p-3">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
          className="flex items-end gap-2"
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={draft}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask FinAlly…"
            className="min-h-9 flex-1 resize-none rounded border border-edge bg-canvas px-3 py-2 text-sm font-normal leading-normal text-[#e6edf3] focus:ring-2 focus:ring-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={sending || draft.trim().length === 0}
            aria-label="Send message"
            className="rounded bg-submit p-2 text-white disabled:opacity-40 focus:ring-2 focus:ring-accent focus:outline-none"
          >
            {sending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </form>
        {sendError && (
          <p role="alert" className="mt-2 text-xs font-semibold leading-tight text-destructive">
            {sendError}
          </p>
        )}
      </div>
    </aside>
  );
}
