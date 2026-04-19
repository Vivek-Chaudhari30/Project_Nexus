FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python deps from project spec + extras needed at runtime
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        fastapi==0.115.6 \
        "uvicorn[standard]==0.32.1" \
        pydantic==2.10.3 \
        pydantic-settings==2.7.0 \
        asyncpg==0.30.0 \
        "redis[hiredis]==5.2.1" \
        "python-jose[cryptography]==3.3.0" \
        "passlib[bcrypt]==1.7.4" \
        httpx==0.28.1 \
        langchain-core==0.3.28 \
        langchain-anthropic==0.3.3 \
        langchain-openai==0.3.3 \
        langchain-google-genai==2.0.8 \
        langgraph==0.4.1 \
        "langgraph-checkpoint>=2.0.10,<3.0.0" \
        langgraph-checkpoint-postgres==2.0.21 \
        openai==1.58.1 \
        anthropic==0.42.0 \
        "pinecone-client==5.0.1" \
        tavily-python==0.5.0 \
        grpcio==1.68.1 \
        grpcio-tools==1.68.1 \
        prometheus-client==0.21.1 \
        slowapi==0.1.9 \
        python-multipart==0.0.20 \
        beautifulsoup4==4.12.3 \
        structlog==24.4.0

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -u 1001 -m -s /sbin/nologin nexus

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY backend/ ./backend/

RUN chown -R nexus:nexus /app
USER nexus

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
