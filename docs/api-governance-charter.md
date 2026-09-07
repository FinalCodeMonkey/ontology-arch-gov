# API 治理技术宪章

> **本文件是 API 定义的强制约束基线。** 所有后端 Controller、前端 API 调用、BO 元数据 `apiConfig` 配置、
> `OPERATION` Fragment 声明，MUST 遵守本宪章。违反任何条款的代码不得合入主干。
>
> 宪章只规定"必须做什么 / 禁止做什么"，不重复 URL 形态全集、Scope 枚举详解、policy 字段说明。
> 需要查阅这些内容时，请阅读对应文档：
> - URL 路径形态、正则提取规则、匹配引擎伪代码 → `api-url-regex-charter.md`
> - Scope 枚举、`aggregateApiPolicy` / `entityApiPolicy` 字段详解、配置组合示例 → `api-governance-mapping.md`

---

## 第零章 文档裁决链（NON-NEGOTIABLE）

本工作区 API 治理文档由三份构成，裁决优先级如下：

```
api-governance-charter.md（本文件，强制约束基线，最高）
  ↓ 当本文档文字描述有歧义时，以 regex 的算法定义为准（歧义最低原则）
api-url-regex-charter.md（权威实现规范，正则+伪代码，零歧义）
  ↓ 当与下方文档的描述性文字冲突时，以本文档为准
api-governance-mapping.md（映射规则参考手册，最低）
  ↓
人工确认（最终裁决）
```

| 场景 | 裁决结果 |
|------|----------|
| charter 与 regex 对同一规则的文字描述不一致 | 若 charter 文字有歧义且 regex 零歧义 → **以 regex 为准**，charter 随之调整对齐；若 charter 约束明确且 regex 算法偏差 → **以 charter 为准**，修正 regex |
| charter 与 regex 均明确但结论冲突 | 进入**人工确认** |
| charter 与 mapping 对同一规则描述冲突 | **以 charter 为准**，mapping 应随之调整 |
| 三份文档均无法覆盖的新场景 | 人工确认后，先更新 charter，再同步 regex/mapping |

> **维护纪律**：charter 是约束基线，变更 charter 后 MUST 同步检查 regex 和 mapping 是否需要对齐；
> regex 变更后 MAY 发现 charter/mapping 滞后，此时应修正 charter/mapping 对齐 regex 的算法定义。
> mapping 变更不反向影响 charter/regex。

---

## 第一章 总则

### 1.1 宪章地位

本宪章与 `copilot-instructions.md` 第三章 3.3 节（PATCH → POST 降级）共同构成 API 层的强制约束。
当本宪章与 `api-governance-mapping.md` 的描述性文字冲突时，以本宪章为准；
当本宪章文字描述有歧义时，以 `api-url-regex-charter.md` 的算法定义为准（见第零章）。

### 1.2 适用范围

| 对象 | 约束内容 |
|------|----------|
| 后端 Controller | HTTP Method、URL 路径形态、响应封装、权限标记 |
| BO 元数据 `apiConfig` | `aggregateApiPolicy`、`entityApiPolicy`、`alternateAggregateApis`、`alternateEntityApis` 配置 |
| `OPERATION` Fragment | 显式 Operation 的声明、`authzAction` 配置 |
| 前端 API 调用 | URL 拼接、ID 传递、HTTP Method 选择 |
| 发布服务 | 虚拟 Operation 生成、路由解析表、权限项派生 |

### 1.3 核心原则

1. **URL 能定位 BO 和 Operation**：每个受保护 URL MUST 能解析出唯一 BO；写操作和自定义操作 MUST 能解析出唯一 Operation。URL 合法形态与解析规则见 `api-url-regex-charter.md`。
2. **权限由元数据派生**：API 合同 MUST NOT 直接写死 `perm_item_id`；权限项由 `RES_DATA_BO + boMetaId + authzAction` 确定性推导。
3. **同一路径不承载双重语义**：当"仅主实体"与"完整聚合"两类接口并存时，MUST 通过 `alternateAggregateApis` 显式声明，不得让同一路径承载两种语义。

---

## 第二章 标准 CRUD — 可隐式推导

### 2.1 可自动推导的接口

以下标准 CRUD API 无需在 `OPERATION` Fragment 中显式声明，由发布服务根据 `aggregateApiPolicy` / `entityApiPolicy` 自动生成虚拟 Operation。

**聚合根级别**（`LIST` / `SEARCH` / `READ` / `BATCH_QUERY` / `CREATE` / `BATCH_CREATE` / `UPDATE` / `BATCH_UPDATE` / `DELETE` / `BATCH_DELETE`）
与**子实体级别**（创建/查询/更新/删除/批量创建/批量更新/批量删除）的完整路径形态、Method、`authzAction`、触发条件，
详见 `api-url-regex-charter.md` 第二章 URL 路径形态全集（A1~A4、B1~B7、C7~C8、D1~D5）
及 `api-governance-mapping.md` §1.2 标准 CRUD 虚拟 Operation 规则。

> 本宪章不重复上述表格。以下仅保留强制约束条款。

### 2.2 隐式推导的约束

| 规则 | 说明 |
|------|------|
| **MUST 配置 `apiConfig.resourcePath`** | 决定路由前缀，未配置则无法生成虚拟 Operation |
| **MUST 配置 `aggregateApiPolicy` 各 Scope** | 决定每个动作的处理范围；Scope 枚举值详见 `api-governance-mapping.md` §1 |
| **批量接口 MUST 设 `batchEnabled=true`** | 否则批量类虚拟 Operation 不生成 |
| **复杂查询 MUST 设 `searchEnabled=true`** | 否则 `SEARCH` 虚拟 Operation 不生成 |
| **子实体 MUST 配置 `routeSegment`** | 否则子实体嵌套路由不生成 |
| **MAY 显式声明同名 Operation** | 若 `OPERATION` Fragment 显式声明了同一路由或同一语义的操作，以显式 Operation 为准，保留业务化命名、展示位置、触发事件等治理信息；不得保存原型文件、按钮文案、事件函数等原型引用 |

---

## 第三章 CRUD 变体 — 必须显式声明

### 3.1 必须显式声明的场景

当同一资源同时需要"仅主实体"与"完整聚合"两类接口语义时，MUST 通过 `alternateAggregateApis` 或 `alternateEntityApis` 显式声明 `operationCode`。

变体类型包括：主实体详情（`/root`）、编辑态读数据（`/edit`）、聚合增量更新（`/aggregate`）、聚合整体替换（`/replace-aggregate`）、
局部聚合详情/更新（子实体 `/{subId}/aggregate`）。各变体的完整路径形态、`requestScope`、`responseScope` 详见：

- `api-url-regex-charter.md` §2.3（C1~C4）、§2.5（E1~E2）
- `api-governance-mapping.md` §1.1（主实体接口与完整聚合接口并存）、§2.1（多级子实体局部聚合接口）

> 本宪章不重复上述表格。以下仅保留强制约束条款。

### 3.2 编辑态读数据专项规则

| 规则 | 说明 |
|------|------|
| **数据投影与详情一致时** | 复用 `GET /{resource}/{id}`，`authzAction=READ`，无需额外接口 |
| **数据投影与详情不同时** | MUST 通过 `alternateAggregateApis` 声明 `GET /{resource}/{id}/edit`，`responseScope=ROOT_ENTITY_ONLY` |
| **编辑态接口权限** | 仍然是 `GET` + `READ`，URL 中带 `/edit` 只控制返回数据投影 |
| **能不能进入编辑态** | 由前端根据 `UPDATE` 权限项做 UI 控制，不需要为此单开后端 API |

### 3.3 编辑会话与互斥锁专项规则

当打开编辑态不仅是读取编辑投影，还需要返回下拉选项、候选值、编辑上下文，或需要申请互斥锁/编辑会话时，该动作已产生后端命令语义，MUST 显式声明为独立 Operation。

| 规则 | 说明 |
|------|------|
| **打开编辑会话 MUST 显式声明** | 使用 `operationKind=CUSTOM`、`httpMethod=POST`、`authzAction=UPDATE`，示例：`POST /{resource}/{id}/edit-session` |
| **编辑会话返回编辑态 DTO** | 返回值可包含表单初始值、下拉选项、候选集合、锁 token、版本号、锁过期时间等编辑上下文 |
| **保存修改仍是 UPDATE** | 保存 Operation 使用 `operationKind=UPDATE`、`authzAction=UPDATE`；请求体 MUST 携带锁 token 或版本号以校验并发冲突 |
| **释放/续租锁显式声明** | 取消编辑、关闭编辑态、续租锁等有后端副作用的动作使用独立 `CUSTOM` Operation，但 `authzAction` 仍归并为 `UPDATE` |
| **权限项不因会话拆分而增加** | 打开编辑会话、保存修改、释放/续租锁共享 `UPDATE` 权限项，不生成 `SAVE`、`LOCK`、`UNLOCK` 权限项 |

### 3.4 禁止事项

```
❌ 让同一路径承载"仅主实体"和"完整聚合"两种语义
❌ CRUD 变体不声明 operationCode，依赖路径猜测
❌ 编辑态读数据接口使用非 GET 方法或非 READ 权限
❌ 用 /edit 路径控制"能不能编辑"（应归 UPDATE 权限）
❌ 将需要申请互斥锁的编辑态打开动作混在保存修改 Operation 中
```

---

## 第四章 业务流程 / 状态改变 — 必须显式标记

### 4.1 强制标记规则

`operationKind` 为 `STATE_CHANGE` 或 `CUSTOM` 的操作 **MUST** 显式配置，不允许缺省：

| 必填项 | 说明 |
|--------|------|
| **`operationCode`** | MUST 写入 `OPERATION` Fragment，保留业务化命名、展示位置、触发事件等治理信息；不得保存原型文件、按钮文案、事件函数等原型引用 |
| **`authzAction`** | MUST 显式配置，如 `SUBMIT`、`PUBLISH`、`ARCHIVE`、`VOID`、`ADJUST_RIVAL` 等 |
| **URL 解析** | 每个此类 API URL MUST 能解析出唯一 Operation |

### 4.2 `authzAction` 配置规则

| `operationKind` / HTTP 语义 | 默认 `authzAction` | 是否允许缺省 |
|-----------------------------|--------------------|--------------|
| 查询、详情、查看态请求、`GET` | `READ` | 允许 |
| `CREATE` | `CREATE` | 允许 |
| `UPDATE`、编辑、保存修改 | `UPDATE` | 允许 |
| `DELETE` | `DELETE` | 允许 |
| `IMPORT` | `IMPORT` | 允许 |
| `EXPORT` | `EXPORT` | 允许 |
| **`STATE_CHANGE` / `CUSTOM`** | **必须显式配置** | **禁止缺省** |

### 4.3 禁止事项

```
❌ 状态流转操作复用 SAVE / UPDATE / CREATE 作为 authzAction
❌ STATE_CHANGE / CUSTOM 操作不声明 authzAction
❌ 提交审批、发布、归档、作废等操作不写入 OPERATION Fragment
❌ 业务流程操作无法从 URL 解析出唯一 Operation
```

---

## 第五章 HTTP 方法与 URL 路径

### 5.1 PATCH → POST 降级（NON-NEGOTIABLE）

> 详见 `copilot-instructions.md` 第 3.3 节。本宪章重申其强制性。

| 规则 | 说明 |
|------|------|
| **部分更新 MUST 用 `@PostMapping`** | 所有部分更新操作（聚合根、子实体、增量更新）的 Controller 端点 MUST 使用 `@PostMapping` + 动作路径，禁止 `@PatchMapping` |
| **URL MUST 携带动作语义** | 降级为 POST 时，路径必须通过 segment 表达更新语义：`POST /{resource}/{id}/update`、`POST /{resource}/{id}/aggregate` |
| **`PUT` 不受限制** | `@PutMapping` 可正常用于全量替换类操作 |
| **设计文档保留 PATCH 语义** | `api-governance-mapping.md`、`OPERATION` Fragment 中的 `httpMethod: "PATCH"` 保留，表示 REST 语义；发布服务自动映射 `PATCH 语义 → POST 实现` |

### 5.2 子实体路由与自定义操作路由

子实体路由规则、自定义操作路由模式（`scope` × `supportsBatch` → 路径模板）的完整定义，
详见 `api-url-regex-charter.md` 第二章 URL 路径形态全集及 §3.2 路径分类正则。

> 本宪章仅重申以下强制约束：
>
> - **子实体 MUST 嵌套路由**，通过 `parentEntityCode + parentRefField + routeSegment` 生成，禁止暴露独立顶级路由
> - **子实体操作不改变聚合根默认 `updateScope`**：`PATCH /{resource}/{id}` MUST NOT 顺带覆盖子实体，子实体变更走 `/{resource}/{id}/products` 或聚合内命令
> - **自定义操作 MUST 有 `actionPath`**：`POST /{resource}/{id}` 不是合法路径（见 regex §3.2 优先级 2 注释）
> - **boCode 恒为 URL 第一段（NON-NEGOTIABLE）**：PSP `ApiUrlBoExtractor` 按「URL 第一段 = boCode」推导。**禁止在 URL 中嵌套其他 BO 的资源路径**（如 `GET /meetings/{id}/participants` 查询参会人——`participants` 属于独立 BO `meeting-participants`，不能挂在 `meetings` 下）
> - **跨 BO 查询 MUST 用 search**：查询另一 BO 的数据时，使用 `POST /{目标BO}/search`（如 `POST /meeting-participants/search`），外部 ID 作为 **body 过滤条件**（如 `meetingId`），禁止作为 URL 路径段

---

## 第六章 响应封装与返回值

### 6.1 强制规则

| 规则 | 说明 |
|------|------|
| **所有 API MUST 返回 `ApiResponse<T>`** | 统一响应封装，位于 `com.enterprise.platform.common.web` |
| **单条操作** | 返回单个 DTO 或 `Void` |
| **批量操作** | 返回 `BatchResultDTO` |
| **导出类异步操作** | 返回任务 DTO |
| **查询接口分类** | 简单查询 `GET`、复杂查询 `POST /search`、已知 ID 批量查询 `POST /batch/query` |

### 6.2 同步流式下载 / 导出豁免（NON-NEGOTIABLE）

以下情形**不受 §6.1 "MUST 返回 ApiResponse<T>" 约束**，允许方法签名返回 `void`：

| 条件 | 说明 |
|------|------|
| **方法签名含 `HttpServletResponse` 参数** | 且方法体内直接通过 `response.getOutputStream()` / `response.getWriter()` 写入响应流 |
| **全局异常处理器覆盖** | 此类方法不应自行 try-catch；异常由 `@ControllerAdvice` 统一拦截并返回标准错误响应 |
| **OPERATION Fragment 声明一致性** | `singleResultType` MUST 标注为 `Void`（同步下载）或 `ApiResponse<ExportTaskDTO>`（异步导出），与 Controller 实际返回值一致 |

**示例 — 合规的同步下载接口**：

```java
// ✅ 合规：直接写流 + void 返回
@PostMapping("/export")
public void export(@RequestBody ExportRequest request, HttpServletResponse response) { ... }

// ✅ 合规：下载模板
@GetMapping("/import-template")
public void downloadTemplate(HttpServletResponse response) { ... }
```

**异步导出** 不受此豁免影响——应返回 `ApiResponse<ExportTaskDTO>`（含任务 ID），
由前端轮询任务状态后通过独立下载接口获取文件。

### 6.3 禁止事项

```
❌ 接口直接返回裸 DTO / 裸 List / 裸 Map
❌ 批量操作返回单条 DTO
❌ 查询接口用 POST 操作数据
```

---

## 第七章 权限推导链路

### 7.1 两段式推导（NON-NEGOTIABLE）

权限项由 `RES_DATA_BO + boMetaId + authzAction` 确定性推导，推导流程图与示例详见 `api-governance-mapping.md` §3.1。

> 本宪章仅重申：API 合同 MUST NOT 直接写死 `perm_item_id`；`authzAction` 是 Operation 到 PSP 的标准投影，不是 API 到权限项的显式绑定。

### 7.2 权限项唯一键

```
authz_permission_item 唯一键 = tenant_id + app_code + res_model_code + res_id + act_code
```

同一个 BO 下相同 `authzAction` 会合并为一条权限项。

### 7.3 冲突裁决规则

| 场景 | 裁决结果 |
|------|----------|
| 显式 Operation 与虚拟 Operation 同路由 / 同语义 | **显式优先**，虚拟 Operation 被覆盖，保留业务化命名、展示位置、触发事件等治理信息 |
| 多个 Operation 映射到同一 `authzAction` | **合并**为同一权限项，发布服务输出合并提示和 `permissionItem -> operations` 派生关系 |
| 路由不同但 `authzAction` 相同 | **不冲突**，各自独立 Operation，共享同一权限项 |

### 7.4 禁止事项

```
❌ API 合同直接保存 perm_item_id
❌ 在 API 路由上显式绑定权限项
❌ STATE_CHANGE / CUSTOM 操作缺省 authzAction
❌ 用 SAVE 作为独立 authzAction（编辑按钮、编辑态、保存修改都归 UPDATE）
```

---

## 第八章 前后端 ID 传递（NON-NEGOTIABLE）

> 详见 `copilot-instructions.md` 第 3.7 节。本宪章重申其强制性，不重复规则细节。
>
> 核心约束：后端 MUST NOT 输出裸 Long；前端 MUST 保持 ID 原始类型，禁止 `Number()` / `parseInt()` / `+id` 转换；
> URL 路径直接字符串拼接；TS 类型 ID 字段 MUST 为 `string`（大整数场景）。

---

## 第九章 发布校验清单

发布服务在合成 BO Snapshot 时 MUST 校验以下项，任一失败则发布中止：

| # | 校验项 | 失败后果 |
|---|--------|----------|
| 1 | 每个受保护 URL 能解析出唯一 BO | 发布中止 |
| 2 | 写操作、自定义操作、状态流转 URL 能解析出唯一 Operation | 发布中止 |
| 3 | Operation 能得到唯一 `authzAction`；`STATE_CHANGE` 和 `CUSTOM` 不允许缺省 | 发布中止 |
| 4 | API 合同未直接保存 `perm_item_id` | 发布中止 |
| 5 | `deleteScope=ROOT_ENTITY_ONLY` 时已声明 `orphanPolicy` | 发布中止 |
| 6 | CRUD 变体已通过 `alternateAggregateApis` / `alternateEntityApis` 显式声明 | 发布中止 |
| 7 | 多个 Operation 映射到同一 `authzAction` 时输出合并提示 | 警告，不中止 |

---

## 第十章 速查矩阵

### 10.1 "这个接口需要显式声明吗？"

```
是标准 CRUD 吗？
  ├─ 是 → 隐式推导，无需声明（第二章）
  │       └─ 但若需要保留原型追溯，MAY 显式声明（显式优先）
  └─ 否 → 是 CRUD 变体吗？
          ├─ 是 → MUST 显式声明 alternateAggregateApis / alternateEntityApis（第三章）
          └─ 否 → 是业务流程 / 状态改变吗？
                  ├─ 是 → MUST 显式标记 operationCode + authzAction（第四章）
                  └─ 否 → 重新审视需求
```

### 10.2 "这个操作用什么 authzAction？"

```
查询 / 详情 / 查看态 → READ
新增 / 创建         → CREATE
编辑 / 保存修改     → UPDATE
删除               → DELETE
导入 / 导出         → IMPORT / EXPORT
提交 / 发布 / 归档 / 作废 / 自定义业务动作 → 必须显式配置独立 authzAction
```

### 10.3 "这个更新用 POST 还是 PATCH？"

```
设计文档 / 治理文档 → 写 PATCH（表达 REST 语义）
Controller 实现     → 用 @PostMapping + 动作路径（第五章）
PUT                → 不受限制，可用于全量替换
```

---

## 附录 A：与相关文档的关系

| 文档 | 角色 | 与本宪章的关系 |
|------|------|---------------|
| `api-url-regex-charter.md` | **权威实现规范**（URL 形态全集、正则提取、匹配引擎伪代码） | 当本宪章文字描述有歧义时，以 regex 的算法定义为准（见第零章）。两者冲突且均无歧义时进入人工确认 |
| `api-governance-mapping.md` | 映射规则参考手册（Scope 枚举、policy 字段详解、配置组合示例） | 描述冲突时以本宪章为准 |
| `copilot-instructions.md` 第 3.3 节 | PATCH → POST 降级规则 | 本宪章第五章重申其强制性 |
| `copilot-instructions.md` 第 3.7 节 | 前后端 ID 传递约束 | 本宪章第八章重申其强制性 |
| `copilot-instructions.md` 第 3.8 节 | API 治理宪章强制引用 | 本宪章的入口引用，Copilot 处理 API 相关任务时 MUST 先阅读本宪章 |
| `governance-profile-guide.md` | Governance Profile 配置说明 | 提供 `apiDefaults` 等项目级默认参数 |
| `coding-constitution-mybatis-plus.md` | MyBatis-Plus DDD 编码宪章 | 互补关系，该宪章管持久化层，本宪章管 API 层 |
