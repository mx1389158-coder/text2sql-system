# 星云智家智能问数系统

这是一个按 P0–P5 分层实现的中文 Text2SQL 工程：自然语言问题经过意图/澄清、Schema
Linking、候选生成、SQL AST 安全检查、只读执行、有限修正后返回表格、解释和完整 trace。

## 已实现

- 23 张 PostgreSQL 业务表、固定种子、只读角色和超时配置；
- 版本化 Schema/业务口径目录、混合检索、低置信度扩展、外键补全和 token 预算 M-Schema；
- 离线规则提供方及 OpenAI-compatible 本地模型接口（Ollama/vLLM 等）；
- 1–3 候选、轻量语义评分、SQLGlot 单语句白名单、用户作用域权限和强制 LIMIT；
- PostgreSQL 只读事务与 SQLite 本地演示执行器、错误分类和最多两轮修正；
- FastAPI 查询/澄清/实时 SSE/反馈/持久化评测/模型/Schema API；
- Vue 3 问数、图表、Schema 关系图、2×2 实验和 Badcase 界面；
- 2,500/300/300 语料、100 安全集、80 歧义集、QLoRA 配置和 E00–E11 manifests；
- 单元、集成、E2E 与安全攻击测试。

真实 QLoRA adapter、训练曲线和实验分数不在仓库中预造。运行训练与冻结盲测后，再把
模型注册状态从 `not_trained` 更新为 `validated`。

## 1. 本地快速演示（无需 Docker/GPU）

要求 Python 3.11、Node 22+。

```bash
conda create -p .conda python=3.11 pip -y
conda activate ./.conda
pip install -e ".[dev,eval]"
python scripts/bootstrap_demo.py
uvicorn apps.api.app.main:app --reload
```

另开终端：

```bash
cd apps/web
npm install
npm run dev
```

打开 `http://localhost:5173`。默认使用 SQLite 固定快照与离线规则生成器，适合验证系统闭
环，不代表模型能力。

## 2. PostgreSQL 全栈

复制 `.env.example` 为 `.env`，修改两个数据库密码，然后：

```bash
docker compose up --build -d
```

默认宿主机端口为 Web 15173、API 18000、PostgreSQL 15432、Redis 16379，避免和其他
项目的常见默认端口冲突。API 使用 `text2sql_readonly` 账户。
首次初始化后若修改迁移，请创建新编号迁移；开发期要重建空卷时再显式删除卷。

按方案目标生成 5 万订单、3 万设备和 2 万工单的确定性数据：

```bash
python scripts/generate_business_data.py \
  --database-url postgresql://text2sql_admin:<password>@localhost:5432/text2sql \
  --customers 10000 --orders 50000 --devices 30000 --tickets 20000 --seed 42
```

## 3. 连接本地模型

设置：

```dotenv
TEXT2SQL_LLM_PROVIDER=openai-compatible
TEXT2SQL_LLM_BASE_URL=http://localhost:11434/v1
TEXT2SQL_LLM_API_KEY=ollama
TEXT2SQL_LLM_MODEL=qwen2.5-coder:3b
```

提供方必须返回 JSON object：`intent`、`sql`、`used_tables`、`assumptions`。模型输出始终经过
SQLGuard；模型无法解除安全拒绝。

## 4. API

- `POST /api/v1/query`：提交问题；`?stream=true` 返回 SSE 事件；
- `POST /api/v1/query/{id}/clarify`：补充口径并恢复状态机；
- `GET /api/v1/query/{id}`：查询完整结果与 trace；
- `POST /api/v1/feedback`：写入人工候选 Badcase，不自动训练；
- `POST /api/v1/evals/run`、`GET /api/v1/evals/{id}`：后台评测；
- `GET /api/v1/models`、`GET /api/v1/schema`。

OpenAPI 文档位于 `http://localhost:8000/docs`。

## 5. 数据与训练

```bash
python -m training.scripts.build_governed_corpus --database-url postgresql://text2sql_admin:<password>@localhost:15432/text2sql
python -m training.scripts.prepare_dataset --database-url postgresql://text2sql_readonly:<password>@localhost:15432/text2sql
python -m scripts.seal_evaluation_set training/datasets/raw/dev.jsonl data/evaluation/dev_v1.jsonl --database-url postgresql://text2sql_readonly:<password>@localhost:15432/text2sql
python -m scripts.seal_evaluation_set training/datasets/raw/blind.jsonl data/evaluation/blind_v1.jsonl --database-url postgresql://text2sql_readonly:<password>@localhost:15432/text2sql
llamafactory-cli train training/configs/smoke_100.yaml
llamafactory-cli train training/configs/qwen25_coder_1_5b_qlora.yaml
```

先完成 100 条 overfit smoke test，再开始完整训练。训练前确认 `bf16` 支持；异常时改用
`fp16`，并依次降低 cutoff、LoRA target 与并发。不要在 8GB 显存上承诺 7B 全参数训练。

如果宿主机不安装 Docker Desktop，可按 `infra/virtualbox/README.md` 创建独立的
`nebula-text2sql-docker` 虚拟机。脚本遇到同名虚拟机会退出，也不会修改其他虚拟机。

## 6. 评测与测试

```bash
pytest
text2sql-eval data/processed/smoke.jsonl --strategy optimized
cd apps/web && npm run build
```

冒烟数据只验证工程正确性。正式结论必须使用固定快照、冻结盲测集和
`experiments/manifests/E00.yaml` 至 `E11.yaml`，同时报告失败样本、调用预算、延迟与资源。

## 目录

```text
apps/api          FastAPI 与状态机编排
apps/web          Vue 3 工作台
packages          Schema、生成、执行、评测核心包
infra             PostgreSQL 迁移与基础设施
training          数据、QLoRA 配置和模型注册
experiments       2×2 manifests、预测与报告
tests             unit / integration / e2e / security
docs              ADR、数据卡、模型卡、实验协议和威胁模型
```

