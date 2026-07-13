function toggleDebugMode() {

  debugMode = !debugMode;

  const btn = document.getElementById('btn-debug-mode');

  btn.classList.toggle('active', debugMode);

  btn.style.color = debugMode ? 'var(--accent-purple)' : 'var(--accent-purple)';

  btn.style.background = debugMode ? 'rgba(156,39,176,0.15)' : '';

  

  if (debugMode) {

    enableDebugMode();

  } else {

    disableDebugMode();

  }

}

function enableDebugMode() {

  debugOverlay = document.createElement('div');

  debugOverlay.id = 'debug-overlay';

  debugOverlay.style.cssText = 'position:fixed;bottom:20px;right:20px;background:var(--panel);border:1px solid var(--err);border-radius:8px;padding:12px;z-index:9999;max-width:380px;font-size:12px;box-shadow:0 4px 16px rgba(0,0,0,0.4);';

  debugOverlay.innerHTML = `

    <div style="font-weight:600;margin-bottom:8px;color:var(--accent-purple);">🎯 组件定位模式</div>

    <div style="color:var(--text-muted);margin-bottom:8px;">按住 <kbd style="background:var(--bg-primary);padding:1px 4px;border-radius:3px;border:1px solid var(--border-color);">Ctrl</kbd> + 点击元素查看信息</div>

    <div id="debug-info" style="background:var(--bg-primary);padding:8px;border-radius:4px;min-height:40px;">等待 Ctrl+点击...</div>

    <div id="debug-collected" style="margin-top:8px;max-height:120px;overflow-y:auto;"></div>

    <div style="margin-top:8px;display:flex;gap:8px;justify-content:flex-end;">

      <button class="btn btn-sm btn-outline" onclick="toggleDebugMode()">关闭</button>

    </div>

  `;

  document.body.appendChild(debugOverlay);

  

  document.addEventListener('click', debugClickHandler, true);

  document.addEventListener('mouseover', debugHoverHandler, true);

  document.addEventListener('keydown', debugEscHandler, true);

  renderDebugCollected();

}

function disableDebugMode() {

  if (debugOverlay) {

    debugOverlay.remove();

    debugOverlay = null;

  }

  document.removeEventListener('click', debugClickHandler, true);

  document.removeEventListener('mouseover', debugHoverHandler, true);

  document.removeEventListener('keydown', debugEscHandler, true);

  document.querySelectorAll('.debug-highlight').forEach(el => el.classList.remove('debug-highlight'));

}

function debugClickHandler(e) {

  if (!debugMode) return;

  if (e.target.closest('#debug-overlay')) return;

  if (!e.ctrlKey) return;

  e.preventDefault();

  e.stopPropagation();

  

  var el = e.target;

  var info = getElementInfo(el);

  var infoEl = document.getElementById('debug-info');

  if (infoEl) {

    var formatted = formatNodeForPrompt(info);

    infoEl.innerHTML = '<pre style="margin:0;font-size:11px;white-space:pre-wrap;color:var(--text-primary);background:var(--bg-primary);padding:6px;border-radius:4px;">' + escapeHtml(formatted) + '</pre>' +

      '<div style="margin-top:6px;" id="debug-add-btn-wrap"></div>';

    debugOverlay._currentInfo = info;

    var btnWrap = document.getElementById('debug-add-btn-wrap');

    var addBtn = document.createElement('button');

    addBtn.className = 'btn btn-sm btn-primary';

    addBtn.style.cssText = 'font-size:11px;';

    addBtn.textContent = '📌 加入提示词';

    addBtn.addEventListener('click', function(ev) {

      ev.stopPropagation();

      addDebugNode();

    });

    btnWrap.appendChild(addBtn);

  }

}

function debugHoverHandler(e) {

  if (!debugMode) return;

  if (e.target.closest('#debug-overlay')) return;

  document.querySelectorAll('.debug-highlight').forEach(el => el.classList.remove('debug-highlight'));

  e.target.classList.add('debug-highlight');

}

function debugEscHandler(e) {

  if (e.key === 'Escape' && debugMode) toggleDebugMode();

}

function addDebugNode() {

  const info = debugOverlay._currentInfo;

  if (!info) return;

  const exists = debugCollectedNodes.some(n => n.id === info.id && n.tag === info.tag && n.text === info.text);

  if (!exists) {

    debugCollectedNodes.push(info);

    renderDebugCollected();

    updatePromptButtonCount();

  }

  

  // 打开侧边栏并填入组件信息

  activePromptNodes = debugCollectedNodes.map(n => ({

    file: n.file || '',

    lineStart: n.lineStart || '',

    lineEnd: n.lineEnd || '',

    name: n.id || n.tag || n.text?.substring(0, 20) || '组件',

    desc: formatNodeForPrompt(n)

  }));

  

  openGlobalPromptPanel('map');

  

  const files = [...new Set(activePromptNodes.map(n => n.file).filter(Boolean))];

  const componentNames = activePromptNodes.map(n => n.name).filter(Boolean);

  if (files.length > 0) {

    document.getElementById('global-prompt-file-input').value = files.join(', ');

    document.getElementById('global-prompt-meta').textContent = files.join(', ');

  }

  if (componentNames.length > 0) {

    document.getElementById('global-prompt-component-input').value = componentNames.join(', ');

  }

  

  const quickContainer = document.getElementById('global-quick-component-container');

  const badgesEl = document.getElementById('global-quick-component-badges');

  quickContainer.style.display = 'flex';

  badgesEl.innerHTML = activePromptNodes.map(node => {

    return '<button class="btn btn-sm btn-outline" style="font-family:monospace; font-size:11px;" onclick="insertGlobalComponentRef(\'' + node.name.replace(/'/g, "\\'") + '\')">【' + escapeHtml(node.name) + '】</button>';

  }).join('');

  

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

  showToast('已加入 (' + activePromptNodes.length + ' 个组件)', 'success');

}

function removeDebugNode(idx) {

  debugCollectedNodes.splice(idx, 1);

  renderDebugCollected();

  updatePromptButtonCount();

}

function clearDebugNodes() {

  debugCollectedNodes = [];

  renderDebugCollected();

  updatePromptButtonCount();

}

function renderDebugCollected() {

  const el = document.getElementById('debug-collected');

  if (!el) return;

  if (debugCollectedNodes.length === 0) {

    el.innerHTML = '<div style="color:var(--text-muted);font-size:11px;">暂无收集的组件</div>';

    return;

  }

  el.innerHTML = debugCollectedNodes.map((n, i) => {

    const label = n.id || n.text?.substring(0, 20) || n.tag;

    return `<span style="display:inline-block;background:rgba(88,166,255,0.12);color:var(--accent-blue);border:1px solid rgba(88,166,255,0.2);border-radius:4px;padding:2px 6px;margin:2px;font-size:10px;cursor:pointer;" onclick="removeDebugNode(${i})" title="点击移除">${escapeHtml(label)} ×</span>`;

  }).join('') + `<div style="margin-top:4px;"><button class="btn btn-sm btn-outline" onclick="clearDebugNodes()" style="font-size:10px;padding:2px 6px;">清空</button></div>`;

}

function getElementInfo(el) {

  var target = el;

  var tag = el.tagName.toLowerCase();

  

  // 如果是容器元素，向上找更具体的

  if (!el.id && !el.getAttribute('onclick') && el.parentElement) {

    var parent = el.parentElement;

    for (var i = 0; i < 3 && parent; i++) {

      var ptag = parent.tagName.toLowerCase();

      if (ptag === 'html' || ptag === 'body') break;

      if (parent.getAttribute('onclick') || parent.id || parent.tagName === 'BUTTON' || parent.tagName === 'A') {

        target = parent;

        break;

      }

      parent = parent.parentElement;

    }

  }

  

  // 提取子元素 onclick 函数名

  var childActions = [];

  var children = target.querySelectorAll('[onclick]');

  for (var j = 0; j < Math.min(children.length, 5); j++) {

    var oc = children[j].getAttribute('onclick') || '';

    var match = oc.match(/^(\w+)\s*\(/);

    childActions.push(match ? match[1] : oc.substring(0, 30));

  }

  

  return {

    tag: target.tagName.toLowerCase(),

    id: target.id || '',

    classes: Array.from(target.classList).join(' '),

    text: (target.textContent || '').trim().substring(0, 100),

    onclick: target.getAttribute('onclick') || '',

    placeholder: target.getAttribute('placeholder') || '',

    type: target.getAttribute('type') || '',

    href: target.getAttribute('href') || '',

    title: target.getAttribute('title') || '',

    childActions: childActions,

    childCount: target.children.length

  };

}
