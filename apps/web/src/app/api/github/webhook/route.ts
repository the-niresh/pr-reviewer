import { verifyGitHubSignature } from "@pr-reviewer/core/src/github/verifySignature";
import { enqueueReviewJob } from "@pr-reviewer/core/src/jobs/enqueueReviewJob";

export async function POST(request: Request): Promise<Response> {
  const body = Buffer.from(await request.arrayBuffer());
  const signature = request.headers.get("x-hub-signature-256") ?? "";
  const deliveryId = request.headers.get("x-github-delivery") ?? "";
  const eventName = request.headers.get("x-github-event") ?? "";

  if (!deliveryId || !eventName) {
    return Response.json({ error: "missing github headers" }, { status: 400 });
  }

  if (!verifyGitHubSignature(body, signature, process.env.GITHUB_WEBHOOK_SECRET ?? "")) {
    return Response.json({ error: "invalid signature" }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = JSON.parse(body.toString("utf8"));
  } catch {
    return Response.json({ error: "malformed json" }, { status: 400 });
  }

  const result = await enqueueReviewJob(deliveryId, eventName, payload);
  const status = result === "enqueued" ? 202 : 200;

  return Response.json({ result }, { status });
}
