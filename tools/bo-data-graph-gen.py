#!/usr/bin/env python3
"""
Data Knowledge Graph Generator — 从 demo-data 构建实例数据图谱
读取各 BO 的 sample.json，提取记录和跨记录引用关系，输出 vis.js 格式的 nodes + edges。

用法: 被 bo-api-server.py 内嵌调用，或独立运行:
  python bo-data-graph-gen.py --scenario-dir education
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

TOOLS_DIR = Path(__file__).resolve().parent
DEMO_DATA_DIR = TOOLS_DIR / "demo-data"
PROJECT_DIR = TOOLS_DIR.parent  # bo-arch-gov/
META_DIR = PROJECT_DIR / "metadata"


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def _load_records(demo_dir: Path, bo_code: str) -> list:
    """加载 demo-data/{boCode}.sample.json 的全部记录"""
    sample_file = demo_dir / f"{bo_code}.sample.json"
    data = _load_json(sample_file)
    if not data:
        return []
    if "records" in data:
        return data["records"]
    return [data]


def _load_link_metadata() -> list:
    """加载发布态 LINK 元数据，优先读 crm.ontology-snapshot.v1.json（含显式 + 自动派生 LINK）。
    回退到 design-time crm-link.fragment.json。返回 links 列表。"""
    # 优先：发布态快照（权威数据源，含 EXPLICIT + INFERRED LINK）
    snapshot_file = META_DIR / "release-time" / "_ontology" / "crm.ontology-snapshot.v1.json"
    data = _load_json(snapshot_file)
    if data:
        links = data.get("links", [])
        if links:
            return links

    # 回退：design-time fragment
    link_file = META_DIR / "design-time" / "_ontology" / "fragments" / "crm-link.fragment.json"
    data = _load_json(link_file)
    if data:
        return data.get("content", {}).get("links", [])
    return []


def _resolve_link_fields(link: dict) -> tuple:
    """从 LINK 提取 (src_bo, tgt_bo, src_field, tgt_field, name, code, inv, mat, link_src)。
    兼容 fragment 嵌套格式和快照扁平格式。"""
    code, name, inv, mat, link_src = (link.get(k, "") for k in ("code", "name", "inverseName", "materialization", "source"))
    source = link.get("source", {})
    target = link.get("target", {})
    if isinstance(source, dict) and source:
        return (source.get("boCode", ""), target.get("boCode", ""),
                source.get("fieldCode", ""), target.get("fieldCode", ""),
                name, code, inv, mat, str(link_src) if isinstance(link_src, str) else "EXPLICIT")
    return (link.get("sourceBoCode", ""), link.get("targetBoCode", ""),
            link.get("sourceFieldCode", ""), link.get("targetFieldCode", ""),
            name, code, inv, mat, str(link_src))


def _load_schema(bo_code: str) -> dict:
    """加载发布态 schema-view.v2.json"""
    spath = META_DIR / "release-time" / bo_code / f"{bo_code}.schema-view.v2.json"
    return _load_json(spath) or {}


def _derive_fks_from_schemas() -> dict:
    """从发布态 schema 自动派生 FK（子→父方向外键）。
    数据来源：(1) crossBoRef 声明 (2) semanticRole=PARENT_REF 自引用 (3) view.refObject 引用。
    覆盖 LINK 元数据未定义但 schema 已声明的 BO 间引用。"""
    derived = {}
    for bo_code in BO_CONFIG:
        schema = _load_schema(bo_code)
        if not schema:
            continue
        for entity in schema.get("entities", []):
            for attr in entity.get("attributes", []):
                fk_def = None

                # 来源 1：crossBoRef（最权威）
                ref = attr.get("crossBoRef")
                if ref:
                    ref_bo = ref.get("refBoCode", "")
                    ref_field = ref.get("refFieldCode", "id")
                    if ref_bo and ref_bo in BO_CONFIG:
                        fk_def = {
                            "field": attr["code"], "targetBo": ref_bo,
                            "label": attr.get("name", attr["code"]),
                            "refField": ref_field,
                            "_sourceLink": "SCHEMA_CROSSBO_REF", "_sourceOrigin": "schema",
                        }

                # 来源 2：semanticRole=PARENT_REF（自引用树形结构，如 orgs.parent_org_id）
                if not fk_def and attr.get("semanticRole") == "PARENT_REF":
                    fk_def = {
                        "field": attr["code"], "targetBo": bo_code,
                        "label": attr.get("name", attr["code"]),
                        "refField": "id",
                        "_sourceLink": "SCHEMA_PARENT_REF", "_sourceOrigin": "schema",
                    }

                # 来源 3：view.refObject（UI 层声明的引用关系）
                if not fk_def:
                    view = attr.get("view", {})
                    ref_obj = view.get("refObject", "")
                    ref_field_view = view.get("refField", "id")
                    if ref_obj and ref_obj in BO_CONFIG and ref_obj != bo_code:
                        fk_def = {
                            "field": attr["code"], "targetBo": ref_obj,
                            "label": attr.get("name", attr["code"]),
                            "refField": ref_field_view,
                            "_sourceLink": "SCHEMA_VIEW_REFOBJECT", "_sourceOrigin": "schema",
                        }

                if not fk_def:
                    continue

                # 自引用设置 skipNull
                if fk_def["targetBo"] == bo_code:
                    fk_def["skipNull"] = True
                # 逗号分隔的多值引用
                if "," in str(fk_def["field"]) or str(fk_def["field"]).endswith("_snapshot"):
                    fk_def["_split"] = ","
                # 非主键引用（如 department_code -> orgs.department_code）
                if fk_def.get("refField") and fk_def["refField"] != "id":
                    fk_def["refField"] = fk_def["refField"]
                else:
                    fk_def["refField"] = "id"

                derived.setdefault(bo_code, [])
                if not any(d["field"] == fk_def["field"] and d["targetBo"] == fk_def["targetBo"] for d in derived[bo_code]):
                    derived[bo_code].append(fk_def)

    return derived


def _derive_fks_from_links() -> dict:
    """从 LINK 元数据自动派生 BO_CONFIG.fks（子→父方向外键）。
    支持 design-time fragment 和 release-time snapshot 两种格式。"""
    links = _load_link_metadata()
    derived = {}

    for link in links:
        if link.get("materialization") != "FIELD_REF":
            continue
        src_bo, tgt_bo, src_field, tgt_field, name, code, inv, mat, link_src = _resolve_link_fields(link)
        if not src_bo or not tgt_bo or not tgt_field:
            continue
        if src_bo not in BO_CONFIG or tgt_bo not in BO_CONFIG:
            continue

        # 构造 fk：持有 fieldCode 的 BO 作为源
        fk_bo = tgt_bo
        fk_field = tgt_field
        fk_target = src_bo
        fk_label = inv or name
        skip_null = (src_bo == tgt_bo)

        fk_def = {
            "field": fk_field, "targetBo": fk_target, "label": fk_label,
            "_sourceLink": code, "_sourceOrigin": link_src,
        }
        if skip_null:
            fk_def["skipNull"] = True
        if "," in str(tgt_field) or str(tgt_field).endswith("_snapshot"):
            fk_def["_split"] = ","

        derived.setdefault(fk_bo, [])
        if not any(d["field"] == fk_field and d["targetBo"] == fk_target for d in derived[fk_bo]):
            derived[fk_bo].append(fk_def)

    return derived


def _derive_logical_links_from_links() -> list:
    """从 LINK 元数据提取逻辑关联（逗号分隔字段、语义映射不精确字段）。"""
    links = _load_link_metadata()
    derived = []
    seen = set()

    for link in links:
        if link.get("materialization") != "FIELD_REF":
            continue
        src_bo, tgt_bo, src_field, tgt_field, name, code, inv, mat, link_src = _resolve_link_fields(link)
        if not src_bo or not tgt_bo or not src_field:
            continue
        if src_bo not in BO_CONFIG or tgt_bo not in BO_CONFIG:
            continue

        # 识别需要逻辑关联的特征
        is_split = "," in str(tgt_field) or str(tgt_field).endswith("_snapshot")
        is_logical = code in ("TARGET_OWNS_CUSTOMER",)
        is_inferred_useful = (link_src == "INFERRED" and not is_split
                              and tgt_field not in ("id", "parent_customer_id", "fop_customer_id",
                                                    "business_customer_id", "customer_id",
                                                    "parent_opportunity_id", "parent_id",
                                                    "customers_id", "scene_id", "approval_record_id"))

        if not (is_split or is_logical or is_inferred_useful):
            continue

        dedup_key = (src_bo, src_field, tgt_bo, tgt_field)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        entry = {
            "fromBo": src_bo, "fromField": src_field,
            "toBo": tgt_bo, "toField": tgt_field,
            "label": name, "_sourceLink": code,
        }
        if is_split:
            entry["split"] = ","
        derived.append(entry)

    return derived


# ── 展示层配置：仅颜色和图标（纯 UI 属性，schema 中不存在）──
# label/idField/displayField 从 schema 自动派生（见 _build_bo_config()）
BO_DISPLAY = {
    "customers":          {"icon": "👤", "color": "#4f46e5"},
    "opportunities":      {"icon": "💼", "color": "#0d9488"},
    "sales-activities":   {"icon": "📅", "color": "#0ea5e9"},
    "contacts":           {"icon": "📇", "color": "#8b5cf6"},
    "scenes":             {"icon": "🎯", "color": "#f59e0b"},
    "competitors":        {"icon": "⚔️", "color": "#ef4444"},
    "exchange-rates":     {"icon": "💱", "color": "#14b8a6"},
    "sales-targets":      {"icon": "🎯", "color": "#d97706"},
    "users":              {"icon": "👷", "color": "#6366f1"},
    "products":           {"icon": "📦", "color": "#a855f7"},
    "customer-relations": {"icon": "🔗", "color": "#3b82f6"},
    "orgs":               {"icon": "🏢", "color": "#64748b"},
    "scene-archs":        {"icon": "🏗️", "color": "#7c3aed"},
    "renewal-quotes":     {"icon": "📋", "color": "#059669"},
}

# 默认展示属性（未在 BO_DISPLAY 中显式定义的 BO 使用）
_DEFAULT_DISPLAY = {"icon": "📊", "color": "#64748b"}


def _build_bo_config() -> dict:
    """从 schema 自动派生 BO_CONFIG（label/idField/displayField），合并展示层属性。
    BO 列表来源于 release-time 目录扫描，无需手动维护。"""
    import os
    config = {}
    release_dir = META_DIR / "release-time"
    if not release_dir.exists():
        return config

    for bo_dir in sorted(os.listdir(release_dir)):
        spath = release_dir / bo_dir / f"{bo_dir}.schema-view.v2.json"
        schema = _load_json(spath)
        if not schema:
            continue
        bo_code = schema.get("boCode", bo_dir)
        if bo_code != bo_dir:
            continue  # 目录名与 boCode 不一致，跳过

        api_cfg = schema.get("apiConfig", {})
        bo_cfg = schema.get("boConfig", {})
        display = BO_DISPLAY.get(bo_code, _DEFAULT_DISPLAY)

        config[bo_code] = {
            "label": schema.get("boName", bo_code),
            "icon": display["icon"],
            "color": display["color"],
            "idField": api_cfg.get("idField", "id"),
            "displayField": bo_cfg.get("nameField", "id"),
        }

    return config


BO_CONFIG = _build_bo_config()

# FK 派生策略：先从 schema crossBoRef 派生（覆盖面最广），再从 LINK 元数据补充（含语义标签）
# 两者在 generate() 中合并去重，无需手动 FK 定义

# BO 之间的逻辑关联（非外键，通过字段值匹配）
# 大部分逻辑关联已从 LINK 元数据自动派生（见 _derive_logical_links_from_links()），
# 此处仅保留元数据中无法表达的代码独有关联：
# - currency 是枚举值（非 ID 引用），无法用 crossBoRef 表达
# - temporal-events 是辅助数据流，不是 BO
LOGICAL_LINKS = [
    # opportunities.currency → exchange-rates（枚举值匹配，非 ID 引用）
    {"fromBo": "opportunities", "fromField": "currency", "toBo": "exchange-rates",
     "toField": "base_currency", "label": "币种汇率",
     "filterTo": {"status": "ACTIVE", "target_currency": "CNY"}},
    # renewal-quotes.opportunity_id → opportunities（demo-data 有此字段但 schema 未声明 crossBoRef）
    {"fromBo": "renewal-quotes", "fromField": "opportunity_id", "toBo": "opportunities",
     "toField": "id", "label": "关联商机"},
]

# temporal-events 关联（辅助数据流，非 BO，无法从元数据派生）
TEMPORAL_LINKS = {
    "stageEvents": {"targetBo": "opportunities", "label": "阶段事件"},
    "activityEvents": {"targetBo": "customers", "label": "活动事件"},
}


def _derive_xref_config_from_links() -> list:
    """从 LINK 元数据中的 ASSOCIATION_ENTITY 类型自动派生 XREF_CONFIG。
    匹配 demo-data 中的 {fromBo}-{toBo}-xref.sample.json 文件。"""
    links = _load_link_metadata()
    xref_list = []
    for link in links:
        if link.get("materialization") != "ASSOCIATION_ENTITY":
            continue
        src_bo, tgt_bo, src_field, tgt_field, name, code, inv, mat, link_src = _resolve_link_fields(link)
        if not src_bo or not tgt_bo:
            continue
        if src_bo not in BO_CONFIG or tgt_bo not in BO_CONFIG:
            continue
        # 尝试匹配 demo-data 文件名模式：{fromBo}-{toBo}-xref.sample.json
        # 也尝试 {toBo}-{fromBo}-xref.sample.json
        for file_pattern in [
            f"{src_bo}-{tgt_bo}-xref.sample.json",
            f"{tgt_bo}-{src_bo}-xref.sample.json",
        ]:
            xref_list.append({
                "file": file_pattern,
                "fromField": src_field,
                "toField": tgt_field,
                "fromBo": src_bo,
                "toBo": tgt_bo,
                "label": name or "关联",
            })
    return xref_list


XREF_CONFIG = _derive_xref_config_from_links()


def _derive_product_config_from_schema() -> dict:
    """从 scenes schema 的 scene-product 子实体自动派生 PRODUCT_CONFIG。
    scene-product 子实体的 crossBoRef 声明了 products_id -> products.id。"""
    scenes_schema = _load_schema("scenes")
    for entity in scenes_schema.get("entities", []):
        if entity.get("code") == "scene-product":
            for attr in entity.get("attributes", []):
                ref = attr.get("crossBoRef")
                if ref and ref.get("refBoCode") == "products":
                    return {
                        "label": "产品", "icon": "📦", "color": "#a855f7",
                        "idField": attr["code"],
                        "displayField": "product_model",
                    }
    # 回退默认值
    return {
        "label": "产品", "icon": "📦", "color": "#a855f7",
        "idField": "products_id", "displayField": "product_model",
    }


PRODUCT_CONFIG = _derive_product_config_from_schema()


def _derive_polymorphic_edges(all_records: dict, edge_set: set) -> list:
    """从 schema crossBoRef + owner_type 枚举自动派生多态引用边。
    
    当某 BO 的字段有 crossBoRef 指向 BO X，但同 BO 有 owner_type 枚举字段
    且枚举值包含其他 BO 名称时，按 owner_type 动态选择目标 BO。
    
    典型场景：sales-targets.owner_id 的 crossBoRef 指向 users，
    但 owner_type 枚举有 EMPLOYEE/CUSTOMER，需按 owner_type 分流。
    """
    edges = []
    
    # 扫描所有 BO 的 schema，找出多态引用模式
    for bo_code in BO_CONFIG:
        schema = _load_schema(bo_code)
        if not schema:
            continue
        
        # 收集该 BO 所有 crossBoRef 字段
        ref_fields = {}  # field_code -> ref_bo
        owner_type_field = None
        owner_type_enums = []
        
        for entity in schema.get("entities", []):
            if not entity.get("isPrimary"):
                continue
            for attr in entity.get("attributes", []):
                if attr.get("crossBoRef"):
                    ref_fields[attr["code"]] = attr["crossBoRef"]["refBoCode"]
                # 检测 owner_type 枚举字段
                enum_vals = attr.get("validation", {}).get("enum", [])
                if enum_vals and attr["code"] in ("owner_type", "target_type", "ref_type"):
                    owner_type_field = attr["code"]
                    if isinstance(enum_vals[0], dict):
                        owner_type_enums = [e["value"] for e in enum_vals]
                    else:
                        owner_type_enums = enum_vals
        
        if not ref_fields or not owner_type_field:
            continue
        
        # 枚举值到 BO 的映射（EMPLOYEE -> users, CUSTOMER -> customers 等）
        enum_to_bo = {}
        for ev in owner_type_enums:
            ev_lower = ev.lower()
            if "employee" in ev_lower or "staff" in ev_lower or "user" in ev_lower:
                enum_to_bo[ev] = "users"
            elif "customer" in ev_lower:
                enum_to_bo[ev] = "customers"
            elif "org" in ev_lower:
                enum_to_bo[ev] = "orgs"
        
        if len(enum_to_bo) < 2:
            continue  # 不是多态
        
        # 为每条记录按 owner_type 选择目标 BO
        bo_cfg = BO_CONFIG.get(bo_code, {})
        bo_color = bo_cfg.get("color", "#71717a")
        for rec_id, rec in all_records.get(bo_code, {}).items():
            owner_type = rec.get(owner_type_field, "")
            target_bo = enum_to_bo.get(owner_type)
            if not target_bo:
                continue
            
            # 找到引用字段（通常是 owner_id / target_id / ref_id）
            for ref_field, default_target_bo in ref_fields.items():
                ref_val = str(rec.get(ref_field, ""))
                if not ref_val or ref_val in ("None", "null", ""):
                    continue
                if ref_val in all_records.get(target_bo, {}):
                    edge_id = f"{bo_code}:{rec_id}~~poly:{target_bo}:{ref_val}"
                    if edge_id not in edge_set:
                        edge_set.add(edge_id)
                        edges.append({
                            "id": edge_id,
                            "from": f"{bo_code}:{rec_id}",
                            "to": f"{target_bo}:{ref_val}",
                            "label": "目标归属",
                            "arrows": "to",
                            "dashes": [6, 3],
                            "color": {"color": bo_color + "88", "highlight": bo_color},
                        })
    
    return edges


def generate(scenario_dir: str = "education") -> dict:
    """生成数据知识图谱"""
    demo_dir = DEMO_DATA_DIR / scenario_dir
    if not demo_dir.exists():
        return {"error": f"Scenario directory not found: {scenario_dir}"}

    nodes = []
    edges = []
    edge_set = set()  # 去重

    # ── 1a. 元数据驱动：从 schema crossBoRef + LINK 派生 fks，merge 到 BO_CONFIG ──
    # 优先级：schema crossBoRef（覆盖面广）→ LINK 元数据（含语义标签）
    _schema_fks = _derive_fks_from_schemas()
    _link_fks = _derive_fks_from_links()
    # 合并：schema FK 先入，LINK FK 补充（去重 by field+targetBo）
    for bo_code, fk_list in _schema_fks.items():
        if bo_code in BO_CONFIG:
            existing_fks = BO_CONFIG[bo_code].get("fks", [])
            existing_fields = {f["field"] for f in existing_fks}
            new_fks = [f for f in fk_list if f["field"] not in existing_fields]
            BO_CONFIG[bo_code]["fks"] = existing_fks + new_fks
        else:
            BO_CONFIG[bo_code] = BO_CONFIG.get(bo_code, {})
            BO_CONFIG[bo_code]["fks"] = fk_list
    for bo_code, fk_list in _link_fks.items():
        if bo_code in BO_CONFIG:
            existing_fks = BO_CONFIG[bo_code].get("fks", [])
            existing_fields = {f["field"] for f in existing_fks}
            new_fks = [f for f in fk_list if f["field"] not in existing_fields]
            BO_CONFIG[bo_code]["fks"] = existing_fks + new_fks
        else:
            BO_CONFIG[bo_code] = BO_CONFIG.get(bo_code, {})
            BO_CONFIG[bo_code]["fks"] = fk_list

    _derived_ll = _derive_logical_links_from_links()
    existing_ll_codes = {l.get("_sourceLink") for l in LOGICAL_LINKS if "_sourceLink" in l}
    for ll in _derived_ll:
        if ll.get("_sourceLink") not in existing_ll_codes:
            LOGICAL_LINKS.append(ll)

    # ── 1b. 为每个 BO 的每条记录创建节点 ──
    all_records = {}  # boCode -> {id -> record}
    bo_record_counts = {}

    for bo_code, cfg in BO_CONFIG.items():
        records = _load_records(demo_dir, bo_code)
        all_records[bo_code] = {}
        bo_record_counts[bo_code] = len(records)

        for rec in records:
            rec_id = str(rec.get(cfg["idField"], ""))
            if not rec_id:
                continue
            all_records[bo_code][rec_id] = rec

            display_name = rec.get(cfg["displayField"], rec_id)
            # 特殊显示格式：从 schema 字段组合生成（非 labelExpr 硬编码）
            if bo_code == "exchange-rates":
                display_name = f"{rec.get('base_currency','?')}→{rec.get('target_currency','?')} {rec.get('rate','?')}"
            elif bo_code == "sales-targets":
                display_name = f"{rec.get('owner_name','?')} ¥{rec.get('goal_value',0):,.0f}"
            # 截断过长的名称
            if len(str(display_name)) > 20:
                display_name = str(display_name)[:18] + ".."

            # 附加关键信息到 title
            title_parts = [f"{cfg['icon']} {cfg['label']}: {rec.get(cfg['displayField'], rec_id)}"]
            if bo_code == "customers":
                title_parts.append(f"行业: {rec.get('market_segment', '—')}")
                title_parts.append(f"类别: {rec.get('customer_category', '—')}")
            elif bo_code == "opportunities":
                title_parts.append(f"阶段: {rec.get('project_stage', '—')}")
                title_parts.append(f"金额: ¥{rec.get('expected_order_amount', 0):,}")
                title_parts.append(f"状态: {rec.get('status', '—')}")
            elif bo_code == "sales-activities":
                title_parts.append(f"时间: {str(rec.get('visit_time', '—'))[:10]}")
                title_parts.append(f"方式: {rec.get('visit_method', '—')}")
            elif bo_code == "exchange-rates":
                title_parts.append(f"{rec.get('base_currency', '?')}→{rec.get('target_currency', '?')} = {rec.get('rate', '?')}")
                title_parts.append(f"状态: {rec.get('status', '—')}")
            elif bo_code == "sales-targets":
                title_parts.append(f"目标: ¥{rec.get('goal_value', 0):,}")
                title_parts.append(f"周期: {rec.get('apply_rule', '—')}")

            nodes.append({
                "id": f"{bo_code}:{rec_id}",
                "label": f"{cfg['icon']} {display_name}",
                "shape": "dot",
                "size": 18,
                "font": {"size": 11, "color": "#e4e4e7", "face": "Inter, sans-serif"},
                "color": {
                    "background": cfg["color"] + "33",
                    "border": cfg["color"],
                    "highlight": {"background": cfg["color"] + "55", "border": cfg["color"]},
                    "hover": {"background": cfg["color"] + "44", "border": cfg["color"]},
                },
                "borderWidth": 2,
                "boCode": bo_code,
                "recordId": rec_id,
                "recordData": rec,
                "title": "\n".join(title_parts),
            })

    # ── 2. 外键引用边 ──
    for bo_code, cfg in BO_CONFIG.items():
        fks = cfg.get("fks", [])
        for fk in fks:
            target_bo = fk["targetBo"]
            fk_field = fk["field"]
            edge_label = fk["label"]
            skip_null = fk.get("skipNull", False)
            ref_field = fk.get("refField", "id")  # 默认按 id 匹配，支持非主键引用
            split_char = fk.get("_split", ",")

            # 构建目标 BO 的 ref_field -> record_id 索引（用于非主键引用）
            target_cfg = BO_CONFIG.get(target_bo, {})
            target_id_field = target_cfg.get("idField", "id")
            if ref_field == "id":
                # 主键引用：直接用 all_records 的 key
                target_lookup = None  # 不需要额外索引
            else:
                # 非主键引用：构建 ref_field 值 -> record_id 的映射
                target_lookup = {}
                for tid, trec in all_records.get(target_bo, {}).items():
                    rv = str(trec.get(ref_field, ""))
                    if rv:
                        target_lookup.setdefault(rv, []).append(tid)

            for rec_id, rec in all_records[bo_code].items():
                fk_value = rec.get(fk_field)
                if not fk_value:
                    continue
                fk_value = str(fk_value)
                if skip_null and fk_value in ("None", "null", ""):
                    continue

                # 处理逗号分隔的引用
                if split_char and split_char in fk_value:
                    vals = [v.strip() for v in fk_value.split(split_char) if v.strip()]
                else:
                    vals = [fk_value]

                for v in vals:
                    if target_lookup is not None:
                        # 非主键引用匹配
                        matched_ids = target_lookup.get(v, [])
                        for tid in matched_ids:
                            edge_id = f"{bo_code}:{rec_id}→{target_bo}:{tid}"
                            if edge_id not in edge_set:
                                edge_set.add(edge_id)
                                edges.append({
                                    "id": edge_id,
                                    "from": f"{bo_code}:{rec_id}",
                                    "to": f"{target_bo}:{tid}",
                                    "label": edge_label,
                                    "arrows": "to",
                                    "color": {"color": cfg["color"] + "88", "highlight": cfg["color"]},
                                })
                    else:
                        # 主键引用匹配
                        if v in all_records.get(target_bo, {}):
                            edge_id = f"{bo_code}:{rec_id}→{target_bo}:{v}"
                            if edge_id not in edge_set:
                                edge_set.add(edge_id)
                                edges.append({
                                    "id": edge_id,
                                    "from": f"{bo_code}:{rec_id}",
                                    "to": f"{target_bo}:{v}",
                                    "label": edge_label,
                                    "arrows": "to",
                                    "color": {"color": cfg["color"] + "88", "highlight": cfg["color"]},
                                })

    # ── 3. 逻辑关联边 ──
    for link in LOGICAL_LINKS:
        from_bo = link["fromBo"]
        from_field = link["fromField"]
        to_bo = link["toBo"]
        to_field = link["toField"]
        edge_label = link["label"]
        split_char = link.get("split")
        filter_to = link.get("filterTo", {})

        for rec_id, rec in all_records.get(from_bo, {}).items():
            from_val = rec.get(from_field)
            if not from_val:
                continue

            if split_char and isinstance(from_val, str) and split_char in from_val:
                vals = [v.strip() for v in from_val.split(split_char)]
            else:
                vals = [str(from_val)]

            for v in vals:
                for target_id, target_rec in all_records.get(to_bo, {}).items():
                    # 应用 filter
                    if filter_to:
                        skip = False
                        for k, val in filter_to.items():
                            if target_rec.get(k) != val:
                                skip = True
                                break
                        if skip:
                            continue
                    if str(target_rec.get(to_field, "")) == v:
                        edge_id = f"{from_bo}:{rec_id}~~{to_bo}:{target_id}"
                        if edge_id not in edge_set:
                            edge_set.add(edge_id)
                            edges.append({
                                "id": edge_id,
                                "from": f"{from_bo}:{rec_id}",
                                "to": f"{to_bo}:{target_id}",
                                "label": edge_label,
                                "arrows": "to",
                                "dashes": [6, 3],
                                "color": {"color": "#71717a88", "highlight": "#a1a1aa"},
                            })

    # ── 4. temporal-events 边 ──
    temporal_file = demo_dir / "temporal-events.sample.json"
    temporal_data = _load_json(temporal_file) or {}
    for event_type, cfg in TEMPORAL_LINKS.items():
        events = temporal_data.get(event_type, [])
        target_bo = cfg["targetBo"]
        for i, evt in enumerate(events):
            obj_id = str(evt.get("objectId", ""))
            if obj_id and obj_id in all_records.get(target_bo, {}):
                edge_id = f"temporal:{event_type}:{i}→{target_bo}:{obj_id}"
                if edge_id not in edge_set:
                    edge_set.add(edge_id)
                    edges.append({
                        "id": edge_id,
                        "from": f"{target_bo}:{obj_id}",
                        "to": f"{target_bo}:{obj_id}",
                        "label": cfg["label"],
                        "arrows": "",
                        "color": {"color": "#14b8a688"},
                        "dashes": [2, 2],
                    })

    # ── 5. FK 反向边（P0-3: 父→子方向，使 LINK 定义的双向关系在图谱中可见）──
    for bo_code, cfg in BO_CONFIG.items():
        fks = cfg.get("fks", [])
        for fk in fks:
            target_bo = fk["targetBo"]
            fk_field = fk["field"]
            edge_label = fk.get("reverseLabel", fk["label"] + "(反向)")
            skip_null = fk.get("skipNull", False)
            ref_field = fk.get("refField", "id")
            target_cfg = BO_CONFIG.get(target_bo, {})

            # 构建非主键引用的反向索引
            if ref_field != "id":
                target_lookup = {}
                for tid, trec in all_records.get(target_bo, {}).items():
                    rv = str(trec.get(ref_field, ""))
                    if rv:
                        target_lookup.setdefault(rv, []).append(tid)
            else:
                target_lookup = None

            for rec_id, rec in all_records[bo_code].items():
                fk_value = rec.get(fk_field)
                if not fk_value:
                    continue
                fk_value = str(fk_value)
                if skip_null and fk_value in ("None", "null", ""):
                    continue

                if target_lookup is not None:
                    matched_ids = target_lookup.get(fk_value, [])
                    for tid in matched_ids:
                        rev_edge_id = f"rev:{target_bo}:{tid}→{bo_code}:{rec_id}"
                        if rev_edge_id not in edge_set:
                            edge_set.add(rev_edge_id)
                            edges.append({
                                "id": rev_edge_id,
                                "from": f"{target_bo}:{tid}",
                                "to": f"{bo_code}:{rec_id}",
                                "label": edge_label,
                                "arrows": "to",
                                "dashes": [4, 4],
                                "color": {"color": target_cfg.get("color", cfg["color"]) + "66", "highlight": target_cfg.get("color", cfg["color"])},
                            })
                else:
                    if fk_value in all_records.get(target_bo, {}):
                        rev_edge_id = f"rev:{target_bo}:{fk_value}→{bo_code}:{rec_id}"
                        if rev_edge_id not in edge_set:
                            edge_set.add(rev_edge_id)
                            edges.append({
                                "id": rev_edge_id,
                                "from": f"{target_bo}:{fk_value}",
                                "to": f"{bo_code}:{rec_id}",
                                "label": edge_label,
                                "arrows": "to",
                                "dashes": [4, 4],
                                "color": {"color": target_cfg.get("color", cfg["color"]) + "66", "highlight": target_cfg.get("color", cfg["color"])},
                            })

    # ── 6. 交叉引用边（P0-1: customer-competitor-xref 等 ASSOCIATION_ENTITY 数据）──
    for xref in XREF_CONFIG:
        xref_file = demo_dir / xref["file"]
        xref_data = _load_json(xref_file)
        if not xref_data:
            continue
        xref_records = xref_data.get("records", xref_data if isinstance(xref_data, list) else [])
        from_bo = xref["fromBo"]
        to_bo = xref["toBo"]
        for xr in xref_records:
            from_id = str(xr.get(xref["fromField"], ""))
            to_id = str(xr.get(xref["toField"], ""))
            if not from_id or not to_id:
                continue
            if from_id in all_records.get(from_bo, {}) and to_id in all_records.get(to_bo, {}):
                edge_id = f"xref:{from_bo}:{from_id}→{to_bo}:{to_id}"
                if edge_id not in edge_set:
                    edge_set.add(edge_id)
                    from_cfg = BO_CONFIG.get(from_bo, {})
                    edges.append({
                        "id": edge_id,
                        "from": f"{from_bo}:{from_id}",
                        "to": f"{to_bo}:{to_id}",
                        "label": xref["label"],
                        "arrows": "to",
                        "dashes": [4, 4],
                        "color": {"color": from_cfg.get("color", "#ef4444") + "88", "highlight": from_cfg.get("color", "#ef4444")},
                    })

    # ── 7. 场景嵌入产品节点（scene_products → products BO 节点 + 边）──
    # 如果 products BO 已有该产品（通过 7b 步关联），则不重复创建
    # 仅当 products BO 无对应 demo-data 时，从嵌入数组补充创建
    product_nodes = {}  # products_id → node（仅补充未在 products BO 中的）
    pc = PRODUCT_CONFIG
    products_bo_cfg = BO_CONFIG.get("products", {})
    products_color = products_bo_cfg.get("color", pc["color"])
    products_icon = products_bo_cfg.get("icon", pc["icon"])
    products_label = products_bo_cfg.get("label", pc["label"])
    for rec_id, rec in all_records.get("scenes", {}).items():
        scene_products = rec.get("scene_products", [])
        if not isinstance(scene_products, list):
            continue
        for sp in scene_products:
            pid = str(sp.get(pc["idField"], ""))
            if not pid:
                continue
            # 如果 products BO 已有该产品，跳过（7b 步会处理关联）
            if pid in all_records.get("products", {}):
                continue
            # products BO 无此产品，从嵌入数组补充创建
            if pid not in product_nodes:
                pname = sp.get(pc["displayField"], pid)
                product_nodes[pid] = {
                    "id": f"products:{pid}",
                    "label": f"{products_icon} {pname[:18] + '..' if len(str(pname)) > 20 else pname}",
                    "shape": "dot",
                    "size": 14,
                    "font": {"size": 10, "color": "#e4e4e7", "face": "Inter, sans-serif"},
                    "color": {
                        "background": products_color + "33",
                        "border": products_color,
                        "highlight": {"background": products_color + "55", "border": products_color},
                    },
                    "borderWidth": 1.5,
                    "boCode": "products",
                    "recordId": pid,
                    "title": f"{products_icon} {products_label}: {pname}\n型号: {sp.get('product_model', '—')}\n品类: {sp.get('product_category', '—')}",
                }
            # 场景→产品边
            edge_id = f"scenes:{rec_id}→products:{pid}"
            if edge_id not in edge_set:
                edge_set.add(edge_id)
                edges.append({
                    "id": edge_id,
                    "from": f"scenes:{rec_id}",
                    "to": f"products:{pid}",
                    "label": "配置产品",
                    "arrows": "to",
                    "dashes": [4, 4],
                    "color": {"color": products_color + "88", "highlight": products_color},
                })
    nodes.extend(product_nodes.values())
    # 补充创建的产品计入 products BO 计数
    if product_nodes:
        existing_count = bo_record_counts.get("products", 0)
        bo_record_counts["products"] = existing_count + len(product_nodes)

    # ── 7b. 独立 products 节点 ↔ scenes 关联（scene_products[].products_id → products.id）──
    for rec_id, rec in all_records.get("scenes", {}).items():
        scene_products = rec.get("scene_products", [])
        if not isinstance(scene_products, list):
            continue
        for sp in scene_products:
            pid = str(sp.get("products_id", ""))
            if not pid:
                continue
            if pid in all_records.get("products", {}):
                edge_id = f"scenes:{rec_id}~~products:{pid}"
                if edge_id not in edge_set:
                    edge_set.add(edge_id)
                    edges.append({
                        "id": edge_id,
                        "from": f"scenes:{rec_id}",
                        "to": f"products:{pid}",
                        "label": "配置产品",
                        "arrows": "to",
                        "dashes": [4, 4],
                        "color": {"color": "#a855f788", "highlight": "#a855f7"},
                    })

    # ── 8. 场景↔商机间接关联（P1: 通过共享 customer_id 桥接）──
    for s_id, scene in all_records.get("scenes", {}).items():
        s_cust = str(scene.get("customers_id", ""))
        if not s_cust:
            continue
        for o_id, opp in all_records.get("opportunities", {}).items():
            o_cust = str(opp.get("business_customer_id", ""))
            if o_cust == s_cust:
                edge_id = f"scenes:{s_id}~~opportunities:{o_id}"
                if edge_id not in edge_set:
                    edge_set.add(edge_id)
                    edges.append({
                        "id": edge_id,
                        "from": f"scenes:{s_id}",
                        "to": f"opportunities:{o_id}",
                        "label": "场景→商机",
                        "arrows": "to",
                        "dashes": [4, 4],
                        "color": {"color": "#f59e0b88", "highlight": "#f59e0b"},
                    })

    # ── 9. 多态引用边（从 schema crossBoRef + owner_type enum 自动派生）──
    # 当 schema 中某字段的 crossBoRef 指向 BO X，但同 BO 有 owner_type 枚举字段
    # 且枚举值包含其他 BO 名称时，按 owner_type 动态选择目标 BO
    _polymorphic_edges = _derive_polymorphic_edges(all_records, edge_set)
    edges.extend(_polymorphic_edges)

    return {
        "nodes": nodes,
        "edges": edges,
        "boRecordCounts": bo_record_counts,
        "scenarioDir": scenario_dir,
        "summary": {
            "totalNodes": len(nodes),
            "totalEdges": len(edges),
            "boCounts": bo_record_counts,
        },
    }


if __name__ == "__main__":
    scenario_dir = "education"
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--scenario-dir" and i + 1 < len(args):
            scenario_dir = args[i + 1]

    result = generate(scenario_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
