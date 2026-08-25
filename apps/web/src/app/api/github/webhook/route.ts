import { verifyGitHubSignature } from "@pr-reviewer/core/src/github/verifySignature";
import { enqueueReviewJob } from "@pr-reviewer/core/src/jobs/enqueueReviewJob";

export const MAX_WEBHOOK_BODY_BYTES = 1024 * 1024;

export async function POST(request: Request): Promise<Response> {
  const body = await readWebhookBody(request);
  if (body === null) {
    return Response.json({ error: "payload too large" }, { status: 413 });
  }

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

async function readWebhookBody(request: Request): Promise<Buffer | null> {
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null && Number(contentLength) > MAX_WEBHOOK_BODY_BYTES) {
    return null;
  }

  if (request.body === null) {
    return Buffer.alloc(0);
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        return Buffer.concat(chunks, size);
      }

      size += value.byteLength;
      if (size > MAX_WEBHOOK_BODY_BYTES) {
        await reader.cancel();
        return null;
      }

      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
}
