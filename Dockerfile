# Same image runs locally (docker compose) and on Cloud Run Jobs.
# Build with a browser for JS-heavy sites:  docker build --build-arg WITH_BROWSER=1 -t rice-tracker .
FROM python:3.12-slim

ARG WITH_BROWSER=0
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[gcp]" \
 && if [ "$WITH_BROWSER" = "1" ]; then pip install ".[browser]" && playwright install --with-deps chromium; fi

COPY config ./config

# Cloud Run Jobs pass the args (e.g. `run --tier 1`); default shows help.
ENTRYPOINT ["tracker"]
CMD ["--help"]
