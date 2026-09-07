"use client";

import {
  BracketsCurly,
  Circle,
  FileCode,
  FileText,
  LockSimple,
} from "@phosphor-icons/react/ssr";
import { useRef } from "react";
import type { KeyboardEvent } from "react";

import { cx } from "@/lib/cx";

/** The tab key for the brief, which is not a file. */
export const BRIEF_TAB = "brief";

export const EDITOR_PANEL_ID = "editor-panel";

interface FileListProps {
  editable: string[];
  readonly: string[];
  selected: string;
  dirty: ReadonlySet<string>;
  onSelect: (name: string) => void;
}

interface Tab {
  key: string;
  label: string;
  group: "brief" | "editable" | "readonly";
}

export function tabId(key: string): string {
  return `file-tab-${key.replace(/[^a-z0-9]/gi, "-")}`;
}

/**
 * One vertical tab list: the brief, the editable files, the read-only files.
 *
 * Keyboard: Up/Down move and select (automatic activation), Home/End jump.
 * A roving tabindex keeps the list a single Tab stop.
 */
export function FileList({ editable, readonly, selected, dirty, onSelect }: FileListProps) {
  const listRef = useRef<HTMLDivElement>(null);

  const tabs: Tab[] = [
    { key: BRIEF_TAB, label: "Brief", group: "brief" },
    ...editable.map((name) => ({ key: name, label: name, group: "editable" as const })),
    ...readonly.map((name) => ({ key: name, label: name, group: "readonly" as const })),
  ];

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.findIndex((tab) => tab.key === selected);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowUp") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    const target = tabs[next];
    onSelect(target.key);
    listRef.current
      ?.querySelector<HTMLButtonElement>(`#${tabId(target.key)}`)
      ?.focus();
  };

  const renderTab = (tab: Tab) => {
    const isSelected = tab.key === selected;
    const isDirty = dirty.has(tab.key);
    const Icon =
      tab.group === "brief"
        ? FileText
        : tab.key.endsWith(".json")
          ? BracketsCurly
          : FileCode;
    return (
      <button
        key={tab.key}
        type="button"
        role="tab"
        id={tabId(tab.key)}
        aria-selected={isSelected}
        aria-controls={EDITOR_PANEL_ID}
        tabIndex={isSelected ? 0 : -1}
        onClick={() => onSelect(tab.key)}
        className={cx(
          "flex min-h-10 w-full min-w-0 cursor-pointer items-center gap-2 rounded-md px-2 text-left",
          "font-mono text-sm transition-colors duration-200",
          isSelected
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
        )}
      >
        <Icon size={16} aria-hidden className="shrink-0" />
        <span className="min-w-0 flex-1 truncate">{tab.label}</span>
        {isDirty ? (
          <>
            <Circle size={10} weight="fill" aria-hidden className="text-accent shrink-0" />
            <span className="sr-only">, unsaved changes</span>
          </>
        ) : null}
        {tab.group === "readonly" ? (
          <>
            <LockSimple size={14} aria-hidden className="shrink-0" />
            <span className="sr-only">, read only</span>
          </>
        ) : null}
      </button>
    );
  };

  const group = (title: string, items: Tab[]) => (
    <div className="grid gap-0.5">
      <p className="text-muted-foreground px-2 pt-3 pb-1 text-[11px] font-semibold tracking-widest uppercase">
        {title}
      </p>
      {items.map(renderTab)}
    </div>
  );

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label="Files"
      aria-orientation="vertical"
      onKeyDown={onKeyDown}
      className="border-border w-full shrink-0 overflow-hidden border-b p-2 sm:w-52 sm:border-r sm:border-b-0"
    >
      {renderTab(tabs[0])}
      {group("Editable", tabs.filter((tab) => tab.group === "editable"))}
      {group("Read only", tabs.filter((tab) => tab.group === "readonly"))}
    </div>
  );
}
