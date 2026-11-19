# A reproducible environment for compiling the contracts and running the tests.
# No external blockchain node is needed: Ape runs a local chain in-process.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd -ms /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

# 1. Python dependencies (cached unless pyproject.toml / uv.lock change)
COPY --chown=appuser:appuser pyproject.toml uv.lock README.md ./
COPY --chown=appuser:appuser rain/ ./rain
RUN uv sync --frozen

# 2. Compile the contracts (cached unless they change). This also downloads the
#    Solidity compiler and the OpenZeppelin dependency into the image.
COPY --chown=appuser:appuser ape-config.yaml .
COPY --chown=appuser:appuser contracts/ ./contracts
RUN uv run ape compile

# 3. Everything else (tests and scripts change most often)
COPY --chown=appuser:appuser . .

CMD ["uv", "run", "ape", "test"]
