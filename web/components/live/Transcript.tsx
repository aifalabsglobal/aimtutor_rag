"use client";

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { TranscriptEntry } from "./types";

interface TranscriptProps {
  entries: TranscriptEntry[];
}

export function Transcript({ entries }: TranscriptProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const lastLenRef = useRef(0);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const lengthChanged = entries.length !== lastLenRef.current;
    lastLenRef.current = entries.length;
    const target = lengthChanged ? node.scrollHeight : node.scrollHeight;
    node.scrollTo({ top: target, behavior: lengthChanged ? "smooth" : "auto" });
  }, [entries]);

  if (entries.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-[13.5px] text-[var(--muted-foreground)]">
        {t("live.transcriptEmpty")}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto px-4 py-3"
      role="log"
      aria-live="polite"
    >
      <ol className="flex flex-col gap-2.5">
        {entries.map((entry) => (
          <li
            key={entry.id}
            className={`flex gap-2 text-[13.5px] leading-relaxed ${
              entry.who === "ai"
                ? "text-[var(--foreground)]"
                : "text-[var(--muted-foreground)]"
            }`}
          >
            <span
              className={`shrink-0 select-none font-medium uppercase tracking-wide text-[10.5px] mt-0.5 ${
                entry.who === "ai"
                  ? "text-[var(--primary)]"
                  : "text-[var(--muted-foreground)]"
              }`}
            >
              {entry.who === "ai" ? t("live.ai") : t("live.you")}
            </span>
            <span
              className={`whitespace-pre-wrap ${
                entry.isInterim ? "italic opacity-60" : ""
              }`}
            >
              {entry.text}
              {entry.isStreaming ? (
                <span className="ml-1 inline-block h-3 w-[2px] translate-y-0.5 animate-pulse bg-[var(--primary)]" />
              ) : null}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
