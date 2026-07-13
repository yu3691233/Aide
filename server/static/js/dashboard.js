async function refreshStatus() {

  const status = await apiCall('/api/status');

  const sysInfo = status.system || {};

  const svc = status.service || {};



  // 状态卡片

  const cards = document.getElementById('status-cards');

  const statusBadge = svc.running

    ? '<span class="badge badge-success">● 运行中</span>'

    : '<span class="badge badge-danger">● 已停止</span>';

  cards.innerHTML = `

    <div class="stat-card">

      <div class="stat-icon ${svc.running ? 'green' : 'red'}">${svc.running ? '✅' : '⛔'}</div>

      <div class="stat-info">

        <div class="stat-value">${statusBadge}</div>

        <div class="stat-label">服务状态</div>

      </div>

    </div>

    <div class="stat-card">

      <div class="stat-icon blue">🔗</div>

      <div class="stat-info">

        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom: 2px;">

          <div class="stat-value" style="font-size: 15px; font-weight: 700; color: var(--accent-blue); cursor: pointer;" onclick="navigator.clipboard.writeText('${status.local_ip || ''}'); showToast('IP已复制！', 'success');" title="点击复制 IP">${status.local_ip || '—'}</div>

          <button class="btn btn-sm btn-outline" style="padding:2px 6px; font-size:11px;" onclick="showQRModal('${status.local_ip || ''}')" title="显示连接二维码">📷 二维码</button>

        </div>

        <div class="stat-label">连接 IP (点击复制)</div>

      </div>

    </div>

    <div class="stat-card">

      <div class="stat-icon blue">🔢</div>

      <div class="stat-info">

        <div class="stat-value">${svc.pid || '—'}</div>

        <div class="stat-label">进程 PID</div>

      </div>

    </div>

    <div class="stat-card">

      <div class="stat-icon yellow">🌐</div>

      <div class="stat-info">

        <div class="stat-value">${svc.port || '—'}</div>

        <div class="stat-label">监听端口</div>

      </div>

    </div>

    <div class="stat-card">

      <div class="stat-icon purple">⏱️</div>

      <div class="stat-info">

        <div class="stat-value">${svc.uptime || '—'}</div>

        <div class="stat-label">运行时间</div>

      </div>

    </div>

  `;



  // 系统信息

  const sysEl = document.getElementById('system-info');

  if (sysEl) {

    sysEl.innerHTML = `

      <div class="stat-card">

        <div class="stat-icon blue">💻</div>

        <div class="stat-info"><div class="stat-value">${sysInfo.cpu_percent || 0}%</div><div class="stat-label">CPU 使用率</div></div>

      </div>

      <div class="stat-card">

        <div class="stat-icon purple">🧠</div>

        <div class="stat-info"><div class="stat-value">${sysInfo.memory_used_mb || 0} / ${sysInfo.memory_total_mb || 0} MB</div><div class="stat-label">内存 (${sysInfo.memory_percent || 0}%)</div></div>

      </div>

      <div class="stat-card">

        <div class="stat-icon green">💾</div>

        <div class="stat-info"><div class="stat-value">${sysInfo.disk_used_gb || 0} / ${sysInfo.disk_total_gb || 0} GB</div><div class="stat-label">磁盘 (${sysInfo.disk_percent || 0}%)</div></div>

      </div>

      <div class="stat-card">

        <div class="stat-icon yellow">📊</div>

        <div class="stat-info"><div class="stat-value">${svc.memory_mb || 0} MB</div><div class="stat-label">服务内存</div></div>

      </div>

    `;

  }



  // 进程信息

  const procEl = document.getElementById('process-info');

  if (procEl && svc.running) {

    procEl.innerHTML = `

      <table>

        <tr><td style="width:120px;color:var(--text-secondary)">PID</td><td>${svc.pid}</td></tr>

        <tr><td style="color:var(--text-secondary)">端口</td><td>${svc.port}</td></tr>

        <tr><td style="color:var(--text-secondary)">启动时间</td><td>${svc.create_time || '—'}</td></tr>

        <tr><td style="color:var(--text-secondary)">运行时长</td><td>${svc.uptime || '—'}</td></tr>

        <tr><td style="color:var(--text-secondary)">CPU</td><td>${svc.cpu_percent || 0}%</td></tr>

        <tr><td style="color:var(--text-secondary)">内存</td><td>${svc.memory_mb || 0} MB</td></tr>

      </table>

    `;

  } else if (procEl) {

    procEl.innerHTML = '<p style="color:var(--text-muted)">服务未运行</p>';

  }

}
