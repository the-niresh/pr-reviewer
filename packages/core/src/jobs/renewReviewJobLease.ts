import { db, type WorkerDatabaseClient } from "../db/client";
import { REVIEW_JOB_LEASE_INTERVAL } from "./claimReviewJob";

export async function renewReviewJobLease(jobId: string, workerId: string, client?: WorkerDatabaseClient): Promise<void> {
  const result = await (client ?? db).query<{ id: string }>(
    `update review_jobs
     set locked_until = now() + $3::interval, updated_at = now()
     where id = $1
       and status = 'running'
       and locked_by = $2
       and locked_until > now()
     returning id`,
    [jobId, workerId, REVIEW_JOB_LEASE_INTERVAL],
  );

  if (result.rowCount !== 1) {
    throw new Error(`Review job lease is not owned by worker: ${jobId}`);
  }
}
