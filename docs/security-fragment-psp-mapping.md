# SECURITY Fragment 到 PSP 权限控制映射

本文说明 `SECURITY` Fragment 如何支持当前 PSP 的 RBAC / ABAC / PBAC 权限控制。核心结论：`SECURITY` Fragment 不是角色授权记录本身，而是补充 `authz_bo_meta_model` 中某一条 BO 元数据的安全投影、策略参数和运行时上下文的设计态来源。

## 1. 三段式定位

| Fragment 内容 | PSP 落点 | 运行时作用 |
|----------------|----------|------------|
| `rowSecurity` | BO 发布态 `schema_json.entities[].rowLevelRuleEntries`，并辅助生成 DATA 策略模板参数 | 约束哪些资源字段可用于数据范围表达式和 SQL 行过滤 |
| `fieldSecurity` | BO 发布态 `schema_json.entities[].attributes[]` 的字段控制元数据，并辅助生成 FIELD 策略模板参数 | 约束哪些字段允许绑定字段控制策略，以及默认建议动作 |
| `authzProjection` | `authz_bo_meta_model.schema_json` 中该 BO 的安全投影，如 SCENE 这条 BO 元数据内的 `RES_SCENE` | 给策略配置 UI、PIP 和策略表达式提供该 BO 的 `res.*` 属性目录、类型、取值和引用说明 |

PSP 真正执行鉴权时，仍以 `authz_permission_item + authz_assignment + authz_std_pol_template` 为运行时主链路。对 BO 数据资源来说，运行时锚点是 `authz_permission_item.res_model_code=RES_DATA_BO` 与 `authz_permission_item.res_id=authz_bo_meta_model.id`。`SECURITY` Fragment 负责告诉 PSP：这条 BO 元数据可以按哪些资源属性判断、哪些字段可以做行级/字段级控制、这些字段来自哪里。

## 2. 与 PSP 表的关系

### 2.1 BO 权限资源与 RES_SCENE 的关系

当前 PSP 的标准资源模型枚举中，BO 数据资源使用固定资源模型 `RES_DATA_BO`，它对应的是 `authz_bo_meta_model` 表。SCENE 的权限项不以 `RES_SCENE` 作为 `res_model_code`，而是这样定位：

```text
authz_permission_item.res_model_code = RES_DATA_BO
authz_permission_item.res_id         = authz_bo_meta_model.id
authz_permission_item.act_code       = READ / UPDATE / CREATE / DELETE / EXPORT / ...
```

`RES_SCENE` 的正确位置是 SCENE 这条 BO 元数据内的安全投影编码：

```text
authz_bo_meta_model.id          = SCENE_BO_MODEL_ID
authz_bo_meta_model.bo_code     = SCENE
authz_bo_meta_model.schema_json = {
  ...,
  "security": {
    "authzProjection": {
      "modelCode": "RES_SCENE",
      "attributes": [ ... ]
    }
  }
}
```

因此，`RES_SCENE` 与 PSP 的关系不是新增一个独立的 PSP 标准资源类型，而是绑定到 `authz_bo_meta_model` 中 SCENE 这条业务对象元数据，作为该 BO 的 `res.*` 属性视图标识。

`SECURITY` Fragment 不直接生成 `act_code`。动作权限项主要来自 `OPERATION` / API / 菜单治理。`SECURITY` Fragment 影响的是这些权限项命中之后，是否还要叠加 DATA / STATE / FIELD 等策略。

### 2.2 BO 元模型

发布服务需要把 BO Snapshot 同步到 `authz_bo_meta_model.schema_json`。其中与 `SECURITY` 相关的字段包括：

```json
{
  "entities": [
    {
      "code": "scene_main",
      "tableName": "scene_main",
      "rowLevelRuleEntries": ["fop_customer_id", "sales_owner_id", "dept_id", "status"],
      "attributes": [
        {
          "code": "current_year_estimated_sales",
          "fieldName": "currentYearEstimatedSales",
          "columnName": "current_year_estimated_sales",
          "type": "DECIMAL",
          "fieldControl": true,
          "fieldControlStrategy": "MASK"
        }
      ]
    }
  ]
}
```

注意治理值和 PSP 运行时值需要转换：

| SECURITY `fieldControl` | PSP FIELD action / `fieldControlStrategy` |
|-------------------------|--------------------------------------------|
| `OPEN` | `OPEN` |
| `RESTRICTED` | `RESTRICTED` |
| `MASKED` | `MASK` |
| `HIDDEN` | `HIDE` |

当前 PSP FIELD 策略校验要求目标字段在 BO schema 运行时元数据中满足 `fieldControl=true`。因此发布服务不能只写治理枚举值，还需要生成 PSP 可识别的布尔开关和策略动作。

### 2.3 BO 权限属性投影

`authzProjection` 应随 BO Snapshot 合并进 `authz_bo_meta_model.schema_json`。它可以复用 `authz_schema_view` 的属性描述结构，但当前 PSP 运行时应以 BO 元数据为主源：

```text
authz_bo_meta_model.id = SCENE_BO_MODEL_ID
schema_json.security.authzProjection.modelCode = RES_SCENE
schema_json.security.authzProjection.attributes = authzProjection.attributes
```

`RES_SCENE` 的主要价值是策略配置和审计说明：告诉管理员和 PIP 适配器，在 SCENE BO 上可以使用哪些 `res.*` 属性，例如 `res.dept_id`、`res.sales_owner_id`、`res.business_name`。如果后续为了检索或 UI 展示把它同步到其他索引表，也必须保留到 `authz_bo_meta_model.id` 的绑定关系，不能把它当成脱离 BO 元数据的独立资源模型。

## 3. 运行时如何发挥作用

### 3.1 RBAC 基础授权

角色、用户、组织等主体先通过 `authz_assignment` 获得某个权限项：

```text
角色 R_SCENE_SALES
  -> authz_assignment.perm_item_id
  -> authz_permission_item(RES_DATA_BO, SCENE_BO_MODEL_ID, UPDATE)
```

这一步回答“谁对 SCENE 有 UPDATE 权限”。它主要来自 `OPERATION` 或 API 权限项派生，不由 `SECURITY` 单独完成。界面上的“编辑”和“保存修改”都应归并到同一个 `UPDATE` 权限项，不生成 `SAVE`。

### 3.2 ABAC / PBAC 策略门控

权限项命中后，PSP 的 PDP 会按 `ENV -> STATE -> DATA -> FIELD` 执行策略模板。`SECURITY` Fragment 提供策略可引用的资源属性和字段控制范围。

示例：只允许负责人编辑自己的场景。

```text
策略类型: STATE 或 DATA
表达式: sub.user_id == res.sales_owner_id
来源: SCENE BO 元数据的 authzProjection.attributes.sales_owner_id
```

示例：只允许查看所属部门数据。

```text
策略类型: DATA
表达式: scene_main.dept_id in sub.dept_scope_ids
来源: rowSecurity.entriesByEntity.scene_main.dept_id
结果: obligations.rowFilter，由 AuthzRowFilterInterceptor 注入 SQL
```

示例：预计销量字段脱敏。

```text
策略类型: FIELD
policyParams.targetField = current_year_estimated_sales
policyParams.action      = MASK
来源: fieldSecurity 中 current_year_estimated_sales = MASKED
结果: obligations.fieldControls，由 AuthzFieldControlAdvice 修改响应 JSON
```

### 3.3 PIP 属性加载

当请求检查 `RES_DATA_BO` 权限项时，PIP 使用 `authz_permission_item.res_id` 定位 `authz_bo_meta_model.id`，再读取该 BO 元数据中的 `schema_json` 和业务实例属性。`RES_SCENE` 是这条 BO 元数据内的安全投影编码，`authzProjection` 中声明的属性必须能从 SCENE 实例或派生计算中得到，否则应按 `onMissingValue` 执行失败关闭、放行或跳过。

## 4. SCENE 示例落地

`scene-security.fragment.json` 对 PSP 的含义如下：

| 片段 | SCENE 示例 | PSP 效果 |
|------|------------|----------|
| `rowSecurity.entriesByEntity.scene_main` | `fop_customer_id`、`business_name`、`scene_category`、`sales_owner_id`、`dept_id`、`status` | 这些字段允许进入 DATA 策略和行级 SQL 过滤 |
| `fieldSecurity` | `current_year_estimated_sales=MASKED`、`sales_owner_id=RESTRICTED` | 发布时生成字段控制元数据；绑定 FIELD 策略后生成 `fieldControls` |
| `authzProjection.modelCode` | `RES_SCENE` | 标识 SCENE 这条 BO 元数据内的权限属性投影，供策略配置 UI、PIP、表达式提示和审计展示使用 |
| `authzProjection.attributes[].filterable=true` | `dept_id`、`sales_owner_id`、`business_name` 等 | 推荐作为 DATA / STATE 策略候选字段 |
| `authzProjection.attributes[].onMissingValue` | `DENY` / `ALLOW` | PIP 缺失属性时的安全策略建议 |

## 5. 它不能单独完成什么

`SECURITY` Fragment 不能单独完成以下事情：

1. 不能创建角色、用户组或授权分配；这些仍由 RBAC 授权管理写入 `authz_assignment`。
2. 不能决定 `READ / UPDATE / CREATE / DELETE` 动作清单；动作主要来自 `OPERATION`、API 或菜单治理。
3. 不能自动让字段脱敏生效；必须有命中的 FIELD 策略，并且该字段已发布为 PSP 可控字段。
4. 不能自动生成业务实例属性；PIP / BO resolver 必须能按实例 ID 取到或计算出 `authzProjection` 声明的属性。
5. 不能替代应用层领域规则；状态流转、一致性和自动化规则应进入 `RULE` Fragment 或应用层领域模型。

## 6. 发布服务应做的转换

发布服务至少需要执行以下转换，才能让 `SECURITY` Fragment 真正支撑 PSP：

1. 将 `rowSecurity.entriesByEntity` 合并到 BO Snapshot 的实体级 `rowLevelRuleEntries`。
2. 将 `fieldSecurity` 合并到 BO Snapshot 的属性级字段控制元数据，并把 `MASKED/HIDDEN` 转换成 PSP 的 `MASK/HIDE`。
3. 将 `authzProjection` 合并到 `authz_bo_meta_model.schema_json` 中该 BO 的安全投影区域；如需额外索引表，只能作为从 BO 元数据派生的查询视图。
4. 校验 `authzProjection.attributes[].source` 引用的实体和字段存在。
5. 校验 `filterable=true` 的属性具备可用于 DATA / STATE 策略的类型、来源和缺失值处理策略。
6. 为策略配置 UI 输出候选字段、候选值、引用模型和示例表达式。
7. 将 `OPERATION` 派生的动作权限项与 `SECURITY` 派生的策略模板关联到授权配置流程中。

这样分工后，`SECURITY` Fragment 的定位就很明确：它是 `authz_bo_meta_model` 中 BO 元数据安全投影的治理来源，并支撑 PSP 数据权限、字段权限和策略表达式资源属性，不是最终授权结果。