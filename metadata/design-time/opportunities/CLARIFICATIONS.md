# 商机 BO 元数据 — 业务澄清记录

> 本文档记录元数据审计过程中提出的业务问题及其裁决结论，
> 避免同一问题在后续迭代中被重复质疑。

---

## B-1：`expected_bid_date` 对 OC_MAIN 不应 required

- **问题**：OC_MAIN 是集采框架协议，无招标环节。预计开标日期不应 required
- **裁决**：**暂不处理**。当前阶段 OC_MAIN 占比低，后续统一评估
- **日期**：2026-07-07

## B-2：`opportunity_owner` / `presales_engineer` 缺少 CROSS_BO_DISPLAY

- **问题**：两个 users 引用字段无 displayFields
- **裁决**：**补充**。新增 `opportunity_owner_name` + `presales_engineer_name` 两个 CROSS_BO_DISPLAY 属性
- **日期**：2026-07-07 ✅

## B-3：DELETE 操作缺少状态前置条件

- **问题**：ACTIVE/终态商机被误删将导致销售数据丢失
- **裁决**：**补充** RULE `OPPORTUNITY_STATUS_DELETE`：仅 DRAFT 可删除
- **日期**：2026-07-07 ✅

## B-4：`predict_category` 缺少方向约束

- **问题**：8 级置信度可能被随意回退，破坏预测准确性
- **裁决**：**补充** RULE `OPPORTUNITY_PREDICT_CATEGORY_ORDER`，severity=WARN（非硬阻断），由应用层二次确认
- **日期**：2026-07-07 ✅

## B-5：`opportunity-scene` 关联表管理入口

- **问题**：关联子实体 ASSOCIATION 无独立 OPERATION
- **裁决**：**无需操作**。关联子实体（entityNature: "ASSOCIATION"）的场景关联通过聚合根 create/update 时传入 sceneIds 批量管理，关联表由基础设施层自动维护。MODEL 中 ROOT entity 已有 `#sym:sceneIds` 标记（Domain 层持有 `List<Long> sceneIds`），结构完整
- **日期**：2026-07-07

## B-6：配件 VIEW 嵌套编辑入口

- **问题**：产品配件是产品行子行，应有树表嵌套编辑
- **裁决**：**无需操作**。VIEW 中 `opportunity-product-accessory` 的 fieldView 定义完整（editableInForm=true），树表嵌套由前端框架按 parentEntityCode 自动展开为行内子表。元数据层面已足够
- **日期**：2026-07-07

## B-7：CANCEL vs LOSE 的业务语义

- **问题**：DRAFT 可 CANCEL，但不能 LOSE。规则如何对齐？
- **建议**：
  - DRAFT → CANCEL：业务合理（草稿作废），保留
  - DRAFT → LOSE：语义矛盾（未跟进何来输单），RULE 已正确约束只有 ACTIVE 可 LOSE
  - CLOSED_LOST → CANCEL：RULE 中 cancel() 不允许 CLOSED_LOST 取消（`!=CLOSED_WON`），但 CLOSED_LOST 可 cancel
- **裁决**：**保持现状**。当前状态机规则本身自洽，无需调整
- **日期**：2026-07-07

## B-8：`createScope: FULL_AGGREGATE` 子实体必填策略

- **问题**：创建时产品清单/团队成员是否必填无声明
- **建议**：在 MODEL 的 `apiConfig` 或每个实体的属性上增加 `requiredOnCreate` 标记
- **裁决**：**暂时搁置，先不修改元数据**。当前业务上创建商机不强制附带产品或团队成员（两步向导可跳过第二步），元数据 `createScope: FULL_AGGREGATE` 表示"允许"而非"强制"。必填性由 VALIDATION 中 entity-level 的 required 控制
- **日期**：2026-07-07

## B-9：`quotation-product.scene_id` 是否存在

- **核实**：
  - `opportunity-quotation`（报价单头行）：**无** scene_id / scene_name
  - `opportunity-quotation-product`（报价单产品行）：**有** scene_id / scene_name（L1193-L1220）
- **裁决**：**存在且保留**。场景关联在报价单产品行级别而非报价单头行级别——同一报价单中不同产品行可能归属不同业务场景（如交换机归 DC 场景、路由器归 OC 场景）
- **日期**：2026-07-07 ✅（已核实，保留）

## B-10：`opportunity-stage-history` 缺少 `updated_time` / `updated_by`

- **问题**：阶段记录是可编辑的，应有更新审计字段
- **裁决**：**补充**。MODEL 中 stage-history 新增 `updated_time` + `updated_by`
- **日期**：2026-07-07 ✅

## B-11：`_has_quotation` 虚拟字段定义

- **问题**：VIEW 用 `_has_quotation` 控制显示切换，但不在任何 Fragment 中定义
- **裁决**：**无需在元数据定义**。这是应用层运行时布尔标记（`quotationList != null && !quotationList.isEmpty()`），由 ApplicationService 在 toDetailView() 中计算。不属于 MODEL 属性或常量枚举，不需要定义
- **日期**：2026-07-07
## B-14：移除 `customers_id` 和 `primary_customer_id` — 商机只关联业务主体客户

- **背景**：商机只关联业务主体客户（`customers_id`），`customers_id`（FOP 客户）不需要，`primary_customer_id`（一级客户）可通过 `customers_id` 的 parent 推导
- **变更**：
  - MODEL：移除 `customers_id` / `customer_name` / `primary_customer_id` / `primary_customer_name` 四个属性
  - VIEW：移除对应四个 fieldView；`customers_id` / `business_customer_name` 改为 `showInList: true`
  - VALIDATION：移除对应四个校验块
  - SECURITY：rowSecurity 移除 `customers_id` / `primary_customer_id`；authzProjection 移除两个属性定义
  - RULE：移除 `OPPORTUNITY_FOP_CUSTOMER_EXISTS` / `OPPORTUNITY_PRIMARY_CUSTOMER_EXISTS` 两条规则
  - DDL：移除 `customers_id` / `primary_customer_id` 列及对应索引
  - 一级客户名称由应用层根据 `customers_id` 查询 customers BO 的 parent 获取
- **日期**：2026-07-08 ✅

## B-15：新增 `primary_customer_name` — 方案 B 级联派生

- **背景**：商机详情需要展示一级客户名称，但商机不直接持有 `primary_customer_id`，一级客户通过 `customers_id → customers.parent_customer_id → customers.customer_name` 两步推导
- **方案**：方案 B — 纯应用层两阶段查询
  - MODEL：新增 `primary_customer_name` 属性（`semanticRole: CROSS_BO_DISPLAY`），标注 `_derivationPath` 和 `_resolution: APPLICATION_LAYER`，不产生 DB 列
  - VIEW：新增 `primary_customer_name` fieldView（`showInList: false, showInDetail: true, editableInForm: false`）
  - VALIDATION：不需要加校验（数据校验在源 BO customers 完成）
  - 应用层：`toDetailView()` 中 Phase 1 查 customers 拿 `parent_customer_id` 集合，Phase 2 批量查一级客户拿 `customer_name`
- **日期**：2026-07-08 ✅

## B-16：product_model 从 CROSS_BO_REF 改为 CROSS_BO_DISPLAY — 统一按 id 引用产品

- **背景**：products BO 中 `product_model` 不是主键，不应该作为 CROSS_BO_REF 的 `refFieldCode`。按 DDD 聚合根引用约定，跨 BO 引用 MUST 通过目标 BO 的 PK（id）完成
- **变更**：
  - MODEL：3 个实体（`opportunity-product` / `opportunity-product-accessory` / `opportunity-quotation-product`）新增 `product_id`（LONG, CROSS_BO_REF → products.id），原 `product_model` 改为 CROSS_BO_DISPLAY（`product_id.displayFields → product_model`）
  - VIEW：3 个实体各新增 `product_id` fieldView（OBJECT_SELECT / HIDDEN）+ `product_model` 改为 INPUT disabled（只读展示）
  - VALIDATION：`product_model` 必填校验改为 `product_id` 必填；`quotation-product.product_model` 仅保留 `max: 128`
  - DDL：3 个表各新增 `product_id BIGINT NOT NULL` 列；移除 `product_model` 冗余列及 `idx_product_model` 索引。`product_model` 采用 `redundant: false`（不存 DB），视图层由 ApplicationService 按 `product_id` 批量查 products BO 获取名称
  - 名称搜索：两阶段查询 — Phase 1 查 products 表按 model 名称 LIKE 匹配得 product_id 集合，Phase 2 `product_id IN (...)` 过滤
- **日期**：2026-07-08 ✅

## B-17：合并 `opportunity-product-accessory` 入 `opportunity-product` — 自引用树形结构

- **背景**：配件行（opportunity-product-accessory）与主产品行（opportunity-product）数据结构 80% 重叠，通过 `parent_product_id` 自引用即可表达主/配件关系，无需单独子实体表
- **变更**：
  - MODEL：`opportunity-product` 新增 `parent_product_id`（LONG, NULL=主产品行）+ `ratio`（INTEGER, 仅配件行填写）；删除 `opportunity-product-accessory` 整个 entity
  - VIEW：新增 `parent_product_id`（HIDDEN）+ `ratio`（NUMBER, visibleWhen: parent_product_id 非空）；删除 5 个 accessory fieldView
  - VALIDATION：新增 `ratio` 条件校验（min:1, 仅 parent_product_id 非空时生效）；删除 3 个 accessory 校验块
  - OPERATION：删除 `CREATE_PRODUCT_ACCESSORY` / `EDIT_PRODUCT_ACCESSORY` / `DELETE_PRODUCT_ACCESSORY` 三个操作
  - DDL：`crm_opportunity_product` 新增 `parent_product_id BIGINT DEFAULT NULL` + `ratio INT DEFAULT NULL` + `idx_parent_product_id` 索引；删除 `crm_opportunity_product_accessory` 整个表
- **日期**：2026-07-08 ✅

## B-12：深度排查（2026-07-07 第二轮审计）

以下问题在第二轮全量交叉排查中发现并已全部修复：

### S-1：DELETE OPERATION 描述与 RULE 状态约束冲突 ✅ 已修复

- **问题**：OPERATION DELETE.description 写"仅允许在非终态前执行"，但 RULE `OPPORTUNITY_STATUS_DELETE` 明确只允许 DRAFT 态删除
- **修复**：OPERATION description 改为"仅草稿态商机可删除，已跟进（ACTIVE）和已结束（终态）商机不可删除"

### S-2：`customer_owner` 缺失 displayFields、CROSS_BO_DISPLAY、rowSecurity ✅ 已修复

- **问题**：`customer_owner` 引用了 users BO 但无 `displayFields`，无 `customer_owner_name` CROSS_BO_DISPLAY，不在 rowSecurity 中
- **修复**：MODEL 增加 displayFields + `customer_owner_name`；VIEW 增加对应 fieldView；SECURITY rowSecurity 增加 `customer_owner`

### S-3：`uploaded_by` 缺失 displayFields ✅ 已修复

- **问题**：`opportunity-stage-attachment.uploaded_by` 无 displayFields，导致展示用户 ID 而非姓名
- **修复**：MODEL 增加 displayFields + `uploaded_by_name`；VIEW 中 `uploaded_by` 改为 HIDDEN，新增 `uploaded_by_name`

### W-1：`deleteScope=CASCADE_AGGREGATE` 与 `orphanPolicy` 语义矛盾 ✅ 已修复

- **问题**：`orphanPolicy` 仅在 `deleteScope=ROOT_ENTITY_ONLY` 时生效，与 `CASCADE_AGGREGATE` 并存无意义
- **修复**：移除 `orphanPolicy` 配置

### W-5：CROSS_BO_DISPLAY 字段被本 BO 校验 ✅ 已修复

- **问题**：`opportunity-scene.scene_category` / `scene_name` 为 CROSS_BO_DISPLAY，其枚举/长度校验应在 source BO（scenes）完成
- **修复**：移除 VALIDATION 中这两个字段的独立校验规则块

### W-6：`opportunity-product.scene_id` LONG 类型误用 `max:64` 字符串约束 ✅ 已修复

- **问题**：MODEL 中 `scene_id` 类型为 LONG，VALIDATION 中 `max: 64` 对数值类型无意义
- **修复**：移除 `max: 64`

### P-2：`opportunity-team-member.member_role` 无 `required` 约束 ✅ 已修复

- **问题**：VIEW 中配置了 SELECT + dictCode，暗示应为必选，但 VALIDATION 未声明 required
- **修复**：增加 `required: true` + message

### P-3：VIEW 缺少部分 HIDDEN fieldView ✅ 已修复

- **问题**：`user_id`（team-member）、`promoter`（stage-history）、`scene_id`（quotation-product）、`opportunity_id`（product）、`opportunity_product_id`（accessory）无 fieldView
- **修复**：补充 `formType: "HIDDEN"` 的 fieldView

- **日期**：2026-07-07 ✅

## B-13：深度排查（2026-07-07 第三轮全量交叉审计）

以下问题在第三轮全量交叉排查中发现：

### 🔴 D-1：`opportunity-product.scene_id` 空校验块 ✅ 已修复

- **问题**：VALIDATION 中 `opportunity-product.scene_id` 仅声明了 `entityCode` + `fieldCode`，无任何约束属性（required/min/max 全缺），是一个语义为空的无效校验块。删除后不影响任何行为，保留则会造成"已校验"的假象。
- **修复**：移除该空校验块

### 🔴 D-2：`opportunity-quotation-product.scene_name` 违反 CROSS_BO_DISPLAY 校验原则 ✅ 已修复

- **问题**：`quotation-product.scene_name` 在 MODEL 中 `semanticRole=CROSS_BO_DISPLAY`（数据来源是 scenes BO 的 scene_name_dept），但 VALIDATION 中仍保留了 `max: 200`。W-5 已将 `opportunity-scene.scene_category` / `scene_name` 的同类问题修复，此处为遗漏项。
- **修复**：移除 VALIDATION 中 `opportunity-quotation-product.scene_name` 的 `max: 200` 约束块

### 🔴 D-3：SECURITY `rowSecurity` 缺失 `parent_opportunity_id` ✅ 已修复

- **问题**：`parent_opportunity_id` 是自引用 CROSS_BO_REF（refBoCode=opportunities），是 OC 子项目关联框架主项目的关键字段。但不在 rowSecurity entriesByEntity.opportunity 列表中。这意味着 PSP DATA 策略无法基于父子关系做行级过滤（如"只能看自己负责框架主项目下的 OC 子项目"）。
- **修复**：将 `parent_opportunity_id` 加入 rowSecurity.entriesByEntity.opportunity 数组（追加在 `market_segment` 之后），并同步在 authzProjection 中新增 `parent_opportunity_id` 属性投影（nullable=true, onMissingValue=ALLOW，因仅 OC_SUB 有值）

### 🟡 W-2：`opportunity-product.quantity` 未声明 `required` ✅ 已修复

- **问题**：产品行数量字段在 VALIDATION 中只有 `min: 0`，无 `required: true`。UI 层面允许创建数量为空的产品行，但业务上数量为空的"幽灵产品行"无意义。
- **修复**：添加 `required: true`，message 更新为"数量不能为空且必须为非负整数"

### 🟡 W-3：`opportunity-scene` VIEW 缺 `scene_id` fieldView ✅ 已修复

- **问题**：ASSOCIATION 实体 `opportunity-scene` 在 VIEW 中只有 `id`、`scene_category`、`scene_name` 三个 fieldView，缺失 `scene_id`。关联场景通过聚合根 sceneIds 写入，`scene_id` 是 CROSS_BO_REF 外键字段，无 fieldView 意味着前端即使需要通过 ID 引用也无声明。
- **修复**：补充 `formType: "HIDDEN"` 的 scene_id fieldView（order=11，位于 id 之后）

### 🟡 W-4：`SUPPLEMENT_STAGE_ATTACHMENT` 的 `operationKind=UPDATE` + `httpMethod=POST` 组合

- **问题**：`SUPPLEMENT_STAGE_ATTACHMENT` 声明 `operationKind=UPDATE` + `httpMethod=POST`。业务语义是"仅补充附件"（文件上传），POST 合理，但与 `EDIT_STAGE_RECORD`（operationKind=UPDATE + httpMethod=PATCH）语义层次不同。发布服务自动推导时需确认该组合不会产生歧义。
- **严重度**：LOW — 发布服务校验点
- **建议**：确认发布服务的 OPERATION 合成逻辑正确处理 `operationKind != httpMethod` 的非默认映射。若发布服务校验放行，维持现状

### ✅ 一致性验证通过的完整清单

以下交叉验证维度全部通过，无问题：

| 验证项 | 详情 |
|--------|------|
| MODEL 实体 → VIEW fieldViews 覆盖 | 9 个实体（opportunity / product / accessory / team-member / scene / stage-history / stage-attachment / quotation / quotation-product）全部有对应 fieldViews |
| CROSS_BO_REF → CROSS_BO_DISPLAY 链路 | 11 条引用链路全部完整
| MODEL cascadeDelete 与 OPERATION | quotation / quotation-product（EXTERNAL_REF）cascadeDelete=false，其余子实体 cascadeDelete=true，与 OPERATION.DELETE 描述一致 |
| SECURITY fieldSecurity 与 MODEL | expected_order_amount MASKED / customer_owner RESTRICTED / unit_price MASKED / is_in_funnel & is_committed RESTRICTED 均已声明 |
| RULE 状态机 | 12 条 RULE 覆盖 DRAFT/ACTIVE/终态 × 8 个 STATE_CHANGE 操作的完整矩阵，无违反逻辑 |
| B-1~B-11 裁决落地 | 全部已在 MODEL/VIEW/VALIDATION/RULE/SECURITY Fragment 中体现 |
| PSP authzProjection | SECURITY 中 14 个属性投影覆盖 rowSecurity 声明的全部 13 个字段（多出 opportunity_name 展示用，合理） |
| OPERATION authzAction 独立性 | 11 个非标准 CRUD 操作各有独立 authzAction，不会在 PSP 发布时合并 |
| VIEW dataType 约定 | 所有 Long ID 字段 fieldView.dataType = "string"，符合 Snowflake 精度保护约定 |
| VALIDATION conditionalEnum | project_stage 按 project_type 分 5 组 conditionalEnum，与 SECURITY authzProjection allowedValues 完全一致（DC/OC_MAIN/OC_SUB/BC/EC 各 8/9/4/6/6 项） |
| created_by / updated_by 未标记 CROSS_BO_REF | 符合 copilot-instructions.md 6.1 节规定：审计字段 MUST NOT 标记为 CROSS_BO_REF |

- **日期**：2026-07-07 ✅
