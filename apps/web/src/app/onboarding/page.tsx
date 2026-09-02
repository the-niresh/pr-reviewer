"use client";

import { FormEvent, useEffect, useState } from "react";
import { CheckCircle2, CircleAlert, ShieldCheck } from "lucide-react";

import { GithubMark } from "@/components/github-mark";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

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
  const [modelKey, setModelKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [csrf, setCsrf] = useState("");
  const [mode, setMode] = useState<ModePayload | null>(null);
  const [modeError, setModeError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [modeResponse, sessionResponse] = await Promise.all([
          fetch(`${LOCAL_API}/onboarding/mode`, { credentials: "include" }),
          fetch(`${LOCAL_API}/onboarding/session`, { credentials: "include" }),
        ]);
        if (!modeResponse.ok || !sessionResponse.ok) {
          throw new Error("onboarding API unavailable");
        }
        const payload = (await modeResponse.json()) as ModePayload;
        const session = (await sessionResponse.json()) as { csrf_token: string };
        if (!cancelled) {
          setMode(payload);
          setCsrf(session.csrf_token);
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

  async function onSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    try {
      const response = await fetch(`${LOCAL_API}/onboarding/model-key`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
        },
        body: JSON.stringify({ provider: "openai", key: modelKey }),
      });
      if (!response.ok) {
        return;
      }
      setModelKey("");
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }

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
            <Button variant="outline">
              <GithubMark className="size-4" />
              Sign in with GitHub
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Model key</CardTitle>
            <CardDescription>
              Bring your own key. It is stored on this machine and never sent to the
              hosted control plane.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSave} className="flex flex-wrap items-end gap-3">
              <div className="min-w-56 flex-1">
                <label
                  htmlFor="model-key"
                  className="mb-1.5 block text-sm font-medium"
                >
                  API key
                </label>
                <Input
                  id="model-key"
                  name="model-key"
                  type="password"
                  autoComplete="off"
                  placeholder="sk-..."
                  value={modelKey}
                  onChange={(event) => setModelKey(event.target.value)}
                />
              </div>
              <Button type="submit" disabled={!csrf}>
                Save
              </Button>
            </form>
            {saved ? (
              <p className="text-primary mt-3 inline-flex items-center gap-1.5 text-sm">
                <CheckCircle2 aria-hidden="true" />
                API key saved
              </p>
            ) : null}
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
