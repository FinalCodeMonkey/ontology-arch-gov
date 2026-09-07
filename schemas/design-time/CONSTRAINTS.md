# BO Fragment Schema 约束清单

各 Fragment 的完整性约束规则，分"Schema 层面强制执行"和"check_consistency.py 强制执行"两类。

---

## MODEL Fragment

> 来源：`model-fragment.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `attribute.semanticRole=CROSS_BO_REF` → `crossBoRef` 必填（allOf） |
| B | `aggregateRole=SUB_ENTITY` → `parentEntityCode` + `parentRefField` 必填（allOf） |
| C | `entityNature=ASSOCIATION` 的子实体，代码生成器应生成复合唯一键 `(parentRefField, 首个 CROSS_BO_REF 字段)`；前端渲染走轻量多选/Tag 交互而非完整表单 |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `apiConfig.idField` 指向的 attribute code 必须在 ROOT entity attributes 中存在且 `isPk=true` |
| 2 | `apiConfig.businessKeyField` 指向的 attribute code 必须在 ROOT entity attributes 中存在 |
| 3 | `boConfig.nameField` / `statusField` 指向的 attribute code 必须在 ROOT entity attributes 中存在 |
| 4 | `entities` 中有且仅有一个 `isPrimary=true` 且 `aggregateRole=ROOT`，且二者指向同一 entity |
| 5 | `entity.parentEntityCode` 必须指向同一 BO 内的另一个 entity code |
| 6 | `entity.parentRefField` 是子实体自身持有的父 ID 外键字段，必须存在于当前子实体的 attributes 中（不是父实体） |
| 7 | `crossBoRef.refBoCode` 须为有效的已发布 BO |
| 8 | `boConfig.defaultSort.field`（若配置）指向的 attribute code 必须在 ROOT entity attributes 中存在 |
| 9 | `entities` 数组内 `entity.code` 必须唯一；`attributes` 数组内 `attribute.code` 必须唯一 |
| 10 | `crossBoRef.displayFields[].localCode` 必须在同一 entity 的 attributes 中存在，且对应属性的 `semanticRole=CROSS_BO_DISPLAY` |
| 11 | `semanticRole=CROSS_BO_DISPLAY` 的属性必须被同一 entity 内某个 CROSS_BO_REF 属性的 `crossBoRef.displayFields[].localCode` 引用 |
| 12 | `created_by` / `updated_by` 为基础设施层审计字段，**MUST NOT** 标记为 `CROSS_BO_REF` |
| 13 | `semanticRole=CROSS_BO_DISPLAY` 且 `redundant≠true` → 代码生成器仅在 View/DTO 层生成，DB/Entity/Domain 均不生成 |
| 14 | `redundant=true` 仅允许在 `semanticRole=CROSS_BO_DISPLAY` 的属性上使用 |
| 15 | 所有 entity 的 PK attribute code MUST 为 `"id"`，不允许语义化 PK 名（如 `line_id`、`accessory_id`） |
| 17 | `entity.code` 使用 kebab-case（`^[a-z][a-z0-9-]*$`），与 API 路径风格一致。子实体默认使用 entity.code 作为路由段，无需额外配置 `routeSegment` |

---

## OPERATION Fragment

> 来源：`operation-fragment.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `scope=ENTITY` → `entityCode` 必填（allOf） |
| B | `operationKind=CUSTOM` + `triggerEvent∈[API_CALL, CONFIRM_THEN_API]` → `actionPath` 必填（allOf） |
| C | `primaryDataAction` 必填，枚举值为 `CREATE` / `READ` / `UPDATE` / `DELETE`，表示该操作对业务数据层的主效应；复杂业务命令只填写主效应 |
| D | Operation 元数据不得持久化原型文件、按钮文案或事件函数引用；`prototypeRefs` 不属于 schema 允许字段，出现即校验失败 |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| C | `operations` 数组内 `operation.code` 必须唯一 |
| D | `scope=ENTITY` 时 `entityCode` 必须在 MODEL entities 中存在 |
| E | `scope=BO` / `GLOBAL` 时 `entityCode` 语义上不应出现，由发布服务校验 |
| F | 编辑态若需要返回不同 DTO、下拉选项或申请互斥锁，必须声明独立编辑会话 Operation；该 Operation 使用 `operationKind=CUSTOM`、`httpMethod=POST`、`authzAction=UPDATE`，不得复用保存修改 Operation |
| G | 保存修改 Operation 使用 `operationKind=UPDATE`、`authzAction=UPDATE`；不得为保存动作生成 `SAVE`、`LOCK`、`UNLOCK` 等独立权限动作 |

---

## RULE Fragment

> 来源：`rule-fragment.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `scope=CROSS_BO` → `crossBoRef` 必填（allOf），适用所有 `ruleType` |
| B | `scope=ENTITY` → `entityCode` 必填（allOf） |
| C | `scope=FIELD` → `entityCode` + `fieldCode` 必填（allOf） |
| D | `scope=OPERATION` → `operationCode` 必填（allOf） |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| E | `rules` 数组内 `rule.code` 必须唯一 |
| F | `entityCode` / `fieldCode` 必须在 MODEL entities 中存在 |
| G | `operationCode` 必须在 OPERATION fragment 中存在 |
| H | `crossBoRef.localEntityCode` / `localFieldCode` 必须在 MODEL entities 中存在 |
| I | `scope=BO` 时 `entityCode` / `fieldCode` / `operationCode` 语义上不应出现，由发布服务校验 |
| J | `exprAst` 若存在，必须通过 `expression-ast.schema.json` 校验；`exprAst` 中引用的字段路径必须在 MODEL 中存在，`viaLink` 必须在 LINK 发布态中存在 |

---

## SECURITY Fragment

> 来源：`security-fragment.schema.json`

### v3 变更

`allowedValues` 从 `string[]` 改为 `{value, label}` 对象数组，支持显示名与存储值分离。

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `fieldSecurity[]` 的结构合法性（entityCode/fieldCode/fieldControl/privacyClass 必填、enum 取值）由 JSON Schema 本身保证 |
| B | `fieldSecurity[].fieldCode` 对应的 MODEL 字段的 `semanticRole` **不受 Schema 约束**——跨文件引用无法用 JSON Schema 表达；此项由 `check_consistency.py` 强制执行（见下方第 8 条） |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `fieldSecurity[].entityCode` / `fieldCode` 必须在 MODEL entities 中存在 |
| 2 | `rowSecurity.entriesByEntity` 的所有 key 必须在 MODEL entities 中存在 |
| 3 | `rowSecurity.entriesByEntity` 的所有字段名必须在对应 entity.attributes 中存在 |
| 4 | `authzProjection.attributes[].source.entityCode` / `fieldCode` 必须在 MODEL entities 中存在 |
| 5 | `authzProjection.attributes` 的 `allowedValues` 与 `valueRef` 互斥，不得同时出现 |
| 6 | `fieldSecurity` 和 `authzProjection.attributes` 数组内条目 key 级唯一性由 check_consistency.py 保障 |
| 7 | 跨 Fragment 校验：`fieldControl=HIDDEN` 的字段在 VIEW 中不得有 `exportable=true` |
| 8 | `fieldSecurity` 不应覆盖 `semanticRole=CROSS_BO_REF | TECHNICAL_ID | PARENT_REF | BUSINESS_KEY` 的字段 — 这些字段为外键/技术键，不包含业务敏感内容；行级安全通过 `rowSecurity` 控制，名称脱敏应在目标被引用 BO 的 SECURITY 中处理 |

---

## VALIDATION Fragment

> 来源：`validation-fragment.schema.json`

### v3 变更

`enum` 从 `string[]` 改为 `{value, label}` 对象数组，支持显示名与存储值分离。

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `rules[].entityCode` 必须在 MODEL entities 中存在 |
| 2 | `rules[].fieldCode` 必须在对应 entity.attributes 中存在 |
| 3 | `rules` 数组内 `(entityCode, fieldCode)` 组合必须唯一 |
| 4 | `min` 与 `max` 同时存在时 `min` 必须 ≤ `max` |
| 5 | `min`/`max` 语义取决于对应 MODEL attribute.type：STRING 类型解释为字符长度约束，INTEGER/LONG/DECIMAL 解释为数值约束 |

---

## VIEW Fragment

> 来源：`view-fragment.schema.json`

| 编号 | 约束 |
|------|------|
| 1 | `fieldViews[].entityCode` 必须在 MODEL entities 中存在 |
| 2 | 普通 `fieldViews[].fieldCode` 必须在对应 entity.attributes 中存在；若声明 `computedField`，fieldCode 可为纯 VIEW 计算字段，但 `computedField.sources[]` 必须引用 MODEL 中存在的字段 |
| 3 | `fieldViews` 数组内 `(entityCode, fieldCode)` 组合必须唯一 |
| 4 | `formType=NUMBER|DATE|DATETIME|SWITCH` 应与 MODEL attribute.type 兼容 |
| 5 | `formType=OBJECT_SELECT` 且对应 MODEL `attribute.semanticRole=CROSS_BO_REF` 时，`refObject` 必须与 `crossBoRef.refBoCode` 一致 |
| 6 | SECURITY `fieldControl=HIDDEN` 的字段 `exportable` 不得为 `true` |
| 7 | `computedField` 必须是只读展示字段，`editableInForm` 不得为 `true`，且不应设置 `importable=true` |
| 8 | **CROSS_BO_REF 字段**：`showInList=true`、`showInDetail=true`、`editableInForm=true`、`formType` 为 `OBJECT_SELECT`（refBoCode 非 users）或 `USER_SELECT`（refBoCode 为 users）；`refObject` 必须与 MODEL `crossBoRef.refBoCode` 一致；`refField` 必须与 MODEL `crossBoRef.displayFields` 中 `displayRole=NAME` 的 `refFieldCode` 一致；`queryable=true`、`dataType=string`、`importable=true` |
| 9 | **CROSS_BO_DISPLAY 字段**：`showInList=true`、`showInDetail=true`、`editableInForm=false`、`formType=INPUT`、`queryable=true`、`dataType=string`、`importable=false`；`queryOperatorOptions` 应包含 `LIKE` |

---

## LINK Fragment

> 来源：`link-fragment.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `source` 与 `target` 是不同 BO 时，两端的 `boCode` 均须存在（由发布服务校验，JSON Schema 无法表达跨文件引用） |
| B | `materialization=FIELD_REF` 时，目标字段应能在 MODEL 中找到对应 `semanticRole=CROSS_BO_REF`（check_consistency.py 校验） |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `links` 数组内 `link.code` 必须唯一 |
| 2 | `source.boCode` / `target.boCode` 必须在同一 `tenantId/appCode` 的 BO 集合中存在 |
| 3 | `source.entityCode` / `source.fieldCode` 必须在源 BO 的 MODEL entities 中存在 |
| 4 | `target.entityCode` / `target.fieldCode` 必须在目标 BO 的 MODEL entities 中存在 |
| 5 | `cardinality=MANY_TO_MANY` 时必须 `materialization=ASSOCIATION_ENTITY` 或 `DERIVED` |
| 6 | `authzMode=BOTH_ENDPOINTS` 时，发布服务必须校验源端和目标端均声明了 `rowSecurity.entriesByEntity` |
| 7 | 显式 LINK 的 `source/target` 组合不能与自动派生 LINK 完全重复（code 相同视为同一 LINK） |
| 8 | `validFromField` / `validToField` 若配置，必须存在于 `source` 或 `target` 对应的 entity.attributes 中 |

---

## DERIVATION Fragment

> 来源：`derivation-fragment.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `apiExposure.enabled=true` → `resourcePath` 必填（由 Schema 定义，详见 derivation-fragment.schema.json） |
| B | `materialization.mode=ON_READ_CACHE` → `ttlSeconds` 建议显式声明（无强制，但推荐；未声明时默认 0=永不过期） |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `derivedObjects` 数组内 `derivedObject.code` 必须唯一 |
| 2 | `root.boCode` / `entityCode` / `idField` 必须在 MODEL 中存在 |
| 3 | `dependencies[].boCode` 必须在同一 `tenantId/appCode` 的 BO 集合中存在 |
| 4 | `dependencies[].viaLink` 必须在 LINK 发布态中存在 |
| 5 | 派生对象依赖图不得存在循环（check_consistency.py 拓扑检测） |
| 6 | `fields[].expression` 必须能通过 expression-ast.schema.json 校验 |
| 7 | `expression` 中引用的字段路径必须在 MODEL entities 或本派生对象的 fields 中存在 |
| 8 | `apiExposure.resourcePath` 不能与 MODEL.apiConfig.resourcePath 或已有派生对象的 resourcePath 冲突 |
| 9 | `materialization.tableName` 若配置，不得与现有业务表名冲突 |

---

## TEMPORAL Fragment

> 来源：`temporal-fragment.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `eventSources[].sourceType=OPERATION` → `operationCode` 必填（allOf） |
| B | `eventSources[].sourceType=ENTITY` → `entityCode` 必填（allOf） |
| C | `metrics[].metricType` 带 `WINDOW` 后缀 → `window` 和 `sourceLink` 必填（allOf） |
| D | `metrics[].metricType=SUM_WINDOW` 或 `AVG_WINDOW` → `targetField` 必填（allOf） |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `timelines` 数组内 `timeline.code` 必须唯一 |
| 2 | `boCode` / `entityCode` 必须在 MODEL 中存在 |
| 3 | `timeField` / `stateField` / `statusField` 必须在对应 entity.attributes 中存在 |
| 4 | `snapshots` 中的字段 code 必须在对应 entity.attributes 中存在 |
| 5 | `eventSources[].operationCode` 必须在 OPERATION Fragment 中存在 |
| 6 | `eventSources[].entityCode`（sourceType=ENTITY 时）必须在 MODEL entities 中存在 |
| 7 | `metrics[].sourceLink` 必须在 LINK 发布态中存在 |
| 8 | `metrics[].targetField` 必须在对应 BO 的 MODEL entities 中存在 |

---

## Expression AST

> 来源：`expression-ast.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `type=literal` → `value` 必填 |
| B | `type=field` → `path` 必填 |
| C | `type=metric` → `code` 必填 |
| D | `type=binary` → `op` + `left` + `right` 必填 |
| E | `type=logical` → `op` + `items` 必填 |
| F | `type=isNull` → `expr` 必填 |
| G | `type=isNotNull` → `expr` 必填 |
| H | `type=exists` → `source` + `viaLink` 必填 |
| I | `type=aggregate` → `fn` + `source` + `viaLink` 必填 |
| J | `type=temporalAggregate` → `fn` + `source` + `viaLink` + `window` + `timeField` 必填 |
| K | `type=weightedScore` → `itemsForWeight` 必填 |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `path` 引用的字段在 MODEL entities 中存在（当前 BO 作用域内查找） |
| 2 | `source`（aggregate/temporalAggregate/exists）的 boCode 必须存在 |
| 3 | `viaLink` 必须在 LINK 发布态中存在 |
| 4 | 聚合表达式中引用的 `field` / `where.path` 必须在目标 BO 的 MODEL 中存在 |
| 5 | `op` 与 `left`/`right` 的字面量类型必须兼容 |
| 6 | `itemsForWeight` 各项 weight 之和应接近 1.0（check_consistency.py 报 WARN，偏离超过 0.05 时触发） |
| 7 | `scoreRef` 引用的字段 code 必须在本派生对象的 fields 中存在 |

---

## ACTION_CHAIN Fragment

> 来源：`action-chain-fragment.schema.json`

### Schema 层面强制执行

| 编号 | 约束 |
|------|------|
| A | `trigger.type=OPERATION_COMPLETED` → `boCode` + `operationCode` 必填（allOf） |
| B | `trigger.type=ON_STATE_CHANGE` → `boCode` 必填（allOf） |
| C | `trigger.type=SCHEDULED` → `cronExpression` 必填（allOf） |
| D | `trigger.type=EVENT_RECEIVED` → `eventCode` 必填（allOf） |
| E | `stepType=DERIVATION_REFRESH` → `target` 必填（allOf）；`target.derivedCode` 有效性由 check_consistency.py 校验 |
| F | `stepType=BO_OPERATION` → `target` 必填（allOf）；`target.boCode` + `target.operationCode` 有效性由 check_consistency.py 校验 |
| G | `stepType=EVENT_PUBLISH` → `target` 必填（allOf）；`target.eventCode` 有效性由 check_consistency.py 校验 |

### check_consistency.py 强制执行

| 编号 | 约束 |
|------|------|
| 1 | `chains` 数组内 `chain.code` 必须唯一 |
| 2 | `steps` 数组内 `step.code` 必须唯一（链内） |
| 3 | `trigger.boCode` / `trigger.operationCode` 必须在 MODEL/OPERATION 中存在 |
| 4 | step `target.derivedCode` 必须在 DERIVATION 发布态中存在 |
| 5 | step `target.boCode` / `target.operationCode` 必须在 MODEL/OPERATION 中存在 |
| 6 | `dependsOn` 引用的 step code 必须在本链 steps 中存在 |
| 7 | 步骤依赖图不得存在循环 |
| 8 | `failurePolicy=COMPENSATE` 时，`compensateStepCode` 必须在本链 steps 中存在 |
| 9 | `condition` 若存在，必须通过 expression-ast.schema.json 校验 |
| 10 | `maxTriggerDepth=0` 时，链步骤的 `stepType=BO_OPERATION` 目标 Operation 不得触发其他动作链；`maxTriggerDepth>0` 时，发布服务校验触发链不存在循环 |
