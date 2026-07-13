// AideLink 组件定位器 — Background Service Worker

console.log("[AideLink] background.js loaded");

// 点击图标打开侧边栏
try {
  const result = chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  if (result && result.then) {
    result.then(() => console.log("[AideLink] setPanelBehavior OK"))
          .catch(e => console.error("[AideLink] setPanelBehavior failed:", e));
  }
} catch (e) {
  console.error("[AideLink] setPanelBehavior exception:", e);
}

// Ctrl+Click 时保存数据并打开侧边栏
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "ELEMENT_COLLECTED") {
    chrome.storage.local.get("collected", (data) => {
      const list = data.collected || [];
      list.push(msg.data);
      chrome.storage.local.set({ collected: list });
    });
    if (sender.tab) {
      chrome.sidePanel.open({ tabId: sender.tab.id })
        .then(() => console.log("[AideLink] sidePanel opened"))
        .catch(e => console.error("[AideLink] sidePanel.open failed:", e));
    }
    sendResponse({ success: true });
  } else if (msg.type === "CLEAR_COLLECTED") {
    chrome.storage.local.set({ collected: [] });
    sendResponse({ success: true });
  }
  return true;
});
