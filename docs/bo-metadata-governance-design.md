# BO 元数据治理设计

## 1. 模型分层

BO 元数据治理分为三层：设计态 Fragment、发布态 BO Snapshot、派生态 Authz Model / UI / API。

```text
gov_bo_meta_fragment
    MODEL / VALIDATION / SECURITY / RULE / VIEW / OPERATION
        |
        | 合成、跨字段校验、计算 checksum
        v
gov_bo_meta_release
  schema_view_json，发布版本不可变
        |
        | 派生
        v
authz_meta_model.schema_view / UI Model / API Contract / Permission Items
```

## 2. Fragment 与发布态的区别

设计态 Fragment 不是从完整 `schema_view` 中截取一块 JSON，而是按治理职责重新组织的标准结构。

例如字段校验在发布态里嵌入字段：

```json
{
  "code": "scene_no",
  "validation": { "required": true, "unique": true, "max": 50 }
}
```

但在 `VALIDATION` Fragment 中按规则列表表达：

```json
{
  "rules": [
    { "entityCode": "scene_main", "fieldCode": "scene_no", "required": true, "unique": true, "max": 50 }
  ]
}
```

这样更适合编辑、审批、对比、校验和合成。

## 2.1 本体规则层

参考 Palantir 本体建模时，可以将四要素映射为：

| 本体要素 | BO 治理对应 | 说明 |
|----------|-------------|------|
| 对象类 | `MODEL.boCode`、`entities`、聚合结构 | 描述业务对象、实体、关系和聚合边界 |
| 属性 | `MODEL.entities[].attributes` | 描述字段、类型、主键、可过滤、展示等元数据 |
| 行为 | `OPERATION.operations` | 描述用户或系统可触发的业务动作、API、批量能力和风险等级 |
| 规则 | `RULE.rules` | 描述校验、状态、派生、权限、一致性和自动化规则 |

`VALIDATION` 不是完整 Rule，只是规则体系中的“输入校验/数据质量”子集。`SECURITY` 也不是完整 Rule，而是规则体系中的“权限、数据范围、字段控制”子集。为了兼容现有治理资产，`VALIDATION` 与 `SECURITY` 仍保留为专用 Fragment；但在本体语义上，它们应被视为 `RULE` 的专用投影。

推荐的规则分类如下：

| ruleType | 规则范围 | 典型例子 | 与现有 Fragment 的关系 |
|----------|----------|----------|--------------------------|
| `VALIDATION` | 字段级、表单级、导入级校验 | 必填、唯一、长度、枚举、跨字段日期关系 | 可由 `VALIDATION` Fragment 承载或派生到 `RULE` |
| `STATE` | 状态机、操作前置条件、可编辑性 | `DRAFT` 才允许编辑，`ACTIVE` 才允许归档 | 由 `RULE` 承载，并影响 `OPERATION` 是否可执行 |
| `DERIVATION` | 计算字段、汇总字段、投影属性 | 从产品清单汇总 `our_stage`、预计销量 | 由 `RULE` 承载，结果可写回 `MODEL` computed 字段或 `SECURITY.authzProjection` |
| `PERMISSION` | 权限策略、数据范围、字段控制 | 本部门可见、负责人可编辑、金额字段脱敏 | 可由 `SECURITY` Fragment 承载，并派生 PSP 策略模板 |
| `AUTOMATION` | 事件触发、同步、通知、流程编排 | 场景转 ACTIVE 后同步商机线索池 | 由 `RULE` 承载，运行时落到事件或流程服务 |
| `CONSISTENCY` | 聚合内不变量、跨实体一致性 | 有产品清单才能生效，删除主实体不得留下孤儿子实体 | 由 `RULE` 承载，发布时和应用层执行时都要校验 |

因此，`RULE` 是面向业务本体的统一规则目录；`VALIDATION` 和 `SECURITY` 是为了编辑体验、运行时派生和兼容 PSP 权限模型而保留的专业化入口。

## 3. 发布校验规则

发布前必须由应用层校验以下规则，不能只依赖 JSON Schema：

| 规则 | 说明 |
|------|------|
| 主实体唯一 | 有且仅有一个 `isPrimary=true` |
| 聚合根唯一 | 有且仅有一个 `aggregateRole=ROOT` |
| 主实体与聚合根一致 | 标准 BO 下 `isPrimary=true` 必须同时 `aggregateRole=ROOT` |
| 字段唯一 | 同一实体内 `attribute.code` 唯一 |
| 主键唯一 | 每个实体有且仅有一个 `isPk=true` |
| 父子关系完整 | 子实体必须声明 `parentEntityCode` 和 `parentRefField` |
| name/status 有效 | `nameField`、`statusField` 必须存在于主实体 |
| 行级字段有效 | `rowLevelRuleEntries` 必须存在且 `filterable=true` |
| API 路径规范 | `resourcePath` 和 `actionPath` 必须符合 API 治理 kebab-case 规范 |
| 聚合 API 范围 | `aggregateApiPolicy` 必须显式声明读、建、改、删对完整聚合或主实体的处理范围 |
| 子实体局部聚合 | 多级子实体若需要“本体接口 + 局部聚合接口”并存，必须声明 `entityApiPolicy` |
| batch 返回值 | 批量操作必须返回 `BatchResultDTO` |
| 安全默认值 | 无 DATA 策略命中默认建议 `NONE` |

### 3.1 聚合根 API 范围策略

聚合根 API 面向 BO 聚合，而不是只面向主表实体；但不同 HTTP 动作不能混用处理范围。推荐默认策略：

```json
{
    "listProjectionScope": "ROOT_SUMMARY",
    "readScope": "FULL_AGGREGATE",
    "createScope": "FULL_AGGREGATE",
    "updateScope": "ROOT_ENTITY_ONLY",
    "deleteScope": "CASCADE_AGGREGATE"
}
```

语义如下：

| 字段 | 语义 |
|------|------|
| `listProjectionScope=ROOT_SUMMARY` | 列表返回主实体字段加汇总/投影字段，不内嵌完整子实体 |
| `readScope=FULL_AGGREGATE` | 详情返回完整聚合，内嵌配置的子实体 |
| `createScope=FULL_AGGREGATE` | 创建可提交主实体和子实体，应用层同事务保持聚合一致性 |
| `updateScope=ROOT_ENTITY_ONLY` | 普通 PATCH 只更新主实体字段，避免误覆盖子实体 |
| `deleteScope=CASCADE_AGGREGATE` | 删除聚合根时级联逻辑删除或归档子实体 |
| `orphanPolicy` | 当 `deleteScope=ROOT_ENTITY_ONLY` 时声明孤儿子实体治理策略 |

如果业务确实需要整棵聚合替换，必须定义显式命令，例如 `POST /scenes/{id}/replace-aggregate`，不要复用普通 `PATCH /scenes/{id}`。

当同时需要“只处理主实体”和“按聚合整体处理”两类接口时，使用 `alternateAggregateApis` 声明额外端点。标准 API 负责默认语义，替代 API 负责另一类明确语义；禁止同一路径在不同调用场景下时而处理主实体、时而处理完整聚合。

示例：

```json
{
    "aggregateApiPolicy": {
        "readScope": "FULL_AGGREGATE",
        "createScope": "FULL_AGGREGATE",
        "updateScope": "ROOT_ENTITY_ONLY",
        "deleteScope": "CASCADE_AGGREGATE",
        "alternateAggregateApis": [
            {
                "code": "GET_SCENE_ROOT",
                "method": "GET",
                "path": "/scenes/{id}/root",
                "requestScope": "NONE",
                "responseScope": "ROOT_ENTITY_ONLY"
            },
            {
                "code": "PATCH_SCENE_AGGREGATE",
                "method": "PATCH",
                "path": "/scenes/{id}/aggregate",
                "requestScope": "FULL_AGGREGATE_PATCH",
                "responseScope": "FULL_AGGREGATE"
            }
        ]
    }
}
```

### 3.2 子实体局部聚合 API 范围策略

多级子实体也可能具有“局部聚合根”的治理语义。例如 `scene_product` 下挂 `scene_product_accessory` 和 `scene_annual_estimate`。此时子实体本身也需要区分：

- 实体本体接口：只处理产品清单行本身。
- 局部聚合接口：处理产品清单行 + 典配 + 年度测算。

使用 `entityApiPolicy` 声明：

```json
{
    "code": "scene_product",
    "entityApiPolicy": {
        "listProjectionScope": "ENTITY_SUMMARY",
        "readScope": "ENTITY_ONLY",
        "createScope": "ENTITY_AGGREGATE",
        "updateScope": "ENTITY_ONLY",
        "deleteScope": "CASCADE_CHILDREN",
        "orphanPolicy": "DENY_DELETE_WHEN_CHILD_EXISTS",
        "detailEmbedEntities": ["scene_product_accessory", "scene_annual_estimate"],
        "alternateEntityApis": [
            {
                "code": "GET_PRODUCT_AGGREGATE",
                "method": "GET",
                "path": "/scenes/{id}/products/{subId}/aggregate",
                "requestScope": "NONE",
                "responseScope": "ENTITY_AGGREGATE"
            }
        ]
    }
}
```

没有下级实体的普通子实体不需要显式配置，发布服务使用 Governance Profile 中的默认 `ENTITY_ONLY` 策略即可。

## 4. Governance Profile

schema 是治理能力模型，不应要求每个 BO 都重复填写所有参数。公司或项目应先确定一份治理参数文件，即 Governance Profile，再以它作为发布合成默认值。

推荐流程：

```text
governance-profile.default.json
                |
                | 提供默认 API、命名、安全、操作抽取规则
                v
MODEL / VALIDATION / SECURITY / RULE / VIEW / OPERATION Fragment
                |
                | 只声明业务差异项
                v
发布态完整 schema_view
```

默认参数文件位于：`government/arch/config/governance-profile.default.json`。

参数配置说明见：`government/arch/docs/governance-profile-guide.md`。Profile 文件内也包含 `usageGuide`，可直接查看每个参数的中文说明、选项、推荐值和影响范围。

建议项目启动前固定以下核心参数：

| 参数组 | 需要先定的默认值 |
|--------|------------------|
| API 响应 | `responseWrapper=ApiResponse`、`batchResultType=BatchResultDTO` |
| 路径命名 | 聚合根复数 kebab-case、操作 kebab-case |
| 聚合根 API | 默认 `read/create=FULL_AGGREGATE`，`update=ROOT_ENTITY_ONLY`，`delete=CASCADE_AGGREGATE` |
| 子实体 API | 默认 `ENTITY_ONLY`，多级子实体按需启用 `ENTITY_AGGREGATE` |
| 删除孤儿策略 | 默认 `DENY_DELETE_WHEN_CHILD_EXISTS` |
| 主实体规则 | `isPrimary=true` 必须对应 `aggregateRole=ROOT` |
| 业务唯一键 | 默认 `{bo_snake}_no`，允许业务覆盖 |
| 行级安全 | 默认 `rowFallbackScope=NONE` |
| 原型操作抽取 | 默认要求 `prototypeRefs`，过滤纯 UI utility |

## 5. Java 核心片段

以下代码为核心实现片段，真实落地时应放在应用层服务内，保持事务边界在 Application Service。

### 5.1 Fragment 类型

```java
public enum BoMetaType {
    MODEL, VALIDATION, SECURITY, RULE, VIEW, OPERATION
}
```

`RULE` 是本体规则层。`VALIDATION` 与 `SECURITY` 可以继续作为独立 Fragment 保存和审批，但发布服务应能把它们视为 `RULE` 的专用子集，生成统一规则目录，供发布校验、权限派生、API 合同和运行时规则执行引用。

### 5.2 发布入口

```java
@Transactional
public BoMetaRelease publish(String tenantId, String appCode, String boCode, int draftVersion) {
    GovernanceProfile profile = profileRepository.findDefaultProfile(tenantId, appCode);
    Map<BoMetaType, JsonNode> fragments = fragmentRepository
        .findDraftFragments(tenantId, appCode, boCode, draftVersion)
        .stream()
        .collect(Collectors.toMap(BoMetaFragment::getMetaType, BoMetaFragment::getContentJson));

    requireAllFragments(fragments);
    BoSchemaView schemaView = assembler.assemble(profile, fragments);
    validator.validate(schemaView);

    String schemaJson = objectMapper.writeValueAsString(schemaView);
    String checksum = sha256(canonicalJson(schemaJson));
    int nextVersion = releaseRepository.nextReleaseVersion(tenantId, appCode, boCode);

    releaseRepository.clearCurrent(tenantId, appCode, boCode);
    BoMetaRelease release = BoMetaRelease.create(
        tenantId, appCode, boCode, schemaView.getBoName(), nextVersion,
        draftVersion, schemaView.getSchemaVersion(), schemaJson,
        sourceFragmentsJson(fragments), checksum);
    releaseRepository.save(release);

    fragmentRepository.markPublished(tenantId, appCode, boCode, draftVersion);
    authzBoMetaModelSyncService.sync(release);
    derivedModelPublisher.publishAll(release);
    return release;
}
```

### 5.3 Fragment 合成

```java
public BoSchemaView assemble(GovernanceProfile profile, Map<BoMetaType, JsonNode> fragments) {
    ModelFragment model = convert(fragments.get(BoMetaType.MODEL), ModelFragment.class);
    ValidationFragment validation = convert(fragments.get(BoMetaType.VALIDATION), ValidationFragment.class);
    SecurityFragment security = convert(fragments.get(BoMetaType.SECURITY), SecurityFragment.class);
    RuleFragment rule = convertOptional(fragments.get(BoMetaType.RULE), RuleFragment.class);
    ViewFragment view = convert(fragments.get(BoMetaType.VIEW), ViewFragment.class);
    OperationFragment operation = convert(fragments.get(BoMetaType.OPERATION), OperationFragment.class);

    BoSchemaView result = new BoSchemaView();
    applyProfileDefaults(result, profile);
    result.setBoCode(model.getBoCode());
    result.setBoName(model.getBoName());
    result.setSchemaVersion("2.0");
    result.setApiConfig(model.getApiConfig());
    result.setBoConfig(model.getBoConfig());
    result.setEntities(copyEntities(model.getEntities()));
    result.setListViewConfig(view.getListViewConfig());
    List<BoOperation> virtualOperations = deriveStandardCrudOperations(model, profile);
    result.setOperations(mergeOperations(virtualOperations, operation.getOperations()));

    applyValidation(result, validation);
    applySecurity(result, security);
    applyRules(result, mergeRuleSubsets(validation, security, rule));
    applyView(result, view);
    return result;
}
```

`deriveStandardCrudOperations` 根据 `MODEL.apiConfig`、聚合根策略、子实体策略和 alternate API 自动生成标准 CRUD 虚拟 Operation。`mergeOperations` 以显式 OPERATION Fragment 为优先级：同一路由或同一标准语义被显式声明时，保留显式 Operation 的 `code`、`authzAction`、`prototypeRefs` 和展示配置。

`mergeRuleSubsets` 的职责是把 `VALIDATION`、`SECURITY` 中已经专业化维护的规则投影进统一规则目录，同时保留 `RULE` Fragment 中声明的状态、派生、一致性和自动化规则。合并后的规则目录可用于：

- 发布校验：检查规则引用的实体、字段、状态、操作是否存在。
- API 派生：把操作前置条件、风险等级、批量限制映射到 API 合同。
- Authz 派生：把 `PERMISSION` 类规则映射为 PSP 的 DATA / STATE / ENV / FIELD 策略模板。
- 运行时执行：由应用服务在事务内执行一致性、状态、派生和自动化规则。

### 5.3.1 Operation 从原型按钮抽取

`OPERATION` Fragment 可以从界面原型按钮抽取，但必须区分业务操作和纯 UI 交互。

| 原型交互 | 是否生成 Operation | 说明 |
|----------|--------------------|------|
| 新建场景、导入、导出、编辑场景 | 是 | BO 级或全局业务操作 |
| 新建产品清单、编辑产品清单、删除产品清单 | 是 | 聚合内子实体操作 |
| 新增配件、删除配件、年度测算新增行、年度测算删除行 | 是 | 可合并为产品清单维护命令，也可派生成子实体操作 |
| 竞对调整、保存调整、新建竞争对手、删除竞争对手 | 是 | 竞对年度调整命令 |
| 新增团队成员、查看、编辑、删除 | 是 | 团队成员子实体操作 |
| 刷新、列设置、全屏、分页、Tab 切换、年份切换、弹窗关闭 | 否 | UI utility，不进入 BO Operation |

抽取后的 Operation 应保留 `prototypeRefs`，用于追溯按钮来源：

```json
{
    "code": "CREATE_TEAM_MEMBER",
    "name": "新增团队成员",
    "scope": "ENTITY",
    "entityCode": "scene_team_member",
    "prototypeRefs": [
        {
            "file": "government/场景管理/场景详情.html",
            "label": "新增团队成员",
            "event": "openAtmDialog()",
            "positionHint": "详情页团队成员 Tab 顶部"
        }
    ]
}
```

原型按钮是 Operation 候选源，不是最终 API 合同。发布校验仍需根据 DDD 聚合边界、API 路径规范、批量语义和返回值规范进行二次治理。

### 5.4 发布校验

```java
public void validate(BoSchemaView schemaView) {
    List<BoEntity> entities = schemaView.getEntities();
    BoEntity primary = exactlyOne(entities, BoEntity::isPrimary, "BO must have exactly one primary entity");
    BoEntity root = exactlyOne(entities, e -> e.getAggregateRole() == AggregateRole.ROOT,
        "BO must have exactly one aggregate root");

    if (!primary.getCode().equals(root.getCode())) {
        throw new GovernanceException("Standard BO requires isPrimary entity to be aggregate ROOT");
    }

    for (BoEntity entity : entities) {
        assertUnique(entity.getAttributes(), BoAttribute::getCode, "Duplicate attribute code in " + entity.getCode());
        exactlyOne(entity.getAttributes(), BoAttribute::isPk, "Entity must have exactly one primary key: " + entity.getCode());

        if (entity.getAggregateRole() != AggregateRole.ROOT) {
            requireText(entity.getParentEntityCode(), "Sub entity must declare parentEntityCode");
            requireText(entity.getParentRefField(), "Sub entity must declare parentRefField");
            requireAttribute(entity, entity.getParentRefField());
        }
    }

    requireAttribute(primary, schemaView.getBoConfig().getNameField());
    if (schemaView.getBoConfig().getStatusField() != null) {
        requireAttribute(primary, schemaView.getBoConfig().getStatusField());
    }

    validateApiContract(schemaView);
    validateRowSecurity(schemaView);
}
```

### 5.5 Authz Model 派生

`SECURITY` Fragment 到 PSP 的映射不是单一步骤：`authzProjection` 合并到 `authz_bo_meta_model.schema_json` 中 SCENE 这条 BO 元数据的安全投影，`rowSecurity` 合并进 BO 发布态行级字段，`fieldSecurity` 合并进 BO 发布态字段控制元数据。详细运行时关系见 [security-fragment-psp-mapping.md](security-fragment-psp-mapping.md)。

```java
public AuthzSchemaView deriveAuthzModel(BoSchemaView boSchemaView, SecurityFragment security) {
    AuthzProjection projection = security.getAuthzProjection();
    AuthzSchemaView authz = new AuthzSchemaView();
    authz.setCategory("RESOURCE");
    authz.setDescription(projection.getDescription());
    authz.setUsageNote(projection.getUsageNote());

    List<AuthzAttribute> attrs = projection.getAttributes().stream()
        .map(rule -> {
            BoAttribute source = findSourceAttribute(boSchemaView, rule.getSource());
            AuthzAttribute attr = new AuthzAttribute();
            attr.setCode(rule.getCode());
            attr.setName(rule.getName() != null ? rule.getName() : source.getName());
            attr.setType(rule.getType() != null ? rule.getType() : source.getType());
            attr.setPk(rule.isPk());
            attr.setFilterable(rule.isFilterable());
            attr.setNullable(rule.isNullable());
            attr.setOnMissingValue(rule.getOnMissingValue());
            attr.setAllowedValues(rule.getAllowedValues());
            attr.setValueRef(rule.getValueRef());
            attr.setReferenceModel(rule.getReferenceModel());
            attr.setDisplayOrder(rule.getDisplayOrder());
            attr.setDisplayGroup(rule.getDisplayGroup());
            attr.setDescription(rule.getDescription());
            attr.setI18nKey(rule.getI18nKey());
            attr.setValueExamples(rule.getValueExamples());
            return attr;
        })
        .collect(Collectors.toList());

    authz.setAttributes(attrs);
    return authz;
}
```

### 5.6 API Contract 派生

```java
public ApiContract deriveApiContract(BoSchemaView schemaView) {
    String root = schemaView.getApiConfig().getResourcePath();
    ApiContract contract = new ApiContract(root);

    contract.add("POST", root, "create", "ApiResponse<SceneDTO>");
    contract.add("GET", root, "list", "ApiResponse<PageResult<SceneDTO>>");
    contract.add("POST", root + "/search", "search", "ApiResponse<PageResult<SceneDTO>>");
    contract.add("GET", root + "/{id}", "get", "ApiResponse<SceneDTO>");
    contract.add("POST", root + "/batch/query", "batchQuery", "ApiResponse<List<SceneDTO>>");
    contract.add("PATCH", root + "/{id}", "update", "ApiResponse<SceneDTO>");
    contract.add("PATCH", root + "/batch", "batchUpdate", "ApiResponse<BatchResultDTO>");
    contract.add("DELETE", root + "/{id}", "delete", "ApiResponse<Void>");
    contract.add("DELETE", root + "/batch", "batchDelete", "ApiResponse<BatchResultDTO>");

    for (BoEntity entity : schemaView.getSubEntities()) {
        String path = root + "/{id}/" + entity.getRouteSegment();
        contract.add("POST", path, "create" + entity.getJavaName(), "ApiResponse<" + entity.getDtoName() + ">");
        contract.add("GET", path, "list" + entity.getJavaName(), "ApiResponse<List<" + entity.getDtoName() + ">>");
        contract.add("PATCH", path + "/{subId}", "update" + entity.getJavaName(), "ApiResponse<" + entity.getDtoName() + ">");
        contract.add("DELETE", path + "/{subId}", "delete" + entity.getJavaName(), "ApiResponse<Void>");
    }

    for (BoOperation op : schemaView.getOperations()) {
        contract.addOperation(resolvePath(schemaView, op), op);
    }
    return contract;
}
```

## 6. 发布同步建议

发布成功后推荐同步顺序：

1. 写入 `gov_bo_meta_release`，并设置当前版本。
2. 更新或插入 `authz_bo_meta_model.schema_json`。
3. 在 `authz_bo_meta_model.schema_json` 中写入 `RES_SCENE` 安全投影，作为该 BO 元数据的 `res.*` 属性契约。
4. 派生权限项、UI 模型、API 合同。
5. 记录审计日志，包含 releaseVersion、checksum、发布人、来源 fragment 版本。

### 6.1 权限项派生建议

PSP 权限项从 `authz_bo_meta_model.schema_json` 中的 BO 与 Operation 定义派生，但不能直接把界面按钮或请求阶段当成权限项。发布服务应使用 `operation.authzAction` 作为 PSP `act_code`，并按 `RES_DATA_BO + authz_bo_meta_model.id + authzAction` 去重生成权限项。`authzAction` 是多个 Operation 归并到同一权限项的聚合键，不是 API 到某条权限项 ID 的硬绑定。

发布态可以生成 `permissionItem -> operations` 的反向派生关系，便于授权配置页面展示“一项权限控制哪些操作”。该关系应由 Operation 分组生成，不应在设计态手工维护为第二套主数据。

发布态 Operation 包含两类来源：

1. 标准 CRUD 虚拟 Operation：由 `MODEL.apiConfig`、`aggregateApiPolicy`、`entityApiPolicy`、`alternateAggregateApis`、`alternateEntityApis` 自动生成。
2. 显式 Operation：来自 `OPERATION` Fragment，通常用于自定义业务命令、标准 CRUD 的业务化覆盖、原型按钮追溯和特殊权限动作。

关键规则：

1. 查看列表、查看详情和查看态数据请求统一使用 `READ`，`VIEW` 只作为别名。
2. 点击编辑、进入编辑态、保存编辑结果统一使用 `UPDATE`，`EDIT` 只作为别名，不生成 `SAVE`。
3. 点击新增、打开新增弹窗、保存新增结果统一使用 `CREATE`，保存只是创建命令的提交阶段。
4. 提交审批、发布、归档、作废、竞对调整等独立业务行为使用独立 `authzAction`。
5. 同一 BO 下相同 `authzAction` 只生成一条权限项；需要 operation 级细分时，要么配置独立 `authzAction`，要么扩展 PSP 权限项模型增加 operation 维度。
