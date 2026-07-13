# CLAUDE.md — 必读规则

## ⚠️ 多 IDE 协同（最重要）

**改代码前必须做**：
1. `git pull` — 拉取其他 IDE 的修改
2. 告诉用户你要改哪个文件
3. 改完立即 `git commit`

**禁止**：
- ❌ 不改别人正在改的文件
- ❌ 不删别人加的功能
- ❌ 不覆盖别人的 import

## 文件归属

| 归谁改 | 文件 |
|--------|------|
| MiMoCode | `server/*.py`, `**/data/**`, `**/di/**`, `AGENTS.md` |
| Trae | `**/ui/**`, `**/navigation/**` |
| 任何 IDE | 测试、文档 |

## 提交规范
```bash
git add <文件>
git commit -m "做了什么"
```
