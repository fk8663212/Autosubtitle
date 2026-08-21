const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
let toastTimer;

function showToast(message, error = false) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.className = `toast visible${error ? " error" : ""}`;
  toastTimer = setTimeout(() => { toast.className = "toast"; }, 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* no JSON */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function basename(path) {
  return path.split(/[\\/]/).pop();
}

function formatTime(value) {
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
  }).format(new Date(value));
}

function statusLabel(status) {
  return ({ queued: "等待中", processing: "處理中", completed: "已完成", failed: "失敗" })[status] || status;
}

async function loadStatus() {
  try {
    const data = await api("/api/status");
    $("#service-dot").className = "state-dot online";
    $("#service-state").textContent = data.worker_alive ? "服務運作中" : "Worker 已停止";
    $("#device").textContent = data.device.toUpperCase();
    $("#model").textContent = data.model;
    $("#translation").textContent = data.translation_enabled
      ? `${data.translation_provider} → ${data.target_language}`
      : "停用";
    $("#current-job").textContent = data.current_job_id ? `#${data.current_job_id}` : "閒置";
  } catch (_) {
    $("#service-dot").className = "state-dot offline";
    $("#service-state").textContent = "無法連線";
  }
}

async function loadJobs() {
  try {
    const jobs = await api("/api/jobs");
    const body = $("#jobs-body");
    body.replaceChildren();
    if (!jobs.length) {
      const row = body.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 5;
      cell.className = "table-empty";
      cell.textContent = "目前沒有工作，加入第一支影片吧。";
      return;
    }
    for (const job of jobs) {
      const row = body.insertRow();
      const statusCell = row.insertCell();
      const pill = document.createElement("span");
      pill.className = `status-pill status-${job.status}`;
      pill.textContent = statusLabel(job.status);
      statusCell.append(pill);

      const pathCell = row.insertCell();
      pathCell.className = "job-path";
      const name = document.createElement("strong");
      name.textContent = basename(job.input_path);
      pathCell.append(name);
      if (job.error) {
        const error = document.createElement("span");
        error.className = "job-error";
        error.textContent = job.error;
        pathCell.append(error);
      }
      row.insertCell().textContent = job.source;
      row.insertCell().textContent = formatTime(job.updated_at);
      const actionCell = row.insertCell();
      if (job.status === "completed") {
        const download = document.createElement("a");
        download.className = "download-button";
        download.href = `/api/jobs/${job.id}/download`;
        download.textContent = "下載 SRT";
        download.setAttribute("download", "");
        actionCell.append(download);
      } else if (job.status === "failed") {
        const retry = document.createElement("button");
        retry.className = "retry-button";
        retry.textContent = "重試";
        retry.addEventListener("click", async () => {
          try {
            await api(`/api/jobs/${job.id}/retry`, { method: "POST" });
            showToast(`工作 #${job.id} 已重新排入`);
            await loadJobs();
          } catch (error) { showToast(error.message, true); }
        });
        actionCell.append(retry);
      }
    }
  } catch (error) { showToast(`讀取工作失敗：${error.message}`, true); }
}

async function loadWatchFolders() {
  try {
    const folders = await api("/api/watch-folders");
    const list = $("#watch-list");
    list.replaceChildren();
    list.className = "watch-list";
    if (!folders.length) {
      list.className = "watch-list empty-state";
      list.textContent = "尚未設定監控資料夾";
      return;
    }
    for (const folder of folders) {
      const item = document.createElement("div");
      item.className = "watch-item";
      const info = document.createElement("div");
      const path = document.createElement("strong");
      path.textContent = folder.path;
      const mode = document.createElement("small");
      mode.textContent = folder.recursive ? "包含子資料夾" : "僅此資料夾";
      info.append(path, mode);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "移除";
      remove.addEventListener("click", async () => {
        try {
          await api(`/api/watch-folders/${folder.id}`, { method: "DELETE" });
          await loadWatchFolders();
        } catch (error) { showToast(error.message, true); }
      });
      item.append(info, remove);
      list.append(item);
    }
  } catch (error) { showToast(`讀取監控設定失敗：${error.message}`, true); }
}

function setSelectValue(selector, value) {
  const select = $(selector);
  const normalized = value ?? "";
  if (![...select.options].some((option) => option.value === normalized)) {
    const option = document.createElement("option");
    option.value = normalized;
    option.textContent = normalized;
    select.append(option);
  }
  select.value = normalized;
}

function updateTranslationFields() {
  const enabled = $("#setting-translate").checked;
  const provider = $("#setting-provider").value;
  $("#translation-settings").classList.toggle("disabled", !enabled);
  $("#llm-fields").hidden = provider === "google";
  $("#setting-llm-endpoint").placeholder = provider === "ollama"
    ? "http://localhost:11434"
    : "https://example.com/v1/chat/completions";
}

async function loadSettings() {
  try {
    const settings = await api("/api/settings");
    setSelectValue("#setting-model", settings.model);
    setSelectValue("#setting-language", settings.language);
    setSelectValue("#setting-device", settings.device);
    setSelectValue("#setting-compute-type", settings.compute_type);
    $("#setting-beam-size").value = settings.beam_size;
    $("#setting-overwrite").checked = settings.overwrite;
    $("#setting-translate").checked = settings.translate;
    setSelectValue("#setting-provider", settings.translation_provider);
    setSelectValue("#setting-target-language", settings.target_language);
    $("#setting-bilingual").checked = settings.bilingual;
    $("#setting-llm-endpoint").value = settings.llm_endpoint || "";
    $("#setting-llm-model").value = settings.llm_model || "";
    $("#setting-llm-api-key").value = "";
    $("#api-key-state").textContent = settings.llm_api_key_configured
      ? "已有儲存的 API Key；留白不會清除"
      : "尚未設定 API Key";
    updateTranslationFields();
  } catch (error) { showToast(`讀取設定失敗：${error.message}`, true); }
}

$("#video-file").addEventListener("change", (event) => {
  $("#file-label").textContent = event.target.files[0]?.name || "選擇影片檔案";
});

$("#upload-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#video-file");
  if (!input.files.length) return;
  const button = event.currentTarget.querySelector("button");
  const progress = $("#upload-progress");
  const request = new XMLHttpRequest();
  request.open("POST", "/api/jobs/upload");
  request.upload.addEventListener("progress", (progressEvent) => {
    if (progressEvent.lengthComputable) progress.style.width = `${progressEvent.loaded / progressEvent.total * 100}%`;
  });
  request.addEventListener("load", async () => {
    button.disabled = false;
    if (request.status >= 200 && request.status < 300) {
      showToast("影片已上傳並排入工作");
      input.value = "";
      $("#file-label").textContent = "選擇影片檔案";
      await loadJobs();
    } else {
      let detail = "上傳失敗";
      try { detail = JSON.parse(request.responseText).detail || detail; } catch (_) { /* no JSON */ }
      showToast(detail, true);
    }
    setTimeout(() => { progress.style.width = "0"; }, 500);
  });
  request.addEventListener("error", () => { button.disabled = false; showToast("上傳連線中斷", true); });
  button.disabled = true;
  const form = new FormData();
  form.append("file", input.files[0]);
  request.send(form);
});

$("#path-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const result = await api("/api/jobs/path", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: $("#video-path").value })
    });
    showToast(result.created ? "影片已排入工作" : "相同版本的影片已經排入過");
    form.reset();
    await loadJobs();
  } catch (error) { showToast(error.message, true); }
});

$("#watch-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api("/api/watch-folders", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: $("#watch-path").value, recursive: $("#watch-recursive").checked })
    });
    showToast("監控資料夾已啟用");
    form.reset();
    await loadWatchFolders();
  } catch (error) { showToast(error.message, true); }
});

$("#setting-translate").addEventListener("change", updateTranslationFields);
$("#setting-provider").addEventListener("change", updateTranslationFields);
$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  const payload = {
    model: $("#setting-model").value,
    language: $("#setting-language").value || null,
    device: $("#setting-device").value,
    compute_type: $("#setting-compute-type").value,
    beam_size: Number($("#setting-beam-size").value),
    overwrite: $("#setting-overwrite").checked,
    translate: $("#setting-translate").checked,
    translation_provider: $("#setting-provider").value,
    target_language: $("#setting-target-language").value,
    bilingual: $("#setting-bilingual").checked,
    llm_endpoint: $("#setting-llm-endpoint").value || null,
    llm_model: $("#setting-llm-model").value || null,
    llm_api_key: $("#setting-llm-api-key").value || null
  };
  button.disabled = true;
  try {
    await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    showToast("全域設定已儲存，將從下一個任務開始套用");
    await Promise.all([loadSettings(), loadStatus()]);
  } catch (error) { showToast(error.message, true); }
  finally { button.disabled = false; }
});

$("#refresh-jobs").addEventListener("click", loadJobs);
loadStatus();
loadJobs();
loadWatchFolders();
loadSettings();
setInterval(() => { loadStatus(); loadJobs(); }, 4000);
