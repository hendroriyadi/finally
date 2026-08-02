"use client";

import { ConnectionStatusDot } from "@/components/ConnectionStatusDot";
import { usePriceStreamContext } from "@/components/PriceStreamProvider";

/**
 * Terminal header bar: app title on the left, connection-status dot on the
 * right, driven by the shared price stream. Carries no other content (no
 * cash balance, no portfolio value; those belong to Phase 2's UI-03).
 */
export function AppHeader() {
  const { status } = usePriceStreamContext();

  return (
    <header className="flex items-center justify-between border-b border-edge bg-panel px-8 py-4">
      <h1 className="text-xl font-semibold leading-tight">FinAlly</h1>
      <div className="flex items-center gap-2">
        <ConnectionStatusDot status={status} />
      </div>
    </header>
  );
}
