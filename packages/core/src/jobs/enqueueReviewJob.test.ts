import { afterEach, describe, expect, it, vi } from "vitest";

const { connect } = vi.hoisted(() => ({ connect: vi.fn() }));

vi.mock("../db/client", () => ({
  db: { connect },
}));

import { enqueueReviewJob } from "./enqueueReviewJob";

describe("enqueueReviewJob", () => {
  afterEach(() => {
    connect.mockReset();
  });

  it("ignores non-pull-request events without opening a database connection", async () => {
    await expect(enqueueReviewJob("delivery-1", "push", {})).resolves.toBe("ignored");

    expect(connect).not.toHaveBeenCalled();
  });

  it("inserts a delivery and a pending review job in one transaction", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rowCount: null })
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ id: "delivery-1" }] })
      .mockResolvedValueOnce({ rowCount: 1 })
      .mockResolvedValueOnce({ rowCount: null });
    const release = vi.fn();
    connect.mockResolvedValue({ query, release });

    await expect(enqueueReviewJob("delivery-1", "pull_request", {})).resolves.toBe("enqueued");

    expect(query).toHaveBeenNthCalledWith(1, "begin");
    expect(query).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("insert into github_deliveries"),
      ["delivery-1", "pull_request"],
    );
    expect(query).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("insert into review_jobs"),
      ["delivery-1"],
    );
    expect(query).toHaveBeenNthCalledWith(4, "commit");
    expect(release).toHaveBeenCalledOnce();
  });

  it("rolls back and returns duplicate when the delivery already exists", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rowCount: null })
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      .mockResolvedValueOnce({ rowCount: null });
    const release = vi.fn();
    connect.mockResolvedValue({ query, release });

    await expect(enqueueReviewJob("delivery-1", "pull_request", {})).resolves.toBe("duplicate");

    expect(query).toHaveBeenNthCalledWith(3, "rollback");
    expect(release).toHaveBeenCalledOnce();
  });
});
