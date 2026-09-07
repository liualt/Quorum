import { ReviewExchange } from "@/components/review/ReviewExchange";

/** The one-time reviewer link. The exchange itself needs the browser, so the
 *  page only unwraps the route param and hands it to a client leaf. */
export default async function ReviewPage(props: PageProps<"/review/[token]">) {
  const { token } = await props.params;
  return <ReviewExchange token={token} />;
}
