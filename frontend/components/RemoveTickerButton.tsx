"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { removeWatchlistTicker, ApiError } from "@/lib/api";

interface RemoveTickerButtonProps {
  ticker: string;
  onRemoved: (ticker: string) => void;
}

/**
 * Per-row remove control. No confirmation dialog anywhere in this component
 * — the UI-SPEC decides that explicitly. The row is only removed after the
 * DELETE succeeds (never optimistically), so client state never silently
 * diverges from the server on a failed delete.
 */
export function RemoveTickerButton({ ticker, onRemoved }: RemoveTickerButtonProps) {
  const [removing, setRemoving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (errorTimerRef.current !== null) {
        clearTimeout(errorTimerRef.current);
      }
    };
  }, []);

  async function handleClick() {
    setRemoving(true);
    setErrorMessage(null);

    try {
      await removeWatchlistTicker(ticker);
      onRemoved(ticker);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(`Couldn't remove ${ticker} — try again.`);
        if (errorTimerRef.current !== null) {
          clearTimeout(errorTimerRef.current);
        }
        errorTimerRef.current = setTimeout(() => {
          setErrorMessage(null);
          errorTimerRef.current = null;
        }, 4000);
      } else {
        throw err;
      }
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="flex flex-col items-end">
      <button
        type="button"
        aria-label={`Remove ${ticker}`}
        onClick={handleClick}
        disabled={removing}
        className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded p-1 focus:outline-none focus:ring-2 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50 md:min-h-0 md:min-w-0 md:p-3"
      >
        {removing ? (
          <Loader2 size={16} className="animate-spin text-destructive" />
        ) : (
          <Trash2 size={16} className="text-destructive" />
        )}
      </button>
      {errorMessage ? (
        <p role="alert" className="text-xs font-normal leading-normal text-destructive">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
