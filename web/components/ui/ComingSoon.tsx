import { Panel } from "@/components/ui/Panel";

interface ComingSoonProps {
  title: string;
  /** What the id names, e.g. "Interview". */
  idLabel: string;
  id: string;
}

/**
 * A placeholder surface for a route whose screen is built in a later task.
 *
 * It exists so links and redirects from the finished pages resolve to something
 * that shows which record was reached, rather than a 404.
 */
export function ComingSoon({ title, idLabel, id }: ComingSoonProps) {
  return (
    <main className="mx-auto w-full max-w-xl px-4 py-12 sm:px-6">
      {/* The panel's title is an h2; the page still needs a top-level heading. */}
      <h1 className="sr-only">{title}</h1>
      <Panel title={title}>
        <dl className="grid gap-1 text-sm">
          <dt className="text-muted-foreground">{idLabel}</dt>
          <dd className="font-mono break-all">{id}</dd>
        </dl>
        <p className="text-muted-foreground mt-4 text-sm">
          This screen is coming in a later task.
        </p>
      </Panel>
    </main>
  );
}
