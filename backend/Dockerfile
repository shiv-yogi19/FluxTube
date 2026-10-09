FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno: JavaScript runtime yt-dlp uses to solve YouTube's signature / "n" challenges.
# Official single-binary image; no install script or extra apt packages needed.
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno
RUN deno --version

WORKDIR /app
COPY requirements.txt .
# Change YTDLP_CACHEBUST (or pass --build-arg) to force a fresh yt-dlp install even
# when the Docker layer cache would otherwise reuse an old, outdated one.
ARG YTDLP_CACHEBUST=2026-10-09
RUN pip install --no-cache-dir -U -r requirements.txt \
    && python -m yt_dlp --version
COPY main.py .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
