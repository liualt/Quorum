"use client";

import Editor from "@monaco-editor/react";

export type EditorLanguage = "python" | "json";

interface CodeEditorProps {
  /** The file name. Monaco keeps one model per path, so undo history survives tab switches. */
  path: string;
  value: string;
  language: EditorLanguage;
  readOnly: boolean;
  onChange: (value: string) => void;
  ariaLabel: string;
}

/**
 * The Monaco editor, configured once.
 *
 * Loaded through `next/dynamic` with `ssr: false` — Monaco needs `window` at
 * import time — which is why this is the default export.
 */
export default function CodeEditor({
  path,
  value,
  language,
  readOnly,
  onChange,
  ariaLabel,
}: CodeEditorProps) {
  return (
    <Editor
      height="100%"
      path={path}
      value={value}
      language={language}
      theme="vs-dark"
      onChange={(next) => onChange(next ?? "")}
      loading={<EditorLoading />}
      options={{
        minimap: { enabled: false },
        fontSize: 14,
        fontFamily: "var(--font-mono)",
        readOnly,
        ariaLabel,
        scrollBeyondLastLine: false,
        automaticLayout: true,
        wordWrap: "on",
        tabSize: 4,
        renderLineHighlight: "line",
      }}
    />
  );
}

export function EditorLoading() {
  return (
    <p role="status" className="text-muted-foreground p-4 text-sm">
      Loading the editor…
    </p>
  );
}
