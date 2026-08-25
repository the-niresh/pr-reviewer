import { afterEach, describe, expect, it, vi } from "vitest";

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock("../db/client", () => ({
  db: { query },
}));

import { completeReviewJob } from "./completeReviewJob";

describe("completeReviewJob", () => {
  afterEach(() => {
    query.mockReset();
  });

  it("marks a running job as succeeded", async () => {
    query.mockResolvedValueOnce({ rowCount: 1, rows: [{ id: "job-1" }] });

    await expect(completeReviewJob("job-1", "worker-1")).resolves.toBeUndefined();

    expect(query).toHaveBeenCalledWith(
      expect.stringContaining("status = 'succeeded'"),
      ["job-1", "worker-1"],
    );
    expect(query).toHaveBeenCalledWith(expect.stringContaining("locked_by = $2"), ["job-1", "worker-1"]);
  });

  it("rejects when the job is not running", async () => {
    query.mockResolvedValueOnce({ rowCount: 0, rows: [] });

    await expect(completeReviewJob("job-1", "worker-1")).rejects.toThrow(
      "Review job is not owned by worker: job-1",
    );
  });
});
