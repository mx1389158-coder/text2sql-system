# QLoRA A/B/C 运行手册

## 通用门禁

运行 `training/scripts/preflight.py --strict`。CUDA、BF16、NF4 算子、依赖锁、数据规模、磁盘和
基线证据任何一项失败都不得启动完整训练。训练配置和推理配置分开保存。

## 阶段 A：训练链路

- 数据：`text2sql_smoke_v1` 100 条；
- 目标：小样本过拟合、loss 下降、checkpoint 可保存/加载、JSON/SQL 格式有效；
- 产物：`training/smoke_validation.json` 和 smoke adapter；
- 禁止：把此阶段结果描述为泛化能力。

## 阶段 B：完整 QLoRA 与 Badcase

- 使用 train/dev，不查看 blind/Holdout Gold；
- 同时保留基座预测和微调预测；
- 按字段归属、事实表、桥接表、JOIN、时间、口径分类失败；
- 无提升或回归仍登记模型，不删除结果。v1 即为保留的失败版本。

## 阶段 C：固定最终实验

- 固定模型 revision、数据哈希、Prompt、seed、token 和调用预算；
- 开发集选定配置后，在冻结集只运行正式评估；
- 保存 adapter、config hash、训练/验证曲线、预测、2×2、Badcase、显存与模型卡；
- 当前最终模型为 v5，证据见 `training/model_cards/qwen25-coder-1.5b-text2sql-v5.md`。

## 恢复而非重跑

默认命令只检查恢复点并打印命令：

```powershell
.\.conda\python.exe training\scripts\resume_training.py
```

检查结果同时保存到 `training/resume-plan.json`。只有确认确实要继续中断训练时才加
`--execute`。脚本拒绝缺失 optimizer、scheduler 或 trainer state 的 checkpoint。
