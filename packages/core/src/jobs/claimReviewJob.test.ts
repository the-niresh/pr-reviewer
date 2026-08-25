import { afterEach, describe, expect, it, vi } from "vitest";

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock("../db/client", () => ({
  db: { query },
}));

import { claimReviewJob } from "./claimReviewJob";

describe("claimReviewJob", () => {
  afterEach(() => {
    query.mockReset();
  });

  it("claims one available pending job and marks it running", async () => {
    query.mockResolvedValueOnce({
      rowCount: 1,
      rows: [
        {
          id: "job-1",
          deliveryId: "delivery-1",
          pullRequestId: null,
          status: "running",
          attempts: 1,
          availableAt: new Date("2026-08-25T00:00:00.000Z"),
          createdAt: new Date("2026-08-25T00:00:00.000Z"),
          updatedAt: new Date("2026-08-25T00:01:00.000Z"),
        },
      ],
    });

    await expect(claimReviewJob("worker_test_1")).resolves.toMatchObject({
      id: "job-1",
      status: "running",
      attempts: 1,
    });

    expect(query).toHaveBeenCalledWith(
      expect.stringContaining("status = 'pending' and available_at <= now()"),
    );
    expect(query).toHaveBeenCalledWith(expect.stringContaining("for update skip locked"));
    expect(query).toHaveBeenCalledWith(expect.stringContaining("attempts = attempts + 1"));
  });

  it("returns null when no pending job is available", async () => {
    query.mockResolvedValueOnce({ rowCount: 0, rows: [] });

    await expect(claimReviewJob("worker_test_1")).resolves.toBeNull();
  });
});
