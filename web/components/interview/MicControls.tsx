"use client";

import {
  CircleNotch,
  Microphone,
  MicrophoneSlash,
  Plugs,
  TextT,
  Waveform,
} from "@phosphor-icons/react/ssr";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import type { ChipTone } from "@/components/ui/Chip";
import type { AgentActivity } from "@/lib/voice";

/** How the workspace reports voice: the three live states plus text mode. */
export type VoiceUiStatus = "connecting" | "connected" | "text" | "disconnected";

interface MicControlsProps {
  voice: VoiceUiStatus;
  /** Why voice is not on, or the last voice error. */
  note: string | null;
  agentActivity: AgentActivity | null;
  muted: boolean;
  paused: boolean;
  onToggleMute: () => void;
  onReconnect: () => void;
  onContinueWithText: () => void;
  /** A reconnect is in flight. */
  busy: boolean;
}

const STATUS: Record<VoiceUiStatus, { label: string; tone: ChipTone; icon: ReactNode }> = {
  connecting: {
    label: "Voice connecting",
    tone: "neutral",
    icon: <CircleNotch size={14} aria-hidden className="animate-spin" />,
  },
  connected: {
    label: "Voice connected",
    tone: "positive",
    icon: <Waveform size={14} aria-hidden />,
  },
  text: { label: "Text mode", tone: "neutral", icon: <TextT size={14} aria-hidden /> },
  disconnected: {
    label: "Voice disconnected",
    tone: "negative",
    icon: <Plugs size={14} aria-hidden />,
  },
};

const ACTIVITY: Record<AgentActivity, string> = {
  idle: "The panel is idle",
  listening: "The panel is listening",
  thinking: "The panel is thinking",
  speaking: "The panel is speaking",
  silent: "The panel is silent",
};

export function MicControls({
  voice,
  note,
  agentActivity,
  muted,
  paused,
  onToggleMute,
  onReconnect,
  onContinueWithText,
  busy,
}: MicControlsProps) {
  const status = STATUS[voice];
  const micAvailable = voice === "connected" && !paused;

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Chip tone={status.tone} icon={status.icon}>
          {status.label}
        </Chip>
        {voice === "connected" && agentActivity ? (
          <p role="status" className="text-muted-foreground text-sm">
            {ACTIVITY[agentActivity]}
          </p>
        ) : null}
        {voice !== "text" ? (
          <Button
            variant="secondary"
            className="ml-auto"
            aria-pressed={muted}
            aria-label={muted ? "Unmute microphone" : "Mute microphone"}
            disabled={!micAvailable}
            onClick={onToggleMute}
          >
            {muted ? (
              <MicrophoneSlash size={18} aria-hidden />
            ) : (
              <Microphone size={18} aria-hidden />
            )}
            {muted ? "Unmute" : "Mute"}
          </Button>
        ) : null}
      </div>

      {voice === "disconnected" ? (
        <div
          role="alert"
          className="border-destructive bg-destructive/10 grid gap-3 rounded-lg border p-3 text-sm"
        >
          <p>Voice disconnected. Your work is saved. Reconnect or continue with text.</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={onReconnect} disabled={busy}>
              {busy ? "Reconnecting…" : "Reconnect"}
            </Button>
            <Button variant="secondary" onClick={onContinueWithText} disabled={busy}>
              Continue with text
            </Button>
          </div>
        </div>
      ) : null}

      {note ? (
        <p role="status" className="text-muted-foreground text-sm">
          {note}
        </p>
      ) : null}
    </div>
  );
}
