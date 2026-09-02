import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { GithubMark } from "@/components/github-mark";

// GitHub cannot show a repository to an App that is not installed on it, and the
// install/permission flow is the same GitHub-hosted step either way, so this page has
// exactly one thing to do: point at it.
const APP_SLUG = process.env.NEXT_PUBLIC_GITHUB_APP_SLUG ?? "";
const INSTALL_URL = APP_SLUG ? `https://github.com/apps/${APP_SLUG}/installations/new` : "";

export const metadata = {
  title: "Choose repositories",
};

export default function ConnectPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6 py-16">
      <Card>
        <CardHeader>
          <CardTitle>Choose repositories</CardTitle>
          <CardDescription>
            GitHub only shows this App the repositories you pick. Choose them once and
            reviewer can start reviewing pull requests against them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {INSTALL_URL ? (
            <a
              href={INSTALL_URL}
              className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md px-6 text-sm font-medium"
            >
              <GithubMark className="size-4" />
              Choose repositories on GitHub
            </a>
          ) : (
            <p className="text-muted-foreground text-sm italic">
              The install link is unavailable because the App slug is not configured on
              this deployment.
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
