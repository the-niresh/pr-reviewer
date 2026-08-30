"use client";

import { FormEvent, useEffect, useState } from "react";

const LOCAL_API = process.env.NEXT_PUBLIC_LOCAL_API_ORIGIN ?? "http://127.0.0.1:8741";

type ModePayload = {
  granted_mode: string;
  requested_mode: string;
  downgraded: boolean;
  disabled_features: string[];
  forces_human_approval: boolean;
};

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

  return (
    <main>
      <h1>Pair this runner</h1>
      <p>
        Sign in on the hosted control plane. GitHub cannot redirect to 127.0.0.1, so this page
        waits until the pairing code is exchangeable.
      </p>
      <a href="#">Sign in with GitHub</a>

      <h2>Repositories</h2>
      <p>Repository selection happens on the hosted origin after GitHub sign-in.</p>

      <h2>Model key</h2>
      <form onSubmit={onSave}>
        <label htmlFor="model-key">API key</label>
        <input
          id="model-key"
          name="model-key"
          type="password"
          autoComplete="off"
          value={modelKey}
          onChange={(event) => setModelKey(event.target.value)}
        />
        <button type="submit" disabled={!csrf}>
          Save
        </button>
      </form>
      {saved ? <p>API key saved</p> : null}

      <h2>Doctor</h2>
      <p>Docker isolation is checked before full mode is granted.</p>

      <h2>Runtime mode</h2>
      {modeError ? <p>Could not load runtime mode from the local daemon.</p> : null}
      {mode ? (
        <>
          <p>
            {mode.granted_mode === "full"
              ? "Full mode."
              : mode.downgraded
                ? "Analysis-only (downgraded because Docker isolation is not proven)."
                : "Analysis-only."}
          </p>
          <p>Disabled features:</p>
          <ul data-testid="disabled-features">
            {mode.disabled_features.map((feature) => (
              <li key={feature}>{feature}</li>
            ))}
          </ul>
        </>
      ) : null}
      <button type="button">Confirm</button>
    </main>
  );
}
