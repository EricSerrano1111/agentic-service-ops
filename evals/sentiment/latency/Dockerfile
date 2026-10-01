# Throwaway latency-proxy image (ADR-065). Built locally by run_latency.py, never pushed.
#
# Installs exactly the uv.lock versions of the `bert` extra (requirements.txt is
# `uv export`ed from the lock by run_latency.py, with hashes), and copies in the pinned
# bert-base-uncased files, so it runs with --network none.

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
COPY requirements.txt /tmp/requirements.txt
# torch's +cpu build exists only on the PyTorch CPU index; every other package comes from
# PyPI. --require-hashes holds each file to the hash uv.lock recorded.
RUN uv pip install --system --no-deps --require-hashes -r /tmp/requirements.txt \
        --index-url https://pypi.org/simple \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        --index-strategy unsafe-best-match
COPY model /model
COPY bench.py /app/bench.py
WORKDIR /app
RUN useradd --system --uid 10001 bench
USER bench
