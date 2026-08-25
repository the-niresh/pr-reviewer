import { db } from "../db/client";

export const MAX_REVIEW_JOB_ATTEMPTS = 3;
export const REVIEW_JOB_RETRY_INTERVAL = "1 minute";

type FailedReviewJob = {
  id: string;
  status: "pending" | "failed";
};

export async function failReviewJob(jobId: string, workerId: string, error: string): Promise<void> {
  const client = await db.connect();

  try {
    await client.query("begin");

    const result = await client.query<FailedReviewJob>(
      `update review_jobs
       set status = case when attempts >= $3 then 'failed' else 'pending' end,
           available_at = case when attempts >= $3 then available_at else now() + $4::interval end,
           locked_by = null,
           locked_until = null,
           last_error = $5,
           updated_at = now()
       where id = $1 and status = 'running' and locked_by = $2
       returning id, status`,
      [jobId, workerId, MAX_REVIEW_JOB_ATTEMPTS, REVIEW_JOB_RETRY_INTERVAL, error],
    );

    if (result.rowCount !== 1) {
      throw new Error(`Review job is not owned by worker: ${jobId}`);
    }

    const job = result.rows[0];
    await client.query(
      `insert into agent_events (review_job_id, event_type, payload)
       values ($1, $2, $3::jsonb)`,
      [
        jobId,
        job.status === "failed" ? "review_job_failed" : "review_job_retry_scheduled",
        JSON.stringify({ error, status: job.status }),
      ],
    );

    await client.query("commit");
  } catch (failure) {
    await client.query("rollback");
    throw failure;
  } finally {
    client.release();
  }
}
