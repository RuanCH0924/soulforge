# AGENTS.md

工作区协作规范与边界。

## 职责边界

- 本 Agent 只处理自己的 workspace
- 不修改其他 Agent 的文件，除非走同步流程
- 不触碰 `.credentials.md` / `.env`

## 协作规范

- 高价值结论写入 `memory/YYYY-MM-DD.md`
- 跨会话状态写 `MEMORY.md`
- 与老板的私人偏好相关的内容写入 `USER.md`，不写在这里

## 质量要求

- 交付前自查：是否留了 L4 痕迹（时间戳 / 版本号 / 修复叙述）
