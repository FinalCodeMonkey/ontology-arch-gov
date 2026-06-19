# BO 元数据治理架构

本目录沉淀业务对象（BO）元数据持续治理的设计资产，覆盖设计态 Fragment、发布态 BO Snapshot、派生态 Authz Projection / UI / API 三层模型。

## 目录结构

| 路径 | 说明 |
|------|------|
| `schemas/` | BO 发布态 schema、设计态 fragment schema、各 fragment 类型 schema |
| `config/` | 公司/项目级治理参数文件 Governance Profile |
| `sql/` | `gov_bo_meta_fragment` 与 `gov_bo_meta_release` 建表脚本 |
| `docs/` | 三层模型、规则治理、Security 到 PSP 映射、发布转换流程、Java 核心实现片段 |
| `examples/scene/` | 场景 BO 作为首个元数据治理对象的设计态 Fragment 示例 |

## 核心原则

1. 设计态按治理职责拆分：`MODEL / VALIDATION / SECURITY / RULE / VIEW / OPERATION`。其中 `RULE` 是本体规则层，`VALIDATION` 与 `SECURITY` 是规则层的专用子集和兼容投影。
2. 发布态合成为完整 BO `schema_view` 快照，运行时只读发布态。
3. 权限、前端、API 都从发布态派生，避免多源真相。
4. `isPrimary` 与 `aggregateRole=ROOT` 语义分离，但标准 BO 发布校验要求二者一一对应。
5. 子实体外键不强制物理命名为 `parent_id`，但必须显式声明 `parentEntityCode` 与 `parentRefField`。
6. Operation 可从界面原型按钮抽取，但必须过滤刷新、列设置、全屏、分页、Tab 切换等纯 UI utility，并通过 `prototypeRefs` 保留来源追溯。
7. 聚合根标准 API 面向 BO 聚合，但必须通过 `aggregateApiPolicy` 显式声明列表、详情、创建、更新、删除分别处理完整聚合还是主实体。
8. 当主实体接口和完整聚合接口都需要时，使用 `alternateAggregateApis` 声明额外端点；删除只处理主实体时必须配置 `orphanPolicy`。
9. 多级子实体如果也需要“实体本体接口 + 局部聚合接口”，使用 `entityApiPolicy` 和 `alternateEntityApis`。
10. schema 表达治理能力，项目级默认值放入 Governance Profile，BO Fragment 只声明业务差异。
11. Governance Profile 内置 `usageGuide` 中文说明，同时提供 [docs/governance-profile-guide.md](docs/governance-profile-guide.md) 作为实施说明。
12. 参考 Palantir 本体四要素时，`MODEL` 对应对象类和属性，`OPERATION` 对应行为，`RULE` 对应规则；不要把 `VALIDATION` 等同于完整规则体系。
13. `SECURITY` Fragment 不是授权结果本身，它通过 [docs/security-fragment-psp-mapping.md](docs/security-fragment-psp-mapping.md) 中定义的转换关系支撑 PSP 的 DATA / FIELD / STATE 等策略。

## 三层模型

```text
设计态 Fragment
  MODEL / VALIDATION / SECURITY / RULE / VIEW / OPERATION
        |
        v
发布态 BO Snapshot
  完整 bo_schema_view，按 release_version 不可变归档
        |
        v
派生态模型
  Authz Projection / UI Model / API Contract / Permission Items
```

## 推荐落地顺序

1. 先使用 `examples/scene/fragments` 注册 `SCENE` 的设计态 Fragment；现有样例以 `VALIDATION`、`SECURITY` 承载规则子集，后续可补充 `RULE` Fragment 汇总状态、派生、一致性和自动化规则。
2. 发布服务加载 `config/governance-profile.default.json`，用项目默认参数补齐 Fragment。
3. 通过发布服务合成 BO Snapshot，写入 `gov_bo_meta_release`。
4. 将当前版本同步到 `authz_bo_meta_model.schema_json`。
5. 在 `authz_bo_meta_model.schema_json` 中保留 `RES_SCENE` 安全投影，作为 SCENE 这条 BO 元数据的 `res.*` 属性契约。
6. 基于发布态快照生成 UI 配置、API 合同和权限项。
