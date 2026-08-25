import { describe, expect, it } from "vitest";
import { FindingSchema } from "./finding";

describe("FindingSchema", () => {
  it("requires evidence and verification status", () => {
    const parsed = FindingSchema.parse({
      id: "finding_1",
      reviewJobId: "job_1",
      concern: "security",
      severity: "high",
      category: "sql-injection",
      filePath: "src/api/users.ts",
      lineStart: 42,
      lineEnd: 44,
      title: "Unsafe raw SQL input",
      rationale: "The query joins user input into SQL text.",
      evidence: ["src/api/users.ts:42 uses request.query.name"],
      confidence: 0.82,
      verified: false,
      verificationMethod: "not_applicable",
      publicSafe: false,
      status: "queued_for_human",
    });

    expect(parsed.publicSafe).toBe(false);
  });

  it("rejects findings without exact location", () => {
    expect(() =>
      FindingSchema.parse({
        id: "finding_1",
        reviewJobId: "job_1",
        concern: "tests",
        severity: "medium",
        category: "missing-test",
        title: "Missing regression test",
        rationale: "The changed branch is not covered.",
        evidence: ["diff hunk mentions new branch"],
        confidence: 0.7,
        verified: false,
        verificationMethod: "not_applicable",
        publicSafe: true,
        status: "draft",
      }),
    ).toThrow();
  });
});
