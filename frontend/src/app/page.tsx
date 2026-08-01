"use client";

import { Terminal } from "@/components/Terminal";
import { TerminalProvider } from "@/hooks/useTerminal";

export default function Page() {
  return (
    <TerminalProvider>
      <Terminal />
    </TerminalProvider>
  );
}
