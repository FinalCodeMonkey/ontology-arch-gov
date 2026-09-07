# Governance Profile 配置说明

Governance Profile 是公司或项目级 BO 元数据治理默认参数文件。它解决的问题是：schema 表达能力较完整，参数较多，但一个项目通常只需要先确定一组稳定默认值，单个 BO 只声明业务差异。

默认参数文件：`government/arch/config/governance-profile.default.json`。

## 使用规则

发布合成时按以下优先级取值：

```text
BO Fragment 显式配置
  > Governance Profile 默认配置
  > JSON Schema 默认值
```

实施建议：

1. 项目启动时先评审 Governance Profile。
2. 只把公司级、项目级稳定规范放入 Profile。
3. 单个 BO 的特殊规则写入对应 Fragment，不修改默认 Profile。
4. 发布服务输出最终生效值，用于审计和问题排查。

其中 `VALIDATION` 与 `SECURITY` 是规则体系的专用子集；跨字段、状态流转、派生计算、聚合一致性和自动化触发等规则应进入 `RULE`。如果当前项目尚未落地 `RULE` Fragment，可先继续维护 `VALIDATION` / `SECURITY`，发布服务后续再将它们投影进统一规则目录。

## 核心参数组

| 参数组 | 作用 | 是否建议项目启动前固定 |
|--------|------|------------------------|
| `apiDefaults` | API 响应、路径、聚合根和子实体 API 默认范围 | 是 |
| `metadataDefaults` | 主实体/聚合根关系、业务键、父引用字段命名 | 是 |
| `securityDefaults` | 行级回退、字段权限、资源模型派生要求 | 是 |
| `operationExtractionDefaults` | 是否允许原型按钮作为离线 Operation 候选输入，过滤哪些 UI 动作 | 是 |

## 常用选项速查

### 聚合根 API 范围

| 字段 | 推荐值 | 选项 |
|------|--------|------|
| `listProjectionScope` | `ROOT_SUMMARY` | `ROOT_SUMMARY` / `ROOT_ENTITY_ONLY` / `FULL_AGGREGATE` |
| `readScope` | `FULL_AGGREGATE` | `FULL_AGGREGATE` / `ROOT_ENTITY_ONLY` |
| `createScope` | `FULL_AGGREGATE` | `FULL_AGGREGATE` / `ROOT_ENTITY_ONLY` |
| `updateScope` | `ROOT_ENTITY_ONLY` | `ROOT_ENTITY_ONLY` / `FULL_AGGREGATE_PATCH` / `FULL_AGGREGATE_REPLACE` |
| `deleteScope` | `CASCADE_AGGREGATE` | `CASCADE_AGGREGATE` / `ROOT_ENTITY_ONLY` |
| `orphanPolicy` | `DENY_DELETE_WHEN_CHILD_EXISTS` | `DENY_DELETE_WHEN_CHILD_EXISTS` / `KEEP_CHILDREN_AS_HISTORY` / `DETACH_CHILDREN` / `MANUAL_CLEANUP_REQUIRED` |

### 子实体 API 范围

| 字段 | 推荐值 | 选项 |
|------|--------|------|
| `listProjectionScope` | `ENTITY_SUMMARY` | `ENTITY_SUMMARY` / `ENTITY_ONLY` / `ENTITY_AGGREGATE` |
| `readScope` | `ENTITY_ONLY` | `ENTITY_ONLY` / `ENTITY_AGGREGATE` |
| `createScope` | `ENTITY_ONLY` | `ENTITY_ONLY` / `ENTITY_AGGREGATE` |
| `updateScope` | `ENTITY_ONLY` | `ENTITY_ONLY` / `ENTITY_AGGREGATE_PATCH` / `ENTITY_AGGREGATE_REPLACE` |
| `deleteScope` | `ENTITY_ONLY` | `ENTITY_ONLY` / `CASCADE_CHILDREN` |

### 元数据建模

| 字段 | 推荐值 | 说明 |
|------|--------|------|
| `primaryEntityMustBeAggregateRoot` | `true` | 标准 BO 下技术主实体和领域聚合根保持一致 |
| `businessKeyNaming` | `{bo_snake}_no` | 例如 `scene_no`、`customer_no`，比统一 `biz_no` 更有语义 |
| `technicalIdField` | `id` | 技术主键默认字段 |
| `routeSegmentDefault` | `plural-entity-name` | 子实体路由使用复数名词 |
| `parentRefFieldDefault` | `semantic-parent-id` | 推荐 `scene_id`、`line_id`，不强制 `parent_id` |

### 安全默认值

| 字段 | 推荐值 | 说明 |
|------|--------|------|
| `rowFallbackScope` | `NONE` | 无 DATA 策略命中时默认无权，失败关闭 |
| `fieldControl` | `OPEN` | 字段默认开放，敏感字段在 BO 中显式声明 |
| `privacyClass` | `PUBLIC` | 默认公开，敏感字段显式覆盖 |
| `authzProjectionRequiredForResourceBo` | `true` | 可授权资源 BO 必须提供随 BO 元数据发布的权限属性投影 |

## 配置示例

如果某个 BO 的详情页性能压力大，只想默认查询主实体，可以在该 BO 的 `MODEL` Fragment 中覆盖：

```json
{
  "apiConfig": {
    "aggregateApiPolicy": {
      "readScope": "ROOT_ENTITY_ONLY"
    }
  }
}
```

如果某个子实体存在下级子实体，并需要局部聚合接口，可以在该实体上覆盖：

```json
{
  "code": "scene_product",
  "entityApiPolicy": {
    "readScope": "ENTITY_ONLY",
    "updateScope": "ENTITY_ONLY",
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
