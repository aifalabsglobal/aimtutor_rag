"use client";

/**
 * useTTS
 * ======
 *
 * Sentence-level text-to-speech queue backed by ``window.speechSynthesis``.
 * The pipeline streams sentences from the live WS, and each sentence is
 * spoken as it arrives — yielding a "speaks while it thinks" feel.
 *
 * ``cancel()`` flushes the queue immediately (used for user barge-in).
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface UseTTSParams {
  language?: string;
  rate?: number;
  pitch?: number;
  onSpeakingChange?: (speaking: boolean) => void;
}

export interface UseTTSReturn {
  supported: boolean;
  speaking: boolean;
  enqueue: (text: string) => void;
  cancel: () => void;
  /**
   * Eagerly load voices and speak a near-silent utterance so the OS speech
   * engine is initialized. Call once on session start (within a user
   * gesture) to avoid a 200-500 ms cold-start on the first real sentence.
   */
  warmup: () => void;
}

export function useTTS(params: UseTTSParams = {}): UseTTSReturn {
  const { language = "en-US", rate = 1.1, pitch = 1.0, onSpeakingChange } = params;

  const [supported] = useState(
    () => typeof window !== "undefined" && "speechSynthesis" in window,
  );
  const [speaking, setSpeaking] = useState(false);
  const queueRef = useRef<string[]>([]);
  const playingRef = useRef(false);
  const onSpeakingChangeRef = useRef(onSpeakingChange);
  const cancelledRef = useRef(false);
  const playNextRef = useRef<() => void>(() => {});

  useEffect(() => {
    onSpeakingChangeRef.current = onSpeakingChange;
  }, [onSpeakingChange]);

  const setSpeakingState = useCallback((value: boolean) => {
    setSpeaking(value);
    onSpeakingChangeRef.current?.(value);
  }, []);

  const playNext = useCallback(() => {
    if (typeof window === "undefined") return;
    if (playingRef.current) return;

    const next = queueRef.current.shift();
    if (!next) {
      setSpeakingState(false);
      return;
    }

    playingRef.current = true;
    setSpeakingState(true);
    cancelledRef.current = false;

    const utterance = new SpeechSynthesisUtterance(next);
    utterance.lang = language;
    utterance.rate = rate;
    utterance.pitch = pitch;

    utterance.onend = () => {
      playingRef.current = false;
      if (cancelledRef.current) {
        cancelledRef.current = false;
        setSpeakingState(false);
        return;
      }
      playNextRef.current();
    };
    utterance.onerror = () => {
      playingRef.current = false;
      if (cancelledRef.current) {
        cancelledRef.current = false;
        setSpeakingState(false);
        return;
      }
      playNextRef.current();
    };

    try {
      window.speechSynthesis.speak(utterance);
    } catch {
      playingRef.current = false;
      setSpeakingState(false);
    }
  }, [language, pitch, rate, setSpeakingState]);

  useEffect(() => {
    playNextRef.current = playNext;
  }, [playNext]);

  const enqueue = useCallback(
    (text: string) => {
      const cleaned = text.trim();
      if (!cleaned || typeof window === "undefined") return;
      queueRef.current.push(cleaned);
      if (!playingRef.current) playNext();
    },
    [playNext],
  );

  const cancel = useCallback(() => {
    if (typeof window === "undefined") return;
    queueRef.current = [];
    cancelledRef.current = true;
    try {
      window.speechSynthesis.cancel();
    } catch {
      /* ignore */
    }
    playingRef.current = false;
    setSpeakingState(false);
  }, [setSpeakingState]);

  const warmup = useCallback(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    try {
      window.speechSynthesis.getVoices();
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0;
      u.rate = 1.0;
      u.lang = language;
      window.speechSynthesis.speak(u);
    } catch {
      /* warmup is best-effort */
    }
  }, [language]);

  useEffect(() => {
    return () => {
      if (typeof window === "undefined") return;
      queueRef.current = [];
      try {
        window.speechSynthesis.cancel();
      } catch {
        /* ignore */
      }
    };
  }, []);

  return { supported, speaking, enqueue, cancel, warmup };
}
