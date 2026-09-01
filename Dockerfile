FROM busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 AS api
USER 65532:65532
WORKDIR /app
COPY src/pr_reviewer /app/pr_reviewer

FROM busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 AS worker
USER 65532:65532
WORKDIR /app
COPY src/pr_reviewer /app/pr_reviewer

FROM busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 AS ui
USER 65532:65532
WORKDIR /app
COPY apps/web/package.json /app/package.json

FROM busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 AS sandbox
USER 65532:65532
WORKDIR /work
