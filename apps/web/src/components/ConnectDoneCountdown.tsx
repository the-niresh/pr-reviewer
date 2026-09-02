"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const REDIRECT_SECONDS = 5;
const REDIRECT_PATH = "/dashboard";

/** The five-second pause is the whole point: it gives someone time to read "go back to
 *  your terminal" before the page moves on without them. The countdown is real (a timer
 *  that actually fires the redirect), not a decorative label, and the link below it means
 *  nobody who already knows what to do next has to sit through it. */
export function ConnectDoneCountdown() {
  const router = useRouter();
  const [secondsLeft, setSecondsLeft] = useState(REDIRECT_SECONDS);

  useEffect(() => {
    if (secondsLeft <= 0) {
      router.push(REDIRECT_PATH);
      return;
    }
    const timer = setTimeout(() => setSecondsLeft((current) => current - 1), 1000);
    return () => clearTimeout(timer);
  }, [secondsLeft, router]);

  const percentComplete = ((REDIRECT_SECONDS - secondsLeft) / REDIRECT_SECONDS) * 100;

  return (
    <>
      <p aria-live="polite" className="text-muted-foreground mt-6 text-sm">
        Taking you to the dashboard in {secondsLeft} second{secondsLeft === 1 ? "" : "s"}.
      </p>
      <div
        role="progressbar"
        aria-valuenow={Math.round(percentComplete)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Redirect countdown"
        className="bg-muted mt-4 h-1 w-full max-w-xs overflow-hidden rounded-full"
      >
        <div
          className="bg-primary h-full rounded-full transition-[width] duration-1000 ease-linear motion-reduce:transition-none"
          style={{ width: `${percentComplete}%` }}
        />
      </div>
      <Link
        href={REDIRECT_PATH}
        className="text-primary mt-6 inline-block rounded-sm text-sm underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        Go to the dashboard now
      </Link>
    </>
  );
}
