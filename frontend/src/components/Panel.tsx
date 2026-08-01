import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Panel({
  title,
  actions,
  children,
  className = "",
  bodyClassName = "",
}: PanelProps) {
  return (
    <section
      className={`flex h-full min-h-0 flex-col border border-edge bg-panel ${className}`}
    >
      <header className="flex h-7 shrink-0 items-center justify-between border-b border-edge px-2">
        <h2 className="panel-title">{title}</h2>
        {actions}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
