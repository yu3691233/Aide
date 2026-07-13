
        // 临时禁用 SW（清理缓存后�?
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.getRegistrations().then(regs => {
                regs.forEach(r => r.unregister());
            });
        }

        const chatContainer = document.getElementById('chat-container');
        const msgInput = document.getElementById('msg-input');
        const sendBtn = document.getElementById('send-btn');
        const soundToggle = document.getElementById('sound-toggle');
        
        let lastHistoryHash = "";
        let audioContext = null;
        let soundEnabled = false;

        function enableSound() {
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            soundEnabled = true;
            soundToggle.textContent = "🔔 声音已开�?;
            soundToggle.className = "active";
            soundToggle.disabled = true;
            playChime();
        }

        function playChime() {
            if (!soundEnabled || !audioContext) return;
            try {
                if (audioContext.state === 'suspended') {
                    audioContext.resume();
                }
                const now = audioContext.currentTime;
                
                const osc1 = audioContext.createOscillator();
                const gain1 = audioContext.createGain();
                osc1.type = 'sine';
                osc1.frequency.setValueAtTime(523.25, now);
                gain1.gain.setValueAtTime(0.15, now);
                gain1.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
                osc1.connect(gain1);
                gain1.connect(audioContext.destination);
                osc1.start(now);
                osc1.stop(now + 0.3);
                
                const osc2 = audioContext.createOscillator();
                const gain2 = audioContext.createGain();
                osc2.type = 'sine';
                osc2.frequency.setValueAtTime(659.25, now + 0.12);
                gain2.gain.setValueAtTime(0.15, now + 0.12);
                gain2.gain.exponentialRampToValueAtTime(0.01, now + 0.45);
                osc2.connect(gain2);
                gain2.connect(audioContext.destination);
                osc2.start(now + 0.12);
                osc2.stop(now + 0.45);
            } catch (e) {
                console.error("Audio error:", e);
            }
        }

        function getHash(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                hash = (hash << 5) - hash + str.charCodeAt(i);
                hash |= 0;
            }
            return hash.toString();
        }

        function loadHistory() {
            fetch('/history?t=' + Date.now())
                .then(r => r.json())
                .then(data => {
                    const dataStr = JSON.stringify(data);
                    const currentHash = getHash(dataStr);
                    
                    if (currentHash !== lastHistoryHash) {
                        chatContainer.innerHTML = '';
                        data.forEach(msg => {
                            const wrapper = document.createElement('div');
                            wrapper.className = `bubble-wrapper ${msg.sender}`;
                            
                            let displayText = msg.text;
                            let options = msg.options || [];
                            
                            // Parse options from text if present (format: [选择: option1 | option2])
                            const optionReg = /\[(?:选择|选项):\s*([^\]]+)\]/;
                            const match = displayText.match(optionReg);
                            if (match) {
                                options = match[1].split(/[|�?�?]/).map(s => s.trim()).filter(Boolean);
                                displayText = displayText.replace(optionReg, '').trim();
                            }

                            const bubble = document.createElement('div');
                            bubble.className = 'bubble';
                            bubble.textContent = displayText;

                            if (msg.image) {
                                const img = document.createElement('img');
                                img.src = msg.image;
                                img.style.maxWidth = '100%';
                                img.style.maxHeight = '200px';
                                img.style.borderRadius = '8px';
                                img.style.marginTop = '8px';
                                img.style.display = 'block';
                                img.style.cursor = 'pointer';
                                img.onclick = () => window.open(msg.image, '_blank');
                                bubble.appendChild(img);
                            }
                            
                            const time = document.createElement('div');
                            time.className = 'time';
                            time.textContent = msg.time;
                            
                            wrapper.appendChild(bubble);
                            
                            // Render quick reply options
                            if (options.length > 0 && msg.sender === 'agent') {
                                const optContainer = document.createElement('div');
                                optContainer.style.display = 'flex';
                                optContainer.style.gap = '8px';
                                optContainer.style.flexWrap = 'wrap';
                                optContainer.style.marginTop = '8px';
                                optContainer.style.marginBottom = '4px';
                                
                                options.forEach(opt => {
                                    const btn = document.createElement('button');
                                    btn.textContent = opt;
                                    btn.style.background = 'var(--bubble-agent)';
                                    btn.style.border = '1px solid var(--border-color)';
                                    btn.style.color = 'var(--accent-color)';
                                    btn.style.padding = '6px 12px';
                                    btn.style.borderRadius = '15px';
                                    btn.style.cursor = 'pointer';
                                    btn.style.fontSize = '0.85rem';
                                    btn.style.transition = 'all 0.2s';
                                    btn.style.outline = 'none';
                                    
                                    btn.onclick = () => {
                                        msgInput.value = opt;
                                        sendMessage();
                                    };
                                    optContainer.appendChild(btn);
                                });
                                wrapper.appendChild(optContainer);
                            }
                            
                            wrapper.appendChild(time);
                            chatContainer.appendChild(wrapper);
                        });
                        
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                        
                        if (lastHistoryHash !== "" && data.length > 0) {
                            const lastMsg = data[data.length - 1];
                            if (lastMsg.sender === 'agent') {
                                playChime();
                            }
                        }
                        
                        lastHistoryHash = currentHash;
                    }
                });
        }

        let activeTarget = "assistant";
        let activeSessionId = "trae_global";
        let allSessions = [];

        function toggleMoreIdesDropdown(e) {
            if (e) e.stopPropagation();
            const dropdown = document.getElementById('more-ides-dropdown');
            dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
        }

        document.addEventListener('click', () => {
            const dropdown = document.getElementById('more-ides-dropdown');
            if (dropdown) dropdown.style.display = 'none';
        });

        function selectMoreIde(target, name, e) {
            if (e) e.stopPropagation();
            document.getElementById('more-ides-dropdown').style.display = 'none';
            
            // Set activeTarget
            activeTarget = target;
            
            // Remove active from all tabs
            document.querySelectorAll('.target-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.target-tab-dropdown').forEach(t => t.classList.remove('active'));
            
            // Highlight current dropdown option
            const targetEl = document.querySelector(`.target-tab-dropdown[data-target="${target}"]`);
            if (targetEl) targetEl.classList.add('active');
            
            // Highlight the "More" button
            const moreBtn = document.getElementById('more-ides-btn');
            moreBtn.classList.add('active');
            moreBtn.textContent = `�?${name}`;
            
            msgInput.placeholder = `发消息给 ${name}...`;
            
            if (monitorActive) {
                refreshMonitor();
            }
        }

        const tabs = document.querySelectorAll('.target-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.target-tab-dropdown').forEach(t => t.classList.remove('active'));
                
                tab.classList.add('active');
                activeTarget = tab.dataset.target;
                
                const moreBtn = document.getElementById('more-ides-btn');
                moreBtn.classList.remove('active');
                moreBtn.textContent = '�?;

                // Map target back to global virtual session if selected from main tab
                if (activeTarget === 'assistant') {
                    activeSessionId = 'agy_global'; // assistant falls back to agy
                    msgInput.placeholder = "发消息给小梦�?..";
                } else if (activeTarget === 'agy') {
                    activeSessionId = 'agy_global';
                    msgInput.placeholder = "发消息给 Antigravity IDE...";
                } else if (activeTarget === 'trae') {
                    activeSessionId = 'trae_global';
                    msgInput.placeholder = "发消息给 Trae IDE...";
                }
                
                // Update dropdown to match if there is a matching virtual session option
                const select = document.getElementById('global-session-select');
                if (select) {
                    if (activeTarget === 'assistant' || activeTarget === 'agy') {
                        select.value = 'agy_global';
                    } else if (activeTarget === 'trae') {
                        select.value = 'trae_global';
                    }
                }

                if (monitorActive) {
                    refreshMonitor();
                }
            });
        });

        // Load sessions list from Flask backend
        function loadSessions() {
            fetch('/sessions?t=' + Date.now())
                .then(r => r.json())
                .then(data => {
                    allSessions = data;
                    const select = document.getElementById('global-session-select');
                    if (!select) return;
                    const currentVal = select.value;
                    
                    select.innerHTML = '';
                    
                    data.forEach(s => {
                        const opt = document.createElement('option');
                        opt.value = s.id;
                        opt.textContent = s.title;
                        opt.dataset.target = s.target;
                        opt.dataset.directory = s.directory;
                        if (s.directory && s.directory !== "本地活动窗口") {
                            opt.title = s.directory;
                        }
                        select.appendChild(opt);
                    });
                    
                    // Restore previous value if it still exists
                    if (data.some(s => s.id === currentVal)) {
                        select.value = currentVal;
                    } else if (data.length > 0) {
                        select.value = data[0].id;
                        // Avoid overriding if user already has an active selection
                        if (!currentVal) {
                            switchSession(data[0].id);
                        }
                    }
                });
        }
        
        function switchSession(sessionId) {
            activeSessionId = sessionId;
            const select = document.getElementById('global-session-select');
            if (!select) return;
            const opt = select.querySelector(`option[value="${sessionId}"]`);
            if (!opt) return;
            
            const target = opt.dataset.target;
            
            if (target === 'assistant' || target === 'agy' || target === 'trae') {
                // Main row tabs
                document.querySelectorAll('.target-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.target-tab-dropdown').forEach(t => t.classList.remove('active'));
                
                const tab = document.querySelector(`.target-tab[data-target="${target}"]`);
                if (tab) tab.classList.add('active');
                
                const moreBtn = document.getElementById('more-ides-btn');
                moreBtn.classList.remove('active');
                moreBtn.textContent = '�?;
                
                activeTarget = target;
                msgInput.placeholder = target === 'assistant' ? "发消息给小梦�?.." : `发消息给 ${tab ? tab.textContent : target}...`;
            } else {
                // Dropdown items (oc / mimo)
                const name = target === 'oc' ? 'OpenCode' : 'MimoCode';
                selectMoreIde(target, name);
            }
            
            if (monitorActive) {
                refreshMonitor();
            }
        }
        
        // Fetch sessions list every 5 seconds
        setInterval(loadSessions, 5000);
        loadSessions();

        let selectedImage = null;

        function triggerUpload() {
            const fi = document.getElementById('file-input');
            try {
                fi.click();
            } catch (err) {
                showToast('无法打开图片选择器：' + err + '。iOS PWA 请重新添加到主屏幕�?);
            }
        }

        function handleFileSelect(input) {
            const file = input.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            msgInput.placeholder = "正在上传图片...";

            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.url) {
                    selectedImage = { url: data.url, path: data.path };
                    document.getElementById('image-preview').src = data.url;
                    document.getElementById('image-preview-container').style.display = 'flex';
                }
                
                if (activeTarget === 'assistant') {
                    msgInput.placeholder = "发消息给小梦�?..";
                } else if (activeTarget === 'agy') {
                    msgInput.placeholder = "发消息给 Antigravity IDE...";
                } else if (activeTarget === 'trae') {
                    msgInput.placeholder = "发消息给 Trae IDE...";
                }
                input.value = '';
            })
            .catch(err => {
                console.error("Upload error:", err);
                alert("图片上传失败");
                if (activeTarget === 'assistant') {
                    msgInput.placeholder = "发消息给小梦�?..";
                } else if (activeTarget === 'agy') {
                    msgInput.placeholder = "发消息给 Antigravity IDE...";
                } else if (activeTarget === 'trae') {
                    msgInput.placeholder = "发消息给 Trae IDE...";
                }
                input.value = '';
            });
        }

        function clearSelectedImage() {
            selectedImage = null;
            document.getElementById('image-preview-container').style.display = 'none';
            document.getElementById('image-preview').src = '';
        }

        let monitorInterval = null;
        let monitorActive = false;

        function toggleMonitor() {
            const btn = document.getElementById('monitor-toggle-btn-header');
            const img = document.getElementById('monitor-screen');
            const loading = document.getElementById('monitor-loading');
            
            monitorActive = !monitorActive;
            if (monitorActive) {
                if (btn) btn.style.color = 'var(--accent-color)';
                updateMonitorVisibility();
                loading.style.display = 'block';
                
                // Immediately refresh once
                refreshMonitor();
                
                // Set interval to poll every 1.5s
                monitorInterval = setInterval(refreshMonitor, 1500);
            } else {
                if (btn) btn.style.color = '#8b949e';
                updateMonitorVisibility();
                img.src = '';
                
                if (monitorInterval) {
                    clearInterval(monitorInterval);
                    monitorInterval = null;
                }
            }
        }

        function refreshMonitor() {
            if (!monitorActive) return;
            const img = document.getElementById('monitor-screen');
            const loading = document.getElementById('monitor-loading');
            
            let targetVal = activeTarget;
            if (targetVal === 'assistant') {
                targetVal = 'agy'; // default fallback for capture if in assistant channel
            }
            
            const tempImg = new Image();
            tempImg.src = `/screenshot?target=${targetVal}&t=${Date.now()}`;
            tempImg.onload = () => {
                img.src = tempImg.src;
                loading.style.display = 'none';
            };
            tempImg.onerror = () => {
                loading.style.display = 'none';
            };
        }

        function sendMessage() {
            const text = msgInput.value.trim();
            if (!text && !selectedImage) return;
            msgInput.value = '';
            
            if (audioContext && audioContext.state === 'suspended') {
                audioContext.resume();
            }
            
            const payload = {
                message: text,
                target: activeTarget,
                session_id: activeSessionId
            };
            if (selectedImage) {
                payload.image = selectedImage.url;
                payload.image_path = selectedImage.path;
            }
            
            clearSelectedImage();
            
            fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(() => {
                loadHistory();
                if (monitorActive) {
                    setTimeout(refreshMonitor, 500);
                    setTimeout(refreshMonitor, 1500);
                }
            });
        }

        const confirmModal = document.getElementById('confirm-modal');

        function clearHistory() {
            confirmModal.classList.add('active');
        }

        function closeConfirmModal() {
            confirmModal.classList.remove('active');
        }

        function triggerClearHistory() {
            closeConfirmModal();
            fetch('/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).then(() => {
                loadHistory();
            });
        }

        // ==================== 设置面板 ====================
        let _cropConfig = {};

        function openSettingsPanel() {
            document.getElementById('settings-panel').style.display = 'block';
            loadCropConfig();
            // 首次打开时绑定框选监听器
            if (typeof attachSelectorListeners === 'function') {
                attachSelectorListeners();
            }
            const btn = document.getElementById('settings-btn-header');
            if (btn) btn.style.color = 'var(--accent-color)';
        }

        function closeSettingsPanel() {
            document.getElementById('settings-panel').style.display = 'none';
            const btn = document.getElementById('settings-btn-header');
            if (btn) btn.style.color = 'var(--text-color)';
        }

        function loadCropConfig() {
            fetch('/screenshot/crop?t=' + Date.now())
                .then(r => r.json())
                .then(data => {
                    _cropConfig = data || {};
                    loadCropForm();
                })
                .catch(err => showToast('加载配置失败: ' + err));
        }

        function loadCropForm() {
            const target = document.getElementById('crop-target-select').value;
            const cfg = _cropConfig[target] || {left:0,right:0,top:0,bottom:0};
            const form = document.getElementById('crop-form');
            const fields = [
                {key:'left',   label:'�?(left)',   hint:'IDE 左侧'},
                {key:'right',  label:'�?(right)',  hint:'IDE 右侧'},
                {key:'top',    label:'�?(top)',    hint:'IDE 顶部'},
                {key:'bottom', label:'�?(bottom)', hint:'IDE 底部'},
            ];
            form.innerHTML = fields.map(f => {
                const v = cfg[f.key] || 0;
                return '<label style="color:#8b949e;">' + f.label + '</label>' +
                    '<input type="range" id="crop-' + f.key + '" min="0" max="600" value="' + v + '" oninput="updateCropLabel(&quot;' + f.key + '&quot;)">' +
                    '<span id="crop-' + f.key + '-val" style="text-align:right; color:var(--accent-color);">' + v + '</span>';
            }).join('');
        }

        function updateCropLabel(key) {
            const v = document.getElementById('crop-' + key).value;
            document.getElementById('crop-' + key + '-val').textContent = v;
        }

        function saveCropConfig() {
            const target = document.getElementById('crop-target-select').value;
            const cfg = {
                left:   parseInt(document.getElementById('crop-left').value),
                right:  parseInt(document.getElementById('crop-right').value),
                top:    parseInt(document.getElementById('crop-top').value),
                bottom: parseInt(document.getElementById('crop-bottom').value),
            };
            fetch('/screenshot/crop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: target, ...cfg })
            })
            .then(r => r.json())
            .then(data => {
                _cropConfig[target] = cfg;
                showToast('�?已保存：' + JSON.stringify(data.config));
            })
            .catch(err => showToast('保存失败: ' + err));
        }

        function resetCropConfig() {
            const target = document.getElementById('crop-target-select').value;
            const defaults = {
                trae: {left:300,right:350,top:30,bottom:35},
                agy:  {left:0,right:0,top:30,bottom:100},
                oc:   {left:0,right:0,top:0,bottom:0},
                mimo: {left:0,right:0,top:0,bottom:0},
            };
            const cfg = defaults[target] || {left:0,right:0,top:0,bottom:0};
            fetch('/screenshot/crop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: target, ...cfg })
            })
            .then(r => r.json())
            .then(() => {
                _cropConfig[target] = cfg;
                loadCropForm();
                showToast('已恢复默�?);
            });
        }

        function testCroppedShot() {
            const target = document.getElementById('crop-target-select').value;
            const url = '/screenshot?target=' + target + '&t=' + Date.now();
            document.getElementById('crop-preview').innerHTML =
                '<img src="' + url + '" style="max-width:100%; max-height:400px; border:1px solid var(--border-color); border-radius:8px;" onload="showToast(&quot;截图已更�?quot;)">';
        }

        // ==================== 框选模�?====================
        let _selState = {startX:0, startY:0, endX:0, endY:0, dragging:false, imgW:0, imgH:0};

        function openSelectorPanel() {
            const target = document.getElementById('crop-target-select').value;
            document.getElementById('selector-panel').style.display = 'block';
            loadSelectorImage();
        }

        function closeSelectorPanel() {
            document.getElementById('selector-panel').style.display = 'none';
        }

        function loadSelectorImage() {
            const target = document.getElementById('crop-target-select').value;
            const img = document.getElementById('selector-img');
            document.getElementById('selector-box').style.display = 'none';
            img.onload = function() {
                _selState.imgW = img.naturalWidth;
                _selState.imgH = img.naturalHeight;
                // 如果已有 crop 配置，预填选区
                const cfg = _cropConfig[target] || {};
                if (cfg.left || cfg.right || cfg.top || cfg.bottom) {
                    const x1 = cfg.left || 0;
                    const y1 = cfg.top || 0;
                    const x2 = _selState.imgW - (cfg.right || 0);
                    const y2 = _selState.imgH - (cfg.bottom || 0);
                    if (x2 > x1 && y2 > y1) {
                        showSelectorBox(x1, y1, x2, y2);
                    }
                }
                showToast('已加�?' + _selState.imgW + 'x' + _selState.imgH);
            };
            img.src = '/screenshot/full?target=' + target + '&t=' + Date.now();
        }

        function attachSelectorListeners() {
            const container = document.getElementById('selector-container');
            const box = document.getElementById('selector-box');
            const img = document.getElementById('selector-img');

            function getRelPos(e) {
                const rect = img.getBoundingClientRect();
                const clientX = e.touches ? e.touches[0].clientX : e.clientX;
                const clientY = e.touches ? e.touches[0].clientY : e.clientY;
                const scaleX = img.naturalWidth / rect.width;
                const scaleY = img.naturalHeight / rect.height;
                let x = (clientX - rect.left) * scaleX;
                let y = (clientY - rect.top) * scaleY;
                x = Math.max(0, Math.min(x, img.naturalWidth));
                y = Math.max(0, Math.min(y, img.naturalHeight));
                return {x, y};
            }

            function onDown(e) {
                e.preventDefault();
                const p = getRelPos(e);
                _selState.startX = p.x; _selState.startY = p.y;
                _selState.endX = p.x; _selState.endY = p.y;
                _selState.dragging = true;
                showSelectorBox(p.x, p.y, p.x, p.y);
            }
            function onMove(e) {
                if (!_selState.dragging) return;
                e.preventDefault();
                const p = getRelPos(e);
                _selState.endX = p.x; _selState.endY = p.y;
                showSelectorBox(_selState.startX, _selState.startY, p.x, p.y);
            }
            function onUp(e) {
                if (!_selState.dragging) return;
                e.preventDefault();
                _selState.dragging = false;
                const p = getRelPos(e);
                _selState.endX = p.x; _selState.endY = p.y;
                showSelectorBox(_selState.startX, _selState.startY, p.x, p.y);
            }

            img.ontouchstart = onDown;
            img.ontouchmove = onMove;
            img.ontouchend = onUp;
            img.onmousedown = onDown;
            img.onmousemove = onMove;
            img.onmouseup = onUp;
            img.onmouseleave = onUp;
        }

        function showSelectorBox(x1, y1, x2, y2) {
            const img = document.getElementById('selector-img');
            const box = document.getElementById('selector-box');
            const rect = img.getBoundingClientRect();
            const containerRect = img.parentElement.getBoundingClientRect();
            const scaleX = rect.width / img.naturalWidth;
            const scaleY = rect.height / img.naturalHeight;
            const left = (Math.min(x1, x2) * scaleX);
            const top = (Math.min(y1, y2) * scaleY);
            const width = Math.abs(x2 - x1) * scaleX;
            const height = Math.abs(y2 - y1) * scaleY;
            box.style.left = left + 'px';
            box.style.top = top + 'px';
            box.style.width = width + 'px';
            box.style.height = height + 'px';
            box.style.display = 'block';
        }

        function applySelectorAndClose() {
            const target = document.getElementById('crop-target-select').value;
            const x1 = Math.min(_selState.startX, _selState.endX);
            const y1 = Math.min(_selState.startY, _selState.endY);
            const x2 = Math.max(_selState.startX, _selState.endX);
            const y2 = Math.max(_selState.startY, _selState.endY);
            if (x2 - x1 < 20 || y2 - y1 < 20) {
                showToast('选区太小，请重新框�?);
                return;
            }
            const cfg = {
                left: Math.round(x1),
                right: Math.round(_selState.imgW - x2),
                top: Math.round(y1),
                bottom: Math.round(_selState.imgH - y2),
            };
            fetch('/screenshot/crop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: target, ...cfg })
            })
            .then(r => r.json())
            .then(data => {
                _cropConfig[target] = cfg;
                showToast('�?已保存：' + JSON.stringify(data.config));
                closeSelectorPanel();
                loadCropForm();
            })
            .catch(err => showToast('保存失败: ' + err));
        }

        // ==================== 剪贴板面�?====================
        let _clipboardCache = [];

        function openClipboardPanel() {
            document.getElementById('clipboard-panel').style.display = 'block';
            document.getElementById('clipboard-search').value = '';
            refreshClipboardPanel();
            const btn = document.getElementById('clipboard-btn-header');
            if (btn) btn.style.color = 'var(--accent-color)';
        }

        function closeClipboardPanel() {
            document.getElementById('clipboard-panel').style.display = 'none';
            const btn = document.getElementById('clipboard-btn-header');
            if (btn) btn.style.color = '#8b949e';
        }

        function refreshClipboardPanel() {
            fetch('/clipboard?limit=200&t=' + Date.now())
                .then(r => r.json())
                .then(data => {
                    _clipboardCache = data || [];
                    renderClipboardList(_clipboardCache);
                })
                .catch(err => {
                    document.getElementById('clipboard-list').innerHTML =
                        '<div style="text-align:center; color:#f85149; padding:20px;">加载失败�? + err + '</div>';
                });
        }

        function searchClipboard(q) {
            if (!q) {
                renderClipboardList(_clipboardCache);
                return;
            }
            const lower = q.toLowerCase();
            const filtered = _clipboardCache.filter(it => (it.text || '').toLowerCase().includes(lower));
            renderClipboardList(filtered);
        }

        function renderClipboardList(items) {
            const list = document.getElementById('clipboard-list');
            if (!items || items.length === 0) {
                list.innerHTML = '<div style="text-align:center; color:#8b949e; padding:40px 20px;">📭 剪贴板历史为�?br><br><span style="font-size:0.85rem;">复制一些内容后会出现在这里</span></div>';
                return;
            }
            const html = items.slice().reverse().map((it, idx) => {
                const text = it.text || '';
                const preview = text.length > 500 ? text.substring(0, 500) + '...' : text;
                const sourceLabel = it.source === 'mobile' ? '📱 手动' : '🖥�?自动';
                return `
                    <div class="clipboard-item" style="background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 0.75rem; color: #8b949e;">
                            <span>${sourceLabel} · ${it.time || ''}</span>
                            <div style="display: flex; gap: 6px;">
                                <button onclick="copyClipboardItem('${escapeHtml(text).replace(/'/g, "\'")}')" style="background: #21262d; border: 1px solid var(--border-color); color: var(--accent-color); padding: 3px 10px; border-radius: 10px; cursor: pointer; font-size: 0.75rem;">📋 复制</button>
                                <button onclick="useClipboardAsInput('${escapeHtml(text).replace(/'/g, "\'")}')" style="background: #21262d; border: 1px solid var(--border-color); color: #58a6ff; padding: 3px 10px; border-radius: 10px; cursor: pointer; font-size: 0.75rem;">✉️ 发�?/button>
                            </div>
                        </div>
                        <pre style="margin: 0; color: var(--text-color); font-size: 0.85rem; white-space: pre-wrap; word-break: break-all; font-family: inherit;">${escapeHtml(preview)}</pre>
                    </div>
                `;
            }).join('');
            list.innerHTML = html;
        }

        function escapeHtml(s) {
            return String(s).replace(/[&<>"']/g, c => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[c]));
        }

        function copyClipboardItem(text) {
            fetch('/clipboard/append', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, source: 'mobile' })
            });
            msgInput.value = text;
            msgInput.focus();
            showToast('已填入输入框（点击发送）');
        }

        function useClipboardAsInput(text) {
            msgInput.value = text;
            closeClipboardPanel();
            msgInput.focus();
            showToast('已填入输入框，可点击发�?);
        }

        function clearClipboardPanel() {
            if (!confirm('确定清空所有剪贴板历史�?)) return;
            fetch('/clipboard/clear', { method: 'POST' })
                .then(() => {
                    _clipboardCache = [];
                    renderClipboardList([]);
                    showToast('已清�?);
                });
        }

        function showToast(msg) {
            let toast = document.getElementById('toast-msg');
            if (!toast) {
                toast = document.createElement('div');
                toast.id = 'toast-msg';
                toast.style.cssText = 'position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.85); color: white; padding: 10px 20px; border-radius: 20px; z-index: 10000; font-size: 0.9rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3);';
                document.body.appendChild(toast);
            }
            toast.textContent = msg;
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 2000);
        }

        sendBtn.addEventListener('click', sendMessage);
        msgInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        // Hide monitor container when focusing input field or when keyboard is visible to save vertical space
        const monitorContainer = document.getElementById('monitor-container');
        
        function updateMonitorVisibility() {
            if (!monitorContainer) return;
            
            let shouldHide = false;
            // 1. If input is active (focused)
            if (document.activeElement === msgInput) {
                shouldHide = true;
            }
            // 2. If visual viewport height is significantly reduced (soft keyboard shown)
            if (window.visualViewport && (window.innerHeight - window.visualViewport.height > 80)) {
                shouldHide = true;
            }
            
            if (shouldHide) {
                monitorContainer.style.display = 'none';
            } else {
                if (monitorActive) {
                    monitorContainer.style.display = 'block';
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                } else {
                    monitorContainer.style.display = 'none';
                }
            }
        }

        msgInput.addEventListener('focus', updateMonitorVisibility);
        msgInput.addEventListener('blur', () => {
            // Delay slightly to prevent flickering when clicking other buttons
            setTimeout(updateMonitorVisibility, 150);
        });

        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', updateMonitorVisibility);
            window.visualViewport.addEventListener('scroll', updateMonitorVisibility);
        }

        setInterval(loadHistory, 1500);
        loadHistory();
    