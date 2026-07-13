async function loadSessions() {

  const result = await apiCall('/api/sessions');

  const tbody = document.getElementById('sessions-table');

  if (result.sessions && result.sessions.length > 0) {

    tbody.innerHTML = result.sessions.map(s => `

      <tr>

        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(s.id)}</td>

        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-secondary)">${escapeHtml(s.last_message || '')}</td>

        <td>${s.last_time || '—'}</td>

        <td>${s.message_count || 0}</td>

      </tr>

    `).join('');

  } else {

    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">暂无会话数据</td></tr>';

  }

}

async function loadChatHistory() {

  const result = await apiCall('/api/chat/history');

  const container = document.getElementById('chat-history');

  if (result.history && result.history.length > 0) {

    container.innerHTML = result.history.slice(-50).map(m => {

      const role = m.role || m.from || 'unknown';

      const content = m.content || m.message || m.text || '';

      const time = m.timestamp || m.time || '';

      const roleColor = role === 'user' ? 'var(--accent-blue)' : role === 'assistant' ? 'var(--accent-green)' : 'var(--accent-yellow)';

      return `<div style="margin-bottom:10px;padding:8px;border-radius:6px;background:rgba(255,255,255,0.02)">

        <div style="font-size:11px;font-weight:600;color:${roleColor};margin-bottom:4px">${escapeHtml(role)}${time ? ' · ' + escapeHtml(time) : ''}</div>

        <div style="color:var(--text-secondary);white-space:pre-wrap">${escapeHtml(String(content).substring(0, 500))}</div>

      </div>`;

    }).join('');

  } else {

    container.innerHTML = '<p style="color:var(--text-muted)">暂无聊天记录</p>';

  }

}
