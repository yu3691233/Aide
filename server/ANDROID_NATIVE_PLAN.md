# Android Native Plan

> 历史方案已精简。当前 Android 客户端以 `AideLink-app/` 为准。

## 当前方向

- 保持 Android App 作为移动控制入口。
- 设备发现、安装、启动、日志获取和验证优先调用 AideLink MCP。
- 不再把 Happy 作为当前客户端方案或依赖。

## 维护原则

- 新功能优先复用现有 App / Server 模块。
- 大屏幕或大 ViewModel 应逐步拆分，避免单文件过长。
- 过时方案放入历史文档，不继续误导当前开发。
