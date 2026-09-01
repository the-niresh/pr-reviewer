import type { ReactNode } from "react";

import { DashboardShell } from "@/components/DashboardShell";

export const metadata = {
  title: "Review dashboard",
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
