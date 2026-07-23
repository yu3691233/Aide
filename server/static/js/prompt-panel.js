function openGlobalPromptPanel(source) {

  globalPromptSource = source || 'task';

  globalPromptCategory = 'unspecified';
  window._globalPromptSurface = 'general';

  isGlobalPromptPreviewManuallyEdited = false;

  

  // 来源为任务列表时清空节点数据

  if (globalPromptSource === 'task') {

    activePromptNodes = [];

  }

  

  // 更新来源标识

  const sourceEl = document.getElementById('global-prompt-source');

  if (globalPromptSource === 'task') {

    sourceEl.innerHTML = '📋 来源：任务管理';

  } else {

    sourceEl.innerHTML = '🗺️ 来源：项目地图';

  }

  

  // 重置表单

  document.getElementById('global-prompt-meta').innerHTML = '<span style="color:var(--text-muted);">点击"分析需求"自动识别，或手动输入</span>';

  document.getElementById('global-prompt-file-input').value = '';

  document.getElementById('global-prompt-component-input').value = '';

  document.getElementById('global-prompt-user-req').value = '';

  document.getElementById('global-prompt-preview').value = '';

  document.getElementById('global-prompt-candidates-container').style.display = 'none';

  document.getElementById('global-prompt-candidates').innerHTML = '';

  

  // 隐藏快速插入组件

  document.getElementById('global-quick-component-container').style.display = 'none';

  document.getElementById('global-quick-component-badges').innerHTML = '';

  

  // 重置类型按钮

  document.getElementById('global-btn-prompt-type-unspecified').classList.add('active-tab');

  document.getElementById('global-btn-prompt-type-feature').classList.remove('active-tab');

  document.getElementById('global-btn-prompt-type-optimize').classList.remove('active-tab');

  document.getElementById('global-btn-prompt-type-bug').classList.remove('active-tab');
  document.getElementById('global-btn-prompt-type-other').classList.remove('active-tab');
  selectGlobalPromptSurface('general');
  document.getElementById('global-prompt-functional-areas').value = '';
  document.getElementById('global-prompt-ui-location').value = '';

  

  // 显示面板并推挤主内容

  const panel = document.getElementById('global-prompt-panel');

  panel.style.display = 'flex';

  document.querySelector('.main-content').style.marginRight = '480px';

  document.getElementById('global-prompt-user-req').focus();

}

function closeGlobalPromptPanel() {

  document.getElementById('global-prompt-panel').style.display = 'none';

  document.querySelector('.main-content').style.marginRight = '0';

  window._parentTaskId = null;

}

function openGlobalPromptPanelWithComponent(component, file, tasks) {

  openGlobalPromptPanel('task');

  

  // 填充组件和文件信息

  if (component) {

    document.getElementById('global-prompt-component-input').value = component;

  }

  if (file) {

    document.getElementById('global-prompt-file-input').value = file;

    document.getElementById('global-prompt-meta').textContent = file;

  }

  

  // 构建完整上下文：聚合该组件下所有任务的信息

  let contextParts = [];

  if (tasks && tasks.length > 0) {

    contextParts.push('该组件下有 ' + tasks.length + ' 个历史任务：');

    tasks.forEach((t, i) => {

      const title = t.title || '';

      const msg = t.message || '';

      const status = t.status || '';

      const ide = t.target_ide || t.dispatched_ide || '';

      const time = t.time ? new Date(t.time).toLocaleString('zh-CN') : '';

      

      // 提取需求内容

      let req = '';

      const reqMatch = msg.match(/(?:【内容】|【修改需求说明】)\n?([\s\S]+?)(?:\n\n【代码修改与优化任务】|\n\n以下是待合并|$)/);

      if (reqMatch) req = reqMatch[1].trim().substring(0, 200);

      

      contextParts.push('\n--- 任务 ' + (i+1) + ': ' + title + ' ---');

      if (status) contextParts.push('状态: ' + status);

      if (ide) contextParts.push('修改 IDE: ' + ide);

      if (time) contextParts.push('时间: ' + time);

      if (req) contextParts.push('需求: ' + req);

      

      // 提取反馈记录

      const feedbacks = t.feedbacks || [];

      if (feedbacks.length > 0) {

        contextParts.push('反馈记录 (' + feedbacks.length + ' 条):');

        feedbacks.forEach((fb, fi) => {

          const fbTime = fb.time ? new Date(fb.time).toLocaleString('zh-CN') : '';

          contextParts.push('  ' + (fi+1) + '. ' + fbTime + ': ' + (fb.text || '').substring(0, 100));

        });

      }

    });

  }

  

  if (contextParts.length > 0) {

    document.getElementById('global-prompt-user-req').value = contextParts.join('\n');

  }

  

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

}

function selectGlobalPromptCategory(cat) {

  globalPromptCategory = cat;

  document.getElementById('global-btn-prompt-type-unspecified').classList.toggle('active-tab', cat === 'unspecified');

  document.getElementById('global-btn-prompt-type-feature').classList.toggle('active-tab', cat === 'feature');

  document.getElementById('global-btn-prompt-type-optimize').classList.toggle('active-tab', cat === 'optimize');

  document.getElementById('global-btn-prompt-type-bug').classList.toggle('active-tab', cat === 'bug');
  document.getElementById('global-btn-prompt-type-other').classList.toggle('active-tab', cat === 'other');

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

}

function selectGlobalPromptSurface(surface) {
  window._globalPromptSurface = surface;
  document.querySelectorAll('#global-prompt-surface-buttons [data-surface]').forEach(button => {
    button.classList.toggle('active-tab', button.dataset.surface === surface);
  });
}

function getGlobalPromptClassification() {
  const typeMap = {
    feature: 'feature',
    optimize: 'optimization',
    bug: 'bug_fix',
    other: 'other'
  };
  return {
    surface: window._globalPromptSurface || 'general',
    task_type: typeMap[globalPromptCategory] || '',
    functional_areas: splitTaskClassificationAreas(
      document.getElementById('global-prompt-functional-areas').value
    ),
    ui_location: document.getElementById('global-prompt-ui-location').value.trim(),
    state: 'confirmed',
    source: 'user'
  };
}

async function suggestGlobalPromptClassification() {
  const userReq = document.getElementById('global-prompt-user-req').value.trim();
  if (!userReq) {
    showToast('请先输入任务需求', 'error');
    return;
  }
  showToast('正在生成分类建议...', 'info');
  const res = await apiCall('/api/tasks/classification/suggest', 'POST', { text: userReq });
  if (!res || !res.success || !res.suggestion) {
    showToast(res ? res.message : '分类建议生成失败', 'error');
    return;
  }
  const suggestion = res.suggestion;
  const categoryMap = {
    feature: 'feature',
    optimization: 'optimize',
    bug_fix: 'bug',
    other: 'other'
  };
  selectGlobalPromptCategory(categoryMap[suggestion.task_type] || 'unspecified');
  selectGlobalPromptSurface(suggestion.surface || 'general');
  document.getElementById('global-prompt-functional-areas').value =
    (suggestion.functional_areas || []).join('，');
  document.getElementById('global-prompt-ui-location').value = suggestion.ui_location || '';
  showToast(res.fallback ? 'AI 暂不可用，已填写基础规则建议，请确认' : '已填写 AI 建议，请确认或修改', 'success');
}

async function analyzeGlobalRequirements() {

  const userReq = document.getElementById('global-prompt-user-req').value.trim();

  const fileInput = document.getElementById('global-prompt-file-input').value.trim();

  const componentInput = document.getElementById('global-prompt-component-input').value.trim();

  

  if (!userReq && !fileInput && !componentInput && (!activePromptNodes || activePromptNodes.length === 0)) {

    showToast('请输入需求或目标文件信息', 'error');

    return;

  }

  

  showToast('Aide 正在分析需求...', 'info');

  

  // 构建分析上下文

  let contextParts = [];

  let userIntent = '';

  if (globalPromptCategory === 'bug') userIntent = '修复bug';

  else if (globalPromptCategory === 'optimize') userIntent = '功能优化';

  else if (globalPromptCategory === 'feature') userIntent = '新增功能';

  else if (globalPromptCategory === 'other') userIntent = '其他任务';

  

  if (userIntent) contextParts.push('用户意图: ' + userIntent);

  if (activePromptNodes && activePromptNodes.length > 0) {

    contextParts.push('目标组件: ' + activePromptNodes.map(n => n.name).join(', '));

    contextParts.push('组件文件: ' + [...new Set(activePromptNodes.map(n => n.file).filter(Boolean))].join(', '));

  }

  if (fileInput) contextParts.push('目标文件: ' + fileInput);

  if (componentInput) contextParts.push('组件/函数: ' + componentInput);

  if (userReq) contextParts.push('用户需求: ' + userReq);

  

  const nodeFile = activePromptNodes?.length > 0 ? activePromptNodes[0].file : fileInput;

  const nodeName = activePromptNodes?.length > 0 ? activePromptNodes[0].name : componentInput;

  

  try {

    // 调用 Aide AI 分析

    const res = await apiCall('/api/prompt/predict', 'POST', {

      file: nodeFile || '',

      name: nodeName || '',

      desc: contextParts.join('\n'),

      category: globalPromptCategory,

      user_req: userReq

    });

    

    if (res && res.success && res.candidates && res.candidates.length > 0) {

      // AI 分析成功，解析建议

      const suggestions = res.candidates.map(c => {

        const promptText = typeof c === 'object' ? c.prompt : c;

        const effectText = typeof c === 'object' ? c.effect : '';

        const reasonText = typeof c === 'object' ? c.reason : '';

        

        // 从 AI 返回的 prompt 中智能提取类型

        let detectedType = 'feature';

        const pLower = (promptText || '').toLowerCase();

        if (['bug', '错误', '异常', '修复', 'fix', 'error'].some(kw => pLower.includes(kw))) detectedType = 'bug';

        else if (['优化', '改进', '重构', 'refactor', 'optimize'].some(kw => pLower.includes(kw))) detectedType = 'optimize';

        

        return {

          title: promptText.substring(0, 60),

          file: nodeFile || fileInput || '',

          component: nodeName || componentInput || '',

          type: detectedType,

          prompt: promptText,

          effect: effectText,

          reason: reasonText

        };

      });

      

      // 自动选择第一个建议的类型

      if (suggestions.length > 0) {

        selectGlobalPromptCategory(suggestions[0].type);

        if (suggestions[0].file && !fileInput) {

          document.getElementById('global-prompt-file-input').value = suggestions[0].file;

          document.getElementById('global-prompt-meta').textContent = suggestions[0].file;

        }

        if (suggestions[0].component && !componentInput) {

          document.getElementById('global-prompt-component-input').value = suggestions[0].component;

        }

      }

      

      // 显示建议列表

      const container = document.getElementById('global-prompt-candidates-container');

      const candidatesEl = document.getElementById('global-prompt-candidates');

      container.style.display = 'block';

      candidatesEl.innerHTML = suggestions.map((s, idx) => {

        const typeLabel = s.type === 'bug' ? '🐛 修复bug' : s.type === 'optimize' ? '⚡ 功能优化' : '✨ 新增功能';

        let metaHtml = '';

        if (s.effect || s.reason) {

          metaHtml = '<div style="margin-top:6px; font-size:11px; display:flex; flex-direction:column; gap:4px; border-top:1px dashed var(--border-color); padding-top:6px;">' +

            (s.effect ? '<div><span style="color:var(--accent-green); font-weight:bold;">🎯 预期效果:</span> ' + escapeHtml(s.effect) + '</div>' : '') +

            (s.reason ? '<div><span style="color:var(--accent-blue); font-weight:bold;">💡 建议理由:</span> ' + escapeHtml(s.reason) + '</div>' : '') +

            '</div>';

        }

        return '<div style="padding:10px 12px; background:var(--bg-primary); border:1px solid var(--border-color); border-radius:6px; cursor:pointer; transition:var(--transition); margin-bottom:8px;" ' +

          'onclick="applyGlobalSuggestion(' + idx + ')" onmouseover="this.style.borderColor=\'var(--accent-blue)\'" onmouseout="this.style.borderColor=\'var(--border-color)\'">' +

          '<div style="font-size:12px; color:var(--text-primary); font-weight:500;">' + escapeHtml(s.prompt.substring(0, 100)) + '</div>' +

          '<div style="display:flex; gap:8px; margin-top:6px; font-size:11px;">' +

          (s.file ? '<span style="color:var(--accent-blue);">📁 ' + escapeHtml(s.file) + '</span>' : '') +

          (s.component ? '<span style="color:var(--accent-purple);">🧩 ' + escapeHtml(s.component) + '</span>' : '') +

          '<span style="color:var(--accent-green);">' + typeLabel + '</span></div>' +

          metaHtml + '</div>';

      }).join('');

      

      window._globalSuggestions = suggestions;

      showToast('Aide 分析完成', 'success');

    } else {

      // AI 返回失败，降级到本地分析

      generateLocalSuggestions(userReq, fileInput, componentInput);

    }

  } catch (e) {

    // 网络错误，降级到本地分析

    generateLocalSuggestions(userReq, fileInput, componentInput);

  }

}

function generateLocalSuggestions(userReq, fileInput, componentInput) {

  const suggestions = [];

  const files = fileInput ? fileInput.split(',').map(f => f.trim()).filter(Boolean) : [];

  const components = componentInput ? componentInput.split(',').map(c => c.trim()).filter(Boolean) : [];

  const hasNodes = activePromptNodes && activePromptNodes.length > 0;

  

  // 智能分析用户输入，判断修改类型

  let detectedType = 'feature';

  const reqLower = (userReq || '').toLowerCase();

  const bugKeywords = ['bug', '错误', '异常', '崩溃', '闪退', '报错', '失败', '无法', '不能', '不工作', '修复', 'fix', 'error', 'crash', 'broken'];

  const optKeywords = ['优化', '改进', '改善', '重构', 'refactor', 'optimize', 'performance', '性能', '加速', '精简', '简化'];

  if (bugKeywords.some(kw => reqLower.includes(kw))) {

    detectedType = 'bug';

  } else if (optKeywords.some(kw => reqLower.includes(kw))) {

    detectedType = 'optimize';

  }

  

  // 从用户输入中提取文件路径（如 server/xxx.py, src/xxx.js, xxx.html 等）

  const filePathRegex = /(?:^|\s|["'`])([\w\-\.\/\\]+?\.(?:py|js|ts|jsx|tsx|html|css|json|kt|java|go|rs|vue|svelte))(?:\s|$|["'`.,;:!?])/gi;

  let match;

  const detectedFiles = [];

  while ((match = filePathRegex.exec(userReq || '')) !== null) {

    detectedFiles.push(match[1]);

  }

  const allFiles = [...new Set([...files, ...detectedFiles])];

  

  // 从用户输入中提取组件/函数名（如 xxx(), XxxComponent, <xxx> 等）

  const compRegex = /(?:[\w]+\(\)|<[\w\-]+>|[\w]+\.(?:py|js|kt))/g;

  const detectedComps = [];

  while ((match = compRegex.exec(userReq || '')) !== null) {

    detectedComps.push(match[0]);

  }

  const allComponents = [...new Set([...components, ...detectedComps])];

  

  // 更新类型选择器

  selectGlobalPromptCategory(detectedType);

  

  // 如果检测到文件，自动填入

  if (detectedFiles.length > 0 && !fileInput) {

    document.getElementById('global-prompt-file-input').value = detectedFiles.join(', ');

    document.getElementById('global-prompt-meta').textContent = detectedFiles.join(', ');

  }

  

  // 生成建议

  if (hasNodes) {

    const nodeNames = activePromptNodes.map(n => n.name).join('、');

    const nodeFiles = [...new Set(activePromptNodes.map(n => n.file).filter(Boolean))];

    suggestions.push({

      title: `修改 ${nodeNames}`,

      file: nodeFiles.join(', '),

      component: activePromptNodes.map(n => n.name).join(', '),

      type: detectedType,

      prompt: userReq || `改进 ${nodeNames} 的功能`

    });

  }

  

  if (allFiles.length > 0) {

    const fileName = allFiles[0].split('/').pop().replace(/\.[^.]+$/, '');

    suggestions.push({

      title: `修改 ${allFiles[0]}`,

      file: allFiles.join(', '),

      component: allComponents.join(', ') || fileName,

      type: detectedType,

      prompt: userReq || `修改 ${fileName}`

    });

  }

  

  if (userReq) {

    suggestions.push({

      title: userReq.substring(0, 50),

      file: allFiles.join(', '),

      component: allComponents.join(', '),

      type: detectedType,

      prompt: userReq

    });

  }

  

  if (suggestions.length === 0) {

    suggestions.push({

      title: '添加新功能',

      file: '',

      component: '',

      type: 'feature',

      prompt: userReq || '（请描述您想要实现的功能）'

    });

  }

  

  const typeLabel = detectedType === 'bug' ? '🐛 修复bug' : detectedType === 'optimize' ? '⚡ 功能优化' : '✨ 新增功能';

  

  const container = document.getElementById('global-prompt-candidates-container');

  const candidatesEl = document.getElementById('global-prompt-candidates');

  container.style.display = 'block';

  candidatesEl.innerHTML = suggestions.map((s, idx) => {

    const sTypeLabel = s.type === 'bug' ? '🐛 修复bug' : s.type === 'optimize' ? '⚡ 功能优化' : '✨ 新增功能';

    return `

      <div style="padding:10px 12px; background:var(--bg-primary); border:1px solid var(--border-color); border-radius:6px; cursor:pointer; transition:var(--transition);" 

           onclick="applyGlobalSuggestion(${idx})" 

           onmouseover="this.style.borderColor='var(--accent-blue)'" 

           onmouseout="this.style.borderColor='var(--border-color)'">

        <div style="font-size:13px; font-weight:500; color:var(--text-primary);">${escapeHtml(s.title)}</div>

        <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; font-size:11px;">

          ${s.file ? '<span style="color:var(--accent-blue);">📁 ' + escapeHtml(s.file) + '</span>' : ''}

          ${s.component ? '<span style="color:var(--accent-purple);">🧩 ' + escapeHtml(s.component) + '</span>' : ''}

          <span style="color:var(--accent-green);">${sTypeLabel}</span>

        </div>

      </div>

    `;

  }).join('');

  

  window._globalSuggestions = suggestions;

  showToast('已分析需求，类型: ' + typeLabel, 'success');

}

function applyGlobalSuggestion(idx) {

  const suggestions = window._globalSuggestions;

  if (!suggestions || !suggestions[idx]) return;

  

  const s = suggestions[idx];

  if (s.prompt) {

    document.getElementById('global-prompt-user-req').value = s.prompt;

  }

  if (s.file) {

    document.getElementById('global-prompt-file-input').value = s.file;

  }

  if (s.component) {

    document.getElementById('global-prompt-component-input').value = s.component;

  }

  if (s.type) {

    selectGlobalPromptCategory(s.type);

  }

  

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

  showToast('已应用建议', 'success');

}

function updateGlobalPromptPreview() {

  if (isGlobalPromptPreviewManuallyEdited) return;

  

  const userReq = document.getElementById('global-prompt-user-req').value.trim();

  const fileInput = document.getElementById('global-prompt-file-input').value.trim();

  const componentInput = document.getElementById('global-prompt-component-input').value.trim();

  

  let typeCN = '未指定';

  if (globalPromptCategory === 'feature') typeCN = '新增功能';

  else if (globalPromptCategory === 'optimize') typeCN = '功能优化';

  else if (globalPromptCategory === 'bug') typeCN = '修复bug';

  else if (globalPromptCategory === 'other') typeCN = '其他任务';

  

  let promptText = '';

  

  // 内容

  if (userReq) {

    promptText += `【内容】${userReq}\n`;

  } else {

    promptText += `【内容】（请在此处说明您希望实现的功能）\n`;

  }

  

  promptText += `\n【代码修改与优化任务】\n`;

  

  // 如果有选中的组件节点（来自项目地图），生成详细信息

  if (activePromptNodes && activePromptNodes.length > 0) {

    if (activePromptNodes.length === 1) {

      const node = activePromptNodes[0];

      let range = '';

      if (node.lineStart) {

        range = `第 ${node.lineStart} 行` + (node.lineEnd && node.lineEnd !== node.lineStart ? ` 到第 ${node.lineEnd} 行` : '');

      }

      promptText += `目标文件: ${node.file}\n`;

      if (range) promptText += `目标范围: ${range}\n`;

      promptText += `组件/类/函数: ${node.name}\n`;

      if (node.desc) promptText += `组件描述: ${node.desc}\n`;

    } else {

      promptText += `目标文件与组件范围:\n`;

      activePromptNodes.forEach((node, idx) => {

        let range = '';

        if (node.lineStart) {

          range = ` (行 ${node.lineStart}${node.lineEnd && node.lineEnd !== node.lineStart ? '-' + node.lineEnd : ''})`;

        }

        promptText += `  ${idx + 1}. [组件] ${node.name} -> 文件: ${node.file}${range}\n`;

      });

    }

  } else {

    // 手动输入模式

    if (fileInput) promptText += `目标文件: ${fileInput}\n`;

    if (componentInput) promptText += `组件/类/函数: ${componentInput}\n`;

  }

  

  if (globalPromptCategory !== 'unspecified') {

    promptText += `修改类型: ${typeCN}\n`;

  }

  

  document.getElementById('global-prompt-preview').value = promptText;

}

function onGlobalPromptPreviewManualEdit() {

  isGlobalPromptPreviewManuallyEdited = true;

}

function insertGlobalComponentRef(name) {

  const input = document.getElementById('global-prompt-user-req');

  const textToInsert = `【${name}】`;

  const start = input.selectionStart;

  const end = input.selectionEnd;

  const val = input.value;

  input.value = val.substring(0, start) + textToInsert + val.substring(end);

  input.selectionStart = input.selectionEnd = start + textToInsert.length;

  input.focus();

  updateGlobalPromptPreview();

}

async function predictGlobalPromptCandidates() {

  const fileInput = document.getElementById('global-prompt-file-input').value.trim();

  const componentInput = document.getElementById('global-prompt-component-input').value.trim();

  const userReq = document.getElementById('global-prompt-user-req').value.trim();

  const hasNodes = activePromptNodes && activePromptNodes.length > 0;

  

  if (!hasNodes && !fileInput && !componentInput && !userReq) {

    showToast('请先选择组件或输入目标文件/需求', 'error');

    return;

  }

  

  const container = document.getElementById('global-prompt-candidates-container');

  const list = document.getElementById('global-prompt-candidates');

  

  container.style.display = 'block';

  list.innerHTML = '<div style="font-size:12px; color:var(--text-muted);">🧚 Aide 正在为您预测相关的提示词，请稍候...</div>';

  

  let predictFile = '';

  let predictName = '';

  let predictDesc = '';

  

  if (hasNodes) {

    const node = activePromptNodes[0] || {};

    predictFile = activePromptNodes.length === 1 ? node.file : activePromptNodes.map(n => n.file).join(', ');

    predictName = activePromptNodes.length === 1 ? node.name : activePromptNodes.map(n => n.name).join(', ');

    predictDesc = activePromptNodes.length === 1 ? node.desc : `多组件关联: ${activePromptNodes.map(n => n.name).join(' & ')}`;

  } else {

    predictFile = fileInput;

    predictName = componentInput;

    predictDesc = userReq;

  }

  

  const res = await apiCall('/api/prompt/predict', 'POST', {

    file: predictFile,

    name: predictName,

    desc: predictDesc,

    category: globalPromptCategory,

    user_req: userReq

  });

  

  if (res && res.success && res.candidates && res.candidates.length > 0) {

    window._globalPredictedCandidates = res.candidates;

    list.innerHTML = res.candidates.map((c, i) => {

      const promptText = typeof c === 'object' ? c.prompt : c;

      const effectText = typeof c === 'object' ? c.effect : '';

      const reasonText = typeof c === 'object' ? c.reason : '';

      

      let metaHtml = '';

      if (effectText || reasonText) {

        metaHtml = `

          <div style="margin-top: 6px; font-size: 11px; display: flex; flex-direction: column; gap: 4px; border-top: 1px dashed var(--border-color); padding-top: 6px;">

            ${effectText ? `<div><span style="color: var(--accent-green); font-weight: bold; margin-right: 4px;">🎯 预期效果:</span><span style="color: var(--text-primary);">${escapeHtml(effectText)}</span></div>` : ''}

            ${reasonText ? `<div><span style="color: var(--accent-blue); font-weight: bold; margin-right: 4px;">💡 建议理由:</span><span style="color: var(--text-secondary);">${escapeHtml(reasonText)}</span></div>` : ''}

          </div>

        `;

      }

      

      return `

        <div onclick="applyGlobalPredictedCandidate(${i})" style="background:var(--bg-primary); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:10px; font-size:12px; cursor:pointer; transition:var(--transition); line-height:1.4; margin-bottom: 8px;" onmouseover="this.style.borderColor='var(--accent-blue)';" onmouseout="this.style.borderColor='var(--border-color)';">

          <div style="font-weight: 500; color: var(--text-primary);"><span style="font-weight:600; color:var(--accent-blue); margin-right:6px;">推荐 ${i+1}:</span> ${escapeHtml(promptText)}</div>

          ${metaHtml}

        </div>

      `;

    }).join('');

  } else {

    list.innerHTML = '<div style="font-size:12px; color:var(--accent-red);">❌ AI 预测失败，请重试或手动输入。</div>';

  }

}

function applyGlobalPredictedCandidate(idx) {

  const c = (window._globalPredictedCandidates || [])[idx];

  if (!c) return;

  const promptText = typeof c === 'object' ? c.prompt : c;

  document.getElementById('global-prompt-user-req').value = promptText;

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

}

async function saveGlobalPromptAsTask() {

  const promptText = document.getElementById('global-prompt-preview').value;
  const originalText = document.getElementById('global-prompt-user-req').value.trim();

  if (!promptText.trim()) {

    showToast('提示词内容不能为空', 'error');

    return;

  }

  

  showToast('正在创建任务...', 'info');

  const body = {

    text: promptText,
    original_text: originalText,
    title: originalText.substring(0, 60),
    source: 'web',
    auto_dispatch: false,
    classification: getGlobalPromptClassification()

  };

  if (window._parentTaskId) {

    body.parent_task_id = window._parentTaskId;

  }

  const res = await apiCall('/api/tasks/create', 'POST', body);

  

  if (res && res.ok) {

    showToast('成功加入任务列表！', 'success');

    closeGlobalPromptPanel();

    if (document.getElementById('page-tasks') && document.getElementById('page-tasks').classList.contains('active')) {

      loadTasksList();

    }

  } else {

    showToast(res ? res.message : '保存失败', 'error');

  }

}

function copyGlobalPrompt() {

  const promptText = document.getElementById('global-prompt-preview').value;

  if (!promptText.trim()) {

    showToast('提示词内容不能为空', 'error');

    return;

  }

  navigator.clipboard.writeText(promptText);

  showToast('AI 提示词已复制到剪贴板！', 'success');

  closeGlobalPromptPanel();

}

function openPromptBuilder(event, file, lineStart, lineEnd, name, desc) {

  if (event) event.stopPropagation();

  const selectedNode = { file, lineStart, lineEnd, name, desc };

  const debugNodes = debugCollectedNodes.map(n => ({

    file: n.id ? `#${n.id}` : '',

    lineStart: '', lineEnd: '',

    name: n.id || n.tag || '组件',

    desc: formatNodeForPrompt(n)

  }));

  activePromptNodes = [selectedNode, ...debugNodes.filter(d => d.name !== selectedNode.name)];

  debugCollectedNodes = [];

  

  const files = [...new Set(activePromptNodes.map(n => n.file).filter(Boolean))];

  const componentNames = activePromptNodes.map(n => n.name).filter(Boolean);

  

  openGlobalPromptPanel('map');

  

  if (files.length > 0) {

    document.getElementById('global-prompt-file-input').value = files.join(', ');

    document.getElementById('global-prompt-meta').textContent = files.join(', ');

  }

  if (componentNames.length > 0) {

    document.getElementById('global-prompt-component-input').value = componentNames.join(', ');

  }

  

  const quickContainer = document.getElementById('global-quick-component-container');

  const badgesEl = document.getElementById('global-quick-component-badges');

  if (activePromptNodes.length > 0) {

    quickContainer.style.display = 'flex';

    badgesEl.innerHTML = activePromptNodes.map(node => {

      return `<button class="btn btn-sm btn-outline" style="font-family:monospace; font-size:11px;" onclick="insertGlobalComponentRef('${node.name.replace(/'/g, "\\'")}')">【${escapeHtml(node.name)}】</button>`;

    }).join('');

  }

  

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

}

function openBatchPromptBuilder() {

  const checkboxes = document.querySelectorAll('.tree-node-select:checked');

  const debugNodes = debugCollectedNodes.map(n => ({

    file: n.id ? `#${n.id}` : '',

    lineStart: '', lineEnd: '',

    name: n.id || n.tag || '组件',

    desc: formatNodeForPrompt(n)

  }));

  

  if (checkboxes.length === 0 && debugNodes.length === 0) {

    showToast('请先选择组件或在调试模式中收集组件', 'error');

    return;

  }

  

  const checkedNodes = Array.from(checkboxes).map(cb => ({

    file: cb.getAttribute('data-file'),

    lineStart: cb.getAttribute('data-linestart'),

    lineEnd: cb.getAttribute('data-lineend'),

    name: cb.getAttribute('data-name'),

    desc: cb.getAttribute('data-desc')

  }));

  

  activePromptNodes = [...checkedNodes, ...debugNodes];

  debugCollectedNodes = [];

  

  // 合并文件信息

  const files = [...new Set(activePromptNodes.map(n => n.file).filter(Boolean))];

  const componentNames = activePromptNodes.map(n => n.name).filter(Boolean);

  

  openGlobalPromptPanel('map');

  

  // 预填文件和组件信息

  if (files.length > 0) {

    document.getElementById('global-prompt-file-input').value = files.join(', ');

    document.getElementById('global-prompt-meta').textContent = files.join(', ');

  }

  if (componentNames.length > 0) {

    document.getElementById('global-prompt-component-input').value = componentNames.join(', ');

  }

  

  // 渲染快速插入组件徽章

  const quickContainer = document.getElementById('global-quick-component-container');

  const badgesEl = document.getElementById('global-quick-component-badges');

  if (activePromptNodes.length > 0) {

    quickContainer.style.display = 'flex';

    badgesEl.innerHTML = activePromptNodes.map(node => {

      return `<button class="btn btn-sm btn-outline" style="font-family:monospace; font-size:11px;" onclick="insertGlobalComponentRef('${node.name.replace(/'/g, "\\'")}')">【${escapeHtml(node.name)}】</button>`;

    }).join('');

  } else {

    quickContainer.style.display = 'none';

  }

  

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

}

function selectComponentForPrompt(label, page, description) {

  switchMapSubTab('ui');

  

  const contextText = description || label;

  activePromptNodes = [{

    file: '',

    lineStart: '',

    lineEnd: '',

    name: label,

    desc: `${page} - ${contextText}`

  }];

  

  // 合并文件和组件信息

  const files = [...new Set(activePromptNodes.map(n => n.file).filter(Boolean))];

  const componentNames = activePromptNodes.map(n => n.name).filter(Boolean);

  

  openGlobalPromptPanel('map');

  

  if (files.length > 0) {

    document.getElementById('global-prompt-file-input').value = files.join(', ');

    document.getElementById('global-prompt-meta').textContent = files.join(', ');

  }

  if (componentNames.length > 0) {

    document.getElementById('global-prompt-component-input').value = componentNames.join(', ');

  }

  

  // 渲染快速插入组件徽章

  const quickContainer = document.getElementById('global-quick-component-container');

  const badgesEl = document.getElementById('global-quick-component-badges');

  if (activePromptNodes.length > 0) {

    quickContainer.style.display = 'flex';

    badgesEl.innerHTML = activePromptNodes.map(node => {

      return `<button class="btn btn-sm btn-outline" style="font-family:monospace; font-size:11px;" onclick="insertGlobalComponentRef('${node.name.replace(/'/g, "\\'")}')">【${escapeHtml(node.name)}】</button>`;

    }).join('');

  }

  

  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

}

function initPromptPanel() { /* merged into openBatchPromptBuilder */ }

function closePromptPanel() { closeGlobalPromptPanel(); }

function closePromptModal() { closeGlobalPromptPanel(); }

function selectPromptCategory(cat) { selectGlobalPromptCategory(cat); }

function updatePromptPreview() { updateGlobalPromptPreview(); }

function onPromptPreviewManualEdit() { onGlobalPromptPreviewManualEdit(); }

function predictPromptCandidates() { predictGlobalPromptCandidates(); }

function applyCandidateByIndex(idx) { applyGlobalPredictedCandidate(idx); }

function savePromptAsTaskDraft() { saveGlobalPromptAsTask(); }

function copyGeneratedPrompt() { copyGlobalPrompt(); }

function analyzeInlineRequirements() { analyzeGlobalRequirements(); }

function applyInlineSuggestion(idx) { applyGlobalSuggestion(idx); }

function openFollowUpPrompt(taskId) {

  const task = allTasksData.find(t => t.task_id === taskId);

  if (!task) { showToast('找不到任务', 'error'); return; }



  openGlobalPromptPanel('task');



  // 从任务消息中提取组件名和文件路径

  const msg = task.message || '';

  let file = '';

  let component = '';

  const mFile = msg.match(/目标文件:\s*([^\n\r]+)/);

  const mComp = msg.match(/组件\/类\/函数:\s*([^\n\r]+)/);

  if (mFile) file = mFile[1].trim();

  if (mComp) component = mComp[1].trim();



  // 提取核心需求（去掉模板结构）

  let coreReq = msg;

  const contentMatch = msg.match(/【内容】\n?([\s\S]+?)(?:\n\n【代码修改与优化任务】|\n\n以下是待合并|$)/);

  if (contentMatch) coreReq = contentMatch[1].trim();

  // 去掉可能混入的模板头部

  coreReq = coreReq.replace(/^【代码修改与优化任务】\s*\n*/g, '').trim();

  // 取第一行作为简短摘要（太长则截断）

  const summary = coreReq.split('\n')[0].trim().substring(0, 80);



  // 预填组件和文件

  if (component) document.getElementById('global-prompt-component-input').value = component;

  if (file) document.getElementById('global-prompt-file-input').value = file;



  // 构建上下文文本

  const status = task.status || '';

  const ide = task.target_ide || task.dispatched_ide || '';

  const time = task.time ? new Date(task.time).toLocaleString('zh-CN') : '';

  const feedbacks = task.feedbacks || [];



  let context = '===== 前置任务背景 =====\n';

  context += `需求: ${summary}\n`;

  if (status) context += `状态: ${status}\n`;

  if (ide) context += `修改 IDE: ${ide}\n`;

  if (time) context += `创建时间: ${time}\n`;

  if (file) context += `目标文件: ${file}\n`;

  if (component) context += `组件: ${component}\n`;



  if (feedbacks.length > 0) {

    context += '\n历史反馈:\n';

    feedbacks.forEach((fb, i) => {

      const fbTime = fb.time ? new Date(fb.time).toLocaleString('zh-CN') : '';

      context += `${i+1}. ${fbTime}: ${fb.text || ''}\n`;

    });

  }



  context += '\n===== 补充任务 =====\n\n';



  // 预填需求输入框

  const reqEl = document.getElementById('global-prompt-user-req');

  reqEl.value = context;

  reqEl.focus();

  reqEl.selectionStart = reqEl.selectionEnd = context.length;



  // 存储原始任务 ID，供保存时传递

  window._parentTaskId = taskId;



  isGlobalPromptPreviewManuallyEdited = false;

  updateGlobalPromptPreview();

}
