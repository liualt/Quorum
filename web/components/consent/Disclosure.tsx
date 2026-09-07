import {
  CloudArrowUp,
  ClockCounterClockwise,
  Code,
  ListChecks,
  MicrophoneSlash,
  PauseCircle,
  Prohibit,
  UsersThree,
} from "@phosphor-icons/react/ssr";
import type { ReactNode } from "react";

import { AIBadge } from "@/components/ui/AIBadge";
import { Panel } from "@/components/ui/Panel";

/**
 * The AI disclosure shown before consent (PRD §12).
 *
 * This is a static server component: the wording is a product commitment, so it
 * ships in the HTML rather than appearing after hydration, and it stays in one
 * file so a change to the disclosure is a change to one place.
 */

interface Item {
  icon: ReactNode;
  term: string;
  detail: ReactNode;
}

const ICON = { size: 20, "aria-hidden": true } as const;

const ITEMS: Item[] = [
  {
    icon: <UsersThree {...ICON} />,
    term: "Three AI interviewers, not people",
    detail: (
      <>
        A technical interviewer, a product manager and a customer administrator
        take turns asking you questions. Every one of them is a language model.
        Their role labels and their captions carry an <AIBadge /> badge for the
        whole session.
      </>
    ),
  },
  {
    icon: <Code {...ICON} />,
    term: "One engineering case",
    detail:
      "You get a brief, a small codebase with a real defect, an editor and a set of checks you can run. You change the code, run the checks, and explain your reasoning as you go.",
  },
  {
    icon: <CloudArrowUp {...ICON} />,
    term: "Agora and the model provider process your audio and text",
    detail:
      "Agora carries the voice conversation. The model provider receives your speech transcript and the code you write in order to ask the next question and to write the assessment. Both process that data under their own terms — this is not zero retention.",
  },
  {
    icon: <MicrophoneSlash {...ICON} />,
    term: "This app does not record raw audio",
    detail:
      "Quorum stores the text transcript, your saved code snapshots and the results of the checks you run. It does not record or keep the audio itself.",
  },
  {
    icon: <ClockCounterClockwise {...ICON} />,
    term: "Kept for seven days, deletable at any moment",
    detail:
      "Everything from this interview is deleted seven days after it ends. You can delete it yourself, immediately, from your report.",
  },
  {
    icon: <ListChecks {...ICON} />,
    term: "Four dimensions, and a human decision",
    detail:
      "You are described on four dimensions: understanding the problem, implementing and checking a fix, explaining consequences, and responding to new evidence. Quorum reports what it observed and links each observation to the transcript, code and test results behind it. It does not score you, rank you or decide anything. A person makes the hiring decision.",
  },
  {
    icon: <Prohibit {...ICON} />,
    term: "What is never asked for",
    detail:
      "No CV, no webcam, no identity document and no access to a private repository. A display name — a pseudonym is fine — is all Quorum keeps about you.",
  },
  {
    icon: <PauseCircle {...ICON} />,
    term: "You stay in control",
    detail:
      "Pause whenever you want. Captions are always on. You can type instead of speaking, and you can correct anything the transcript got wrong once the interview is over.",
  },
];

export function Disclosure() {
  return (
    <Panel title="Before you agree">
      <dl className="grid gap-6 sm:grid-cols-2">
        {ITEMS.map((item) => (
          <div key={item.term} className="flex gap-3">
            <span className="text-accent mt-0.5 shrink-0">{item.icon}</span>
            <div className="min-w-0">
              <dt className="font-mono text-sm font-semibold">{item.term}</dt>
              <dd className="text-muted-foreground mt-1 text-sm">
                {item.detail}
              </dd>
            </div>
          </div>
        ))}
      </dl>
    </Panel>
  );
}
