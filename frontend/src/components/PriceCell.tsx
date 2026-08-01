"use client";

import { useEffect, useRef, useState } from "react";
import { num } from "@/lib/format";

const FLASH_MS = 500;

interface PriceCellProps {
  price: number | null | undefined;
  className?: string;
}

export function PriceCell({ price, className = "" }: PriceCellProps) {
  const previous = useRef<number | null>(null);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    if (price == null) return;
    const prior = previous.current;
    previous.current = price;
    if (prior == null || prior === price) return;

    setFlash(price > prior ? "up" : "down");
    const timer = window.setTimeout(() => setFlash(null), FLASH_MS);
    return () => window.clearTimeout(timer);
  }, [price]);

  return (
    <span
      data-testid="price-cell"
      className={`flash inline-block rounded-sm px-1 tabular-nums ${
        flash ? `flash-${flash}` : ""
      } ${className}`}
    >
      {num(price)}
    </span>
  );
}
