"use client";

import { Microphone, TextT } from "@phosphor-icons/react/ssr";
import { useEffect, useState } from "react";

import { AIBadge } from "@/components/ui/AIBadge";
import { Button } from "@/components/ui/Button";
import { ErrorText } from "@/components/ui/ErrorText";
import { Panel } from "@/components/ui/Panel";
import type { InterviewView } from "@/lib/types";

interface PreJoinProps {
  interview: InterviewView;
  /** A start request is in flight. */
  busy: boolean;
  error: string | null;
  onJoin: (withVoice: boolean) => void;
}

type MicState = "requesting" | "silent" | "working" | "blocked";

/** RMS of the time-domain signal above which the microphone is clearly picking something up. */
const WORKING_LEVEL = 0.03;
/** How often the meter re-renders; the analyser runs every frame regardless. */
const METER_INTERVAL_MS = 100;

interface MicTest {
  state: MicState;
  /** 0–1, smoothed enough to read. */
  level: number;
  detail: string | null;
}

/**
 * Ask for the microphone and watch its level until the component unmounts.
 *
 * This stream is only a test. It is released on unmount — before the voice
 * session opens its own track — so nothing here outlives the pre-join screen.
 */
function useMicTest(): MicTest {
  const [state, setState] = useState<MicState>("requesting");
  const [level, setLevel] = useState(0);
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    let frame = 0;

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) return;
        context = new AudioContext();
        const analyser = context.createAnalyser();
        analyser.fftSize = 512;
        context.createMediaStreamSource(stream).connect(analyser);
        const samples = new Uint8Array(analyser.fftSize);
        let lastPaint = 0;
        setState("silent");

        const tick = (now: number) => {
          analyser.getByteTimeDomainData(samples);
          let sum = 0;
          for (const sample of samples) {
            const deviation = (sample - 128) / 128;
            sum += deviation * deviation;
          }
          const rms = Math.sqrt(sum / samples.length);
          if (now - lastPaint >= METER_INTERVAL_MS) {
            lastPaint = now;
            setLevel(Math.min(1, rms * 4));
          }
          if (rms > WORKING_LEVEL) setState("working");
          frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      } catch (cause) {
        if (cancelled) return;
        setState("blocked");
        setDetail(
          cause instanceof DOMException && cause.name === "NotAllowedError"
            ? "Microphone access was not allowed."
            : cause instanceof DOMException && cause.name === "NotFoundError"
              ? "No microphone was found."
              : "The microphone could not be opened.",
        );
      }
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
      context?.close().catch(() => {
        // Closing a context that never started is not a failure.
      });
    };
  }, []);

  return { state, level, detail };
}

const MIC_MESSAGES: Record<MicState, string> = {
  requesting: "Asking for microphone access…",
  silent: "Microphone connected. Say something to test it.",
  working: "Microphone working.",
  blocked: "Microphone unavailable.",
};

export function PreJoin({ interview, busy, error, onJoin }: PreJoinProps) {
  const mic = useMicTest();
  const rejoining = interview.started_at !== null;
  const voiceOffered = interview.voice_enabled && mic.state !== "blocked";

  const voiceHint = !interview.voice_enabled
    ? "Voice is not set up on this server, so the interview runs in text."
    : mic.state === "blocked"
      ? "Allow microphone access to join with voice, or continue with text."
      : "You can switch to typing at any point; captions are always on.";

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8 sm:px-6 sm:py-12">
      <p className="text-muted-foreground mb-4 flex items-center gap-2 font-mono text-xs tracking-widest uppercase">
        Quorum
        <AIBadge />
      </p>
      <h1 className="mb-6 text-2xl font-bold">
        {rejoining ? "Rejoin your interview" : "Before you join"}
      </h1>

      <Panel title={rejoining ? "Your session is still open" : "What happens next"}>
        <div className="grid gap-6">
          <p className="text-muted-foreground text-sm">
            {interview.display_name}, three AI interviewers will question you about a caching
            change in a document-search application. The brief, the code and the checks are
            in the workspace. The session is capped at {interview.session_cap_minutes} minutes
            {rejoining ? ", counted from when you first joined" : ""}.
          </p>

          <div>
            <p className="mb-2 text-sm font-medium">Microphone test</p>
            <div
              role="meter"
              aria-label="Microphone level"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(mic.level * 100)}
              className="bg-background border-border-strong h-3 w-full overflow-hidden rounded-full border"
            >
              <div
                className="bg-accent h-full transition-[width] duration-150"
                style={{ width: `${Math.round(mic.level * 100)}%` }}
              />
            </div>
            <p role="status" className="text-muted-foreground mt-2 text-sm">
              {MIC_MESSAGES[mic.state]}
              {mic.detail ? ` ${mic.detail}` : ""}
            </p>
          </div>

          {error ? <ErrorText>{error}</ErrorText> : null}

          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={() => onJoin(true)} disabled={busy || !voiceOffered}>
              <Microphone size={20} aria-hidden />
              {busy ? "Joining…" : rejoining ? "Rejoin with voice" : "Join with voice"}
            </Button>
            <Button size="lg" variant="secondary" onClick={() => onJoin(false)} disabled={busy}>
              <TextT size={20} aria-hidden />
              Continue with text
            </Button>
          </div>
          <p className="text-muted-foreground text-sm">{voiceHint}</p>
        </div>
      </Panel>
    </main>
  );
}
