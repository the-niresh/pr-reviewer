FROM ghcr.io/astral-sh/uv:0.9.30@sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4 AS uv

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS python-deps
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev
ENV PATH=/app/.venv/bin:$PATH

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS api
COPY --from=python-deps /app /app
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH
USER 65532:65532
EXPOSE 8000
ENTRYPOINT ["/app/.venv/bin/pr-reviewer-api"]

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS worker
COPY --from=python-deps /app /app
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH
USER 65532:65532
ENTRYPOINT ["/app/.venv/bin/pr-reviewer-worker"]

FROM oven/bun:1.3.11-slim@sha256:478281fdd196871c7e51ba6a820b7803a8ae97042ec86cdbc2e1c6b6626442d9 AS ui-build
WORKDIR /app
COPY apps/web/package.json apps/web/bun.lock ./
RUN bun install --frozen-lockfile
COPY apps/web ./
COPY docs/reports /docs/reports
ENV NEXT_TELEMETRY_DISABLED=1
RUN bun run build

FROM oven/bun:1.3.11-slim@sha256:478281fdd196871c7e51ba6a820b7803a8ae97042ec86cdbc2e1c6b6626442d9 AS ui
WORKDIR /app
COPY --from=ui-build --chown=65532:65532 /app /app
USER 65532:65532
EXPOSE 3000
ENTRYPOINT ["bun", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
