

/* ========== 全局变量 ========== */
const configTabLoaders = {
  basic: () => loadConfig(),
  frp: () => loadFrpProxies(),
  oc_web: () => loadOcWebConfig(),
  nasfrp: () => loadNasFrp(),
  models: () => loadModels(),
  devices: () => loadDevices(),
  ides: () => loadIdes()
};
const configTabLoaded = {};
const pages = { dashboard: 'page-dashboard', tasks: 'page-tasks', toolbox: 'page-toolbox', logs: 'page-logs', sessions: 'page-sessions', config: 'page-config' };
let currentLogSource = 'desktop';
let logStreamActive = false;
let logEventSource = null;
let showErrorsOnly = false;
let tasksLogSource = 'desktop';
let tasksLogInterval = null;
let currentNasFrpConfig = null;
let currentRawConfig = '';
let xiaomenglingLoaded = false;
let idesLoaded = false;
let projectMapLoaded = false;
let tasksLoaded = false;
let toolboxLoaded = false;
let collapsedStatesCache = {};
let _changedPaths = null;
let currentMapData = null;
let currentMapSubTab = 'ui';
let debugMode = false;
let debugOverlay = null;
let debugCollectedNodes = [];
const debugStyle = document.createElement('style');
let currentComponentMap = null;
let currentComponentPlatform = 'react';
let activePromptNodes = [];
let globalPromptCategory = 'full-stack';
let globalPromptSource = 'local';
let isGlobalPromptPreviewManuallyEdited = false;
let currentTasksTab = 'pending';
let currentTasksView = 'list';
let allTasksData = { pending: [], done: [] };
let allQueueStatus = {};
let IDE_LIST = [];
let runningIdes = new Set();
let ideStatusLoaded = false;
let tasksCollapsed = {};

async function loadIDEList() {
  try {
    const res = await apiCall('/api/desktop-ides');
    if (res && res.ides) {
      IDE_LIST = res.ides.map(ide => ({
        key: ide.key,
        name: ide.name,
        type: ide.type || 'desktop',
        color: ide.color || '#888',
        icon: ide.icon || '⚡',
        path: ide.path || '',
      }));
      if (typeof renderIdeButtons === 'function') renderIdeButtons();
    }
  } catch (e) {}
}

/* ========== 工具函数 ========== */
function showToast(msg, type = 'info') {

  const container = document.getElementById('toast-container');

  const toast = document.createElement('div');

  toast.className = `toast toast-${type}`;

  toast.textContent = msg;

  container.appendChild(toast);

  const duration = (type === 'error' || type === 'danger') ? 8000 : 3000;

  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, duration);

}

async function apiCall(url, method = 'GET', body = null) {

  try {

    const opts = { method, headers: { 'Content-Type': 'application/json' } };

    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(url, opts);

    return await res.json();

  } catch (e) {

    // 网络错误(服务重启/不可达)静默失败，避免轮询场景下刷屏。
    // 调用方可通过返回值的 error 字段判断失败并自行提示。
    return { error: e.message, _networkError: true };

  }

}

async function apiAction(action) {

  const result = await apiCall(`/api/service/${action}`, 'POST');

  if (result.message) {

    showToast(result.message, result.success !== false ? 'success' : 'error');

  }

  refreshStatus();

}

function escapeHtml(str) {

  const div = document.createElement('div');

  div.textContent = str;

  return div.innerHTML;

}

function switchPage(name) {

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  document.getElementById('page-' + name).classList.add('active');

  document.querySelector(`.nav-item[onclick="switchPage('${name}')"]`).classList.add('active');

  if (name === 'logs') startLogStream();

  else stopLogStream();

  if (name === 'config') switchConfigTab('basic');

  

  // 更新版本号显示

  apiCall('/api/version').then(res => {

    if (res && res.success) {

      const el = document.getElementById('dashboard-version');

      if (el) el.textContent = 'v' + res.version;

      const tel = document.getElementById('topbar-version');

      if (tel) tel.textContent = 'v' + res.version;

    }

  });

  

  // 切换页面时清理任务页面的内嵌日志定时器并关闭折叠栏

  if (name !== 'tasks') {

    if (tasksLogInterval) {

      clearInterval(tasksLogInterval);

      tasksLogInterval = null;

    }

    const details = document.getElementById('tasks-embedded-logs-details');

    if (details) details.removeAttribute('open');

  }

}

function switchConfigTab(tabName) {

  document.querySelectorAll('.config-tab').forEach(t => t.classList.remove('active'));

  document.querySelectorAll('.config-tab-panel').forEach(p => p.classList.remove('active'));

  document.querySelector(`.config-tab[onclick="switchConfigTab('${tabName}')"]`).classList.add('active');

  document.getElementById('config-tab-' + tabName).classList.add('active');

  if (configTabLoaders[tabName] && !configTabLoaded[tabName]) {

    configTabLoaders[tabName]();

    configTabLoaded[tabName] = true;

  }

  // 每次切换到设置页面时更新版本号显示

  apiCall('/api/version').then(res => {

    if (res && res.success) {

      const el = document.getElementById('dashboard-version');

      if (el) el.textContent = 'v' + res.version;

      const tel = document.getElementById('topbar-version');

      if (tel) tel.textContent = 'v' + res.version;

    }

  });

}

function openFlaskUI() {

  window.open('http://localhost:5000', '_blank');

}

async function restartManagerUI() {

  showToast('正在发起热重启，请稍候...', 'info');

  const res = await apiCall('/api/service/restart', 'POST');

  if (res && res.success) {

    showToast('正在重新启动...', 'success');

  } else {

    showToast('重启失败: ' + (res ? res.message : '未知错误'), 'error');

  }

}


// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', () => {

  refreshStatus();

  loadLogs();

  loadIDEList(); // 加载 IDE 列表填充 IDE_LIST

  loadCachedIdeStatus(); // 立即用缓存渲染 IDE 按钮

  setInterval(refreshStatus, 5000);



  // 按需加载其他页面数据

  let sessionsLoaded = false;

  let configLoaded = false;

  const origSwitch = switchPage;

  window.switchPage = function(name) {

    origSwitch(name);

    if (name === 'sessions' && !sessionsLoaded) {

      loadSessions();

      loadChatHistory();

      sessionsLoaded = true;

    }

    if (name === 'config' && !configLoaded) {

      loadConfig();

      configLoaded = true;

    }

    if (name === 'xiaomengling' && !xiaomenglingLoaded) {

      loadModels();

      xiaomenglingLoaded = true;

    }

    if (name === 'ides' && !idesLoaded) {

      loadIdes();

      idesLoaded = true;

    }

    if (name === 'tasks') {

      loadProjectListDash();

      loadTasksList();

      loadProjectMap();

    }

    if (name === 'toolbox' && !toolboxLoaded) {

      if (typeof renderUiDictionary === 'function') renderUiDictionary();

      toolboxLoaded = true;

    }

    if (name === 'service') refreshStatus();

  };

});

function initProjectMapSSE() {

  try {

    const sse = new EventSource('/api/project-map/events');

    sse.onmessage = function(e) {

      try {

        const data = JSON.parse(e.data);

        if (data.type === 'file_changes' && data.changes) {

          // 高亮变更节点

          highlightMapChanges(data.changes);

        } else if (data.type === 'map_updated') {

          showToast(data.message || '项目地图已更新', 'info');

        }

      } catch (_) {}

    };

    sse.onerror = function() { sse.close(); };

  } catch (_) {}

}
