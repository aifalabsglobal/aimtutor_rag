/**
 * Live Voice Session — wire types
 *
 * Mirror of the JSON frames defined in
 * `deeptutor/api/routers/live_ws.py`. Plain JSON, never msgpack.
 */

export interface ClientTranscriptFrame {
  type: "transcript";
  text: string;
  is_final: boolean;
  timestamp: number;
}

export interface ClientInterruptFrame {
  type: "interrupt";
}

export interface ClientPongFrame {
  type: "pong";
}

export type ClientFrame =
  | ClientTranscriptFrame
  | ClientInterruptFrame
  | ClientPongFrame;

export interface ServerReadyFrame {
  type: "ready";
  session_id: string;
}

export interface ServerTokenFrame {
  type: "token";
  text: string;
  index: number;
}

export interface ServerSentenceFrame {
  type: "sentence";
  text: string;
}

export interface ServerDoneFrame {
  type: "done";
  full_text: string;
  ttft_ms: number;
}

export interface ServerMetaFrame {
  type: "meta";
  topic: string;
  difficulty: number;
  mastery: Record<string, number>;
}

export interface ServerErrorFrame {
  type: "error";
  message: string;
  retryable: boolean;
}

export interface ServerPingFrame {
  type: "ping";
}

export type ServerFrame =
  | ServerReadyFrame
  | ServerTokenFrame
  | ServerSentenceFrame
  | ServerDoneFrame
  | ServerMetaFrame
  | ServerErrorFrame
  | ServerPingFrame;

/**
 * Type guard — narrow an unknown payload to a `ServerFrame`.
 *
 * Done structurally (no `any`) so consumers can dispatch on `type`.
 */
export function parseServerFrame(value: unknown): ServerFrame | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as { type?: unknown };
  switch (candidate.type) {
    case "ready":
    case "token":
    case "sentence":
    case "done":
    case "meta":
    case "error":
    case "ping":
      return value as ServerFrame;
    default:
      return null;
  }
}

export interface TranscriptEntry {
  id: string;
  who: "ai" | "user";
  text: string;
  isStreaming?: boolean;
  isInterim?: boolean;
}

export type LiveStatus = "idle" | "connecting" | "ready" | "error";
