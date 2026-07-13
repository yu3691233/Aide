(function () {
  "use strict";
  const SERVER = "http://localhost:5000";
  let collected = [];
  let selectedIndex = -1;
  let response = null;
  let selectedCandidate = 0;

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function itemName(item) { return item.componentName || item.ariaLabel || item.text || item.id || item.componentType || "界面组件"; }
  function itemLocation(item) { return ["Web", item.pageTitle, item.location, itemName(item)].filter(Boolean).join(" · "); }

  function renderList() {
    $("count").textContent = collected.length;
    if (!collected.length) {
      $("collectedList").innerHTML = '<div class="empty">尚未选择网页组件</div>';
      selectItem(-1);
      return;
    }
    $("collectedList").innerHTML = collected.map((item, i) => `
      <div class="item ${i === selectedIndex ? "selected" : ""}" data-index="${i}">
        <div class="item-title">${esc(itemName(item))}</div>
        <div class="item-meta">${esc([item.componentType, item.location, item.pageTitle].filter(Boolean).join(" · "))}</div>
      </div>`).join("");
    document.querySelectorAll(".item").forEach((el) => el.addEventListener("click", () => selectItem(Number(el.dataset.index))));
    if (selectedIndex < 0 || selectedIndex >= collected.length) selectItem(collected.length - 1);
  }

  function selectItem(index) {
    selectedIndex = index;
    const item = collected[index];
    $("componentSummary").textContent = item ? itemLocation(item) : "请先在网页中选择组件";
    $("componentName").value = item ? itemName(item) : "";
    document.querySelectorAll(".item").forEach((el) => el.classList.toggle("selected", Number(el.dataset.index) === index));
  }

  function requestBody() {
    const item = collected[selectedIndex] || {};
    let urlPath = "";
    try { urlPath = new URL(item.url || "").pathname; } catch (_) {}
    return {
      task_type: $("taskType").value,
      user_text: $("userText").value.trim(),
      component: {
        platform: "Web",
        name: $("componentName").value.trim() || itemName(item),
        type: item.componentType || item.tag || "界面组件",
        page: item.pageTitle || "",
        location: item.location || "",
        technical: { tag: item.tag || "", id: item.id || "", role: item.role || "", selector: item.cssSelector || "", url_path: urlPath }
      }
    };
  }

  async function generate() {
    if (selectedIndex < 0) { $("status").textContent = "请先 Ctrl+点击一个网页组件"; return; }
    if (!$("userText").value.trim()) { $("status").textContent = "请补充几个字说明问题或需求"; return; }
    $("generateBtn").disabled = true;
    $("status").textContent = "正在生成…";
    try {
      const r = await fetch(`${SERVER}/api/prompt/compose`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(requestBody()) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      response = await r.json();
      selectedCandidate = 0;
      renderResult();
      $("status").textContent = response.used_ai ? "已由 Aide 生成" : "AI 暂不可用，已使用基础模板";
    } catch (e) {
      $("status").textContent = `无法连接 AideLink 服务：${e.message}`;
    } finally {
      $("generateBtn").disabled = false;
    }
  }

  function renderResult() {
    if (!response) return;
    $("result").style.display = "block";
    $("typeBadge").textContent = response.task_type_label;
    $("difficultyBadge").textContent = response.difficulty_label;
    $("candidates").innerHTML = (response.candidates || []).map((c, i) => `
      <div class="candidate ${i === selectedCandidate ? "selected" : ""}" data-index="${i}"><strong>${esc(c.title)}</strong><small>${esc(c.understanding)}</small></div>`).join("");
    document.querySelectorAll(".candidate").forEach((el) => el.addEventListener("click", () => { selectedCandidate = Number(el.dataset.index); renderResult(); }));
    const candidate = response.candidates[selectedCandidate] || { prompt: response.prompt };
    $("prompt").textContent = candidate.prompt || "";
  }

  async function copyPrompt() {
    const text = $("prompt").textContent;
    if (!text) return;
    await navigator.clipboard.writeText(text);
    $("status").textContent = "提示词已复制，可直接粘贴到 IDE";
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "ELEMENT_COLLECTED") {
      collected.push(msg.data);
      if (collected.length > 20) collected = collected.slice(-20);
      selectedIndex = collected.length - 1;
      chrome.storage.local.set({ collected });
      renderList();
    }
  });
  chrome.storage.local.get("collected", (data) => { collected = data.collected || []; selectedIndex = collected.length - 1; renderList(); });
  $("clearBtn").addEventListener("click", () => { collected = []; selectedIndex = -1; response = null; $("result").style.display = "none"; chrome.storage.local.set({ collected: [] }); renderList(); });
  $("generateBtn").addEventListener("click", generate);
  $("regenerateBtn").addEventListener("click", generate);
  $("copyBtn").addEventListener("click", copyPrompt);
})();
