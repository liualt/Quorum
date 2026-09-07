import { Report } from "@/components/evidence/Report";

/**
 * The assessment report for one interview.
 *
 * The server side only unwraps the route param: the report needs the session
 * cookie and the event stream, both of which live in the browser.
 */
export default async function AssessmentPage(props: PageProps<"/assessment/[id]">) {
  const { id } = await props.params;
  return <Report interviewId={id} />;
}
