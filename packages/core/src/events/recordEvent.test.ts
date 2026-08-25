import { afterEach, describe, expect, it, vi } from "vitest";

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock("../db/client", () => ({
  db: { query },
}));

import { listEventsForJob } from "./listEventsForJob";
import { recordEvent } from "./recordEvent";

describe("event spine", () => {
  afterEach(() => {
    query.mockReset();
  });

  it("records a time ordered event with review job id", async () => {
    query.mockResolvedValueOnce({ rowCount: 1, rows: [] });

    await recordEvent({
      reviewJobId: "00000000-0000-0000-0000-000000000001",
      eventType: "webhook.accepted",
      payload: { deliveryId: "delivery_1" },
    });

    expect(query).toHaveBeenCalledWith(
      expect.stringContaining("insert into agent_events"),
      [
        "00000000-0000-0000-0000-000000000001",
        "webhook.accepted",
        JSON.stringify({ deliveryId: "delivery_1" }),
      ],
    );
  });

  it("lists events by append sequence", async () => {
    const createdAt = new Date("2026-08-26T10:00:00.000Z");
    query.mockResolvedValueOnce({
      rowCount: 2,
      rows: [
        {
          id: "00000000-0000-0000-0000-000000000001",
          sequence: "7",
          reviewJobId: "job-1",
          eventType: "webhook.accepted",
          payload: { deliveryId: "delivery-1" },
          createdAt,
        },
      ],
    });

    await expect(listEventsForJob("job-1")).resolves.toEqual([
      {
        id: "00000000-0000-0000-0000-000000000001",
        sequence: "7",
        reviewJobId: "job-1",
        eventType: "webhook.accepted",
        payload: { deliveryId: "delivery-1" },
        createdAt,
      },
    ]);

    expect(query).toHaveBeenCalledWith(
      expect.stringContaining("order by sequence asc"),
      ["job-1"],
    );
  });

  it("rejects invalid JSON payloads before insertion", async () => {
    await expect(
      recordEvent({
        reviewJobId: "job-1",
        eventType: "webhook.accepted",
        payload: { count: Number.NaN },
      }),
    ).rejects.toThrow("Expected a finite JSON number");

    expect(query).not.toHaveBeenCalled();
  });
});
