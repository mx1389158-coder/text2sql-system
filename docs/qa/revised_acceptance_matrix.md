# 项目二 v2 最终验收矩阵

- [x] 固定数据库快照、可重复数据生成器、32 条外键一致性和版本化业务口径。
- [x] 自然语言 → Schema → SQL → AST/字段权限 → 只读执行 → 表格/解释/trace 闭环。
- [x] 独立 100 条 SQL 安全集、20 条请求安全集、只读权限、超时与恢复实测。
- [x] 4,100/620/300 数据具有 review、difficulty、snapshot、template_group，跨 split 泄漏为 0。
- [x] 100 条 smoke、完整 QLoRA、v5 adapter、曲线、模型卡、固定 revision 和许可证。
- [x] 计划角色 E00/E01/E10/E11 四格完成；最终 tuned 角色由不可变实际运行 E20/E21 映射，严格同数据、192 token、5 调用预算。
- [x] EX、表/列 Recall、澄清、安全、Repair Gain、token、调用、p50/p95、显存和 Badcase 报告。
- [x] Web 查询、SQL/结果、Schema 证据、实验对比、README、模型卡、数据卡和 Langfuse Cloud。
- [x] QueryRecord scope 所有权、详情 404、列表/澄清/反馈 scope 过滤和 legacy 记录 fail-closed。
- [x] 结果/Schema/Few-shot 缓存按权限与策略版本隔离，命中后重新生成请求级元数据。

补充门禁：四类产品验收 4/4；完整 Python 回归、Ruff、Web typecheck/build 必须通过后才能发布。

v1.1.1 权限与缓存收尾证据见 `docs/qa/security_cache_hardening_v1.1.1.md`。
v1.1.2 生产鉴权启动门禁见 `docs/qa/production_auth_hardening_v1.1.2.md`。
