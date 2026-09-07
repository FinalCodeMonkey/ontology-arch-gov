# BO 治理工具集

> 位于 `bo-arch-gov/tools/`，统一管理 BO 元数据的**可视化、校验、生成、发布全链路工具**。

## 快速开始

```powershell
# 启动服务并自动打开界面（一步完成）
.\bo-api.bat start

# 停止服务
.\bo-api.bat stop
```

> 启动后浏览器自动打开 http://127.0.0.1:8765 即显示可视化图谱界面。

---

## 目录结构

```
tools/
├── bo-api-server.py             # HTTP API 服务（端口 8765）
├── bo-ontology-graph.html       # 可视化图谱界面
├── bo-graph-viz.py              # Fragment → graph-data.json 解析器
├── bo-publish-gen.py            # Fragment → schema-view.v2 发布态生成器
├── bo-projection-gen.py         # schema-view.v2 → 多类型投影生成器 (authz / API / UI / 属性)
├── bo-ddl-gen.py                # MODEL → DDL 建表 SQL 生成器
├── bo-consistency-check.py     # 全量深度校验（JSON Schema + 结构 + 语义 + 跨BO引用 + 命名一致性）
├── graph-data.json              # 图谱数据（自动生成）
├── bo-api.bat                   # API 服务启动/停止脚本
└── README.md                    # 本文件
```

---

## 一、API 服务管理

### 通过 .bat 脚本

| 命令 | 功能 |
|------|------|
| `.\bo-api.bat start` | 后台启动服务（端口 8765） |
| `.\bo-api.bat stop` | 停止服务 |
| `.\bo-api.bat restart` | 重启服务 |

### 通过命令行

```powershell
# 启动（前台，Ctrl+C 停止）
python bo-api-server.py

# 指定端口
python bo-api-server.py --port 8888
```

### API 端点

| 端点 | 方法 | 请求体 | 功能 |
|------|------|--------|------|
| `/` | GET | — | 可视化图谱界面 |
| `/api/health` | POST | `{}` | 健康检查 |
| `/api/graph` | POST | `{}` | 重新解析 Fragment，生成 graph-data.json |
| `/api/validate` | POST | `{}` | 运行 bo-consistency-check.py 全面校验 |
| `/api/publish` | POST | `{"boCode":"customers"}` | 生成指定 BO 的 schema-view.v2 发布态，写入 release-time/ |
| `/api/projection` | POST | `{"boCode":"customers","projectionType":"authz_bo_meta_model"}` | 从发布态生成投影，写入 projection-run-time/，projectionType 可选值见下方 |
| `/api/ddl` | POST | `{"boCode":"customers"}` | 生成指定 BO 的 DDL 建表 SQL |
| `/api/inspect` | POST | `{"boCode":"customers","cmd":"all"}` | 数据库检查（drift/profile/validate/ref-integrity/all） |

---

## 二、界面方式

### 前提

必须启动 API 服务：`.\bo-api.bat start`

### 打开界面

启动服务后浏览器自动打开 http://127.0.0.1:8765。

也可手动访问：`start http://127.0.0.1:8765` 或直接双击 `bo-ontology-graph.html`（需在 `tools/` 目录下）。

### 工具栏按钮（图谱左上角）

| 按钮 | 功能 | 对应 API |
|------|------|---------|
| 🔍 搜索框 | 按 BO 名称 / 实体 / 属性搜索，高亮匹配节点 | — |
| ⊞ 适应 | 缩放至全图可视 | — |
| ↺ 重置布局 | 解冻并重新力导向布局，5 秒后自动冻结 | — |
| ⚡ 自动布局 | 切换图谱冻结/运动状态 | — |
| 🔄 重载图谱 | 重新解析所有 Fragment 并刷新图谱 | `/api/graph` |
| 🔍 校验检查 | 运行深度校验，弹窗展示结果 | `/api/validate` |
| 📦 全量发布元数据 | 批量生成所有 BO 的发布态 | `/api/publish` |
| 🎯 全量投影元数据 | 批量生成所有 BO 的投影（用下拉框选类型） | `/api/projection` |
| 🗄️ 全量DDL | 批量导出 DDL | `/api/ddl` |
| 🔬 全量探查 | 批量数据探查 | `/api/inspect` |

### 投影类型选择器

界面顶部和详情面板各有一个多选投影下拉框，支持 3 种投影目标（可多选）：

| 投影类型 | 代号 | 输出路径 | 说明 |
|----------|------|----------|------|
| 🔐 支持权限引擎 | `authz_bo_meta_model` | `projection-run-time/{boCode}/{boCode}.authz_bo_meta_model.schema_json.v2.json` | authz_bo_meta_model 表 schema_json 字段 |
| 📡 API 契约 | `api-contract` | `projection-run-time/{boCode}/{boCode}.api-contract.json` | REST 端点定义与聚合策略 |
| 🖥️ UI 模型 | `ui-model` | `projection-run-time/{boCode}/{boCode}.ui-model.json` | 前端列表列定义 |

### 详情面板按钮（点击任意 BO 节点后出现）

| 按钮 | 功能 | 前置条件 | 对应 API |
|------|------|---------|---------|
| 📦 发布 | 生成 schema-view.v2 发布态 JSON，写入 release-time/，弹窗展示 | 需选中 BO | `/api/publish` |
| 🎯 投影 | 从发布态生成选定类型的投影，写入 projection-run-time/，弹窗展示 | 需先点📦 | `/api/projection` |
| 🗄️ DDL | 生成当前 BO 的建表 SQL，弹窗展示+下载 | 需选中 BO | `/api/ddl` |
| 🔬 探查 | 连接数据库执行 DDL漂移/数据画像/校验/引用完整性 | 需选中 BO | `/api/inspect` |

### 图谱交互

- **单击节点** → 右侧展示 BO 详情（实体结构、属性、操作、安全策略、校验规则、视图配置）
- **双击节点** → 聚焦该节点
- **拖拽节点** → 调整布局
- **滚轮** → 缩放
- **点击 🔗 关联标签** → 跳转到关联 BO 的详情
- **实体卡片折叠** → 点击展开/收起属性列表
- **自引用** → 以环形标注，悬停 tooltip 显示 "⚠ 自引用"

---

## 三、命令行方式

### 1. 解析 Fragment → graph-data.json

```powershell
python bo-graph-viz.py
```

输出：`tools/graph-data.json`

### 2. 生成发布态（schema-view.v2）

```powershell
# 单个 BO
python bo-publish-gen.py customers

# 多个 BO
python bo-publish-gen.py customers scenes opportunities
```

输出：`metadata/release-time/{boCode}/{boCode}.schema-view.v2.json`

### 3. 生成投影

```powershell
# 默认生成权限元模型投影
python bo-projection-gen.py customers

# 指定投影类型
python bo-projection-gen.py customers --type api-contract
python bo-projection-gen.py customers --type authz_projection
python bo-projection-gen.py customers --type ui-model

# 多个 BO + 指定类型
python bo-projection-gen.py customers scenes --type authz_bo_meta_model
```

投影类型对照：

| `--type` 值 | 输出文件 | 说明 |
|-------------|----------|------|
| `authz_bo_meta_model`（默认） | `{boCode}.authz_bo_meta_model.schema_json.v2.json` | 支持权限引擎 — authz_bo_meta_model 表 schema_json 字段 |
| `api-contract` | `{boCode}.api-contract.json` | API 契约 — REST 端点 + 聚合策略 |
| `ui-model` | `{boCode}.ui-model.json` | UI 模型 — 列表列定义 |

输出：`metadata/projection-run-time/{boCode}/{boCode}.{suffix}`

### 4. 生成 DDL 建表 SQL

```powershell
# 全部 BO（默认）
python bo-ddl-gen.py

# 当前仅支持全部生成
```

输出：`generated-sql/` 目录下的 `V_{boCode}__create_tables.sql` 和 `_all_tables.sql`

### 5. 全面校验

```powershell
# 全量校验（JSON Schema + 结构 + 语义 + 跨BO引用）
python bo-consistency-check.py

# 快速模式 — 跳过 JSON Schema 形式化校验
python bo-consistency-check.py --no-json-schema
```

四阶段执行：
1. **Phase 0 — JSON Schema 形式化校验** — 用 jsonschema 库校验 governance profile + fragment 信封 + 6 个子 schema
2. **Phase 1 — 基础规范检查** — boCode 命名、metaType 合法性、重复 fragment、resourcePath 一致性等
3. **Phase 2 — 逐 BO 深度检查** — 结构完整性、entity/attribute 必填字段、类型/semanticRole/PK 合法性、CROSS_BO_REF 跨 BO 存在性、VALIDATION/VIEW/SECURITY/RULE/OPERATION 交叉引用、authzAction 合并报告、SECURITY HIDDEN vs VIEW exportable 冲突等
4. **Phase 3 — 跨 BO 命名一致性** — 同名不同码检测、displayFields localCode 统一性、同 BO 内跨 entity 同名属性类型一致性

### 6. 数据库检查

```powershell
# 全量检查（DDL漂移 + 数据画像 + 校验执行 + 引用完整性）
python bo-data-inspector.py all customers

# 单项检查
python bo-data-inspector.py drift customers          # DDL 漂移
python bo-data-inspector.py profile customers         # 数据画像
python bo-data-inspector.py validate customers        # 校验规则执行
python bo-data-inspector.py ref-integrity customers   # 跨BO引用完整性
```

> 数据库连接从 `application-dev.properties` 自动读取，也可直接修改脚本中的 `DEFAULT_CONFIG`。

---

## 四、典型工作流

### 场景 A：新增一个 BO 的属性字段

```
1. 修改 metadata/design-time/{boCode}/fragments/{boCode}-model.fragment.json
2. 界面：点击 🔄 重载图谱 → 图谱自动刷新
3. 界面：选中该 BO → 点击 📦 生成发布态 → 校验生成的 JSON
4. 界面：点击 🔍 校验检查 → 确认无错误
5. CLI（可选）: python bo-publish-gen.py {boCode}
```

### 场景 B：首次为 BO 生成完整治理产物

```
1. 确保 6 个 Fragment 文件齐全（MODEL/VALIDATION/SECURITY/RULE/VIEW/OPERATION）
2. CLI: python bo-consistency-check.py                      # 深度校验
3. CLI: python bo-graph-viz.py                              # 重构图谱
4. CLI: python bo-publish-gen.py {boCode}                   # 生成发布态
5. CLI: python bo-projection-gen.py {boCode} --type api-contract   # 生成 API 契约投影
6. CLI: python bo-projection-gen.py {boCode}                       # 生成权限元模型投影
7. CLI: python bo-ddl-gen.py                                # 生成 DDL
```

### 场景 C：修改 Fragment 后快速验证

```
1. 界面：点击 🔄 重载图谱
2. 界面：选中该 BO → 点击 📦 生成发布态 → 检查自动补齐的操作
3. 界面：点击 🔍 校验检查 → 确认通过
```

---

## 五、数据流

```
                    ┌────────────────────┐
   Fragment JSON ──→│ bo-graph-viz.py    │──→ graph-data.json
   (开发态)          └────────────────────┘          │
                                                     ↓
                    ┌────────────────────┐   bo-ontology-graph.html
   Fragment JSON ──→│ bo-publish-gen.py  │──→ schema-view.v2.json
   (6种类型)         └────────────────────┘     (发布态完整快照)
                                                     │
                                                     ↓
                    ┌────────────────────┐
                    │ bo-projection-gen  │──→ 多种投影产物:
                    │ --type {目标}       │    ├── authz_bo_meta_model (支持权限引擎)
                    └────────────────────┘    ├── api-contract (API 契约)
                                              └── ui-model (UI 模型)

   MODEL Fragment ──→ bo-ddl-gen.py ──→ Flyway 迁移 SQL
```

## 六、API 调用示例

### 发布态生成

```powershell
# curl
curl -X POST http://127.0.0.1:8765/api/publish -H "Content-Type: application/json" -d "{\"boCode\":\"customers\"}"

# PowerShell
Invoke-RestMethod -Uri http://127.0.0.1:8765/api/publish -Method Post -ContentType "application/json" -Body '{"boCode":"customers"}'
```

### 投影生成

```powershell
# 支持权限引擎投影（默认）
curl -X POST http://127.0.0.1:8765/api/projection -H "Content-Type: application/json" -d "{\"boCode\":\"customers\",\"projectionType\":\"authz_bo_meta_model\"}"

# API 契约投影
curl -X POST http://127.0.0.1:8765/api/projection -H "Content-Type: application/json" -d "{\"boCode\":\"customers\",\"projectionType\":\"api-contract\"}"

# 授权属性投影
curl -X POST http://127.0.0.1:8765/api/projection -H "Content-Type: application/json" -d "{\"boCode\":\"customers\",\"projectionType\":\"authz_projection\"}"

# 支持权限引擎投影（默认）
curl -X POST http://127.0.0.1:8765/api/projection -H "Content-Type: application/json" -d "{\"boCode\":\"customers\",\"projectionType\":\"authz_bo_meta_model\"}"

# UI 模型投影
curl -X POST http://127.0.0.1:8765/api/projection -H "Content-Type: application/json" -d "{\"boCode\":\"customers\",\"projectionType\":\"ui-model\"}"

# PowerShell
Invoke-RestMethod -Uri http://127.0.0.1:8765/api/projection -Method Post -ContentType "application/json" -Body '{"boCode":"customers","projectionType":"api-contract"}'
```

---

## 七、常见问题

**Q: 界面按钮点击后提示 "服务未启动"？**
A: 先运行 `.\bo-api.bat start`，等待 1-2 秒后再操作。

**Q: 图谱不显示数据？**
A: 先运行 `python bo-graph-viz.py` 生成 `graph-data.json`，或在界面点击 🔄 重载图谱。

**Q: 脚本报 `ModuleNotFoundError`？**
A: 确保使用项目虚拟环境：`..\..\..\.venv\Scripts\python.exe` 或先激活 venv。

**Q: tools/ 目录能否整体迁移？**
A: 可以。所有路径使用 `Path(__file__).resolve().parent.parent` 相对引用，迁移后只需保持 `tools/` 与 `metadata/`、`schemas/` 的相对位置不变。

---

## 附录：基于 BO 本体定义的数据库级服务

> 连接 `unify_engine` 库后，基于 BO 本体定义可提供以下数据库级服务：

### 一、Schema 层面

| 服务 | 说明 | 输入 |
|------|------|------|
| DDL 漂移检测 | 对比 MODEL Fragment 定义 vs 实际表结构，发现缺表、缺列、类型不匹配 | BO 元数据 + INFORMATION_SCHEMA |
| 索引合规检查 | 检查 `filterable=true` / `CROSS_BO_REF` 字段是否有对应索引 | MODEL Fragment |
| 审计列一致性 | 检查所有表是否含 `created_by` / `updated_by` / `created_time` / `updated_time` / `is_deleted` / `tenant_code` | 基础设施规范 |

### 二、数据质量层面

| 服务 | 说明 | 输入 |
|------|------|------|
| 校验规则执行 | 用 VALIDATION Fragment 的规则（`required` / `enum` / `max` / `pattern` / `unique`）扫描真实数据，输出违规行 | VALIDATION Fragment + 真实表 |
| 跨 BO 引用完整性 | 检查 `CROSS_BO_REF` 字段值是否在目标表中存在，发现悬空引用 | MODEL Fragment 的 `crossBoRef` |
| 一致性规则校验 | 执行 RULE Fragment 的 CONSISTENCY 规则（如"有子客户不可删父客户"） | RULE Fragment |
| 字段安全合规 | 检查 RESTRICTED / MASKED 字段在日志/导出中是否被不当暴露 | SECURITY Fragment |

### 三、数据探查层面

| 服务 | 说明 |
|------|------|
| 数据画像 | 每 BO 的行数、空值率、枚举分布、创建时间分布 |
| 跨 BO 关联图谱 | 以某个 customers 记录为起点，递归展示关联的 contacts → opportunities → scenes → products |
| 样例数据导出 | 按 BO 导出格式化 JSON（属性名用 `code`，含 `CROSS_BO_DISPLAY` 名称解析） |

### 四、权限仿真层面

| 服务 | 说明 |
|------|------|
| 行级安全模拟 | 给定 `userId`，基于 `rowLevelRuleEntries` 和 PSP 策略，模拟该用户可见的数据范围 |
| 字段安全模拟 | 对同一用户，标注哪些字段因 `fieldControl=RESTRICTED` 被隐藏/脱敏 |
| 权限项覆盖分析 | 查 `authz_bo_meta_model` 表，列出每个 BO 实际配置的 `operation → authzAction` 映射，与发布态对比 |


