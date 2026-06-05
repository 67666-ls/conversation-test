# Conversation-Test — AI外呼智能评测与优化平台

> 美团AI Hackathon 命题二作品 | 双Agent架构 + 12种用户人设 + 5维自动评分

## 项目简介

基于大语言模型的双Agent AI外呼评测系统。**主Agent** 模拟外呼客服执行营销任务，**用户模拟器Agent** 支持12种人设自动生成真实对话场景，**评测引擎** 从5个维度自动打分并输出改进建议，辅以人工审核队列实现"机器初筛+人工复核"双保险。

## 核心功能

| 模块 | 说明 |
|------|------|
| **双Agent对话引擎** | 主Agent执行外呼任务 + 用户模拟器扮演12种人设自动对话 |
| **5维自动评分** | 任务完成度(35%) / 沟通质量(25%) / 合规性(20%) / 效率(10%) / 体验(10%) |
| **人工审核队列** | 低分/违规会话自动标记，支持通过/驳回/改分+备注 |
| **用户系统** | 注册/登录 + 管理员后台（任务管理/批量操作） |
| **对话回放** | 逐轮对话展示 + 维度打分依据解释 |
| **模拟评测** | 离线脚本 `scripts/run_mock_eval.py`，不依赖API即可验证系统 |

## 技术栈

```
后端：FastAPI + SQLite + SQLAlchemy + WebSocket
前端：Alpine.js SPA（单文件HTML，无需打包）
AI：  DeepSeek API（支持agent_fn / chat双接口）
部署：GitHub Pages（前端）+ Railway/Render（后端）
```

## 目录结构

```
conversation-test/
├── backend/
│   ├── main.py              # 启动入口（端口8088）
│   ├── app/
│   │   ├── services/
│   │   │   ├── evaluator.py      # 评测引擎（5维评分+详释）
│   │   │   ├── user_simulator.py # 12种用户人设模拟器
│   │   │   ├── eval_service.py   # 评测流程编排
│   │   │   └── auth.py           # 注册/登录（bcrypt）
│   │   ├── routers/
│   │   │   └── tasks.py          # API路由（评测/审核/管理）
│   │   ├── models/
│   │   │   └── user.py           # 数据模型
│   │   └── schemas/              # Pydantic校验
│   ├── scripts/
│   │   └── run_mock_eval.py      # 离线模拟评测脚本
│   └── .env.example              # 环境变量模板
├── frontend/
│   └── index.html                # Alpine.js SPA前端
├── reports/
│   └── mock_eval_report.md       # 24条模拟对话评测报告
└── data/                         # 指令模板 + 测试数据
```

## 快速开始

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 DeepSeek API Key

# 3. 启动服务
python main.py
# 访问 http://localhost:8088
```

## 12种用户人设

| 基础人设 | 进阶人设 |
|----------|----------|
| 配合型 | 急躁型 / 困惑型 |
| 抗拒型 | 愤怒型 / 挑剔型 |
| 好奇型 | 老年型 / 新手型 |
| 被中途打断型 | 熟练型 / 心不在焉型 |

## 评测结果验证

使用 `scripts/run_mock_eval.py` 对 12人设 × 2场景 = 24条模拟对话离线评测：

| 指标 | 数值 |
|------|------|
| 平均总分 | **73.2分** |
| 等级分布 | A:0 / B:19 / C:5 |
| 触发审核率 | 37.5% |
| 最优人设 | 配合型、熟练型 |
| 最差人设 | 抗拒型、愤怒型 |

完整报告：[reports/mock_eval_report.md](reports/mock_eval_report.md)

## 作品链接

- **GitHub**：https://github.com/67666-ls/conversation-test
- **模拟评测报告**：[reports/mock_eval_report.md](reports/mock_eval_report.md)

## 团队

| 成员 | 分工 |
|------|------|
| 刘师岐（队长） | 系统架构、后端开发、评测引擎、LLM集成、项目管理 |
| 高鑫 | 前端交互设计、12种用户人设模拟器、场景设计、测试验证 |

## License

MIT
