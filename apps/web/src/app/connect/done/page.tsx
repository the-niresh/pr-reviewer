import { ConnectDoneCountdown } from "@/components/ConnectDoneCountdown";

export const metadata = {
  title: "You're all set",
};

// Sign-in and repository permission are both finished here, but the review itself only
// happens back in the terminal, so this page's one job is to send the person there and
// then get out of their way onto the dashboard. See ConnectDoneCountdown for the timer.
export default function ConnectDonePage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col items-center justify-center px-6 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">You&apos;re signed in</h1>
      <p className="text-muted-foreground mt-3 max-w-prose text-sm leading-relaxed">
        Setup is finished. Go back to your terminal to start a review.
      </p>
      <ConnectDoneCountdown />
    </main>
  );
}
