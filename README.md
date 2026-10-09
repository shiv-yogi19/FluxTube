# FluxTube — YouTube Downloader Starter

A small, security-conscious starter project with:
- Static frontend (deploy on GitHub Pages or Cloudflare Pages)
- FastAPI + yt-dlp backend (deploy separately, e.g. a Docker-capable host)
- YouTube-only URL allowlist
- Video/audio modes, available-format listing, playlist item selection
- Temporary server-side files, deleted after the response completes
- No permanent storage of downloaded media

## Important limitations

This is a starter, not a promise of unlimited production service. Long downloads and large playlists may exceed free-host request timeouts, memory/disk quotas, or bandwidth limits. The synchronous download endpoint is intended for initial testing. For a more robust production deployment, replace it with a background job queue and expiring download links.

Only download content you own, have permission to download, or that the platform makes available for downloading. Do not use this project to bypass DRM, private-content restrictions, authentication, or platform access controls.

## Project layout

```text
FluxTube/
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── backend/
    ├── main.py
    ├── requirements.txt
    ├── Dockerfile
    └── .env.example
```

## 1. Run backend locally

Python 3.11+ is recommended. FFmpeg is needed for merging separate streams and MP3 conversion.

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Health check: `http://127.0.0.1:8000/health`

If FFmpeg is missing, metadata and some downloads may still work, but merged high-resolution video or MP3 conversion may fail.

## 2. Configure the frontend

Open `frontend/app.js` and change `API_BASE` to your deployed backend URL, e.g.:

```js
const API_BASE = "https://YOUR-BACKEND.example.com";
```

Do not include a trailing slash.

For local testing, serve the frontend from a local HTTP server rather than opening the file directly:
```bash
cd frontend
python -m http.server 8080
```
Then open `http://127.0.0.1:8080`.

## 3. Deploy backend

Use a Docker-capable host. The included Dockerfile installs FFmpeg and the Python dependencies. Configure the host to build from `backend/Dockerfile` with `backend` as build context if the dashboard asks for both. Set the service's health-check path to `/health`.

After deployment, test:
- `https://YOUR-BACKEND/health`
- `https://YOUR-BACKEND/docs`

Set `CORS_ORIGINS` to the exact frontend origin(s), comma-separated. Example:
`https://YOUR-USERNAME.github.io,https://your-site.pages.dev`

Do not use `*` for production CORS. CORS is not authentication; public endpoints can still be called by scripts. Before exposing this publicly, add rate limits, abuse controls, job limits, and a proper background queue.

## 4. Deploy frontend

Publish the `frontend/` directory as a static site. GitHub Pages or Cloudflare Pages can host it. Set `API_BASE` first, then redeploy.

## API

- `GET /health` — service/FFmpeg health
- `POST /api/info` — JSON body `{"url":"https://www.youtube.com/watch?v=..."}`
- `POST /api/download` — JSON body:
  `{"url":"...","mode":"video","quality":"best","playlist_items":[1,2]}`
  `mode` is `video` or `audio`; `quality` is `best`, `1080`, `720`, `480`, or `360`.
  `playlist_items` omitted or empty means all available playlist entries (subject to configured item limit); list values are 1-based playlist positions.

## Security notes

- The API accepts YouTube URLs only and rejects other hostnames.
- No shell command is constructed from user input.
- Downloaded files live in a per-request temporary directory and are cleaned up after the response.
- Playlist size is capped with `MAX_PLAYLIST_ITEMS`.
- This is not sufficient on its own for a high-traffic public service. Add per-IP rate limiting, authentication/quotas, worker isolation, and a queue before production.
