# 运行态投影 Schema 说明

## authz-bo-meta-model-projection

> 来源：`authz-projection/authz-bo-meta-model-projection.schema.json`

由 `bo-projection-gen.py --type authz_bo_meta_model` 从发布态 `schema-view.v2` 生成，写入 PSP `authz_bo_meta_model` 表的 `schema_json` 字段。PSP `BoSchemaJsonValidator` 据此校验 BO 元数据并派生权限项。

### 结构要点

- `fieldControl` 为 **boolean**（非 enum），`true` 时必须输出 `fieldControlStrategy`
- `fieldControlStrategy` 使用 PSP 枚举值：`MASK` / `HIDE` / `RESTRICTED`（设计态 `MASKED→MASK`，`HIDDEN→HIDE`）
- `scope` 使用 PSP 枚举值：仅 `BO` / `ENTITY`（设计态 `GLOBAL→BO`）
- `operations` 不含 `httpMethod` / `actionPath` / `operationKind`（PSP 不需要）
- `operation.code` 兼容连字符（如 `EDIT-APPROVE`）和下划线（如 `EDIT_APPROVE`）
- `_sql.expected_permission_items_after_publish` 按 `authzAction` 去重生成权限项键

### PSP BoSchemaJsonValidator 约束

- `SUPPORTED_FIELD_CONTROL_STRATEGIES`: `OPEN` / `RESTRICTED` / `MASK` / `HIDE`
- `validateOperations`: scope 仅支持 `BO` 或 `ENTITY`

### 旧版数据迁移

已有 PSP 上线数据需重新运行 `bo-projection-gen.py --type authz_bo_meta_model` 完成以下迁移：

1. 子实体补充 `rowLevelRuleEntries: []`（即使为空数组也必须声明）
2. `fieldControl=true` 的属性补充 `fieldControlStrategy`（`RESTRICTED` / `MASK` / `HIDE`）
3. 每个 `operation` 补充 `authzAction`（从设计态 OPERATION fragment 透传）

---

## bo-merge-manifest

> 来源：`authz-projection/bo-merge-manifest.schema.json`

### 使用场景

设计态按治理目标拆分为多个 BO（如 MDM `customers` + MCR `customer-relations`），但运行态物理表为单表（`crm_customer`），需要合并为单一 PSP BO 注册。

### 合并流程

1. 发布服务加载 merge manifest
2. 按 `sources[].boCode` 加载各 BO 的 `schema_view`
3. 按 `entityMergeStrategy` 合并实体（`SAME_ROW_COLUMN_SUBSET` / `PASS_THROUGH`）
4. 按 `operationRename` 重命名冲突操作
5. 按 `mergeRules` 合并行级过滤字段和操作
6. 输出合并后的 `schema_json`，写入 `targetBoCode` 对应的 `authz_bo_meta_model` 行

合并产物仍符合 `authz-bo-meta-model-projection.schema.json`，PSP 无感知。
