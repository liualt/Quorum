import { ConsentForm } from "@/components/consent/ConsentForm";
import { Disclosure } from "@/components/consent/Disclosure";
import { AIBadge } from "@/components/ui/AIBadge";

/**
 * The consent and disclosure landing page.
 *
 * A server component: the disclosure is in the HTML before any JavaScript runs,
 * and only the form — which needs state — is a client leaf.
 */
export default function ConsentPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="mb-8">
        <p className="text-muted-foreground mb-2 flex items-center gap-2 font-mono text-xs tracking-widest uppercase">
          Quorum
          <AIBadge />
        </p>
        <h1 className="text-2xl font-bold sm:text-3xl">
          A panel of AI interviewers, one engineering case
        </h1>
        <p className="text-muted-foreground mt-3 text-base">
          You will debug a small system while three AI interviewers ask you about
          it. Afterwards Quorum writes down what it observed and links every
          observation to the transcript, the code and the test results behind it.
          Read what that involves before you agree.
        </p>
      </header>

      <div className="grid gap-6">
        <Disclosure />
        <ConsentForm />
      </div>

      <footer className="text-muted-foreground mt-8 text-sm">
        <p>
          Human review does not by itself establish legal compliance. Any real
          hiring use needs review for its jurisdiction and its actual use — see{" "}
          <a
            href="https://www.eeoc.gov/eeoc-disability-related-resources/artificial-intelligence-and-ada"
            target="_blank"
            rel="noreferrer"
            className="text-foreground underline underline-offset-4"
          >
            the EEOC guidance on artificial intelligence and the ADA
          </a>
          .
        </p>
      </footer>
    </main>
  );
}
