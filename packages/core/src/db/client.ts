import { Pool, type PoolClient } from "pg";

export const localDatabaseUrl =
  "postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer";

export const databaseUrl = process.env.DATABASE_URL ?? localDatabaseUrl;

export const db = new Pool({ connectionString: databaseUrl });

export type WorkerDatabaseClient = Pick<PoolClient, "query">;

export class WorkerDatabaseOperationAbortedError extends Error {
  constructor() {
    super("Worker database operation aborted");
  }
}

export class WorkerDatabaseOperationTimedOutError extends Error {
  constructor(timeoutMs: number) {
    super(`Worker database operation timed out after ${timeoutMs}ms`);
  }
}

export async function runWorkerDatabaseOperation<T>(
  operation: (client: WorkerDatabaseClient) => Promise<T>,
  { signal, timeoutMs }: { signal: AbortSignal; timeoutMs: number },
): Promise<T> {
  let client: PoolClient | undefined;
  let releaseError: Error | undefined;
  let released = false;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let rejectInterruption: ((reason: Error) => void) | undefined;

  const releaseClient = (error: Error) => {
    releaseError = error;
    if (client !== undefined && !released) {
      client.release(error);
      released = true;
    }
  };

  const interruption = new Promise<never>((_resolve, reject) => {
    rejectInterruption = (error) => {
      if (releaseError !== undefined) {
        return;
      }
      releaseClient(error);
      reject(error);
    };
  });
  const onAbort = () => rejectInterruption?.(new WorkerDatabaseOperationAbortedError());

  if (signal.aborted) {
    onAbort();
  } else {
    signal.addEventListener("abort", onAbort, { once: true });
  }
  timeout = setTimeout(() => rejectInterruption?.(new WorkerDatabaseOperationTimedOutError(timeoutMs)), timeoutMs);

  const connection = db.connect();
  void connection.then(
    (lateClient) => {
      if (releaseError !== undefined) {
        lateClient.release(releaseError);
        released = true;
      }
    },
    () => {},
  );

  try {
    client = await Promise.race([connection, interruption]);
    if (releaseError !== undefined) {
      throw releaseError;
    }
    return await Promise.race([operation(client), interruption]);
  } finally {
    signal.removeEventListener("abort", onAbort);
    clearTimeout(timeout);
    if (client !== undefined && !released) {
      client.release();
    }
  }
}
