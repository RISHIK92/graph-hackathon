import { redirect } from "next/navigation";

/** The organisation first: the Directory is the landing page (DESIGN.md §2.3). */
export default function Home() {
  redirect("/directory");
}
