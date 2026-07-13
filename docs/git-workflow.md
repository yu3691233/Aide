# AideLink Git 工作流

> 当前采用 `main` 单分支轮流协作，不再使用旧的按 IDE 分支长期并行方案。

## 原则

- 一次只让一个 IDE 做实质修改。
- 修改前确认是否与其他 IDE 的工作重叠。
- 对已有未提交改动先判断是否完整；能验证就验证，确认完整后应提交，不要长期留半成品。
- 大改动、删除、迁移或跨 Android + Server 修改前，先给简短方案。

## 基本流程

```powershell
git pull origin main
# 修改并验证
git status --short
git add <files>
git commit -m "描述改动"
git push origin main
```

## 冲突处理

不要强制覆盖。先保存当前修改，再手动合并并重新验证。
