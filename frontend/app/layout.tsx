import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { AppHeader } from "@/components/AppHeader";
import { PriceStreamProvider } from "@/components/PriceStreamProvider";
import { PortfolioProvider } from "@/components/PortfolioProvider";
import { ChatPanel } from "@/components/ChatPanel";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FinAlly",
  description: "AI-powered trading workstation with live market data and an AI copilot.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="flex h-full min-h-screen flex-col bg-canvas font-sans antialiased">
        <PriceStreamProvider>
          <PortfolioProvider>
            <AppHeader />
            {/* The `min-w-0` on the content wrapper is load-bearing: without
                it a flex child refuses to shrink below its content's
                intrinsic width, and the dashboard would push the dock
                off-screen instead of reflowing. Column below `xl` stacks the
                panel beneath the dashboard in source order — the
                narrow-viewport behaviour, with no second layout to
                maintain. */}
            <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
              <div className="flex min-w-0 flex-1 flex-col">{children}</div>
              <ChatPanel />
            </div>
          </PortfolioProvider>
        </PriceStreamProvider>
      </body>
    </html>
  );
}
