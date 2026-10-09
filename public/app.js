const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const resultsNode = document.querySelector("#results");
const statusNode = document.querySelector("#status");
const video = document.querySelector("#video");
const overlay = document.querySelector("#overlay");
const playerEmpty = document.querySelector("#player-empty");
const playerShell = document.querySelector("#player-shell");
const evidence = document.querySelector("#evidence");
const glassesToggle = document.querySelector("#glasses-toggle");
const searchButton = form.querySelector("button[type=submit]");

const state = {
  results: [],
  selected: null,
  detections: {},
  event: null,
  animationFrame: null,
};

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.classList.toggle("error", isError);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    data = { error: `Unexpected response (${response.status})` };
  }
  if (!response.ok) {
    throw new Error(data.error || data.detail || `Request failed (${response.status})`);
  }
  return data;
}

function first(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function normalizeResult(raw, index) {
  const source = first(raw.source, raw.preview_source, raw.segment_source, raw.video_source, "");
  const caption = first(
    raw.reasoning_content,
    raw.caption,
    raw.description,
    raw.reasoning,
    raw.summary,
    "No caption was returned."
  );
  const start = Number(
    first(raw.start_time, raw.start_sec, raw.best_match_start_sec, raw.segment_start, 0)
  );
  const end = Number(
    first(raw.end_time, raw.end_sec, raw.best_match_end_sec, raw.segment_end, 0)
  );
  return {
    raw,
    source,
    caption: String(caption),
    cameraId: String(first(raw.camera_id, raw.metadata?.camera_id, "unknown")),
    score: Number(first(raw.similarity_score, raw.score, raw.similarity, 0)),
    start,
    end,
    title: String(
      first(raw.filename, raw.original_video, source.split("/").pop(), `Clip ${index + 1}`)
    ),
  };
}

function unpackResults(data) {
  const exact = Array.isArray(data.results) ? data.results : [];
  const chunks = Array.isArray(data.chunk_results) ? data.chunk_results : [];
  return (exact.length ? exact : chunks).map(normalizeResult).filter((result) => result.source);
}

function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ]
  );
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function renderResults() {
  if (!state.results.length) {
    resultsNode.className = "results empty-state";
    resultsNode.innerHTML =
      "<p>No matching segments.</p><span>The archive may not contain a bicycle-mounted camera. Re-ingest cannot create footage that was never recorded.</span>";
    return;
  }

  resultsNode.className = "results";
  resultsNode.innerHTML = state.results
    .map(
      (result, index) => `
        <button class="result-card ${state.selected === result ? "active" : ""}" data-index="${index}">
          <div class="result-top">
            <span class="result-rank">MATCH ${String(index + 1).padStart(2, "0")}</span>
            <span class="result-score">${result.score ? `${(result.score * 100).toFixed(1)}%` : "SCORE —"}</span>
          </div>
          <h3>${escapeHtml(result.caption.slice(0, 190))}${result.caption.length > 190 ? "…" : ""}</h3>
          <p>${escapeHtml(result.title)}</p>
          <div class="result-meta">
            <span>${escapeHtml(result.cameraId)}</span>
            <span>${formatTime(result.start)}–${formatTime(result.end)}</span>
          </div>
        </button>
      `
    )
    .join("");

  resultsNode.querySelectorAll(".result-card").forEach((button) => {
    button.addEventListener("click", () => selectResult(Number(button.dataset.index)));
  });
}

async function search(query) {
  searchButton.disabled = true;
  setStatus("Searching the index with no camera filter…");
  try {
    const data = await api("api/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k: 8 }),
    });
    state.results = unpackResults(data);
    state.selected = null;
    renderResults();
    setStatus(
      state.results.length
        ? `${state.results.length} candidate segments found. Open one and verify that the camera is on the rider.`
        : "No candidate segments found. The archive may not contain bicycle POV footage."
    );
  } catch (error) {
    setStatus(error.message, true);
    resultsNode.className = "results empty-state";
    resultsNode.innerHTML = `<p>Search unavailable.</p><span>${escapeHtml(error.message)}</span>`;
  } finally {
    searchButton.disabled = false;
  }
}

async function selectResult(index) {
  const selected = state.results[index];
  if (!selected) return;
  state.selected = selected;
  state.event = null;
  state.detections = {};
  renderResults();
  setStatus("Loading clip, stored detections, and evidence event…");

  playerEmpty.style.display = "none";
  video.src = `api/video?source=${encodeURIComponent(selected.source)}`;
  video.load();

  let detections = {};
  try {
    detections = await api(`api/detections?source=${encodeURIComponent(selected.source)}`);
  } catch (error) {
    detections = { unavailable: error.message };
  }
  state.detections = detections;

  try {
    state.event = await api("api/event", {
      method: "POST",
      body: JSON.stringify({
        source: selected.source,
        clip_id: selected.title,
        camera_id: selected.cameraId,
        caption: selected.caption,
        start_s: selected.start,
        end_s: selected.end,
        detections,
      }),
    });
    renderEvidence();
    setStatus(
      state.event.avoid.length
        ? "Evidence matched. Red boxes require both the caption and a stored detection."
        : "No evidence-backed avoid object. The corridor is shown without a red box."
    );
  } catch (error) {
    setStatus(error.message, true);
  }
  drawLoop();
}

function renderEvidence() {
  const event = state.event;
  if (!event) return;
  evidence.classList.remove("hidden");
  document.querySelector("#event-summary").textContent = event.summary;
  document.querySelector("#event-camera").textContent = event.camera_id;
  document.querySelector("#event-corridor").textContent = event.corridor;
  document.querySelector("#event-avoid").textContent = event.avoid.length
    ? event.avoid.map((item) => `${item.label} / ${item.side}`).join(", ")
    : "none";
  document.querySelector("#source-caption").textContent = state.selected.caption;
  document.querySelector("#event-json").textContent = JSON.stringify(event, null, 2);
  document.querySelector("#hud-mode").textContent = event.corridor.toUpperCase();
  document.querySelector("#hud-confidence").textContent = `${event.confidence.toUpperCase()} CONFIDENCE`;
}

function walk(value, visit) {
  if (Array.isArray(value)) {
    value.forEach((item) => walk(item, visit));
  } else if (value && typeof value === "object") {
    visit(value);
    Object.values(value).forEach((item) => walk(item, visit));
  }
}

function detectionBoxes(label) {
  const boxes = [];
  walk(state.detections, (item) => {
    const itemLabel = String(
      first(item.label, item.class_name, item.class, item.name, "")
    ).toLowerCase();
    if (itemLabel !== label) return;

    let box = first(item.bbox, item.box, item.xyxy, item.bounding_box);
    if (box && !Array.isArray(box)) {
      box = [box.x1 ?? box.xmin ?? box.left, box.y1 ?? box.ymin ?? box.top,
        box.x2 ?? box.xmax ?? (box.left + box.width),
        box.y2 ?? box.ymax ?? (box.top + box.height)];
    }
    if (Array.isArray(box) && box.length >= 4 && box.slice(0, 4).every(Number.isFinite)) {
      boxes.push({ box: box.slice(0, 4).map(Number), item });
    }
  });
  return boxes;
}

function videoRect(canvasWidth, canvasHeight) {
  if (!video.videoWidth || !video.videoHeight) {
    return { x: 0, y: 0, width: canvasWidth, height: canvasHeight };
  }
  const scale = Math.min(canvasWidth / video.videoWidth, canvasHeight / video.videoHeight);
  const width = video.videoWidth * scale;
  const height = video.videoHeight * scale;
  return { x: (canvasWidth - width) / 2, y: (canvasHeight - height) / 2, width, height };
}

function drawOverlay() {
  const ratio = window.devicePixelRatio || 1;
  const bounds = playerShell.getBoundingClientRect();
  const width = Math.max(1, Math.round(bounds.width * ratio));
  const height = Math.max(1, Math.round(bounds.height * ratio));
  if (overlay.width !== width || overlay.height !== height) {
    overlay.width = width;
    overlay.height = height;
  }
  const context = overlay.getContext("2d");
  context.clearRect(0, 0, width, height);
  if (!state.event || !state.selected) return;

  const rect = videoRect(width, height);
  const mode = state.event.corridor;
  const shift = mode === "shift_left" ? -0.12 : mode === "shift_right" ? 0.12 : 0;
  const center = rect.x + rect.width * (0.5 + shift);
  const bottomY = rect.y + rect.height * 0.94;
  const topY = rect.y + rect.height * (mode === "slow" ? 0.68 : 0.51);
  const bottomHalf = rect.width * 0.16;
  const topHalf = rect.width * 0.035;

  context.beginPath();
  context.moveTo(center - bottomHalf, bottomY);
  context.lineTo(center - topHalf, topY);
  context.lineTo(center + topHalf, topY);
  context.lineTo(center + bottomHalf, bottomY);
  context.closePath();
  context.fillStyle = "rgba(184, 255, 61, 0.18)";
  context.strokeStyle = "rgba(184, 255, 61, 0.95)";
  context.lineWidth = 3 * ratio;
  context.fill();
  context.stroke();

  state.event.avoid.forEach((avoid) => {
    const matches = detectionBoxes(avoid.label);
    if (!matches.length) return;
    const candidate = matches
      .map(({ box, item }) => {
        const normalized = Math.max(...box) <= 1.5;
        const x1 = normalized ? box[0] * rect.width : box[0] * (rect.width / video.videoWidth);
        const y1 = normalized ? box[1] * rect.height : box[1] * (rect.height / video.videoHeight);
        const x2 = normalized ? box[2] * rect.width : box[2] * (rect.width / video.videoWidth);
        const y2 = normalized ? box[3] * rect.height : box[3] * (rect.height / video.videoHeight);
        return { x1, y1, x2, y2, area: Math.abs((x2 - x1) * (y2 - y1)), item };
      })
      .sort((a, b) => b.area - a.area)[0];
    if (!candidate) return;
    context.strokeStyle = "#ff4d37";
    context.fillStyle = "rgba(255, 77, 55, 0.11)";
    context.lineWidth = 3 * ratio;
    const x = rect.x + candidate.x1;
    const y = rect.y + candidate.y1;
    const w = candidate.x2 - candidate.x1;
    const h = candidate.y2 - candidate.y1;
    context.fillRect(x, y, w, h);
    context.strokeRect(x, y, w, h);
    context.fillStyle = "#ff4d37";
    context.font = `${11 * ratio}px ui-monospace, monospace`;
    context.fillText(`${avoid.label.toUpperCase()} / ${avoid.side.toUpperCase()}`, x, Math.max(y - 8, 14));
  });
}

function drawLoop() {
  cancelAnimationFrame(state.animationFrame);
  const tick = () => {
    drawOverlay();
    state.animationFrame = requestAnimationFrame(tick);
  };
  tick();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  search(queryInput.value.trim());
});

document.querySelectorAll(".chips button").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.query;
    search(button.dataset.query);
  });
});

glassesToggle.addEventListener("change", () => {
  playerShell.classList.toggle("glasses", glassesToggle.checked);
  drawOverlay();
});

window.addEventListener("resize", drawOverlay);
video.addEventListener("loadedmetadata", drawOverlay);
