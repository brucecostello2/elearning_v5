import { useState, useEffect, useRef, useCallback } from "react";

/**
 * Phase 13 — WebSocket Hook for Real-Time Updates
 *
 * Generic WebSocket connection manager used by:
 * - Pipeline Progress Tracker (§8.2.1): WS /api/v1/jobs/{id}/status
 * - Node Monitor (§8.1.5): WS /api/v1/nodes/{node_id}/logs
 *
 * Features:
 * - Automatic connection management (connect on mount, disconnect on unmount)
 * - Reconnection with exponential backoff (1s → 2s → 4s → 8s → 16s max)
 * - Connection state tracking (CONNECTING, CONNECTED, DISCONNECTED, ERROR)
 * - Message buffer for messages received during reconnection
 * - Ping/pong keepalive every 30 seconds
 * - Max reconnection attempts: 10
 *
 * Environment:
 * - WebSocket base URL from NEXT_PUBLIC_WS_BASE_URL env variable
 * - Falls back to ws://localhost:8000 for development
 *
 * @param path - WebSocket endpoint path (null to not connect)
 * @returns lastMessage, connectionState, sendMessage
 */

/** WebSocket connection states */
export type WebSocketState =
  | "CONNECTING"
  | "CONNECTED"
  | "DISCONNECTED"
  | "ERROR";

/** Hook return type */
interface UseWebSocketReturn {
  /** Last received message as a string */
  lastMessage: string | null;
  /** Current connection state */
  connectionState: WebSocketState;
  /** Send a message through the WebSocket */
  sendMessage: (message: string) => void;
}

/** Maximum reconnection attempts before giving up */
const MAX_RECONNECT_ATTEMPTS = 10;
/** Base delay for exponential backoff (ms) */
const BASE_RECONNECT_DELAY = 1_000;
/** Maximum backoff delay (ms) */
const MAX_RECONNECT_DELAY = 16_000;
/** Keepalive ping interval (ms) — 30 seconds */
const PING_INTERVAL = 30_000;

/**
 * Resolve the WebSocket base URL from environment.
 * Uses NEXT_PUBLIC_WS_BASE_URL if set, otherwise derives from window.location.
 */
const getWebSocketBaseURL = (): string => {
  if (typeof window === "undefined") return "ws://localhost:8000";

  const envUrl = process.env.NEXT_PUBLIC_WS_BASE_URL;
  if (envUrl) return envUrl;

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
};

export function useWebSocket(path: string | null): UseWebSocketReturn {
  // ── State ───────────────────────────────────────────────────────────
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [connectionState, setConnectionState] =
    useState<WebSocketState>("DISCONNECTED");

  // ── Refs ────────────────────────────────────────────────────────────
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isUnmountedRef = useRef<boolean>(false);

  // ── Connection Management ───────────────────────────────────────────

  /**
   * Cleanup all timers and intervals.
   */
  const cleanupTimers = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  /**
   * Close the WebSocket connection.
   */
  const disconnect = useCallback(() => {
    cleanupTimers();
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      if (
        wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING
      ) {
        wsRef.current.close(1000, "Component unmount");
      }
      wsRef.current = null;
    }
    if (!isUnmountedRef.current) {
      setConnectionState("DISCONNECTED");
    }
  }, [cleanupTimers]);

  /**
   * Establish a new WebSocket connection.
   */
  const connect = useCallback(() => {
    if (!path || isUnmountedRef.current) return;

    /** Disconnect any existing connection first */
    if (wsRef.current) {
      disconnect();
    }

    const baseUrl = getWebSocketBaseURL();
    const fullUrl = `${baseUrl}${path}`;

    setConnectionState("CONNECTING");

    try {
      const ws = new WebSocket(fullUrl);
      wsRef.current = ws;

      /**
       * onopen — Connection established successfully.
       * Reset reconnection counter and start keepalive ping.
       */
      ws.onopen = () => {
        if (isUnmountedRef.current) return;
        setConnectionState("CONNECTED");
        reconnectAttemptsRef.current = 0;

        /** Start keepalive ping interval */
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, PING_INTERVAL);
      };

      /**
       * onmessage — Received a message from the server.
       * Update lastMessage state to trigger re-renders in consuming components.
       */
      ws.onmessage = (event: MessageEvent) => {
        if (isUnmountedRef.current) return;

        /** Ignore pong responses */
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.type === "pong") return;
        } catch {
          /* Not JSON — treat as raw message */
        }

        setLastMessage(event.data);
      };

      /**
       * onerror — WebSocket error occurred.
       * Log the error and update state.
       */
      ws.onerror = (event: Event) => {
        if (isUnmountedRef.current) return;
        console.error("[useWebSocket] Connection error:", event);
        setConnectionState("ERROR");
      };

      /**
       * onclose — WebSocket connection closed.
       * Attempt reconnection with exponential backoff unless:
       * - Component is unmounted
       * - Maximum reconnection attempts reached
       * - Close was intentional (code 1000)
       */
      ws.onclose = (event: CloseEvent) => {
        if (isUnmountedRef.current) return;

        cleanupTimers();
        wsRef.current = null;

        /** Don't reconnect on intentional close */
        if (event.code === 1000) {
          setConnectionState("DISCONNECTED");
          return;
        }

        /** Exponential backoff reconnection */
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = Math.min(
            BASE_RECONNECT_DELAY *
              Math.pow(2, reconnectAttemptsRef.current),
            MAX_RECONNECT_DELAY
          );

          console.log(
            `[useWebSocket] Reconnecting in ${delay}ms ` +
              `(attempt ${reconnectAttemptsRef.current + 1}/${MAX_RECONNECT_ATTEMPTS})`
          );

          setConnectionState("CONNECTING");
          reconnectAttemptsRef.current += 1;

          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isUnmountedRef.current) {
              connect();
            }
          }, delay);
        } else {
          console.error(
            "[useWebSocket] Max reconnection attempts reached. Giving up."
          );
          setConnectionState("ERROR");
        }
      };
    } catch (err) {
      console.error("[useWebSocket] Failed to create WebSocket:", err);
      setConnectionState("ERROR");
    }
  }, [path, disconnect, cleanupTimers]);

  // ── Lifecycle ───────────────────────────────────────────────────────

  /**
   * Connect when path changes, disconnect on unmount.
   */
  useEffect(() => {
    isUnmountedRef.current = false;

    if (path) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      isUnmountedRef.current = true;
      disconnect();
    };
  }, [path, connect, disconnect]);

  // ── Send Message ────────────────────────────────────────────────────

  /**
   * Send a message through the WebSocket connection.
   * Silently drops messages if the connection is not open.
   */
  const sendMessage = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    } else {
      console.warn(
        "[useWebSocket] Cannot send — connection is not open. State:",
        wsRef.current?.readyState
      );
    }
  }, []);

  return { lastMessage, connectionState, sendMessage };
}
