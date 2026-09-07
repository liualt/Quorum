import { ComingSoon } from "@/components/ui/ComingSoon";

/** Placeholder for the assessment report (task 11). */
export default async function AssessmentPage(
  props: PageProps<"/assessment/[id]">,
) {
  const { id } = await props.params;
  return <ComingSoon title="Assessment" idLabel="Interview" id={id} />;
}
