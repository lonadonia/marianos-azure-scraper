# marianos-azure-headless: one container image for every command (scheduled job and manual operations).
# Build:  docker build --build-arg SOURCE_COMMIT=$(git rev-parse HEAD) -t marianos-collector:1.2.1 .
#   or:   az acr build --registry <acr> --image marianos-collector:1.2.1 --build-arg SOURCE_COMMIT=<sha> .
# No secret is ever baked in: the Scrapfly key and the database come from the job's environment.
# The Playwright package's driver connects to Scrapfly's cloud browser over CDP: no browser is installed.

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
ARG SOURCE_COMMIT=unknown
ARG BUILT_AT=unknown
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MARIANOS_COLLECTOR_CONFIG=/app/config/collector.yaml \
    MARIANOS_COLLECTOR_DATA_DIR=/app/data
RUN groupadd --system --gid 10001 collector && useradd --system --uid 10001 --gid collector --home /app collector
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
COPY config ./config
RUN printf '{"commit": "%s", "built_at": "%s"}\n' "$SOURCE_COMMIT" "$BUILT_AT" > /app/BUILD_INFO.json \
    && mkdir -p /app/data && chown collector:collector /app/data
USER collector
# Each Azure job passes its own command, e.g. ["run", "--store", "marianos-53100503-instore", "--scheduled"].
ENTRYPOINT ["marianos-collector"]
CMD ["validate-config"]
