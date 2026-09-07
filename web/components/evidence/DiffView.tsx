"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { cx } from "@/lib/cx";
import type { FileMap } from "@/lib/types";

/*
 * Monaco is a large client-only bundle; it is loaded when the Code tab first
 * renders, not with the page.
 */
const DiffEditor = dynamic(
  () => import("@monaco-editor/react").then((module) => module.DiffEditor),
  {
    ssr: false,
    loading: () => (
      <p role="status" className="text-muted-foreground p-4 text-sm">
        Loading the diff editor…
      </p>
    ),
  },
);

export interface DiffSide {
  /**
   * Stable identity of the side — the snapshot id, or "scenario" — used to
   * name Monaco's text models so the same file is one model however often
   * it is opened.
   */
  key: string;
  /** Which snapshot (id, hash, time) or "the scenario as given". */
  label: string;
  files: FileMap;
}

/*
 * Snapshots are immutable, so a model named after one never goes stale, and
 * the models are kept rather than disposed on unmount: the library disposes
 * them before it resets the diff editor, which Monaco 0.55 reports as an
 * error, and a handful of small models is nothing to keep.
 */
const modelPath = (side: DiffSide, name: string) => `quorum://${side.key}/${name}`;

interface DiffViewProps {
  original: DiffSide;
  modified: DiffSide;
}

const LANGUAGES: Record<string, string> = {
  py: "python",
  json: "json",
  md: "markdown",
};

function languageFor(name: string): string {
  return LANGUAGES[name.split(".").pop() ?? ""] ?? "plaintext";
}

/** The code difference between two snapshots, one file at a time. */
export function DiffView({ original, modified }: DiffViewProps) {
  const names = useMemo(
    () =>
      Array.from(
        new Set([...Object.keys(modified.files), ...Object.keys(original.files)]),
      ).sort(),
    [original.files, modified.files],
  );
  const [chosen, setChosen] = useState<string | null>(null);
  const isChanged = (name: string) => original.files[name] !== modified.files[name];
  // Open on the first file that changed; a reader came for the difference.
  const active =
    chosen !== null && names.includes(chosen)
      ? chosen
      : (names.find(isChanged) ?? names[0]);

  if (active === undefined) {
    return <p className="text-muted-foreground text-sm">Neither snapshot holds any files.</p>;
  }

  return (
    <div className="grid gap-3">
      <dl className="grid gap-2 font-mono text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Original</dt>
          <dd className="break-all">{original.label}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Modified</dt>
          <dd className="break-all">{modified.label}</dd>
        </div>
      </dl>

      <div role="group" aria-label="Files" className="flex flex-wrap gap-1">
        {names.map((name) => {
          const selected = name === active;
          const unchanged = original.files[name] === modified.files[name];
          return (
            <button
              key={name}
              type="button"
              aria-pressed={selected}
              onClick={() => setChosen(name)}
              className={cx(
                "min-h-11 cursor-pointer rounded-md border px-3 font-mono text-xs",
                "transition-colors duration-200",
                selected
                  ? "border-border-strong bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted border-transparent",
              )}
            >
              {name}
              {unchanged ? <span className="text-muted-foreground"> · unchanged</span> : null}
            </button>
          );
        })}
      </div>

      <div className="border-border overflow-hidden rounded-lg border">
        <DiffEditor
          height={360}
          language={languageFor(active)}
          original={original.files[active] ?? ""}
          modified={modified.files[active] ?? ""}
          originalModelPath={modelPath(original, active)}
          modifiedModelPath={modelPath(modified, active)}
          keepCurrentOriginalModel
          keepCurrentModifiedModel
          theme="vs-dark"
          options={{
            readOnly: true,
            renderSideBySide: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
            automaticLayout: true,
          }}
        />
      </div>
    </div>
  );
}
