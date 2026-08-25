import { db, type WorkerDatabaseClient } from "../db/client";

export type ReviewJobStatus = "pending" | "running" | "succeeded" | "failed";

export type ReviewJob = {
  id: string;
  deliveryId: string;
  pullRequestId: string | null;
  status: ReviewJobStatus;
  attempts: number;
  availableAt: Date;
  lockedBy: string | null;
  lockedUntil: Date | null;
  lastError: string | null;
  createdAt: Date;
  updatedAt: Date;
};

export const REVIEW_JOB_LEASE_INTERVAL = "5 minutes";

export async function claimReviewJob(workerId: string, client?: WorkerDatabaseClient): Promise<ReviewJob | null> {
  const result = await (client ?? db).query<ReviewJob>(
    `with next_job as (
       select id
       from review_jobs
       where (status = 'pending' and available_at <= now())
          or (status = 'running' and locked_until <= now())
       order by available_at asc, created_at asc
       for update skip locked
       limit 1
     )
     update review_jobs
     set status = 'running',
         locked_by = $1,
         locked_until = now() + $2::interval,
         attempts = attempts + 1,
         updated_at = now()
     where id = (select id from next_job)
     returning
       id,
       delivery_id as "deliveryId",
       pull_request_id as "pullRequestId",
       status,
       attempts,
       available_at as "availableAt",
       locked_by as "lockedBy",
       locked_until as "lockedUntil",
       last_error as "lastError",
       created_at as "createdAt",
       updated_at as "updatedAt"`,
    [workerId, REVIEW_JOB_LEASE_INTERVAL],
  );

  return result.rows[0] ?? null;
}
