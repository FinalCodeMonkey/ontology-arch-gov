# API 治理映射规则

本文件是 API 治理的**映射规则参考手册**，说明 BO 发布态 `schema_view` 如何映射为 API 合同。

> **文档定位**：本文件提供 Scope 枚举详解、`aggregateApiPolicy` / `entityApiPolicy` 字段说明、配置组合示例。
> 强制约束条款见 `api-governance-charter.md`；URL 路径形态全集与正则提取规则见 `api-url-regex-charter.md`。
> 三份文档的裁决优先级见 `api-governance-charter.md` 第零章。

## 1. 聚合根 API

假设 `apiConfig.resourcePath=/scenes`，且 `apiConfig.aggregateApiPolicy` 为：

```json
{
	"listProjectionScope": "ROOT_SUMMARY",
	"readScope": "FULL_AGGREGATE",
	"createScope": "FULL_AGGREGATE",
	"updateScope": "ROOT_ENTITY_ONLY",
	"deleteScope": "CASCADE_AGGREGATE",
	"orphanPolicy": "DENY_DELETE_WHEN_CHILD_EXISTS"
}
```

### aggregateApiPolicy 各字段说明

#### 范围枚举值（Scope）

每个 HTTP 动作的"处理范围"由以下枚举值决定，控制请求体可提交哪些实体字段、响应体应返回哪些实体层级：

| 枚举值 | 含义 | 适用动作 |
|--------|------|----------|
| `ROOT_ENTITY_ONLY` | 仅处理聚合根主实体（如 `scene_main`），不涉及任何子实体 | update、list |
| `ROOT_SUMMARY` | 主实体 + 汇总/投影字段，例如场景列表行附带产品数、竞对汇总等统计列，但不内嵌子实体集合 | list |
| `ENTITY_ONLY` | 仅处理当前子实体本体，不涉及它的下级子实体 | 子实体 API |
| `ENTITY_SUMMARY` | 当前子实体 + 下级汇总字段 | 子实体列表 |
| `ENTITY_AGGREGATE` | 当前子实体及其下所有子孙实体组成的局部聚合 | 子实体详情 |
| `ENTITY_AGGREGATE_PATCH` | 增量更新当前子实体及其下级（新增/修改/删除由请求体内容决定，不覆盖未提交的下级） | 子实体局部聚合更新 |
| `FULL_AGGREGATE` | 完整聚合：主实体 + 全部子实体树，从根到叶子一次性处理 | create、read |
| `FULL_AGGREGATE_REPLACE` | 整体替换：先删后建整棵聚合树，必须显式命令，不可由普通 PATCH 隐式触发 | 替换聚合 |
| `FULL_AGGREGATE_PATCH` | 增量更新完整聚合（新增/修改/删除由请求体内容决定，不覆盖未提交的子实体） | 聚合增量更新 |
| `CASCADE_AGGREGATE` | 级联聚合：删除主实体时同时级联删除其下所有子实体 | delete |
| `NONE` | 不涉及任何实体变更，仅查询或引用 | 只读辅助接口 |

#### 各属性详解

| 属性 | 类型 | 作用域 | 说明 |
|------|------|--------|------|
| `listProjectionScope` | Scope 枚举 | 列表查询（`GET /scenes`、`POST /scenes/search`） | 定义列表接口的返回投影层级。`ROOT_SUMMARY` 表示每行包含主实体字段及子实体统计信息（如产品数、竞对汇总），但不内嵌完整的子实体数组；`ROOT_ENTITY_ONLY` 表示仅返回主实体字段，不含任何子实体信息 |
| `readScope` | Scope 枚举 | 单条详情（`GET /scenes/{id}`） | 定义详情接口的响应范围。`FULL_AGGREGATE` 表示返回主实体 + 全部内嵌子实体树，适合详情页一次性加载；`ROOT_ENTITY_ONLY` 表示只返回主实体，子实体通过独立 API 按需加载 |
| `createScope` | Scope 枚举 | 创建（`POST /scenes`） | 定义创建请求可以提交的数据范围。`FULL_AGGREGATE` 允许在同一个 POST 中提交主实体和子实体（产品清单、团队成员等）一次性创建完整聚合；`ROOT_ENTITY_ONLY` 表示只允许提交主实体字段，子实体需后续独立创建 |
| `updateScope` | Scope 枚举 | 更新（`PATCH /scenes/{id}`） | 定义默认更新请求可以修改的数据范围。`ROOT_ENTITY_ONLY` 是最常见配置，表示普通 PATCH 只修改主实体字段（如场景名称、分类）、不能顺带修改子实体；子实体变更必须走 `/scenes/{id}/products` 等子资源 API 或显式的聚合更新命令 |
| `deleteScope` | Scope 枚举 | 删除（`DELETE /scenes/{id}`） | 定义删除主实体时对子实体的处理方式。`CASCADE_AGGREGATE` 表示级联删除全部子实体；`ROOT_ENTITY_ONLY` 表示仅删除主实体，此时必须配合 `orphanPolicy` 声明子实体处置策略 |
| `orphanPolicy` | 字符串 | 仅当 `deleteScope=ROOT_ENTITY_ONLY` 时生效 | 声明删除主实体后遗留子实体的处置策略，详见下方 `orphanPolicy` 枚举 |

#### orphanPolicy 枚举值

| 值 | 含义 | 推荐场景 |
|----|------|----------|
| `DENY_DELETE_WHEN_CHILD_EXISTS` | 存在子实体时禁止删除主实体，返回错误提示用户先清理子数据 | **推荐默认值**，防止产生孤立数据 |
| `KEEP_CHILDREN_AS_HISTORY` | 保留子实体作为历史数据，不做任何修改 | 需要保留审计轨迹的场景 |
| `DETACH_CHILDREN` | 将子实体的外键置空，子实体不再关联任何主实体 | 通常不推荐，容易产生数据一致性问题 |
| `MANUAL_CLEANUP_REQUIRED` | 允许删除但标记主实体为"待清理"状态，由后台任务或人工处理孤儿子实体 | 过渡期方案 |

#### 配置组合示例

| 场景 | 配置 | 效果 |
|------|------|------|
| **典型主从表单**（如场景管理） | `list=ROOT_SUMMARY, read=FULL_AGGREGATE, create=FULL_AGGREGATE, update=ROOT_ENTITY_ONLY, delete=CASCADE_AGGREGATE` | 列表带统计信息、详情展示全部、新建可一次性填、编辑只改主表、删除级联清理 |
| **纯主数据**（如竞争对手、产品） | `list=ROOT_ENTITY_ONLY, read=ROOT_ENTITY_ONLY, create=ROOT_ENTITY_ONLY, update=ROOT_ENTITY_ONLY, delete=ROOT_ENTITY_ONLY, orphanPolicy=DENY_DELETE_WHEN_CHILD_EXISTS` | 所有操作仅处理单表，无子实体 |
| **审计保留** | `delete=ROOT_ENTITY_ONLY, orphanPolicy=KEEP_CHILDREN_AS_HISTORY` | 删除主实体时子实体作为历史记录保留 |

> 标准 CRUD API 的完整路径形态、Method、`authzAction`、触发条件见 `api-url-regex-charter.md` §2（A1~A4、B1~B7）
> 及 `api-governance-charter.md` §2.2 隐式推导约束。本文件不重复该表格。

> 重要：聚合根 API 面向 BO 聚合，不等同于只面向 `scene_main` 主表；但不同 HTTP 动作的处理范围必须由 `aggregateApiPolicy` 显式声明。普通 `PATCH /scenes/{id}` 默认只更新主实体，不能隐式覆盖整棵子实体树。

如确实需要整棵聚合替换，必须使用显式命令（`POST /{resource}/{id}/replace-aggregate`，`FULL_AGGREGATE_REPLACE`），路径形态见 `api-url-regex-charter.md` §2.3 C4。

## 1.1 主实体接口与完整聚合接口并存

当业务同时需要“只处理主实体”和“按聚合整体处理”两类接口时，不要让同一个路径承载两种语义。治理规则是：标准 API 只选择一种默认语义，另一类通过 `alternateAggregateApis` 显式声明。

推荐做法：

| 类型 | 示例 API | requestScope | responseScope | 说明 |
|------|----------|--------------|---------------|------|
| 默认详情 | `GET /scenes/{id}` | `NONE` | `FULL_AGGREGATE` | 面向业务详情页，返回完整聚合 |
| 主实体详情 | `GET /scenes/{id}/root` | `NONE` | `ROOT_ENTITY_ONLY` | 只返回 `scene_main`，不内嵌子实体 |
| 默认创建 | `POST /scenes` | `FULL_AGGREGATE` | `FULL_AGGREGATE` | 新建场景时可同时提交产品清单 |
| 主实体创建 | `POST /scenes/root` | `ROOT_ENTITY_ONLY` | `ROOT_ENTITY_ONLY` | 只创建主实体，子实体后续独立维护 |
| 默认更新 | `PATCH /scenes/{id}` | `ROOT_ENTITY_ONLY` | `ROOT_ENTITY_ONLY` | 普通编辑场景只改主实体 |
| 聚合增量更新 | `PATCH /scenes/{id}/aggregate` | `FULL_AGGREGATE_PATCH` | `FULL_AGGREGATE` | 显式提交主实体和子实体变更 |
| 聚合整体替换 | `POST /scenes/{id}/replace-aggregate` | `FULL_AGGREGATE_REPLACE` | `FULL_AGGREGATE` | 整棵聚合替换，高风险，需单独权限和审计 |

`alternateAggregateApis` 示例：

```json
{
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
```

如果 `deleteScope=ROOT_ENTITY_ONLY`，必须声明 `orphanPolicy`，避免删除主实体后留下无主子实体：

| orphanPolicy | 含义 |
|---------------|------|
| `DENY_DELETE_WHEN_CHILD_EXISTS` | 存在子实体时禁止删除主实体，推荐默认值 |
| `KEEP_CHILDREN_AS_HISTORY` | 保留子实体作为历史数据 |
| `DETACH_CHILDREN` | 将子实体外键置空，通常不推荐 |
| `MANUAL_CLEANUP_REQUIRED` | 允许删除但标记需要人工清理 |

## 1.2 标准 CRUD 虚拟 Operation

标准 CRUD API 必须在发布态形成可解析的 Operation，但不要求全部写入 `OPERATION` Fragment。治理规则是：

1. 设计态 `OPERATION` Fragment 只维护自定义业务操作、标准 CRUD 的业务化覆盖项，以及需要显式声明的编辑会话、锁释放、状态流转等 API 行为。
2. 标准列表、详情、创建、更新、删除、批量创建、批量更新、批量删除、复杂查询等 Operation 由发布服务根据 `MODEL.apiConfig`、`aggregateApiPolicy`、`entityApiPolicy` 自动生成。
3. 这些自动生成的 Operation 称为“标准 CRUD 虚拟 Operation”，必须进入发布态 BO schema、API 合同和路由解析表。
4. 如果 `OPERATION` Fragment 中显式声明了同一路由或同一语义的操作，以显式 Operation 为准，并保留业务化命名、展示位置、触发事件等治理信息；不得保存原型文件、按钮文案、事件函数或 `prototypeRefs`。
5. 权限项仍按虚拟或显式 Operation 的 `authzAction` 统一派生，不因 Operation 是否虚拟而改变。

> 聚合根标准虚拟 Operation 的完整清单（`LIST` / `SEARCH` / `READ` / `BATCH_QUERY` / `CREATE` / `BATCH_CREATE` / `UPDATE` / `BATCH_UPDATE` / `DELETE` / `BATCH_DELETE`）
> 及其 API 路径、默认 `authzAction`、来源，见 `api-url-regex-charter.md` §2（A1~A4、B1~B7）。
> 本文件不重复该表格。

`alternateAggregateApis` 和 `alternateEntityApis` 也应生成虚拟 Operation。它们通常不是普通 CRUD 的重复，而是“主实体接口”“完整聚合接口”“局部聚合接口”等明确语义的派生操作，例如 `PATCH_SCENE_AGGREGATE`、`REPLACE_SCENE_AGGREGATE`。

scenes 当前 `scenes-operation.fragment.json` 中显式声明了 `CREATE`、`OPEN_EDIT_SCENE`、`EDIT_SCENE` 等操作，是因为这些操作需要业务化命名、编辑会话或显式 API 语义。未显式声明的 `LIST`、`READ`、`DELETE` 等仍应由发布服务作为标准 CRUD 虚拟 Operation 生成。

## 2. 子实体 API

子实体通过 `parentEntityCode + parentRefField + routeSegment` 生成嵌套路由。

> 子实体标准 CRUD 的完整路径形态（创建/查询/更新/删除/批量创建/批量更新/批量删除）见 `api-url-regex-charter.md` §2.3 C7~C8、§2.4 D1~D5。
> 本文件不重复该表格。

多级子实体仍按聚合根路径进入，路由可按父实体嵌套展开，也可由应用层提供聚合内专用命令接口。治理默认要求任何子实体操作都不能暴露独立顶级路由。

子实体 API 只处理目标子实体及其必要的下级一致性，不改变聚合根 API 的默认 `updateScope`。例如 `PATCH /scenes/{id}` 不应顺带覆盖 `products`，产品清单变更应走 `/scenes/{id}/products` 或 `CREATE_PRODUCT / EDIT_PRODUCT_LIST` 这类聚合内命令。

## 2.1 多级子实体局部聚合接口

多级子实体也可能同时需要“只处理实体本体”和“按局部聚合整体处理”的两类接口。以 `scene_product` 为例：

```text
scene_product
	scene_product_accessory
	scene_annual_estimate
```

推荐使用 `entityApiPolicy`：

| 类型 | 示例 API | requestScope | responseScope | 说明 |
|------|----------|--------------|---------------|------|
| 产品行列表 | `GET /scenes/{id}/products` | `NONE` | `ENTITY_SUMMARY` | 返回产品行列表，不内嵌典配和年度测算 |
| 产品行更新 | `PATCH /scenes/{id}/products/{subId}` | `ENTITY_ONLY` | `ENTITY_ONLY` | 只更新产品行本体 |
| 产品局部聚合详情 | `GET /scenes/{id}/products/{subId}/aggregate` | `NONE` | `ENTITY_AGGREGATE` | 返回产品行 + 典配 + 年度测算 |
| 产品局部聚合更新 | `PATCH /scenes/{id}/products/{subId}/aggregate` | `ENTITY_AGGREGATE_PATCH` | `ENTITY_AGGREGATE` | 显式更新产品行及下级子实体 |

没有下级实体的普通子实体使用 Governance Profile 默认 `ENTITY_ONLY` 即可，不需要在每个实体上重复声明。

## 3. 自定义操作 API

`OPERATION` 描述“系统允许有哪些业务行为”，`RULE` 描述“这些行为在什么条件下允许执行、执行后触发什么派生或自动化”。API 合同派生时不能只看按钮或 HTTP 方法，还要合并 `RULE` 中与该操作相关的规则。

典型映射关系：

| 规则类型 | 对 API 的影响 |
|----------|---------------|
| `COMPLEX_VALIDATION` | 生成请求 DTO 校验、导入校验、错误提示 |
| `STATE` | 生成操作前置条件，例如只有 `DRAFT` 可编辑 |
| `CONSISTENCY` | 生成应用层事务内校验，例如删除前检查子实体 |
| `DERIVATION` | 生成响应或持久化后的汇总字段刷新要求 |
| `PERMISSION` | 生成权限项、策略模板和字段/数据范围控制 |
| `AUTOMATION` | 生成事件、异步任务或流程触发点 |

例如“编辑场景”和“保存修改”在界面上可能是两个按钮或两个事件，但在 API 治理上应归并为同一个 `EDIT_SCENE` Operation；在 PSP 权限治理上应归并为同一个 `UPDATE` 权限项。是否允许保存，由 `UPDATE` 权限项加 `STATE` / `PERMISSION` / `VALIDATION` 规则共同决定。

### 3.1 URL 到 BO / Operation 的解析

API 治理的目标是通过 `HTTP Method + URL Template` 可以稳定定位到 BO 和 Operation。这个目标不要求每个 URL 显式绑定 PSP 权限项 ID，也不建议在 API 合同里写死 `perm_item_id`。正确链路是两段式推导：

```text
HTTP Method + URL Template
	-> BO 定位：boCode / authz_bo_meta_model.id
	-> Operation 定位：显式 operation.code 或标准 CRUD 虚拟 Operation
	-> PSP 权限动作：operation.authzAction
	-> PSP 权限项：RES_DATA_BO + authz_bo_meta_model.id + authzAction
```

因此，当 BO Operation 与 PSP `act_code` 完全一致时，可以省略 `authzAction`，由发布服务按默认规则推导。当二者不一致时，只在 Operation 元数据上声明 `authzAction`，不要在 API 路由上显式绑定权限项。这里的 `authzAction` 不是把 Operation 硬绑定到某条权限项 ID，而是多个 Operation 归并为同一权限项的动作聚合键。

| API 示例 | URL 定位结果 | PSP 权限项推导 |
|----------|--------------|----------------|
| `GET /scenes` | `BO=scenes`，标准列表查询 Operation | `RES_DATA_BO + SCENE_BO_ID + READ` |
| `GET /scenes/{id}` | `BO=scenes`，标准详情查询 Operation | `RES_DATA_BO + SCENE_BO_ID + READ` |
| `PATCH /scenes/{id}` | `BO=scenes`，`Operation=EDIT_SCENE` | `RES_DATA_BO + SCENE_BO_ID + UPDATE` |
| `POST /scenes` | `BO=scenes`，`Operation=CREATE` | `RES_DATA_BO + SCENE_BO_ID + CREATE` |
| `POST /scenes/{id}/rivals/adjust` | `BO=scenes`，`Operation=ADJUST_RIVAL` | `RES_DATA_BO + SCENE_BO_ID + ADJUST_RIVAL` |

发布服务需要生成或校验一张路由解析表，但这张表只负责 API 到 BO / Operation 的归属，不负责手工绑定权限项：

```json
{
	"method": "PATCH",
	"pathTemplate": "/scenes/{id}",
	"boCode": "scenes",
	"operationCode": "EDIT_SCENE",
	"authzAction": "UPDATE"
}
```

其中 `authzAction` 是从 Operation 元数据复制出来的派生值，便于网关、拦截器或审计日志快速判断；它不是人工维护的 API 到权限项绑定。真正的权限项仍由 `RES_DATA_BO + boMetaId + authzAction` 确定，发布态可以再反向生成 `permissionItem -> operations` 清单，供授权配置、审计和文档展示使用。

> 发布校验规则的完整清单见 `api-governance-charter.md` 第九章发布校验清单。本文件不重复。

这样处理后，URL 仍然能明确定位 BO 和 Operation；PSP 权限项也仍然可由 BO 元数据和 Operation 元数据确定性推导，只是中间多了一个受治理的 `authzAction` 投影层。

### 3.2 Operation 到 PSP 权限项

`operationKind` 描述业务操作类型，`authzAction` 描述发布到 PSP 的授权动作，两者不能混用。发布服务应优先使用 `operation.authzAction` 生成 `authz_permission_item.act_code`；未配置时才按默认规则从 `operationKind` 推导。

| 界面/请求阶段 | Operation 表达 | PSP `act_code` | 权限语义 |
|---------------|----------------|----------------|----------|
| 查看列表、查看详情、请求查看态数据 | `operationKind=CUSTOM` 或标准查询 API | `READ`，兼容别名 `VIEW` | 控制能不能看列表、详情、查看态数据 |
| 点击编辑、打开编辑会话、保存编辑结果、释放/续租编辑锁 | 打开/释放/续租使用 `operationKind=CUSTOM`，保存使用 `operationKind=UPDATE` | `UPDATE`，兼容别名 `EDIT` | 控制编辑按钮显示、编辑会话申请、表单可编辑和提交修改；不得拆出 `SAVE`、`LOCK`、`UNLOCK` 权限项 |
| 点击新增、打开新增弹窗、保存新增结果 | `operationKind=CREATE` | `CREATE` | 控制新增按钮显示、表单可填写和提交创建 |
| 删除 | `operationKind=DELETE` | `DELETE` | 控制删除按钮和删除请求 |
| 导入、导出 | `operationKind=IMPORT/EXPORT` | `IMPORT` / `EXPORT` | 独立的数据交换能力 |
| 提交审批、发布、归档、作废 | `operationKind=STATE_CHANGE` 或 `CUSTOM` | `SUBMIT` / `PUBLISH` / `ARCHIVE` / `VOID` 等独立动作 | 独立业务行为，不复用 `SAVE`、`UPDATE` 或 `CREATE` |

发布到 PSP 时，BO 权限项仍使用同一条 BO 元数据作为资源：

```text
authz_permission_item.res_model_code = RES_DATA_BO
authz_permission_item.res_id         = authz_bo_meta_model.id
authz_permission_item.act_code       = operation.authzAction
```

由于 PSP 权限项唯一键是 `tenant_id + app_code + res_model_code + res_id + act_code`，同一个 BO 下相同 `authzAction` 会合并为一条权限项。这是解决“能编辑但不能保存”困惑的关键：编辑按钮、编辑会话申请、保存修改、释放/续租编辑锁都归并到 `UPDATE`，新增按钮、新增弹窗、保存新增都归并到 `CREATE`。如果某个操作必须单独授权，例如发布、归档、作废或竞对调整，应给它独立 `authzAction`，而不是再拆一个 `SAVE`。

默认推导规则如下：

| `operationKind` / HTTP 语义 | 默认 `authzAction` |
|-----------------------------|--------------------|
| 查询、详情、查看态请求、`GET` | `READ` |
| `CREATE` | `CREATE` |
| `UPDATE`、编辑、保存修改 | `UPDATE` |
| `DELETE` | `DELETE` |
| `IMPORT` | `IMPORT` |
| `EXPORT` | `EXPORT` |
| `STATE_CHANGE` / `CUSTOM` | 必须显式配置 `authzAction` |

如果项目希望“编辑场景基础信息”和“编辑产品清单”共用一个 scenes 更新权限，二者都配置 `authzAction=UPDATE`。如果希望它们分开授权，当前 PSP 表结构不能在同一个 `RES_DATA_BO + boMetaId + UPDATE` 下再区分 operationCode，必须为独立操作配置不同的 `authzAction`，或者扩展 PSP 权限项模型增加 operation 维度。

这里的 `authzAction` 是 Operation 到 PSP 的标准投影，不是 API 到权限项的显式绑定。API 只需要保证 URL 能解析到正确 Operation；权限项由发布服务按上述规则统一生成。

### 3.3 权限项包含多个 Operation

可以让发布态权限项反向包含多个 Operation，但不建议把它作为设计态的主维护方式。推荐模型是：

```text
Operation.authzAction
  -> group by boMetaId + authzAction
  -> authz_permission_item
  -> derived permissionItem.operations[]
```

也就是说，`authzAction` 是归并规则，`permissionItem.operations[]` 是发布结果。这样既能实现 URL 到权限项的关联，也能避免重复维护两套关系。

示例：

```json
{
	"permItem": {
		"resModelCode": "RES_DATA_BO",
		"resId": "SCENE_BO_ID",
		"actCode": "UPDATE"
	},
	"operations": [
		"EDIT_SCENE",
		"EDIT_PRODUCT"
	]
}
```

两种方案的取舍：

| 方案 | 优点 | 风险 | 推荐结论 |
|------|------|------|----------|
| 在 Operation 上声明或推导 `authzAction` | Operation 是 URL 解析的直接目标，发布服务可确定性生成权限项；多个 Operation 共享权限项只需相同 `authzAction` | 需要解释清楚它不是权限项 ID 绑定 | 推荐作为设计态主规则 |
| 在权限项上手工维护包含的 Operation 列表 | 授权管理员容易看到“一项权限控制哪些操作” | 与 Operation/API 路由双向重复，容易漏配、循环依赖；变更权限项分组会影响既有授权分配 | 只推荐作为发布态派生视图或治理报告 |

如果业务确实希望人工配置“权限包”，应把它命名为权限分组或授权包，而不是替代 PSP 的 `authz_permission_item`。权限分组可以包含多个权限项，权限项再由 `RES_DATA_BO + boMetaId + authzAction` 唯一确定。

> 自定义操作路由模式（`scope` × `supportsBatch` → 路径模板）见 `api-url-regex-charter.md` §3.2 路径分类正则及 §2 URL 路径形态全集。本文件不重复该表格。

## 4. 返回值规则

> 返回值强制规则见 `api-governance-charter.md` 第六章响应封装与返回值。本文件不重复。
>
> 核心要点：所有 HTTP API 必须使用 `ApiResponse<T>`；单条操作返回单个 DTO 或 `Void`；
> 批量操作返回 `BatchResultDTO`；导出类异步操作返回任务 DTO；
> 查询接口分为简单查询 `GET`、复杂查询 `POST /search`、已知 ID 批量查询 `POST /batch/query`。
