"use client";

/**
 * useSpeechRecognition
 * ====================
 *
 * Wraps the browser ``SpeechRecognition`` (a.k.a. ``webkitSpeechRecognition``)
 * with continuous + interim-results enabled, plus an ``AnalyserNode`` so the
 * UI can render a live waveform from the user's mic. The two streams share a
 * single ``getUserMedia({ audio: true })`` request so the user sees one
 * permission prompt.
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      length: number;
      0: { transcript: string };
    };
  };
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null;
  onerror: ((ev: Event & { error?: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

interface SpeechRecognitionWindow extends Window {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
}

export interface UseSpeechRecognitionParams {
  language?: string;
  onFinalTranscript: (text: string) => void;
  onInterimTranscript: (text: string) => void;
  onUserStartedSpeaking: () => void;
  /**
   * Treat an interim transcript as final when it has been stable
   * (unchanged) for this many ms. Defaults to 800. Chrome's native
   * ``isFinal`` flip waits for a much longer pause; this shortcut
   * roughly halves perceived input latency.
   * Set to ``0`` to disable and only honor native finals.
   */
  interimStableMs?: number;
}

export interface UseSpeechRecognitionReturn {
  supported: boolean;
  listening: boolean;
  errorMessage: string | null;
  analyser: AnalyserNode | null;
  start: () => Promise<void>;
  stop: () => void;
}

export function useSpeechRecognition(
  params: UseSpeechRecognitionParams,
): UseSpeechRecognitionReturn {
  const {
    language = "en-US",
    onFinalTranscript,
    onInterimTranscript,
    onUserStartedSpeaking,
    interimStableMs = 800,
  } = params;

  const [supported] = useState(() => {
    if (typeof window === "undefined") return false;
    const w = window as SpeechRecognitionWindow;
    return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
  });
  const [listening, setListening] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wantListeningRef = useRef(false);
  const lastInterimAtRef = useRef(0);
  const stableTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastInterimTextRef = useRef("");
  const softFinalizedTextRef = useRef("");

  const onFinalRef = useRef(onFinalTranscript);
  const onInterimRef = useRef(onInterimTranscript);
  const onUserStartedRef = useRef(onUserStartedSpeaking);

  useEffect(() => {
    onFinalRef.current = onFinalTranscript;
  }, [onFinalTranscript]);
  useEffect(() => {
    onInterimRef.current = onInterimTranscript;
  }, [onInterimTranscript]);
  useEffect(() => {
    onUserStartedRef.current = onUserStartedSpeaking;
  }, [onUserStartedSpeaking]);

  const clearStableTimer = useCallback(() => {
    if (stableTimerRef.current) {
      clearTimeout(stableTimerRef.current);
      stableTimerRef.current = null;
    }
  }, []);

  const teardown = useCallback(() => {
    clearStableTimer();
    lastInterimTextRef.current = "";
    softFinalizedTextRef.current = "";
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        /* ignore */
      }
      recognitionRef.current = null;
    }
    if (sourceRef.current) {
      try {
        sourceRef.current.disconnect();
      } catch {
        /* ignore */
      }
      sourceRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }
    setAnalyser(null);
    setListening(false);
  }, [clearStableTimer]);

  const start = useCallback(async () => {
    if (typeof window === "undefined") return;
    const w = window as SpeechRecognitionWindow;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) {
      setErrorMessage("Speech recognition not supported in this browser.");
      return;
    }

    setErrorMessage(null);
    wantListeningRef.current = true;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const AudioCtx: typeof AudioContext =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      const ctx = new AudioCtx();
      audioContextRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;

      const analyserNode = ctx.createAnalyser();
      analyserNode.fftSize = 512;
      analyserNode.smoothingTimeConstant = 0.6;
      source.connect(analyserNode);
      setAnalyser(analyserNode);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Microphone access denied",
      );
      teardown();
      return;
    }

    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = language;
    recognitionRef.current = recognition;

    recognition.onstart = () => setListening(true);
    recognition.onend = () => {
      setListening(false);
      if (wantListeningRef.current && recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch {
          /* will retry on next user action */
        }
      }
    };
    recognition.onerror = (ev) => {
      const code = ev.error;
      if (code && code !== "no-speech" && code !== "aborted") {
        setErrorMessage(`Speech recognition error: ${code}`);
      }
    };

    recognition.onresult = (ev) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const result = ev.results[i];
        const transcript = result[0].transcript;
        if (result.isFinal) {
          const finalText = transcript.trim();
          if (finalText) {
            // Skip if we already soft-finalized this exact text via the
            // interim-stability shortcut below — avoids duplicate sends.
            if (finalText !== softFinalizedTextRef.current) {
              onFinalRef.current(finalText);
            }
            softFinalizedTextRef.current = "";
            lastInterimTextRef.current = "";
            clearStableTimer();
          }
        } else {
          interim += transcript;
        }
      }
      const cleanedInterim = interim.trim();
      if (cleanedInterim) {
        const now = Date.now();
        if (now - lastInterimAtRef.current > 250) {
          lastInterimAtRef.current = now;
          onUserStartedRef.current();
        }
        onInterimRef.current(cleanedInterim);

        if (interimStableMs > 0 && cleanedInterim !== lastInterimTextRef.current) {
          lastInterimTextRef.current = cleanedInterim;
          clearStableTimer();
          stableTimerRef.current = setTimeout(() => {
            stableTimerRef.current = null;
            const stable = lastInterimTextRef.current.trim();
            if (stable && stable !== softFinalizedTextRef.current) {
              softFinalizedTextRef.current = stable;
              onFinalRef.current(stable);
            }
          }, interimStableMs);
        }
      } else {
        onInterimRef.current("");
      }
    };

    try {
      recognition.start();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to start recognition",
      );
      teardown();
    }
  }, [clearStableTimer, interimStableMs, language, teardown]);

  const stop = useCallback(() => {
    wantListeningRef.current = false;
    teardown();
  }, [teardown]);

  useEffect(() => {
    return () => {
      wantListeningRef.current = false;
      teardown();
    };
  }, [teardown]);

  return { supported, listening, errorMessage, analyser, start, stop };
}
