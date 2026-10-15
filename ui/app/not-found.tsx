import Link from "next/link";
import { Empty } from "@/components/ui";

/** m15: a branded empty state instead of Next's default 404. */
export default function NotFound() {
  return (
    <div className="page">
      <div className="page-body">
        <Empty title="We couldn't find that page" action={<Link className="btn sm" href="/ask">Go to Ask</Link>}>
          Search from the bar at the top, or ask a question.
        </Empty>
      </div>
    </div>
  );
}
