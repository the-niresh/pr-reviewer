import { afterEach, describe, expect, it, vi } from "vitest";

const { connect } = vi.hoisted(() => ({ connect: vi.fn() }));

vi.mock("../db/client", () => ({
  db: { connect },
}));

import { failReviewJob } from "./failReviewJob";

describe("failReviewJob", () => {
  afterEach(() => {
    connect.mockReset();
  });

  it("marks a running job failed and stores the error in the event log", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rowCount: null })
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ id: "job-1", status: "pending" }] })
      .mockResolvedValueOnce({ rowCount: 1 })
      .mockResolvedValueOnce({ rowCount: null });
    const release = vi.fn();
    connect.mockResolvedValue({ query, release });

    await expect(failReviewJob("job-1", "worker-1", "GitHub request failed")).resolves.toBeUndefined();

    expect(query).toHaveBeenNthCalledWith(1, "begin");
    expect(query).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("then 'failed' else 'pending'"),
      ["job-1", "worker-1", 3, "1 minute", "GitHub request failed"],
    );
    expect(query).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("insert into agent_events"),
      [
        "job-1",
        "review_job_retry_scheduled",
        JSON.stringify({ error: "GitHub request failed", status: "pending" }),
      ],
    );
    expect(query).toHaveBeenNthCalledWith(4, "commit");
    expect(release).toHaveBeenCalledOnce();
  });

  it("rolls back when the job is not running", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rowCount: null })
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      .mockResolvedValueOnce({ rowCount: null });
    const release = vi.fn();
    connect.mockResolvedValue({ query, release });

    await expect(failReviewJob("job-1", "worker-1", "GitHub request failed")).rejects.toThrow(
      "Review job is not owned by worker: job-1",
    );

    expect(query).toHaveBeenNthCalledWith(3, "rollback");
    expect(release).toHaveBeenCalledOnce();
  });
});
