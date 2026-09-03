import { cookies } from "next/headers";

import { GithubMark } from "@/components/github-mark";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadError, SignInPrompt } from "@/components/DashboardState";
import { fetchProfile } from "@/lib/profile";

export const metadata = {
  title: "Profile",
};

export default async function ProfilePage() {
  const cookieStore = await cookies();
  const result = await fetchProfile(cookieStore.toString());

  if (result.kind === "unauthenticated") {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Profile</h1>
        {/* /dashboard/profile is not in the hosted allowlist (github_oauth.py's
            ALLOWED_RETURN_TO_PATHS is only /dashboard and /dashboard/reviews); passing it
            here made the sign-in link 400 at the control plane. */}
        <SignInPrompt returnTo="/dashboard" />
      </main>
    );
  }

  if (result.kind === "error") {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Profile</h1>
        <LoadError />
      </main>
    );
  }

  const { profile } = result;

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Profile</h1>
      <Card className="mt-8">
        <CardHeader>
          <div className="flex items-center gap-3">
            <GithubMark className="size-8 shrink-0" />
            <div>
              {/* A session sealed before login was captured has none yet; a fresh
                  sign-in always fills it in, so this is honest rather than a placeholder. */}
              <CardTitle>{profile.login ?? "Signed in with GitHub"}</CardTitle>
              <CardDescription className="font-mono text-xs">
                GitHub id {profile.github_user_id}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
      </Card>
    </main>
  );
}
