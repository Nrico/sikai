const presets = [
  "copy",
  "paste",
  "cut",
  "undo",
  "redo",
  "save",
  "spotlight",
  "enter",
  "escape",
  "f13",
  "f14",
  "f15",
  "play",
  "next",
  "previous",
  "mute",
  "volup",
  "voldown",
  "wheelup",
  "wheeldown",
  "click",
];

const ledColors = [
  "#ffffff",
  "#ef4444",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#06b6d4",
  "#3b82f6",
  "#8b5cf6",
];

const state = {
  config: null,
  led: {},
  layer: 0,
  selected: { kind: "button", row: 0, column: 0 },
};

const el = {
  status: document.querySelector("#status"),
  layerTabs: document.querySelector("#layerTabs"),
  padGrid: document.querySelector("#padGrid"),
  selectedLabel: document.querySelector("#selectedLabel"),
  actionInput: document.querySelector("#actionInput"),
  actionList: document.querySelector("#actionList"),
  presetGrid: document.querySelector("#presetGrid"),
  output: document.querySelector("#output"),
  uploadStatus: document.querySelector("#uploadStatus"),
  colorSwatches: document.querySelector("#colorSwatches"),
  ledTarget: document.querySelector("#ledTarget"),
  ledMode: document.querySelector("#ledMode"),
  applyLedButton: document.querySelector("#applyLedButton"),
  saveButton: document.querySelector("#saveButton"),
  uploadButton: document.querySelector("#uploadButton"),
  validateButton: document.querySelector("#validateButton"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    const message = [data.stderr, data.stdout].filter(Boolean).join("\n") || "Request failed";
    throw new Error(message);
  }
  return data;
}

async function load() {
  const [config, actions, led, uploadStatus] = await Promise.all([
    api("/api/config"),
    api("/api/actions"),
    api("/api/led"),
    api("/api/upload-status"),
  ]);
  state.config = config;
  state.led = led;
  renderActions(actions.actions);
  renderPresets();
  renderSwatches();
  renderUploadStatus(uploadStatus);
  render();
  setStatus("Mapping loaded");
}

function renderActions(actions) {
  el.actionList.replaceChildren(
    ...actions.map((action) => {
      const option = document.createElement("option");
      option.value = action;
      return option;
    }),
  );
}

function renderPresets() {
  el.presetGrid.replaceChildren(
    ...presets.map((preset) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = preset;
      button.addEventListener("click", () => {
        el.actionInput.value = preset;
        commitSelected();
      });
      return button;
    }),
  );
}

function render() {
  renderTabs();
  renderPad();
  renderEditor();
  renderLighting();
}

function renderTabs() {
  el.layerTabs.replaceChildren(
    ...state.config.layers.map((_, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `Layer ${index + 1}`;
      button.className = index === state.layer ? "active" : "";
      button.addEventListener("click", () => {
        state.layer = index;
        state.selected = { kind: "button", row: 0, column: 0 };
        render();
      });
      return button;
    }),
  );
}

function renderPad() {
  const layer = currentLayer();
  el.padGrid.replaceChildren();

  for (let visualRow = 0; visualRow < state.config.columns; visualRow += 1) {
    for (let visualColumn = 0; visualColumn < state.config.rows; visualColumn += 1) {
      const rowIndex = visualColumn;
      const columnIndex = state.config.columns - 1 - visualRow;
      const action = layer.buttons[rowIndex][columnIndex];
      const number = rowIndex * state.config.columns + columnIndex + 1;
      const button = document.createElement("button");
      const led = ledForKey(String(number));
      button.type = "button";
      button.className = selectedMatches({ kind: "button", row: rowIndex, column: columnIndex }) ? "key selected" : "key";
      button.dataset.kind = "button";
      button.dataset.row = rowIndex;
      button.dataset.column = columnIndex;
      button.style.setProperty("--led", led.color || "#ffffff");
      button.innerHTML = `<span class="key-meta"><small>${number}</small><span class="key-led" title="LED preview"></span></span><strong>${escapeHtml(action)}</strong>`;
      button.addEventListener("click", () => selectButton(rowIndex, columnIndex));
      el.padGrid.append(button);
    }
  }

  for (const direction of ["ccw", "press", "cw"]) {
    const value = layer.knobs[0][direction] || "";
    const target = document.querySelector(`#knob-${direction}`);
    if (target) target.textContent = value;
    const control = document.querySelector(`[data-kind="knob"][data-direction="${direction}"]`);
    if (control) {
      control.classList.toggle("selected", selectedMatches({ kind: "knob", direction }));
      control.onclick = () => selectKnob(direction);
    }
  }
}

function renderEditor() {
  const selected = state.selected;
  el.selectedLabel.value = selectedName(selected);
  el.actionInput.value = getSelectedValue();
}

function renderSwatches() {
  el.colorSwatches.replaceChildren(
    ...ledColors.map((color) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "swatch";
      button.style.setProperty("--swatch", color);
      button.title = color;
      button.addEventListener("click", () => {
        currentLed().color = color;
        renderPad();
        renderLighting();
        setStatus("LED color selected");
      });
      return button;
    }),
  );
}

function renderLighting() {
  const led = currentLed();
  el.ledMode.value = String(led.mode ?? 1);
  el.ledTarget.textContent = ledTargetName();
  document.querySelectorAll(".swatch").forEach((swatch) => {
    swatch.classList.toggle("active", swatch.title.toLowerCase() === (led.color || "#ffffff").toLowerCase());
  });
}

function selectButton(row, column) {
  state.selected = { kind: "button", row, column };
  render();
  el.actionInput.focus();
  el.actionInput.select();
}

function selectKnob(direction) {
  state.selected = { kind: "knob", direction };
  render();
  el.actionInput.focus();
  el.actionInput.select();
}

function commitSelected() {
  const value = el.actionInput.value.trim();
  const selected = state.selected;
  if (selected.kind === "button") {
    currentLayer().buttons[selected.row][selected.column] = value;
  } else {
    currentLayer().knobs[0][selected.direction] = value;
  }
  renderPad();
  setStatus("Unsaved changes");
}

async function save() {
  commitSelected();
  const data = await api("/api/config", {
    method: "POST",
    body: JSON.stringify(state.config),
  });
  appendOutput(data);
  state.config = await api("/api/config");
  render();
  setStatus("Saved");
}

async function validate() {
  const data = await api("/api/validate", { method: "POST", body: "{}" });
  appendOutput(data);
  setStatus("Valid");
}

async function uploadConfig() {
  await save();
  const data = await api("/api/upload", { method: "POST", body: "{}" });
  appendOutput(data);
  renderUploadStatus(data);
  setStatus(data.address ? `Uploaded to ${data.address}` : "Upload attempted");
}

async function applyLed() {
  const led = currentLed();
  led.mode = Number(el.ledMode.value);
  const data = await api("/api/led", {
    method: "POST",
    body: JSON.stringify({ layer: state.layer + 1, key: currentLedKey(), mode: led.mode, color: led.color }),
  });
  state.led = data.settings;
  render();
  appendOutput(data);
  const encoded = data.encodedMode ? ` (${data.encodedMode})` : "";
  setStatus(data.address ? `LED command sent to ${data.address}${encoded}` : `LED command attempted${encoded}`);
}

function currentLayer() {
  return state.config.layers[state.layer];
}

function currentLed() {
  const layerKey = String(state.layer + 1);
  const key = currentLedKey();
  if (!state.led[layerKey]) {
    state.led[layerKey] = { keys: {} };
  }
  if (!state.led[layerKey].keys) {
    state.led[layerKey] = { keys: { all: state.led[layerKey] } };
  }
  if (!state.led[layerKey].keys[key]) {
    const fallback = state.led[layerKey].keys.all || { mode: 1, color: "#ffffff" };
    state.led[layerKey].keys[key] = { ...fallback };
  }
  return state.led[layerKey].keys[key];
}

function ledForKey(key) {
  const layerKey = String(state.layer + 1);
  const layer = state.led[layerKey] || {};
  const keys = layer.keys || {};
  return keys[key] || keys.all || { mode: 1, color: "#ffffff" };
}

function currentLedKey() {
  if (state.selected.kind !== "button") return "all";
  return String(state.selected.row * state.config.columns + state.selected.column + 1);
}

function ledTargetName() {
  const key = currentLedKey();
  return key === "all" ? "All keys" : `Key ${key}`;
}

function getSelectedValue() {
  const selected = state.selected;
  if (selected.kind === "button") {
    return currentLayer().buttons[selected.row][selected.column];
  }
  return currentLayer().knobs[0][selected.direction];
}

function selectedName(selected) {
  if (selected.kind === "button") {
    const number = selected.row * state.config.columns + selected.column + 1;
    return `Layer ${state.layer + 1} - Key ${number}`;
  }
  const label = { ccw: "CCW", press: "Press", cw: "CW" }[selected.direction];
  return `Layer ${state.layer + 1} - Knob ${label}`;
}

function selectedMatches(candidate) {
  const selected = state.selected;
  return Object.keys(candidate).every((key) => candidate[key] === selected[key]);
}

function appendOutput(data) {
  const text = [
    data.completedAt ? `Completed: ${data.completedAt}` : "",
    data.address ? `USB address: ${data.address}` : "",
    Number.isInteger(data.exitCode) ? `Exit code: ${data.exitCode}` : "",
    data.command ? `Command: ${data.command}` : "",
    data.stdout,
    data.stderr,
    data.backup ? `Backup: ${data.backup}` : "",
  ].filter(Boolean).join("\n");
  el.output.textContent = text || JSON.stringify(data, null, 2);
  el.output.classList.toggle("error", !data.ok);
}

function renderUploadStatus(data) {
  if (!data || data.ok === null) {
    el.uploadStatus.textContent = "No upload recorded yet.";
    el.uploadStatus.className = "";
    return;
  }

  const status = data.ok ? "Confirmed" : "Failed";
  const address = data.address || "unknown address";
  const time = data.completedAt || "unknown time";
  el.uploadStatus.textContent = `${status} at ${time} on ${address} (exit ${data.exitCode})`;
  el.uploadStatus.className = data.ok ? "good" : "bad";
}

function setStatus(message) {
  el.status.textContent = message;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
  });
}

el.actionInput.addEventListener("input", commitSelected);
el.actionInput.addEventListener("change", commitSelected);
el.saveButton.addEventListener("click", () => save().catch(showError));
el.validateButton.addEventListener("click", () => validate().catch(showError));
el.uploadButton.addEventListener("click", () => uploadConfig().catch(showError));
el.ledMode.addEventListener("change", () => {
  currentLed().mode = Number(el.ledMode.value);
  setStatus("Lighting mode selected");
});
el.applyLedButton.addEventListener("click", () => applyLed().catch(showError));

function showError(error) {
  el.output.textContent = error.message;
  el.output.classList.add("error");
  setStatus("Needs attention");
}

load().catch(showError);
