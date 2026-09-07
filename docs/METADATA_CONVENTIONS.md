# BO 元数据编写公约

> 本文件定义 6 个 Fragment 的编写规范和自检清单，所有 BO 元数据 author/reviewer 必须遵循。
> 配套自动化校验脚本：`tools/check_metadata_consistency.py`

---

## 一、通用原则

### 1.1 唯一权威源

| 信息类型 | 权威 Fragment | 说明 |
|---------|:----------:|------|
| 实体结构（字段、类型、关系） | **MODEL** | 所有其他 Fragment 的 (entityCode, fieldCode) 必须能在 MODEL 中找到 |
| 业务术语（displayName） | **VIEW** | MODEL/SECURITY/RULE 中的名称描述以 VIEW 为准 |
| 操作定义（HTTP Method、URL） | **OPERATION** | RULE 中 scope=OPERATION 必须匹配已有操作 |
| 校验规则 | **VALIDATION** | 每个 (entityCode, fieldCode) 最多一条规则 |
| 安全策略 | **SECURITY** | 引用的 entityCode/fieldCode 必须在 MODEL 中存在 |
| 业务规则 | **RULE** | 引用的 entityCode/fieldCode/operationCode 必须匹配现有定义 |

### 1.2 修改前必做

- [ ] 先跑 `python tools/check_metadata_consistency.py`，确认当前基线通过
- [ ] 修改 MODEL 字段后，同步检查 VIEW / VALIDATION / SECURITY 是否需要对应变更
- [ ] 新增 OPERATION 后，检查 RULE 是否需要补充对应的 STATE 规则
- [ ] 新增 CROSS_BO_REF 后，检查是否需要配套的 CROSS_BO_DISPLAY + VALIDATION.redundant + RULE.CONSISTENCY

---

## 二、MODEL Fragment 编写规范

### 2.1 entity / attribute 命名

- `entity.code` 用 kebab-case：`opportunity-product`、`opportunity-stage-history`
- `tableName` 用 snake_case：`crm_opportunity_product`（禁止连字符）
- `attribute.code` 保持与 DB 列名一致：snake_case
- **审计字段必须在 ROOT entity 中声明**：`created_time` / `updated_time` / `created_by` / `updated_by`
- `created_by` / `updated_by` **MUST NOT** 标记为 `CROSS_BO_REF`（是基础设施审计字段，不是业务引用）

### 2.2 CROSS_BO_REF / CROSS_BO_DISPLAY

- 每个 `semanticRole=CROSS_BO_REF` → 必须填写 `crossBoRef` 对象
- `crossBoRef.refFieldCode` 必须引用目标 BO 的 PK（`id`）或 `businessKeyField`
- 每个 `crossBoRef.displayFields[].localCode` → 必须在本 entity 中有对应的 `semanticRole=CROSS_BO_DISPLAY` 属性
- CROSS_BO_DISPLAY 属性若未被任何 displayFields 引用 → **孤立属性**，应删除
- `redundant=true` 仅允许在 CROSS_BO_DISPLAY 上
- 关联子实体（`entityNature: "ASSOCIATION"`）不需要独立 OPERATION

### 2.3 aggregateApiPolicy

- `detailEmbedEntities` 只需列**一级直属于聚合根的实体**
- `resourcePath` 必须等于 `/{boCode}`

---

## 三、VIEW Fragment 编写规范

### 3.1 fieldView 必须覆盖

- MODEL 中每个 entity 的非审计字段都应有对应的 `fieldView`
- `dataType` 声明：与 MODEL.type 兼容（如 LONG → integer/reference，STRING → string/enum）
- **Snowflake Long ID 精度保护**：所有超出 JS 安全整数的 Long ID 在 VIEW 中 `dataType` 标记为 `"string"`，前端禁止 Number() 转换

### 3.2 displayName 一致性

- 同一 `fieldCode` 的 `displayName` 在整个 VIEW 中必须一致（主 fieldView + tab columns）
- `biz_attribution` → displayName = `"业务名称"`（不是"业务归属"）
- `expected_order_amount` → 非 OC_MAIN 时 displayName = `"预计下单金额"`，OC_MAIN 时通过 `displayRules` 覆盖为 `"集采框架总金额"`

### 3.3 计算字段

- 纯 VIEW 计算字段（`computedField`）不需要在 MODEL 中声明属性
- 例：`ordered_quantity`、`remaining_quantity` 是 OC_MAIN 产品清单中的视图计算列

---

## 四、OPERATION Fragment 编写规范

### 4.1 操作覆盖

| 操作类型 | 必须声明 | 说明 |
|---------|:------:|------|
| CREATE | ✅ | 新建聚合根 |
| DELETE | ✅ | 删除聚合根（当 `aggregateApiPolicy.deleteScope != NONE` 时） |
| EDIT/UPDATE | ✅ | 更新聚合根/子实体 |
| LIST/READ | 按需 | `aggregateApiPolicy` 可隐式推导，建议显式声明 |
| STATE_CHANGE | ✅ | 每个状态流转操作 |
| CUSTOM | ✅ | 自定义操作 |

- 子实体（SUB_ENTITY）的 CRUD 操作可选声明（`scope: "ENTITY"`）
- **DELETE 操作必须**：当 `aggregateApiPolicy.deleteScope = CASCADE_AGGREGATE` 时声明根实体 DELETE

### 4.2 PATCH → POST 降级

- `httpMethod: "PATCH"` 在 OPERATION Fragment 中保留（表达 REST 语义）
- 实际实现用 `@PostMapping` + 动作路径，参照宪章 3.3 节

---

## 五、VALIDATION Fragment 编写规范

### 5.1 唯一性

- 每个 `(entityCode, fieldCode)` 最多一条规则
- **禁止重复**：新增前先搜索是否已存在同一 key 的规则

### 5.2 覆盖

- MODEL 中 `required` 的业务字段必须在 VALIDATION 中有对应规则
- 条件必填使用 `conditional.dependsOn + when/whenNot`
- Boolean 字段建议显式声明 `required`（即使有 defaultValue）

---

## 六、SECURITY Fragment 编写规范

### 6.1 fieldSecurity 引用

- 引用的 `(entityCode, fieldCode)` 必须在 MODEL 中存在
- `fieldControl=HIDDEN` 时，VIEW 中对应的 `exportable` 不能为 `true`

### 6.2 authzProjection

- 每个需要行级/字段级控制的业务字段都应投影
- `allowedValues` 与 `valueRef` 互斥，不得同时出现
- `onMissingValue` 与 `nullable` 语义不重叠时，去掉 `onMissingValue`

---

## 七、RULE Fragment 编写规范

### 7.1 scope 引用

- `scope=FIELD` → `entityCode + fieldCode` 必须在 MODEL 中存在
- `scope=ENTITY` → `entityCode` 必须在 MODEL 中存在
- `scope=OPERATION` → `operationCode` 必须在 OPERATION Fragment 中存在
- `scope=CROSS_BO` → `crossBoRef.localEntityCode + localFieldCode` 必须在 MODEL 中存在

### 7.2 命名规范

- Rule code 命名：`{BO}_{SCOPE}_{CONCERN}`，如 `OPPORTUNITY_STATUS_WIN`
- `message` 中的业务术语参照 VIEW 的 displayName

---

## 八、跨 Fragment 交叉自检清单

修改任何 Fragment 后，执行以下检查：

```
□ python tools/check_metadata_consistency.py → 无 ERROR
□ VALIDATION 中无 (entityCode, fieldCode) 重复
□ VIEW 和 MODEL 的关键字段命名一致
□ OPERATION HTTP Method 符合宪章（PATCH→POST 降级）
□ CROSS_BO_REF 的 displayFields.localCode 都有对应的 CROSS_BO_DISPLAY
□ 所有 CROSS_BO_REF（引用 customers）都有对应的 RULE.CROSS_BO 存在性校验
□ SECURITY.fieldSecurity 引用的字段在 MODEL 中存在
```
