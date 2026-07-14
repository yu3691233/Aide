async function loadConfig() {

  const result = await apiCall('/api/config');

  const config = result.config || result;

  currentRawConfig = config;

  

  document.getElementById('cfg-flask-host').value = config.flask_host || '0.0.0.0';

  document.getElementById('cfg-flask-port').value = config.flask_port || 5000;

  document.getElementById('cfg-auto-start').checked = !!config.auto_start;

  document.getElementById('cfg-project-dir').value = config.project_dir || config.opencode_project_dir || '';

}

function onFrpTypeChange(type) {

  const domainGroup = document.getElementById('cfg-frp-domains-group');

  const portGroup = document.getElementById('cfg-frp-port-group');

  if (domainGroup) domainGroup.style.display = (type === 'http' || type === 'https') ? 'flex' : 'none';

  if (portGroup) portGroup.style.display = (type === 'http' || type === 'https') ? 'none' : 'flex';

}

function toggleFrpForm(enabled) {

  const fields = document.getElementById('frp-form-fields');

  if (!fields) return;

  if (enabled) {

    fields.style.opacity = '1';

    fields.style.pointerEvents = 'auto';

  } else {

    fields.style.opacity = '0.5';

    fields.style.pointerEvents = 'none';

  }

}

async function saveFormConfig() {

  if (!currentRawConfig) {
    try { await loadConfig(); } catch (e) { showToast('配置尚未加载：' + e.message, 'error'); return; }
  }

  

  currentRawConfig.flask_host = document.getElementById('cfg-flask-host').value;

  currentRawConfig.flask_port = parseInt(document.getElementById('cfg-flask-port').value) || 5000;

  currentRawConfig.auto_start = document.getElementById('cfg-auto-start').checked;

  currentRawConfig.project_dir = document.getElementById('cfg-project-dir').value.trim();

  

  showToast('正在保存本地配置...', 'info');

  const result = await apiCall('/api/config', 'POST', currentRawConfig);

  if (result && result.success !== false) {

    showToast('配置保存成功，正在重启桥接服务以生效...🔌✨', 'success');

    await apiAction('restart');

  } else {

    showToast('配置保存失败: ' + (result ? result.message : '未知错误'), 'error');

  }

}

async function loadModels() {

  const res = await apiCall('/api/xiaomengling/models');

  const tbody = document.getElementById('models-table');

  const showUnconfigured = document.getElementById('show-unconfigured-models') ? document.getElementById('show-unconfigured-models').checked : false;

  

  if (res && res.models) {

    // Populate default model select dropdown

    const defaultSelect = document.getElementById('default-model-select');

    if (defaultSelect) {

      const prevVal = defaultSelect.value;

      defaultSelect.innerHTML = '';

      const activeModels = res.models.filter(m => m.enabled && (!m.needs_api_key || m.has_api_key));

      activeModels.forEach(m => {

        const opt = document.createElement('option');

        opt.value = m.key;

        opt.textContent = m.key;

        if (m.key === res.default_model) {

          opt.selected = true;

        }

        defaultSelect.appendChild(opt);

      });

    }



    let filteredModels = res.models;

    if (!showUnconfigured) {

      filteredModels = res.models.filter(m => !m.needs_api_key || m.has_api_key);

    }

    

    if (filteredModels.length === 0) {

      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text-muted)">暂无模型（勾选“显示未配置 Key 的模型”可以配置预设模型）</td></tr>';

      return;

    }

    tbody.innerHTML = filteredModels.map(m => {

      const isDefault = m.key === res.default_model;

      const defaultBadge = isDefault ? ' <span style="color:var(--accent-yellow)">★ 默认</span>' : '';

      

      const statusBadge = m.enabled && m.has_api_key

        ? '<span class="badge badge-success">可用</span>'

        : m.enabled && !m.needs_api_key

        ? '<span class="badge badge-success">可用</span>'

        : !m.enabled

        ? '<span class="badge badge-danger">已禁用</span>'

        : '<span class="badge badge-danger">缺 Key</span>';

      const keyDisplay = m.has_api_key ? '●●●●●●●●' : '—';

      const toggleBtn = m.enabled

        ? `<button class="btn btn-sm btn-danger" onclick="toggleModel('${m.key}', false)">禁用</button>`

        : `<button class="btn btn-sm btn-success" onclick="toggleModel('${m.key}', true)">启用</button>`;

      const apiKeyBtn = m.needs_api_key

        ? `<button class="btn btn-sm btn-outline" onclick="setModelApiKey('${m.key}')">🔑 Key</button>`

        : '';

      const deleteBtn = m.source === 'custom'

        ? `<button class="btn btn-sm btn-danger" onclick="deleteModel('${m.key}')">🗑️</button>`

        : '';

      return `<tr>

        <td style="font-weight:600">${escapeHtml(m.key)}${defaultBadge}</td>

        <td>${escapeHtml(m.provider)}</td>

        <td style="font-family:monospace;font-size:12px">${escapeHtml(m.model_id)}</td>

        <td style="color:var(--text-secondary)">${escapeHtml(m.description)}</td>

        <td>${keyDisplay}</td>

        <td>${statusBadge}</td>

        <td><div class="btn-group">${toggleBtn}${apiKeyBtn}${deleteBtn}</div></td>

      </tr>`;

    }).join('');

  } else {

    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--accent-red)">加载失败</td></tr>';

  }

}

async function setDefaultModel(key) {

  const res = await apiCall('/api/xiaomengling/models/default', 'POST', { key });

  if (res && res.success) {

    showToast(res.message, 'success');

  } else {

    showToast('设置默认模型失败: ' + (res ? res.message : '网络错误'), 'error');

  }

}

async function toggleModel(key, enabled) {

  const res = await apiCall('/api/xiaomengling/models/toggle', 'POST', { key, enabled });

  if (res && res.message) {

    showToast(res.message, res.success !== false ? 'success' : 'error');

  }

  loadModels();

}

async function setModelApiKey(key) {

  const apiKey = prompt(`请输入 ${key} 的 API Key:`);

  if (apiKey === null) return;

  const res = await apiCall('/api/xiaomengling/models/apikey', 'POST', { key, api_key: apiKey });

  if (res && res.message) {

    showToast(res.message, res.success !== false ? 'success' : 'error');

  }

  loadModels();

}

async function deleteModel(key) {

  if (!confirm(`确定要删除模型 ${key} 吗？`)) return;

  const res = await apiCall('/api/xiaomengling/models/delete', 'POST', { key });

  if (res && res.message) {

    showToast(res.message, res.success !== false ? 'success' : 'error');

  }

  loadModels();

}

function showAddModelDialog() {

  const key = prompt('模型 Key（英文标识符，如 my-model）:');

  if (!key) return;

  const modelId = prompt('模型 ID（如 deepseek-chat）:');

  if (!modelId) return;

  const apiUrl = prompt('API URL（如 https://api.deepseek.com/v1/chat/completions）:');

  if (!apiUrl) return;

  const provider = prompt('提供商（如 deepseek / openai / custom）:', 'custom') || 'custom';

  const description = prompt('描述:', key) || key;

  const needsApiKey = confirm('该模型需要 API Key 吗？');



  apiCall('/api/xiaomengling/models/upsert', 'POST', {

    key,

    enabled: true,

    api_key: needsApiKey ? '' : null,

    extra: { provider, model_id: modelId, api_url: apiUrl, description, needs_api_key: needsApiKey, caps: ['chat', 'code'] }

  }).then(res => {

    if (res && res.message) {

      showToast(res.message, res.success !== false ? 'success' : 'error');

    }

    loadModels();

  });

}

async function loadIdes() {
  const tbody = document.getElementById('ides-table');

  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-muted)">正在加载 IDE 列表...</td></tr>';

  const res = await apiCall('/api/desktop-ides');

  if (res && res.ides) {

    renderIdesTable(res.ides);

  } else {

    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--accent-red)">加载失败: ${res ? res.message : '网络错误'}</td></tr>`;

  }

}

function renderIdesTable(ides) {

  const tbody = document.getElementById('ides-table');

  tbody.innerHTML = '';

  if (!ides || ides.length === 0) {

    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-muted)">未检测到任何桌面 IDE，请点击自动扫描或手动添加。</td></tr>';

    return;

  }

  ides.forEach(ide => {

    const tr = document.createElement('tr');

    const isManual = ide.source === 'manual';
    const isRemovable = isManual || ide.source === 'scan';

    const sourceLabel = isManual ? '<span class="badge badge-success">手动</span>' : '<span class="badge badge-success" style="background:rgba(88,166,255,0.15);color:var(--accent-blue);">扫描</span>';

    

    tr.innerHTML = `

      <td style="font-weight:600;">${escapeHtml(ide.exe_key || ide.key)}</td>

      <td>
        <div style="font-weight:500;">${escapeHtml(ide.name || ide.key)}</div>
      </td>

      <td style="font-family:monospace;font-size:12px;word-break:break-all;">${ide.path || '—'}</td>

      <td>${ide.version || '—'}</td>

      <td>${sourceLabel}</td>

      <td style="text-align:center;">

        <input type="checkbox" id="accept-tasks-${ide.key}" ${ide.accept_test_tasks ? 'checked' : ''} onchange="toggleIdeTestRole('${ide.key}', this.checked)" style="width:16px;height:16px;cursor:pointer;accent-color:var(--accent-blue);" />

      </td>

      <td style="text-align:center;">

        <input type="checkbox" id="primary-ide-${ide.key}" ${ide.is_primary ? 'checked' : ''} onchange="toggleIdePrimaryRole('${ide.key}', this.checked)" title="多个 IDE 同时运行时优先进入主 IDE；全局最多一个" style="width:16px;height:16px;cursor:pointer;accent-color:var(--accent-blue);" />

      </td>

      <td style="text-align:center">

        <div class="btn-group" style="justify-content:center;">

          <button class="btn btn-sm" onclick="toggleIdeFromManager('${ide.key}', '${ide.name.replace(/'/g, "\\'")}')" id="ide-toggle-${ide.key}" title="点击切换状态">⏳ 检测中...</button>

          <button class="btn btn-sm btn-outline" onclick="openIdeWindowBinding('${ide.key}', '${ide.name.replace(/'/g, "\\'")}')" title="IDE 更新后找不到窗口时重新绑定">🪟 绑定窗口</button>

          <button class="btn btn-sm btn-outline" onclick="startCalibration('${ide.key}')" title="可视化校准截图区域">🎯 校准</button>

          <button class="btn btn-sm btn-outline" onclick="renameIdeKey('${ide.key}', '${ide.name.replace(/'/g, "\\'")}', '${(ide.path || '').replace(/\\/g, "\\\\").replace(/'/g, "\\'")}')">🏷️ 修改标识(Key)</button>

          <button class="btn btn-sm btn-outline" onclick="editIdePath('${ide.key}', '${ide.name.replace(/'/g, "\\'")}', '${(ide.path || "").replace(/'/g, "\\'").replace(/\\/g, "\\\\")}')">✏️ 修改路径</button>

          ${isRemovable ? `<button class="btn btn-sm btn-danger" onclick="deleteDesktopIde('${ide.key}')">🗑️ 删除</button>` : ''}

          <button class="btn btn-sm btn-outline" onclick="installMcpForIde('${ide.key}')" title="将 AideLink MCP 配置自动注入此 IDE">🔌 安装MCP</button>

        </div>

      </td>

    `;

    tbody.appendChild(tr);

  });

  // 异步加载运行状态

  loadIdeRunningStatus();

}

async function toggleIdeTestRole(ideKey, enabled) {

  showToast('正在更新 IDE 测试角色...', 'info');

  try {

    const res = await apiCall('/api/ide/toggle-test-role', 'POST', { key: ideKey, enabled });

    if (res && res.success) {

      showToast(res.message, 'success');

    } else {

      showToast('更新失败: ' + (res ? res.message : '未知错误'), 'error');

      const cb = document.getElementById('accept-tasks-' + ideKey);

      if (cb) cb.checked = !enabled;

    }

  } catch (e) {

    showToast('网络错误: ' + e.message, 'error');

    const cb = document.getElementById('accept-tasks-' + ideKey);

    if (cb) cb.checked = !enabled;

  }

}

async function loadIdeRunningStatus() {

  try {

    const res = await apiCall('/api/ide/active_status');

    if (res && res.ides) {

      const running = new Set(res.ides.filter(i => i.running).map(i => i.key));

      const busy = new Set(res.ides.filter(i => i.status === 'busy').map(i => i.key));

      document.querySelectorAll('[id^="ide-toggle-"]').forEach(btn => {

        const key = btn.id.replace('ide-toggle-', '');

        const isRunning = running.has(key);

        const isBusy = busy.has(key);

        

        btn.textContent = isRunning ? (isBusy ? '🟡 正忙' : '🟢 运行中') : '⚪ 未运行';

        btn.style.background = isRunning ? (isBusy ? 'rgba(210,153,34,0.15)' : 'rgba(70,201,122,0.15)') : 'var(--bg-tertiary)';

        btn.style.border = isRunning ? (isBusy ? '1px solid rgba(210,153,34,0.4)' : '1px solid rgba(70,201,122,0.4)') : '1px solid var(--border-color)';

        btn.style.color = isRunning ? (isBusy ? 'var(--accent-yellow)' : 'var(--ok)') : 'var(--text-muted)';

      });

    }

  } catch (e) {}

}

function showScreenshotModal(ideKey, monitor) {

  const monParam = monitor && monitor !== '_default' ? '&monitor=' + encodeURIComponent(monitor) : '';

  const url = '/api/ide-screenshot-image?key=' + encodeURIComponent(ideKey) + monParam + '&t=' + Date.now();

  const label = monitor && monitor !== '_default' ? ' (' + monitor + ')' : '';

  const overlay = document.createElement('div');

  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;cursor:pointer;';

  overlay.innerHTML = '<div style="position:relative;max-width:90vw;max-height:90vh;">' +

    '<img src="' + url + '" style="max-width:90vw;max-height:90vh;border-radius:8px;border:2px solid var(--border-color);" />' +

    '<div style="position:absolute;top:-32px;left:0;color:#fff;font-size:14px;font-weight:600;">' + escapeHtml(ideKey.toUpperCase()) + label + ' 截图</div>' +

    '<div style="position:absolute;top:-32px;right:0;color:rgba(255,255,255,0.7);font-size:12px;">点击关闭</div>' +

  '</div>';

  overlay.addEventListener('click', function() { overlay.remove(); });

  document.body.appendChild(overlay);

}

async function toggleIdePrimaryRole(ideKey, enabled) {

  showToast(enabled ? '正在设置主 IDE...' : '正在取消主 IDE...', 'info');

  try {

    const res = await apiCall('/api/ide/set-primary-role', 'POST', { key: ideKey, enabled });

    if (res && res.success) {

      showToast(res.message, 'success');

      await loadIdes();

    } else {

      showToast('更新失败: ' + (res ? res.message : '未知错误'), 'error');

      const cb = document.getElementById('primary-ide-' + ideKey);

      if (cb) cb.checked = !enabled;

    }

  } catch (e) {

    showToast('网络错误: ' + e.message, 'error');

    const cb = document.getElementById('primary-ide-' + ideKey);

    if (cb) cb.checked = !enabled;

  }

}

// 配置页可能在首次打开前没有触发其它加载流程，提前读取一次保证保存按钮可用。
document.addEventListener('DOMContentLoaded', () => { loadConfig().catch(() => {}); });

async function openIdeWindowBinding(ideKey, ideName, autoCalibrateAfter) {
  // 绑定前统一启动并最大化，确保候选列表对应当前 IDE 主窗口。
  const launchRes = await apiCall('/api/launch-ide', 'POST', { key: ideKey });
  if (launchRes && launchRes.success) {
    showToast(launchRes.message || (ideName + ' 启动中...'), 'info');
    // 等待 IDE 进程启动并创建窗口
    await new Promise(r => setTimeout(r, 2500));
  }
  showToast('正在最大化 ' + (ideName || ideKey) + '...', 'info');
  await apiCall('/window/maximize', 'POST', { target: ideKey });
  await new Promise(r => setTimeout(r, 800));
  // 自定义 IDE 优先使用“启动/激活/最大化后”的前台窗口自动绑定。
  // 只有前台窗口无法证明属于目标 exe 时，才退回候选列表让用户选择。
  const autoBind = await apiCall('/api/ide-window-bindings/auto', 'POST', { key: ideKey });
  if (autoBind && autoBind.success) {
    showToast('已自动绑定 ' + (autoBind.binding?.title || ideName || ideKey), 'success');
    if (autoCalibrateAfter) setTimeout(() => askCalibrationAfterBinding(ideKey), 400);
    return;
  }
  await _openIdeWindowBindingDialog(ideKey, ideName, autoCalibrateAfter);
}

function askCalibrationAfterBinding(ideKey) {
  const shouldCalibrate = window.confirm('窗口已绑定成功。是否现在校准截图区域，以便手机端监控？');
  if (shouldCalibrate) startCalibration(ideKey);
}

async function _openIdeWindowBindingDialog(ideKey, ideName, autoCalibrateAfter) {
  showToast('正在读取当前桌面窗口...', 'info');
  const res = await apiCall('/api/ide-window-bindings/candidates?key=' + encodeURIComponent(ideKey));
  if (!res || !res.success) {
    showToast(res ? res.message : '读取窗口失败', 'error');
    return;
  }

  const windows = res.windows || [];
  const binding = res.binding || null;
  const recommendation = res.recommendation || null;
  const preferredIndex = binding ? windows.findIndex(win => {
    const sameExe = binding.exe_name && binding.exe_name.toLowerCase() === (win.exe_name || '').toLowerCase();
    const sameProcess = binding.process_name && binding.process_name.toLowerCase() === (win.process_name || '').toLowerCase();
    const sameTitle = binding.title && binding.title.toLowerCase() === (win.title || '').toLowerCase();
    return (sameExe || sameProcess) && sameTitle;
  }) : -1;
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.78);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px;';
  // 标记：绑定保存后是否自动进入校准（仅自定义添加 IDE 时为 true）
  overlay.dataset.autoCalibrate = autoCalibrateAfter ? '1' : '';

  const recommendedHwnd = recommendation ? String(recommendation.hwnd) : '';
  const rows = windows.map((win, index) => {
    const processLabel = win.process_name || win.exe_name || '未知进程';
    const isLikelyCurrent = binding && binding.exe_name && binding.exe_name.toLowerCase() === (win.exe_name || '').toLowerCase();
    const isRecommended = recommendedHwnd && String(win.hwnd) === recommendedHwnd;
    return '<label style="display:grid;grid-template-columns:32px minmax(220px,2fr) minmax(130px,1fr) 120px;gap:10px;align-items:center;padding:10px;border-bottom:1px solid var(--border-color);cursor:pointer;background:' + (isRecommended ? 'rgba(46,160,67,0.14)' : (isLikelyCurrent ? 'rgba(88,166,255,0.10)' : 'transparent')) + ';">' +
      '<input type="radio" name="ide-window-candidate" value="' + win.hwnd + '" ' + ((isRecommended || (!recommendedHwnd && index === (preferredIndex >= 0 ? preferredIndex : 0))) ? 'checked' : '') + ' />' +
      '<div><div style="font-weight:600;word-break:break-all;">' + escapeHtml(win.title) + '</div><div style="font-size:11px;color:var(--text-muted);">HWND ' + win.hwnd + (isRecommended ? ' · 系统推荐' : (isLikelyCurrent ? ' · 当前绑定候选' : '')) + '</div></div>' +
      '<div style="font-family:monospace;font-size:12px;word-break:break-all;">' + escapeHtml(processLabel) + '</div>' +
      '<div style="font-size:12px;">' + win.width + ' × ' + win.height + '</div>' +
    '</label>';
  }).join('');

  const bindingSummary = binding
    ? '当前规则：' + escapeHtml(binding.process_name || binding.exe_name || '未知进程') + ' / ' + escapeHtml(binding.title || '任意标题')
    : '当前使用内置窗口识别规则';

  overlay.innerHTML = '<div style="background:var(--panel);border:1px solid var(--border-color);border-radius:12px;width:min(900px,96vw);max-height:90vh;overflow:auto;padding:20px;">' +
    '<h3 style="margin:0 0 8px 0;">🪟 绑定 ' + escapeHtml(ideName || ideKey) + ' 窗口</h3>' +
    '<p style="font-size:13px;color:var(--text-secondary);margin:0 0 6px 0;">选择当前已经打开的 IDE 主窗口。保存后监控会优先按进程和窗口类别匹配，即使以后标题变化也能继续工作。</p>' +
    '<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">' + bindingSummary + '</div>' +
    (recommendation ? '<div style="font-size:12px;color:#3fb950;background:rgba(46,160,67,0.12);padding:8px;border-radius:6px;margin-bottom:12px;">系统推荐：' + escapeHtml(recommendation.title || '候选窗口') + '（' + escapeHtml((recommendation.reasons || []).join('、') || '匹配当前 IDE') + '），请确认后保存。</div>' : '<div style="font-size:12px;color:var(--text-muted);padding:8px;background:rgba(139,148,158,0.10);border-radius:6px;margin-bottom:12px;">暂未识别到明确的 IDE 窗口，请从列表中确认。</div>') +
    '<div id="ide-window-list" style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;max-height:55vh;overflow-y:auto;">' +
      (rows || '<div style="padding:24px;text-align:center;color:var(--text-muted);">没有找到可见桌面窗口，请先打开目标 IDE，然后点击"刷新窗口"。</div>') +
    '</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;flex-wrap:wrap;">' +
      '<button class="btn btn-sm btn-outline" id="ide-window-refresh" onclick="_refreshIdeWindowList(this, \'' + escapeHtml(ideKey) + '\', \'' + escapeHtml(ideName || '').replace(/'/g, "\\'") + '\')">🔄 刷新窗口</button>' +
      '<button class="btn btn-sm btn-outline" onclick="resetIdeWindowBinding(\'' + escapeHtml(ideKey) + '\', this)">恢复默认</button>' +
      '<button class="btn btn-sm btn-outline" onclick="testIdeWindowBinding(\'' + escapeHtml(ideKey) + '\')">测试匹配</button>' +
      '<button class="btn btn-sm btn-outline" onclick="this.closest(\'div[style*=fixed]\').remove()">取消</button>' +
      '<button class="btn btn-sm btn-primary" ' + (windows.length ? '' : 'disabled') + ' onclick="saveIdeWindowBinding(\'' + escapeHtml(ideKey) + '\', this)">保存绑定</button>' +
    '</div></div>';
  overlay.addEventListener('click', event => { if (event.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

async function _refreshIdeWindowList(btn, ideKey, ideName) {
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = '刷新中...';
  try {
    const res = await apiCall('/api/ide-window-bindings/candidates?key=' + encodeURIComponent(ideKey));
    if (!res || !res.success) {
      showToast(res ? res.message : '读取窗口失败', 'error');
      return;
    }
    const overlay = btn.closest('div[style*=fixed]');
    const listEl = overlay.querySelector('#ide-window-list');
    const saveBtn = overlay.querySelector('.btn-primary');
    const windows = res.windows || [];
    const binding = res.binding || null;
    const recommendation = res.recommendation || null;
    const preferredIndex = binding ? windows.findIndex(win => {
      const sameExe = binding.exe_name && binding.exe_name.toLowerCase() === (win.exe_name || '').toLowerCase();
      const sameProcess = binding.process_name && binding.process_name.toLowerCase() === (win.process_name || '').toLowerCase();
      const sameTitle = binding.title && binding.title.toLowerCase() === (win.title || '').toLowerCase();
      return (sameExe || sameProcess) && sameTitle;
    }) : -1;
    const recommendedHwnd = recommendation ? String(recommendation.hwnd) : '';
    const rows = windows.map((win, index) => {
      const processLabel = win.process_name || win.exe_name || '未知进程';
      const isLikelyCurrent = binding && binding.exe_name && binding.exe_name.toLowerCase() === (win.exe_name || '').toLowerCase();
      const isRecommended = recommendedHwnd && String(win.hwnd) === recommendedHwnd;
      return '<label style="display:grid;grid-template-columns:32px minmax(220px,2fr) minmax(130px,1fr) 120px;gap:10px;align-items:center;padding:10px;border-bottom:1px solid var(--border-color);cursor:pointer;background:' + (isRecommended ? 'rgba(46,160,67,0.14)' : (isLikelyCurrent ? 'rgba(88,166,255,0.10)' : 'transparent')) + ';">' +
        '<input type="radio" name="ide-window-candidate" value="' + win.hwnd + '" ' + ((isRecommended || (!recommendedHwnd && index === (preferredIndex >= 0 ? preferredIndex : 0))) ? 'checked' : '') + ' />' +
        '<div><div style="font-weight:600;word-break:break-all;">' + escapeHtml(win.title) + '</div><div style="font-size:11px;color:var(--text-muted);">HWND ' + win.hwnd + (isRecommended ? ' · 系统推荐' : (isLikelyCurrent ? ' · 当前绑定候选' : '')) + '</div></div>' +
        '<div style="font-family:monospace;font-size:12px;word-break:break-all;">' + escapeHtml(processLabel) + '</div>' +
        '<div style="font-size:12px;">' + win.width + ' × ' + win.height + '</div>' +
      '</label>';
    }).join('');
    listEl.innerHTML = rows || '<div style="padding:24px;text-align:center;color:var(--text-muted);">没有找到可见桌面窗口，请先打开目标 IDE，然后点击"刷新窗口"。</div>';
    if (saveBtn) saveBtn.disabled = windows.length === 0;
    showToast('已刷新，共 ' + windows.length + ' 个窗口', 'success');
  } catch (e) {
    showToast('网络错误: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function saveIdeWindowBinding(ideKey, button) {
  const overlay = button.closest('div[style*=fixed]');
  const selected = overlay.querySelector('input[name="ide-window-candidate"]:checked');
  if (!selected) {
    showToast('请先选择一个窗口', 'error');
    return;
  }
  const res = await apiCall('/api/ide-window-bindings', 'POST', { key: ideKey, hwnd: parseInt(selected.value, 10) });
  if (res && res.success) {
    showToast(res.message || '窗口绑定已保存', 'success');
    const autoCalibrate = overlay.dataset.autoCalibrate === '1';
    overlay.remove();
    if (autoCalibrate) {
      // 绑定不再强制进入校准，由用户决定是否立即配置手机监控。
      setTimeout(() => askCalibrationAfterBinding(ideKey), 400);
    }
  } else {
    showToast(res ? res.message : '保存绑定失败', 'error');
  }
}

async function resetIdeWindowBinding(ideKey, button) {
  const res = await apiCall('/api/ide-window-bindings', 'DELETE', { key: ideKey });
  if (res && res.success) {
    showToast(res.message || '已恢复默认规则', 'success');
    button.closest('div[style*=fixed]').remove();
  } else {
    showToast(res ? res.message : '重置失败', 'error');
  }
}

async function testIdeWindowBinding(ideKey) {
  const res = await apiCall('/api/ide-window-bindings/test', 'POST', { key: ideKey });
  showToast(res ? res.message : '匹配测试失败', res && res.success ? 'success' : 'error');
}

async function startCalibration(ideKey) {

  showToast('正在检查并启动 IDE...', 'info');
  let status = await apiCall('/api/launch-ide-status');
  let running = !!(status && status.success && (status.running || []).includes(ideKey));
  if (!running) {
    const launchRes = await apiCall('/api/launch-ide', 'POST', { key: ideKey });
    if (!launchRes || !launchRes.success) {
      showToast(launchRes ? launchRes.message : 'IDE 启动失败', 'error');
      return;
    }
    // 自定义 IDE 的运行状态可能暂时无法用旧 key 命中；启动成功后直接
    // 给窗口创建留出时间，后续最大化接口会再次验证真实窗口。
    await new Promise(resolve => setTimeout(resolve, 2000));
    running = true;
  }
  if (!running) return;
  showToast('正在最大化 IDE...', 'info');
  const prepared = await apiCall('/api/calibrate-maximize', 'POST', { key: ideKey, prepare_only: true });
  if (!prepared || !prepared.success) {
    showToast(prepared ? prepared.message : 'IDE 最大化失败', 'error');
    return;
  }
  showCalibrationReadyDialog(ideKey);

}

function showCalibrationReadyDialog(ideKey) {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.72);z-index:10000;display:flex;align-items:center;justify-content:center;';
  const dialog = document.createElement('div');
  dialog.style.cssText = 'background:var(--panel);border:1px solid var(--border-color);border-radius:12px;padding:22px;max-width:460px;';
  dialog.innerHTML =
    '<h3 style="margin:0 0 10px;">校准 ' + escapeHtml(ideKey.toUpperCase()) + '</h3>' +
    '<div style="font-size:13px;line-height:1.7;color:var(--text-muted);">IDE 已启动。请确认目标窗口已显示并准备好，点击“已启动，开始校准”后系统会最大化窗口并截图。</div>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:18px;">' +
      '<button class="btn btn-sm btn-outline" id="calib-ready-cancel">取消</button>' +
      '<button class="btn btn-sm btn-primary" id="calib-ready-confirm">已启动，开始校准</button>' +
    '</div>';
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  dialog.querySelector('#calib-ready-cancel').onclick = () => overlay.remove();
  dialog.querySelector('#calib-ready-confirm').onclick = async () => {
    const button = dialog.querySelector('#calib-ready-confirm');
    button.disabled = true;
    button.textContent = '正在最大化并截图...';
    const res = await apiCall('/api/calibrate', 'POST', { key: ideKey });
    overlay.remove();
    if (!res || !res.success) {
      showToast(res ? res.message : '校准失败', 'error');
      return;
    }
    showCalibrationDialog(ideKey, res);
  };
}

function showCalibrationDialog(ideKey, data) {

  const imgW = data.width, imgH = data.height;

  const monitor = data.monitor || {};

  const crop = data.crop || {left:0,right:0,top:0,bottom:0,dialog_position:'center',calib_width:0,calib_height:0,focus_input_enabled:false,input_region:null};

  const monitorName = data.monitor_name || 'primary';

  // 校准基准尺寸用缩放后的 imgW/imgH(用户实际拖框的图)，
  // 而非 data.client_width(物理尺寸)。set_crop_config 会按
  // phys_w / calib_width 把边距放大到物理坐标系，避免大窗口(>1920)
  // 时校准边距被当物理坐标存导致手机端裁剪错位。
  const clientW = imgW;
  const clientH = imgH;

  // 输入框初始值：把存储的物理坐标边距反向缩放到当前显示图(imgW×imgH)坐标系，
  // 否则物理坐标(如 calib_width=2880 下的 left=591)会与 1920 宽的图对不上，
  // 用户看到"上下左右都是反的"。
  let initLeft = crop.left || 0, initRight = crop.right || 0;
  let initTop = crop.top || 0, initBottom = crop.bottom || 0;
  const cropCalibW = crop.calib_width || 0, cropCalibH = crop.calib_height || 0;
  if (cropCalibW > 0 && cropCalibH > 0 && (cropCalibW !== imgW || cropCalibH !== imgH)) {
    const rx = imgW / cropCalibW, ry = imgH / cropCalibH;
    initLeft = Math.round(initLeft * rx);
    initRight = Math.round(initRight * rx);
    initTop = Math.round(initTop * ry);
    initBottom = Math.round(initBottom * ry);
  }
  // 检测旧错误数据(endX/endY)：right/bottom 被存成绝对坐标而非"从边的距离"，
  // 导致 left+right > calib_width。此时反向缩放后仍然 left+right > imgW，
  // 直接清零让用户重新拖框。
  if (initLeft + initRight > imgW) { initLeft = 0; initRight = 0; }
  if (initTop + initBottom > imgH) { initTop = 0; initBottom = 0; }

  let dialogPos = crop.dialog_position || 'center';
  const focusEnabled = crop.focus_input_enabled === true;
  const inputRegion = crop.input_region || null;

  const allMonitors = data.all_monitors || [monitorName];
  const calibratedMonitors = (data.calibrated_monitors || []);
  const remainingMonitors = allMonitors.filter(m => !calibratedMonitors.includes(m) && m !== monitorName);
  const isRecalibrating = data.recalibrate === true;


  const overlay = document.createElement('div');

  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:10000;display:flex;align-items:center;justify-content:center;';



  const dialog = document.createElement('div');

  dialog.style.cssText = 'background:var(--panel);border:1px solid var(--border-color);border-radius:12px;padding:20px;max-width:95vw;max-height:95vh;overflow:auto;';



  dialog.innerHTML =

    '<h3 style="margin-bottom:8px;">校准 ' + escapeHtml(ideKey.toUpperCase()) + ' 截图区域</h3>' +

    '<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">当前显示器: <b style="color:var(--accent-blue);">' + escapeHtml(monitorName) + '</b> | 全部显示器: ' + allMonitors.map(m => {
      const done = calibratedMonitors.includes(m);
      const cur = m === monitorName;
      const style = 'padding:1px 6px;border-radius:4px;font-size:11px;' + (cur ? 'background:var(--accent-blue);color:#000;' : (done ? 'background:rgba(63,185,80,0.2);color:var(--accent-green);' : 'background:var(--bg-secondary);color:var(--text-muted);'));
      return '<span style="' + style + '">' + escapeHtml(m) + (done && !cur ? ' ✓' : '') + (cur ? ' ←' : '') + '</span>';
    }).join(' ') + '</div>' +

    '<div style="margin-bottom:10px;display:flex;gap:8px;align-items:center;">' +

      '<span style="font-size:12px;color:var(--text-muted);">对话框位置:</span>' +

      '<button class="btn btn-sm ' + (dialogPos === 'left' ? 'btn-primary' : 'btn-outline') + '" id="calib-pos-left" onclick="switchDialogPosition(this,\'left\')">靠左</button>' +

      '<button class="btn btn-sm ' + (dialogPos === 'center' ? 'btn-primary' : 'btn-outline') + '" id="calib-pos-center" onclick="switchDialogPosition(this,\'center\')">居中</button>' +

      '<button class="btn btn-sm ' + (dialogPos === 'right' ? 'btn-primary' : 'btn-outline') + '" id="calib-pos-right" onclick="switchDialogPosition(this,\'right\')">靠右</button>' +

    '</div>' +

    '<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">选择对话框在 IDE 窗口中的位置，窗口缩放时边距将自动调整</div>' +

    '<div style="margin-bottom:10px;padding:10px;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-secondary);">' +
      '<label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">' +
        '<input type="checkbox" id="calib-focus-enabled" ' + (focusEnabled ? 'checked' : '') + ' />' +
        '<b>派发任务前点击输入框聚焦</b>' +
      '</label>' +
      '<div style="display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap;">' +
        '<span style="font-size:12px;color:var(--text-muted);">校准用途:</span>' +
        '<button type="button" class="btn btn-sm btn-primary" id="calib-mode-crop">截图区域</button>' +
        '<button type="button" class="btn btn-sm btn-outline" id="calib-mode-input" ' + (focusEnabled ? '' : 'disabled') + '>输入框位置</button>' +
        '<span id="calib-focus-status" style="font-size:11px;color:' + (inputRegion ? 'var(--accent-green)' : 'var(--text-muted)') + ';">' +
          (inputRegion ? '已记录输入框点击位置，可重新点击调整' : '勾选后切换到“输入框位置”并点击输入框') +
        '</span>' +
      '</div>' +
    '</div>' +

    '<div style="position:relative;display:inline-block;cursor:crosshair;" id="calib-canvas-wrap">' +

      '<img src="data:image/jpeg;base64,' + data.image + '" style="display:block;max-width:85vw;max-height:70vh;" id="calib-img" />' +

      '<div id="calib-overlay" style="position:absolute;inset:0;"></div>' +

      '<div id="calib-rect" style="position:absolute;border:2px solid #58a6ff;background:rgba(88,166,255,0.15);display:none;pointer-events:none;"></div>' +

      '<div id="calib-input-rect" style="position:absolute;border:2px solid #3fb950;background:rgba(63,185,80,0.35);display:none;pointer-events:none;width:14px;height:14px;border-radius:50%;transform:translate(-7px,-7px);"></div>' +

    '</div>' +

    '<div style="margin-top:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">' +

      '<div style="display:flex;gap:8px;font-size:13px;">' +

        '<span>上: <input type="number" id="calib-top" value="' + initTop + '" style="width:60px;padding:2px 4px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text);" /> px</span>' +

        '<span>下: <input type="number" id="calib-bottom" value="' + initBottom + '" style="width:60px;padding:2px 4px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text);" /> px</span>' +

        '<span>左: <input type="number" id="calib-left" value="' + initLeft + '" style="width:60px;padding:2px 4px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text);" /> px</span>' +

        '<span>右: <input type="number" id="calib-right" value="' + initRight + '" style="width:60px;padding:2px 4px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text);" /> px</span>' +

      '</div>' +

      '<button class="btn btn-sm btn-primary" id="calib-save-btn" onclick="saveCalibration(\'' + escapeHtml(ideKey) + '\',\'' + escapeHtml(monitorName) + '\',' + clientW + ',' + clientH + ')">保存校准</button>' +

      '<button class="btn btn-sm btn-outline" onclick="_recalibrateCurrent(\'' + escapeHtml(ideKey) + '\',\'' + escapeHtml(monitorName) + '\')">🔄 重新截图</button>' +

      '<button class="btn btn-sm btn-outline" onclick="resetCalibration()">重置</button>' +

      '<button class="btn btn-sm btn-outline" onclick="this.closest(\'div[style*=fixed]\').remove()">关闭</button>' +

    '</div>';

  // 在 overlay 上记录多显示器状态，供 saveCalibration 和 _recalibrateCurrent 读取
  overlay.dataset.allMonitors = JSON.stringify(allMonitors);
  overlay.dataset.calibratedMonitors = JSON.stringify(calibratedMonitors);
  overlay.dataset.inputRegion = inputRegion ? JSON.stringify(inputRegion) : '';

  overlay.appendChild(dialog);

  document.body.appendChild(overlay);



  // 拖框逻辑

  const imgEl = dialog.querySelector('#calib-img');

  const rectEl = dialog.querySelector('#calib-rect');

  const inputRectEl = dialog.querySelector('#calib-input-rect');

  const overlayEl = dialog.querySelector('#calib-overlay');

  let dragging = false, startX = 0, startY = 0;
  let selectionMode = 'crop';

  const focusCheckbox = dialog.querySelector('#calib-focus-enabled');
  const cropModeBtn = dialog.querySelector('#calib-mode-crop');
  const inputModeBtn = dialog.querySelector('#calib-mode-input');

  function setSelectionMode(mode) {
    if (mode === 'input' && !focusCheckbox.checked) return;
    selectionMode = mode;
    cropModeBtn.classList.toggle('btn-primary', mode === 'crop');
    cropModeBtn.classList.toggle('btn-outline', mode !== 'crop');
    inputModeBtn.classList.toggle('btn-primary', mode === 'input');
    inputModeBtn.classList.toggle('btn-outline', mode !== 'input');
  }

  cropModeBtn.addEventListener('click', function() { setSelectionMode('crop'); });
  inputModeBtn.addEventListener('click', function() { setSelectionMode('input'); });
  focusCheckbox.addEventListener('change', function() {
    inputModeBtn.disabled = !focusCheckbox.checked;
    if (focusCheckbox.checked) setSelectionMode('input');
    else setSelectionMode('crop');
  });



  function getScale() {

    const dispW = imgEl.clientWidth, dispH = imgEl.clientHeight;

    return { sx: imgW / dispW, sy: imgH / dispH };

  }

  function showSavedCropRegion() {
    if (!imgEl.clientWidth || !imgEl.clientHeight) return;
    const s = getScale();
    if (initLeft === 0 && initRight === 0 && initTop === 0 && initBottom === 0) {
      rectEl.style.display = 'none';
      return;
    }
    const cropWidth = imgW - initLeft - initRight;
    const cropHeight = imgH - initTop - initBottom;
    if (cropWidth <= 0 || cropHeight <= 0) {
      rectEl.style.display = 'none';
      return;
    }
    rectEl.style.display = 'block';
    rectEl.style.left = (initLeft / s.sx) + 'px';
    rectEl.style.top = (initTop / s.sy) + 'px';
    rectEl.style.width = (cropWidth / s.sx) + 'px';
    rectEl.style.height = (cropHeight / s.sy) + 'px';
  }



  function updateCropFromRect(x1, y1, x2, y2) {

    const s = getScale();

    // 先把 DOM 坐标转成 img 像素坐标，避免 imgW(像素) 与 DOM 坐标混单位
    // 否则当图被 CSS 缩小显示(dispW<imgW)时，r = imgW - DOM 会算出类似 endX 的值
    // 而非"从右边的距离"，导致 left+right>calib_width，手机端裁出一条线
    const ix1 = x1 * s.sx, ix2 = x2 * s.sx;

    const iy1 = y1 * s.sy, iy2 = y2 * s.sy;

    const l = Math.max(0, Math.min(ix1, ix2));

    const t = Math.max(0, Math.min(iy1, iy2));

    const r = Math.max(0, imgW - Math.max(ix1, ix2));

    const b = Math.max(0, imgH - Math.max(iy1, iy2));

    dialog.querySelector('#calib-left').value = Math.round(l);

    dialog.querySelector('#calib-top').value = Math.round(t);

    dialog.querySelector('#calib-right').value = Math.round(r);

    dialog.querySelector('#calib-bottom').value = Math.round(b);

  }

  function updateInputRegionFromPoint(x, y) {
    const dispW = imgEl.clientWidth, dispH = imgEl.clientHeight;
    const px = Math.max(0, Math.min(dispW, x));
    const py = Math.max(0, Math.min(dispH, y));
    const region = {
      x: px / dispW,
      y: py / dispH,
      width: 0.01,
      height: 0.01
    };
    overlay.dataset.inputRegion = JSON.stringify(region);
    const status = dialog.querySelector('#calib-focus-status');
    status.textContent = '已记录输入框点击位置，可重新点击调整';
    status.style.color = 'var(--accent-green)';
  }

  function showSavedInputRegion() {
    if (!inputRegion || !imgEl.clientWidth || !imgEl.clientHeight) return;
    inputRectEl.style.display = 'block';
    inputRectEl.style.left = (inputRegion.x * imgEl.clientWidth) + 'px';
    inputRectEl.style.top = (inputRegion.y * imgEl.clientHeight) + 'px';
  }

  function showSavedRegions() {
    showSavedCropRegion();
    showSavedInputRegion();
  }

  if (imgEl.complete) showSavedRegions();
  else imgEl.addEventListener('load', showSavedRegions);



  overlayEl.addEventListener('mousedown', function(e) {

    if (selectionMode === 'input') {
      const rect = imgEl.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      updateInputRegionFromPoint(x, y);
      inputRectEl.style.display = 'block';
      inputRectEl.style.left = x + 'px';
      inputRectEl.style.top = y + 'px';
      return;
    }

    dragging = true;

    const rect = imgEl.getBoundingClientRect();

    startX = e.clientX - rect.left;

    startY = e.clientY - rect.top;

    const activeRect = selectionMode === 'input' ? inputRectEl : rectEl;

    activeRect.style.display = 'block';

    activeRect.style.left = startX + 'px';

    activeRect.style.top = startY + 'px';

    activeRect.style.width = '0px';

    activeRect.style.height = '0px';

  });



  overlayEl.addEventListener('mousemove', function(e) {

    if (!dragging) return;

    const rect = imgEl.getBoundingClientRect();

    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;

    const x = Math.min(startX, cx), y = Math.min(startY, cy);

    const w = Math.abs(cx - startX), h = Math.abs(cy - startY);

    const activeRect = selectionMode === 'input' ? inputRectEl : rectEl;

    activeRect.style.left = x + 'px';

    activeRect.style.top = y + 'px';

    activeRect.style.width = w + 'px';

    activeRect.style.height = h + 'px';

  });



  overlayEl.addEventListener('mouseup', function(e) {

    if (!dragging) return;

    dragging = false;

    const rect = imgEl.getBoundingClientRect();

    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;

    updateCropFromRect(startX, startY, cx, cy);

  });



  // 点击遮罩关闭

  overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });

}

async function saveCalibration(ideKey, monitorName, clientW, clientH) {

  const left = parseInt(document.getElementById('calib-left').value) || 0;

  const right = parseInt(document.getElementById('calib-right').value) || 0;

  const top = parseInt(document.getElementById('calib-top').value) || 0;

  const bottom = parseInt(document.getElementById('calib-bottom').value) || 0;

  const posBtn = document.querySelector('[id^="calib-pos-"].btn-primary');

  const dialogPosition = posBtn ? posBtn.id.replace('calib-pos-', '') : 'center';

  const focusInputEnabled = document.getElementById('calib-focus-enabled').checked;
  const overlay = document.querySelector('div[style*=fixed][data-all-monitors]');
  let inputRegion = null;
  try { inputRegion = overlay && overlay.dataset.inputRegion ? JSON.parse(overlay.dataset.inputRegion) : null; } catch (e) {}
  if (focusInputEnabled && !inputRegion) {
    showToast('请先切换到“输入框位置”，在截图上点击输入框', 'error');
    return;
  }

  const res = await apiCall('/api/save-calibration', 'POST', { key: ideKey, monitor: monitorName, left, right, top, bottom, dialog_position: dialogPosition, calib_width: clientW, calib_height: clientH, focus_input_enabled: focusInputEnabled, input_region: inputRegion });

  if (res && res.success) {

    // 从 overlay 数据属性读取多显示器状态
    const allMonitors = overlay ? (JSON.parse(overlay.dataset.allMonitors || '[]')) : [monitorName];
    const calibratedMonitors = overlay ? (JSON.parse(overlay.dataset.calibratedMonitors || '[]')) : [];
    const newCalibrated = Array.from(new Set([...calibratedMonitors, monitorName]));
    const remaining = allMonitors.filter(m => !newCalibrated.includes(m));

    if (remaining.length > 0) {
      // 还有未校准的显示器 → 提示用户，自动切到下一个显示器
      showToast('已保存 ' + monitorName + '！正在切换到 ' + remaining[0] + '...', 'success');
      const nextMonitor = remaining[0];
      // 关闭当前对话框
      overlay.remove();
      // 调用 maximize-and-calibrate 移到下一个显示器
      showToast('正在移动窗口到 ' + nextMonitor + ' 并最大化...', 'info');
      const nextRes = await apiCall('/api/calibrate-maximize', 'POST', { key: ideKey, monitor_name: nextMonitor });
      if (nextRes && nextRes.success) {
        nextRes.calibrated_monitors = newCalibrated;
        nextRes.recalibrate = false;
        nextRes.crop = nextRes.crop || {};
        nextRes.crop.focus_input_enabled = focusInputEnabled;
        nextRes.crop.input_region = inputRegion;
        showCalibrationDialog(ideKey, nextRes);
      } else {
        showToast(nextRes ? nextRes.message : '切换显示器失败', 'error');
      }
    } else {
      showToast('校准已保存！所有显示器已完成校准。', 'success');
      if (overlay) overlay.remove();
    }

  } else {

    showToast(res ? res.message : '保存失败', 'error');

  }

}

async function _recalibrateCurrent(ideKey, monitorName) {
  // 重新截图当前显示器（窗口已最大化），保留已校准的显示器列表
  const overlay = document.querySelector('div[style*=fixed][data-all-monitors]');
  const allMonitors = overlay ? (JSON.parse(overlay.dataset.allMonitors || '[]')) : [monitorName];
  const calibratedMonitors = overlay ? (JSON.parse(overlay.dataset.calibratedMonitors || '[]')) : [];
  showToast('正在重新截图 ' + monitorName + '...', 'info');
  const res = await apiCall('/api/calibrate', 'POST', { key: ideKey });
  if (!res || !res.success) {
    showToast(res ? res.message : '重新截图失败', 'error');
    return;
  }
  res.all_monitors = allMonitors;
  res.calibrated_monitors = calibratedMonitors;
  res.recalibrate = true;
  // 关闭旧对话框，打开新对话框
  if (overlay) overlay.remove();
  showCalibrationDialog(ideKey, res);
}

function resetCalibration() {

  document.getElementById('calib-left').value = 0;

  document.getElementById('calib-right').value = 0;

  document.getElementById('calib-top').value = 0;

  document.getElementById('calib-bottom').value = 0;

  document.getElementById('calib-rect').style.display = 'none';

  const focusCheckbox = document.getElementById('calib-focus-enabled');
  const inputRect = document.getElementById('calib-input-rect');
  const overlay = document.querySelector('div[style*=fixed][data-all-monitors]');
  if (focusCheckbox) focusCheckbox.checked = false;
  if (inputRect) inputRect.style.display = 'none';
  if (overlay) overlay.dataset.inputRegion = '';
  const inputModeBtn = document.getElementById('calib-mode-input');
  const focusStatus = document.getElementById('calib-focus-status');
  if (inputModeBtn) inputModeBtn.disabled = true;
  if (focusStatus) {
    focusStatus.textContent = '勾选后切换到“输入框区域”并在截图上拖框';
    focusStatus.style.color = 'var(--text-muted)';
  }

}

async function triggerSystemScreenshot() {

  await apiCall('/api/trigger-screenshot', 'POST');

}

function switchDialogPosition(btn, pos) {

  document.querySelectorAll('[id^="calib-pos-"]').forEach(b => {

    b.className = 'btn btn-sm btn-outline';

  });

  btn.className = 'btn btn-sm btn-primary';

}

async function toggleIdeFromManager(key, name) {

  const btn = document.getElementById('ide-toggle-' + key);

  const isRunning = btn && btn.textContent.includes('运行中');

  if (isRunning) {

    showToast('正在关闭 ' + name + '...', 'info');

    await apiCall('/api/stop-ide', 'POST', { key });

  } else {

    showToast('正在启动 ' + name + '...', 'info');

    await apiCall('/api/launch-ide', 'POST', { key });

  }

  loadIdeRunningStatus();

}

async function scanIdes() {

  showToast('正在扫描本机 IDE 安装路径...', 'info');

  const res = await apiCall('/api/scan-ides', 'POST');

  if (res && (res.success !== false) && Array.isArray(res.ides)) {

    const count = typeof res.count === 'number' ? res.count : res.ides.length;
    showToast(res.message || `扫描完成！发现 ${count} 个 IDE。`, 'success');

    loadIdes();

  } else {

    showToast('扫描失败: ' + (res ? res.message : '未知错误'), 'error');

  }

}

function showAddIdeDialog() {
  // 弹窗：优先从桌面选择 IDE 快捷方式/入口，系统自动解析真实 exe。
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px;';
  overlay.innerHTML = '<div style="background:var(--panel);border:1px solid var(--border-color);border-radius:12px;padding:20px;width:min(560px,96vw);">' +
    '<h3 style="margin:0 0 12px 0;">➕ 添加自定义 IDE</h3>' +
    '<div style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">请选择桌面上的 IDE 快捷方式或应用入口，系统会自动解析真实程序并填充信息。</div>' +
    '<label style="display:block;font-size:12px;color:var(--text-muted);margin-bottom:4px;">IDE 入口</label>' +
    '<div style="display:flex;gap:8px;margin-bottom:12px;">' +
      '<input id="add-ide-path" type="text" placeholder="点击右侧按钮选择 exe..." style="flex:1;padding:8px;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-secondary);color:var(--text);font-size:13px;" readonly />' +
      '<button class="btn btn-sm btn-primary" id="add-ide-browse" style="white-space:nowrap;">📁 用户桌面</button>' +
      '<button class="btn btn-sm btn-outline" id="add-ide-browse-public" style="white-space:nowrap;">🌐 公共桌面</button>' +
    '</div>' +
    '<div style="display:flex;gap:12px;margin-bottom:12px;">' +
      '<div style="flex:1;">' +
        '<label style="display:block;font-size:12px;color:var(--text-muted);margin-bottom:4px;">显示名称</label>' +
        '<input id="add-ide-name" type="text" placeholder="如 WorkBuddy" style="width:100%;padding:8px;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-secondary);color:var(--text);font-size:13px;" />' +
      '</div>' +
      '<div style="flex:1;">' +
        '<label style="display:block;font-size:12px;color:var(--text-muted);margin-bottom:4px;">IDE 标识 (key)</label>' +
        '<input id="add-ide-key" type="text" placeholder="如 workbuddy" style="width:100%;padding:8px;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-secondary);color:var(--text);font-size:13px;" />' +
      '</div>' +
    '</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
      '<button class="btn btn-sm btn-outline" id="add-ide-cancel">取消</button>' +
      '<button class="btn btn-sm btn-primary" id="add-ide-confirm" disabled>确认添加</button>' +
    '</div>' +
  '</div>';
  document.body.appendChild(overlay);

  const pathInput = overlay.querySelector('#add-ide-path');
  const nameInput = overlay.querySelector('#add-ide-name');
  const keyInput = overlay.querySelector('#add-ide-key');
  const confirmBtn = overlay.querySelector('#add-ide-confirm');
  const cancelBtn = overlay.querySelector('#add-ide-cancel');
  const browseBtn = overlay.querySelector('#add-ide-browse');
  const publicBrowseBtn = overlay.querySelector('#add-ide-browse-public');

  function close() { overlay.remove(); }
  cancelBtn.onclick = close;
  overlay.addEventListener('click', function(e) { if (e.target === overlay) close(); });

  async function browseIde(startDir, button, label) {
    button.disabled = true;
    button.textContent = '选择中...';
    try {
      const payload = { title: label };
      if (startDir) payload.start_dir = startDir;
      const res = await apiCall('/api/browse-path', 'POST', payload);
      if (res && res.ok && res.path) {
        pathInput.value = res.path;
        // 从 exe 文件名提取默认 name 和 key（如 WorkBuddy.exe → WorkBuddy / workbuddy）
        const basename = res.path.split(/[\\/]/).pop().replace(/\.(exe|cmd|bat)$/i, '');
        if (basename) {
          nameInput.value = basename;
          keyInput.value = basename.toLowerCase();
          confirmBtn.disabled = false;
        }
      } else if (res && res.cancelled) {
        // 用户取消，不报错
      } else {
        showToast(res ? res.message : '选择失败', 'error');
      }
    } catch (e) {
      showToast('网络错误: ' + e.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = label.includes('公共') ? '🌐 公共桌面' : '📁 用户桌面';
    }
  }
  browseBtn.onclick = () => browseIde('', browseBtn, '从用户桌面选择 IDE 入口');
  publicBrowseBtn.onclick = () => browseIde('C:\\Users\\Public\\Desktop', publicBrowseBtn, '从公共桌面选择 IDE 入口');

  confirmBtn.onclick = async function() {
    const path = pathInput.value.trim();
    const name = nameInput.value.trim();
    const key = keyInput.value.trim().toLowerCase();
    if (!path || !name || !key) {
      showToast('请填写完整信息', 'error');
      return;
    }
    confirmBtn.disabled = true;
    confirmBtn.textContent = '保存中...';
    try {
      const res = await apiCall('/api/manual-ides', 'POST', { key, name, path });
      // 后端返回 {ok: true}，旧代码误检查 success 导致永远走 else 分支
      if (res && res.ok) {
        showToast('IDE 保存成功！请确保该 IDE 已打开，即将进入窗口绑定...', 'success');
        await loadIdes();
        close();
        // 自动串联：自定义添加后依次进入 绑定窗口 → 校准
        openIdeWindowBinding(key, name, true);
      } else {
        showToast('保存失败: ' + (res ? res.message : '未知错误'), 'error');
        confirmBtn.disabled = false;
        confirmBtn.textContent = '确认添加';
      }
    } catch (e) {
      showToast('网络错误: ' + e.message, 'error');
      confirmBtn.disabled = false;
      confirmBtn.textContent = '确认添加';
    }
  };
}

function editIdePath(key, name, currentPath) {

  const newPath = prompt(`修改 ${name} (${key}) 的可执行文件路径:`, currentPath);

  if (newPath === null) return;

  apiCall('/api/manual-ides', 'POST', { key, name, path: newPath }).then(res => {

    // 后端返回 {ok: true}，旧代码误检查 success 导致永远走 else 分支
    if (res && res.ok) {

      showToast('路径更新成功！', 'success');

      loadIdes();

    } else {

      showToast('更新失败: ' + (res ? res.message : '未知错误'), 'error');

    }

  });

}

function renameIdeKey(key, name, currentPath) {

  const newKey = prompt(`请输入 ${name} 的 IDE 标识(Key):`, key || '');

  if (newKey === null) return;

  const trimmed = newKey.trim().toLowerCase();

  if (!trimmed) {

    showToast('Key 不能为空', 'error');

    return;

  }

  apiCall('/api/desktop-ides/rename', 'POST', { key, new_key: trimmed, name, path: currentPath }).then(res => {

    if (res && res.ok) {

      showToast(res.message || 'Key 已更新', 'success');

      loadIdes();

    } else {

      showToast('修改 Key 失败: ' + (res ? res.message : '未知错误'), 'error');

    }

  });

}

async function launchIde(key) {

  showToast(`正在启动 ${key.toUpperCase()}...`, 'info');

  const res = await apiCall('/api/launch-ide', 'POST', { key });

  if (res && res.success) {

    showToast(res.message, 'success');

  } else {

    showToast(res ? res.message : '启动失败', 'error');

  }

}

async function stopIde(key, name) {

  if (!confirm(`确定要关闭 ${name} (${key}) 吗？`)) return;

  showToast(`正在关闭 ${key.toUpperCase()}...`, 'info');

  const res = await apiCall('/api/stop-ide', 'POST', { key });

  if (res && res.success) {

    showToast(res.message, 'success');

  } else {

    showToast(res ? res.message : '关闭失败', 'error');

  }

}

async function deleteIde(key) {

  if (!confirm(`确定要删除手动配置 of IDE [${key}] 吗？`)) return;

  const res = await apiCall('/api/manual-ides', 'DELETE', { key });

  // 后端返回 {ok: true}，旧代码误检查 success 导致永远走 else 分支
  if (res && res.ok) {

    showToast('删除成功！', 'success');

    loadIdes();

  } else {

    showToast('删除失败: ' + (res ? res.message : '未知错误'), 'error');

  }

}

async function deleteDesktopIde(key) {
  if (!confirm(`确定要删除本机 IDE 条目 [${key}] 吗？删除后可重新扫描恢复。`)) return;
  const res = await apiCall('/api/desktop-ides/' + encodeURIComponent(key), 'DELETE');
  if (res && res.ok) {
    showToast('IDE 条目已删除', 'success');
    loadIdes();
  } else {
    showToast('删除失败: ' + (res ? res.message : '未知错误'), 'error');
  }
}

let _deviceAutoRefreshTimer = null;

function toggleAutoRefresh() {
  const btn = document.getElementById('btn-auto-refresh');
  if (_deviceAutoRefreshTimer) {
    clearInterval(_deviceAutoRefreshTimer);
    _deviceAutoRefreshTimer = null;
    btn.textContent = '⏱ 自动刷新';
    btn.classList.remove('btn-primary');
    btn.classList.add('btn-outline');
  } else {
    _deviceAutoRefreshTimer = setInterval(loadDevices, 5000);
    btn.textContent = '⏱ 停止刷新';
    btn.classList.remove('btn-outline');
    btn.classList.add('btn-primary');
    loadDevices();
  }
}

async function loadFrpStatus() {
  try {
    const res = await apiCall('/api/frp/status');
    const textEl = document.getElementById('frp-status-text');
    const btnEl = document.getElementById('btn-frp-toggle');
    if (!res || !textEl) return;
    if (res.running) {
      textEl.innerHTML = `🌐 FRP: <span style="color:var(--accent-green)">✅ 已开启</span> → ${res.public_url || '---'}`;
      btnEl.textContent = '⏹ 关闭';
    } else {
      textEl.innerHTML = '🌐 FRP: <span style="color:var(--text-muted)">⭕ 未开启</span>';
      btnEl.textContent = '🚀 开启';
    }
  } catch (e) {}
}

async function toggleFrp() {
  const btn = document.getElementById('btn-frp-toggle');
  btn.disabled = true;
  btn.textContent = '操作中...';
  try {
    const res = await apiCall('/api/frp/status');
    if (res && res.running) {
      await apiCall('/api/frp/stop', 'POST');
      showToast('FRP 已关闭', 'info');
    } else {
      await apiCall('/api/frp/start', 'POST');
      showToast('FRP 已开启', 'success');
    }
    loadFrpStatus();
  } catch (e) {
    showToast('FRP 操作失败: ' + e.message, 'error');
  }
  btn.disabled = false;
}

async function loadDevices() {

  const listEl = document.getElementById('devices-list');

  const selectEl = document.getElementById('device-select');

  listEl.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">正在加载设备列表...</div>';
  loadFrpStatus();

  try {

    const res = await apiCall('/api/devices');

    if (!res || !res.ok) {

      throw new Error(res ? res.error : '网络错误');

    }

    const devices = res.devices || [];

    const aliases = res.aliases || {};

    

    if (devices.length === 0) {

      listEl.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">暂无已连接设备（请确保手机已打开 AideLink）</div>';

    } else {

      listEl.innerHTML = devices.map(d => {

        const alias = d.alias || '未设置';
        const online = d.is_online;
        const statusText = online ? '🟢 在线' : '⚪ 离线';
        const adbStatus = d.is_adb_connected ? ' · ✅ ADB' : '';
        const adbInfo = d.adb_port ? `${d.ip}:${d.adb_port}` : (d.ip || '未知');
        const onlineIp = d.online_ip && d.online_ip !== d.ip ? ` (当前: ${d.online_ip})` : '';
        const modelInfo = d.model ? d.model : '';
        const brandInfo = d.brand ? d.brand : '';
        const deviceInfo = [brandInfo, modelInfo].filter(Boolean).join(' ') || '';
        const serialInfo = d.serial ? `SN: ${d.serial}` : '';
        const ipChanged = d.ip_changed ? '<span style="color:var(--accent-yellow);margin-left:6px;" title="IP 已变更">⚠️ IP变更</span>' : '';
        const ips = d.ips || [];
        const ipsInfo = ips.length > 0 ? `<div style="color:var(--text-dim);font-size:10px;margin-top:4px;">历史IP: ${ips.join(', ')}</div>` : '';

        return `<div style="padding: 10px 12px; background: var(--bg-tertiary); border-radius: 6px; margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="min-width:0;">
              <strong style="color: ${online ? 'var(--accent-green)' : 'var(--accent-blue)'};">${alias}</strong>
              ${deviceInfo ? `<span style="color: var(--text-muted); margin-left: 8px; font-size: 12px;">${deviceInfo}</span>` : ''}
              ${serialInfo ? `<span style="color: var(--text-dim); margin-left: 6px; font-size: 11px;">${serialInfo}</span>` : ''}
              ${ipChanged}
            </div>
            <div style="font-size: 12px; color: var(--text-muted); white-space:nowrap;">
              ${statusText}${adbStatus}${onlineIp}
            </div>
          </div>
          ${ipsInfo}
          <div style="display:flex;gap:6px;margin-top:6px;">
            ${online && !d.is_adb_connected ? `<button class="btn btn-sm btn-outline" style="padding:2px 8px;font-size:11px;" onclick="enableWirelessAdb('${d.online_ip || d.ip || ''}', '${alias}')">📡 开启调试</button>` : ''}
            ${d.is_adb_connected && d.device_id ? `<button class="btn btn-sm btn-outline" style="padding:2px 8px;font-size:11px;" onclick="disconnectAdb('${d.device_id}', '${alias}')">🔌 断开</button>` : ''}
            ${d.alias ? `<button class="btn btn-sm btn-outline" style="padding:2px 8px;font-size:11px;color:var(--accent-red);" onclick="deleteDeviceAlias('${d.alias}')">🗑 删除</button>` : ''}
          </div>
        </div>`;

      }).join('');

    }

    

    selectEl.innerHTML = devices.length === 0 

      ? '<option value="">暂无设备</option>'

      : devices.map(d => {

          const info = [d.brand, d.model].filter(Boolean).join(' ');

          const label = d.alias 

            ? (info ? `${d.alias} (${info})` : `${d.alias} (${d.ip || '未知'})`)

            : (info ? `${info} - ${d.ip || '未知'}` : (d.ip || '未知'));

          const port = d.adb_port || 5555;

          return `<option value="${d.ip || ''}" data-port="${port}">${label}</option>`;

        }).join('');

    

  } catch (e) {

    console.error('Failed to load devices:', e);

    listEl.innerHTML = `<div style="color: var(--accent-red); font-size: 12px;">加载失败: ${e.message}</div>`;

  }

}

async function setDeviceAlias() {

  const selectEl = document.getElementById('device-select');

  const ip = selectEl.value;

  const port = parseInt(selectEl.selectedOptions[0]?.dataset.port) || 5555;

  const alias = document.getElementById('device-alias').value.trim();

  

  if (!ip) {

    showToast('请选择设备', 'error');

    return;

  }

  if (!alias) {

    showToast('请输入别名', 'error');

    return;

  }

  

  try {

    const res = await apiCall('/api/devices/alias', 'POST', { ip, alias, port });

    if (!res || !res.ok) {

      throw new Error(res ? res.error : '网络错误');

    }

    

    showToast(`已设置别名 '${alias}'`, 'success');

    document.getElementById('device-alias').value = '';

    await loadDevices();

  } catch (e) {

    showToast('设置失败: ' + e.message, 'error');

  }

}

async function deleteDeviceAlias(alias) {

  if (!confirm(`确定要删除别名 '${alias}' 吗？`)) {

    return;

  }

  

  try {

    const res = await apiCall(`/api/devices/alias/${alias}`, 'DELETE');

    if (!res || !res.ok) {

      throw new Error(res ? res.error : '网络错误');

    }

    

    showToast(`已删除别名 '${alias}'`, 'success');

    await loadDevices();

  } catch (e) {

    showToast('删除失败: ' + e.message, 'error');

  }

}

async function enableWirelessAdb(ip, alias) {
  const label = alias || ip;
  const btn = event && event.target;
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 连接中...'; }
  showToast(`正在为 ${label} 开启无线调试...`, 'info');
  try {
    const res = await apiCall('/api/adb/connect', 'POST', { ip, timeout: 30 });
    if (res && res.ok) {
      const method = res.method || 'unknown';
      const methodLabel = method === 'root' ? 'Root' : method === 'shizuku' ? 'Shizuku' : method === 'usb_tcpip' ? 'USB切换' : method;
      showToast(`${label} 已连接 (${methodLabel})`, 'success');
      await loadDevices();
    } else {
      showToast(`${label} 连接失败: ${res ? res.error : '网络错误'}\n提示: 需要 Root 或 Shizuku 才能远程开启无线调试`, 'error');
    }
  } catch (e) {
    showToast(`连接失败: ${e.message}`, 'error');
  }
  if (btn) { btn.disabled = false; btn.textContent = '📡 开启调试'; }
}

async function disconnectAdb(deviceId, alias) {
  const label = alias || deviceId;
  if (!confirm(`确定要断开 ${label} 的 ADB 连接吗？`)) return;
  try {
    const res = await apiCall('/api/adb/disconnect', 'POST', { device_id: deviceId });
    if (res && res.ok) {
      showToast(`${label} 已断开`, 'success');
      await loadDevices();
    } else {
      showToast(`断开失败: ${res ? res.error : '未知错误'}`, 'error');
    }
  } catch (e) {
    showToast(`断开失败: ${e.message}`, 'error');
  }
}

async function loadOcWebConfig() {

  const res = await apiCall('/settings');

  if (!res || !res.settings) return;

  document.getElementById('cfg-oc-web-port').value = res.settings.opencode_web_port || 4096;

  document.getElementById('cfg-oc-web-pwd').value = res.settings.opencode_web_password || '';

}

async function saveOcWebConfig() {

  const saveEl = document.getElementById('oc-web-save-result');

  saveEl.textContent = '保存中...';

  saveEl.style.color = 'var(--text-muted)';

  const body = {

    opencode_web_port: parseInt(document.getElementById('cfg-oc-web-port').value) || 4096,

    opencode_web_password: document.getElementById('cfg-oc-web-pwd').value,

  };

  const res = await apiCall('/settings', 'POST', body);

  if (res && res.ok) {

    saveEl.textContent = '✅ 已保存';

    saveEl.style.color = 'var(--ok)';

  } else {

    saveEl.textContent = '❌ 保存失败: ' + (res ? res.message : '网络错误');

    saveEl.style.color = 'var(--err)';

  }

}

function loadCachedIdeStatus() {

  try {

    const cached = localStorage.getItem('ide-status-cache');

    if (cached) {

      const data = JSON.parse(cached);

      // 缓存 30 秒内有效

      if (Date.now() - data.ts < 30000) {

        runningIdes = new Set(data.running || []);

        ideStatusLoaded = true;

        renderIdeButtons();

        return true;

      }

    }

  } catch (e) {}

  return false;

}

function saveIdeStatusCache(running) {

  try {

    localStorage.setItem('ide-status-cache', JSON.stringify({ ts: Date.now(), running: running }));

  } catch (e) {}

}

async function loadIdeStatus() {

  // 先用缓存快速渲染

  if (!ideStatusLoaded) {

    loadCachedIdeStatus();

  }

  // 后台刷新真实状态

  try {

    const res = await apiCall('/api/ide/active_status');

    if (res && res.ides) {

      const runningList = res.ides.filter(i => i.running).map(i => i.key);

      runningIdes = new Set(runningList);

      saveIdeStatusCache(runningList);

      ideStatusLoaded = true;

      renderIdeButtons(res.ides);

    }

  } catch (e) {}

}

function renderIdeButtons(ideStatusList = []) {

  const container = document.getElementById('ide-quick-select');

  if (!container) return;

  

  // 如果没有传入状态列表，使用基础 IDE 列表进行降级渲染

  const statusMap = {};

  if (ideStatusList && ideStatusList.length > 0) {

    ideStatusList.forEach(item => {

      statusMap[item.key] = item;

    });

  }



  const desktopIdes = IDE_LIST.filter(ide => ide.type === 'desktop');

  const webIdes = IDE_LIST.filter(ide => ide.type === 'web');



  function ideBtnHtml(ide) {

    const statusInfo = statusMap[ide.key] || { running: runningIdes.has(ide.key), status: 'idle' };

    const isRunning = statusInfo.running;

    const isBusy = statusInfo.status === 'busy';

    

    let bg = 'var(--bg-tertiary)';

    let border = 'var(--border-color)';

    let color = 'var(--text-muted)';

    let statusDot = '⚪';

    

    if (isRunning) {

      if (isBusy) {

        bg = 'rgba(210,153,34,0.15)';

        border = 'rgba(210,153,34,0.4)';

        color = 'var(--accent-yellow)';

        statusDot = '🟡';

      } else {

        bg = 'rgba(70,201,122,0.15)';

        border = 'rgba(70,201,122,0.4)';

        color = 'var(--accent-green)';

        statusDot = '🟢';

      }

    }

    

    const tooltip = isRunning 

      ? `${ide.name} 运行中 (${isBusy ? '正忙' : '空闲'}) | 单击派发 · 双击关闭` 

      : `${ide.name} 未运行 | 单击启动并派发 · 双击启动`;



    return `<button class="btn btn-sm" 

      onclick="quickDispatch('${ide.key}')" 

      ondblclick="toggleIde('${ide.key}', event)"

      style="background:${bg};border:1px solid ${border};color:${color};font-size:12px;padding:4px 10px;cursor:pointer;"

      title="${tooltip}">

      ${statusDot} ${ide.icon} ${ide.name}

    </button>`;

  }



  let html = '<span style="font-size:11px;color:var(--text-muted);margin-right:4px;">💻 桌面端</span>';

  html += desktopIdes.map(ideBtnHtml).join('');

  html += '<span style="font-size:11px;color:var(--text-muted);margin:0 4px 0 12px;">🌐 Web</span>';

  html += webIdes.map(ideBtnHtml).join('');

  container.innerHTML = html;

}

async function toggleIde(ideKey, event) {

  event.preventDefault();

  event.stopPropagation();

  const isRunning = runningIdes.has(ideKey);

  if (isRunning) {

    showToast(`正在关闭 ${ideKey.toUpperCase()}...`, 'info');

    await apiCall('/api/stop-ide', 'POST', { key: ideKey });

    runningIdes.delete(ideKey);

  } else {

    showToast(`正在启动 ${ideKey.toUpperCase()}...`, 'info');

    await apiCall('/api/launch-ide', 'POST', { key: ideKey });

    runningIdes.add(ideKey);

  }

  renderIdeButtons();

}

async function activateIdeAndShowModal(ideKey, mon) {

  try {

    await apiCall('/api/focus-ide', 'POST', { key: ideKey });

  } catch (e) {

    console.error("Focus IDE failed:", e);

  }

  showScreenshotModal(ideKey, mon);

}

function dispatchTestTask(taskId, originalIde) {

  const task = allTasksData.find(t => t.task_id === taskId);

  if (!task) { showToast('找不到任务', 'error'); return; }



  const origMsg = task.message || '';

  const origTitle = task.title || '';



  // 弹出选择 IDE 的对话框

  const overlay = document.createElement('div');

  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;display:flex;align-items:center;justify-content:center;';

  overlay.innerHTML = `

    <div style="background:var(--panel);border:1px solid var(--border-color);border-radius:12px;padding:20px;width:90%;max-width:450px;">

      <h3 style="margin-bottom:12px;font-size:15px;">🧪 派发测试任务</h3>

      <div style="margin-bottom:8px;font-size:12px;color:var(--text-muted);">

        原始任务: <span style="color:var(--text-secondary);">${escapeHtml((origTitle || origMsg).substring(0, 80))}</span>

      </div>

      <div style="margin-bottom:8px;font-size:12px;color:var(--text-muted);">

        修改 IDE: <span style="color:var(--accent-blue);font-weight:600;">${originalIde.toUpperCase()}</span>

      </div>

      <div class="field" style="margin-bottom:12px;">

        <label style="display:block;margin-bottom:6px;font-size:13px;font-weight:500;">选择测试 IDE</label>

        <select id="test-ide-select" style="width:100%;background:#0c0e13;color:var(--text);border:1px solid var(--border-color);border-radius:6px;padding:8px 10px;font-size:13px;">

          <option value="trae" ${originalIde === 'trae' ? 'disabled' : ''}>Trae ${originalIde === 'trae' ? '(修改中)' : ''}</option>

          <option value="agy" ${originalIde === 'agy' ? 'disabled' : ''}>Antigravity ${originalIde === 'agy' ? '(修改中)' : ''}</option>

          <option value="mimo" ${originalIde === 'mimo' ? 'disabled' : ''}>MiMoCode ${originalIde === 'mimo' ? '(修改中)' : ''}</option>

          <option value="oc" ${originalIde === 'oc' ? 'disabled' : ''}>OpenCode ${originalIde === 'oc' ? '(修改中)' : ''}</option>

        </select>

      </div>

      <div style="display:flex;gap:8px;justify-content:flex-end;">

        <button class="btn btn-sm btn-outline" onclick="this.closest('div[style*=fixed]').remove()">取消</button>

        <button class="btn btn-sm btn-primary" onclick="submitTestTask('${escapeHtml(taskId)}')">🧪 派发测试</button>

      </div>

    </div>

  `;

  document.body.appendChild(overlay);

  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

}

async function submitTestTask(taskId) {

  const select = document.getElementById('test-ide-select');

  const testIde = select ? select.value : '';

  if (!testIde) { showToast('请选择测试 IDE', 'error'); return; }



  // 关闭弹窗

  const overlay = select.closest('div[style*="fixed"]');

  if (overlay) overlay.remove();



  showToast('正在派发测试任务...', 'info');

  const res = await apiCall('/api/tasks/test', 'POST', { task_id: taskId, test_ide: testIde });

  if (res && res.success) {

    showToast(res.message, 'success');

    loadTasksList();

  } else {

    showToast(res ? res.message : '派发失败', 'error');

  }

}

async function quickDispatch(ideKey) {

  const selectedCbs = document.querySelectorAll('.task-row-checkbox:checked');

  if (selectedCbs.length === 0) {

    showToast('请先勾选要派发的任务', 'error');

    return;

  }

  const taskIds = Array.from(selectedCbs).map(cb => cb.getAttribute('data-id'));

  

  // 如果 IDE 未运行，先启动

  if (!runningIdes.has(ideKey)) {

    showToast(`正在启动 ${ideKey.toUpperCase()}...`, 'info');

    await apiCall('/api/launch-ide', 'POST', { key: ideKey });

    runningIdes.add(ideKey);

    renderIdeButtons();

  }

  

  // 派发任务

  showToast(`正在派发 ${taskIds.length} 个任务到 ${ideKey.toUpperCase()}...`, 'info');

  const res = await apiCall('/api/tasks/dispatch', 'POST', { task_ids: taskIds, target_ide: ideKey });

  if (res && res.success) {

    showToast(res.message, 'success');

    loadTasksList();

  } else {

    showToast(res ? res.message : '派发失败', 'error');

  }

}

async function installMcpForIde(ideKey) {
  showToast('正在为 ' + ideKey + ' 配置 MCP...', 'info');
  try {
    const res = await apiCall('/api/ide/install-mcp', 'POST', { key: ideKey });
    if (res && res.success) {
      showToast('✅ ' + res.message, 'success');
    } else {
      showToast('❌ ' + (res ? res.message : '请求失败'), 'error');
    }
  } catch (e) {
    showToast('❌ 网络错误: ' + e, 'error');
  }
}
