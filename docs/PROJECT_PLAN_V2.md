# 项目二：智能问数 Text2SQL 技术方案 v2（执行版）

本文件是原 16 页方案的增量修订，不删除已经完成的数据、模型或实验。优先级定义为：
P0 是可靠闭环和可验收证据，P1 是准确率与实验增强，P2 是展示增强，P3 是后续研究。

## 第 1 章：实验平台与开发约束

- 保留独立 Python 3.11 环境、8GB 级显存预算和 4bit QLoRA。
- Windows 宿主机承担 CUDA 训练，独立 `nebula-text2sql-docker` VM 承担 PostgreSQL、API、Web；训练和推理/服务配置分离。
- `environment.yml`、`requirements-lock.txt`、Web lock 和 Compose 固定依赖。
- `training/scripts/preflight.py` 实测 CUDA、compute capability、BF16、bitsandbytes NF4 算子、磁盘、依赖版本、数据规模和基线证据。
- `training/scripts/resume_training.py` 只从包含 trainer/optimizer/scheduler 状态的完整 checkpoint 恢复；默认 dry-run，必须显式 `--execute`。
- 当前证据：`training/preflight-v3-report.json` 全部通过，恢复点为 v5 `checkpoint-257`，未触发重训。

## 第 2 章：业务目标与核心贡献

系统闭环为中文问题 → 意图/澄清 → Schema Linking → 结构化 SQL → AST/权限检查 →
只读执行 → 表格/解释/trace。四类 P0 验收场景固定为：

1. 单表查询/统计；
2. 多表 JOIN；
3. CTE、窗口函数或复杂时间窗口；
4. 业务口径澄清及状态恢复。

机器可读用例位于 `data/evaluation/product_acceptance_v2.jsonl`，当前 4/4 通过，报告为
`docs/qa/product_acceptance_v2.json`。

## 第 3 章：数据库、数据集与业务口径

- 首轮允许 10–12 表、数百条样本，但已有成果不回退：当前 23 表、4,100 train、620 dev、300 blind，另有 300 条未见模板族 Holdout。
- 数据生成器为 `scripts/generate_business_data.py`；快照验证为 `scripts/verify_postgres.py`。
- 当前 PostgreSQL 快照达到 50,003 orders、150,003 order_items、30,002 devices、100,001 upgrades、20,003 tickets、100,001 events。
- 32 条外键全部无孤儿数据；只读写拒绝、50ms 超时、超时后连接恢复、合法空结果均实测通过，见 `docs/data_card/snapshot_validation_report.json`。
- split 必须按 ID、规范化问题和 `template_group` 隔离，并按业务语义模板、关联表组合、难度输出分层统计。审计报告显示跨 split 泄漏为 0，见 `docs/data_card/dataset_governance_report.json`。
- 业务指标使用 `key@version` 的语义目录，说明见 `docs/data_card/business_metrics_v1.md`；重复报修率明确观察窗口、判定窗口、分子和分母。

## 第 4 章：总体架构与状态机

- 查询状态：`running`、`clarification_required`、`completed`、`rejected`、`failed`。
- 意图状态：`QUERY`、`META`、`CLARIFY`、`REJECT`。
- 结构化失败码覆盖请求拒绝、模型响应、语义不匹配、安全拒绝、语法、字段、类型、超时、权限、连接和空结果。
- 在线预算由候选数、最多两轮修复、模型 token、数据库 statement/lock timeout、返回行数、并发和速率共同约束。
- 澄清沿原 `query_id` 恢复，但重新经过 Schema、生成/受治理编译、安全和执行阶段。

## 第 5 章：本地 QLoRA 微调

- 基座：`Qwen/Qwen2.5-Coder-1.5B-Instruct`，固定 revision
  `2e1fd397ee46e1388853d2af2c993145b0f1098a`，Apache-2.0。
- 实际配置：NF4、BF16、rank 16、alpha 32、batch 1、gradient accumulation 16、gradient checkpointing、cutoff 1024。
- 阶段 A：100 条 overfit smoke，验证 loss、保存、恢复和结构化输出，不报告泛化。
- 阶段 B：完整 QLoRA 与开发集分析，保留 v1 失败结论，不删除负结果。
- 阶段 C：固定 v5 配置，在冻结 Holdout 进行最终同预算比较，保存 adapter、曲线、预测、Badcase、显存和模型卡。
- 训练步骤和恢复命令见 `docs/training/qlora_runbook.md`。模型适配的目标是可复现和可解释，不预设一定提升全部语义指标。

## 第 6 章：Schema、Prompt、候选与修正

### 6.1 自适应 Schema

混合关键词/向量召回、表列 Recall@k、低置信度扩展、FK 图补全、M-Schema 和 token 预算均保留。
权限现在同时过滤表、字段和 M-Schema 样例值；`restricted_analyst` 示例禁止样例值和 `SELECT *`。

### 6.2 Prompt

结构化 JSON 协议、PostgreSQL 方言、安全规则、版本化业务口径和 Few-shot 保留。每条查询记录
`prompt_version=text2sql-system-v1.0.0`，生成 trace 同时记录版本和失败码。

### 6.3 候选

单候选是基础策略，三候选是优化策略。选择顺序以静态有效、可执行、语义分、Schema 覆盖为主，
非空结果仅为末级信号。CTE 派生字段不得被错误改写为物理 FK 连接。

### 6.4 修正

安全拒绝永不进入绕过流程；语法/字段/类型/受控超时可有限修正。报告同时记录修复新增正确数和改坏数。
执行成功、结果非空和语义正确是三个不同概念。

## 第 7 章：SQL 安全执行器

1. 输入层拒绝写请求、提示注入和权限绕过；
2. SQLGlot 遍历整棵 AST，拒绝多语句、嵌套写 CTE、DDL/DML、锁、系统 Schema、危险函数和越权表字段；
3. PostgreSQL 最小权限只读账号与限定 Schema/表是最终安全边界；
4. 只读事务、statement timeout、lock timeout、行数、并发和速率限制资源。

测试覆盖合法 SELECT/CTE、嵌套写操作、危险函数、表/字段/Schema 越权、超时恢复、大查询中断、空结果和误杀率。

## 第 8 章：代码结构

保持 `schema_linker`、`generation`、`execution`、`evaluation`、`training` 分离；新增或固化：

- `scripts/generate_business_data.py`：数据生成；
- `scripts/verify_postgres.py`：快照、外键和安全运行时校验；
- `scripts/audit_dataset_governance.py`：泄漏和分层审计；
- `training/model_registry.json`：模型 revision、许可证、状态和指标；
- `scripts/validate_experiment_matrix.py`：同预算 2×2 验证。

当前不引入额外 Agent 框架。

## 第 9 章：实施顺序

执行顺序调整为：数据库与安全 → 基础 SQL → 自动评测基线 → Schema Linking → QLoRA →
策略优化 → 前端与观测。现有 P0–P5 已完成；后续变更必须先通过安全和评测回归，再修改展示。

## 第 10 章：实验矩阵

计划角色仍使用 E00/E01/E10/E11。为保留历史，旧 v1 的 E10/E11 manifest 不覆盖；最终 v5 实际运行
编号 E20/E21 分别映射到计划角色 E10/E11。映射位于 `experiments/canonical_2x2.json`，验证报告
`docs/experiments/canonical_2x2_validation.json` 证明四格使用同一数据哈希、192 token 和最多 5 次模型调用。

| 计划角色 | 实际报告 | 模型/策略 | EX |
| --- | --- | --- | ---: |
| E00 | E00 | Base + Baseline | 20.00% |
| E01 | E01 | Base + Optimized | 60.67% |
| E10 | E20 | v5 + Baseline | 33.33% |
| E11 | E21 | v5 + Optimized | 100.00% |

高价值消融优先完整/自适应 Schema、0/有限反馈、无/有 FK 路径。当前已有 9 项系统消融；LoRA rank、cutoff 和多 seed 属后续研究，不阻塞首版。

## 第 11 章：指标、结果等价与 Badcase

- 自动报告 SQL Valid、EX、Test-Suite、表/列 Recall@k、Clarification、Safety TPR/FPR、Repair Gain、token、调用、p50/p95 和显存。
- 每个样本保存预测、状态、SQL、正确性、修复、时延和调用；盲测文件固定 SHA-256。
- EX 规则：浮点保留六位、NULL 只与 NULL 等价、重复行保留重数、默认忽略行序，仅显式 `order_sensitive` 时比较顺序；空结果是合法结果。
- Badcase 按 Schema、语义、SQL 构造、执行反馈和数据标注分类，不删除失败样本。

## 第 12 章：服务化与前端

P0/P1 四个重点界面均已具备：

1. 自然语言查询与澄清；
2. 生成 SQL、执行结果、解释和 trace；
3. Schema 表关系、候选表列和证据；
4. 2×2、消融、资源、错误分布和样本差异。

Badcase 页面属于额外 P2 能力。API、Web、PostgreSQL 运行在独立 VM，Langfuse Cloud 保存真实 trace。

## 第 13 章：持续迭代

v1 单库安全闭环、v2 Schema/澄清、v3 QLoRA、v4 候选/修正均已完成。跨数据库、多方言、
Harness 类自动优化和多 Agent 保持 P3，不纳入当前完成度声明。

## 第 14 章：技术答辩知识栈

项目证据覆盖 Python/FastAPI、SQL AST、PostgreSQL 权限与事务、Schema RAG、Prompt、QLoRA、
PyTorch/CUDA、数据泄漏、实验控制和 Docker。技术说明需能回答：

- `EXPLAIN`、索引选择、JOIN 顺序和 statement timeout 的关系；
- 只读事务、最小权限、连接回滚和隔离边界；
- NF4、LoRA rank/alpha、梯度累积/checkpointing 与显存估算；
- template_group 泄漏为何比问题文本去重更严格；
- 候选数、Schema token、模型调用和延迟/成本的复杂度；
- 如何从 lock、Git SHA、数据哈希、配置、checkpoint 和 seed 复现训练。

## 第 15 章：项目成果与交付验收

只引用机器日志：23 表和规模、4,100/620/300 数据、同预算 2×2、9 项消融、三快照 Test-Suite、
120/120 安全、80/80 歧义、10/10 澄清执行、资源和浏览器验收。不得把单库 100% 外推成任意 Schema 泛化。
最终勾选矩阵见 `docs/qa/revised_acceptance_matrix.md`。

## 附录 A：参考文档

- Qwen2.5-Coder 模型卡与许可证：https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct
- LLaMA-Factory：https://llamafactory.readthedocs.io/
- PEFT LoRA：https://huggingface.co/docs/peft/main/en/conceptual_guides/lora
- SQLGlot：https://sqlglot.com/sqlglot
- PostgreSQL 权限与只读事务：https://www.postgresql.org/docs/current/ddl-priv.html
- Langfuse：https://langfuse.com/docs

## 附录 B：训练前实际检查

```powershell
.\.conda\python.exe training\scripts\preflight.py --strict --output training\preflight-v3-report.json
.\.conda\python.exe training\scripts\resume_training.py
```

确认报告通过后，首次训练使用正式配置；只有恢复中断训练时才执行：

```powershell
.\.conda\python.exe training\scripts\resume_training.py --execute
```

训练前还必须记录 Git SHA、数据哈希、模型 revision、Prompt 版本、seed 和剩余磁盘；训练完成后保存曲线、adapter、预测和失败样本。
