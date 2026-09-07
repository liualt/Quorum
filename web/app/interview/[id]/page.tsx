import { Workspace } from "@/components/workspace/Workspace";

/**
 * The interview workspace. Everything on it needs the browser — the session
 * cookie, the event stream, the editor, the microphone — so the page only
 * unwraps the route param and hands it to the client component.
 */
export default async function InterviewPage(props: PageProps<"/interview/[id]">) {
  const { id } = await props.params;
  return <Workspace id={id} />;
}
