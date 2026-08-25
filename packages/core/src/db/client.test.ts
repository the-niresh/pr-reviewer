import { afterEach, describe, expect, it, vi } from "vitest";

const pool = vi.hoisted(() => ({
  connect: vi.fn(),
  end: vi.fn(),
}));

vi.mock("pg", () => ({
  Pool: class {
    connect = pool.connect;
    end = pool.end;
  },
}));

import { db, runWorkerDatabaseOperation } from "./client";

describe("runWorkerDatabaseOperation", () => {
  afterEach(() => {
    pool.connect.mockReset();
    pool.end.mockReset();
  });

  it("destroys a hung worker client during shutdown so pool shutdown finishes", async () => {
    const controller = new AbortController();
    let released = false;
    const release = vi.fn(() => {
      released = true;
    });
    const query = vi.fn(() => new Promise<void>(() => {}));
    pool.connect.mockResolvedValue({
      query,
      release,
    });
    pool.end.mockImplementation(() => (released ? Promise.resolve() : new Promise<void>(() => {})));

    const operation = runWorkerDatabaseOperation(
      async (client) => client.query("select pg_sleep(60)"),
      { signal: controller.signal, timeoutMs: 60_000 },
    );

    await waitFor(() => expect(pool.connect).toHaveBeenCalledOnce());
    await waitFor(() => expect(query).toHaveBeenCalledOnce());
    controller.abort();

    await expect(operation).rejects.toThrow("Worker database operation aborted");
    await expect(settlesWithin(db.end(), 100)).resolves.toBe(true);
    expect(release).toHaveBeenCalledWith(expect.any(Error));
  });

  it("destroys a timed out worker client so pool shutdown finishes", async () => {
    let released = false;
    const release = vi.fn(() => {
      released = true;
    });
    const query = vi.fn(() => new Promise<void>(() => {}));
    pool.connect.mockResolvedValue({ query, release });
    pool.end.mockImplementation(() => (released ? Promise.resolve() : new Promise<void>(() => {})));

    const operation = runWorkerDatabaseOperation(
      async (client) => client.query("select pg_sleep(60)"),
      { signal: new AbortController().signal, timeoutMs: 20 },
    );

    await waitFor(() => expect(query).toHaveBeenCalledOnce());

    await expect(operation).rejects.toThrow("Worker database operation timed out");
    await expect(settlesWithin(db.end(), 100)).resolves.toBe(true);
    expect(release).toHaveBeenCalledWith(expect.any(Error));
  });
});

async function settlesWithin(promise: Promise<void>, timeoutMs: number): Promise<boolean> {
  return Promise.race([
    promise.then(() => true),
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), timeoutMs)),
  ]);
}

async function waitFor(assertion: () => void): Promise<void> {
  const deadline = Date.now() + 100;

  while (true) {
    try {
      assertion();
      return;
    } catch (error) {
      if (Date.now() >= deadline) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
  }
}
