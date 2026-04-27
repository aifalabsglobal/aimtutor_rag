"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Mic, MicOff, Sparkles, User as UserIcon } from "lucide-react";
import { ChannelCard } from "./ChannelCard";
import { Transcript } from "./Transcript";
import { useLiveSession, type GetTokenFn } from "@/hooks/useLiveSession";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useTTS } from "@/hooks/useTTS";

export interface LiveSessionProps {
  /** Resolves a WS auth token. Local-dev returns ``"local-dev-user"``. */
  getToken: GetTokenFn;
}

export function LiveSession({ getToken }: LiveSessionProps) {
  const { t } = useTranslation();

  const tts = useTTS({ rate: 1.2 });

  const liveSession = useLiveSession({
    getToken,
    onSentence: (text) => tts.enqueue(text),
  });

  const speech = useSpeechRecognition({
    onFinalTranscript: useCallback(
      (text: string) => {
        tts.cancel();
        liveSession.interrupt();
        liveSession.setAISpeaking(false);
        liveSession.sendTranscript(text, true);
      },
      [liveSession, tts],
    ),
    onInterimTranscript: useCallback(
      (text: string) => {
        liveSession.pushInterimUserText(text);
      },
      [liveSession],
    ),
    onUserStartedSpeaking: useCallback(() => {
      if (tts.speaking) {
        tts.cancel();
        liveSession.interrupt();
        liveSession.setAISpeaking(false);
      }
    }, [liveSession, tts]),
    interimStableMs: 500,
  });

  useEffect(() => {
    liveSession.setAISpeaking(tts.speaking);
  }, [liveSession, tts.speaking]);

  const [hasStarted, setHasStarted] = useState(false);

  const handleStart = useCallback(async () => {
    setHasStarted(true);
    tts.warmup();
    liveSession.start();
    await speech.start();
  }, [liveSession, speech, tts]);

  const handleStop = useCallback(() => {
    setHasStarted(false);
    speech.stop();
    tts.cancel();
    liveSession.stop();
  }, [liveSession, speech, tts]);

  const sortedMastery = useMemo(() => {
    return Object.entries(liveSession.mastery)
      .map(([skill, p]) => [skill, Math.max(0, Math.min(1, p))] as const)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [liveSession.mastery]);

  const connectionLabel = (() => {
    switch (liveSession.status) {
      case "connecting":
        return t("live.statusConnecting");
      case "ready":
        return t("live.statusReady");
      case "error":
        return t("live.statusError");
      default:
        return t("live.statusIdle");
    }
  })();

  const statusDotClass = (() => {
    switch (liveSession.status) {
      case "ready":
        return "bg-emerald-500";
      case "connecting":
        return "bg-amber-500 animate-pulse";
      case "error":
        return "bg-[var(--destructive)]";
      default:
        return "bg-[var(--muted-foreground)]/40";
    }
  })();

  const userActive = speech.listening && (hasStarted || liveSession.status === "ready");
  const aiActive = liveSession.isAISpeaking || tts.speaking;

  const errorBanner = liveSession.errorMessage || speech.errorMessage;

  return (
    <div className="flex h-full flex-col bg-[var(--background)]">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--border)]/60 px-6 py-4">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-[18px] font-semibold tracking-tight text-[var(--foreground)]">
            {t("live.title")}
          </h1>
          <p className="text-[13px] text-[var(--muted-foreground)]">
            {t("live.subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 rounded-full border border-[var(--border)]/60 bg-[var(--card)]/60 px-3 py-1 text-[12px] text-[var(--muted-foreground)]">
            <span className={`h-1.5 w-1.5 rounded-full ${statusDotClass}`} aria-hidden />
            {connectionLabel}
            {liveSession.ttftMs !== null && liveSession.status === "ready" ? (
              <span className="text-[var(--muted-foreground)]/70">
                {`· TTFT ${liveSession.ttftMs}ms`}
              </span>
            ) : null}
          </div>
          {hasStarted ? (
            <button
              type="button"
              onClick={handleStop}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border)]/60 bg-[var(--card)] px-4 py-1.5 text-[13px] font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--muted)]"
            >
              <MicOff size={14} strokeWidth={1.7} />
              {t("live.endSession")}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStart}
              disabled={!speech.supported}
              className="inline-flex items-center gap-2 rounded-full bg-[var(--primary)] px-4 py-1.5 text-[13px] font-medium text-[var(--primary-foreground)] shadow-sm transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-60"
            >
              <Mic size={14} strokeWidth={1.7} />
              {t("live.startSession")}
            </button>
          )}
        </div>
      </header>

      {!speech.supported ? (
        <div className="mx-6 mt-4 rounded-lg border border-[var(--destructive)]/40 bg-[var(--destructive)]/10 px-4 py-2 text-[13px] text-[var(--destructive)]">
          {t("live.unsupported")}
        </div>
      ) : null}

      {errorBanner ? (
        <div className="mx-6 mt-4 rounded-lg border border-[var(--destructive)]/40 bg-[var(--destructive)]/10 px-4 py-2 text-[13px] text-[var(--destructive)]">
          {errorBanner}
        </div>
      ) : null}

      <section className="grid flex-1 gap-4 overflow-hidden p-6 lg:grid-cols-[1fr_1fr_minmax(0,360px)]">
        <ChannelCard
          label={t("live.aiChannel")}
          variant="ai"
          active={aiActive}
          icon={<Sparkles size={14} strokeWidth={1.8} />}
          statusText={
            aiActive ? t("live.speaking") : t("live.idleStatus")
          }
        />
        <ChannelCard
          label={t("live.userChannel")}
          variant="user"
          active={userActive}
          analyser={speech.analyser}
          icon={<UserIcon size={14} strokeWidth={1.8} />}
          statusText={
            speech.listening ? t("live.listening") : t("live.idleStatus")
          }
        />

        <aside className="flex min-h-0 flex-col rounded-2xl border border-[var(--border)]/60 bg-[var(--card)]/80 shadow-sm">
          <div className="flex items-center justify-between border-b border-[var(--border)]/50 px-4 py-3">
            <div>
              <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                {t("live.transcriptHeading")}
              </h2>
              <p className="mt-0.5 text-[11.5px] text-[var(--muted-foreground)]/80">
                {`${liveSession.topic} · L${liveSession.difficulty}`}
              </p>
            </div>
            <button
              type="button"
              onClick={() => liveSession.interrupt()}
              disabled={liveSession.status !== "ready"}
              className="rounded-md border border-[var(--border)]/60 px-2 py-1 text-[11.5px] font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("live.interrupt")}
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <Transcript entries={liveSession.transcript} />
          </div>
          {sortedMastery.length > 0 ? (
            <div className="border-t border-[var(--border)]/50 px-4 py-3">
              <div className="mb-2 text-[11.5px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                {t("live.masteryHeading")}
              </div>
              <ul className="flex flex-col gap-1.5">
                {sortedMastery.map(([skill, p]) => (
                  <li
                    key={skill}
                    className="flex items-center justify-between gap-3 text-[12px] text-[var(--foreground)]"
                  >
                    <span className="truncate">{skill}</span>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--muted)]">
                        <div
                          className="h-full bg-[var(--primary)]"
                          style={{ width: `${Math.round(p * 100)}%` }}
                        />
                      </div>
                      <span className="w-10 text-right tabular-nums text-[var(--muted-foreground)]">
                        {Math.round(p * 100)}%
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </section>
    </div>
  );
}
