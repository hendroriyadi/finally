import type { ConnectionStatus } from "@/lib/types";

interface ConnectionStatusDotProps {
  status: ConnectionStatus;
}

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connected: "Connected",
  reconnecting: "Reconnecting",
  disconnected: "Disconnected",
};

const STATUS_CLASS: Record<ConnectionStatus, string> = {
  connected: "bg-positive",
  reconnecting: "bg-accent animate-pulse",
  disconnected: "bg-destructive",
};

/**
 * Fixed 8px, no-text-content connection indicator. The only state surface is
 * the color mapping below — overflow and long-text are not applicable
 * (per `01-UI-SPEC.md`).
 */
export function ConnectionStatusDot({ status }: ConnectionStatusDotProps) {
  const label = STATUS_LABEL[status];

  return (
    <span
      role="status"
      aria-label={label}
      title={label}
      className={`inline-block h-2 w-2 rounded-full ${STATUS_CLASS[status]}`}
    />
  );
}
