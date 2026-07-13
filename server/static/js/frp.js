// FRP 代理管理已拆到 frp.js

/* ========== FRP 代理管理 ========== */

let currentFrpProxies = [];

function toggleSetupGuide() {

  const guide = document.getElementById('frp-setup-guide');

  const icon = document.getElementById('guide-toggle-icon');

  if (!guide) return;

  const visible = guide.style.display !== 'none';

  guide.style.display = visible ? 'none' : 'block';

  if (icon) icon.textContent = visible ? '▼' : '▲';

  if (!visible) renderSetupGuide();

}

function renderSetupGuide() {

  const addr = (document.getElementById('cfg-frp-server-addr') || {}).value || '';

  const port = (document.getElementById('cfg-frp-server-port') || {}).value || '7000';

  const token = (document.getElementById('cfg-frp-token') || {}).value || '';

  const sshEl = document.getElementById('guide-ssh');

  const dlEl = document.getElementById('guide-download');

  const cfgEl = document.getElementById('guide-config');

  if (!sshEl || !dlEl || !cfgEl) return;

  const host = addr.replace(/^https?:\/\//, '').replace(/:\d+$/, '').trim();

  sshEl.textContent = 'ssh root@' + (host || '<你的服务器IP>');

  dlEl.textContent = [

    'wget -qO- https://github.com/fatedier/frp/releases/download/v0.54.0/frp_0.54.0_linux_amd64.tar.gz | tar xz',

    'cd frp_0.54.0_linux_amd64'

  ].join('\n');

  const lines = ['cat > frps.toml << \'EOF\''];

  lines.push('bindPort = ' + port);

  if (token) {

    lines.push('');

    lines.push('auth.method = "token"');

    lines.push('auth.token = "' + token + '"');

  }

  lines.push('EOF');

  lines.push('');

  lines.push('./frps -c frps.toml');

  cfgEl.textContent = lines.join('\n');

}

async function loadFrpServerConfig() {

  const cfg = await apiCall('/api/config');

  const frp = (cfg.config || cfg).frp || {};

  document.getElementById('cfg-frp-enabled').checked = !!frp.enabled;

  document.getElementById('cfg-frp-server-addr').value = frp.server_addr || '';

  document.getElementById('cfg-frp-server-port').value = frp.server_port || 7000;

  document.getElementById('cfg-frp-token').value = frp.token || '';

  toggleFrpForm(!!frp.enabled);

}

async function saveFrpServerConfig() {

  const cfg = await apiCall('/api/config');

  const data = cfg.config || cfg;

  data.frp = data.frp || {};

  data.frp.enabled = document.getElementById('cfg-frp-enabled').checked;

  data.frp.server_addr = document.getElementById('cfg-frp-server-addr').value;

  data.frp.server_port = parseInt(document.getElementById('cfg-frp-server-port').value) || 7000;

  data.frp.token = document.getElementById('cfg-frp-token').value;

  if (!data.frp.type) data.frp.type = 'http';

  if (!data.frp.custom_domains) data.frp.custom_domains = '';

  if (!data.frp.remote_port) data.frp.remote_port = 5000;

  showToast('正在保存服务器配置...', 'info');

  const result = await apiCall('/api/config', 'POST', data);

  if (result && result.success !== false) {

    showToast('服务器配置已保存', 'success');

  } else {

    showToast('保存失败: ' + (result ? result.message : '未知错误'), 'error');

  }

}

async function loadFrpProxies() {

  const tbody = document.getElementById('frp-proxy-table');

  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text-muted)">加载中...</td></tr>';

  const res = await apiCall('/api/frp/proxies');

  if (res && res.ok) {

    currentFrpProxies = res.proxies || [];

    renderFrpProxyTable();

    loadFrpServerConfig();

  } else {

    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--accent-red)">加载失败: ${res ? (res.error || res.message || '未知错误') : '网络错误'}</td></tr>`;

  }

}

function renderFrpProxyTable() {

  const tbody = document.getElementById('frp-proxy-table');

  if (!tbody) return;

  tbody.innerHTML = '';

  if (currentFrpProxies.length === 0) {

    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text-muted)">无代理规则，点击 ➕ 新增</td></tr>';

    return;

  }

  currentFrpProxies.forEach((p, idx) => {

    const tr = document.createElement('tr');

    const isHttp = p.type === 'http' || p.type === 'https';

    const remoteVal = isHttp ? (p.custom_domains || '') : (p.remote_port || '');

    const placeholder = isHttp ? '域名 (例如: your-domain.com)' : '公网端口 (例如: 5000)';

    tr.innerHTML = `

      <td><input type="text" class="table-input" value="${escapeHtml(p.name || '')}" onchange="updateFrpProxyField(${idx}, 'name', this.value)"></td>

      <td>

        <select class="table-select" onchange="updateFrpProxyType(${idx}, this.value)">

          <option value="tcp" ${p.type === 'tcp' ? 'selected' : ''}>tcp</option>

          <option value="udp" ${p.type === 'udp' ? 'selected' : ''}>udp</option>

          <option value="http" ${p.type === 'http' ? 'selected' : ''}>http</option>

          <option value="https" ${p.type === 'https' ? 'selected' : ''}>https</option>

        </select>

      </td>

      <td><input type="text" class="table-input" value="${escapeHtml(p.local_ip || '127.0.0.1')}" onchange="updateFrpProxyField(${idx}, 'local_ip', this.value)"></td>

      <td><input type="number" class="table-input" value="${p.local_port || ''}" onchange="updateFrpProxyField(${idx}, 'local_port', parseInt(this.value))"></td>

      <td><input type="text" class="table-input" placeholder="${placeholder}" value="${escapeHtml(String(remoteVal))}" onchange="updateFrpProxyRemote(${idx}, this.value)"></td>

      <td style="text-align:center"><button class="btn btn-sm btn-danger" onclick="deleteFrpProxyRow(${idx})">🗑️</button></td>

    `;

    tbody.appendChild(tr);

  });

}

function updateFrpProxyField(idx, field, value) {

  if (currentFrpProxies[idx]) currentFrpProxies[idx][field] = value;

}

function updateFrpProxyType(idx, value) {

  if (!currentFrpProxies[idx]) return;

  const p = currentFrpProxies[idx];

  p.type = value;

  if (value === 'http' || value === 'https') {

    p.remote_port = 0;

  } else {

    p.custom_domains = '';

  }

  renderFrpProxyTable();

}

function updateFrpProxyRemote(idx, value) {

  if (!currentFrpProxies[idx]) return;

  const p = currentFrpProxies[idx];

  if (p.type === 'http' || p.type === 'https') {

    p.custom_domains = value;

  } else {

    p.remote_port = parseInt(value) || 0;

  }

}

function addFrpProxyRow() {

  currentFrpProxies.push({

    name: 'new-proxy',

    type: 'tcp',

    local_ip: '127.0.0.1',

    local_port: 8080,

    custom_domains: '',

    remote_port: 8080

  });

  renderFrpProxyTable();

}

function deleteFrpProxyRow(idx) {

  currentFrpProxies.splice(idx, 1);

  renderFrpProxyTable();

}

async function saveFrpProxies() {

  showToast('正在保存代理配置...', 'info');

  const res = await apiCall('/api/frp/proxies/save', 'POST', { proxies: currentFrpProxies });

  if (res && res.ok) {

    showToast(res.restarted ? '配置已保存，frpc 已重启' : '配置已保存', 'success');

    loadFrpProxies();

  } else {

    showToast('保存失败: ' + (res ? (res.error || '未知错误') : '网络错误'), 'error');

  }

}
