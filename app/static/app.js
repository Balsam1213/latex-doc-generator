const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
function $on(sel, ev, fn) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.addEventListener(ev, fn);
}

const state = {
  jobId: null, es: null, busy: false, codeShown: false, lastSource: null,
  files: [], kind: "generate",
};
const STEP_ORDER = ["generate", "compile", "fix", "done"];
const FILE_EXTS = [".tex", ".txt", ".md", ".markdown", ".pdf", ".png", ".jpg", ".jpeg", ".webp"];

/* ---------- 环境自检 ---------- */
async function init() {
  try {
    const res = await fetch("/api/health");
    const h = await res.json();
    const items = [];
    items.push(
      h.llm_configured
        ? `<span class="ok">✔ 模型已配置（${h.llm_model}）</span>`
        : `<span class="bad">✘ 未配置 API Key：打开项目根目录 .env，把 LLM_API_KEY= 后面换成你的智谱 Key，保存后重启服务</span>`
    );
    items.push(
      h.tectonic_found
        ? `<span class="ok">✔ Tectonic 就绪</span>`
        : `<span class="bad">✘ 未找到 Tectonic：请把 tectonic.exe 放入项目 vendor/ 目录</span>`
    );
    $("#health").innerHTML = items.join('<span class="sep">·</span>');
    const sel = $("#doc-type");
    for (const t of h.doc_types) {
      const o = document.createElement("option");
      o.value = t.key;
      o.textContent = t.label;
      sel.appendChild(o);
    }
  } catch (e) {
    $("#health").innerHTML = `<span class="bad">✘ 无法连接后端服务</span>`;
  }
}

/* ---------- 步骤指示 ---------- */
function setStep(name) {
  const idx = STEP_ORDER.indexOf(name);
  $$("#steps li").forEach((li) => {
    const i = STEP_ORDER.indexOf(li.dataset.step);
    li.classList.toggle("done", i >= 0 && i < idx && !li.hidden);
    li.classList.toggle("active", li.dataset.step === name);
  });
}
function markAllDone() {
  setStep("done");
  $(`#steps li[data-step="done"]`).classList.add("done");
}
function setStatus(text) {
  $("#status").textContent = text;
}
function setBusy(b) {
  state.busy = b;
  $("#btn-generate").disabled = b;
  $("#btn-cancel").hidden = !b;
}

/* ---------- 页签 ---------- */
function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
}

/* ---------- 输出区复位 ---------- */
function resetOutput() {
  $("#code").value = "";
  $("#code").readOnly = true;
  state.lastSource = null;
  $("#log").textContent = "";
  const pv = $("#pdf-view");
  pv.hidden = true;
  pv.removeAttribute("src");
  $("#pdf-empty").hidden = false;
  $("#btn-download").hidden = true;
  $("#btn-tex-dl").hidden = true;
  $("#btn-use-format").hidden = true;
  $("#btn-copy").hidden = true;
  $("#btn-recompile").hidden = true;
  $("#log-tab").hidden = true;
  $("#fix-round").textContent = "";
  $(`#steps li[data-step="fix"]`).hidden = true;
  setStep(null);
  setStatus("");
}

/* ---------- 附件 ---------- */
function addFiles(list) {
  for (const f of list) {
    const dot = f.name.lastIndexOf(".");
    const ext = dot >= 0 ? f.name.slice(dot).toLowerCase() : "";
    if (!FILE_EXTS.includes(ext)) {
      setStatus(`不支持的附件类型：${f.name}（支持 tex/txt/md/pdf/png/jpg/webp）`);
      continue;
    }
    if (f.size > 10 * 1024 * 1024) {
      setStatus(`附件 ${f.name} 超过 10MB 限制`);
      continue;
    }
    if (state.files.some((x) => x.name === f.name && x.size === f.size)) continue;
    state.files.push(f);
  }
  renderFiles();
}

function renderFiles() {
  const box = $("#file-list");
  box.innerHTML = "";
  state.files.forEach((f, i) => {
    const div = document.createElement("div");
    div.className = "file-item";
    const size = f.size < 1024 * 1024
      ? `${Math.max(1, Math.round(f.size / 1024))} KB`
      : `${(f.size / 1024 / 1024).toFixed(1)} MB`;
    const span = document.createElement("span");
    span.className = "name";
    span.textContent = `📎 ${f.name}（${size}）`;
    span.title = f.name;
    const rm = document.createElement("button");
    rm.className = "rm";
    rm.textContent = "✕";
    rm.title = "移除";
    rm.addEventListener("click", () => {
      state.files.splice(i, 1);
      renderFiles();
    });
    div.append(span, rm);
    box.appendChild(div);
  });
}

/* ---------- 任务提交与 SSE ---------- */
async function startJob(fd, kind) {
  state.kind = kind;
  setBusy(true);
  setStatus(kind === "convert" ? "转换任务已提交，排队中…" : "任务已提交，排队中…");
  const res = await fetch("/api/jobs", { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    setStatus("✘ " + (err.detail || "提交失败"));
    setBusy(false);
    return;
  }
  const { job_id } = await res.json();
  state.jobId = job_id;
  if (kind === "generate") {
    state.files = []; // 附件已随任务上传
    renderFiles();
  }
  state.es = new EventSource(`/api/jobs/${job_id}/events`);
  state.es.onmessage = (e) => handleEvent(JSON.parse(e.data));
  state.es.onerror = () => {
    // 服务端在 done/error 后主动断流；若仍处于忙碌状态说明连接异常
    if (state.busy) {
      state.es.close();
      setBusy(false);
      setStatus("✘ 与服务的连接中断，请重试。");
    }
  };
}

async function generate() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) {
    setStatus("请先填写需求描述。");
    return;
  }
  resetOutput();
  state.codeShown = false;

  const fd = new FormData();
  fd.append("prompt", prompt);
  fd.append("doc_type", $("#doc-type").value);
  for (const f of state.files) fd.append("files", f, f.name);
  await startJob(fd, "generate");
}

function pdf2tex(file) {
  resetOutput();
  state.codeShown = false;
  const fd = new FormData();
  fd.append("kind", "convert");
  fd.append("files", file, file.name);
  startJob(fd, "convert");
}

function handleEvent(ev) {
  if (ev.type === "stage") {
    if (ev.stage === "preparing") {
      setStatus("正在读取与识别附件…");
    } else if (ev.stage === "generating") {
      setStep("generate");
      setStatus("正在生成 LaTeX…");
    } else if (ev.stage === "compiling") {
      setStep("compile");
      setStatus(`正在编译（第 ${ev.round} 次）…`);
    } else if (ev.stage === "fixing") {
      $(`#steps li[data-step="fix"]`).hidden = false;
      $("#fix-round").textContent = `第 ${ev.round} 轮`;
      setStep("fix");
      setStatus(`编译失败，正在让模型自动修复（第 ${ev.round} 轮）…`);
    }
  } else if (ev.type === "token") {
    const c = $("#code");
    c.value += ev.text;
    c.scrollTop = c.scrollHeight;
    if (!state.codeShown) {
      switchTab("code");
      state.codeShown = true;
    }
  } else if (ev.type === "notice") {
    setStatus(ev.text);
  } else if (ev.type === "done") {
    state.es && state.es.close();
    setBusy(false);
    markAllDone();
    $("#code").value = ev.tex;
    $("#code").readOnly = false;
    state.lastSource = ev.tex;
    $("#btn-recompile").hidden = false;
    $("#btn-copy").hidden = false;
    const url = ev.pdf_url + "?t=" + Date.now();
    const pv = $("#pdf-view");
    pv.src = url;
    pv.hidden = false;
    $("#pdf-empty").hidden = true;
    const dl = $("#btn-download");
    dl.href = url;
    dl.hidden = false;
    if (state.kind === "convert") {
      $("#btn-tex-dl").href = ev.pdf_url.replace("main.pdf", "main.tex") + "?t=" + Date.now();
      $("#btn-tex-dl").hidden = false;
      $("#btn-use-format").hidden = false;
      setStatus("✔ 转换完成！可下载 .tex，或点「用作格式示范」将其加入附件。注意：AI 近似重建，复杂版式与图片无法完全还原。");
    } else {
      setStatus("✔ 完成！可预览与下载，也可在「LaTeX 源码」页手动修改后点「重新编译」。");
    }
    switchTab("pdf");
    loadHistory();
  } else if (ev.type === "error") {
    state.es && state.es.close();
    setBusy(false);
    setStatus("✘ " + ev.message);
    if (ev.tex) {
      $("#code").value = ev.tex;
      $("#code").readOnly = false; // 允许手动改码后重新编译
      state.lastSource = ev.tex;
      $("#btn-copy").hidden = false;
      $("#btn-recompile").hidden = false;
    }
    if (ev.log) {
      $("#log").textContent = ev.log;
      $("#log-tab").hidden = false;
    }
    switchTab("code");
    loadHistory();
  }
}

/* ---------- 取消 / 复制 / 重新编译 ---------- */
async function cancelJob() {
  if (state.jobId) {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST" }).catch(() => {});
  }
  state.es && state.es.close();
  setBusy(false);
  setStatus("已取消。");
}

async function copyCode() {
  try {
    await navigator.clipboard.writeText($("#code").value);
    setStatus("源码已复制到剪贴板。");
  } catch (e) {
    $("#code").select();
    document.execCommand("copy");
    setStatus("源码已复制到剪贴板。");
  }
}

async function recompile() {
  const tex = $("#code").value;
  state.lastSource = tex;
  setStatus("正在重新编译…");
  const res = await fetch(`/api/jobs/${state.jobId}/recompile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tex }),
  });
  const data = await res.json();
  if (data.ok) {
    const url = data.pdf_url + "?t=" + Date.now();
    const pv = $("#pdf-view");
    pv.src = url;
    pv.hidden = false;
    $("#pdf-empty").hidden = true;
    const dl = $("#btn-download");
    dl.href = url;
    dl.hidden = false;
    setStatus("✔ 编译成功！");
    switchTab("pdf");
  } else {
    $("#log").textContent = data.log || data.errors || "";
    $("#log-tab").hidden = false;
    setStatus("✘ 仍然编译失败，请参考编译日志继续修改。");
    switchTab("log");
  }
}

/* ---------- 历史记录 ---------- */
function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const { items } = await res.json();
    const ul = $("#history");
    ul.innerHTML = "";
    if (!items.length) {
      ul.innerHTML = '<li class="hist-empty">暂无记录</li>';
      return;
    }
    for (const it of items) {
      const li = document.createElement("li");
      li.className = "hist-item";
      const icon = it.status === "done" ? "✔" : it.status === "failed" ? "✘" : "⏳";
      const badge = it.kind === "convert" ? '<em class="badge">转换</em>' : "";
      const snippet = (it.prompt || "").slice(0, 32) + ((it.prompt || "").length > 32 ? "…" : "");
      const main = document.createElement("div");
      main.className = "hist-main";
      main.innerHTML = `<span class="st ${it.status}">${icon}</span>${badge}<span class="txt" title="${it.prompt || ""}">${snippet}</span><span class="time">${fmtTime(it.created_at)}</span>`;
      main.addEventListener("click", () => openJob(it.id));
      const rm = document.createElement("button");
      rm.className = "rm";
      rm.textContent = "✕";
      rm.title = "删除此记录及文件";
      rm.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteHistory(it.id);
      });
      li.append(main, rm);
      ul.appendChild(li);
    }
  } catch (e) {
    /* 历史加载失败不影响主功能 */
  }
}

async function deleteHistory(id) {
  await fetch(`/api/jobs/${id}`, { method: "DELETE" }).catch(() => {});
  if (state.jobId === id) {
    state.jobId = null;
    resetOutput();
  }
  loadHistory();
}

async function openJob(id) {
  if (state.busy) return; // 任务运行中不允许切换
  const res = await fetch(`/api/jobs/${id}`);
  if (!res.ok) {
    loadHistory();
    return;
  }
  const d = await res.json();
  state.es && state.es.close();
  state.es = null;
  state.jobId = id;
  state.kind = d.kind || "generate";
  state.codeShown = true;
  state.lastSource = d.tex || null;
  setBusy(false);
  setStep(null);
  $("#code").value = d.tex || "";
  $("#code").readOnly = false;
  $("#btn-copy").hidden = false;
  $("#btn-recompile").hidden = false;
  $("#btn-tex-dl").hidden = d.kind !== "convert";
  $("#btn-use-format").hidden = d.kind !== "convert";
  if (d.kind === "convert") {
    $("#btn-tex-dl").href = `/workspace/${id}/main.tex?t=` + Date.now();
  }
  const pv = $("#pdf-view");
  if (d.pdf_url) {
    pv.src = d.pdf_url + "?t=" + Date.now();
    pv.hidden = false;
    $("#pdf-empty").hidden = true;
    $("#btn-download").href = d.pdf_url + "?t=" + Date.now();
    $("#btn-download").hidden = false;
    switchTab("pdf");
  } else {
    pv.hidden = true;
    pv.removeAttribute("src");
    $("#pdf-empty").hidden = false;
    $("#btn-download").hidden = true;
    switchTab("code");
  }
  const st = d.status === "done" ? "已完成" : d.status === "failed" ? "失败" : d.status;
  setStatus(`已加载历史任务（${st}）${d.error ? "：" + d.error : ""}`);
  $("#log-tab").hidden = true;
  markAllDoneIfDone(d.status);
}

function markAllDoneIfDone(status) {
  if (status === "done") markAllDone();
  else setStep(null);
}

/* ---------- 退出服务 / 用作格式示范 ---------- */
async function shutdownService() {
  if (!confirm("确定退出服务？页面将不可用，之后可双击桌面图标重新启动。")) return;
  setStatus("正在退出服务…");
  try {
    const res = await fetch("/api/shutdown", { method: "POST" });
    if (res.ok) {
      setStatus("服务已退出。重新启动：双击桌面「LaTeX 文档生成器」图标。");
    } else {
      const err = await res.json().catch(() => ({}));
      setStatus(err.detail || "退出失败：可能是以控制台方式启动的，请直接关闭命令行窗口。");
    }
  } catch (e) {
    setStatus("服务已退出。重新启动：双击桌面「LaTeX 文档生成器」图标。");
  }
}

async function useAsFormat() {
  try {
    const res = await fetch(`/workspace/${state.jobId}/main.tex?t=` + Date.now());
    const text = await res.text();
    const file = new File([text], "converted_format.tex", { type: "application/x-tex" });
    const idx = state.files.findIndex((f) => f.name === file.name);
    if (idx >= 0) state.files[idx] = file;
    else state.files.push(file);
    renderFiles();
    setStatus("已把转换结果加入附件。请在需求描述中说明把它作为格式示范，然后点「生成 PDF」。");
    $("#prompt").focus();
  } catch (e) {
    setStatus("✘ 读取转换结果失败，请重试。");
  }
}

/* ---------- API Key 设置 ---------- */
async function openSettings() {
  $("#cfg-error").hidden = true;
  $("#cfg-key").value = "";
  try {
    const res = await fetch("/api/config");
    const c = await res.json();
    $("#cfg-current").textContent = c.llm_configured
      ? `已配置（${c.llm_api_key_masked}），模型 ${c.llm_model}`
      : "未配置——请按下面步骤获取并填入";
    $("#cfg-current").className = "cfg-current " + (c.llm_configured ? "ok" : "bad");
  } catch (e) {
    $("#cfg-current").textContent = "读取失败";
  }
  $("#modal-mask").hidden = false;
  $("#cfg-key").focus();
}

function closeSettings() {
  $("#modal-mask").hidden = true;
}

async function saveSettings() {
  const key = $("#cfg-key").value.trim();
  const errEl = $("#cfg-error");
  if (!key) {
    errEl.textContent = "请先粘贴 API Key";
    errEl.hidden = false;
    return;
  }
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ llm_api_key: key }),
  });
  if (res.ok) {
    closeSettings();
    setStatus("✔ API Key 已更新，立即生效（无需重启）。");
    init(); // 刷新顶栏状态
  } else {
    const err = await res.json().catch(() => ({}));
    errEl.textContent = err.detail || "保存失败";
    errEl.hidden = false;
  }
}

/* ---------- 事件绑定 ---------- */
$on("#code", "input", () => {
  // 已有编译结果时，提示用户可重新编译使修改生效
  if (!state.busy && state.lastSource !== null) {
    if ($("#code").value !== state.lastSource) {
      setStatus("源码已修改，点击「重新编译」更新 PDF。");
    }
  }
});
$on("#btn-generate", "click", generate);
$on("#btn-cancel", "click", cancelJob);
$on("#btn-copy", "click", copyCode);
$on("#btn-recompile", "click", recompile);
$$(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
$('.tab[data-tab="hist"]').addEventListener("click", loadHistory);

$on("#btn-pick", "click", () => $("#file-input").click());
$on("#file-input", "change", (e) => {
  addFiles([...e.target.files]);
  e.target.value = "";
});
const dropZone = $("#drop-zone");
$on(dropZone, "dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});
$on(dropZone, "dragleave", () => dropZone.classList.remove("dragover"));
$on(dropZone, "drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  addFiles([...e.dataTransfer.files]);
});

$on("#btn-pdf2tex", "click", () => $("#pdf2tex-input").click());
$on("#pdf2tex-input", "change", (e) => {
  const f = e.target.files[0];
  if (f) pdf2tex(f);
  e.target.value = "";
});
$on("#btn-use-format", "click", useAsFormat);
$on("#btn-shutdown", "click", shutdownService);
$on("#btn-hist-refresh", "click", loadHistory);
$on("#btn-settings", "click", openSettings);
$on("#cfg-save", "click", saveSettings);
$on("#cfg-cancel", "click", closeSettings);
$on("#cfg-key", "keydown", (e) => {
  if (e.key === "Enter") saveSettings();
});
$on("#modal-mask", "click", (e) => {
  if (e.target === $("#modal-mask")) closeSettings();
});
$on("#btn-tex-dl", "click", (e) => {
  if (!e.currentTarget.href) e.preventDefault();
});

loadHistory();

init();
