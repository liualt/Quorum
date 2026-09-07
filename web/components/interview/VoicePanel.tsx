"use client";

import { useEffect, useState } from "react";

import { AgoraRTCProvider, RemoteUser, createRtcClient, useVoice } from "@/lib/voice";
import type { VoiceControls, VoiceHandlers, VoiceJoin } from "@/lib/voice";

interface VoicePanelProps {
  join: VoiceJoin;
  muted: boolean;
  handlers: VoiceHandlers;
  /** Receives the session's controls once they exist, and null when it ends. */
  onControls: (controls: VoiceControls | null) => void;
}

/**
 * Hosts one voice session. It has no visible UI of its own — the status chip,
 * the mute button and the captions live in the workspace — it exists so that
 * the Agora client is created once, on the client, and released on unmount.
 *
 * Mounting joins; unmounting leaves. The workspace keys this component by the
 * join token, so a reconnect is a fresh mount.
 *
 * Default export: loaded with `next/dynamic({ ssr: false })`.
 */
export default function VoicePanel(props: VoicePanelProps) {
  const [client] = useState(createRtcClient);
  return (
    <AgoraRTCProvider client={client}>
      <VoiceSession {...props} />
    </AgoraRTCProvider>
  );
}

function VoiceSession({ join, muted, handlers, onControls }: VoicePanelProps) {
  const { controls, remoteUsers } = useVoice(join, handlers);

  useEffect(() => {
    onControls(controls);
    return () => onControls(null);
  }, [controls, onControls]);

  useEffect(() => {
    void controls.setMuted(muted);
  }, [controls, muted]);

  // The agent's audio plays through these; nothing is shown.
  return (
    <div hidden aria-hidden>
      {remoteUsers.map((user) => (
        <RemoteUser key={String(user.uid)} user={user} playAudio playVideo={false} />
      ))}
    </div>
  );
}
