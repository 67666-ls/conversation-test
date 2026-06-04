# AI 外呼评测系统 v2

> 面向真实外呼场景的多轮对话自动评测 Web App。
> 双 Agent 架构：被测 Agent + 12种用户人设模拟器，5维度自动评分，人工审核触发机制。

---

## 功能特性

- **用户系统**：注册/登录/JWT 认证，评测数据按用户隔离
- **12种用户人设**：配合/抗拒/好奇/被打断/急躁/困惑/愤怒/老年/熟练/心不在焉/挑剔/新手
- **5维度评分**：约束遵循 · 流程覆盖 · 长度合规 · 语气自然 · 任务完成
- **实时进度**：WebSocket 实时推送评测进度
- **人工审核队列**：分数模糊区间/维度分歧/边界违规自动触发
- **对话回放**：逐轮查看 Agent 与模拟用户的对话内容
- **暗色/亮色模式**

---

## 目录结构

```
├── backend/
│   ├── app/
│   │   ├── config.py          # 配置（.env 读取）
│   │   ├── database.py        # SQLAlchemy + SQLite
│   │   ├── models/            # ORM 模型（User/EvalTask/EvalSession）
│   │   ├── routers/           # API 路由（auth/tasks + WebSocket）
│   │   ├── schemas/           # Pydantic 请求/响应模型
│   │   └── services/          # 业务逻辑（JWT/评测服务）
│   ├── main.py                # 启动入口
│   └── requirements.txt
├── code/                      # 原有核心引擎（复用）
│   ├── user_simulator.py      # 12人设模拟器
│   ├── evaluator.py           # 5维度评测引擎
│   ├── llm_client.py          # DeepSeek/OpenAI 兼容客户端
│   └── report_generator.py
├── frontend/
│   └── index.html             # 单文件 SPA（Alpine.js + Tailwind CDN）
└── data/                      # 数据文件（.gitignore 中不提交 .db）
```

---

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，必须修改 SECRET_KEY
```

### 3. 启动后端

```bash
cd backend
python main.py
# 或
uvicorn app:app --reload --port 8000
```

### 4. 打开前端

用浏览器直接打开 `frontend/index.html`，或用任意静态文件服务器：

```bash
# 方式一：Python
cd frontend && python -m http.server 3000
# 方式二：Node.js npx
npx serve frontend
```

访问 `http://localhost:3000` 即可。

---

## API 文档

启动后访问 `http://localhost:8000/docs` 查看完整 Swagger 文档。

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/tasks` | 创建评测任务（后台异步执行） |
| GET  | `/api/tasks` | 任务列表 |
| GET  | `/api/tasks/{id}/sessions` | 获取评测结果 |
| GET  | `/api/tasks/{id}/report` | 汇总报告 |
| WS   | `/api/tasks/{id}/ws` | 实时进度推送 |

---

## 技术架构

```
前端（Alpine.js + Tailwind CSS）
    ↕ REST API + WebSocket
后端（FastAPI + SQLAlchemy）
    ↕ 复用引擎
评测核心（user_simulator + evaluator + llm_client）
    ↕ API 调用
DeepSeek / OpenAI 兼容 LLM
```

---

## License

MIT
