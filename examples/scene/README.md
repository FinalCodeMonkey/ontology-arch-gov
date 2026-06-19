# SCENE 业务对象治理样例

`SCENE` 是场景管理业务对象，作为 BO 元数据治理的第一个样例对象。

## Fragment 文件

| 文件 | metaType | 说明 |
|------|----------|------|
| `fragments/scene-model.fragment.json` | `MODEL` | BO 身份、API 入口、主子实体、字段骨架、聚合角色、父子关系 |
| `fragments/scene-validation.fragment.json` | `VALIDATION` | 字段必填、唯一、范围、枚举、提示语 |
| `fragments/scene-security.fragment.json` | `SECURITY` | 行级字段白名单、字段安全、SCENE BO 元数据的 Authz Projection 规则 |
| `fragments/scene-rule.fragment.json` | `RULE` | 状态、派生、权限、一致性、自动化等本体规则；当前样例暂未提供物理文件 |
| `fragments/scene-view.fragment.json` | `VIEW` | 列表、表单、查询、导入导出、控件渲染配置 |
| `fragments/scene-operation.fragment.json` | `OPERATION` | 自定义业务操作、标准 CRUD 的业务化覆盖、API 契约、批量能力、触发方式 |

## 发布后派生产物

发布服务应将设计态 Fragment 合成为完整 BO Snapshot，并进一步派生：

1. `authz_bo_meta_model.schema_json`：完整 BO 发布态 schema_view。
2. `authz_bo_meta_model.schema_json.security/authzProjection`：`RES_SCENE` 权限属性投影，隶属于 SCENE 这条 BO 元数据。
3. UI Model：场景列表、详情、表单、查询条件。
4. API Contract：`/scenes` 聚合根接口族和子实体嵌套接口族。
5. Permission Items：标准 CRUD、行级数据权限、字段权限、自定义操作权限项。

本目录已提供三类派生态样例：

| 文件 | 说明 |
|------|------|
| `derived/res_scene.authz_bo_schema_view.json` | 从 `SECURITY.authzProjection` 派生的权限属性视图样例，发布时应随 SCENE BO 元数据进入 `authz_bo_meta_model.schema_json` |
| `derived/scene.api-contract.json` | 从 `MODEL + OPERATION` 派生的 API 合同样例 |
| `derived/scene.ui-model.json` | 从 `MODEL + VIEW + OPERATION` 派生的前端 UI 模型样例 |

`SECURITY` 到 PSP 的详细映射见 [../../docs/security-fragment-psp-mapping.md](../../docs/security-fragment-psp-mapping.md)。需要特别注意：`RES_SCENE` 与 PSP 的关系是绑定到 `authz_bo_meta_model` 中 SCENE 这条 BO 元数据；SCENE 数据权限项在当前 PSP 中使用 `RES_DATA_BO + authz_bo_meta_model.id + act_code` 定位该 BO。

## 关键治理约束

- `scene_main` 是实体，不是 BO；`SCENE` 才是 BO。
- `SCENE` 是 CRM 中我公司对线索对象的业务命名，商机基于场景产生。
- `scene_main.isPrimary=true` 且 `scene_main.aggregateRole=ROOT`。
- 多级子实体通过 `parentEntityCode` 与 `parentRefField` 串联。
- 物理外键不强制统一为 `parent_id`，但必须显式声明。
- `scene_no` 是业务唯一键，`id` 是技术主键，`attribute.code` 是元数据唯一标识。
- `OPERATION` Fragment 从界面原型按钮抽取，`prototypeRefs` 保留按钮来源；刷新、列设置、全屏、分页、Tab 切换等 UI utility 不进入业务 Operation。
- 标准 CRUD 虚拟 Operation 不需要全部写入 `scene-operation.fragment.json`；发布服务会从 `MODEL.apiConfig` 自动生成 `LIST`、`READ`、`DELETE`、批量操作等。当前显式 `CREATE`、`EDIT_SCENE` 是为了保留原型按钮来源和业务化命名。
- `OPERATION.authzAction` 用于派生 PSP `act_code`：查看态使用 `READ`，编辑按钮、编辑态和保存修改共用 `UPDATE`，新增按钮、新增弹窗和保存新增共用 `CREATE`；不得为保存动作单独生成 `SAVE` 权限项。
- SCENE API 不保存 `perm_item_id` 这类显式权限绑定；发布服务通过 `HTTP Method + URL Template` 先解析到 `SCENE + Operation`，再用 `Operation.authzAction` 推导 `RES_DATA_BO + authz_bo_meta_model.id + act_code`。发布态可以反向生成 `permissionItem -> operations` 清单，用于展示一条权限项覆盖哪些操作。
- 同一 SCENE BO 下相同 `authzAction` 会合并为同一条 PSP 权限项；提交审批、发布、归档、作废、竞对调整等独立业务行为应配置独立 `authzAction`。
- `VALIDATION` 与 `SECURITY` 是 `RULE` 的专用子集：前者承载字段和导入校验，后者承载权限资源投影、行级字段和字段安全；状态流转、派生计算、聚合一致性和自动化触发应进入 `RULE` Fragment。
- `apiConfig.aggregateApiPolicy` 声明聚合根 API 的处理范围：列表返回主实体摘要，详情和创建按完整聚合处理，普通 PATCH 只更新主实体，删除按聚合级联处理。
- `alternateAggregateApis` 为 SCENE 额外声明只处理主实体的 `/scenes/{id}/root`、`/scenes/root`，以及显式完整聚合更新 `/scenes/{id}/aggregate`、`/scenes/{id}/replace-aggregate`。
- `scene_product.entityApiPolicy` 声明产品清单作为聚合内部局部根：普通产品 API 只处理产品行本体，`/scenes/{id}/products/{subId}/aggregate` 显式处理产品行 + 典配 + 年度测算。
- 未显式配置 `entityApiPolicy` 的子实体使用 [governance-profile.default.json](../../config/governance-profile.default.json) 中的默认 `ENTITY_ONLY` 策略。
