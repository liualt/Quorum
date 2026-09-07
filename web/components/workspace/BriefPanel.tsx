import type { ReactNode } from "react";

interface BriefPanelProps {
  markdown: string;
}

/**
 * Renders the scenario brief.
 *
 * The brief is authored in this repository, so this handles exactly the
 * Markdown it uses — `#`/`##` headings, paragraphs, `-` lists, `**bold**` and
 * `` `code` `` — and nothing more. Headings start at h3: the page has an h1
 * and the panel it sits in has an h2.
 */
export function BriefPanel({ markdown }: BriefPanelProps) {
  return (
    <article className="h-full overflow-y-auto px-6 py-4 text-sm leading-relaxed">
      {render(markdown)}
    </article>
  );
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="text-foreground font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={index} className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function render(markdown: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flush = () => {
    if (paragraph.length > 0) {
      blocks.push(
        <p key={blocks.length} className="text-muted-foreground mb-3">
          {inline(paragraph.join(" "))}
        </p>,
      );
      paragraph = [];
    }
    if (list.length > 0) {
      blocks.push(
        <ul key={blocks.length} className="text-muted-foreground mb-3 list-disc space-y-1 pl-5">
          {list.map((item, index) => (
            <li key={index}>{inline(item)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };

  for (const raw of markdown.split("\n")) {
    const line = raw.trimEnd();
    if (line.startsWith("# ")) {
      flush();
      blocks.push(
        <h3 key={blocks.length} className="mb-3 text-base font-semibold">
          {inline(line.slice(2))}
        </h3>,
      );
    } else if (line.startsWith("## ")) {
      flush();
      blocks.push(
        <h4 key={blocks.length} className="mt-5 mb-2 text-sm font-semibold tracking-wide uppercase">
          {inline(line.slice(3))}
        </h4>,
      );
    } else if (line.startsWith("- ")) {
      if (paragraph.length > 0) flush();
      list.push(line.slice(2));
    } else if (line.trim() === "") {
      flush();
    } else if (list.length > 0 && line.startsWith("  ")) {
      // A wrapped list item continues on an indented line.
      list[list.length - 1] += ` ${line.trim()}`;
    } else {
      if (list.length > 0) flush();
      paragraph.push(line.trim());
    }
  }
  flush();
  return blocks;
}
