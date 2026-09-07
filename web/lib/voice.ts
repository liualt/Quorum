"use client";

/**
 * The browser side of the voice session: RTC for audio, RTM for messages and
 * presence, and Agora's agent toolkit for captions and agent state.
 *
 * This is the only module in the web app that imports an Agora package. It is
 * reached solely through `components/interview/VoicePanel`, which the
 * workspace loads with `next/dynamic` and `ssr: false`, because the RTC SDK
 * touches `window` at import time. `agora-rtm` is imported lazily here for the
 * same reason.
 *
 * Nothing here talks to the Quorum backend. Final agent turns are handed to
 * the caller once each; the caller decides what to record.
 */

import {
  AgoraVoiceAI,
  AgoraVoiceAIEvents,
  ChatMessagePriority,
  ChatMessageType,
  TranscriptHelperMode,
  TurnStatus,
} from "agora-agent-client-toolkit";
import type { AgentState, AgoraVoiceAIEventHandlers } from "agora-agent-client-toolkit";
import AgoraRTC, {
  AgoraRTCProvider,
  RemoteUser,
  useClientEvent,
  useJoin,
  useLocalMicrophoneTrack,
  usePublish,
  useRemoteUsers,
  useRTCClient,
} from "agora-rtc-react";
import type {
  IAgoraRTCClient,
  IAgoraRTCRemoteUser,
  IMicrophoneAudioTrack,
} from "agora-rtc-react";
import type { RTMClient } from "agora-rtm";
import { useEffect, useMemo, useRef } from "react";

import type { JoinView } from "@/lib/types";

/** The join data the server sends when voice is on. */
export type VoiceJoin = Extract<JoinView, { enabled: true }>;

export type VoiceConnection = "connecting" | "connected" | "disconnected";

/** What the agent is doing, as its presence reports it. */
export type AgentActivity = `${AgentState}`;

/** A caption still being spoken. Shown, never stored. */
export interface LiveCaption {
  turnId: number;
  speaker: "agent" | "candidate";
  text: string;
  time: number;
}

/** An agent turn that finished or was cut off; delivered once per turn. */
export interface FinalAgentTurn {
  turnId: number;
  text: string;
  status: "end" | "interrupted";
}

export interface VoiceHandlers {
  onConnection: (status: VoiceConnection) => void;
  /** The current in-progress captions, complete each time (not a delta). */
  onCaptions: (captions: LiveCaption[]) => void;
  onAgentTurn: (turn: FinalAgentTurn) => void;
  onAgentActivity: (state: AgentActivity) => void;
  onError: (message: string) => void;
}

export interface VoiceControls {
  /** Send typed text to the agent as if spoken, interrupting it if it is talking. */
  sendText: (text: string) => Promise<void>;
  setMuted: (muted: boolean) => Promise<void>;
}

export interface VoiceSession {
  controls: VoiceControls;
  /** Everyone else in the channel — in practice the agent. Render them to hear them. */
  remoteUsers: IAgoraRTCRemoteUser[];
}

export function createRtcClient(): IAgoraRTCClient {
  return AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
}

/** Re-exported so the voice panel never imports an Agora package itself. */
export { AgoraRTCProvider, RemoteUser };

function describe(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

/**
 * Join the voice channel and keep it running until the component unmounts.
 *
 * Leaving is unmounting: the join hook leaves the channel and this hook logs
 * out of RTM and tears the toolkit down in its cleanup. There is no separate
 * `leave` because a second way to end the session would have to be kept in
 * step with the first.
 *
 * Must be rendered inside `AgoraRTCProvider`.
 */
export function useVoice(join: VoiceJoin, handlers: VoiceHandlers): VoiceSession {
  const client = useRTCClient();

  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);

  const agentUid = String(join.agent_uid);

  const joinArgs = useMemo(
    () => ({
      appid: join.app_id,
      channel: join.channel,
      token: join.token,
      uid: join.uid,
    }),
    [join.app_id, join.channel, join.token, join.uid],
  );
  const { isConnected, error: joinError } = useJoin(joinArgs, true, client);
  const { localMicrophoneTrack, error: micError } = useLocalMicrophoneTrack(true);
  usePublish([localMicrophoneTrack], isConnected && localMicrophoneTrack !== null, client);
  const remoteUsers = useRemoteUsers(client);

  /* ------------------------------------------------------------ connection */

  // The channel is only "connected" once the agent is in it too.
  const agentPresent = remoteUsers.some((user) => String(user.uid) === agentUid);
  useEffect(() => {
    if (isConnected && agentPresent) handlersRef.current.onConnection("connected");
  }, [isConnected, agentPresent]);

  useClientEvent(client, "user-left", (user) => {
    if (String(user.uid) === agentUid) handlersRef.current.onConnection("disconnected");
  });

  useClientEvent(client, "connection-state-change", (state, _previous, reason) => {
    if (state === "RECONNECTING") {
      handlersRef.current.onConnection("connecting");
    } else if (state === "DISCONNECTED" && String(reason) !== "LEAVE") {
      // Our own leave is not a disconnect. The reason enum exists only in the
      // SDK's type declarations, so it is compared as the string it is.
      handlersRef.current.onConnection("disconnected");
    }
  });

  useEffect(() => {
    if (!joinError) return;
    handlersRef.current.onError(`Could not join the voice channel: ${joinError.message}`);
    handlersRef.current.onConnection("disconnected");
  }, [joinError]);

  useEffect(() => {
    if (micError) handlersRef.current.onError(`Microphone unavailable: ${micError.message}`);
  }, [micError]);

  /* ------------------------------------------------------------ microphone */

  const trackRef = useRef<IMicrophoneAudioTrack | null>(null);
  const mutedRef = useRef(false);
  useEffect(() => {
    trackRef.current = localMicrophoneTrack;
    // A mute requested before the track existed applies as soon as it does.
    if (localMicrophoneTrack && mutedRef.current) void localMicrophoneTrack.setMuted(true);
  }, [localMicrophoneTrack]);

  useEffect(
    () => () => {
      // Whether or not the track hook releases the device itself, releasing
      // it here guarantees the browser's microphone indicator goes off.
      try {
        trackRef.current?.stop();
        trackRef.current?.close();
      } catch {
        // Already closed.
      }
    },
    [],
  );

  /* ------------------------------------------------------ RTM and toolkit */

  const aiRef = useRef<AgoraVoiceAI | null>(null);
  const reportedTurns = useRef(new Set<number>());

  useEffect(() => {
    let cancelled = false;
    let rtm: RTMClient | null = null;
    let ai: AgoraVoiceAI | null = null;

    const onTranscript: AgoraVoiceAIEventHandlers[AgoraVoiceAIEvents.TRANSCRIPT_UPDATED] = (
      items,
    ) => {
      const live: LiveCaption[] = [];
      for (const item of items) {
        const speaker = item.uid === agentUid ? "agent" : "candidate";
        if (item.status === TurnStatus.IN_PROGRESS) {
          if (item.text) {
            live.push({ turnId: item.turn_id, speaker, text: item.text, time: item._time });
          }
          continue;
        }
        if (speaker !== "agent" || !item.text.trim()) continue;
        if (reportedTurns.current.has(item.turn_id)) continue;
        reportedTurns.current.add(item.turn_id);
        handlersRef.current.onAgentTurn({
          turnId: item.turn_id,
          text: item.text,
          status: item.status === TurnStatus.INTERRUPTED ? "interrupted" : "end",
        });
      }
      handlersRef.current.onCaptions(live);
    };
    const onState: AgoraVoiceAIEventHandlers[AgoraVoiceAIEvents.AGENT_STATE_CHANGED] = (
      _agent,
      event,
    ) => handlersRef.current.onAgentActivity(event.state);
    const onError: AgoraVoiceAIEventHandlers[AgoraVoiceAIEvents.AGENT_ERROR] = (
      _agent,
      error,
    ) => handlersRef.current.onError(`Voice agent error: ${error.message}`);

    const teardown = () => {
      if (ai) {
        ai.off(AgoraVoiceAIEvents.TRANSCRIPT_UPDATED, onTranscript);
        ai.off(AgoraVoiceAIEvents.AGENT_STATE_CHANGED, onState);
        ai.off(AgoraVoiceAIEvents.AGENT_ERROR, onError);
        ai.unsubscribe();
        ai.destroy();
        ai = null;
      }
      rtm?.logout().catch(() => {
        // Logging out of a session that already dropped is not a failure.
      });
      rtm = null;
    };

    (async () => {
      try {
        const { default: AgoraRTM } = await import("agora-rtm");
        // The RTM user id must be the RTC uid as a string: the one token
        // carries both privileges for that identity.
        rtm = new AgoraRTM.RTM(join.app_id, String(join.uid));
        await rtm.login({ token: join.token });
        await rtm.subscribe(join.channel, { withMessage: true, withPresence: true });
        if (cancelled) return teardown();

        ai = await AgoraVoiceAI.init({
          rtcEngine: client,
          rtmEngine: rtm,
          renderMode: TranscriptHelperMode.TEXT,
        });
        if (cancelled) return teardown();

        ai.on(AgoraVoiceAIEvents.TRANSCRIPT_UPDATED, onTranscript);
        ai.on(AgoraVoiceAIEvents.AGENT_STATE_CHANGED, onState);
        ai.on(AgoraVoiceAIEvents.AGENT_ERROR, onError);
        ai.subscribeMessage(join.channel);
        aiRef.current = ai;
      } catch (cause) {
        teardown();
        if (!cancelled) {
          handlersRef.current.onError(`Captions are unavailable: ${describe(cause)}`);
        }
      }
    })();

    return () => {
      cancelled = true;
      aiRef.current = null;
      teardown();
    };
  }, [client, join.app_id, join.channel, join.token, join.uid, agentUid]);

  /* -------------------------------------------------------------- controls */

  const controls = useMemo<VoiceControls>(
    () => ({
      sendText: async (text) => {
        const ai = aiRef.current;
        if (!ai) throw new Error("Voice messaging is not connected yet.");
        await ai.sendText(agentUid, {
          messageType: ChatMessageType.TEXT,
          text,
          priority: ChatMessagePriority.INTERRUPTED,
          responseInterruptable: true,
        });
      },
      setMuted: async (muted) => {
        mutedRef.current = muted;
        await trackRef.current?.setMuted(muted);
      },
    }),
    [agentUid],
  );

  return { controls, remoteUsers };
}
