# Workspace Sandbox + File Upload 实施 Walkthrough

> 实施分支: `feature/workspace-sandbox`
> 计划文件: `C:\Users\z1950\.claude\plans\agent-rosy-lighthouse.md`

---

## 阶段 0: 切分支 + 项目约定

- 切到 `feature/workspace-sandbox` (不在 master 直接动)
- 工作纪律: 每步独立 commit,中文 subject,`feat(scope): 中文动词` 风格;每步 `pytest tests/` 验证零回归;不顺手优化无关代码
- 测试: 真实联调用商汤 (sensenova-6.7-flash-lite, 免费),不用 DeepSeek

---
