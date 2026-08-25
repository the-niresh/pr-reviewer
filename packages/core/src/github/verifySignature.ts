import { createHmac, timingSafeEqual } from "node:crypto";

const signaturePrefix = "sha256=";

export function verifyGitHubSignature(
  body: Buffer,
  signature: string,
  secret: string,
): boolean {
  if (!secret || !signature.startsWith(signaturePrefix)) {
    return false;
  }

  const signatureHex = signature.slice(signaturePrefix.length);
  if (!/^[a-f0-9]{64}$/i.test(signatureHex)) {
    return false;
  }

  const actual = Buffer.from(signatureHex, "hex");
  const expected = createHmac("sha256", secret).update(body).digest();

  return timingSafeEqual(actual, expected);
}
