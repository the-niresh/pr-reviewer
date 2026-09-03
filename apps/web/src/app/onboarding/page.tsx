"use client";

import { useEffect, useState } from "react";
import { CircleAlert, ShieldCheck } from "lucide-react";

import { GithubMark } from "@/components/github-mark";
import { cn } from "@/lib/utils";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const LOCAL_API = process.env.NEXT_PUBLIC_LOCAL_API_ORIGIN ?? "http://127.0.0.1:8741";

type ModePayload = {
  granted_mode: string;
  requested_mode: string;
  downgraded: boolean;
  disabled_features: string[];
  forces_human_approval: boolean;
};

/** The pairing steps, numbered because they are a real sequence: the model key
 *  cannot be saved before the local daemon hands back a CSRF token. */
const STEPS = [
  { n: 1, title: "Sign in", hint: "on the hosted control plane" },
  { n: 2, title: "Pick repositories", hint: "after GitHub sign-in" },
  { n: 3, title: "Add a model key", hint: "stored on this machine only" },
  { n: 4, title: "Confirm runtime mode", hint: "Docker isolation decides it" },
] as const;

export default function OnboardingPage() {
  const [mode, setMode] = useState<ModePayload | null>(null);
  const [modeError, setModeError] = useState(false);
  // The local daemon (not this page) knows the hosted origin and the allowlisted
  // return_to it is configured with, so the URL is fetched rather than built here -- the
  // same reason the button used to have nothing to link to at all.
  const [signInUrl, setSignInUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [modeResponse, sessionResponse, signInResponse] = await Promise.all([
          fetch(`${LOCAL_API}/onboarding/mode`, { credentials: "include" }),
          fetch(`${LOCAL_API}/onboarding/session`, { credentials: "include" }),
          fetch(`${LOCAL_API}/onboarding/pairing/sign-in`, { credentials: "include" }),
        ]);
        if (!modeResponse.ok || !sessionResponse.ok || !signInResponse.ok) {
          throw new Error("onboarding API unavailable");
        }
        const payload = (await modeResponse.json()) as ModePayload;
        const signIn = (await signInResponse.json()) as { url: string };
        if (!cancelled) {
          setMode(payload);
          setSignInUrl(signIn.url);
        }
      } catch {
        if (!cancelled) {
          setModeError(true);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const daemonUp = mode !== null;

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-16">
      <header className="mb-10">
        <p className="text-muted-foreground mb-3 text-xs font-medium tracking-[0.14em] uppercase">
          Runner setup
        </p>
        <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
          Pair this runner
        </h1>
        <p className="text-muted-foreground mt-4 max-w-prose leading-relaxed">
          Sign in on the hosted control plane. GitHub cannot redirect to 127.0.0.1, so
          this page waits until the pairing code is exchangeable.
        </p>
      </header>

      <ol className="mb-12 grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
        {STEPS.map((step) => (
          <li key={step.n} className="bg-card px-4 py-3">
            <span className="text-primary font-mono text-xs">
              {String(step.n).padStart(2, "0")}
            </span>
            <p className="mt-1 text-sm font-medium">{step.title}</p>
            <p className="text-muted-foreground text-xs">{step.hint}</p>
          </li>
        ))}
      </ol>

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>GitHub</CardTitle>
            <CardDescription>
              Repository selection happens on the hosted origin after GitHub sign-in.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {signInUrl ? (
              <a
                href={signInUrl}
                className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
              >
                <GithubMark className="size-4" />
                Sign in with GitHub
              </a>
            ) : (
              <Button variant="outline" disabled>
                <GithubMark className="size-4" />
                Sign in with GitHub
              </Button>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Model key</CardTitle>
            <CardDescription>
              Add your provider key in the TUI, not here. It is written to this
              machine's keychain and never sent to this site, so there is nothing for
              the web to collect.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="bg-muted/50 rounded-md px-3 py-2 font-mono text-xs">
              reviewer
            </p>
            <p className="text-muted-foreground mt-2 text-sm">
              Open the TUI and go to profile.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>Runtime mode</CardTitle>
              {daemonUp ? (
                <Badge variant={mode.granted_mode === "full" ? "default" : "warning"}>
                  {mode.granted_mode === "full" ? "Full" : "Analysis only"}
                </Badge>
              ) : (
                <Badge variant="muted">Unknown</Badge>
              )}
            </div>
            <CardDescription className="inline-flex items-center gap-1.5">
              <ShieldCheck aria-hidden="true" />
              Docker isolation is checked before full mode is granted.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {modeError ? (
              <p className="text-muted-foreground inline-flex items-start gap-2 text-sm">
                <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0" />
                Could not load runtime mode from the local daemon.
              </p>
            ) : null}
            {mode ? (
              <>
                <p className="text-sm">
                  {mode.granted_mode === "full"
                    ? "Full mode."
                    : mode.downgraded
                      ? "Analysis-only (downgraded because Docker isolation is not proven)."
                      : "Analysis-only."}
                </p>
                <p className="text-muted-foreground mt-4 text-xs font-medium tracking-[0.14em] uppercase">
                  Disabled features
                </p>
                <ul
                  data-testid="disabled-features"
                  className="mt-2 flex flex-wrap gap-1.5"
                >
                  {mode.disabled_features.map((feature) => (
                    <li key={feature}>
                      <Badge variant="outline">{feature}</Badge>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="mt-8 flex justify-end">
        <Button type="button" size="lg" disabled={!daemonUp}>
          Confirm
        </Button>
      </div>
    </main>
  );
}
