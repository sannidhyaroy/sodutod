FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY bot/ bot/
COPY main.py rules.md ./

VOLUME /data

CMD ["uv", "run", "--no-sync", "main.py"]
