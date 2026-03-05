FROM python:3.11-slim

# System deps: ffmpeg for audio conversion, libmagic for MIME detection
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

WORKDIR /app

COPY pyproject.toml .
RUN uv sync --no-dev

COPY . .

# Token store dir
RUN mkdir -p .tokens && chmod 700 .tokens

EXPOSE 8080

CMD ["uv", "run", "python", "main.py"]
