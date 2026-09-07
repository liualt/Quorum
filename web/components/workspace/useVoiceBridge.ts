"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import type { VoiceUiStatus } from "@/components/interview/MicControls";
import { reportTranscript, startInterview } from "@/lib/api";
import type { JoinView } from "@/lib/types";
import type {
  AgentActivity,
  LiveCaption,
  VoiceControls,
  VoiceHandlers,
  VoiceJoin,
} from "@/lib/voice";

import { errorMessage } from "./errorMessage";

/**
 * The workspace's side of the voice session.
 *
 * `VoicePanel` owns the Agora objects; this owns what the page shows about
 * them (status, captions in flight, the agent's activity), the join data that
 * mounts the panel, and the disconnect recovery. It never imports an Agora
 * package.
 */
export function useVoiceBridge(
  interviewId: string,
  /** Pauses or resumes the interview on the server; a disconnect pauses (PRD §9). */
  setPaused: (paused: boolean) => Promise<void>,
) {
  const [join, setJoin] = useState<VoiceJoin | null>(null);
  const [status, setStatus] = useState<VoiceUiStatus>("text");
  const [note, setNote] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [agentActivity, setAgentActivity] = useState<AgentActivity | null>(null);
  const [liveCaptions, setLiveCaptions] = useState<LiveCaption[]>([]);
  const [reconnecting, setReconnecting] = useState(false);
  const controlsRef = useRef<VoiceControls | null>(null);

  /** Leave the channel (unmounting the panel is the leave) and show text mode. */
  const drop = useCallback(() => {
    setJoin(null);
    setStatus("text");
    setLiveCaptions([]);
    setAgentActivity(null);
  }, []);

  /** Apply what `/start` answered, given what the candidate asked for. */
  const applyJoin = useCallback((voice: JoinView, withVoice: boolean) => {
    if (withVoice && voice.enabled) {
      setJoin(voice);
      setStatus("connecting");
      setNote(null);
      return;
    }
    setJoin(null);
    setStatus("text");
    setNote(
      !withVoice || voice.enabled
        ? null
        : voice.reason
          ? `Voice could not start: ${voice.reason}. Continuing in text.`
          : "Voice is not available on this server. Continuing in text.",
    );
  }, []);

  const handlers = useMemo<VoiceHandlers>(
    () => ({
      onConnection: (connection) => {
        setStatus(connection);
        if (connection === "disconnected") {
          setLiveCaptions([]);
          setAgentActivity(null);
          void setPaused(true);
        }
      },
      onCaptions: setLiveCaptions,
      onAgentTurn: ({ turnId, text, status: turnStatus }) => {
        reportTranscript(interviewId, "agent", turnStatus, text, turnId).catch(() => {
          // The segment already exists from the model endpoint; a missed
          // spoken-text update leaves the written text, which is still true.
        });
      },
      onAgentActivity: setAgentActivity,
      onError: setNote,
    }),
    [interviewId, setPaused],
  );

  const onControls = useCallback((controls: VoiceControls | null) => {
    controlsRef.current = controls;
  }, []);

  const reconnect = useCallback(async () => {
    setReconnecting(true);
    setJoin(null);
    setNote(null);
    try {
      const { voice } = await startInterview(interviewId);
      if (voice.enabled) {
        setJoin(voice);
        setStatus("connecting");
      } else {
        drop();
        setNote(
          voice.reason
            ? `Voice could not reconnect: ${voice.reason}. Continuing in text.`
            : "Voice could not reconnect. Continuing in text.",
        );
      }
      await setPaused(false);
    } catch (cause) {
      setNote(errorMessage(cause, "Could not reconnect. Try again, or continue with text."));
    } finally {
      setReconnecting(false);
    }
  }, [drop, interviewId, setPaused]);

  const continueWithText = useCallback(async () => {
    drop();
    await setPaused(false);
  }, [drop, setPaused]);

  const toggleMute = useCallback(() => setMuted((value) => !value), []);

  /** Send typed text to the agent. False when voice is not connected. */
  const trySend = useCallback(
    async (text: string): Promise<boolean> => {
      if (status !== "connected" || !controlsRef.current) return false;
      await controlsRef.current.sendText(text);
      return true;
    },
    [status],
  );

  return {
    join,
    status,
    note,
    muted,
    agentActivity,
    liveCaptions,
    reconnecting,
    handlers,
    onControls,
    applyJoin,
    drop,
    reconnect,
    continueWithText,
    toggleMute,
    trySend,
  };
}
