# ⚠️ 必读：多 IDE 协同规则

## 改代码前
1. `git pull origin main` 拉取最新
2. 告诉用户你要改哪个文件
3. 改完立即 `git commit && git push`

## 工作方式
- 所有 IDE 都在 main 分支上工作
- 一次只有一个 IDE 改代码，其他 IDE 只做分析和计划
- 改完就 push，下一个 IDE pull 后再开始

## 禁止
- ❌ 不改别人正在改的文件
- ❌ 不删别人加的功能
- ❌ 不覆盖别人的 import
- ❌ 不用 dev-* 分支

## 文件归属（参考，非强制）
- MiMoCode: server/*.py, **/data/**, **/di/**
- Trae: **/ui/**, **/navigation/**

---
以下是原始消息桥接规则...
