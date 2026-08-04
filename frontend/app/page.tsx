import { WatchlistPanel } from "@/components/WatchlistPanel";
import { TradeBar } from "@/components/TradeBar";
import { PositionsTable } from "@/components/PositionsTable";
import { PortfolioHeatmap } from "@/components/PortfolioHeatmap";
import { PnLChart } from "@/components/PnLChart";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-screen-2xl flex-1 flex-col gap-4 px-8 py-6">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="flex flex-col gap-4">
          <TradeBar />
          <PositionsTable />
          <WatchlistPanel />
        </div>
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <PortfolioHeatmap />
            <PnLChart />
          </div>
        </div>
      </div>
    </main>
  );
}
