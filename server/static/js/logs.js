function switchLogSource(source) {

  currentLogSource = source;

  document.getElementById('btn-log-desktop').classList.toggle('active-tab', source === 'desktop');

  document.getElementById('btn-log-phone').classList.toggle('active-tab', source === 'phone');

  

  const wasActive = logStreamActive;

  if (wasActive) {

    stopLogStream();

  }

  

  loadLogs().then(() => {

    if (wasActive) {

      startLogStream();

    }

  });

}

async function loadLogs() {

  const url = currentLogSource === 'phone' ? '/api/logs/phone?lines=300' : '/api/logs?lines=300';

  const result = await apiCall(url);

  const viewer = document.getElementById('log-viewer');

  if (result.logs) {

    viewer.innerHTML = result.logs.map(l => {

      let cls = 'log-line';

      if (l.includes('ERROR') || l.includes('error') || l.includes('E/') || l.includes('FATAL')) cls += ' error';

      else if (l.includes('WARNING') || l.includes('warn') || l.includes('W/')) cls += ' warn';

      return `<div class="${cls}">${escapeHtml(l)}</div>`;

    }).join('');

    viewer.scrollTop = viewer.scrollHeight;

  }

}

async function startLogStream() {

  if (logStreamActive) return;

  logStreamActive = true;

  document.getElementById('log-toggle-btn').textContent = '⏸ 暂停';

  

  const viewer = document.getElementById('log-viewer');

  viewer.innerHTML = '<div class="log-line info">正在加载历史日志...</div>';

  

  try {

    await loadLogs();

  } catch (e) {

    viewer.innerHTML = `<div class="log-line error">加载历史日志失败: ${e.message}</div>`;

  }

  

  if (currentLogSource === 'desktop') {

    logEventSource = new EventSource('/api/logs/stream');

    logEventSource.onmessage = (e) => {

      if (!logStreamActive) return;

      const line = e.data;

      const div = document.createElement('div');

      div.className = 'log-line';

      if (line.includes('ERROR') || line.includes('error')) div.className += ' error';

      else if (line.includes('WARNING') || line.includes('warn')) div.className += ' warn';

      div.textContent = line;

      viewer.appendChild(div);

      viewer.scrollTop = viewer.scrollHeight;

      while (viewer.children.length > 2000) {

        viewer.removeChild(viewer.firstChild);

      }

    };

  } else {

    logEventSource = setInterval(loadLogs, 3000);

  }

}

function stopLogStream() {

  logStreamActive = false;

  if (logEventSource) {

    if (logEventSource instanceof EventSource) {

      logEventSource.close();

    } else {

      clearInterval(logEventSource);

    }

    logEventSource = null;

  }

}

function toggleLogStream() {

  if (logStreamActive) {

    stopLogStream();

    document.getElementById('log-toggle-btn').textContent = '▶ 继续';

  } else {

    startLogStream();

    document.getElementById('log-toggle-btn').textContent = '⏸ 暂停';

  }

}

function toggleLogFilter() {

  showErrorsOnly = !showErrorsOnly;

  const viewer = document.getElementById('log-viewer');

  const btn = document.getElementById('log-filter-btn');

  

  if (showErrorsOnly) {

    viewer.classList.add('show-errors-only');

    btn.textContent = '📄 显示全部';

    btn.classList.add('active-tab');

  } else {

    viewer.classList.remove('show-errors-only');

    btn.textContent = '⚠️ 仅显示错误';

    btn.classList.remove('active-tab');

  }

}

function copyLogContent() {

  const viewer = document.getElementById('log-viewer');

  let text = '';

  if (showErrorsOnly) {

    const errorLines = viewer.querySelectorAll('.log-line.error');

    text = Array.from(errorLines).map(div => div.textContent).join('\n');

  } else {

    text = viewer.innerText || viewer.textContent;

  }

  navigator.clipboard.writeText(text);

  showToast('日志已复制到剪贴板！', 'success');

}

async function analyzeLogs() {

  const modal = document.getElementById('log-analysis-modal');

  const content = document.getElementById('log-analysis-content');

  

  content.textContent = 'Aide 正在为您翻译并深度解析日志中的报错信息，请耐心等待（通常需要5-15秒）... 🧚✨';

  modal.style.display = 'flex';

  

  const res = await apiCall('/api/logs/analyze', 'POST', { type: currentLogSource });

  if (res && res.success) {

    content.textContent = res.analysis;

  } else {

    content.textContent = '❌ 解析失败: ' + (res ? res.message : '网络请求错误');

  }

}

async function clearLogs() {

  if (!confirm(`确定要清空所有${currentLogSource === 'phone' ? '手机端' : '电脑端'}日志文件内容吗？此操作不可逆。`)) return;

  const res = await apiCall('/api/logs/clear', 'POST', { type: currentLogSource });

  if (res && res.success) {

    showToast(res.message, 'success');

    loadLogs();

  } else {

    showToast(res ? res.message : '清空失败', 'error');

  }

}

function closeLogAnalysisModal() {

  document.getElementById('log-analysis-modal').style.display = 'none';

}
