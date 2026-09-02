export const metadata = {
  title: "You're all set",
};

// There is deliberately nothing to click here. Setup finishes on GitHub, and the review
// itself happens back in the terminal, so a next-action button on this page would be a
// button to nowhere.
export default function ConnectDonePage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col items-center justify-center px-6 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">You&apos;re all set</h1>
      <p className="text-muted-foreground mt-3 max-w-prose text-sm leading-relaxed">
        Setup is finished. Go back to your terminal to continue.
      </p>
    </main>
  );
}
