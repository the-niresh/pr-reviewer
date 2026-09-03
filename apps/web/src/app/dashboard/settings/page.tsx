import { cookies } from "next/headers";

import { GithubMark } from "@/components/github-mark";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadError, SignInPrompt } from "@/components/DashboardState";
import { fetchReviews } from "@/lib/reviews";

export const metadata = {
  title: "Settings",
};

// GitHub is the only place that can grant or remove repository permission for this App;
// this page only shows what is already granted and points at the one place to change it.
const APP_SLUG = process.env.NEXT_PUBLIC_GITHUB_APP_SLUG ?? "";
const INSTALL_URL = APP_SLUG ? `https://github.com/apps/${APP_SLUG}/installations/new` : "";

export default async function SettingsPage() {
  const cookieStore = await cookies();
  const result = await fetchReviews(cookieStore.toString());

  if (result.kind === "unauthenticated") {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        {/* /dashboard/settings is not in the hosted allowlist (github_oauth.py's
            ALLOWED_RETURN_TO_PATHS is only /dashboard and /dashboard/reviews); passing it
            here made the sign-in link 400 at the control plane. */}
        <SignInPrompt returnTo="/dashboard" />
      </main>
    );
  }

  if (result.kind === "error") {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <LoadError />
      </main>
    );
  }

  const repositories = result.data.repositories;

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
      <p className="text-muted-foreground mt-3 max-w-prose leading-relaxed">
        Only GitHub can grant or remove repository permission for this App.
      </p>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Connected repositories</CardTitle>
          <CardDescription>
            {repositories.length === 0
              ? "No repositories are connected yet."
              : `This installation permits ${repositories.length} ${
                  repositories.length === 1 ? "repository" : "repositories"
                }.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {repositories.length > 0 ? (
            <ul className="flex flex-col divide-y rounded-md border">
              {repositories.map((repo) => (
                <li
                  key={`${repo.installation_id}-${repo.github_repository_id}`}
                  className="px-3 py-2.5 font-mono text-sm"
                >
                  {repo.repository_name}
                </li>
              ))}
            </ul>
          ) : null}

          {INSTALL_URL ? (
            <a
              href={INSTALL_URL}
              className="bg-primary text-primary-foreground hover:bg-primary/90 mt-5 inline-flex h-10 items-center gap-2 rounded-md px-6 text-sm font-medium focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <GithubMark className="size-4" />
              Change repository permission on GitHub
            </a>
          ) : (
            <p className="text-muted-foreground mt-5 text-sm italic">
              The install link is unavailable because the App slug is not configured on
              this deployment.
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
