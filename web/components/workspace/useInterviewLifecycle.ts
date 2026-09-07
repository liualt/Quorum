"use client";

import { useCallback, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import {
  finishInterview,
  getInterview,
  sendTurn,
  setPaused as requestPaused,
  startInterview,
} from "@/lib/api";
import type { InterviewView, Role, Stage } from "@/lib/types";

import { errorMessage } from "./errorMessage";
import type { Phase } from "./useInterviewSession";
import { useVoiceBridge } from "./useVoiceBridge";

interface Options {
  id: string;
  setPhase: Dispatch<SetStateAction<Phase>>;
  setInterview: (view: InterviewView) => void;
  setPaused: Dispatch<SetStateAction<boolean>>;
  setStage: (stage: Stage) => void;
  setRole: (role: Role) => void;
  /** Where a failed pause change is reported: the run panel's error line. */
  reportError: (message: string) => void;
  /** Leave for the assessment once the interview has ended. */
  onFinished: () => void;
}

/**
 * What the candidate does to the session: start it, pause and resume it,
 * speak to the panel, and end it. Voice is composed here because pausing
 * and starting are entangled with it — a disconnect pauses, a start joins
 * the channel, an end leaves it — and the bridge is handed back for the
 * panels that render it.
 */
export function useInterviewLifecycle({
  id,
  setPhase,
  setInterview,
  setPaused,
  setStage,
  setRole,
  reportError,
  onFinished,
}: Options) {
  const [startError, setStartError] = useState<string | null>(null);
  const [finishError, setFinishError] = useState<string | null>(null);

  const updatePaused = useCallback(
    async (next: boolean) => {
      setPaused(next);
      try {
        await requestPaused(id, next);
      } catch (cause) {
        setPaused(!next);
        reportError(errorMessage(cause, "Could not change the pause state."));
      }
    },
    [id, reportError, setPaused],
  );

  const voice = useVoiceBridge(id, updatePaused);
  const { applyJoin, trySend, drop: dropVoice } = voice;

  const start = useCallback(
    async (withVoice: boolean) => {
      setPhase("starting");
      setStartError(null);
      try {
        const { voice: join } = await startInterview(id, { voice: withVoice });
        applyJoin(join, withVoice);
        // The server set `started_at`; the timer needs it.
        setInterview(await getInterview(id));
        setPhase("live");
      } catch (cause) {
        setStartError(errorMessage(cause, "Could not start the interview. Try again."));
        setPhase("prejoin");
      }
    },
    [applyJoin, id, setInterview, setPhase],
  );

  const send = useCallback(
    async (text: string) => {
      if (await trySend(text)) return;
      let reply;
      try {
        reply = await sendTurn(id, text);
      } catch (cause) {
        throw new Error(errorMessage(cause, "Could not reach the panel. Try again."));
      }
      // The reply segment itself arrives on the stream — the server emits it
      // before this response returns — so only the stage and role are taken
      // from the response, in case their events are still in flight.
      setStage(reply.stage);
      setRole(reply.role);
    },
    [id, setRole, setStage, trySend],
  );

  const finish = useCallback(async () => {
    setPhase("finishing");
    setFinishError(null);
    // Leave the channel first so the microphone is released while the
    // assessment builds; the server stops the agent on its side.
    dropVoice();
    try {
      await finishInterview(id);
      onFinished();
    } catch (cause) {
      setFinishError(errorMessage(cause, "Could not end the interview. Try again."));
      setPhase("live");
    }
  }, [dropVoice, id, onFinished, setPhase]);

  return { voice, updatePaused, start, send, finish, startError, finishError };
}
