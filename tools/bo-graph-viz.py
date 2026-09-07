#!/usr/bin/env python3
"""
BO Ontology Graph — Data Parser
解析 design-time BO Fragment JSON，构建跨 BO 关系图谱数据。
输出 graph-data.json 供 bo-ontology-graph.html 消费。
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from jsonschema import validate, ValidationError
from referencing import Registry, Resource

sys.stdout.reconfigure(encoding='utf-8')

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
METADATA_DIR = PROJECT_DIR / "metadata"
SCHEMAS_DIR = PROJECT_DIR / "schemas"
OUTPUT_FILE = TOOLS_DIR / "graph-data.json"

# ── semanticRole 颜色映射 ──────────────────────────────────────────
SEMANTIC_ROLE_COLORS = {
    "TECHNICAL_ID":     "#94a3b8",  # slate-400
    "BUSINESS_KEY":     "#60a5fa",  # blue-400
    "NAME":             "#34d399",  # emerald-400
    "NORMAL":           "#d1d5db",  # gray-300
    "CROSS_BO_REF":     "#f59e0b",  # amber-500
    "CROSS_BO_DISPLAY": "#fbbf24",  # amber-400
    "PARENT_REF":       "#c084fc",  # purple-400
    "STATUS":           "#fb923c",  # orange-400
}

FRAGMENT_COLORS = {
    "MODEL":       "#3b82f6",  # blue-500
    "VALIDATION":  "#ef4444",  # red-500
    "SECURITY":    "#f59e0b",  # amber-500
    "RULE":        "#8b5cf6",  # violet-500
    "VIEW":        "#10b981",  # emerald-500
    "OPERATION":   "#06b6d4",  # cyan-500
    "LINK":        "#ec4899",  # pink-500
    "DERIVATION":  "#f97316",  # orange-500
    "TEMPORAL":    "#14b8a6",  # teal-500
    "ACTION_CHAIN":"#7c3aed",  # violet-600
}

LINK_SOURCE_COLORS = {
    "EXPLICIT":      "#10b981",  # green-500
    "INFERRED":      "#94a3b8",  # slate-400
    "DISPLAY_DEPENDENCY": "#fbbf24",  # amber-400
    "CONSISTENCY_RULE":   "#ef4444",  # red-500
}

def load_json(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [WARN] skip {path.name}: {e}", file=sys.stderr)
        return None

# ── Schema 校验 ──────────────────────────────────────────────────
_registry = None
_envelope_schema = None
_sub_schemas = {}  # metaType -> schema dict

def _load_schemas():
    """加载所有 schema 并构建本地 registry，解决 $id / $ref。"""
    global _registry, _envelope_schema

    # 收集所有 schema 文件及其 $id → 本地路径映射
    schema_files = {}
    _collect_schema_files(SCHEMAS_DIR, schema_files)

    # 按 $id 构建 registry
    resources = []
    for uri, path in schema_files.items():
        schema = load_json(path)
        if schema:
            resources.append((uri, Resource.from_contents(schema)))

    _registry = Registry().with_resources(resources)

    # 加载 envelope schema
    envelope_path = SCHEMAS_DIR / "design-time" / "bo-meta-fragment.schema.json"
    _envelope_schema = load_json(envelope_path)
    if not _envelope_schema:
        print("[ERR] Envelope schema load failed -> skip validation", file=sys.stderr)
        return False

    # 加载各 fragment 子 schema（用于 content 单独校验）
    for mt in ["MODEL", "VALIDATION", "SECURITY", "RULE", "VIEW", "OPERATION"]:
        frag_path = SCHEMAS_DIR / "design-time" / "fragments" / f"{mt.lower()}-fragment.schema.json"
        schema = load_json(frag_path)
        if schema:
            _sub_schemas[mt] = schema

    print(f"   Schema 注册完成：{len(resources)} 个 schema")
    return True

def _collect_schema_files(directory: Path, result: dict):
    """递归收集 schema 文件，建立 $id → 本地路径映射。"""
    for item in sorted(directory.iterdir()):
        if item.is_dir():
            _collect_schema_files(item, result)
        elif item.suffix == ".json":
            data = load_json(item)
            if data and "$id" in data:
                result[data["$id"]] = item
                # 也注册本地相对路径别名（处理 envelope 中 `$ref: "fragments/xxx"` 的情况）
                rel = str(item.relative_to(SCHEMAS_DIR)).replace("\\", "/")
                result[rel] = item

def validate_fragment(fragment: dict, file_path: Path) -> list[str]:
    """校验单个 fragment 文件，返回错误信息列表。"""
    errors = []
    if not _envelope_schema or not _registry:
        return errors

    meta_type = fragment.get("metaType", "")
    sub_schema = _sub_schemas.get(meta_type)

    # 使用本地 registry 校验信封
    validator_cls = jsonschema_validator_for(_envelope_schema)
    validator = validator_cls(_envelope_schema, registry=_registry)
    for e in validator.iter_errors(fragment):
        errors.append(f"[信封] {e.message}")

    # 校验 content 子 schema
    if sub_schema and "content" in fragment:
        validator_cls2 = jsonschema_validator_for(sub_schema)
        validator2 = validator_cls2(sub_schema, registry=_registry)
        for e in validator2.iter_errors(fragment["content"]):
            errors.append(f"[{meta_type}] {e.message}")

    return errors

def jsonschema_validator_for(schema):
    """根据 schema 的 $schema 声明选择合适的 validator。"""
    from jsonschema import Draft202012Validator, Draft7Validator, Draft4Validator
    draft = schema.get("$schema", "")
    if "2020-12" in draft:
        return Draft202012Validator
    elif "draft-07" in draft or "draft7" in draft:
        return Draft7Validator
    return Draft202012Validator

def parse_all() -> dict:
    """遍历 examples 下所有 BO 目录，聚合所有 fragment 数据。"""
    bos = {}  # boCode -> BO node

    for bo_dir in sorted((METADATA_DIR / "design-time").iterdir()):
        if not bo_dir.is_dir():
            continue
        # 跳过元容器目录（如 _ontology），它们不是业务对象
        if bo_dir.name.startswith("_"):
            continue
        fragments_dir = bo_dir / "fragments"
        if not fragments_dir.is_dir():
            continue

        bo_code = None
        fragments = {}

        for frag_file in sorted(fragments_dir.glob("*.json")):
            data = load_json(frag_file)
            if not data:
                continue
            # Schema 校验
            errs = validate_fragment(data, frag_file)
            if errs:
                print(f"  [ERR] {bo_dir.name}/{frag_file.name}:")
                for err in errs:
                    print(f"     {err}")
            meta_type = data.get("metaType", "UNKNOWN")
            bo_code = bo_code or data.get("boCode", bo_dir.name)
            fragments[meta_type] = data

        if not bo_code:
            continue

        # ── 构建 BO 节点 ──────────────────────────────────────
        model = fragments.get("MODEL", {})
        content = model.get("content", {})
        bo_node = {
            "boCode": bo_code,
            "boName": content.get("boName", bo_code),
            "description": content.get("description", ""),
            "objectType": content.get("boConfig", {}).get("objectType", "SINGLE"),
            "fragments": {mt: _summarize_fragment(mt, f) for mt, f in fragments.items()},
            "apiConfig": content.get("apiConfig", {}),
            "boConfig": content.get("boConfig", {}),
            "entities": [],
            "crossBoRefs": [],       # 本 BO 对其他 BO 的引用
            "incomingRefs": [],      # 其他 BO 对本 BO 的引用（后填）
            "operations": [],
            "rules": [],
        }

        # ── 解析 entities ──────────────────────────────────────
        for ent in content.get("entities", []):
            attr_nodes = []
            for attr in ent.get("attributes", []):
                attr_node = {
                    "code": attr.get("code"),
                    "name": attr.get("name", attr.get("code")),
                    "type": attr.get("type", "STRING"),
                    "isPk": attr.get("isPk", False),
                    "semanticRole": attr.get("semanticRole", "NORMAL"),
                    "fieldName": attr.get("fieldName", attr.get("code")),
                    "columnName": attr.get("columnName", attr.get("code")),
                    "filterable": attr.get("filterable", False),
                    "defaultValue": attr.get("defaultValue"),
                    "i18nKey": attr.get("i18nKey"),
                    "redundant": attr.get("redundant", False),
                }
                # 跨 BO 引用
                cr = attr.get("crossBoRef")
                if cr:
                    attr_node["crossBoRef"] = {
                        "refBoCode": cr.get("refBoCode"),
                        "refFieldCode": cr.get("refFieldCode"),
                        "relationType": cr.get("relationType", "MANY_TO_ONE"),
                        "referenceNature": cr.get("referenceNature", "MASTER_DATA"),
                        "displayFields": cr.get("displayFields", []),
                    }
                    bo_node["crossBoRefs"].append({
                        "fromEntityCode": ent.get("code"),
                        "fromFieldCode": attr.get("code"),
                        "fromFieldName": attr.get("name", attr.get("code")),
                        "refBoCode": cr.get("refBoCode"),
                        "refFieldCode": cr.get("refFieldCode"),
                        "relationType": cr.get("relationType", "MANY_TO_ONE"),
                        "referenceNature": cr.get("referenceNature", "MASTER_DATA"),
                    })
                    # CROSS_BO_DISPLAY 边：displayFields 声明了展示依赖
                    for df in cr.get("displayFields", []):
                        bo_node["crossBoRefs"].append({
                            "fromEntityCode": ent.get("code"),
                            "fromFieldCode": df.get("localCode"),
                            "fromFieldName": attr.get("name", attr.get("code")) + "→" + df.get("localCode", ""),
                            "refBoCode": cr.get("refBoCode"),
                            "refFieldCode": df.get("refFieldCode"),
                            "relationType": "DISPLAY_DEPENDENCY",
                            "referenceNature": cr.get("referenceNature", "MASTER_DATA"),
                        })
                attr_nodes.append(attr_node)

            bo_node["entities"].append({
                "code": ent.get("code"),
                "name": ent.get("name", ent.get("code")),
                "isPrimary": ent.get("isPrimary", False),
                "aggregateRole": ent.get("aggregateRole", "ROOT"),
                "entityNature": ent.get("entityNature", "BUSINESS"),
                "tableName": ent.get("tableName", ""),
                "parentEntityCode": ent.get("parentEntityCode"),
                "parentRefField": ent.get("parentRefField"),
                "routeSegment": ent.get("routeSegment"),
                "cascadeDelete": ent.get("cascadeDelete"),
                "entityApiPolicy": ent.get("entityApiPolicy"),
                "attributes": attr_nodes,
            })

        # ── 解析 operations ──────────────────────────────────────
        op_frag = fragments.get("OPERATION", {})
        for op in op_frag.get("content", {}).get("operations", []):
            bo_node["operations"].append({
                "code": op.get("code"),
                "name": op.get("name", op.get("code")),
                "scope": op.get("scope"),
                "operationKind": op.get("operationKind"),
                "authzAction": op.get("authzAction"),
                "triggerEvent": op.get("triggerEvent", "API_CALL"),
                "entityCode": op.get("entityCode"),
                "description": op.get("description", ""),
            })

        # ── 解析 field security ──────────────────────────────────
        sec_frag = fragments.get("SECURITY", {})
        bo_node["fieldSecurity"] = []
        for fs in sec_frag.get("content", {}).get("fieldSecurity", []):
            bo_node["fieldSecurity"].append({
                "entityCode": fs.get("entityCode"),
                "fieldCode": fs.get("fieldCode"),
                "fieldControl": fs.get("fieldControl") or fs.get("controlPolicy"),
                "controlPolicy": fs.get("controlPolicy"),
                "privacyClass": fs.get("privacyClass") or fs.get("privacyLevel"),
                "privacyLevel": fs.get("privacyLevel"),
                "reason": fs.get("reason", ""),
            })
        bo_node["rowSecurity"] = sec_frag.get("content", {}).get("rowSecurity", {})
        bo_node["authzProjection"] = sec_frag.get("content", {}).get("authzProjection", {})

        # ── 解析 view ──────────────────────────────────────────
        view_frag = fragments.get("VIEW", {})
        bo_node["fieldViews"] = []
        for fv in view_frag.get("content", {}).get("fieldViews", []):
            bo_node["fieldViews"].append({
                "entityCode": fv.get("entityCode"),
                "fieldCode": fv.get("fieldCode"),
                "displayName": fv.get("displayName"),
                "formType": fv.get("formType"),
                "showInList": fv.get("showInList", True),
                "showInDetail": fv.get("showInDetail", True),
                "editableInForm": fv.get("editableInForm", True),
                "queryable": fv.get("queryable", False),
                "sortable": fv.get("sortable", False),
                "exportable": fv.get("exportable", True),
                "hidden": fv.get("hidden", False),
                "order": fv.get("order"),
            })
        bo_node["listViewConfig"] = view_frag.get("content", {}).get("listViewConfig", {})

        # ── 解析 validations ──────────────────────────────────────
        val_frag = fragments.get("VALIDATION", {})
        bo_node["validations"] = []
        for v in val_frag.get("content", {}).get("rules", []):
            bo_node["validations"].append({
                "entityCode": v.get("entityCode"),
                "fieldCode": v.get("fieldCode"),
                "required": v.get("required", False),
                "min": v.get("min"),
                "max": v.get("max"),
                "pattern": v.get("pattern"),
                "enum": v.get("enum"),
                "unique": v.get("unique", False),
                "message": v.get("message", ""),
            })

        # ── 解析 rules ──────────────────────────────────────────
        rule_frag = fragments.get("RULE", {})
        for r in rule_frag.get("content", {}).get("rules", []):
            rule_node = {
                "code": r.get("code"),
                "name": r.get("name", r.get("code")),
                "ruleType": r.get("ruleType"),
                "scope": r.get("scope"),
                "severity": r.get("severity", "ERROR"),
                "trigger": r.get("trigger") or r.get("triggerTiming"),
                "triggerTiming": r.get("triggerTiming"),
                "description": r.get("description", ""),
                "entityCode": r.get("entityCode"),
                "fieldCode": r.get("fieldCode"),
            }
            cr = r.get("crossBoRef")
            if cr:
                rule_node["crossBoRef"] = {
                    "refBoCode": cr.get("refBoCode"),
                    "refFieldCode": cr.get("refFieldCode"),
                    "localEntityCode": cr.get("localEntityCode"),
                    "localFieldCode": cr.get("localFieldCode"),
                }
                bo_node["crossBoRefs"].append({
                    "fromEntityCode": cr.get("localEntityCode"),
                    "fromFieldCode": cr.get("localFieldCode"),
                    "fromFieldName": r.get("name", cr.get("localFieldCode")),
                    "refBoCode": cr.get("refBoCode"),
                    "refFieldCode": cr.get("refFieldCode"),
                    "relationType": "CONSISTENCY_RULE",
                    "ruleCode": r.get("code"),
                })
            bo_node["rules"].append(rule_node)

        bos[bo_code] = bo_node

    # ── 反向填充 incomingRefs ──────────────────────────────────
    for bo_code, bo in bos.items():
        for ref in bo.get("crossBoRefs", []):
            target = ref.get("refBoCode")
            if target in bos:
                bos[target].setdefault("incomingRefs", []).append({
                    "fromBoCode": bo_code,
                    "fromBoName": bo["boName"],
                    "fromEntityCode": ref.get("fromEntityCode"),
                    "fromFieldCode": ref.get("fromFieldCode"),
                    "fromFieldName": ref.get("fromFieldName"),
                    "refFieldCode": ref.get("refFieldCode"),
                    "relationType": ref.get("relationType"),
                    "ruleCode": ref.get("ruleCode"),
                })

    # ── 构建边列表（从 CROSS_BO_REF） ──────────────────────────
    edges = []
    inferred_edge_keys = set()
    for bo_code, bo in bos.items():
        for ref in bo.get("crossBoRefs", []):
            target = ref.get("refBoCode")
            if target in bos:
                key = (bo_code, target, ref.get("relationType", ""))
                inferred_edge_keys.add(key)
                edges.append({
                    "from": bo_code,
                    "to": target,
                    "fromField": ref.get("fromFieldName", ref.get("fromFieldCode")),
                    "fromEntityCode": ref.get("fromEntityCode"),
                    "relationType": ref.get("relationType"),
                    "referenceNature": ref.get("referenceNature", "MASTER_DATA"),
                    "ruleCode": ref.get("ruleCode"),
                    "linkSource": "INFERRED",
                    "linkSourceLabel": "CROSS_BO_REF"
                })

    # ── 合并显式 LINK ──────────────────────────────────────────
    ontology_dir = METADATA_DIR / "design-time" / "_ontology"
    link_frag_file = ontology_dir / "fragments" / "crm-link.fragment.json"
    explicit_links = []
    if link_frag_file.exists():
        link_data = load_json(link_frag_file)
        if link_data:
            for link in link_data.get("content", {}).get("links", []):
                src_bo = link.get("source", {}).get("boCode", "")
                tgt_bo = link.get("target", {}).get("boCode", "")
                if src_bo and tgt_bo:
                    code = link.get("code", "")
                    explicit_links.append({
                        "from": src_bo,
                        "to": tgt_bo,
                        "linkCode": code,
                        "linkName": link.get("name", code),
                        "cardinality": link.get("cardinality", "MANY_TO_ONE"),
                        "direction": link.get("direction", "SOURCE_TO_TARGET"),
                        "linkKind": link.get("linkKind", "BUSINESS_FLOW"),
                        "materialization": link.get("materialization", "FIELD_REF"),
                        "authzMode": link.get("authzMode", "BOTH_ENDPOINTS"),
                        "description": link.get("description", ""),
                        "linkSource": "EXPLICIT",
                        "linkSourceLabel": "LINK Fragment"
                    })

    # 去重：显式 LINK 优先，移除被覆盖的 inferred 边
    explicit_keys = {(e["from"], e["to"]) for e in explicit_links}
    edges = [e for e in edges if (e["from"], e["to"]) not in explicit_keys]
    edges.extend(explicit_links)

    # ── 解析 _ontology DERIVATION / ACTION_CHAIN / TEMPORAL ──────
    derived_objects = []
    action_chains = []
    temporal_badges = {}   # boCode -> [timeline info]
    temporal_timelines = []  # 全局时间线列表（用于本体配置面板）
    ontology_edges = []

    # ── DERIVATION：派生对象虚拟节点 + 依赖边 ──
    derivation_file = ontology_dir / "fragments" / "crm-derivation.fragment.json"
    if derivation_file.exists():
        der_data = load_json(derivation_file)
        if der_data:
            for dobj in der_data.get("content", {}).get("derivedObjects", []):
                dobj_code = dobj.get("code", "")
                root_bo = dobj.get("root", {}).get("boCode", "")
                derived_objects.append({
                    "id": "derived:" + dobj_code,
                    "code": dobj_code,
                    "name": dobj.get("name", dobj_code),
                    "objectKind": dobj.get("objectKind", "DERIVED_VIEW"),
                    "description": dobj.get("description", ""),
                    "rootBoCode": root_bo,
                    "rootEntityCode": dobj.get("root", {}).get("entityCode", ""),
                    "fieldCount": len(dobj.get("fields", [])),
                    "fields": dobj.get("fields", []),
                    "materialization": dobj.get("materialization", {}),
                    "apiExposure": dobj.get("apiExposure", {}),
                    "dependencies": dobj.get("dependencies", []),
                })
                # root BO → 派生对象
                if root_bo:
                    ontology_edges.append({
                        "from": root_bo,
                        "to": "derived:" + dobj_code,
                        "linkSource": "DERIVATION_ROOT",
                        "linkSourceLabel": "派生根",
                        "label": dobj.get("name", dobj_code),
                    })
                # 依赖 BO → 派生对象
                for dep in dobj.get("dependencies", []):
                    dep_bo = dep.get("boCode", "")
                    if dep_bo:
                        ontology_edges.append({
                            "from": dep_bo,
                            "to": "derived:" + dobj_code,
                            "linkSource": "DERIVATION_DEP",
                            "linkSourceLabel": "派生依赖",
                            "label": dep.get("viaLink", ""),
                            "required": dep.get("required", False),
                        })

    # ── ACTION_CHAIN：动作链虚拟节点 + 触发/执行边 ──
    action_chain_file = ontology_dir / "fragments" / "crm-action-chain.fragment.json"
    if action_chain_file.exists():
        ac_data = load_json(action_chain_file)
        if ac_data:
            for chain in ac_data.get("content", {}).get("chains", []):
                chain_code = chain.get("code", "")
                trigger = chain.get("trigger", {})
                trigger_bo = trigger.get("boCode", "")
                action_chains.append({
                    "id": "chain:" + chain_code,
                    "code": chain_code,
                    "name": chain.get("name", chain_code),
                    "description": chain.get("description", ""),
                    "triggerType": trigger.get("type", ""),
                    "triggerBoCode": trigger_bo,
                    "triggerOperationCode": trigger.get("operationCode", ""),
                    "triggerCron": trigger.get("cronExpression", ""),
                    "triggerEventCode": trigger.get("eventCode", ""),
                    "executionMode": chain.get("executionMode", ""),
                    "stepCount": len(chain.get("steps", [])),
                    "steps": chain.get("steps", []),
                })
                # 触发 BO → 动作链
                if trigger_bo:
                    ontology_edges.append({
                        "from": trigger_bo,
                        "to": "chain:" + chain_code,
                        "linkSource": "TRIGGERS",
                        "linkSourceLabel": "触发",
                        "label": trigger.get("operationCode") or trigger.get("type", ""),
                    })
                # 动作链 → 步骤目标
                for step in chain.get("steps", []):
                    target = step.get("target", {})
                    target_bo = target.get("boCode", "")
                    target_derived = target.get("derivedCode", "")
                    if target_derived:
                        ontology_edges.append({
                            "from": "chain:" + chain_code,
                            "to": "derived:" + target_derived,
                            "linkSource": "EXECUTES",
                            "linkSourceLabel": "执行",
                            "label": step.get("name", step.get("code", "")),
                        })
                    elif target_bo:
                        ontology_edges.append({
                            "from": "chain:" + chain_code,
                            "to": target_bo,
                            "linkSource": "EXECUTES",
                            "linkSourceLabel": "执行",
                            "label": step.get("name", step.get("code", "")),
                        })

    # ── TEMPORAL：仅徽标，不产生节点/边 ──
    temporal_file = ontology_dir / "fragments" / "crm-temporal.fragment.json"
    if temporal_file.exists():
        tmp_data = load_json(temporal_file)
        if tmp_data:
            for tl in tmp_data.get("content", {}).get("timelines", []):
                tl_bo = tl.get("boCode", "")
                tl_info = {
                    "timelineCode": tl.get("code", ""),
                    "timelineName": tl.get("name", ""),
                    "description": tl.get("description", ""),
                    "boCode": tl_bo,
                    "entityCode": tl.get("entityCode", ""),
                    "identityField": tl.get("identityField", "id"),
                    "timeField": tl.get("timeField", ""),
                    "stateField": tl.get("stateField", ""),
                    "statusField": tl.get("statusField", ""),
                    "eventSources": tl.get("eventSources", []),
                    "snapshots": tl.get("snapshots", []),
                    "metricCount": len(tl.get("metrics", [])),
                    "metrics": tl.get("metrics", []),
                }
                temporal_timelines.append(tl_info)
                if tl_bo:
                    temporal_badges.setdefault(tl_bo, []).append(tl_info)

    return {
        "bos": list(bos.values()),
        "edges": edges,
        "explicitLinkCount": len(explicit_links),
        "derivedObjects": derived_objects,
        "actionChains": action_chains,
        "temporalBadges": temporal_badges,
        "temporalTimelines": temporal_timelines,
        "ontologyEdges": ontology_edges,
        "meta": {
            "boCount": len(bos),
            "edgeCount": len(edges),
            "explicitLinkCount": len(explicit_links),
            "derivedObjectCount": len(derived_objects),
            "actionChainCount": len(action_chains),
            "temporalBadgeCount": sum(len(v) for v in temporal_badges.values()),
            "ontologyEdgeCount": len(ontology_edges),
            "fragmentTypes": list(FRAGMENT_COLORS.keys()),
            "semanticRoleColors": SEMANTIC_ROLE_COLORS,
            "fragmentColors": FRAGMENT_COLORS,
            "linkSourceColors": LINK_SOURCE_COLORS,
            "layers": ["BO_REF", "LINK", "CONSISTENCY", "DISPLAY", "DERIVATION", "ACTION_CHAIN", "TEMPORAL_BADGE"],
        }
    }

def _summarize_fragment(meta_type: str, fragment: dict) -> dict:
    """提取 fragment 摘要信息。"""
    content = fragment.get("content", {})
    summary = {
        "metaType": meta_type,
        "draftVersion": fragment.get("draftVersion", 1),
        "schemaVersion": fragment.get("schemaVersion", "2.0"),
    }
    if meta_type == "MODEL":
        summary["entityCount"] = len(content.get("entities", []))
        summary["objectType"] = content.get("boConfig", {}).get("objectType", "SINGLE")
    elif meta_type == "VALIDATION":
        summary["ruleCount"] = len(content.get("rules", []))
    elif meta_type == "SECURITY":
        fs = content.get("fieldSecurity", [])
        summary["fieldSecurityCount"] = len(fs)
        summary["rowSecurityEntities"] = list(content.get("rowSecurity", {}).get("entriesByEntity", {}).keys())
    elif meta_type == "RULE":
        summary["ruleCount"] = len(content.get("rules", []))
    elif meta_type == "VIEW":
        summary["fieldViewCount"] = len(content.get("fieldViews", []))
    elif meta_type == "OPERATION":
        summary["operationCount"] = len(content.get("operations", []))
    return summary


def main():
    print("[SRCH] Parsing BO fragment files ...")
    if _load_schemas():
        print("   Schema 校验已启用")
    else:
        print("   [WARN] Schema load failed -> skip validation")
    graph = parse_all()
    print(f"\n[OK] Found {graph['meta']['boCount']} BOs, {graph['meta']['edgeCount']} cross-BO edges")
    if graph['meta'].get('derivedObjectCount'):
        print(f"   Derived objects: {graph['meta']['derivedObjectCount']}")
    if graph['meta'].get('actionChainCount'):
        print(f"   Action chains: {graph['meta']['actionChainCount']}")
    if graph['meta'].get('temporalBadgeCount'):
        print(f"   Temporal badges: {graph['meta']['temporalBadgeCount']}")
    if graph['meta'].get('ontologyEdgeCount'):
        print(f"   Ontology edges: {graph['meta']['ontologyEdgeCount']}")

    for bo in graph["bos"]:
        print(f"  [OBJ] {bo['boCode']} ({bo['boName']}) — {len(bo['entities'])} entities, {sum(len(e['attributes']) for e in bo['entities'])} attrs, {len(bo['operations'])} ops, {len(bo['rules'])} rules")

    # 确保输出目录存在
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"\n[RSLT] Graph data written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
