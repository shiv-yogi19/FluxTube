// Change this to your deployed API origin. No trailing slash.
const API_BASE = "http://127.0.0.1:8000";

const $ = (id) => document.getElementById(id);
const urlInput = $("url");
const inspectBtn = $("inspect");
const downloadBtn = $("download");
const statusEl = $("status");
const details = $("details");
const playlistArea = $("playlist-area");
const playlistItems = $("playlist-items");
let currentInfo = null;
let ready = false;

function status(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`;
}
function fmtDuration(seconds) {
  if (!Number.isFinite(Number(seconds))) return "Duration unavailable";
  const s = Number(seconds);
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
async function requestJson(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Server returned HTTP ${response.status}`);
  return data;
}
async function checkServer() {
  inspectBtn.disabled = true;
  downloadBtn.disabled = true;
  status("Checking whether the download server is ready…");
  try {
    const response = await fetch(`${API_BASE}/health`, {cache: "no-store"});
    if (!response.ok) throw new Error(`Health check failed (${response.status})`);
    const data = await response.json();
    ready = data.status === "ok";
    if (!ready) throw new Error("Server has not reported ready.");
    status(`Server ready · FFmpeg ${data.ffmpeg ? "available" : "not detected"} · playlist limit ${data.max_playlist_items}`, "ok");
    inspectBtn.disabled = false;
  } catch (e) {
    ready = false;
    status(`Server is not reachable: ${e.message}. Check API_BASE and backend deployment.`, "error");
  }
}
function renderInfo(info) {
  currentInfo = info;
  $("media-title").textContent = info.title || "YouTube media";
  $("media-meta").textContent = `${info.uploader || "Channel unavailable"} · ${fmtDuration(info.duration)}${info.is_playlist ? ` · playlist (${info.playlist_count || info.items.length} items)` : ""}`;
  const thumb = $("thumb");
  if (info.thumbnail) { thumb.src = info.thumbnail; thumb.classList.remove("hidden"); }
  else { thumb.removeAttribute("src"); thumb.classList.add("hidden"); }
  playlistItems.replaceChildren();
  if (info.is_playlist) {
    playlistArea.classList.remove("hidden");
    (info.items || []).forEach((item) => {
      const label = document.createElement("label");
      label.className = "playlist-item";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.dataset.position = String(item.position);
      const pos = document.createElement("span");
      pos.textContent = String(item.position).padStart(2, "0");
      const title = document.createElement("strong");
      title.textContent = item.title || `Video ${item.position}`;
      label.append(checkbox, pos, title);
      playlistItems.append(label);
    });
  } else {
    playlistArea.classList.add("hidden");
  }
  details.classList.remove("hidden");
  downloadBtn.disabled = false;
}
inspectBtn.addEventListener("click", async () => {
  if (!ready) return status("Download server is not ready yet.", "error");
  const url = urlInput.value.trim();
  if (!url) return status("Paste a YouTube link first.", "error");
  inspectBtn.disabled = true;
  details.classList.add("hidden");
  status("Reading video and playlist information…");
  try {
    const info = await requestJson("/api/info", {url});
    renderInfo(info);
    status("Link inspected successfully.", "ok");
  } catch (e) {
    status(e.message, "error");
  } finally {
    inspectBtn.disabled = !ready;
  }
});
$("select-all").addEventListener("click", () => playlistItems.querySelectorAll("input").forEach((x) => x.checked = true));
$("select-none").addEventListener("click", () => playlistItems.querySelectorAll("input").forEach((x) => x.checked = false));

downloadBtn.addEventListener("click", async () => {
  if (!ready || !currentInfo) return;
  const selected = [...playlistItems.querySelectorAll("input:checked")].map(x => Number(x.dataset.position));
  if (currentInfo.is_playlist && !selected.length) return status("Select at least one playlist item.", "error");
  const body = {
    url: urlInput.value.trim(),
    mode: $("mode").value,
    quality: $("quality").value,
    playlist_items: currentInfo.is_playlist ? selected : []
  };
  inspectBtn.disabled = true;
  downloadBtn.disabled = true;
  status("Download started on the server. Large downloads may take time; keep this page open…");
  try {
    const response = await fetch(`${API_BASE}/api/download`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || `Download failed (${response.status})`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : (body.mode === "audio" ? "FluxTube_Audio.mp3" : "FluxTube_Video");
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
    status("The server returned a file. Check your browser's downloads.", "ok");
  } catch (e) {
    status(e.message, "error");
  } finally {
    inspectBtn.disabled = !ready;
    downloadBtn.disabled = false;
  }
});

setTimeout(() => $("splash").classList.add("done"), 2100);
checkServer();
