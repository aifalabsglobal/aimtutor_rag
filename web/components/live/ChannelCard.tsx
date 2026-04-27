"use client";

import { useEffect, useRef } from "react";

interface ChannelCardProps {
  label: string;
  active: boolean;
  variant: "ai" | "user";
  /**
   * AnalyserNode for live mic waveform. Required for the user channel,
   * ignored for the AI channel (which uses a synthesized waveform driven by
   * ``active``).
   */
  analyser?: AnalyserNode | null;
  statusText?: string;
  icon?: React.ReactNode;
  className?: string;
}

const BAR_COUNT = 32;

export function ChannelCard({
  label,
  active,
  variant,
  analyser,
  statusText,
  icon,
  className = "",
}: ChannelCardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number | null>(null);
  const phaseRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const buffer = analyser ? new Uint8Array(analyser.frequencyBinCount) : null;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const cssColor = (() => {
      const probe = document.createElement("div");
      probe.style.color = `var(--primary)`;
      document.body.appendChild(probe);
      const c = getComputedStyle(probe).color || "rgb(176, 80, 30)";
      probe.remove();
      return c;
    })();

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);

      let amplitudes: number[];
      if (variant === "user" && analyser && buffer) {
        analyser.getByteFrequencyData(buffer);
        amplitudes = new Array(BAR_COUNT);
        const step = Math.floor(buffer.length / BAR_COUNT) || 1;
        for (let i = 0; i < BAR_COUNT; i++) {
          let sum = 0;
          for (let j = 0; j < step; j++) sum += buffer[i * step + j] || 0;
          amplitudes[i] = sum / step / 255;
        }
      } else {
        phaseRef.current += active ? 0.18 : 0.04;
        const intensity = active ? 0.55 : 0.08;
        amplitudes = new Array(BAR_COUNT);
        for (let i = 0; i < BAR_COUNT; i++) {
          const t = i / BAR_COUNT;
          const wave = Math.sin(phaseRef.current + t * 6.28 * 1.5);
          amplitudes[i] = intensity * (0.6 + 0.4 * wave) * (active ? 1 : 0.6);
        }
      }

      const barWidth = w / BAR_COUNT;
      ctx.fillStyle = cssColor;
      ctx.globalAlpha = active ? 1 : 0.45;
      for (let i = 0; i < BAR_COUNT; i++) {
        const amp = Math.max(0.04, Math.min(1, amplitudes[i]));
        const barHeight = amp * h * 0.85;
        const x = i * barWidth + barWidth * 0.15;
        const y = (h - barHeight) / 2;
        const drawWidth = barWidth * 0.7;
        const radius = Math.min(drawWidth / 2, 4);
        if (typeof (ctx as CanvasRenderingContext2D).roundRect === "function") {
          ctx.beginPath();
          (ctx as CanvasRenderingContext2D & {
            roundRect: (
              x: number,
              y: number,
              w: number,
              h: number,
              r: number,
            ) => void;
          }).roundRect(x, y, drawWidth, barHeight, radius);
          ctx.fill();
        } else {
          ctx.fillRect(x, y, drawWidth, barHeight);
        }
      }
      ctx.globalAlpha = 1;

      rafRef.current = requestAnimationFrame(render);
    };

    rafRef.current = requestAnimationFrame(render);

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  }, [active, analyser, variant]);

  return (
    <div
      className={`flex flex-col gap-3 rounded-2xl border border-[var(--border)]/60 bg-[var(--card)]/80 p-5 shadow-sm transition-shadow ${
        active ? "ring-1 ring-[var(--primary)]/40 shadow-md" : ""
      } ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon ? (
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full ${
                active
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "bg-[var(--muted)] text-[var(--muted-foreground)]"
              }`}
              aria-hidden
            >
              {icon}
            </span>
          ) : null}
          <span className="text-[13px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
            {label}
          </span>
        </div>
        <span
          className={`flex items-center gap-1.5 text-[11.5px] font-medium ${
            active ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]"
          }`}
        >
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${
              active ? "bg-[var(--primary)] animate-pulse" : "bg-[var(--muted-foreground)]/40"
            }`}
            aria-hidden
          />
          {statusText}
        </span>
      </div>
      <canvas ref={canvasRef} className="h-24 w-full" aria-hidden />
    </div>
  );
}
