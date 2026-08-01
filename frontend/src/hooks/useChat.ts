"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

let counter = 0;
const nextId = () => `msg-${++counter}`;

export function useChat(onActions: () => void | Promise<void>) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);

  const send = useCallback(
    async (content: string) => {
      setMessages((prev) => [...prev, { id: nextId(), role: "user", content }]);
      setPending(true);
      try {
        const reply = await api.chat(content);
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            content: reply.message,
            trades: reply.trades,
            watchlist_changes: reply.watchlist_changes,
          },
        ]);
        if (reply.trades?.length || reply.watchlist_changes?.length) {
          await onActions();
        }
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            content:
              err instanceof Error ? err.message : "The assistant is unavailable.",
            error: true,
          },
        ]);
      } finally {
        setPending(false);
      }
    },
    [onActions],
  );

  return { messages, pending, send };
}
