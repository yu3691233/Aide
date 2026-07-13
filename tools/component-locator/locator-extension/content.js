(function () {
  "use strict";

  let hoveredEl = null;

  function getXPath(el) {
    if (!el) return "";
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === Node.ELEMENT_NODE) {
      let idx = 0;
      let sib = cur.previousSibling;
      while (sib) {
        if (sib.nodeType === Node.ELEMENT_NODE && sib.nodeName === cur.nodeName) idx++;
        sib = sib.previousSibling;
      }
      parts.unshift(`${cur.nodeName.toLowerCase()}[${idx + 1}]`);
      cur = cur.parentNode;
    }
    return "/" + parts.join("/");
  }

  function getCssSelector(el) {
    if (!el) return "";
    if (el.id) return `#${el.id}`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === Node.ELEMENT_NODE) {
      let sel = cur.nodeName.toLowerCase();
      if (cur.id) {
        sel = `#${cur.id}`;
        parts.unshift(sel);
        break;
      }
      if (cur.className && typeof cur.className === "string") {
        const cls = cur.className.trim().split(/\s+/).filter(Boolean).slice(0, 2).join(".");
        if (cls) sel += "." + cls;
      }
      parts.unshift(sel);
      cur = cur.parentElement;
    }
    return parts.join(" > ");
  }

  function collectInfo(el) {
    const rect = el.getBoundingClientRect();
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute("role") || "";
    const inputType = el.getAttribute("type") || "";
    const label = findLabel(el);
    const componentType = inferComponentType(tag, role, inputType, el);
    const componentName = label || componentType;
    return {
      tag,
      id: el.id || "",
      className: el.className && typeof el.className === "string" ? el.className : "",
      text: isSensitiveInput(el) ? "" : (el.textContent || "").trim().slice(0, 200),
      ariaLabel: el.getAttribute("aria-label") || "",
      role,
      inputType,
      componentType,
      componentName,
      location: findLocation(el),
      pageTitle: document.title || "",
      xpath: getXPath(el),
      cssSelector: getCssSelector(el),
      rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
      url: location.origin + location.pathname,
      timestamp: Date.now(),
    };
  }

  function isSensitiveInput(el) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    return el.matches("input, textarea") && ["password", "email", "tel"].includes(type);
  }

  function findLabel(el) {
    if (el.id) {
      const direct = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (direct && direct.textContent.trim()) return direct.textContent.trim().slice(0, 80);
    }
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const labelled = document.getElementById(labelledBy);
      if (labelled && labelled.textContent.trim()) return labelled.textContent.trim().slice(0, 80);
    }
    const aria = el.getAttribute("aria-label");
    if (aria) return aria.trim().slice(0, 80);
    const placeholder = el.getAttribute("placeholder");
    if (placeholder) return placeholder.trim().slice(0, 80);
    const wrappingLabel = el.closest("label");
    if (wrappingLabel && wrappingLabel.textContent.trim()) return wrappingLabel.textContent.trim().slice(0, 80);
    const ownText = (el.textContent || "").trim().replace(/\s+/g, " ");
    return ownText.length <= 80 ? ownText : "";
  }

  function inferComponentType(tag, role, inputType, el) {
    if (role === "tab") return "标签页";
    if (role === "dialog") return "对话框";
    if (tag === "textarea") return "多行输入框";
    if (tag === "select" || role === "combobox" || el.getAttribute("aria-haspopup") === "listbox") return "下拉框";
    if (tag === "button" || role === "button") return "按钮";
    if (tag === "input") {
      if (["checkbox", "radio"].includes(inputType)) return inputType === "checkbox" ? "复选框" : "单选按钮";
      return "输入框";
    }
    if (tag === "a") return "链接";
    if (tag === "img") return "图片";
    return "界面组件";
  }

  function findLocation(el) {
    const parts = [];
    const selectedTab = document.querySelector('[role="tab"][aria-selected="true"], .tab.active, .active-tab');
    if (selectedTab) {
      const tabText = findLabel(selectedTab);
      if (tabText) parts.push(`${tabText} Tab`);
    }
    const container = el.closest('[role="dialog"], dialog, section, main, .card, .panel, .modal');
    if (container) {
      const heading = container.querySelector('h1, h2, h3, [role="heading"], .card-title, .modal-title');
      const headingText = heading ? (heading.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80) : "";
      if (headingText && !parts.includes(headingText)) parts.push(headingText);
    }
    return parts.join(" · ");
  }

  function flash(el) {
    el.classList.add("aidelink-collected");
    setTimeout(() => el.classList.remove("aidelink-collected"), 400);
  }

  // Ctrl+Click 收集元素
  document.addEventListener("click", function (e) {
    if (!e.ctrlKey) return;
    e.preventDefault();
    e.stopPropagation();
    const info = collectInfo(e.target);
    flash(e.target);
    chrome.runtime.sendMessage({ type: "ELEMENT_COLLECTED", data: info });
  }, true);

  // Ctrl 按住时悬停高亮
  document.addEventListener("keydown", function (e) {
    if (e.key === "Control") {
      document.body.style.cursor = "crosshair";
    }
  });

  document.addEventListener("keyup", function (e) {
    if (e.key === "Control") {
      document.body.style.cursor = "";
      if (hoveredEl) {
        hoveredEl.classList.remove("aidelink-locator-highlight");
        hoveredEl = null;
      }
    }
  });

  // 按住 Ctrl 时悬停高亮
  document.addEventListener("mouseover", function (e) {
    if (!e.ctrlKey) return;
    if (hoveredEl) hoveredEl.classList.remove("aidelink-locator-highlight");
    hoveredEl = e.target;
    hoveredEl.classList.add("aidelink-locator-highlight");
  });

  document.addEventListener("mouseout", function (e) {
    if (hoveredEl) {
      hoveredEl.classList.remove("aidelink-locator-highlight");
      hoveredEl = null;
    }
  });

  chrome.runtime.sendMessage({ type: "CONTENT_READY" });
})();
