import { db } from "../db/client";

export async function failReviewJob(jobId: string, error: string): Promise<void> {
  const client = await db.connect();

  try {
    await client.query("begin");

    const result = await client.query<{ id: string }>(
      `update review_jobs
       set status = 'failed', updated_at = now()
       where id = $1 and status = 'running'
       returning id`,
      [jobId],
    );

    if (result.rowCount !== 1) {
      throw new Error(`Review job is not running: ${jobId}`);
    }

    await client.query(
      `insert into agent_events (review_job_id, event_type, payload)
       values ($1, $2, $3::jsonb)`,
      [jobId, "review_job_failed", JSON.stringify({ error })],
    );

    await client.query("commit");
  } catch (failure) {
    await client.query("rollback");
    throw failure;
  } finally {
    client.release();
  }
}
