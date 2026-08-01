import { money, pct, signedMoney, toneClass } from "@/lib/format";
import type { ConnectionState } from "@/lib/types";

const STATUS: Record<ConnectionState, { color: string; label: string }> = {
  connected: { color: "bg-up", label: "LIVE" },
  reconnecting: { color: "bg-accent", label: "RECONNECTING" },
  disconnected: { color: "bg-down", label: "OFFLINE" },
};

interface HeaderProps {
  totalValue: number;
  cash: number;
  pnl: number;
  pnlPct: number;
  connection: ConnectionState;
}

function Stat({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="flex flex-col justify-center border-l border-edge px-4">
      <span className="panel-title">{label}</span>
      <span className={`text-[15px] tabular-nums ${className}`}>{value}</span>
    </div>
  );
}

export function Header({
  totalValue,
  cash,
  pnl,
  pnlPct,
  connection,
}: HeaderProps) {
  const status = STATUS[connection];

  return (
    <header className="flex h-14 shrink-0 items-stretch border-b border-edge bg-raised">
      <div className="flex items-center gap-2.5 px-4">
        <span className="text-[17px] font-bold tracking-[0.18em] text-accent">
          FIN<span className="text-primary">ALLY</span>
        </span>
        <span className="hidden border border-edge px-1.5 py-0.5 text-[9px] tracking-widest text-slate lg:inline">
          AI TRADING WORKSTATION
        </span>
      </div>

      <div className="ml-auto flex items-stretch">
        <Stat label="Total Value" value={money(totalValue)} className="text-accent" />
        <Stat label="Cash" value={money(cash)} />
        <Stat
          label="Unrealized P&L"
          value={`${signedMoney(pnl)}  ${pct(pnlPct)}`}
          className={toneClass(pnl)}
        />
        <div className="flex items-center gap-2 border-l border-edge px-4">
          <span
            data-testid="connection-dot"
            data-state={connection}
            aria-label={`Stream ${connection}`}
            className={`h-2 w-2 rounded-full ${status.color} ${
              connection === "connected" ? "animate-pulse" : ""
            }`}
          />
          <span className="panel-title">{status.label}</span>
        </div>
      </div>
    </header>
  );
}
