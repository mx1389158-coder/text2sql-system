# 星云智家智能问数系统

这是一个按 P0–P5 分层实现的中文 Text2SQL 工程：自然语言问题经过意图/澄清、Schema
Linking、候选生成、SQL AST 安全检查、只读执行、有限修正后返回表格、解释和完整 trace。

按最新逐章节修订后的执行方案见 `docs/PROJECT_PLAN_V2.md`，最终勾选证据见
`docs/qa/revised_acceptance_matrix.md`。

## 最终验收结果

- 严格同预算 2×2（受治理 Schema、同一固定 300 条 Holdout、192 token）：E00 20.00%、
  E01 60.67%、E20 33.33%、E21 100.00% execution accuracy；该数字不代表开放场景通用准确率；
- E21 三快照 Test-Suite 为 300/300，安全集 120/120，歧义检测 80/80，澄清后执行 10/10；
- A40–A48 九组消融全部完成，浏览器验收 8/8，备份恢复演练通过；
- Langfuse Cloud 日本区鉴权、真实查询五阶段 trace 上报和 API 读回验证通过；
- 完整结论见 `docs/experiments/final_report.md`，错误分类见
  `docs/experiments/badcase_report.md`，模型边界见
  `training/model_cards/qwen25-coder-1.5b-text2sql-v5.md`。

## 已实现

- 23 张 PostgreSQL 业务表、固定种子、只读角色和超时配置；
- 版本化 Schema/业务口径目录、混合检索、低置信度扩展、外键补全和 token 预算 M-Schema；
- 离线规则提供方及 OpenAI-compatible 本地模型接口（Ollama/vLLM 等）；
- 1–3 候选、轻量语义评分、SQLGlot 单语句白名单、用户作用域权限和强制 LIMIT；
- PostgreSQL 只读事务与 SQLite 本地演示执行器、错误分类和最多两轮修正；
- FastAPI 查询/澄清/实时 SSE/反馈/持久化评测/模型/Schema API；
- Vue 3 问数、图表、Schema 关系图、2×2 实验和 Badcase 界面；
- 4,100/620/300 训练、开发、冻结盲测语料（含纠正型 Badcase 与全表覆盖样本），另有 300 条未见业务族 holdout、100 安全集、80 歧义集及版本化实验 manifests；
- 单元、集成、E2E 与安全攻击测试。

v1.1.1 安全收尾进一步保证：查询记录在 SQLite 和 API 层按 scope 强制隔离，跨 scope
详情访问统一返回 404，查询列表自动按当前 scope 过滤；未知或缺失权限配置 deny-all。
结果缓存键包含 scope、权限策略、strategy、模型、Prompt、Schema、Few-shot、语义目录和
运行参数版本，缓存值不复用旧请求的 session、trace、调用量、token 和耗时元数据。

v1.1.2 增加生产启动门禁：`TEXT2SQL_ENV=production` 时必须配置
`TEXT2SQL_API_KEY` 或非空 `TEXT2SQL_API_KEYS_JSON`，否则 API 在启动阶段失败。Compose 已透传
两种鉴权配置；Web 顶部可输入并验证 API Key，值仅保存在当前浏览器 sessionStorage。

训练产物保留在本地且不提交大文件；v5 已通过适配器校验、冻结集评测和质量门禁，按受治理
Schema 与优化运行时范围注册。模型注册不代表任意 Schema 的通用准确率。

## 1. 本地快速演示（无需 Docker/GPU）

要求 Python 3.11、Node 22+。

本地无鉴权演示应使用 `TEXT2SQL_ENV=development`。生产环境不可通过清空密钥回退到匿名
`default` scope；可运行 `python scripts/ensure_api_auth.py --env-file .env` 安全生成单 Key，
脚本不会打印密钥或覆盖已有单/多 Key 配置。

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

也可以运行 `python scripts/generate_deployment_secrets.py` 生成不会打印到终端的随机数据库
密码和独立虚拟机密码；脚本默认拒绝覆盖已有文件。

默认宿主机端口为 Web 15173、API 18000、PostgreSQL 15432、Redis 16379，避免和其他
项目的常见默认端口冲突。API 使用 `text2sql_readonly` 账户。
首次初始化后若修改迁移，请创建新编号迁移；开发期要重建空卷时再显式删除卷。

Langfuse Cloud 使用官方环境变量 `LANGFUSE_BASE_URL`、`LANGFUSE_PUBLIC_KEY` 和
`LANGFUSE_SECRET_KEY`。真实凭据只写入被 Git 忽略的 `.env`，可运行
`python scripts/verify_langfuse_live.py` 验证鉴权、上报和读回。

按方案目标生成 5 万订单、3 万设备和 2 万工单的确定性数据：

```bash
python scripts/generate_business_data.py \
  --database-url postgresql://text2sql_admin:<password>@localhost:15432/text2sql \
  --customers 10000 --orders 50000 --devices 30000 --tickets 20000 --seed 42

python scripts/verify_postgres.py \
  --admin-url postgresql://text2sql_admin:<password>@localhost:15432/text2sql \
  --readonly-url postgresql://text2sql_readonly:<password>@localhost:15432/text2sql
```

也可以避免把密码放入命令行，直接生成脱敏验收报告：

```powershell
.\.conda\python.exe scripts\verify_postgres.py --env-file .env `
  --output docs\data_card\snapshot_validation_report.json
.\.conda\python.exe scripts\audit_dataset_governance.py
.\.conda\python.exe scripts\validate_experiment_matrix.py
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
- `GET /api/v1/queries`：只列出当前 API Key scope 拥有的查询记录；
- `POST /api/v1/feedback`：写入人工候选 Badcase，不自动训练；
- `POST /api/v1/evals/run`、`GET /api/v1/evals/{id}`：后台评测；
- `GET /api/v1/models`、`GET /api/v1/schema`。

OpenAPI 文档位于 `http://localhost:8000/docs`。

## 5. 数据与训练

```bash
python -m training.scripts.build_governed_corpus --database-url postgresql://text2sql_admin:<password>@localhost:15432/text2sql
python -m training.scripts.prepare_dataset --database-url postgresql://text2sql_readonly:<password>@localhost:15432/text2sql
python -m scripts.seal_evaluation_set training/datasets/raw/dev.jsonl data/evaluation/dev_v5.jsonl --database-url postgresql://text2sql_readonly:<password>@localhost:15432/text2sql
python -m scripts.seal_evaluation_set training/datasets/raw/holdout_v2.jsonl data/evaluation/holdout_v2.jsonl --database-url postgresql://text2sql_readonly:<password>@localhost:15432/text2sql
llamafactory-cli train training/configs/smoke_100.yaml
llamafactory-cli train training/configs/qwen25_coder_1_5b_qlora_v5.yaml
```

先完成 100 条 overfit smoke test，再开始完整训练。训练前确认 `bf16` 支持；异常时改用
`fp16`，并依次降低 cutoff、LoRA target 与并发。不要在 8GB 显存上承诺 7B 全参数训练。

如果宿主机不安装 Docker Desktop，可按 `infra/virtualbox/README.md` 创建独立的
`nebula-text2sql-docker` 虚拟机。脚本遇到同名虚拟机会退出，也不会修改其他虚拟机。

## 6. 评测与测试

```bash
pytest
text2sql-eval data/processed/smoke.jsonl --strategy optimized
python scripts/run_acceptance_evaluations.py --skip-resolution
python scripts/run_perturbed_test_suite.py experiments/reports/E21.json \
  --database-url postgresql://text2sql_admin:<password>@localhost:15432/text2sql
cd apps/web && npm run build
npm run qa:browser
```

冒烟数据只验证工程正确性。正式结论必须使用固定快照、冻结盲测集和
`experiments/manifests/E20.yaml`、`E21.yaml` 和 `experiments/ablations/v5/`，同时报告失败样本、调用预算、延迟与资源。

最终严格 2×2 使用同一个 300 条 `holdout_v2`：E00/E01 为基座模型，E20/E21 为 v5，
四组均使用 192 token 和每样本最多 5 次模型调用。固定快照结果与三快照
Test-Suite 分开记录，状态/日期和 FK 扰动全部在事务内执行并回滚。

`scripts/run_experiment.py` 默认启用样本级断点：每完成一个样本会原子写入
`experiments/checkpoints/<实验ID>.json`，中断后再次执行相同命令只处理缺失样本；若匹配的
正式报告已经存在，则直接复用。只有明确需要整组重跑时才使用 `--no-resume`。

专用 VirtualBox 数据库的备份恢复演练：

```bash
python scripts/backup_restore_drill.py --password-file E:/test2/virtualbox-password.txt
```

脚本只解析 `nebula-text2sql` Compose 项目的 PostgreSQL 容器，恢复到
`text2sql_restore_drill` 临时数据库，核对后删除临时库并保留备份文件。

虚拟机冷启动后可运行：

```bash
python scripts/start_virtualbox_stack.py --password-file E:/test2/virtualbox-password.txt
```

脚本只接受部署报告中记录的 `nebula-text2sql-docker`，校验 SSH 主机指纹后启动本项目
Compose 栈；当前 Compose 也配置了 `restart: unless-stopped`。

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

