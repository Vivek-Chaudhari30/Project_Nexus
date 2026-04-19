# Nexus sandbox — isolated Python execution container
# Section 9.3 spec: python:3.12-slim, non-root uid 1000, read-only root, 128MB /tmp tmpfs

FROM python:3.12-slim AS builder

# Install build deps + packages, then strip build tools
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    pip install --no-cache-dir \
        grpcio==1.68.1 \
        grpcio-tools==1.68.1 \
        pydantic==2.10.3 \
        httpx==0.28.1 \
        pandas==2.2.3 \
        numpy==2.2.0 \
        beautifulsoup4==4.12.3 && \
    pip uninstall -y pip setuptools wheel && \
    apt-get purge -y gcc && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

FROM python:3.12-slim

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/python3.12 /usr/local/bin/python3.12

# Non-root user
RUN useradd -u 1000 -m -s /sbin/nologin sandbox

# App files
WORKDIR /app
COPY sandbox/executor.proto    /app/executor.proto
COPY sandbox/server.py         /app/server.py
COPY sandbox/egress_allowlist.txt /app/egress_allowlist.txt
COPY sandbox/iptables-setup.sh /app/iptables-setup.sh

# Generate proto stubs inside the image (requires grpcio-tools)
RUN python -m grpc_tools.protoc \
      -I /app \
      --python_out=/app \
      --grpc_python_out=/app \
      /app/executor.proto

# Fix the generated grpc import to work from /app
RUN sed -i 's/^import executor_pb2/import executor_pb2/' /app/executor_pb2_grpc.py

RUN chown -R sandbox:sandbox /app

USER sandbox

ENV SANDBOX_GRPC_PORT=50051

ENTRYPOINT ["/app/iptables-setup.sh"]
CMD ["python", "/app/server.py"]
