"use client";

import { X } from "@phosphor-icons/react/ssr";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/Button";
import { cx } from "@/lib/cx";

export interface DrawerTabSpec {
  id: string;
  label: string;
}

interface EvidenceDrawerProps {
  title: string;
  subtitle?: string;
  /** Shown as a tab strip when there is more than one. */
  tabs?: DrawerTabSpec[];
  activeTab?: string;
  onTabChange?: (id: string) => void;
  onClose: () => void;
  children: ReactNode;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), ' +
  'select:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/**
 * The side panel a reference opens in.
 *
 * It is a modal dialog: focus moves to its heading on open, Tab cycles inside
 * it, Escape closes it, and focus returns to the control that opened it. The
 * page behind stays put (body scroll is locked) so closing lands the reader
 * where they were.
 */
export function EvidenceDrawer({
  title,
  subtitle,
  tabs,
  activeTab,
  onTabChange,
  onClose,
  children,
}: EvidenceDrawerProps) {
  const panelRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const panelId = useId();
  const [shown, setShown] = useState(false);

  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const opener = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    headingRef.current?.focus();
    // A frame in, so the enter transition has a start state to leave from.
    const frame = requestAnimationFrame(() => setShown(true));

    /*
     * The keys are handled on the document, not the panel: a control that
     * becomes disabled while focused (Rerun, Submit) drops focus to the body,
     * and Escape must still close the dialog from there. Tab from outside the
     * panel comes back in.
     */
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => element.offsetParent !== null);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const inside = active instanceof Node && panelRef.current.contains(active);
      if (!inside) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && (active === first || active === headingRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  const showTabs = tabs !== undefined && tabs.length > 1;

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!tabs || !onTabChange) return;
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = tabs[(index + step + tabs.length) % tabs.length];
    onTabChange(next.id);
    (event.currentTarget.parentElement?.children[
      (index + step + tabs.length) % tabs.length
    ] as HTMLElement | undefined)?.focus();
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        aria-hidden
        onClick={onClose}
        className={cx(
          "bg-background/70 absolute inset-0 transition-opacity duration-200",
          shown ? "opacity-100" : "opacity-0",
        )}
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cx(
          "bg-card text-card-foreground border-border relative flex h-full w-full max-w-3xl",
          "flex-col border-l shadow-xl transition-[opacity,transform] duration-200",
          shown ? "translate-x-0 opacity-100" : "translate-x-4 opacity-0",
        )}
      >
        <header className="border-border flex items-start justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            <h2
              ref={headingRef}
              id={titleId}
              tabIndex={-1}
              className="text-base font-semibold"
            >
              {title}
            </h2>
            {subtitle ? (
              <p className="text-muted-foreground font-mono text-xs break-all">{subtitle}</p>
            ) : null}
          </div>
          <Button variant="ghost" onClick={onClose} className="shrink-0">
            <X size={18} aria-hidden />
            Close
          </Button>
        </header>

        {showTabs ? (
          <div role="tablist" className="border-border flex gap-1 border-b px-4 pt-2">
            {tabs.map((tab, index) => {
              const selected = tab.id === activeTab;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={`${panelId}-tab-${tab.id}`}
                  aria-selected={selected}
                  aria-controls={`${panelId}-panel`}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => onTabChange?.(tab.id)}
                  onKeyDown={(event) => onTabKeyDown(event, index)}
                  className={cx(
                    "-mb-px min-h-11 cursor-pointer border-b-2 px-3 text-sm font-semibold",
                    "transition-colors duration-200",
                    selected
                      ? "border-accent text-foreground"
                      : "text-muted-foreground hover:text-foreground border-transparent",
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        ) : null}

        <div
          id={`${panelId}-panel`}
          role={showTabs ? "tabpanel" : undefined}
          aria-labelledby={showTabs && activeTab ? `${panelId}-tab-${activeTab}` : undefined}
          className="min-h-0 flex-1 overflow-y-auto p-4"
        >
          {children}
        </div>
      </aside>
    </div>
  );
}
