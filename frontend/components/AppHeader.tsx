import type { ReactNode } from "react";

interface AppHeaderProps {
  children?: ReactNode;
}

/**
 * Terminal header bar: app title on the left, an optional status slot on the
 * right. Phase 3 mounts the connection-status dot in that slot — this
 * component carries no other content (no cash balance, no portfolio value;
 * those belong to Phase 2's UI-03).
 */
export function AppHeader({ children }: AppHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-edge bg-panel px-8 py-4">
      <h1 className="text-xl font-semibold leading-tight">FinAlly</h1>
      {children ? <div className="flex items-center gap-2">{children}</div> : null}
    </header>
  );
}
