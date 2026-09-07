# BO Fragment Schema 版本策略

## 版本层级

| 层级 | 版本号 | 追踪对象 |
|------|--------|---------|
| 信封 | `schemaVersion` | `bo-meta-fragment.schema.json` 自身的结构版本 |
| 子 Schema | `$id` 路径 | 各子 fragment schema（model / validation / security / rule / view / operation / link / derivation / temporal / action-chain / expression-ast）独立版本化 |

## 版本升级规则

- **信封 `schemaVersion` 升级**：当任一子 fragment schema 发生**不兼容结构变更**时，子 schema 的 `$id` 应变更（如加版本路径段），信封的 `schemaVersion` 随之升级以反映组合不兼容。
- **无需升级信封**：仅子 fragment 内部新增可选字段不构成不兼容变更。

## 当前版本

| 组件 | 版本 | 说明 |
|------|------|------|
| 信封 | `2.0` | 当前最新 |
| validation 子 Schema | v3 | `enum` 从 `string[]` 改为 `{value,label}` 对象数组 |
| security 子 Schema | v3 | `allowedValues` 从 `string[]` 改为 `{value,label}` 对象数组 |
