const apiBase = window.DASHBOARD_CONFIG?.apiBaseUrl || "";

const els = {
  date: document.querySelector("#dateSelect"),
  genre: document.querySelector("#genreSelect"),
  refresh: document.querySelector("#refreshBtn"),
  status: document.querySelector("#status"),
  totalListens: document.querySelector("#totalListens"),
  uniqueListeners: document.querySelector("#uniqueListeners"),
  listeningTime: document.querySelector("#listeningTime"),
  genreCount: document.querySelector("#genreCount"),
  lastUpdated: document.querySelector("#lastUpdated"),
  dailyRows: document.querySelector("#dailyRows"),
  topGenres: document.querySelector("#topGenres"),
  topSongs: document.querySelector("#topSongs"),
};

let dailyItems = [];
const selected = {
  date: "",
  genre: "",
};

function createCustomSelect(root, onChange) {
  const placeholder = root.dataset.placeholder || "Select";
  root.innerHTML = `
    <button class="select-trigger" type="button" aria-haspopup="listbox" aria-expanded="false">
      <span>${escapeHtml(placeholder)}</span>
    </button>
    <ul class="select-menu" role="listbox"></ul>
  `;

  const trigger = root.querySelector(".select-trigger");
  const label = trigger.querySelector("span");
  const menu = root.querySelector(".select-menu");
  let options = [];
  let value = "";

  function close() {
    root.classList.remove("open");
    trigger.setAttribute("aria-expanded", "false");
  }

  function renderOptions() {
    menu.innerHTML = options
      .map(
        (option) => `
          <li
            class="select-option${option.value === value ? " selected" : ""}"
            data-value="${escapeHtml(option.value)}"
            role="option"
            aria-selected="${option.value === value}"
          >${escapeHtml(option.label)}</li>
        `,
      )
      .join("");
  }

  function setValue(nextValue, emit = true) {
    value = nextValue || "";
    const option = options.find((item) => item.value === value);
    label.textContent = option?.label || placeholder;
    renderOptions();
    if (emit) onChange(value);
  }

  trigger.addEventListener("click", () => {
    const isOpen = root.classList.toggle("open");
    trigger.setAttribute("aria-expanded", String(isOpen));
  });

  menu.addEventListener("click", (event) => {
    const option = event.target.closest(".select-option");
    if (!option) return;
    setValue(option.dataset.value);
    close();
  });

  trigger.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      root.classList.add("open");
      trigger.setAttribute("aria-expanded", "true");
    }
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) close();
  });

  return {
    get value() {
      return value;
    },
    setOptions(nextOptions, nextValue = "") {
      options = nextOptions;
      setValue(nextValue, false);
    },
    setValue,
  };
}

let dateSelect;
let genreSelect;

function setStatus(message, isError = false) {
  els.status.textContent = message;
  els.status.classList.toggle("error", isError);
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function formatSeconds(value) {
  const seconds = Number(value || 0);
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

async function get(path, params = {}) {
  const url = new URL(`${apiBase}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value);
  }
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function renderSummary(items) {
  const totalListens = items.reduce((sum, item) => sum + Number(item.listen_count || 0), 0);
  const uniqueListeners = items.reduce((sum, item) => sum + Number(item.unique_listeners || 0), 0);
  const listeningTime = items.reduce(
    (sum, item) => sum + Number(item.total_listening_time_seconds || 0),
    0,
  );
  const latest = items
    .map((item) => item.updated_at)
    .filter(Boolean)
    .sort()
    .at(-1);

  els.totalListens.textContent = formatNumber(totalListens);
  els.uniqueListeners.textContent = formatNumber(uniqueListeners);
  els.listeningTime.textContent = formatSeconds(listeningTime);
  els.genreCount.textContent = formatNumber(items.length);
  els.lastUpdated.textContent = latest ? `Updated ${latest}` : "No update timestamp";
}

function renderDaily(items) {
  if (!items.length) {
    els.dailyRows.innerHTML = `<tr><td colspan="5">No daily KPI rows for this date.</td></tr>`;
    return;
  }

  els.dailyRows.innerHTML = items
    .map(
      (item) => `
        <tr>
          <td>${item.genre}</td>
          <td>${formatNumber(item.listen_count)}</td>
          <td>${formatNumber(item.unique_listeners)}</td>
          <td>${formatSeconds(item.total_listening_time_seconds)}</td>
          <td>${formatSeconds(item.avg_listening_time_per_user_seconds)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderTopGenres(item) {
  const rows = item?.top_genres || [];
  if (!rows.length) {
    els.topGenres.innerHTML = `<li class="empty">No top genres for this date.</li>`;
    return;
  }

  els.topGenres.innerHTML = rows
    .map(
      (row) => `
        <li>
          <span class="rank">${row.rank}</span>
          <span class="name">${row.genre}</span>
          <span class="count">${formatNumber(row.listen_count)}</span>
        </li>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderTopSongs(item) {
  const rows = item?.top_songs || [];
  if (!rows.length) {
    els.topSongs.innerHTML = `<li class="empty">No top songs for this genre.</li>`;
    return;
  }

  els.topSongs.innerHTML = rows
    .map(
      (row) => `
        <li>
          <span class="rank">${row.rank}</span>
          <span class="name" title="${escapeHtml(row.track_name)}">${escapeHtml(row.track_name)}
            <span class="sub" title="${escapeHtml(row.artists)}">${escapeHtml(row.artists)}</span>
          </span>
          <span class="count">${formatNumber(row.listen_count)}</span>
        </li>
      `,
    )
    .join("");
}

function fillGenres(items, preferredGenre) {
  const current = selected.genre;
  const genres = [...new Set(items.map((item) => item.genre).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b),
  );
  const nextValue = genres.includes(current) ? current : "";
  genreSelect.setOptions(
    genres.map((genre) => ({ value: genre, label: genre })),
    nextValue,
  );
  selected.genre = nextValue;
}

async function loadForDate() {
  const date = selected.date;
  if (!date) return;
  setStatus("Loading KPI data...");

  const [daily, topGenres] = await Promise.all([
    get("/daily", { date }),
    get("/top-genres", { date }),
  ]);

  dailyItems = daily.items || [];
  fillGenres(dailyItems);
  renderSummary(dailyItems);
  renderDaily(dailyItems);
  renderTopGenres(topGenres.item);
  await loadTopSongs();
  setStatus(`Showing KPIs for ${date}.`);
}

async function loadTopSongs() {
  const date = selected.date;
  const genre = selected.genre;
  if (!date || !genre) {
    renderTopSongs(null);
    return;
  }
  const topSongs = await get("/top-songs", { date, genre });
  renderTopSongs(topSongs.item);
}

async function init() {
  try {
    if (!apiBase) throw new Error("Dashboard API URL is not configured.");
    const { dates } = await get("/dates");
    if (!dates.length) {
      setStatus("No KPI dates found yet. Run the pipeline, then refresh this page.");
      return;
    }
    selected.date = dates[0];
    dateSelect.setOptions(
      dates.map((date) => ({ value: date, label: date })),
      selected.date,
    );
    await loadForDate();
  } catch (error) {
    setStatus(error.message, true);
  }
}

dateSelect = createCustomSelect(els.date, (value) => {
  selected.date = value;
  selected.genre = "";
  loadForDate().catch((error) => setStatus(error.message, true));
});
genreSelect = createCustomSelect(els.genre, (value) => {
  selected.genre = value;
  loadTopSongs().catch((error) => setStatus(error.message, true));
});

els.refresh.addEventListener("click", () =>
  init().catch((error) => setStatus(error.message, true)),
);

init();
