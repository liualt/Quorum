import { ComingSoon } from "@/components/ui/ComingSoon";

/** Placeholder for the interview workspace (task 10). */
export default async function InterviewPage(
  props: PageProps<"/interview/[id]">,
) {
  const { id } = await props.params;
  return <ComingSoon title="Interview workspace" idLabel="Interview" id={id} />;
}
