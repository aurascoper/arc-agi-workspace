FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (required by codopt) and numpy (required by dsl.py)
RUN pip install --no-cache-dir uv numpy

WORKDIR /workspace
