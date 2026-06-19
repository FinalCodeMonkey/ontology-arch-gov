# API 治理映射规则

本文件说明 BO 发布态 `schema_view` 如何映射为 API 合同。

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

标准 API 为：

| 动作 | Method | API | 处理范围 | 返回 |
|------|--------|-----|----------|------|
| 创建 | POST | `/scenes` | `createScope=FULL_AGGREGATE`，允许提交主实体与子实体 | `ApiResponse<SceneDTO>` |
| 批量创建 | POST | `/scenes/batch` | 批量创建完整聚合，逐条返回处理结果 | `ApiResponse<BatchResultDTO>` |
| 简单查询 | GET | `/scenes?param=value` | `listProjectionScope=ROOT_SUMMARY`，返回主实体加汇总/投影字段 | `ApiResponse<PageResult<SceneDTO>>` |
| 复杂查询 | POST | `/scenes/search` | `listProjectionScope=ROOT_SUMMARY`，条件复杂但不操作数据 | `ApiResponse<PageResult<SceneDTO>>` |
| 查询单条 | GET | `/scenes/{id}` | `readScope=FULL_AGGREGATE`，返回完整聚合并内嵌子实体 | `ApiResponse<SceneDTO>` |
| 批量查询 | POST | `/scenes/batch/query` | 按已知 ID 批量查询完整聚合或配置的详情投影 | `ApiResponse<List<SceneDTO>>` |
| 更新 | PATCH | `/scenes/{id}` | `updateScope=ROOT_ENTITY_ONLY`，只更新聚合根主实体字段 | `ApiResponse<SceneDTO>` |
| 批量更新 | PATCH | `/scenes/batch` | 批量更新聚合根主实体字段 | `ApiResponse<BatchResultDTO>` |
| 删除 | DELETE | `/scenes/{id}` | `deleteScope=CASCADE_AGGREGATE`，删除聚合根并级联处理子实体 | `ApiResponse<Void>` |
| 批量删除 | DELETE | `/scenes/batch` | 批量删除聚合根并级联处理子实体 | `ApiResponse<BatchResultDTO>` |

> 重要：聚合根 API 面向 BO 聚合，不等同于只面向 `scene_main` 主表；但不同 HTTP 动作的处理范围必须由 `aggregateApiPolicy` 显式声明。普通 `PATCH /scenes/{id}` 默认只更新主实体，不能隐式覆盖整棵子实体树。

如确实需要整棵聚合替换，必须使用显式命令，例如：

| 动作 | Method | API | 处理范围 | 返回 |
|------|--------|-----|----------|------|
| 替换完整聚合 | POST | `/scenes/{id}/replace-aggregate` | `FULL_AGGREGATE_REPLACE`，整体替换主实体与子实体 | `ApiResponse<SceneDTO>` |

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

1. 设计态 `OPERATION` Fragment 只维护自定义业务操作、需要原型追溯的按钮操作、标准 CRUD 的业务化覆盖项。
2. 标准列表、详情、创建、更新、删除、批量创建、批量更新、批量删除、复杂查询等 Operation 由发布服务根据 `MODEL.apiConfig`、`aggregateApiPolicy`、`entityApiPolicy` 自动生成。
3. 这些自动生成的 Operation 称为“标准 CRUD 虚拟 Operation”，必须进入发布态 BO schema、API 合同和路由解析表。
4. 如果 `OPERATION` Fragment 中显式声明了同一路由或同一语义的操作，以显式 Operation 为准，并保留 `prototypeRefs`、展示位置、触发事件等界面追溯信息。
5. 权限项仍按虚拟或显式 Operation 的 `authzAction` 统一派生，不因 Operation 是否虚拟而改变。

聚合根标准虚拟 Operation 建议如下：

| 虚拟 Operation | API | 默认 `authzAction` | 来源 |
|----------------|-----|--------------------|------|
| `LIST` | `GET /scenes` | `READ` | `resourcePath + listProjectionScope` |
| `SEARCH` | `POST /scenes/search` | `READ` | `searchEnabled=true` |
| `READ` | `GET /scenes/{id}` | `READ` | `readScope` |
| `BATCH_QUERY` | `POST /scenes/batch/query` | `READ` | `batchEnabled=true` |
| `CREATE` | `POST /scenes` | `CREATE` | `createScope` |
| `BATCH_CREATE` | `POST /scenes/batch` | `CREATE` | `batchEnabled=true` |
| `UPDATE` | `PATCH /scenes/{id}` | `UPDATE` | `updateScope` |
| `BATCH_UPDATE` | `PATCH /scenes/batch` | `UPDATE` | `batchEnabled=true` |
| `DELETE` | `DELETE /scenes/{id}` | `DELETE` | `deleteScope` |
| `BATCH_DELETE` | `DELETE /scenes/batch` | `DELETE` | `batchEnabled=true` |

`alternateAggregateApis` 和 `alternateEntityApis` 也应生成虚拟 Operation。它们通常不是普通 CRUD 的重复，而是“主实体接口”“完整聚合接口”“局部聚合接口”等明确语义的派生操作，例如 `PATCH_SCENE_AGGREGATE`、`REPLACE_SCENE_AGGREGATE`。

SCENE 当前 `scene-operation.fragment.json` 中显式声明了 `CREATE` 和 `EDIT_SCENE`，是因为原型中有明确的新建、编辑入口，需要保留按钮来源和交互语义。未显式声明的 `LIST`、`READ`、`DELETE` 等仍应由发布服务作为标准 CRUD 虚拟 Operation 生成。

## 2. 子实体 API

子实体通过 `parentEntityCode + parentRefField + routeSegment` 生成嵌套路由。

示例：`scene_product.routeSegment=products`。

| 动作 | Method | API |
|------|--------|-----|
| 创建产品行 | POST | `/scenes/{id}/products` |
| 查询产品行 | GET | `/scenes/{id}/products` |
| 更新产品行 | PATCH | `/scenes/{id}/products/{subId}` |
| 删除产品行 | DELETE | `/scenes/{id}/products/{subId}` |
| 批量创建 | POST | `/scenes/{id}/products/batch` |
| 批量更新 | PATCH | `/scenes/{id}/products/batch` |
| 批量删除 | DELETE | `/scenes/{id}/products/batch` |

多级子实体仍按聚合根路径进入，路由可按父实体嵌套展开，也可由应用层提供聚合内专用命令接口。治理默认要求任何子实体操作都不能暴露独立顶级路由。

子实体 API 只处理目标子实体及其必要的下级一致性，不改变聚合根 API 的默认 `updateScope`。例如 `PATCH /scenes/{id}` 不应顺带覆盖 `products`，产品清单变更应走 `/scenes/{id}/products` 或 `CREATE_PRODUCT_LIST / EDIT_PRODUCT_LIST` 这类聚合内命令。

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
| `VALIDATION` | 生成请求 DTO 校验、导入校验、错误提示 |
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
| `GET /scenes` | `BO=SCENE`，标准列表查询 Operation | `RES_DATA_BO + SCENE_BO_ID + READ` |
| `GET /scenes/{id}` | `BO=SCENE`，标准详情查询 Operation | `RES_DATA_BO + SCENE_BO_ID + READ` |
| `PATCH /scenes/{id}` | `BO=SCENE`，`Operation=EDIT_SCENE` | `RES_DATA_BO + SCENE_BO_ID + UPDATE` |
| `POST /scenes` | `BO=SCENE`，`Operation=CREATE` | `RES_DATA_BO + SCENE_BO_ID + CREATE` |
| `POST /scenes/{id}/rivals/adjust` | `BO=SCENE`，`Operation=ADJUST_RIVAL` | `RES_DATA_BO + SCENE_BO_ID + ADJUST_RIVAL` |

发布服务需要生成或校验一张路由解析表，但这张表只负责 API 到 BO / Operation 的归属，不负责手工绑定权限项：

```json
{
	"method": "PATCH",
	"pathTemplate": "/scenes/{id}",
	"boCode": "SCENE",
	"operationCode": "EDIT_SCENE",
	"authzAction": "UPDATE"
}
```

其中 `authzAction` 是从 Operation 元数据复制出来的派生值，便于网关、拦截器或审计日志快速判断；它不是人工维护的 API 到权限项绑定。真正的权限项仍由 `RES_DATA_BO + boMetaId + authzAction` 确定，发布态可以再反向生成 `permissionItem -> operations` 清单，供授权配置、审计和文档展示使用。

发布校验规则：

1. 每个受保护 URL 必须能解析出唯一 BO。
2. 写操作、自定义操作和状态流转 URL 必须能解析出唯一 Operation。
3. Operation 必须能得到唯一 `authzAction`；`STATE_CHANGE` 和 `CUSTOM` 不允许缺省。
4. 禁止 API 合同直接保存 `perm_item_id`，权限项由 `RES_DATA_BO + boMetaId + authzAction` 确定性派生。
5. 如果多个 Operation 映射到同一个 `authzAction`，发布服务应输出合并提示，并生成 `permissionItem -> operations` 派生关系；这代表它们共享同一 PSP 权限项。
6. 如果业务要求多个 Operation 独立授权，必须配置不同 `authzAction`，或扩展 PSP 权限项模型增加 operation 维度。

这样处理后，URL 仍然能明确定位 BO 和 Operation；PSP 权限项也仍然可由 BO 元数据和 Operation 元数据确定性推导，只是中间多了一个受治理的 `authzAction` 投影层。

### 3.2 Operation 到 PSP 权限项

`operationKind` 描述业务操作类型，`authzAction` 描述发布到 PSP 的授权动作，两者不能混用。发布服务应优先使用 `operation.authzAction` 生成 `authz_permission_item.act_code`；未配置时才按默认规则从 `operationKind` 推导。

| 界面/请求阶段 | Operation 表达 | PSP `act_code` | 权限语义 |
|---------------|----------------|----------------|----------|
| 查看列表、查看详情、请求查看态数据 | `operationKind=CUSTOM` 或标准查询 API | `READ`，兼容别名 `VIEW` | 控制能不能看列表、详情、查看态数据 |
| 点击编辑、进入编辑态、保存编辑结果 | `operationKind=UPDATE` | `UPDATE`，兼容别名 `EDIT` | 控制编辑按钮显示、表单可编辑和提交修改 |
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

由于 PSP 权限项唯一键是 `tenant_id + app_code + res_model_code + res_id + act_code`，同一个 BO 下相同 `authzAction` 会合并为一条权限项。这是解决“能编辑但不能保存”困惑的关键：编辑按钮、编辑态、保存修改都归并到 `UPDATE`，新增按钮、新增弹窗、保存新增都归并到 `CREATE`。如果某个操作必须单独授权，例如发布、归档、作废或竞对调整，应给它独立 `authzAction`，而不是再拆一个 `SAVE`。

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

如果项目希望“编辑场景基础信息”和“编辑产品清单”共用一个 SCENE 更新权限，二者都配置 `authzAction=UPDATE`。如果希望它们分开授权，当前 PSP 表结构不能在同一个 `RES_DATA_BO + boMetaId + UPDATE` 下再区分 operationCode，必须为独立操作配置不同的 `authzAction`，或者扩展 PSP 权限项模型增加 operation 维度。

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
		"EDIT_PRODUCT_LIST",
		"MANAGE_ACCESSORY",
		"MANAGE_ANNUAL_ESTIMATE"
	]
}
```

两种方案的取舍：

| 方案 | 优点 | 风险 | 推荐结论 |
|------|------|------|----------|
| 在 Operation 上声明或推导 `authzAction` | Operation 是 URL 解析的直接目标，发布服务可确定性生成权限项；多个 Operation 共享权限项只需相同 `authzAction` | 需要解释清楚它不是权限项 ID 绑定 | 推荐作为设计态主规则 |
| 在权限项上手工维护包含的 Operation 列表 | 授权管理员容易看到“一项权限控制哪些操作” | 与 Operation/API 路由双向重复，容易漏配、循环依赖；变更权限项分组会影响既有授权分配 | 只推荐作为发布态派生视图或治理报告 |

如果业务确实希望人工配置“权限包”，应把它命名为权限分组或授权包，而不是替代 PSP 的 `authz_permission_item`。权限分组可以包含多个权限项，权限项再由 `RES_DATA_BO + boMetaId + authzAction` 唯一确定。

| scope | supportsBatch | 映射规则 |
|-------|---------------|----------|
| `BO` | `false` | `POST /scenes/{id}/{actionPath}` |
| `BO` | `true` | `POST /scenes/batch/{actionPath}` |
| `ENTITY` | `false` | `POST /scenes/{id}/{routeSegment}/{subId}/{actionPath}` |
| `ENTITY` | `true` | `POST /scenes/{id}/{routeSegment}/batch/{actionPath}` |
| `GLOBAL` | - | `POST /scenes/{actionPath}` |

## 4. 返回值规则

- 所有 HTTP API 必须使用 `ApiResponse<T>`。
- 单条操作返回单个 DTO 或 `Void`。
- 批量操作返回 `BatchResultDTO`。
- 导出类异步操作返回任务 DTO。
- 查询接口分为简单查询 `GET /resources`、复杂查询 `POST /resources/search`、已知 ID 批量查询 `POST /resources/batch/query`。
