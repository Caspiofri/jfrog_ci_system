import { Empty, PageHead, Panel } from "@/components/ci";

/** A screen whose API isn't built yet. No sample data: it says what is missing. */
export function Pending({ title, sub, what }: { title: string; sub: string; what: string }) {
  return (
    <>
      <PageHead title={title} sub={sub} />
      <Panel><Empty>{what}</Empty></Panel>
    </>
  );
}
