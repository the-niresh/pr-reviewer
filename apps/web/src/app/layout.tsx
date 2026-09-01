import type { ReactNode } from "react";

import "./globals.css";

export const metadata = {
  title: "PR Reviewer",
  description:
    "The PR reviewer that runs on your machine. Source, diffs, and model keys never leave it.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
