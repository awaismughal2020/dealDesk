import type { Metadata } from "next";
import { ImpactView } from "@/components/impact/impact-view";

export const metadata: Metadata = { title: "Impact" };

export default function ImpactPage() {
  return <ImpactView />;
}
