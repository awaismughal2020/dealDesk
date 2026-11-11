import type { Metadata } from "next";
import { NewRun } from "@/components/new-run";

export const metadata: Metadata = { title: "New run" };

export default function NewRunPage() {
  return <NewRun />;
}
