let taskManagerTypeFilter = '';
let taskManagerSurfaceFilter = '';

function switchTasksTab(tab) {

  currentTasksTab = tab;

  document.getElementById('btn-tab-tasks-pending').classList.toggle('active-tab', tab === 'pending');

  document.getElementById('btn-tab-tasks-testing').classList.toggle('active-tab', tab === 'testing');

  document.getElementById('btn-tab-tasks-completed').classList.toggle('active-tab', tab === 'completed');

  

  // Show or hide elements depending on tab

  const mergeBtn = document.getElementById('btn-merge-tasks');

  if (mergeBtn) {

    mergeBtn.style.display = tab === 'pending' ? 'inline-block' : 'none';

  }

  const dispatchToolbar = document.getElementById('tasks-dispatch-toolbar');

  if (dispatchToolbar) {

    dispatchToolbar.style.display = tab === 'pending' ? 'flex' : 'none';

  }

  const completedSearch = document.getElementById('task-completed-search');
  if (completedSearch) {
    completedSearch.style.display = tab === 'completed' ? 'block' : 'none';
    if (tab !== 'completed') completedSearch.value = '';
  }

  

  renderTasksData(allTasksData);

}

function switchTasksView(view) {

  currentTasksView = view;

  document.getElementById('btn-view-list').classList.toggle('active-tab', view === 'list');

  document.getElementById('btn-view-component').classList.toggle('active-tab', view === 'component');

  

  // 切换视图显示

  const tableWrapper = document.querySelector('#page-tasks .table-wrapper');

  const componentView = document.getElementById('tasks-component-view');

  

  if (view === 'list') {

    tableWrapper.style.display = 'block';

    componentView.style.display = 'none';

  } else {

    tableWrapper.style.display = 'none';

    componentView.style.display = 'block';

    renderComponentView(allTasksData);

  }

}

function renderComponentView(tasks) {

  const container = document.getElementById('component-groups-container');

  

  // 过滤当前 tab 的任务，且仅保留组件类任务（type === 'component' 或含组件信息的任务）

  const filteredTasks = tasks.filter(t => {

    const isCompleted = t.status === 'done' || t.status === 'failed';
    const isPendingTest = t.status === 'pending_test';
    if (currentTasksTab === 'pending' && (isCompleted || isPendingTest)) return false;
    if (currentTasksTab === 'testing' && !isPendingTest) return false;
    if (currentTasksTab === 'completed' && !isCompleted) return false;
    const classification = t.classification || {};
    if (taskManagerSurfaceFilter && classification.surface !== taskManagerSurfaceFilter) return false;
    if (taskManagerTypeFilter === 'unclassified' && classification.state !== 'unclassified') return false;
    if (taskManagerTypeFilter === 'other') {
      if (['feature', 'optimization', 'bug_fix'].includes(classification.task_type)) return false;
    } else if (taskManagerTypeFilter && taskManagerTypeFilter !== 'unclassified' && classification.task_type !== taskManagerTypeFilter) {
      return false;
    }

    

    // 类型校验：仅渲染组件类任务

    const taskType = t.task_type || t.type || '';

    if (taskType === 'component') return true;

    

    // 含组件信息的任务也视为组件类

    const meta = t.metadata || {};

    if (meta.bug_func || meta.bug_file) return true;

    const msg = t.message || '';

    if (msg.includes('组件/类/函数:') || msg.includes('目标文件:') || msg.includes('目标文件与组件范围:')) return true;

    if (msg.includes('【自动检测到 Bug】') || msg.includes('【自动检测到问题】')) return true;

    

    return false;

  });

  

  // 按组件分组

  const componentMap = {};

  filteredTasks.forEach(t => {

    const msg = t.message || '';

    const meta = t.metadata || {};

    let component = '未分类';

    let file = '';

    

    // 格式1: Bug 检测格式（从 metadata 提取）

    if (meta.bug_func || meta.bug_file) {

      component = meta.bug_func || 'Bug修复';

      file = meta.bug_file || '';

    }

    // 格式2: Bug 检测格式（从 message 提取）

    else if (msg.includes('【自动检测到 Bug】') || msg.includes('【自动检测到问题】')) {

      const mFunc = msg.match(/函数:\s*([^\n\r]+)/);

      const mFile = msg.match(/文件:\s*([^\n\r]+)/);

      if (mFunc) component = mFunc[1].trim();

      if (mFile) file = mFile[1].trim();

    }

    // 格式3: 标准格式（组件/类/函数）

    else {

      const mComp = msg.match(/组件\/类\/函数:\s*([^\n\r]+)/);

      const mFile = msg.match(/目标文件:\s*([^\n\r]+)/);

      

      if (mComp) {

        component = mComp[1].trim();

      }

      if (mFile) {

        file = mFile[1].trim();

      }

      

      // 多组件格式

      if (!mComp) {

        const multiMatch = msg.match(/目标文件与组件范围:\s*\n([\s\S]*?)(?:\n\n|\n修改类型:)/);

        if (multiMatch) {

          const itemRegex = /\d+\.\s*\[组件\]\s*(.+?)\s*->\s*文件:\s*(.+?)(?:\s*\(行.*?\))?$/gm;

          let itemMatch;

          const items = [];

          while ((itemMatch = itemRegex.exec(multiMatch[1])) !== null) {

            items.push({ name: itemMatch[1].trim(), file: itemMatch[2].trim() });

          }

          if (items.length > 0) {

            component = items.map(i => i.name).join(', ');

            file = items.map(i => i.file).join(', ');

          }

        }

      }

    }

    

    // 格式4: 聊天/纯文本任务（无结构化信息）

    if (component === '未分类' && !file) {

      // 尝试从内容中提取关键词作为分类

      const content = msg.replace(/【.*?】/g, '').trim();

      if (content.length > 0) {

        // 使用前20个字符作为分类标识

        const shortContent = content.substring(0, 20).replace(/\n/g, ' ');

        component = `💬 ${shortContent}${content.length > 20 ? '...' : ''}`;

      }

    }

    

    if (!componentMap[component]) {

      componentMap[component] = { file, tasks: [] };

    }

    componentMap[component].tasks.push(t);

  });

  

  // 渲染分组

  const entries = Object.entries(componentMap).sort((a, b) => b[1].tasks.length - a[1].tasks.length);

  

  if (entries.length === 0) {

    container.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted);">暂无任务</div>';

    return;

  }

  

  // 存储分组数据供 onclick 使用

  window._componentGroups = entries;

  

  container.innerHTML = entries.map(([comp, data], groupIdx) => {

    const taskCount = data.tasks.length;

    const taskListHtml = data.tasks.map(t => {

      let displayMessage = t.message || '—';

      const reqMatch = displayMessage.match(/(?:【内容】|【修改需求说明】)\n?([\s\S]+?)(?:\n\n【代码修改与优化任务】|\n\n以下是待合并|\Z)/);

      if (reqMatch) {

        displayMessage = reqMatch[1].trim();

      }

      

      const statusLabel = (t.status === 'pending') ? 'draft' : (t.status || 'draft');

      let statusColor = 'var(--text-muted)';

      let statusBg = 'var(--border-color)';

      if (statusLabel === 'draft') { statusColor = 'var(--accent-yellow)'; statusBg = 'rgba(210,153,34,0.15)'; }

      else if (statusLabel === 'queued' || statusLabel === 'dispatched') { statusColor = 'var(--accent-blue)'; statusBg = 'rgba(88,166,255,0.15)'; }

      else if (statusLabel === 'running') { statusColor = 'var(--accent-purple)'; statusBg = 'rgba(188,140,255,0.15)'; }

      else if (statusLabel === 'done') { statusColor = 'var(--accent-green)'; statusBg = 'rgba(63,185,80,0.15)'; }

      else if (statusLabel === 'failed') { statusColor = 'var(--accent-red)'; statusBg = 'rgba(248,81,73,0.15)'; }

      

      return `

        <div style="padding:8px 12px; background:var(--bg-primary); border:1px solid var(--border-color); border-radius:6px; font-size:12px; cursor:pointer;" onclick="openFollowUpPrompt('${escapeHtml(t.task_id)}')">

          <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">

            <span style="font-family:monospace; font-size:10px; color:var(--text-muted);">${escapeHtml(t.task_id || '—')}</span>

            <span style="display:flex; align-items:center; gap:4px;">

              ${t.parent_task_id ? `<span title="后续任务，原始任务: ${escapeHtml(t.parent_task_id)}" style="font-size:9px; padding:1px 5px; background:rgba(88,166,255,0.12); color:var(--accent-blue); border-radius:3px;">↩ 后续</span>` : ''}

              <span style="font-size:10px; padding:2px 6px; background:${statusBg}; color:${statusColor}; border-radius:4px;">${escapeHtml(statusLabel)}</span>

            </span>

          </div>

          <div style="color:var(--text-secondary); max-height:40px; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(displayMessage.substring(0, 100))}${displayMessage.length > 100 ? '...' : ''}</div>

        </div>

      `;

    }).join('');

    

    return `

      <div style="border:1px solid var(--border-color); border-radius:8px; overflow:hidden;">

        <div style="padding:10px 14px; background:var(--bg-tertiary); display:flex; align-items:center; justify-content:space-between; cursor:pointer;" onclick="onComponentGroupClick(${groupIdx})">

          <div style="display:flex; align-items:center; gap:8px;">

            <span style="font-size:16px;">🧩</span>

            <span style="font-weight:600; font-size:13px; color:var(--text-primary);">${escapeHtml(comp)}</span>

            <span style="font-size:11px; color:var(--text-muted);">(${taskCount} 个任务)</span>

          </div>

          <div style="display:flex; align-items:center; gap:6px;">

            ${data.file ? `<span style="font-size:10px; font-family:monospace; color:var(--text-muted); max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(data.file)}">${escapeHtml(data.file)}</span>` : ''}

            <span style="font-size:11px; color:var(--accent-blue);">✍️ 提示词</span>

          </div>

        </div>

        <div style="padding:8px 14px; display:flex; flex-direction:column; gap:6px;">

          ${taskListHtml}

        </div>

      </div>

    `;

  }).join('');

}

function renderTasksData(tasks) {

  const tbody = document.getElementById('tasks-table');

  tbody.innerHTML = '';

  

  // Filter by tab

  const searchValue = currentTasksTab === 'completed'
    ? (document.getElementById('task-completed-search')?.value || '').trim().toLowerCase()
    : '';
  const filteredTasks = tasks.filter(t => {

    const isCompleted = t.status === 'done' || t.status === 'failed';
    const isPendingTest = t.status === 'pending_test';
    if (currentTasksTab === 'pending' && (isCompleted || isPendingTest)) return false;
    if (currentTasksTab === 'testing' && !isPendingTest) return false;
    if (currentTasksTab === 'completed' && !isCompleted) return false;
    const classification = t.classification || {};
    if (taskManagerSurfaceFilter && classification.surface !== taskManagerSurfaceFilter) return false;
    if (taskManagerTypeFilter === 'unclassified' && classification.state !== 'unclassified') return false;
    if (taskManagerTypeFilter === 'other') {
      if (['feature', 'optimization', 'bug_fix'].includes(classification.task_type)) return false;
    } else if (taskManagerTypeFilter && taskManagerTypeFilter !== 'unclassified' && classification.task_type !== taskManagerTypeFilter) {
      return false;
    }
    if (searchValue) {
      const searchable = [
        t.title, taskOriginalRequirement(t),
      ].join(' ').toLowerCase();
      if (!searchable.includes(searchValue)) return false;
    }
    return true;

  });

  

  // Update select all checkbox status

  const selectAllCheckbox = document.getElementById('select-all-tasks');

  if (selectAllCheckbox) {

    selectAllCheckbox.checked = false;

  }

  updateBatchToolbar();

  

  if (!filteredTasks || filteredTasks.length === 0) {

    const emptyLabel = currentTasksTab === 'pending'
      ? '待处理'
      : (currentTasksTab === 'testing' ? '待测试' : '已完成');
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text-muted)">暂无${emptyLabel}任务</td></tr>`;

    return;

  }

  

  filteredTasks.forEach(t => {

    const tr = document.createElement('tr');

    

    let timeStr = t.time || '—';

    let dateStr = '—';

    if (timeStr && timeStr.includes('T')) {

      timeStr = timeStr.replace('T', ' ').substring(0, 19);

      if (timeStr.length >= 16) {

        dateStr = timeStr.substring(5, 16); // e.g. "06-20 22:32"

      }

    }

    

    const type = t.task_type || 'chat';

    let typeClass = 'badge-success';

    let typeLabel = '💬 Chat';

    if (type === 'code') {

      typeClass = 'badge-success';

      typeLabel = '💻 Code';

    } else if (type === 'bug_fix') {

      typeClass = 'badge-danger';

      typeLabel = '🐛 BugFix';

    }

    

    const statusLabel = (t.status === 'pending') ? 'draft' : (t.status || 'draft');

    let statusHtml = '';

    // 计算队列位置

    let queueInfo = '';

    if (t.target_ide && allQueueStatus[t.target_ide]) {

      const qs = allQueueStatus[t.target_ide];

      if (qs.current === t.task_id) {

        queueInfo = '<div style="font-size:10px;color:var(--accent-yellow);margin-top:2px;">当前执行中</div>';

      } else if (qs.pending && qs.pending.includes(t.task_id)) {

        const pos = qs.pending.indexOf(t.task_id) + 2; // +2 因为 current 是第1个

        queueInfo = `<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">队列第 ${pos} 位</div>`;

      }

    }

    if (statusLabel === 'draft') {

      statusHtml = `<span class="badge" style="background:rgba(210,153,34,0.15);color:var(--accent-yellow);">待派发</span>`;

    } else if (statusLabel === 'queued') {

      statusHtml = `<span class="badge" style="background:rgba(88,166,255,0.15);color:var(--accent-blue);">排队中</span>${queueInfo}`;

    } else if (statusLabel === 'dispatched') {

      statusHtml = `<span class="badge" style="background:rgba(88,166,255,0.15);color:var(--accent-blue);">执行中</span>${queueInfo}`;

    } else if (statusLabel === 'running') {

      statusHtml = `<span class="badge" style="background:rgba(188,140,255,0.15);color:var(--accent-purple);">运行中</span>`;

    } else if (statusLabel === 'pending_test') {

      statusHtml = `<span class="badge" style="background:rgba(188,140,255,0.15);color:var(--accent-purple);">待测试</span>`;

    } else if (statusLabel === 'done') {

      statusHtml = `<span class="badge" style="background:rgba(63,185,80,0.15);color:var(--accent-green);">已完成</span>`;

    } else if (statusLabel === 'failed') {

      statusHtml = `<span class="badge" style="background:rgba(248,81,73,0.15);color:var(--accent-red);">已失败</span>`;

    } else if (statusLabel === 'timeout') {

      statusHtml = `<span class="badge" style="background:rgba(248,81,73,0.15);color:var(--accent-red);">已超时</span>`;

    } else {

      statusHtml = `<span class="badge" style="background:var(--border-color);color:var(--text-muted);">${escapeHtml(statusLabel)}</span>`;

    }



    const status = statusLabel;

    const isDone = status === 'done';

    const actionBtnHtml = isDone

      ? `<span style="color:var(--text-muted);font-size:12px;">—</span>`

      : `<button class="btn btn-sm btn-success" onclick="markTaskComplete('${escapeHtml(t.task_id)}')">✅ 完成</button>`;



    const copyBtnHtml = `<button class="btn btn-sm btn-outline" onclick="copyTaskMessage('${escapeHtml(t.task_id)}', this)" title="复制任务内容到剪贴板">📋 复制</button>`;

    const editBtnHtml = (status === 'draft' || status === 'queued')

      ? `<button class="btn btn-sm btn-outline" onclick="editTask('${escapeHtml(t.task_id)}')" title="编辑任务内容">✏️ 编辑</button>`

      : '';

    const feedbackBtnHtml = (status === 'done' || status === 'dispatched' || status === 'failed' || status === 'running' || status === 'timeout')

      ? `<button class="btn btn-sm btn-outline" onclick="feedbackTask('${escapeHtml(t.task_id)}')" title="补充反馈并重新派发" style="background:rgba(240,160,64,0.1);color:var(--accent-yellow);border:1px solid rgba(240,160,64,0.3);">💬 补充</button>`

      : '';

    const testBtnHtml = ((status === 'done' || status === 'running' || status === 'dispatched' || status === 'pending_test') && t.target_ide)

      ? `<button class="btn btn-sm btn-outline" onclick="dispatchTestTask('${escapeHtml(t.task_id)}', '${escapeHtml(t.target_ide)}')" title="派发测试任务到另一个 IDE" style="background:rgba(70,201,122,0.1);color:var(--ok);border:1px solid rgba(70,201,122,0.3);">🧪 测试</button>`

      : '';

    const deleteBtnHtml = `<button class="btn btn-sm btn-outline" onclick="deleteTask('${escapeHtml(t.task_id)}', this)" title="删除任务" style="color:var(--accent-red);border-color:rgba(248,81,73,0.3);">🗑️ 删除</button>`;
    const classifyBtnHtml = `<button class="btn btn-sm btn-outline" onclick="openTaskClassification(['${escapeHtml(t.task_id)}'])" title="整理或纠正任务分类">🏷️ 分类</button>`;



    // Display dispatched IDE

    const ideDisplay = t.target_ide && t.target_ide !== '—' 

      ? t.target_ide.toUpperCase() 

      : '—';



    // Extract "内容"

    const displayMessage = taskOriginalRequirement(t);



    // Parse component and file

    const msg = t.message || '';

    let file = '—';

    let component = '';

    

    // Case 1: Single component format

    // 目标文件: xxx

    // 组件/类/函数: xxx

    const mFile = msg.match(/目标文件:\s*([^\n\r]+)/);

    const mComp = msg.match(/组件\/类\/函数:\s*([^\n\r]+)/);

    if (mFile) file = mFile[1].trim();

    if (mComp) component = mComp[1].trim();

    

    // Case 2: Multiple components format

    // 目标文件与组件范围:

    //   1. [组件] name -> 文件: path (行 123-456)

    //   2. [组件] name2 -> 文件: path2

    if (!component) {

      const multiMatch = msg.match(/目标文件与组件范围:\s*\n([\s\S]*?)(?:\n\n|\n修改类型:)/);

      if (multiMatch) {

        const items = [];

        const itemRegex = /\d+\.\s*\[组件\]\s*(.+?)\s*->\s*文件:\s*(.+?)(?:\s*\(行.*?\))?$/gm;

        let itemMatch;

        while ((itemMatch = itemRegex.exec(multiMatch[1])) !== null) {

          items.push({ name: itemMatch[1].trim(), file: itemMatch[2].trim() });

        }

        if (items.length > 0) {

          component = items.map(i => i.name).join(', ');

          file = items.map(i => i.file).join(', ');

        }

      }

    }

    

    // 提取平台和组件信息（有组件才显示，无组件显示来源）

    let platform = '电脑端';

    if (file && file !== '—' && (file.startsWith('AideLink-app/') || file.startsWith('app/') || file.includes('-app/'))) {

      platform = '手机端';

    }

    const hasComponent = component && component !== '—' && file && file !== '—';

    const classification = t.classification || {};
    const classificationState = classification.state || 'unclassified';
    const classificationStateLabel = classificationState === 'confirmed'
      ? '已确认'
      : (classificationState === 'suggested' ? 'AI 建议' : '未分类');
    const classificationHtml = `
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:5px;">
        <span class="badge" style="font-size:10px;background:${classificationState === 'confirmed' ? 'rgba(63,185,80,.15)' : 'rgba(240,160,64,.15)'};color:${classificationState === 'confirmed' ? 'var(--accent-green)' : 'var(--accent-yellow)'};">${classificationStateLabel}</span>
        ${classification.surface ? `<span class="badge" style="font-size:10px;">${escapeHtml(classification.surface.toUpperCase())}</span>` : ''}
        ${(classification.functional_areas || []).slice(0, 1).map(area => `<span class="badge badge-success" style="font-size:10px;">${escapeHtml(area)}</span>`).join('')}
      </div>`;
    const compDisplayHtml = (hasComponent

      ? `<div style="font-weight:600;font-size:12px;">[${platform}] ${escapeHtml(component)}</div><div style="font-size:10px;color:var(--text-muted);margin-top:2px;font-family:monospace;" title="${escapeHtml(file)}">${escapeHtml(file)}</div>`

      : `<div style="font-size:11px;color:var(--text-muted);">${escapeHtml(t.target_ide && t.target_ide !== '—' ? '📱 来自 ' + t.target_ide.toUpperCase() : '📝 无关联组件')}</div>`) + classificationHtml;



    const taskVersion = t.version || '—';

    const taskIdHtml = `

      <div style="font-family:monospace;font-size:11px;font-weight:600;color:var(--text-muted);">${escapeHtml(t.task_id || '—')}</div>

      <div style="font-size:10px;color:var(--text-muted);margin-top:1px;">${escapeHtml(dateStr)}</div>

      <div style="margin-top:2px;">

        <span class="badge ${typeClass}" style="font-size:10px;">${escapeHtml(typeLabel)}</span>

      </div>

      ${taskVersion !== '—' ? `<div style="margin-top:1px;"><span class="badge" style="font-size:10px;background:rgba(88,166,255,0.15);color:var(--accent-blue);">v${escapeHtml(taskVersion)}</span></div>` : ''}

    `;



    const statusAndPreviewHtml = `

      <div style="margin-bottom:4px;">${statusHtml}</div>

      ${t.test_result ? `<div style="font-size:10px;margin-bottom:3px;color:${t.test_result === 'failed' ? 'var(--accent-red)' : (t.test_result === 'queued' ? 'var(--accent-yellow)' : 'var(--accent-green)')};">🧪 ${
        t.test_result === 'passed' ? '测试通过' :
        t.test_result === 'failed' ? '测试未通过' :
        t.test_result === 'queued' ? '测试排队中' : '已派发测试'
      }</div>` : ''}

      <div style="font-size:11px;color:var(--text-secondary);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(t.response_preview || '')}">${escapeHtml(t.response_preview || '—')}</div>

      ${t.target_ide && t.target_ide !== '—' ? `<div style="margin-top:2px;"><span onclick="launchIde('${escapeHtml(t.target_ide)}')" title="点击启动" style="font-size:11px;color:var(--accent-blue);cursor:pointer;">🚀 ${escapeHtml(t.target_ide.toUpperCase())}</span></div>` : ''}

    `;



    // 提取反馈历史用于显示

    const feedbacks = t.feedbacks || [];

    const fbCount = feedbacks.length;

    const fbBadge = fbCount > 0

      ? `<span style="display:inline-block;background:rgba(240,160,64,0.15);color:var(--accent-yellow);font-size:10px;padding:1px 5px;border-radius:3px;margin-left:4px;font-weight:600;">💬×${fbCount}</span>`

      : '';

    // 显示所有反馈历史

    const allFeedbacksHtml = fbCount > 0

      ? feedbacks.map((fb, idx) => {

          const fbTime = fb.time ? new Date(fb.time).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '';

          return `<div style="margin-top:4px;padding:4px 6px;background:rgba(240,160,64,0.08);border-left:2px solid var(--accent-yellow);border-radius:0 4px 4px 0;font-size:11px;color:var(--accent-yellow);">

            <span style="font-size:10px;color:var(--text-muted);">💬 #${idx+1}${fbTime ? ' ' + fbTime : ''}</span>

            <div style="margin-top:2px;">${escapeHtml(fb.text).substring(0, 200)}${fb.text.length > 200 ? '...' : ''}</div>

          </div>`;

        }).join('')

      : '';



    tr.innerHTML = `

      <td><input type="checkbox" class="task-row-checkbox" data-id="${escapeHtml(t.task_id)}" onchange="updateBatchToolbar()"></td>

      <td>${taskIdHtml}</td>

      <td>${compDisplayHtml}</td>

      <td title="${escapeHtml(displayMessage)}"><div style="display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.45;">${escapeHtml(displayMessage)}</div>${fbBadge}</td>

      <td>${statusAndPreviewHtml}</td>

      <td style="text-align:center;">${copyBtnHtml}${editBtnHtml}${classifyBtnHtml}${testBtnHtml}${feedbackBtnHtml}${deleteBtnHtml}${actionBtnHtml}</td>

    `;

    tbody.appendChild(tr);

  });

}

function taskOriginalRequirement(task) {
  const metadata = task.metadata || {};
  let text = String(
    metadata.original_message || task.original_text || task.message || task.text || task.title || '—'
  ).trim();
  const originalSection = text.match(/###?\s*原始需求\s*\n+([\s\S]+?)(?=\n###?\s|\n---|$)/i);
  if (originalSection) text = originalSection[1].trim();
  const contentSection = text.match(/(?:【内容】|【修改需求说明】)\s*\n?([\s\S]+?)(?=\n\n【代码修改与优化任务】|\n\n以下是待合并|$)/);
  if (contentSection) text = contentSection[1].trim();
  const feedbackMarker = text.indexOf('\n\n---\n测试反馈：');
  if (feedbackMarker >= 0) text = text.slice(0, feedbackMarker).trim();
  return text || '—';
}

function setTaskTypeFilter(value) {
  taskManagerTypeFilter = value;
  document.querySelectorAll('[data-task-type]').forEach(button => {
    button.classList.toggle('active-tab', button.dataset.taskType === value);
  });
  renderTasksData(allTasksData);
  if (currentTasksView === 'component') renderComponentView(allTasksData);
}

function setTaskSurfaceFilter(value) {
  taskManagerSurfaceFilter = value;
  document.querySelectorAll('[data-task-surface]').forEach(button => {
    button.classList.toggle('active-tab', button.dataset.taskSurface === value);
  });
  renderTasksData(allTasksData);
  if (currentTasksView === 'component') renderComponentView(allTasksData);
}

async function loadTasksList() {

  const tbody = document.getElementById('tasks-table');

  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text-muted)">正在读取任务...</td></tr>';

  

  const [res, queueRes] = await Promise.all([

    apiCall('/api/tasks'),

    apiCall('/api/tasks/queue_status')

  ]);

  if (res && res.success && res.tasks) {

    allTasksData = res.tasks;

    allQueueStatus = (queueRes && queueRes.queues) || {};

    renderTasksData(allTasksData);

    tasksLoaded = true;

  } else {

    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--accent-red)">加载失败: ' + (res ? res.message : '网络错误') + '</td></tr>';

  }

  // 同时刷新 IDE 状态

  loadIdeStatus();

}

function toggleTasksCollapse(event) {

  if (event && event.target.closest('.btn-group, [onclick*="openGlobalPromptPanel"], [onclick*="loadTasksList"]')) return;

  tasksCollapsed = !tasksCollapsed;

  const body = document.getElementById('tasks-collapse-body');

  const btn = document.getElementById('btn-toggle-tasks');

  if (tasksCollapsed) {

    body.style.display = 'none';

    btn.textContent = '▼';

    btn.title = '展开任务管理';

  } else {

    body.style.display = '';

    btn.textContent = '▲';

    btn.title = '折叠任务管理';

  }

}

function toggleSelectAllTasks(checked) {

  document.querySelectorAll('.task-row-checkbox').forEach(cb => {

    cb.checked = checked;

  });

  updateBatchToolbar();

}

function updateBatchToolbar() {

  const checked = Array.from(document.querySelectorAll('.task-row-checkbox:checked'));

  const count = checked.length;

  document.getElementById('selected-task-count').textContent = `已选 ${count} 项`;

  document.getElementById('btn-batch-complete').style.display = count > 0 ? 'inline-block' : 'none';
  document.getElementById('btn-batch-classify').style.display = count > 0 ? 'inline-block' : 'none';
  document.getElementById('btn-batch-smart-classify').style.display = count > 0 ? 'inline-block' : 'none';

  document.getElementById('btn-batch-delete').style.display = count > 0 ? 'inline-block' : 'none';

}

const taskCompletedSearch = document.getElementById('task-completed-search');
if (taskCompletedSearch) {
  taskCompletedSearch.addEventListener('input', () => {
    clearTimeout(window._taskManagerSearchTimer);
    window._taskManagerSearchTimer = setTimeout(() => renderTasksData(allTasksData), 180);
  });
}

function selectedTaskIds() {
  return Array.from(document.querySelectorAll('.task-row-checkbox:checked')).map(cb => cb.dataset.id);
}

function openTaskClassification(explicitIds) {
  const taskIds = explicitIds || selectedTaskIds();
  if (!taskIds.length) {
    showToast('请先选择任务', 'error');
    return;
  }
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.68);z-index:1200;display:flex;align-items:center;justify-content:center;';
  overlay.dataset.taskIds = JSON.stringify(taskIds);
  overlay.innerHTML = `
    <div style="background:var(--panel);border:1px solid var(--border-color);border-radius:12px;padding:20px;width:92%;max-width:680px;max-height:90vh;overflow:auto;">
      <h3 style="margin-bottom:6px;">🏷️ 整理任务分类</h3>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">已选择 ${taskIds.length} 个任务。这里由用户直接确认分类。</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <label style="font-size:12px;">项目端<select id="classification-surface" class="table-input" style="width:100%;margin-top:4px;"><option value="">未分类</option><option value="general">通用</option><option value="web">Web</option><option value="android">Android</option><option value="windows">Windows</option></select></label>
        <label style="font-size:12px;">任务类型<select id="classification-type" class="table-input" style="width:100%;margin-top:4px;"><option value="">未分类</option><option value="feature">新功能</option><option value="optimization">功能优化</option><option value="bug_fix">Bug 修复</option><option value="other">其他</option></select></label>
      </div>
      <label style="display:block;font-size:12px;margin-top:12px;">界面位置<input id="classification-location" class="table-input" style="width:100%;margin-top:4px;" placeholder="可选，例如：详情页顶部"></label>
      <label style="display:block;font-size:12px;margin-top:12px;">功能区域（可填多个）<input id="classification-areas-input" class="table-input" style="width:100%;margin-top:4px;" placeholder="用逗号分隔，例如：订单、支付"></label>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;">
        <button class="btn btn-sm btn-outline" onclick="this.closest('div[style*=fixed]').remove()">取消</button>
        <button class="btn btn-sm btn-primary" onclick="saveTaskClassification(this)">确认分类</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', event => { if (event.target === overlay) overlay.remove(); });
}

async function smartClassifySelectedTasks() {
  const taskIds = selectedTaskIds();
  if (!taskIds.length) {
    showToast('请先选择任务', 'error');
    return;
  }
  if (!confirm(`智能整理所选 ${taskIds.length} 个任务？结果会标记为“AI 建议待确认”。`)) return;
  showToast(`正在智能整理 0/${taskIds.length}…`, 'info');
  let successCount = 0;
  let failedCount = 0;
  for (let index = 0; index < taskIds.length; index++) {
    const taskId = taskIds[index];
    const suggested = await apiCall('/api/tasks/classification/suggest', 'POST', {task_id: taskId});
    if (!suggested || !suggested.success) {
      failedCount++;
      continue;
    }
    const classification = {
      ...(suggested.suggestion || {}),
      state: 'suggested',
      source: suggested.suggestion?.source || 'ai',
    };
    const saved = await apiCall('/api/tasks/classification', 'POST', {
      task_ids: [taskId],
      classification,
    });
    if (saved && saved.success) successCount++; else failedCount++;
    showToast(`正在智能整理 ${index + 1}/${taskIds.length}…`, 'info');
  }
  showToast(
    `智能整理完成：${successCount} 个待确认${failedCount ? `，${failedCount} 个失败` : ''}`,
    successCount ? 'success' : 'error',
  );
  loadTasksList();
}

async function saveTaskClassification(button) {
  const overlay = button.closest('div[style*="fixed"]');
  const taskIds = JSON.parse(overlay.dataset.taskIds || '[]');
  const classification = {
    surface: overlay.querySelector('#classification-surface').value,
    task_type: overlay.querySelector('#classification-type').value,
    ui_location: overlay.querySelector('#classification-location').value.trim(),
    functional_areas: splitTaskClassificationAreas(
      overlay.querySelector('#classification-areas-input').value
    ),
    state: 'confirmed',
    source: 'user',
  };
  const result = await apiCall('/api/tasks/classification', 'POST', {task_ids: taskIds, classification});
  if (result && result.success) {
    overlay.remove();
    showToast(`已确认 ${result.updated_task_ids.length} 个任务的分类`, 'success');
    loadTasksList();
  } else {
    showToast(result ? result.message : '分类保存失败', 'error');
  }
}

function splitTaskClassificationAreas(value) {
  return String(value || '')
    .split(/[,，、]/)
    .map(item => item.trim())
    .filter((item, index, all) => item && all.indexOf(item) === index)
    .slice(0, 8);
}

async function batchCompleteTasks() {

  const checked = Array.from(document.querySelectorAll('.task-row-checkbox:checked'));

  if (checked.length === 0) { showToast('请先选择任务', 'error'); return; }

  if (!confirm(`确定要批量完成选中的 ${checked.length} 个任务吗？`)) return;

  showToast(`正在完成 ${checked.length} 个任务...`, 'info');

  let ok = 0, fail = 0;

  for (const cb of checked) {

    const taskId = cb.dataset.id;

    const res = await apiCall('/api/tasks/complete', 'POST', { task_id: taskId, manual: true });

    if (res && res.success) ok++; else fail++;

  }

  showToast(`批量完成 ${ok} 个，失败 ${fail} 个`, ok > 0 ? 'success' : 'error');

  loadTasksList();

}

async function batchDeleteTasks() {

  const checked = Array.from(document.querySelectorAll('.task-row-checkbox:checked'));

  if (checked.length === 0) { showToast('请先选择任务', 'error'); return; }

  if (!confirm(`确定要批量删除选中的 ${checked.length} 个任务吗？此操作不可恢复。`)) return;

  showToast(`正在删除 ${checked.length} 个任务...`, 'info');

  let ok = 0, fail = 0;

  for (const cb of checked) {

    const taskId = cb.dataset.id;

    const res = await apiCall(`/api/tasks/${taskId}`, 'DELETE');

    if (res && res.success) ok++; else fail++;

  }

  showToast(`删除完成 ${ok} 个，失败 ${fail} 个`, ok > 0 ? 'success' : 'error');

  loadTasksList();

}

function editTask(taskId) {

  const task = allTasksData.find(t => t.task_id === taskId);

  if (!task) { showToast('找不到任务', 'error'); return; }



  const overlay = document.createElement('div');

  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;display:flex;align-items:center;justify-content:center;';

  overlay.innerHTML = `

    <div style="background:var(--panel);border:1px solid var(--border-color);border-radius:12px;padding:20px;width:90%;max-width:600px;max-height:80vh;overflow-y:auto;">

      <h3 style="margin-bottom:12px;font-size:15px;">✏️ 编辑任务</h3>

      <div style="margin-bottom:8px;font-size:12px;color:var(--text-muted);">ID: ${escapeHtml(taskId)}</div>

      <div class="field" style="margin-bottom:12px;">

        <label style="display:block;margin-bottom:6px;font-size:13px;font-weight:500;">任务内容</label>

        <textarea id="edit-task-message" style="width:100%;min-height:200px;background:#0c0e13;color:var(--text);border:1px solid var(--border-color);border-radius:6px;padding:10px;font-size:12px;font-family:monospace;resize:vertical;">${escapeHtml(task.message || '')}</textarea>

      </div>

      <div style="display:flex;gap:8px;justify-content:flex-end;">

        <button class="btn btn-sm btn-outline" onclick="this.closest('div[style*=fixed]').remove()">取消</button>

        <button class="btn btn-sm btn-primary" onclick="saveTaskEdit('${escapeHtml(taskId)}')">💾 保存</button>

      </div>

    </div>

  `;

  document.body.appendChild(overlay);

  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

  document.getElementById('edit-task-message').focus();

}

async function saveTaskEdit(taskId) {

  const textarea = document.getElementById('edit-task-message');

  const newMessage = textarea ? textarea.value.trim() : '';

  if (!newMessage) { showToast('任务内容不能为空', 'error'); return; }



  const overlay = textarea.closest('div[style*="fixed"]');

  if (overlay) overlay.remove();



  showToast('正在保存...', 'info');

  const res = await apiCall('/api/tasks/edit', 'POST', { task_id: taskId, message: newMessage });

  if (res && res.success) {

    showToast('任务已更新', 'success');

    loadTasksList();

  } else {

    showToast(res ? res.message : '保存失败', 'error');

  }

}

function copyTaskMessage(taskId, btnEl) {

  const task = allTasksData.find(t => t.task_id === taskId);

  if (!task) { showToast('找不到任务', 'error'); return; }

  const text = task.message || task.title || '';

  if (!text) { showToast('任务内容为空', 'error'); return; }

  navigator.clipboard.writeText(text).then(() => {

    showToast('已复制到剪贴板', 'success');

    const orig = btnEl.innerHTML;

    btnEl.innerHTML = '✅ 已复制';

    btnEl.disabled = true;

    setTimeout(() => { btnEl.innerHTML = orig; btnEl.disabled = false; }, 1500);

  }).catch(() => {

    // fallback

    const ta = document.createElement('textarea');

    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';

    document.body.appendChild(ta); ta.select();

    document.execCommand('copy'); document.body.removeChild(ta);

    showToast('已复制到剪贴板', 'success');

  });

}

function feedbackTask(taskId) {

  const task = allTasksData.find(t => t.task_id === taskId);

  if (!task) { showToast('找不到任务', 'error'); return; }

  

  const origMsg = task.message || '';

  const origTitle = task.title || '';

  const targetIde = task.target_ide || '';

  

  // 提取任务内容

  let taskContent = origMsg || origTitle || '—';

  const reqMatch = taskContent.match(/(?:【内容】|【修改需求说明】)\n?([\s\S]+?)(?:\n\n【代码修改与优化任务】|\n\n以下是待合并|\Z)/);

  if (reqMatch) {

    taskContent = reqMatch[1].trim();

  }

  

  // 提取任务详情（目标文件、组件等）

  let taskDetails = '';

  const mFile = origMsg.match(/目标文件:\s*([^\n\r]+)/);

  const mComp = origMsg.match(/组件\/类\/函数:\s*([^\n\r]+)/);

  const mType = origMsg.match(/修改类型:\s*([^\n\r]+)/);

  if (mFile) taskDetails += `📁 ${mFile[1].trim()}\n`;

  if (mComp) taskDetails += `🧩 ${mComp[1].trim()}\n`;

  if (mType) taskDetails += `📝 ${mType[1].trim()}\n`;

  

  // 显示已有反馈历史

  const feedbacks = task.feedbacks || [];

  let feedbackHistoryHtml = '';

  if (feedbacks.length > 0) {

    feedbackHistoryHtml = `

      <div style="margin-bottom:12px;">

        <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">已有反馈 (${feedbacks.length} 条):</div>

        ${feedbacks.map((fb, idx) => {

          const fbTime = fb.time ? new Date(fb.time).toLocaleString('zh-CN') : '';

          return `<div style="padding:6px 8px;background:rgba(240,160,64,0.08);border-left:2px solid var(--accent-yellow);border-radius:0 4px 4px 0;font-size:11px;color:var(--accent-yellow);margin-bottom:4px;">

            <div style="font-size:10px;color:var(--text-muted);">💬 #${idx+1}${fbTime ? ' · ' + fbTime : ''}</div>

            <div style="margin-top:2px;white-space:pre-wrap;">${escapeHtml(fb.text)}</div>

          </div>`;

        }).join('')}

      </div>

    `;

  }

  

  // 弹出输入框

  const overlay = document.createElement('div');

  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;display:flex;align-items:center;justify-content:center;';

  overlay.innerHTML = `

    <div style="background:var(--panel);border:1px solid var(--border-color);border-radius:12px;padding:20px;width:90%;max-width:600px;max-height:85vh;overflow-y:auto;">

      <h3 style="margin-bottom:12px;font-size:15px;">💬 补充反馈 — ${escapeHtml(taskId)}</h3>

      

      <!-- 主任务内容 -->

      <div style="margin-bottom:12px;">

        <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">📋 主任务内容:</div>

        <div style="padding:10px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;font-size:12px;color:var(--text-secondary);max-height:120px;overflow-y:auto;white-space:pre-wrap;line-height:1.5;">${escapeHtml(taskContent)}</div>

      </div>

      

      <!-- 任务详情 -->

      ${taskDetails ? `

      <div style="margin-bottom:12px;">

        <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">📌 任务详情:</div>

        <div style="padding:8px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;font-size:11px;color:var(--accent-blue);font-family:monospace;white-space:pre-wrap;">${escapeHtml(taskDetails)}</div>

      </div>

      ` : ''}

      

      <!-- 目标 IDE -->

      <div style="margin-bottom:12px;font-size:12px;color:var(--text-muted);">

        🎯 目标 IDE: <span style="color:var(--accent-blue);font-weight:600;">${targetIde ? targetIde.toUpperCase() : '未分配'}</span>

      </div>

      

      <!-- 已有反馈历史 -->

      ${feedbackHistoryHtml}

      

      <!-- 新反馈输入 -->

      <div>

        <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">✏️ 新增补充内容:</div>

        <textarea id="feedback-input" style="width:100%;min-height:100px;background:#0c0e13;color:var(--text);border:1px solid var(--border-color);border-radius:6px;padding:10px;font-size:13px;font-family:inherit;resize:vertical;" placeholder="描述需要修改或补充的内容..."></textarea>

      </div>

      

      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;">

        <button class="btn btn-sm btn-outline" onclick="this.closest('div[style*=fixed]').remove()">取消</button>

        <button class="btn btn-sm btn-primary" onclick="submitFeedback('${escapeHtml(taskId)}')">📤 补充并重新派发</button>

      </div>

    </div>

  `;

  document.body.appendChild(overlay);

  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

  document.getElementById('feedback-input').focus();

}

async function submitFeedback(taskId) {

  const input = document.getElementById('feedback-input');

  const feedback = input ? input.value.trim() : '';

  if (!feedback) { showToast('请输入补充内容', 'error'); return; }

  

  // 关闭弹窗

  const overlay = input.closest('div[style*="fixed"]');

  if (overlay) overlay.remove();

  

  showToast('正在提交补充反馈...', 'info');

  const res = await apiCall('/api/tasks/feedback', 'POST', { task_id: taskId, feedback });

  if (res && res.success) {

    showToast(res.message, 'success');

    loadTasksList();

  } else {

    showToast(res ? res.message : '提交失败', 'error');

  }

}

async function quickGitCommit() {

  const commitMsg = document.getElementById('git-commit-msg').value.trim();

  showToast('正在提交 Git...', 'info');

  const res = await apiCall('/api/git/commit', 'POST', { message: commitMsg });

  if (res && res.success) {

    showToast(res.message, 'success');

    document.getElementById('git-commit-msg').value = '';

  } else {

    showToast(res ? res.message : 'Git 提交失败', 'error');

  }

}

async function deleteTask(taskId, btnEl) {

  if (!confirm('确定要删除这个任务吗？')) return;

  const res = await apiCall(`/api/tasks/${taskId}`, 'DELETE');

  if (res && res.success) {

    showToast('任务已删除', 'success');

    // 从 allTasksData 中移除并重新渲染

    allTasksData = allTasksData.filter(t => t.task_id !== taskId);

    renderTasksData(allTasksData);

  } else {

    showToast(res ? res.message : '删除失败', 'error');

  }

}

async function markTaskComplete(taskId) {

  if (!confirm(`确定要手动标记任务 ${taskId} 为已完成吗？`)) return;

  showToast('正在标记任务完成...', 'info');

  const res = await apiCall('/api/tasks/complete', 'POST', { task_id: taskId, manual: true });

  if (res && res.success) {

    showToast(res.message, 'success');

    loadTasksList();

  } else {

    showToast(res ? res.message : '操作失败', 'error');

  }

}

async function autoGenerateGitCommitMsg() {

  showToast('Aide 正在分析变更并生成提交日志...', 'info');

  const res = await apiCall('/api/git/generate-commit-msg', 'POST');

  if (res && res.success && res.commit_msg) {

    const versionRes = await apiCall('/api/version/bump', 'POST');

    let versionTag = '';

    if (versionRes && versionRes.success) {

      versionTag = ' v' + versionRes.version + ' ';

      showToast('版本号已提升至 v' + versionRes.version, 'info');

    }

    document.getElementById('git-commit-msg').value = versionTag + res.commit_msg;

    showToast('提交日志已生成！', 'success');

  } else {

    showToast(res ? res.message : '生成失败', 'error');

  }

}

function onTasksLogsToggle(isOpen) {

  if (isOpen) {

    loadTasksEmbeddedLogs();

    if (!tasksLogInterval) {

      tasksLogInterval = setInterval(loadTasksEmbeddedLogs, 5000);

    }

  } else {

    if (tasksLogInterval) {

      clearInterval(tasksLogInterval);

      tasksLogInterval = null;

    }

  }

}

function switchTasksLogSource(event, source) {

  if (event) event.stopPropagation();

  tasksLogSource = source;

  document.getElementById('btn-tasks-log-desktop').classList.toggle('active-tab', source === 'desktop');

  document.getElementById('btn-tasks-log-phone').classList.toggle('active-tab', source === 'phone');

  loadTasksEmbeddedLogs();

}

async function loadTasksEmbeddedLogs(event) {

  if (event) event.stopPropagation();

  const url = tasksLogSource === 'phone' ? '/api/logs/phone?lines=100' : '/api/logs?lines=100';

  const result = await apiCall(url);

  const viewer = document.getElementById('tasks-embedded-log-viewer');

  if (result && result.logs) {

    viewer.innerHTML = result.logs.map(l => {

      let cls = 'log-line';

      if (l.includes('ERROR') || l.includes('error') || l.includes('E/') || l.includes('FATAL')) cls += ' error';

      else if (l.includes('WARNING') || l.includes('warn') || l.includes('W/')) cls += ' warn';

      return `<div class="${cls}">${escapeHtml(l)}</div>`;

    }).join('');

    viewer.scrollTop = viewer.scrollHeight;

  }

}

async function mergeSameTargetTasks() {

  if (confirm('确认合并所有针对相同目标位置的待处理任务吗？\n（将使用 Aide AI 进行需求智能合并）')) {

    showToast('正在合并任务...', 'info');

    const res = await apiCall('/api/tasks/merge_same_targets', 'POST');

    if (res && res.success) {

      showToast(res.message, 'success');

      loadTasksList();

    } else {

      showToast('合并失败: ' + (res ? res.message : '网络错误'), 'error');

    }

  }

}
