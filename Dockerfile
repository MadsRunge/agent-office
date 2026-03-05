FROM python:3.11-slim
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev
COPY . .
EXPOSE 8080
CMD ["uv", "run", "python", "main.py"]
