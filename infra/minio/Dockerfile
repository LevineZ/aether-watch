# Official minio/minio Hub tags are often login-walled after the AIStor split.
# Pin the last AGPL community server binary from GitHub Releases instead.
FROM debian:bookworm-slim

ARG TARGETARCH=amd64
ARG MINIO_RELEASE=RELEASE.2024-11-07T00-52-20Z

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && arch="$TARGETARCH" \
    && curl -fsSL -o /usr/local/bin/minio \
      "https://github.com/minio/minio/releases/download/${MINIO_RELEASE}/minio.linux-${arch}.${MINIO_RELEASE}" \
    && chmod +x /usr/local/bin/minio \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
