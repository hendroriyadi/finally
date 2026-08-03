import { WatchlistPanel } from "@/components/WatchlistPanel";
import { TradeBar } from "@/components/TradeBar";
import { PositionsTable } from "@/components/PositionsTable";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-screen-2xl flex-1 flex-col gap-4 px-8 py-6">
      <TradeBar />
      <PositionsTable />
      <WatchlistPanel />
    </main>
  );
}
