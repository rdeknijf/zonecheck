FROM debian:trixie-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/

# uv installs the Python version that .python-version pins, outside /root so
# the app user can run it.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/cache && chown -R app:app /data

WORKDIR /app

COPY .python-version pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev && chown -R app:app /app

USER app

# The last good copy of each NDW feed lives here; mount a volume to keep it.
ENV CACHE_DIR=/data/cache

EXPOSE 8000

CMD [".venv/bin/uvicorn", "zonecheck.main:app", "--host", "0.0.0.0", "--port", "8000"]
