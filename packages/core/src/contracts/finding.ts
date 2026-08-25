import { z } from "zod";

export const FindingSchema = z.object({
  id: z.string().min(1),
  reviewJobId: z.string().min(1),
  concern: z.enum(["security", "correctness", "tests", "docs", "maintainability"]),
  severity: z.enum(["critical", "high", "medium", "low", "info"]),
  category: z.string().min(1),
  filePath: z.string().min(1),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  title: z.string().min(1),
  rationale: z.string().min(1),
  evidence: z.array(z.string().min(1)).min(1),
  confidence: z.number().min(0).max(1),
  verified: z.boolean(),
  verificationMethod: z.enum(["sandbox", "static", "not_applicable", "failed"]),
  publicSafe: z.boolean(),
  status: z.enum(["draft", "queued_for_human", "posted", "rejected", "disputed"]),
});

export type Finding = z.infer<typeof FindingSchema>;
