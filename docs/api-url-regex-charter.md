# API URL 路径正则提取宪章

> **目的**：定义 API URL 的合法形态，以及如何通过正则表达式从 URL 中准确提取 `boCode` 和 `operation`。
> **适用对象**：发布服务、权限拦截器、API 网关路由解析、BO 定位与 Operation 匹配。
> **依据**：`api-governance-charter.md` 第二章～第五章。

> **文档裁决地位（NON-NEGOTIABLE）**：本文件是 API URL 解析的**权威实现规范**（正则+伪代码，零歧义）。
> 当 `api-governance-charter.md` 的文字描述存在歧义时，**以本文件的算法定义为准**。
> 但当本文件与 charter 均明确且结论冲突时，进入人工确认。裁决链见 `api-governance-charter.md` 第零章。
>
> 本文件作为算法级实现规范，在 charter/mapping 有滞后描述时可主动发现并提请注意。修正应优先对齐本文件的算法定义，如有争议则进入人工确认。

---

## 一、URL 路径标记（Token）定义

| Token | 正则约束 | 来源 | 示例 |
|-------|---------|------|------|
| `{resource}` | `^[a-z][a-z0-9-]*$` | `boCode` + `resourcePath` 规则，首位小写字母，后续字母数字或 `-` | `scenes`、`customer-relations` |
| `{id}` | `^\d+$`（Snowflake Long） | `apiConfig.idType=LONG` | `2068959871393136600` |
| `{routeSegment}` | `^[a-z][a-z0-9-]*$` | entity 级 `routeSegment`，首位小写字母 | `products`、`team-members` |
| `{subId}` | `^\d+$` | 子实体主键 | `2068959871393136601` |
| `{actionPath}` | `^[a-z][a-z0-9-]*$` | 自定义操作的 `actionPath` | `submit`、`publish`、`adjust-rival` |

### 保留关键字（不可用作 `routeSegment` / `actionPath`）

以下值在特定路径位置具有系统语义，**MUST NOT** 被 BO 定义为 `routeSegment` 或 `actionPath`：

```
search, batch, query, root, edit, aggregate, replace-aggregate
```

### scope 术语（源自 `OPERATION` Fragment）

| `scope` 值 | 含义 | URL 路由中 `{id}` 的位置 |
|------------|------|--------------------------|
| `BO` | 操作作用于聚合根级别（可连带其子实体） | 聚合根的 ID，在 `resourcePath` 之后 |
| `ENTITY` | 操作仅作用于聚合根下的单个子实体 | 聚合根的 ID + 子实体的 `subId`，嵌套路由 |
| `GLOBAL` | 全局操作，不绑定特定资源实例 | 无 `{id}`，仅 `resourcePath` + `actionPath` |

### `aggregateApiPolicy` 配置项（源自 `MODEL` Fragment）

控制聚合根各 HTTP 动作的处理范围，决定请求体可提交哪些实体、响应体返回哪些层级：

| 配置项 | 作用域 | 枚举值 | 说明 |
|--------|--------|--------|------|
| `listProjectionScope` | 列表查询（`GET /{resource}`、`POST /{resource}/search`） | `ROOT_SUMMARY`（默认）、`ROOT_ENTITY_ONLY`、`FULL_AGGREGATE` | 列表行返回层级。`ROOT_SUMMARY`=主实体+统计列（如产品数），不内嵌子实体数组；`ROOT_ENTITY_ONLY`=仅主实体字段 |
| `readScope` | 单条详情（`GET /{resource}/{id}`） | `FULL_AGGREGATE`（默认）、`ROOT_ENTITY_ONLY` | 详情返回层级。`FULL_AGGREGATE`=主实体+全部子实体树；`ROOT_ENTITY_ONLY`=仅主实体，子实体按需独立加载 |
| `createScope` | 创建（`POST /{resource}`） | `FULL_AGGREGATE`（默认）、`ROOT_ENTITY_ONLY` | 创建请求可提交范围。`FULL_AGGREGATE`=可一次性提交主实体+子实体；`ROOT_ENTITY_ONLY`=仅主实体，子实体后续独立创建 |
| `updateScope` | 更新（`PATCH /{resource}/{id}`） | `ROOT_ENTITY_ONLY`（默认）、`FULL_AGGREGATE_PATCH`、`FULL_AGGREGATE_REPLACE` | 更新处理范围。`ROOT_ENTITY_ONLY`=仅改主实体字段；`FULL_AGGREGATE_PATCH`=主实体+子实体增量补丁；`FULL_AGGREGATE_REPLACE`=整棵聚合树先删后建 |
| `deleteScope` | 删除（`DELETE /{resource}/{id}`） | `CASCADE_AGGREGATE`（默认）、`ROOT_ENTITY_ONLY` | 删除处理范围。`CASCADE_AGGREGATE`=级联删除全部子实体；`ROOT_ENTITY_ONLY`=仅删主实体，须配合 `orphanPolicy` |
| `orphanPolicy` | 仅当 `deleteScope=ROOT_ENTITY_ONLY` 时生效 | `DENY_DELETE_WHEN_CHILD_EXISTS`（默认）、`KEEP_CHILDREN_AS_HISTORY`、`DETACH_CHILDREN`、`MANUAL_CLEANUP_REQUIRED` | 遗留子实体处置策略 |
| `searchEnabled` | 复杂查询 | `true`/`false`（默认 `true`） | 为 `true` 时生成 `POST /{resource}/search` 虚拟 Operation |
| `batchEnabled` | 批量操作 | `true`/`false`（默认 `true`） | 为 `true` 时生成批量类虚拟 Operation（BATCH_CREATE/UPDATE/DELETE/QUERY） |

> **`updateScope` 与 URL 变体的关系**：当 `updateScope=ROOT_ENTITY_ONLY`（默认）时，`PATCH /{resource}/{id}` 仅改主实体；若业务**同时**需要聚合级操作，通过 `alternateAggregateApis` 显式声明 `PATCH /{resource}/{id}/aggregate`（`FULL_AGGREGATE_PATCH`）或 `POST /{resource}/{id}/replace-aggregate`（`FULL_AGGREGATE_REPLACE`）。当 `updateScope=FULL_AGGREGATE_PATCH` 时，默认 PATCH 已是聚合增量更新，`/aggregate` 变体冗余。

### `entityApiPolicy` 配置项（源自 `MODEL` Fragment）

控制子实体各 HTTP 动作的处理范围，与 `aggregateApiPolicy` 结构对称：

| 配置项 | 作用域 | 枚举值 | 说明 |
|--------|--------|--------|------|
| `listProjectionScope` | 子实体列表（`GET /.../{routeSegment}`） | `ENTITY_SUMMARY`（默认）、`ENTITY_ONLY`、`ENTITY_AGGREGATE` | 子实体列表行返回层级 |
| `readScope` | 子实体单条（`GET /.../{routeSegment}/{subId}`） | `ENTITY_ONLY`（默认）、`ENTITY_AGGREGATE` | `ENTITY_AGGREGATE`=当前子实体+下级子孙实体 |
| `createScope` | 子实体创建（`POST /.../{routeSegment}`） | `ENTITY_ONLY`（默认）、`ENTITY_AGGREGATE` | |
| `updateScope` | 子实体更新（`PATCH /.../{routeSegment}/{subId}`） | `ENTITY_ONLY`（默认）、`ENTITY_AGGREGATE_PATCH`、`ENTITY_AGGREGATE_REPLACE` | `ENTITY_AGGREGATE_PATCH`=当前子实体+下级增量补丁 |
| `deleteScope` | 子实体删除（`DELETE /.../{routeSegment}/{subId}`） | `ENTITY_ONLY`（默认）、`CASCADE_CHILDREN` | `CASCADE_CHILDREN`=级联删除下级子实体 |
| `orphanPolicy` | 仅当 `deleteScope=ENTITY_ONLY` 时生效 | 同 `aggregateApiPolicy.orphanPolicy` | 遗留下级子实体处置策略 |

### API 设计前置流程（NON-NEGOTIABLE）

> 在为任何聚合定义 API 路径和 Operation 之前，**MUST 先完成以下配置**。未完成配置的 BO 不得进入 API 定义阶段。

```
步骤 1  识别聚合结构
        └─ 定义 entities（aggregateRole、parentEntityCode、routeSegment）
           └─ 验证：有且仅有一个 isPrimary=true 且 aggregateRole=ROOT

步骤 2  配置 aggregateApiPolicy（MUST）
        └─ listProjectionScope、readScope、createScope、updateScope、deleteScope
        └─ orphanPolicy（仅当 deleteScope=ROOT_ENTITY_ONLY 时）
        └─ searchEnabled、batchEnabled
           └─ 验证：每个 Scope 值已基于聚合业务特征显式声明，不依赖默认值

步骤 3  配置 entityApiPolicy（仅有下级子实体的子实体 MUST 配置）
        └─ 对每个拥有下级子实体的 SUB_ENTITY 配置 readScope、updateScope 等
        └─ 无下级的普通子实体可使用 Governance Profile 默认 ENTITY_ONLY

步骤 4  判断是否需要 alternateAggregateApis / alternateEntityApis 变体
        └─ updateScope=ROOT_ENTITY_ONLY 且业务需要聚合更新 → 声明 /aggregate
        └─ 业务需要整体替换 → 声明 /replace-aggregate
        └─ readScope=FULL_AGGREGATE 且业务需要轻量视图 → 声明 /root
        └─ createScope=FULL_AGGREGATE 且业务需要仅创建主实体 → 声明 POST /{resource}/root

步骤 5  定义 OPERATION Fragment
        └─ 自定义业务操作（STATE_CHANGE / CUSTOM）
        └─ 需要原型追溯的标准 CRUD 覆盖项

步骤 6  发布服务自动生成
        └─ 标准 CRUD 虚拟 Operation + 路由解析表 + 权限项
```

| 步骤 | 是否必须 | 跳过后果 |
|------|---------|---------|
| 步骤 1 | MUST | 无法确定聚合结构，API 路由无意义 |
| 步骤 2 | MUST | 虚拟 Operation 无法生成，请求/响应范围未定义 |
| 步骤 3 | 有下级子实体时 MUST | 子实体局部聚合接口缺失，多级嵌套行为不确定 |
| 步骤 4 | 视业务需求 | 缺失变体接口，同一路径被迫承载双重语义（违反宪章 §1.3） |
| 步骤 5 | 有自定义操作时 MUST | 业务流程操作无法从 URL 解析（违反宪章 §4.1） |
| 步骤 6 | 自动 | — |

---

## 二、URL 路径形态全集

以下按"路径深度"分组，覆盖宪章中所有合法的 API URL。

> **注**：下表中 `PATCH` 标注的是治理文档中的 REST 语义 Method。在 Controller 实现层，`PATCH` 降级为 `@PostMapping` + 动作路径（见 `copilot-instructions.md` §3.3），对应路径为在原 PATCH 路径后追加 `/update`（如 `PATCH /{resource}/{id}` → `POST /{resource}/{id}/update`、`PATCH /{resource}/batch` → `POST /{resource}/batch/update`）。降级路径由发布服务在路由解析时自动识别为同一 Operation，**不在设计态 URL 形态全集中作为独立条目**。

### 2.1 深度 1：`/{resource}`

| # | Method | 路径 | operation | 说明 |
|---|--------|------|-----------|------|
| A1 | GET | `/{resource}` | `LIST` | 列表 |
| A2 | POST | `/{resource}` | `CREATE` | 创建 |
| A3 | POST | `/{resource}/root` | `CREATE_ROOT` | 主实体创建，仅当 `createScope=FULL_AGGREGATE` 且业务同时需要仅创建主实体时显式声明 |
| A4 | POST | `/{resource}/publish` | 业务操作 | 全局操作（如发布、统计）：`POST /{resource}/{actionPath}` |

### 2.2 深度 2：`/{resource}/{segment2}`

| # | Method | 路径 | operation | 说明 |
|---|--------|------|-----------|------|
| B1 | GET | `/{resource}/{id}` | `READ` | 详情 |
| B2 | PATCH | `/{resource}/{id}` | `UPDATE` | 标准更新 |
| B3 | DELETE | `/{resource}/{id}` | `DELETE` | 删除 |
| B4 | POST | `/{resource}/search` | `SEARCH` | 复杂查询（segment2=`search`） |
| B5 | POST | `/{resource}/batch` | `BATCH_CREATE` | 批量创建 |
| B6 | PATCH | `/{resource}/batch` | `BATCH_UPDATE` | 批量更新 |
| B7 | DELETE | `/{resource}/batch` | `BATCH_DELETE` | 批量删除 |

### 2.3 深度 3：`/{resource}/{segment2}/{segment3}`

| # | Method | 路径 | operation | 说明 |
|---|--------|------|-----------|------|
| C1 | GET | `/{resource}/{id}/root` | `READ_ROOT` | 主实体详情，仅当 `readScope=FULL_AGGREGATE` 且业务同时需要仅主实体轻量视图时显式声明 |
| C2 | GET | `/{resource}/{id}/edit` | `READ_EDIT` | 编辑态读数据，仅当编辑表单投影与 B1 详情投影不同时显式声明 |
| C3 | PATCH | `/{resource}/{id}/aggregate` | `UPDATE_AGGREGATE` | 聚合增量更新，`requestScope=FULL_AGGREGATE_PATCH`，仅当 `updateScope=ROOT_ENTITY_ONLY` 时才有意义 |
| C4 | POST | `/{resource}/{id}/replace-aggregate` | `REPLACE_AGGREGATE` | 聚合整体替换，`requestScope=FULL_AGGREGATE_REPLACE`，高风险，需独立权限和审计 |
| C5 | POST | `/{resource}/batch/query` | `BATCH_QUERY` | 批量按 ID 查询 |
| C6 | POST | `/{resource}/batch/{actionPath}` | 批量业务操作 | 如 `POST /scenes/batch/publish` |
| C7 | POST | `/{resource}/{id}/{routeSegment}` | `CREATE_SUB` | 子实体创建 |
| C8 | GET | `/{resource}/{id}/{routeSegment}` | `READ_SUB` | 子实体列表 |
| C9 | POST | `/{resource}/{id}/{actionPath}` | 单条业务操作 | 如 `POST /scenes/123/submit` |

> **B2 vs C3/C4 的关系**：`PATCH /{resource}/{id}`（B2）的默认语义由 `aggregateApiPolicy.updateScope` 控制。当 `updateScope=ROOT_ENTITY_ONLY`（默认）时，B2 仅更新主实体；若业务**同时**需要聚合级操作能力，通过 `alternateAggregateApis` 显式声明 C3（增量补丁）或 C4（整体替换）。两者与 B2 **并存**，而非互斥。当 `updateScope=FULL_AGGREGATE_PATCH` 时，B2 本身已是聚合增量更新，C3 冗余。

### 2.4 深度 4：`/{resource}/{segment2}/{segment3}/{segment4}`

| # | Method | 路径 | operation | 说明 |
|---|--------|------|-----------|------|
| D1 | PATCH | `/{resource}/{id}/{routeSegment}/{subId}` | `UPDATE_SUB` | 子实体更新 |
| D2 | DELETE | `/{resource}/{id}/{routeSegment}/{subId}` | `DELETE_SUB` | 子实体删除 |
| D3 | POST | `/{resource}/{id}/{routeSegment}/batch` | `BATCH_CREATE_SUB` | 子实体批量创建 |
| D4 | PATCH | `/{resource}/{id}/{routeSegment}/batch` | `BATCH_UPDATE_SUB` | 子实体批量更新 |
| D5 | DELETE | `/{resource}/{id}/{routeSegment}/batch` | `BATCH_DELETE_SUB` | 子实体批量删除 |
| D6 | POST | `/{resource}/{id}/{routeSegment}/adjust-quantity` | 子实体业务操作 | 子实体自定义操作：`POST /.../{routeSegment}/{actionPath}`，如调整数量、分配成员 |
| D7 | POST | `/{resource}/{id}/{routeSegment}/batch/{actionPath}` | 子实体批量业务操作 | 子实体批量自定义操作：`POST /.../{routeSegment}/batch/{actionPath}` |
| D8 | POST | `/{resource}/{id}/{routeSegment}/{subId}` | 子实体业务操作 | 无显式 actionPath 的子实体操作 |

> **D6 vs D1 歧义**：`segment4` 可能是 `subId`（标准 CRUD）或 `actionPath`（自定义）。
> 解决：若 `segment4` 不匹配 `^\d+$`（非数字），则必为 `actionPath`；若匹配数字，优先按标准 CRUD 匹配（D1/D2），未命中时回退到自定义匹配（D8）。

### 2.5 深度 5：`/{resource}/{id}/{routeSegment}/{subId}/{segment5}`

| # | Method | 路径 | operation | 说明 |
|---|--------|------|-----------|------|
| E1 | GET | `/{resource}/{id}/{routeSegment}/{subId}/aggregate` | `READ_SUB_AGGREGATE` | 子实体聚合详情，仅当子实体 `readScope=ENTITY_AGGREGATE` 且与普通列表投影不同时使用 |
| E2 | PATCH | `/{resource}/{id}/{routeSegment}/{subId}/aggregate` | `UPDATE_SUB_AGGREGATE` | 子实体聚合更新，语义由实体 `updateScope` 控制 |
| E3 | POST | `/{resource}/{id}/{routeSegment}/{subId}/{actionPath}` | 子实体业务操作 | 如 `POST /scenes/123/products/456/reassign` |

## 三、正则提取规则

### 3.1 boCode 提取

**boCode 恒为 URL 路径的第一段**（去掉前导 `/` 后按 `/` 分割的第一个 segment）。

```regex
# 从完整 URL 路径提取 boCode
^/([a-z][a-z0-9-]+)(?:/|$)
```

| 输入 | 捕获组 1 |
|------|----------|
| `/scenes` | `scenes` |
| `/scenes/123` | `scenes` |
| `/customer-relations/456/team-members` | `customer-relations` |
| `/scenes/123/products/789` | `scenes` |

**发布服务匹配**：`boCode` → 查找 `authz_bo_meta_model` → 获得 `resourcePath`、`entities[]`（含所有 `routeSegment`）、`OPERATION` 列表。

### 3.2 路径分类正则（按优先级从高到低匹配）

发布服务对 URL 路径进行分段匹配，匹配顺序为**从具体到通用**（长路径优先、保留关键字优先）：

---

#### 优先级 1：保留关键字路径（不依赖 BO 元数据即可判定）

```regex
# B4: SEARCH — POST /{resource}/search
^/(?<bo>[a-z][a-z0-9-]+)/search$

# A3: CREATE_ROOT — POST /{resource}/root
^/(?<bo>[a-z][a-z0-9-]+)/root$

# B5/B6/B7: batch root — /{resource}/batch
# B5: POST → BATCH_CREATE; B6: PATCH → BATCH_UPDATE; B7: DELETE → BATCH_DELETE
# PATCH→POST 降级路径 POST /{resource}/batch/update 由实现层补偿，正则视为 B6 同义
^/(?<bo>[a-z][a-z0-9-]+)/batch$

# C5: BATCH_QUERY — POST /{resource}/batch/query
^/(?<bo>[a-z][a-z0-9-]+)/batch/query$

# C6: BO batch custom — POST /{resource}/batch/{actionPath}
# (需排除 query 保留字)
^/(?<bo>[a-z][a-z0-9-]+)/batch/(?<action>[a-z][a-z0-9-]+)$
```

---

#### 优先级 2：聚合根 CRUD（含变体，不依赖 `routeSegment` 即可判定）

```regex
# A1: LIST — GET /{resource}
^/(?<bo>[a-z][a-z0-9-]+)$

# A2: CREATE — POST /{resource}
^/(?<bo>[a-z][a-z0-9-]+)$

# B1: READ — GET /{resource}/{id}
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)$

# B2: UPDATE — PATCH /{resource}/{id}
# B3: DELETE — DELETE /{resource}/{id}
# NOTE: POST /{resource}/{id} 不是合法路径；自定义操作 MUST 有 actionPath
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)$

# C1: READ_ROOT — GET /{resource}/{id}/root
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/root$

# C2: READ_EDIT — GET /{resource}/{id}/edit
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/edit$

# C3: UPDATE_AGGREGATE — PATCH /{resource}/{id}/aggregate
# 仅当 updateScope=ROOT_ENTITY_ONLY 且业务需要聚合增量更新时通过 alternateAggregateApis 声明
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/aggregate$

# C4: REPLACE_AGGREGATE — POST /{resource}/{id}/replace-aggregate
# 高风险，需独立权限和审计
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/replace-aggregate$
```

---

#### 优先级 3：子实体路由（需 BO 元数据提供 `routeSegment` 集合）

> **关键**：发布服务先查 BO 的快照数据，获取所有 `routeSegment` 的集合 `R`。

```regex
# C7: 子实体 CREATE — POST /{resource}/{id}/{routeSegment}
# C8: 子实体 LIST — GET /{resource}/{id}/{routeSegment}
# 前提：segment3 ∈ R（BO 已知的 routeSegment 集合）
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)$

# D1/D2: 子实体单条操作 — /{resource}/{id}/{routeSegment}/{subId}
# D1: PATCH → UPDATE; D2: DELETE → DELETE
# PATCH→POST 降级路径 POST /.../{subId}/update 由实现层补偿
# 前提：segment3 ∈ R, segment4 为数字
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/(?<subId>\d+)$

# D3/D4/D5: 子实体 batch — /{resource}/{id}/{routeSegment}/batch
# D3: POST → BATCH_CREATE; D4: PATCH → BATCH_UPDATE; D5: DELETE → BATCH_DELETE
# PATCH→POST 降级路径 POST /.../batch/update 由实现层补偿
# 前提：segment3 ∈ R
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/batch$

# E1: 子实体聚合详情 — GET /{resource}/{id}/{routeSegment}/{subId}/aggregate
# 前提：segment3 ∈ R
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/(?<subId>\d+)/aggregate$

# E2: 子实体聚合更新 — PATCH /{resource}/{id}/{routeSegment}/{subId}/aggregate
# PATCH→POST 降级路径 POST /.../{subId}/aggregate 由实现层补偿
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/(?<subId>\d+)/aggregate$

# D7: ENTITY batch custom — POST /{resource}/{id}/{routeSegment}/batch/{actionPath}
# 前提：segment3 ∈ R
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/batch/(?<action>[a-z][a-z0-9-]+)$

# E3: ENTITY custom — POST /{resource}/{id}/{routeSegment}/{subId}/{actionPath}
# 前提：segment3 ∈ R, segment4为数字, segment5非aggregate
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/(?<subId>\d+)/(?<action>[a-z][a-z0-9-]+)$
```

---

#### 优先级 4：自定义操作（actionPath，回退匹配）

> 当 segment3 不在已知 `routeSegment` 集合中，或在子实体上下文中 segment4 非数字时，回退为自定义操作。

```regex
# C9: BO 自定义 — POST /{resource}/{id}/{actionPath}
# 前提：segment3 ∉ R（不在已知 routeSegment 集合中）
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<action>[a-z][a-z0-9-]+)$

# A4: GLOBAL 自定义 — POST /{resource}/{actionPath}
# 前提：segment2 非数字、非保留关键字（search/batch/root）
^/(?<bo>[a-z][a-z0-9-]+)/(?<action>[a-z][a-z0-9-]+)$

# D6: ENTITY 自定义 — POST /{resource}/{id}/{routeSegment}/{actionPath}
# 前提：segment3 ∈ R, segment4 非数字（非 batch）
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/(?<action>[a-z][a-z0-9-]+)$

# D8: ENTITY 自定义(无actionPath) — POST /{resource}/{id}/{routeSegment}/{subId}
# 前提：segment3 ∈ R, segment4 为数字（回退；若标准CRUD已命中则不进入此分支）
^/(?<bo>[a-z][a-z0-9-]+)/(?<id>\d+)/(?<route>[a-z][a-z0-9-]+)/(?<subId>\d+)$
```

---

### 3.3 完整匹配流程图

```
输入: HTTP Method + URL Path
  │
  ├─ 1. 提取 boCode (第一段)
  │    └─ 匹配正则: ^/([a-z][a-z0-9-]+)(?:/|$)
  │
  ├─ 2. 查找 BO 快照 (authz_bo_meta_model)
  │    └─ 获取 R = {所有 entity.routeSegment}
  │    └─ 获取已知 operation 列表
  │
  ├─ 3. 路径分段: segments = URL.split("/")[1:]
  │
  ├─ 4. 按优先级匹配 (从具体到通用):
  │    ├─ 匹配保留关键字路径 (search, root, batch, batch/query, batch/{action})
  │    ├─ 匹配聚合根 CRUD + 变体 (root, edit, aggregate, replace-aggregate)
  │    ├─ 匹配子实体路由 (segments[2] ∈ R)
  │    │   ├─ 匹配标准子实体 CRUD (CREATE_SUB/READ_SUB/UPDATE_SUB/DELETE_SUB/batch)
  │    │   ├─ 匹配子实体聚合变体 (aggregate)
  │    │   └─ 匹配子实体自定义 (actionPath)
  │    └─ 回退到自定义操作 (actionPath, GLOBAL)
  │
  ├─ 5. 定位 Operation:
  │    ├─ 标准 CRUD → 虚拟 Operation (直接判定: LIST/READ/CREATE/UPDATE/DELETE/...)
  │    └─ 自定义/变体 → 按 (boCode + Method + 路径模板) 查找显式 Operation
  │
  └─ 6. 派生权限项:
       └─ RES_DATA_BO + boMetaId + authzAction
```

---

## 四、判别 SQL：路径模板 → Operation 判定矩阵

> 以下伪代码（Java 风格）展示发布服务如何从 URL 判定唯一 Operation。

```java
/**
 * @param method    HTTP Method (GET/POST/PUT/PATCH/DELETE)
 * @param path      URL path, e.g. "/scenes/123/products/456/aggregate"
 * @param boSnapshot BO 快照数据 (resourcePath, routeSegments[], operations[])
 * @return Operation 唯一标识, 或 null (无法匹配)
 */
public OperationMatchResult match(String method, String path, BoSnapshot boSnapshot) {

    // Step 1: strip leading /, split
    String[] seg = path.replaceFirst("^/", "").split("/");
    int n = seg.length;
    Set<String> routes = boSnapshot.getRouteSegments(); // R 集合

    // Step 2: boCode verification
    if (n == 0 || !seg[0].equals(boSnapshot.getResourcePath())) return null;

    // Step 3: pattern matching by depth (n=segments count)
    switch (n) {
        case 1:
            // A1/A2: /{resource}
            if ("GET".equals(method))  return matchStandard("LIST");
            if ("POST".equals(method)) return matchStandard("CREATE");
            break;

        case 2:
            // Reserved keywords
            if ("search".equals(seg[1]))
                return "POST".equals(method) ? matchStandard("SEARCH") : null;
            if ("batch".equals(seg[1]))
                return matchBatchRoot(method);
            if ("root".equals(seg[1]))
                return "POST".equals(method) ? matchStandard("CREATE_ROOT") : null;
            // ID or actionPath
            if (seg[1].matches("\\d+")) {
                // B1/B2/B3: /{resource}/{id}
                // NOTE: POST /{resource}/{id} without actionPath is NOT a valid path
                return matchById(method);
            } else {
                // A4: /{resource}/{actionPath} (GLOBAL)
                return matchCustom("GLOBAL", seg[1]);
            }

        case 3:
            // batch/query
            if ("batch".equals(seg[1]) && "query".equals(seg[2]))
                return "POST".equals(method) ? matchStandard("BATCH_QUERY") : null;
            // batch/{actionPath} (custom)
            if ("batch".equals(seg[1]))
                return matchCustom("BO", seg[2], true); // supportsBatch=true
            // ID + keyword
            if (seg[1].matches("\\d+")) {
                if ("root".equals(seg[2]))
                    return "GET".equals(method) ? matchStandard("READ_ROOT") : null;
                if ("edit".equals(seg[2]))
                    return "GET".equals(method) ? matchStandard("READ_EDIT") : null;
                if ("aggregate".equals(seg[2]))
                    return matchMutate("UPDATE_AGGREGATE", method);
                if ("replace-aggregate".equals(seg[2]))
                    return "POST".equals(method) ? matchStandard("REPLACE_AGGREGATE") : null;
                // ID + routeSegment
                if (routes.contains(seg[2]))
                    return matchSubEntityRoot(method); // CREATE_SUB / READ_SUB
                // ID + actionPath (BO custom)
                return matchCustom("BO", seg[2], false);
            }
            break;

        case 4:
            if (seg[1].matches("\\d+") && routes.contains(seg[2])) {
                if ("batch".equals(seg[3]))
                    return matchSubEntityBatch(method);
                if (seg[3].matches("\\d+"))
                    return matchSubEntityById(method); // UPDATE_SUB / DELETE_SUB or custom
                // actionPath (non-numeric, non-batch: D6 custom)
                return matchCustom("ENTITY", seg[3], false, seg[2]);
            }
            break;

        case 5:
            if (seg[1].matches("\\d+") && routes.contains(seg[2])
                && seg[3].matches("\\d+")) {
                if ("aggregate".equals(seg[4]))
                    return matchMutate("UPDATE_SUB_AGGREGATE", method);
                // ENTITY custom (E3)
                return matchCustom("ENTITY", seg[4], false, seg[2]);
            }
            // D7: batch/{actionPath} (sub-entity level)
            if (seg[1].matches("\\d+") && routes.contains(seg[2])
                && "batch".equals(seg[3])) {
                return matchCustom("ENTITY", seg[4], true, seg[2]);
            }
            break;
    }
    return null; // no match
}
```

---

## 五、速查：每个路径模式的提取结果

| URL 示例 | boCode | operation | id | routeSegment | subId | actionPath |
|----------|--------|-----------|----|-------------|-------|------------|
| `GET /scenes` | `scenes` | `LIST` | — | — | — | — |
| `POST /scenes` | `scenes` | `CREATE` | — | — | — | — |
| `POST /scenes/root` | `scenes` | `CREATE_ROOT` | — | — | — | — |
| `POST /scenes/search` | `scenes` | `SEARCH` | — | — | — | — |
| `GET /scenes/123` | `scenes` | `READ` | `123` | — | — | — |
| `PATCH /scenes/123` | `scenes` | `UPDATE` | `123` | — | — | — |
| `DELETE /scenes/123` | `scenes` | `DELETE` | `123` | — | — | — |
| `GET /scenes/123/edit` | `scenes` | `READ_EDIT` | `123` | — | — | — |
| `GET /scenes/123/root` | `scenes` | `READ_ROOT` | `123` | — | — | — |
| `PATCH /scenes/123/aggregate` | `scenes` | `UPDATE_AGGREGATE` | `123` | — | — | — |
| `POST /scenes/123/replace-aggregate` | `scenes` | `REPLACE_AGGREGATE` | `123` | — | — | — |
| `POST /scenes/batch` | `scenes` | `BATCH_CREATE` | — | — | — | — |
| `PATCH /scenes/batch` | `scenes` | `BATCH_UPDATE` | — | — | — | — |
| `DELETE /scenes/batch` | `scenes` | `BATCH_DELETE` | — | — | — | — |
| `POST /scenes/batch/query` | `scenes` | `BATCH_QUERY` | — | — | — | — |
| `POST /scenes/batch/publish` | `scenes` | 批量业务操作 | — | — | — | `publish` |
| `POST /scenes/publish` | `scenes` | 全局业务操作 | — | — | — | `publish` |
| `POST /scenes/123/submit` | `scenes` | 单条业务操作 | `123` | — | — | `submit` |
| `GET /scenes/123/team-members` | `scenes` | `READ_SUB` | `123` | `team-members` | — | — |
| `POST /scenes/123/team-members` | `scenes` | `CREATE_SUB` | `123` | `team-members` | — | — |
| `PATCH /scenes/123/team-members/456` | `scenes` | `UPDATE_SUB` | `123` | `team-members` | `456` | — |
| `DELETE /scenes/123/team-members/456` | `scenes` | `DELETE_SUB` | `123` | `team-members` | `456` | — |
| `POST /scenes/123/team-members/adjust-quantity` | `scenes` | 子实体业务操作 | `123` | `team-members` | — | `adjust-quantity` |
| `POST /scenes/123/team-members/batch` | `scenes` | `BATCH_CREATE_SUB` | `123` | `team-members` | — | — |
| `PATCH /scenes/123/team-members/batch` | `scenes` | `BATCH_UPDATE_SUB` | `123` | `team-members` | — | — |
| `DELETE /scenes/123/team-members/batch` | `scenes` | `BATCH_DELETE_SUB` | `123` | `team-members` | — | — |
| `POST /scenes/123/team-members/batch/reassign` | `scenes` | 子实体批量业务操作 | `123` | `team-members` | — | `reassign` |
| `GET /scenes/123/team-members/456/aggregate` | `scenes` | `READ_SUB_AGGREGATE` | `123` | `team-members` | `456` | — |
| `PATCH /scenes/123/team-members/456/aggregate` | `scenes` | `UPDATE_SUB_AGGREGATE` | `123` | `team-members` | `456` | — |
| `POST /scenes/123/team-members/456/reassign` | `scenes` | 子实体业务操作 | `123` | `team-members` | `456` | `reassign` |

---

## 六、与相关文档的关系

| 文档 | 关系 |
|------|------|
| `api-governance-charter.md` | 强制约束基线（最高优先级）。charter 文字有歧义时，以本文件的算法定义为准；两者明确冲突时进入人工确认。裁决链见 charter 第零章 |
| `api-governance-mapping.md` | 映射规则参考手册。本文件与 mapping 描述不一致时，以本文件的算法定义为准 |
| `model-fragment.schema.json` | 定义 `resourcePath`、`routeSegment`、`actionPath` 的正则约束 |
| `operation-fragment.schema.json` | 定义 `scope`、`httpMethod`、`actionPath`、`supportsBatch` |
| `copilot-instructions.md` §3.3 | PATCH→POST 降级规则 |
