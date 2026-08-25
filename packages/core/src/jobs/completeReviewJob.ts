import { db } from "../db/client";

export async function completeReviewJob(jobId: string): Promise<void> {
  const result = await db.query<{ id: string }>(
    `update review_jobs
     set status = 'succeeded', updated_at = now()
     where id = $1 and status = 'running'
     returning id`,
    [jobId],
  );

  if (result.rowCount !== 1) {
    throw new Error(`Review job is not running: ${jobId}`);
  }
}
