import { db } from "../db/client";

export type ReviewJobStatus = "pending" | "running" | "succeeded" | "failed";

export type ReviewJob = {
  id: string;
  deliveryId: string;
  pullRequestId: string | null;
  status: ReviewJobStatus;
  attempts: number;
  availableAt: Date;
  createdAt: Date;
  updatedAt: Date;
};

export async function claimReviewJob(_workerId: string): Promise<ReviewJob | null> {
  const result = await db.query<ReviewJob>(`
    update review_jobs
    set status = 'running', attempts = attempts + 1, updated_at = now()
    where id = (
      select id
      from review_jobs
      where status = 'pending' and available_at <= now()
      order by created_at asc
      for update skip locked
      limit 1
    )
    returning
      id,
      delivery_id as "deliveryId",
      pull_request_id as "pullRequestId",
      status,
      attempts,
      available_at as "availableAt",
      created_at as "createdAt",
      updated_at as "updatedAt"
  `);

  return result.rows[0] ?? null;
}
