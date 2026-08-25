import { z } from "zod";

export const PullRequestRefSchema = z.object({
  owner: z.string().min(1),
  repository: z.string().min(1),
  number: z.number().int().positive(),
});

export type PullRequestRef = z.infer<typeof PullRequestRefSchema>;

export const GitHubDeliverySchema = z.object({
  deliveryId: z.string().min(1),
  event: z.string().min(1),
  repository: z.string().min(1),
  pullRequest: PullRequestRefSchema,
});

export type GitHubDelivery = z.infer<typeof GitHubDeliverySchema>;
