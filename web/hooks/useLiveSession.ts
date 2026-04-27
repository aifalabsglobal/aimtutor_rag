"use client";

/**
 * useLiveSession
 * ==============
 *
 * Owns the WebSocket lifecycle for the live voice tutoring session.
 *
 * Connects to ``/api/v1/ws/live`` via the existing ``wsUrl()`` helper
 * (resolves ``NEXT_PUBLIC_API_BASE`` to ``ws://`` or ``wss://``). The
 * caller passes a ``getToken`` resolver — when Clerk is configured it
 * returns a JWT, otherwise it returns ``"local-dev-user"``.
 *
 * Reconnect strategy mirrors ``web/lib/unified-ws.ts``:
 *   200 ms × 2^n exponential backoff, capped at 5 attempts.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api";
import {
  parseServerFrame,
  type ClientFrame,
  type LiveStatus,
  type ServerFrame,
  type TranscriptEntry,
} from "@/components/live/types";

const HEARTBEAT_TIMEOUT_MS = 75_000;
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY_MS = 200;

export type GetTokenFn = () => Promise<string | null>;

export interface UseLiveSessionParams {
  /** Resolver for the WS auth token. Return null to abort connection. */
  getToken: GetTokenFn;
  /** Notified when a sentence boundary should be queued for TTS. */
  onSentence?: (text: string) => void;
}

export interface UseLiveSessionReturn {
  status: LiveStatus;
  isAISpeaking: boolean;
  transcript: TranscriptEntry[];
  topic: string;
  difficulty: number;
  mastery: Record<string, number>;
  ttftMs: number | null;
  errorMessage: string | null;
  start: () => void;
  stop: () => void;
  interrupt: () => void;
  sendTranscript: (text: string, isFinal: boolean) => void;
  setAISpeaking: (v: boolean) => void;
  pushInterimUserText: (text: string) => void;
}

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function useLiveSession(
  params: UseLiveSessionParams,
): UseLiveSessionReturn {
  const { getToken, onSentence } = params;

  const [status, setStatus] = useState<LiveStatus>("idle");
  const [isAISpeaking, setIsAISpeaking] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [topic, setTopic] = useState("general");
  const [difficulty, setDifficulty] = useState(1);
  const [mastery, setMastery] = useState<Record<string, number>>({});
  const [ttftMs, setTtftMs] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const intentionalCloseRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastReceivedAtRef = useRef(0);
  const onSentenceRef = useRef(onSentence);
  const getTokenRef = useRef(getToken);
  const streamingEntryIdRef = useRef<string | null>(null);
  const connectRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    onSentenceRef.current = onSentence;
  }, [onSentence]);

  useEffect(() => {
    getTokenRef.current = getToken;
  }, [getToken]);

  const sendFrame = useCallback((frame: ClientFrame) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(JSON.stringify(frame));
    } catch {
      /* socket closing — ignore */
    }
  }, []);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const startHeartbeat = useCallback(() => {
    stopHeartbeat();
    heartbeatTimerRef.current = setInterval(() => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      if (Date.now() - lastReceivedAtRef.current > HEARTBEAT_TIMEOUT_MS) {
        ws.close();
      }
    }, 10_000);
  }, [stopHeartbeat]);

  const handleFrame = useCallback(
    (frame: ServerFrame) => {
      switch (frame.type) {
        case "ready":
          setStatus("ready");
          setErrorMessage(null);
          break;
        case "token": {
          const id = streamingEntryIdRef.current;
          if (!id) {
            const newEntry: TranscriptEntry = {
              id: newId(),
              who: "ai",
              text: frame.text,
              isStreaming: true,
            };
            streamingEntryIdRef.current = newEntry.id;
            setTranscript((prev) => [...prev, newEntry]);
          } else {
            setTranscript((prev) =>
              prev.map((e) =>
                e.id === id ? { ...e, text: e.text + frame.text } : e,
              ),
            );
          }
          break;
        }
        case "sentence":
          onSentenceRef.current?.(frame.text);
          break;
        case "done": {
          const id = streamingEntryIdRef.current;
          streamingEntryIdRef.current = null;
          setTtftMs(frame.ttft_ms);
          if (id) {
            setTranscript((prev) =>
              prev.map((e) =>
                e.id === id
                  ? { ...e, isStreaming: false, text: frame.full_text || e.text }
                  : e,
              ),
            );
          }
          break;
        }
        case "meta":
          setTopic(frame.topic);
          setDifficulty(frame.difficulty);
          setMastery(frame.mastery || {});
          break;
        case "error":
          setErrorMessage(frame.message);
          if (!frame.retryable) {
            setStatus("error");
          }
          break;
        case "ping":
          sendFrame({ type: "pong" });
          break;
      }
    },
    [sendFrame],
  );

  const connect = useCallback(async () => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    intentionalCloseRef.current = false;
    setStatus("connecting");
    setErrorMessage(null);

    let token: string | null;
    try {
      token = await getTokenRef.current();
    } catch (err) {
      setStatus("error");
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to get auth token",
      );
      return;
    }
    if (!token) {
      setStatus("error");
      setErrorMessage("Authentication required");
      return;
    }

    const url = `${wsUrl("/api/v1/ws/live")}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptRef.current = 0;
      lastReceivedAtRef.current = Date.now();
      startHeartbeat();
    };

    ws.onmessage = (ev) => {
      lastReceivedAtRef.current = Date.now();
      try {
        const parsed: unknown = JSON.parse(ev.data as string);
        const frame = parseServerFrame(parsed);
        if (frame) handleFrame(frame);
      } catch {
        /* unparseable — ignore */
      }
    };

    ws.onerror = () => {
      setErrorMessage("WebSocket error");
    };

    ws.onclose = (ev) => {
      wsRef.current = null;
      stopHeartbeat();

      if (intentionalCloseRef.current) {
        setStatus("idle");
        return;
      }

      const code = ev.code;
      if (code === 4001) {
        setStatus("error");
        setErrorMessage("Unauthorized — please sign in again.");
        return;
      }
      if (code === 4003) {
        setStatus("error");
        setErrorMessage(
          "Another live session is already active for this account.",
        );
        return;
      }

      if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setStatus("error");
        setErrorMessage("Connection lost — please retry.");
        reconnectAttemptRef.current = 0;
        return;
      }

      const delay =
        BASE_RECONNECT_DELAY_MS * Math.pow(2, reconnectAttemptRef.current);
      reconnectAttemptRef.current += 1;
      setStatus("connecting");
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        void connectRef.current();
      }, delay);
    };
  }, [handleFrame, startHeartbeat, stopHeartbeat]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const start = useCallback(() => {
    void connect();
  }, [connect]);

  const stop = useCallback(() => {
    intentionalCloseRef.current = true;
    clearReconnectTimer();
    stopHeartbeat();
    streamingEntryIdRef.current = null;
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        /* already closed */
      }
      wsRef.current = null;
    }
    setStatus("idle");
  }, [clearReconnectTimer, stopHeartbeat]);

  const interrupt = useCallback(() => {
    sendFrame({ type: "interrupt" });
    streamingEntryIdRef.current = null;
  }, [sendFrame]);

  const sendTranscript = useCallback(
    (text: string, isFinal: boolean) => {
      const cleaned = text.trim();
      if (!cleaned) return;

      if (isFinal) {
        setTranscript((prev) => {
          const filtered = prev.filter((e) => !(e.who === "user" && e.isInterim));
          return [
            ...filtered,
            { id: newId(), who: "user", text: cleaned },
          ];
        });
      }

      sendFrame({
        type: "transcript",
        text: cleaned,
        is_final: isFinal,
        timestamp: Date.now(),
      });
    },
    [sendFrame],
  );

  const pushInterimUserText = useCallback((text: string) => {
    const cleaned = text.trim();
    setTranscript((prev) => {
      const withoutInterim = prev.filter(
        (e) => !(e.who === "user" && e.isInterim),
      );
      if (!cleaned) return withoutInterim;
      return [
        ...withoutInterim,
        { id: newId(), who: "user", text: cleaned, isInterim: true },
      ];
    });
  }, []);

  useEffect(() => {
    return () => {
      intentionalCloseRef.current = true;
      clearReconnectTimer();
      stopHeartbeat();
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
    };
  }, [clearReconnectTimer, stopHeartbeat]);

  return {
    status,
    isAISpeaking,
    transcript,
    topic,
    difficulty,
    mastery,
    ttftMs,
    errorMessage,
    start,
    stop,
    interrupt,
    sendTranscript,
    setAISpeaking: setIsAISpeaking,
    pushInterimUserText,
  };
}
