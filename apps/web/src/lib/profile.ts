import { CONTROL_PLANE_ORIGIN } from "@/lib/reviews";

export type Profile = {
  github_user_id: number;
  login: string | null;
};

export type FetchProfileResult =
  | { kind: "unauthenticated" }
  | { kind: "error" }
  | { kind: "ok"; profile: Profile };

/** Backs /dashboard/profile. Same three-outcome shape as fetchReviews: signed-out and
 *  broken must never render the same way. */
export async function fetchProfile(cookieHeader: string): Promise<FetchProfileResult> {
  let response: Response;
  try {
    response = await fetch(`${CONTROL_PLANE_ORIGIN}/api/profile`, {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
  } catch {
    return { kind: "error" };
  }
  if (response.status === 401) {
    return { kind: "unauthenticated" };
  }
  if (!response.ok) {
    return { kind: "error" };
  }
  const profile = (await response.json()) as Profile;
  return { kind: "ok", profile };
}
