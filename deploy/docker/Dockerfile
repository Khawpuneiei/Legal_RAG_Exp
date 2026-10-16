# Production image for the API, the queue worker, migrations and the library sync job (one image, four commands).
# Multi-stage, non-root, no build tools or ML training dependencies in the runtime layer.
FROM python:3.12-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.8.17
WORKDIR /app
COPY pyproject.toml ./
RUN uv venv /opt/venv && VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r pyproject.toml --extra postgres

FROM python:3.12-slim
ARG GIT_SHA=unknown
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GIT_SHA=$GIT_SHA \
    APP_ENV=production DEMO_MODE=false STORE=postgres PROCESSING=queue PORT=8000 WEB_CONCURRENCY=2
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --home /app app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY src ./src
COPY configs ./configs
COPY db ./db
COPY skills ./skills
COPY data/synthetic ./data/synthetic
COPY eval/results ./eval/results
COPY docs/figures ./docs/figures
COPY index.py ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"
CMD ["sh", "-c", "exec gunicorn src.app.main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY} -b 0.0.0.0:${PORT} --timeout 120 --graceful-timeout 30 --access-logfile -"]
