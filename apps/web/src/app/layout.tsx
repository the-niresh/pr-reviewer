import type { ReactNode } from "react";

export const metadata = {
  title: "PR Reviewer",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
