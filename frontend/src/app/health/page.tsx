import { Pending } from "@/components/Pending";

export default function HealthPage() {
  return <Pending title="Health" sub="Does the system run, and is it correct"
    what="Built once GET /api/v1/health lands (API contract §3.6)." />;
}
