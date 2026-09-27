const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const state = {
  jobId: null, es: null, busy: false, codeShown: false, lastSource: null,
  files: [],
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
  $("#purpose-row").hidden = state.files.length === 0;
}

/* ---------- 任务提交与 SSE ---------- */
async function generate() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) {
    setStatus("请先填写需求描述。");
    return;
  }
  resetOutput();
  state.codeShown = false;
  setBusy(true);
  setStatus("任务已提交，排队中…");

  const fd = new FormData();
  fd.append("prompt", prompt);
  fd.append("doc_type", $("#doc-type").value);
  if (state.files.length) fd.append("att_purpose", $("#att-purpose").value);
  for (const f of state.files) fd.append("files", f, f.name);

  const res = await fetch("/api/jobs", { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    setStatus("✘ " + (err.detail || "提交失败"));
    setBusy(false);
    return;
  }
  const { job_id } = await res.json();
  state.jobId = job_id;
  state.files = []; // 附件已随任务上传
  renderFiles();
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
    setStatus("✔ 完成！可预览与下载，也可在「LaTeX 源码」页手动修改后点「重新编译」。");
    $("#code").value = ev.tex;
    $("#code").readOnly = false;
    state.lastSource = ev.tex;
    $("#btn-recompile").hidden = false;
    const url = ev.pdf_url + "?t=" + Date.now();
    const pv = $("#pdf-view");
    pv.src = url;
    pv.hidden = false;
    $("#pdf-empty").hidden = true;
    const dl = $("#btn-download");
    dl.href = url;
    dl.hidden = false;
    $("#btn-copy").hidden = false;
    switchTab("pdf");
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

/* ---------- 事件绑定 ---------- */
$("#code").addEventListener("input", () => {
  // 已有编译结果时，提示用户可重新编译使修改生效
  if (!state.busy && state.lastSource !== null) {
    if ($("#code").value !== state.lastSource) {
      setStatus("源码已修改，点击「重新编译」更新 PDF。");
    }
  }
});
$("#btn-generate").addEventListener("click", generate);
$("#btn-cancel").addEventListener("click", cancelJob);
$("#btn-copy").addEventListener("click", copyCode);
$("#btn-recompile").addEventListener("click", recompile);
$$(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));

$("#btn-pick").addEventListener("click", () => $("#file-input").click());
$("#file-input").addEventListener("change", (e) => {
  addFiles([...e.target.files]);
  e.target.value = "";
});
const dropZone = $("#drop-zone");
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  addFiles([...e.dataTransfer.files]);
});

init();
