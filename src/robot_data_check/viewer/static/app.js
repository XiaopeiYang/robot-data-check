// Episode viewer. All text coming from the dataset (tasks, attributes, issue
// details) is inserted with textContent only: it is third-party data.
"use strict";

const $ = (id) => document.getElementById(id);
const PALETTE = ["#4f46e5", "#0891b2", "#16a34a", "#ca8a04", "#ea580c", "#db2777", "#7c3aed", "#64748b"];

const state = {
  meta: null,
  list: [],        // episode summaries in current filter/sort order
  ep: null,        // current episode detail
  t: 0,            // seconds into the current episode
  duration: 0,
  playing: false,
  rate: 1,
  videos: [],      // [{el, from}]
  charts: [],      // [{u, head}]
  lastTick: 0,
};

function el(tag, props = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const c of children) if (c != null) n.append(c);
  return n;
}

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// ---------- episode list ----------

async function loadList() {
  const p = new URLSearchParams();
  if ($("f-check").value) p.set("check", $("f-check").value);
  if ($("f-severity").value) p.set("severity", $("f-severity").value);
  p.set("sort", $("f-sort").value);
  state.list = await api(`/api/episodes?${p}`);
  renderList();
}

function renderList() {
  const ol = $("episode-list");
  ol.replaceChildren();
  const withIssues = state.list.filter((e) => e.errors + e.warnings > 0).length;
  $("list-count").textContent = `${state.list.length} episodes · ${withIssues} with issues`;
  for (const e of state.list) {
    const counts = el("span", { class: "counts" });
    if (e.errors) counts.append(el("span", { class: "badge error", text: `${e.errors} E` }));
    if (e.warnings) counts.append(el("span", { class: "badge warning", text: `${e.warnings} W` }));
    if (!e.errors && !e.warnings) counts.append(el("span", { class: "badge ok", text: "ok" }));
    const li = el(
      "li",
      { "data-ep": e.episode_index, onclick: () => openEpisode(e.episode_index) },
      el("div", { class: "row1" }, el("span", { class: "mono", text: `#${e.episode_index}` }), counts),
      el("div", { class: "li-task", text: e.task || "(no task)" }),
    );
    if (state.ep && state.ep.episode_index === e.episode_index) li.classList.add("active");
    ol.append(li);
  }
}

function step(delta) {
  if (!state.list.length) return;
  const i = state.list.findIndex((e) => state.ep && e.episode_index === state.ep.episode_index);
  const next = state.list[Math.min(Math.max(i + delta, 0), state.list.length - 1)];
  if (next) openEpisode(next.episode_index);
}

// ---------- episode detail ----------

async function openEpisode(idx) {
  pause();
  const [ep, series] = await Promise.all([
    api(`/api/episodes/${idx}`),
    api(`/api/episodes/${idx}/series`),
  ]);
  state.ep = ep;
  state.duration = ep.length / state.meta.fps;
  history.replaceState(null, "", `#ep=${idx}`);

  $("empty").hidden = true;
  $("episode").hidden = false;
  $("ep-title").textContent = `Episode ${idx}`;
  $("ep-task").textContent = ep.task || "(no task)";

  const chips = $("ep-attrs");
  chips.replaceChildren(el("span", { class: "chip", text: `${ep.length} frames` }));
  for (const a of state.meta.attrs) {
    if (ep[a] != null) chips.append(el("span", { class: "chip", text: `${a}: ${ep[a]}` }));
  }

  for (const li of $("episode-list").children) {
    li.classList.toggle("active", Number(li.dataset.ep) === idx);
    if (Number(li.dataset.ep) === idx) li.scrollIntoView({ block: "nearest" });
  }

  renderVideos(ep.videos);
  renderTimeline(ep);
  renderIssues(ep.issues);
  renderCharts(series, ep.issues);
  seek(0);
}

function renderVideos(videos) {
  const box = $("videos");
  // Reuse <video> elements whose file is unchanged: neighbouring episodes usually
  // live in the same file, so switching episodes is just a seek.
  const old = new Map(state.videos.map((v) => [v.camera, v]));
  state.videos = [];
  box.replaceChildren();
  for (const v of videos) {
    let entry = old.get(v.camera);
    if (!entry || entry.url !== v.url) {
      const video = el("video", { muted: "", playsinline: "", preload: "metadata" });
      video.muted = true;
      video.src = v.url;
      video.addEventListener("loadedmetadata", () => seek(state.t));
      entry = { camera: v.camera, url: v.url, el: video };
    }
    entry.from = v.from_ts;
    entry.el.playbackRate = state.rate;
    box.append(el("div", { class: "cam" }, entry.el, el("span", { text: v.camera.replace("observation.images.", "") })));
    state.videos.push(entry);
  }
  box.hidden = videos.length === 0;
}

function bandRange(issue, length) {
  if (issue.frame_start == null) return null;
  const end = issue.frame_end ?? issue.frame_start;
  return [Math.max(0, issue.frame_start), Math.min(length - 1, end)];
}

function renderTimeline(ep) {
  const tl = $("timeline");
  tl.querySelectorAll(".band").forEach((b) => b.remove());
  for (const iss of ep.issues) {
    const r = bandRange(iss, ep.length);
    if (!r) continue;
    tl.append(el("div", {
      class: `band ${iss.severity}`,
      title: `${iss.check_name}: ${iss.detail}`,
      style: `left:${(r[0] / ep.length) * 100}%;width:${((r[1] - r[0] + 1) / ep.length) * 100}%`,
    }));
  }
}

function renderIssues(issues) {
  const ul = $("issues");
  ul.replaceChildren();
  if (!issues.length) {
    ul.append(el("li", { class: "none", text: "No issues found in this episode." }));
    return;
  }
  for (const iss of issues) {
    const where = iss.frame_start == null
      ? "whole episode"
      : iss.frame_start === iss.frame_end
        ? `frame ${iss.frame_start}`
        : `frames ${iss.frame_start}–${iss.frame_end}`;
    const li = el(
      "li",
      {},
      el("span", { class: `badge ${iss.severity}`, text: iss.severity }),
      el("span", { class: "mono", text: iss.check_name }),
      el("span", { class: "muted", text: where }),
      el("span", { text: iss.detail ?? "" }),
    );
    if (iss.frame_start != null) {
      li.classList.add("seekable");
      li.addEventListener("click", () => { pause(); seek(iss.frame_start / state.meta.fps); });
    }
    ul.append(li);
  }
}

// ---------- charts ----------

function dimNames(key, n) {
  let names = state.meta.series[key];
  if (names && !Array.isArray(names)) names = Object.values(names).find(Array.isArray);
  return Array.from({ length: n }, (_, i) => (names && names[i]) || `${key}[${i}]`);
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function renderCharts(data, issues) {
  for (const c of state.charts) c.u.destroy();
  state.charts = [];
  const box = $("charts");
  box.replaceChildren();
  const fps = state.meta.fps;
  // x is frame_index / fps (video time), not the recorded timestamp: broken
  // timestamps are one of the things we check, so they must not move the plot.
  const xs = data.frame_index.map((f) => f / fps);
  const length = state.ep.length;

  const drawBands = (u) => {
    const { ctx } = u;
    const { top, height } = u.bbox;
    ctx.save();
    for (const iss of issues) {
      const r = bandRange(iss, length);
      if (!r) continue;
      const x0 = u.valToPos(r[0] / fps, "x", true);
      const x1 = u.valToPos((r[1] + 1) / fps, "x", true);
      ctx.fillStyle = cssVar(iss.severity === "error" ? "--error-band" : "--warning-band");
      ctx.fillRect(x0, top, Math.max(x1 - x0, 2), height);
    }
    ctx.restore();
  };

  for (const [key, dims] of Object.entries(data.series)) {
    const wrap = el("div", { class: "chart" }, el("h3", { text: key }));
    box.append(wrap);
    const names = dimNames(key, dims.length);
    const axis = { stroke: cssVar("--muted"), grid: { stroke: cssVar("--border") }, ticks: { stroke: cssVar("--border") } };
    const u = new uPlot(
      {
        width: wrap.clientWidth,
        height: 200,
        cursor: { drag: { x: false, y: false } },
        scales: { x: { time: false } },
        axes: [{ ...axis, label: "seconds" }, axis],
        series: [{ label: "t (s)" }, ...names.map((n, i) => ({ label: n, stroke: PALETTE[i % PALETTE.length], width: 1.25 }))],
        hooks: { drawAxes: [drawBands] },
      },
      [xs, ...dims],
      wrap,
    );
    const head = el("div", { class: "playhead" });
    u.over.append(head);
    u.over.addEventListener("click", (e) => { pause(); seek(u.posToVal(e.offsetX, "x")); });
    state.charts.push({ u, head });
  }
}

new ResizeObserver(() => {
  for (const { u } of state.charts) u.setSize({ width: u.root.parentElement.clientWidth, height: 200 });
  renderPlayhead();
}).observe($("charts"));

// ---------- clock ----------
// With videos, the first video is the clock and the others follow it.
// Without videos (e.g. local data without media), a timer drives playback.

function seek(t) {
  const lastFrame = Math.max(state.duration - 1 / state.meta.fps, 0);
  state.t = Math.min(Math.max(t, 0), lastFrame);
  for (const v of state.videos) v.el.currentTime = v.from + state.t;
  renderPlayhead();
}

function play() {
  if (!state.ep) return;
  if (state.t >= state.duration - 1.5 / state.meta.fps) seek(0);
  state.playing = true;
  $("play").textContent = "❚❚";
  for (const v of state.videos) v.el.play().catch(() => {});
  state.lastTick = performance.now();
  requestAnimationFrame(tick);
}

function pause() {
  state.playing = false;
  $("play").textContent = "▶";
  for (const v of state.videos) v.el.pause();
}

function tick(now) {
  if (!state.playing) return;
  if (state.videos.length) {
    const [master, ...rest] = state.videos;
    state.t = master.el.currentTime - master.from;
    for (const v of rest) {
      if (Math.abs(v.el.currentTime - v.from - state.t) > 0.1) v.el.currentTime = v.from + state.t;
    }
  } else {
    state.t += ((now - state.lastTick) / 1000) * state.rate;
  }
  state.lastTick = now;
  // Video files hold many episodes back to back: stop at this episode's end.
  if (state.t >= state.duration - 1 / state.meta.fps) {
    pause();
    seek(state.duration);
    return;
  }
  renderPlayhead();
  requestAnimationFrame(tick);
}

function renderPlayhead() {
  if (!state.ep) return;
  const frame = Math.min(Math.floor(state.t * state.meta.fps + 1e-6), state.ep.length - 1);
  $("frame-label").textContent = `frame ${frame} / ${state.ep.length - 1} · ${state.t.toFixed(2)}s`;
  $("timeline").querySelector(".playhead").style.left = `${(state.t / state.duration) * 100}%`;
  for (const { u, head } of state.charts) {
    head.style.left = `${u.valToPos(state.t, "x")}px`;
  }
}

// ---------- wiring ----------

$("play").addEventListener("click", () => (state.playing ? pause() : play()));
$("speed").addEventListener("change", (e) => {
  state.rate = Number(e.target.value);
  for (const v of state.videos) v.el.playbackRate = state.rate;
});
$("timeline").addEventListener("click", (e) => {
  const r = e.currentTarget.getBoundingClientRect();
  pause();
  seek(((e.clientX - r.left) / r.width) * state.duration);
});
for (const id of ["f-check", "f-severity", "f-sort"]) $(id).addEventListener("change", loadList);

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "SELECT" || !state.ep) return;
  const dt = 1 / state.meta.fps;
  if (e.key === " ") { e.preventDefault(); state.playing ? pause() : play(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); pause(); seek(state.t + dt); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); pause(); seek(state.t - dt); }
  else if (e.key === "j") step(1);
  else if (e.key === "k") step(-1);
});

(async function init() {
  state.meta = await api("/api/meta");
  $("dataset").textContent = `${state.meta.dataset} @ ${String(state.meta.revision).slice(0, 8)}`;
  for (const c of state.meta.checks) $("f-check").append(el("option", { value: c, text: c }));
  await loadList();
  const m = location.hash.match(/ep=(\d+)/);
  const first = m ? Number(m[1]) : state.list[0]?.episode_index;
  if (first != null) openEpisode(first);
})().catch((err) => {
  $("empty").textContent = `Failed to load: ${err.message}`;
});
