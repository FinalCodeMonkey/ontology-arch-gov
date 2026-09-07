#!/usr/bin/env python3
"""
从 schema-view.v2 发布态生成多种投影产物。

用法:
  python bo-projection-gen.py <boCode> [--type <投影类型>]
  python bo-projection-gen.py <boCode> --type merged-authz-bo-meta-model --merge-manifest <path>

投影类型:
  authz_bo_meta_model          权限元模型投影 — authz_bo_meta_model 表 schema_json 字段 (默认)
  api-contract                 API 契约投影 — REST 端点定义与聚合策略
  authz_projection             授权属性投影 — ABAC/PBAC 策略可引用的资源属性
  ui-model                     UI 模型投影 — 前端列表视图列定义
  merged-authz-bo-meta-model   合并权限元模型投影 — 多 BO 按 merge manifest 合并为单一 schema_json

自动合并:
  当使用默认类型 authz_bo_meta_model 时，会自动扫描 merge-manifests/ 目录，
  对本批次投影涉及的 BO 执行合并投影，无需手动指定 --merge-manifest。
  若需手动控制合并参数，仍可使用 --type merged-authz-bo-meta-model --merge-manifest <path>。

输出: metadata/projection-run-time/{boCode}/{boCode}.{type}.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

TOOLS_DIR = Path(__file__).resolve().parent
METADATA_DIR = TOOLS_DIR.parent / "metadata"

# ── 投影类型注册表 ──────────────────────────────────────────────
PROJECTION_TYPES = {
    "authz_bo_meta_model": {
        "name": "权限元模型",
        "suffix": "authz_bo_meta_model.schema_json.v2.json",
        "description": "authz_bo_meta_model 表 schema_json 字段内容",
    },
    "api-contract": {
        "name": "API 契约",
        "suffix": "api-contract.json",
        "description": "REST API 端点定义与聚合策略",
    },
    "authz_projection": {
        "name": "授权属性",
        "suffix": "authz_projection.json",
        "description": "ABAC/PBAC 策略可引用的资源属性视图",
    },
    "ui-model": {
        "name": "UI 模型",
        "suffix": "ui-model.json",
        "description": "前端列表视图列定义与排序配置",
    },
    "merged-authz-bo-meta-model": {
        "name": "合并权限元模型",
        "suffix": "authz_bo_meta_model.schema_json.merged.json",
        "description": "多 BO 按 merge manifest 合并为单一 authz_bo_meta_model schema_json",
    },
}

DEFAULT_TYPE = "authz_bo_meta_model"


def load_schema_view(bo_code: str) -> dict:
    """加载 schema-view.v2.json 发布态文件。"""
    sv_path = METADATA_DIR / "release-time" / bo_code / f"{bo_code}.schema-view.v2.json"
    if not sv_path.exists():
        print(f"❌ 发布态文件不存在: {sv_path}")
        print(f"   请先运行: python bo-publish-gen.py {bo_code}")
        sys.exit(1)
    with open(sv_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════
#  投影生成器
# ═══════════════════════════════════════════════════════════════════

# 显示字段的合法操作符（按类型推导，此常量定义全类型默认集，
# 实际生成时按 type 裁剪）
DISPLAY_FIELD_OPERATORS_BY_TYPE = {
    "STRING": ["EQ", "LIKE", "STARTS_WITH", "ENDS_WITH", "IN",
               "IS_NULL", "IS_NOT_NULL"],
    "LONG":   ["EQ", "IN", "IS_NULL", "IS_NOT_NULL"],
    "INTEGER":["EQ", "IN", "IS_NULL", "IS_NOT_NULL"],
    "DECIMAL":["EQ", "GT", "GTE", "LT", "LTE", "IN",
               "IS_NULL", "IS_NOT_NULL"],
    "DATE":   ["EQ", "GT", "GTE", "LT", "LTE", "BETWEEN",
               "IS_NULL", "IS_NOT_NULL"],
    "DATETIME":["EQ", "GT", "GTE", "LT", "LTE", "BETWEEN",
                "IS_NULL", "IS_NOT_NULL"],
}

def _build_display_field_mappings(entity: dict, current_bo_code: str,
                                  all_entities: list | None = None,
                                  _skip_chained: bool = False) -> dict:
    """为一跳 DIRECT_DISPLAY_REF 构建 displayFieldMappings。

    遍历 entity.attributes 中 semanticRole=CROSS_BO_REF 的属性，
    找出 crossBoRef.displayFields 中伴生的 CROSS_BO_DISPLAY 字段。
    仅收集 redundant=false 的非持久化显示字段，按 code 去重。

    当 all_entities 不为 None 且 _skip_chained=False 时，额外构建 CHAINED 映射。

    Returns:
        { display_field_code: { mapping_obj }, ... }，无匹配时返回 {}。
    """
    # 按 code 构建 attribute 索引
    attr_by_code = {}
    for a in entity.get("attributes", []):
        code = a.get("code")
        if code:
            attr_by_code[code] = a

    mappings = {}

    for ref_attr in entity.get("attributes", []):
        if ref_attr.get("semanticRole") != "CROSS_BO_REF":
            continue

        cross = ref_attr.get("crossBoRef")
        if not cross:
            continue

        ref_bo_code = cross.get("refBoCode")
        ref_field_code = cross.get("refFieldCode")

        for df in cross.get("displayFields", []):
            local_code = df.get("localCode")
            if not local_code:
                continue
            if local_code in mappings:
                # 同一个 display 字段被多个 REF 引用（罕见但可能）
                # 一阶段按 FIRST_WINS 取第一个
                continue

            display_attr = attr_by_code.get(local_code)
            if not display_attr:
                continue
            if display_attr.get("semanticRole") != "CROSS_BO_DISPLAY":
                continue
            if display_attr.get("redundant") is True:
                # redundant=true 的 DISPLAY 字段已有物理列，
                # 已在 attributes 中，不纳入 displayFieldMappings
                continue

            # 尝试解析目标 BO 的物理信息；返回三种状态: PHYSICAL(有完整物理列信息),
            # VIRTUAL_DISPLAY(目标字段是非冗余 CROSS_BO_DISPLAY), NOT_FOUND(不可解析)
            target_info = _resolve_target_bo_info(
                ref_bo_code, ref_field_code, df.get("refFieldCode")
            )

            # 跳过虚拟 DISPLAY 目标：该字段在目标 BO 中不存在物理列，
            # 其值通过更深的 CHAINED_DISPLAY_REF 解析，不应生成半残的 DIRECT_DISPLAY_REF
            if target_info and target_info.get("kind") == "VIRTUAL_DISPLAY":
                continue

            display_type = display_attr.get("type", "STRING")

            mapping = {
                "code": local_code,
                "name": display_attr.get("name", local_code),
                "type": display_type,
                "fieldName": display_attr.get("fieldName", local_code),
                "mappingKind": "DIRECT_DISPLAY_REF",
                "sourceRefCode": ref_attr["code"],
                "sourceRefColumnName": ref_attr.get("columnName",
                                                    ref_attr.get("fieldName",
                                                                 ref_attr["code"])),
                "refBoCode": ref_bo_code,
                "refPkFieldCode": ref_field_code,
                "displayRole": df.get("displayRole", "NAME"),
                "operators": DISPLAY_FIELD_OPERATORS_BY_TYPE.get(
                    display_type,
                    ["EQ", "IS_NULL", "IS_NOT_NULL"]
                ),
            }

            if target_info:
                mapping["refEntityCode"] = target_info["entityCode"]
                mapping["refTableName"] = target_info["tableName"]
                mapping["refPkColumnName"] = target_info["pkColumnName"]
                mapping["refFieldCode"] = df.get("refFieldCode")
                mapping["refColumnName"] = target_info["refColumnName"]
            else:
                # 目标 BO 未发布或字段不可解析时不阻塞生成，
                # 但 PSP 运行期可能无法执行该 mapping
                mapping["refEntityCode"] = ""
                mapping["refPkColumnName"] = ref_field_code or ""
                mapping["refFieldCode"] = df.get("refFieldCode")
                mapping["refColumnName"] = df.get("refFieldCode") or ""

            _decorate_datasource_info(mapping, current_bo_code, ref_bo_code)
            mappings[local_code] = mapping

    if all_entities and not _skip_chained:
        _merge_chained_mappings(
            mappings,
            _build_chained_cross_bo_display_mappings(entity, current_bo_code)
        )
        _merge_chained_mappings(
            mappings,
            _build_chained_parent_display_mappings(entity, current_bo_code, all_entities)
        )
        _merge_chained_mappings(
            mappings,
            _build_policy_derived_field_mappings(entity, current_bo_code, all_entities)
        )

    return mappings


def _merge_chained_mappings(target: dict, additions: dict) -> None:
    for code, mapping in additions.items():
        if code in target:
            print(f"❌ displayFieldMappings code 冲突: {code}", file=sys.stderr)
            sys.exit(1)
        target[code] = mapping


def _decorate_datasource_info(mapping: dict, source_bo_code: str, ref_bo_code: str) -> None:
    mapping["sourceBoCode"] = source_bo_code



def _strip_ref_suffix(code: str) -> str:
    for suffix in ("_id", "_code"):
        if code.endswith(suffix):
            return code[:-len(suffix)]
    return code


def _build_chained_cross_bo_display_mappings(entity: dict, current_bo_code: str,
                                             _visited: set | None = None) -> dict:
    """为当前 BO 的 CROSS_BO_REF 构建跨 BO 链式 DISPLAY 映射。

    递归解析目标 BO 的 displayFieldMappings（含其自身的 DIRECT 和 CHAINED 映射），
    将当前 BO 的 CROSS_BO_REF 跳作为第一跳 prepend 到目标 BO 的映射路径前。
    支持任意深度的链式引用（如 A → B → C → D 中 D 是物理列）。
    """
    if _visited is None:
        _visited = set()
    if current_bo_code in _visited:
        return {}
    _visited.add(current_bo_code)
    mappings = {}
    for ref_attr in entity.get("attributes", []):
        if ref_attr.get("semanticRole") != "CROSS_BO_REF":
            continue
        cross = ref_attr.get("crossBoRef") or {}
        ref_bo_code = cross.get("refBoCode")
        ref_field_code = cross.get("refFieldCode")
        target_entity_info = _resolve_target_entity_info(ref_bo_code, ref_field_code)
        if not target_entity_info:
            continue
        target_entity = target_entity_info["entity"]
        all_entities = target_entity_info.get("all_entities", [])
        # 传入 all_entities 但跳过链式构建（仅取 DIRECT 映射），
        # 避免 _build_display_field_mappings → _build_chained_cross_bo_display_mappings 的无限递归。
        # 对于 CHAINED 类型，用 target_mapping 的已有 path 做 prepend（见下方 else 分支）。
        target_mappings = _build_display_field_mappings(target_entity, ref_bo_code, all_entities,
                                                        _skip_chained=True)
        if not target_mappings:
            continue
        first_hop = _build_cross_bo_hop(entity, current_bo_code, ref_attr, cross, target_entity_info)
        for target_code, target_mapping in target_mappings.items():
            mapping_kind = target_mapping.get("mappingKind")
            common_code = f"{_strip_ref_suffix(ref_attr['code'])}_{target_code}"

            if mapping_kind == "CHAINED_DISPLAY_REF":
                # 目标 BO 自身也是链式引用时，prepend first_hop 到其已有 path 前
                existing_path = list(target_mapping.get("path", []))
                existing_labels = list(target_mapping.get("labelPath", []))
                mappings[common_code] = _build_chained_mapping(
                    common_code,
                    [target_entity.get("name", ref_bo_code)] + existing_labels,
                    [first_hop] + existing_path,
                    target_mapping,
                    current_bo_code,
                    target_mapping.get("refBoCode")
                )
            else:
                # DIRECT_DISPLAY_REF：构建标准的两跳链式映射
                second_hop = _build_hop_from_direct_mapping(target_entity, ref_bo_code, target_mapping)
                if not second_hop:
                    continue
                mappings[common_code] = _build_chained_mapping(
                    common_code,
                    [target_entity.get("name", target_entity.get("code", ref_bo_code)),
                     target_mapping.get("name", target_code)],
                    [first_hop, second_hop],
                    target_mapping,
                    current_bo_code,
                    target_mapping.get("refBoCode")
                )
    return mappings


def _build_chained_parent_display_mappings(entity: dict, current_bo_code: str, all_entities: list) -> dict:
    parent_entity_code = entity.get("parentEntityCode")
    if not parent_entity_code:
        return {}
    parent_entity = next((e for e in all_entities if e.get("code") == parent_entity_code), None)
    if not parent_entity:
        return {}
    parent_pk = _find_entity_pk_info(parent_entity)
    if not parent_pk:
        return {}
    parent_direct_mappings = _build_display_field_mappings(parent_entity, current_bo_code)
    if not parent_direct_mappings:
        return {}

    mappings = {}
    for parent_ref_attr in entity.get("attributes", []):
        if parent_ref_attr.get("semanticRole") != "PARENT_REF":
            continue
        first_hop = {
            "hopKind": "PARENT_REF",
            "fromBoCode": current_bo_code,
            "fromEntityCode": entity.get("code"),
            "fromTableName": entity.get("tableName", ""),
            "fromRefCode": parent_ref_attr["code"],
            "fromRefColumnName": parent_ref_attr.get("columnName", parent_ref_attr.get("fieldName", parent_ref_attr["code"])),
            "toBoCode": current_bo_code,
            "toEntityCode": parent_entity.get("code"),
            "toTableName": parent_entity.get("tableName", ""),
            "toPkFieldCode": parent_pk["fieldCode"],
            "toPkColumnName": parent_pk["columnName"],
        }
        for parent_display_code, parent_mapping in parent_direct_mappings.items():
            second_hop = _build_hop_from_direct_mapping(parent_entity, current_bo_code, parent_mapping)
            if not second_hop:
                continue
            code = f"parent_{parent_display_code}"
            mappings[code] = _build_chained_mapping(
                code,
                [parent_entity.get("name", parent_entity.get("code", parent_entity_code)), parent_mapping.get("name", parent_display_code)],
                [first_hop, second_hop],
                parent_mapping,
                current_bo_code,
                parent_mapping.get("refBoCode")
            )
    return mappings


def _build_policy_derived_field_mappings(entity: dict, current_bo_code: str, all_entities: list) -> dict:
    declarations = entity.get("policyDerivedFields") or []
    if not declarations:
        return {}
    entity_by_code = {e.get("code"): e for e in all_entities if e.get("code")}
    mappings = {}
    for declaration in declarations:
        code = declaration.get("code")
        target = declaration.get("target") or {}
        target_entity = entity_by_code.get(target.get("entityCode"))
        if not code or not target_entity:
            continue
        target_attr = _find_attribute(target_entity, target.get("fieldCode"))
        if not target_attr:
            continue
        path = _build_policy_derived_path(declaration.get("path") or [], entity_by_code, current_bo_code)
        if not path:
            continue
        label_path = declaration.get("labelPath") or [declaration.get("name", code)]
        display_type = declaration.get("type", target_attr.get("type", "STRING"))
        mappings[code] = {
            "code": code,
            "name": declaration.get("name", code),
            "type": display_type,
            "fieldName": declaration.get("fieldName", code),
            "mappingKind": "CHAINED_DISPLAY_REF",
            "labelPath": label_path,
            "operators": DISPLAY_FIELD_OPERATORS_BY_TYPE.get(display_type, ["EQ", "IS_NULL", "IS_NOT_NULL"]),
            "path": path,
            "target": {
                "boCode": current_bo_code,
                "entityCode": target_entity.get("code", ""),
                "tableName": target_entity.get("tableName", ""),
                "fieldCode": target_attr.get("code", ""),
                "columnName": target_attr.get("columnName", target_attr.get("fieldName", target_attr.get("code", ""))),
            },
            "sourceBoCode": current_bo_code,
        }
    return mappings


def _build_policy_derived_path(path_spec: list, entity_by_code: dict, current_bo_code: str) -> list:
    path = []
    for hop_spec in path_spec:
        if hop_spec.get("hopKind") != "PARENT_REF":
            return []
        from_entity = entity_by_code.get(hop_spec.get("fromEntityCode"))
        to_entity = entity_by_code.get(hop_spec.get("toEntityCode"))
        if not from_entity or not to_entity:
            return []
        from_attr = _find_attribute(from_entity, hop_spec.get("fromRefCode"))
        to_pk = _find_entity_pk_info(to_entity)
        if not from_attr or not to_pk:
            return []
        path.append({
            "hopKind": "PARENT_REF",
            "fromBoCode": current_bo_code,
            "fromEntityCode": from_entity.get("code"),
            "fromTableName": from_entity.get("tableName", ""),
            "fromRefCode": from_attr.get("code"),
            "fromRefColumnName": from_attr.get("columnName", from_attr.get("fieldName", from_attr.get("code"))),
            "toBoCode": current_bo_code,
            "toEntityCode": to_entity.get("code"),
            "toTableName": to_entity.get("tableName", ""),
            "toPkFieldCode": to_pk["fieldCode"],
            "toPkColumnName": to_pk["columnName"],
        })
    return path


def _find_attribute(entity: dict, attr_code: str) -> dict | None:
    if not attr_code:
        return None
    return next((a for a in entity.get("attributes", []) if a.get("code") == attr_code), None)


def _build_chained_mapping(code: str, label_path: list, path: list, direct_mapping: dict,
                           source_bo_code: str, ref_bo_code: str) -> dict:
    mapping = {
        "code": code,
        "name": " / ".join([p for p in label_path if p]),
        "type": direct_mapping.get("type", "STRING"),
        "fieldName": code,
        "mappingKind": "CHAINED_DISPLAY_REF",
        "labelPath": label_path,
        "operators": direct_mapping.get("operators", ["EQ", "IS_NULL", "IS_NOT_NULL"]),
        "path": path,
        "target": {
            "boCode": direct_mapping.get("refBoCode", ""),
            "entityCode": direct_mapping.get("refEntityCode", ""),
            "tableName": direct_mapping.get("refTableName", ""),
            "fieldCode": direct_mapping.get("refFieldCode", ""),
            "columnName": direct_mapping.get("refColumnName", ""),
        }
    }
    _decorate_datasource_info(mapping, source_bo_code, ref_bo_code)
    return mapping


def _build_cross_bo_hop(entity: dict, current_bo_code: str, ref_attr: dict, cross: dict,
                        target_entity_info: dict) -> dict:
    return {
        "hopKind": "CROSS_BO_REF",
        "fromBoCode": current_bo_code,
        "fromEntityCode": entity.get("code"),
        "fromTableName": entity.get("tableName", ""),
        "fromRefCode": ref_attr["code"],
        "fromRefColumnName": ref_attr.get("columnName", ref_attr.get("fieldName", ref_attr["code"])),
        "toBoCode": cross.get("refBoCode"),
        "toEntityCode": target_entity_info["entityCode"],
        "toTableName": target_entity_info["tableName"],
        "toPkFieldCode": cross.get("refFieldCode"),
        "toPkColumnName": target_entity_info["pkColumnName"],
    }


def _build_hop_from_direct_mapping(entity: dict, current_bo_code: str, mapping: dict) -> dict | None:
    required = ["sourceRefCode", "sourceRefColumnName", "refBoCode", "refEntityCode", "refTableName", "refPkFieldCode", "refPkColumnName"]
    if any(not mapping.get(k) for k in required):
        return None
    return {
        "hopKind": "CROSS_BO_REF",
        "fromBoCode": current_bo_code,
        "fromEntityCode": entity.get("code"),
        "fromTableName": entity.get("tableName", ""),
        "fromRefCode": mapping["sourceRefCode"],
        "fromRefColumnName": mapping["sourceRefColumnName"],
        "toBoCode": mapping["refBoCode"],
        "toEntityCode": mapping["refEntityCode"],
        "toTableName": mapping["refTableName"],
        "toPkFieldCode": mapping["refPkFieldCode"],
        "toPkColumnName": mapping["refPkColumnName"],
    }


def _find_entity_pk_info(entity: dict) -> dict | None:
    pk_attr = next((a for a in entity.get("attributes", []) if a.get("isPk")), None)
    if not pk_attr:
        return None
    return {
        "fieldCode": pk_attr["code"],
        "columnName": pk_attr.get("columnName", pk_attr.get("fieldName", pk_attr["code"])),
    }


def _resolve_target_entity_info(ref_bo_code: str, pk_field_code: str) -> dict | None:
    if not ref_bo_code or not pk_field_code:
        return None
    sv_path = (METADATA_DIR / "release-time" / ref_bo_code /
               f"{ref_bo_code}.schema-view.v2.json")
    if not sv_path.exists():
        return None
    try:
        with open(sv_path, "r", encoding="utf-8-sig") as f:
            target_sv = json.load(f)
    except Exception:
        return None

    all_entities = target_sv.get("entities", [])
    primary = next((e for e in all_entities if e.get("isPrimary")), None)
    candidates = [primary] if primary else []
    candidates.extend([e for e in all_entities if e is not primary])
    for ent in candidates:
        if ent is None:
            continue
        attr_by_code = {a["code"]: a for a in ent.get("attributes", [])}
        pk_attr = attr_by_code.get(pk_field_code)
        if pk_attr is not None:
            return {
                "entity": ent,
                "entityCode": ent["code"],
                "tableName": ent.get("tableName", ""),
                "pkColumnName": pk_attr.get("columnName", pk_attr.get("fieldName", pk_field_code)),
                "all_entities": all_entities,
            }
    return None


def _resolve_target_bo_info(ref_bo_code: str, pk_field_code: str,
                            display_field_code: str) -> dict | None:
    """读取目标 BO 的发布态 schema，解析 entityCode / pkColumnName / refColumnName。

    Returns:
        - {"kind": "PHYSICAL", "entityCode": ..., ...} — 目标字段在目标 BO 有物理列
        - {"kind": "VIRTUAL_DISPLAY"} — 目标字段是非冗余 CROSS_BO_DISPLAY，需链式解析
        - None — 目标 BO 不存在或字段不可解析
    """
    if not ref_bo_code or not pk_field_code or not display_field_code:
        return None

    sv_path = (METADATA_DIR / "release-time" / ref_bo_code /
               f"{ref_bo_code}.schema-view.v2.json")
    if not sv_path.exists():
        import sys
        print(f"⚠ displayFieldMappings: 目标 BO '{ref_bo_code}' 发布态不存在，"
              f"跳过列名解析 ({pk_field_code}/{display_field_code})",
              file=sys.stderr)
        return None

    try:
        with open(sv_path, "r", encoding="utf-8-sig") as f:
            target_sv = json.load(f)
    except Exception:
        return None

    # 找到包含 pk_field_code 和 display_field_code 的实体
    all_entities = target_sv.get("entities", [])
    # 优先 primary entity，其次遍历
    primary = next((e for e in all_entities if e.get("isPrimary")), None)
    candidates = [primary] if primary else []
    candidates.extend([e for e in all_entities if e is not primary])

    for ent in candidates:
        if ent is None:
            continue
        attr_by_code = {a["code"]: a for a in ent.get("attributes", [])}
        pk_attr = attr_by_code.get(pk_field_code)
        disp_attr = attr_by_code.get(display_field_code)
        if pk_attr is not None and disp_attr is not None:
            # 跳过虚拟 CROSS_BO_DISPLAY：目标字段在目标 BO 中是非持久化显示字段，
            # 其在目标 BO 的真实值由更深的链式引用解析，直接引用会导致 refColumnName 指向不存在的列
            if (disp_attr.get("semanticRole") == "CROSS_BO_DISPLAY"
                    and disp_attr.get("redundant") is not True):
                return {"kind": "VIRTUAL_DISPLAY"}
            return {
                "kind": "PHYSICAL",
                "entityCode": ent["code"],
                "tableName": ent.get("tableName", ""),
                "pkColumnName": pk_attr.get("columnName",
                                             pk_attr.get("fieldName",
                                                         pk_field_code)),
                "refColumnName": disp_attr.get("columnName",
                                                disp_attr.get("fieldName",
                                                              display_field_code)),
            }

    return None


def generate_authz_bo_meta_model(bo_code: str, sv: dict) -> dict:
    """生成 authz_bo_meta_model.schema_json 投影 (权限元模型)。"""
    # 设计态枚举 → PSP 运行时枚举映射
    # PSP BoSchemaJsonValidator.SUPPORTED_FIELD_CONTROL_STRATEGIES: OPEN/RESTRICTED/MASK/HIDE
    field_control_map = {"MASKED": "MASK", "HIDDEN": "HIDE"}
    # PSP BoSchemaJsonValidator.validateOperations: scope 仅支持 BO 或 ENTITY
    scope_map = {"GLOBAL": "BO"}

    entities = []
    for ent in sv.get("entities", []):
        attrs = []
        for a in ent.get("attributes", []):
            # 过滤非持久化 CROSS_BO_DISPLAY 字段
            # seanticrole=CROSS_BO_DISPLAY 且 redundant!=true 表示该字段不在物理表中,
            # 其值由应用层从权威源解析, PSP 无需也不应对一个不存在的列做控制.
            sr = a.get("semanticRole", "")
            if sr == "CROSS_BO_DISPLAY" and not a.get("redundant"):
                continue

            fc = a.get("fieldControl")
            has_fc = bool(fc and fc != "OPEN")
            attr = {
                "code": a["code"],
                "name": a["name"],
                "type": a["type"],
                "isPk": a.get("isPk", False),
                "fieldName": a.get("fieldName", a["code"]),
                "columnName": a.get("columnName", a["code"]),
                "fieldControl": has_fc,
                "filterable": a.get("filterable", False),
            }
            if has_fc:
                attr["fieldControlStrategy"] = field_control_map.get(fc, fc)
            attrs.append(attr)

        entities.append({
            "code": ent["code"],
            "name": ent["name"],
            "isPrimary": ent.get("isPrimary", False),
            "tableName": ent.get("tableName", ""),
            "rowLevelRuleEntries": ent.get("rowLevelRuleEntries", []),
            "cascadeDelete": ent.get("cascadeDelete", False),
            "attributes": attrs,
        })
        # 投影 routeSegment 和 parentEntityCode（用于 URL → Bo 路由提取）
        if ent.get("routeSegment"):
            entities[-1]["routeSegment"] = ent["routeSegment"]
        if ent.get("parentEntityCode"):
            entities[-1]["parentEntityCode"] = ent["parentEntityCode"]

        # 生成 displayFieldMappings (CROSS_BO_DISPLAY && redundant=false 的虚拟显示字段)
        display_mappings = _build_display_field_mappings(ent, sv.get("boCode", bo_code), sv.get("entities", []))
        if display_mappings:
            entities[-1]["displayFieldMappings"] = display_mappings

    operations = []
    # 新的 act_aliases 格式: code=authzAction, act_aliases=该authzAction下所有operation.code
    authz_groups = {}
    for op in sv.get("operations", []):
        authz = op["authzAction"]
        if authz not in authz_groups:
            authz_groups[authz] = []
        authz_groups[authz].append(op)

    for authz, group in authz_groups.items():
        # 优先选 code == authz 的操作作为 name 来源（规范定义操作），
        # 其次取第一个
        winner_op = next((op for op in group if op["code"] == authz), group[0])
        aliases = []
        # V2.1: act_aliases 仅包含 kebab-case actionPath，供 ApiUrlBoExtractor 反向匹配 URL。
        # RuntimeLookupService 已改为仅匹配 operations[].code，不再消费 aliases。
        # 标准 CRUD(READ/DELETE/UPDATE/CREATE) 已有 URL 模板匹配，不需 actionPath；
        # 其他操作如无显式 actionPath，则从 code(UPPER_SNAKE→kebab-case) 自动推导。
        CRUD_KINDS = {"CREATE", "READ", "UPDATE", "DELETE"}
        for op in group:
            ap = op.get("actionPath", "")
            if ap:
                aliases.append(ap)
            elif op.get("operationKind") not in CRUD_KINDS:
                aliases.append(op["code"].replace('_', '-').lower())
        o = {
            "code": authz,
            "name": winner_op.get("name", winner_op["code"]),
            "scope": scope_map.get(winner_op.get("scope", "BO"), winner_op.get("scope", "BO")),
            "act_aliases": ",".join(aliases),
        }
        if winner_op.get("primaryDataAction"):
            o["primaryDataAction"] = winner_op["primaryDataAction"]
        if winner_op.get("entityCode"):
            o["entityCode"] = winner_op["entityCode"]
        operations.append(o)

    perm_items = []
    seen = set()
    for op in operations:
        key = f"RES_DATA_BO + {bo_code}_bo_meta_id + {op['code']}"
        if key not in seen:
            seen.add(key)
            perm_items.append(key)

    return {
        "_gov_meta": {
            "description": f"PSP authz_bo_meta_model 表 schema_json 字段(v2.0)，bo_code='{bo_code}'",
            "target_table": "authz_bo_meta_model",
            "target_condition": f"bo_code = '{bo_code}'",
            "generated_from": f"{bo_code}.schema-view.v2.json",
            "schema_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "schema_json": {"entities": entities, "operations": operations},
        "_sql": {
            "update_statement": f"UPDATE authz_bo_meta_model SET schema_json = '<JSON>', updated_by = 'governance', updated_at = NOW() WHERE bo_code = '{bo_code}' AND tenant_id = 'default' AND is_deleted = 0;",
            "verify_statement": f"SELECT id, bo_code, bo_name, adapter_type, resolver, data_domain_id, updated_at FROM authz_bo_meta_model WHERE bo_code = '{bo_code}' AND tenant_id = 'default' AND is_deleted = 0;",
            "expected_permission_items_after_publish": perm_items,
        },
    }


def generate_api_contract(bo_code: str, sv: dict) -> dict:
    """生成 API 契约投影。"""
    root_entity = next((e for e in sv.get("entities", []) if e.get("isPrimary")), None)
    sub_entities = [e for e in sv.get("entities", []) if not e.get("isPrimary")]

    entity_api_policies = {}
    for ent in sub_entities:
        entity_api_policies[ent["code"]] = {
            "listProjectionScope": "ENTITY_SUMMARY",
            "readScope": "ENTITY_ONLY",
            "createScope": "ENTITY_AGGREGATE",
            "updateScope": "ENTITY_ONLY",
            "deleteScope": "CASCADE_CHILDREN",
            "orphanPolicy": "DENY_DELETE_WHEN_CHILD_EXISTS",
        }

    return {
        "boCode": bo_code,
        "boName": sv.get("boName", bo_code),
        "resourcePath": f"/{bo_code}",
        "responseWrapper": "ApiResponse",
        "batchResultType": "BatchResultDTO",
        "aggregateApiPolicy": {
            "listProjectionScope": "ROOT_SUMMARY",
            "readScope": "FULL_AGGREGATE",
            "createScope": "FULL_AGGREGATE",
            "updateScope": "ROOT_ENTITY_ONLY",
            "deleteScope": "CASCADE_AGGREGATE",
            "orphanPolicy": "DENY_DELETE_WHEN_CHILD_EXISTS",
            "detailEmbedEntities": [e["code"] for e in sub_entities],
            "aggregateReplaceActionPath": "replace-aggregate",
        },
        "entityApiPolicies": entity_api_policies,
        "_gov_meta": {
            "generated_from": f"{bo_code}.schema-view.v2.json",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def generate_authz_projection(bo_code: str, sv: dict) -> dict:
    """生成授权属性投影 (ABAC/PBAC 资源属性视图)。"""
    root_entity = next((e for e in sv.get("entities", []) if e.get("isPrimary")),
                       sv["entities"][0] if sv.get("entities") else {})

    attributes = []
    order = 10
    grouping = {"基本标识": [], "业务属性": [], "组织归属": [], "状态标记": []}

    for attr in root_entity.get("attributes", []):
        sem = attr.get("semanticRole", "NORMAL")
        group = "业务属性"
        if sem in ("TECHNICAL_ID", "BUSINESS_KEY", "NAME"):
            group = "基本标识"
        elif sem in ("PARENT_REF", "CROSS_BO_REF"):
            group = "组织归属"
        elif sem == "STATUS":
            group = "状态标记"

        grouping.setdefault(group, []).append(attr)

    for group_name in ["基本标识", "业务属性", "组织归属", "状态标记"]:
        for attr in grouping.get(group_name, []):
            attributes.append({
                "code": attr["code"],
                "name": attr.get("name", attr["code"]),
                "type": attr.get("type", "STRING"),
                "isPk": attr.get("isPk", False),
                "filterable": attr.get("filterable", False),
                "nullable": not attr.get("isPk", False),
                "onMissingValue": "DENY" if attr.get("isPk") else "IGNORE",
                "displayOrder": order,
                "displayGroup": group_name,
                "description": f"{attr.get('name', attr['code'])} [{(attr.get('semanticRole', 'NORMAL'))}]",
            })
            order += 10

    return {
        "$schema": "https://authz.xbac/schemas/authz_schema_view.schema.json",
        "description": f"{bo_code} 业务对象的权限属性投影",
        "category": "RESOURCE",
        "attributes": attributes,
        "_gov_meta": {
            "generated_from": f"{bo_code}.schema-view.v2.json",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def generate_ui_model(bo_code: str, sv: dict) -> dict:
    """生成 UI 模型投影 (列表视图列定义)。"""
    root_entity = next((e for e in sv.get("entities", []) if e.get("isPrimary")),
                       sv["entities"][0] if sv.get("entities") else {})

    view_fields = sv.get("fieldViews", [])
    view_map = {}
    for vf in view_fields:
        view_map[(vf.get("entityCode", root_entity.get("code", "")),
                  vf.get("fieldCode", ""))] = vf

    columns = []
    for attr in root_entity.get("attributes", []):
        vf = view_map.get((root_entity.get("code", ""), attr["code"]), {})
        if vf.get("showInList", True):
            columns.append({
                "fieldCode": attr["code"],
                "title": attr.get("name", attr["code"]),
                "width": vf.get("columnWidth") or (70 if attr.get("isPk") else 130),
                "sortable": vf.get("sortable", attr.get("filterable", False)),
                "format": "date" if attr.get("type") in ("DATETIME", "DATE") else "text",
            })

    return {
        "boCode": bo_code,
        "boName": sv.get("boName", bo_code),
        "resourcePath": f"/{bo_code}",
        "primaryEntityCode": root_entity.get("code", ""),
        "listView": {
            "defaultPageSize": sv.get("listViewConfig", {}).get("defaultPageSize", 20),
            "defaultSort": {
                "field": "create_time",
                "direction": "desc",
            },
            "columns": columns,
        },
        "_gov_meta": {
            "generated_from": f"{bo_code}.schema-view.v2.json",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ── 合并投影生成器 ─────────────────────────────────────────────

def load_merge_manifest(merge_manifest_path: str) -> dict:
    """加载 merge manifest 配置文件。"""
    p = Path(merge_manifest_path)
    if not p.is_absolute():
        p = METADATA_DIR / "merge-manifests" / merge_manifest_path
    if not p.exists():
        print(f"❌ merge manifest 不存在: {p}")
        sys.exit(1)
    with open(p, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _collect_same_row_merged_entities(sources: list) -> set:
    same_row_entities = set()
    for src in sources:
        src_bo = src["boCode"]
        for ent_code, strategy in src.get("entityMergeStrategy", {}).items():
            if strategy.get("mergeType") == "SAME_ROW_COLUMN_SUBSET":
                same_row_entities.add((src_bo, ent_code))
    return same_row_entities


def _find_merged_root_pk(source_svs: dict, sources: list, root_code: str) -> dict:
    for src in sources:
        src_sv = source_svs[src["boCode"]]
        for ent in src_sv.get("entities", []):
            if ent.get("code") == root_code or ent.get("isPrimary"):
                pk = _find_entity_pk_info(ent)
                if pk:
                    return pk
    return {"fieldCode": "id", "columnName": "id"}


def _rewrite_merged_display_field_mappings(mappings: dict, same_row_entities: set,
                                           merged_source_bo_codes: set,
                                           target_bo_code: str, root_code: str,
                                           target_table: str, root_pk: dict) -> dict:
    rewritten = {}
    for code, mapping in mappings.items():
        next_mapping = dict(mapping)
        if next_mapping.get("mappingKind") == "CHAINED_DISPLAY_REF":
            next_mapping["path"] = _collapse_same_row_merged_path(
                next_mapping.get("path", []),
                same_row_entities,
                target_bo_code,
                root_code,
                target_table,
                root_pk,
            )
            next_mapping["target"] = _rewrite_same_row_merged_target(
                next_mapping.get("target", {}),
                same_row_entities,
                target_bo_code,
                root_code,
                target_table,
                root_pk,
            )
        next_mapping = _normalize_merged_mapping_bo_refs(
            next_mapping,
            merged_source_bo_codes,
            target_bo_code,
        )
        rewritten[code] = next_mapping
    return rewritten


def _normalize_merged_mapping_bo_refs(mapping: dict, merged_source_bo_codes: set,
                                      target_bo_code: str) -> dict:
    def normalize_bo_code(bo_code: str) -> str:
        return target_bo_code if bo_code in merged_source_bo_codes else bo_code

    next_mapping = dict(mapping)
    for key in ("sourceBoCode", "refBoCode"):
        if next_mapping.get(key):
            next_mapping[key] = normalize_bo_code(next_mapping[key])

    if isinstance(next_mapping.get("target"), dict):
        target = dict(next_mapping["target"])
        if target.get("boCode"):
            target["boCode"] = normalize_bo_code(target["boCode"])
        next_mapping["target"] = target

    if isinstance(next_mapping.get("path"), list):
        normalized_path = []
        for hop in next_mapping["path"]:
            next_hop = dict(hop)
            for key in ("fromBoCode", "toBoCode"):
                if next_hop.get(key):
                    next_hop[key] = normalize_bo_code(next_hop[key])
            normalized_path.append(next_hop)
        next_mapping["path"] = normalized_path

    return next_mapping


def _rewrite_same_row_merged_target(target: dict, same_row_entities: set,
                                    target_bo_code: str, root_code: str,
                                    target_table: str, root_pk: dict) -> dict:
    next_target = dict(target)
    if (next_target.get("boCode"), next_target.get("entityCode")) in same_row_entities:
        next_target["boCode"] = target_bo_code
        next_target["entityCode"] = root_code
        next_target["tableName"] = target_table
        next_target["fieldCode"] = root_pk["fieldCode"]
        next_target["columnName"] = root_pk["columnName"]
    return next_target


def _collapse_same_row_merged_path(path: list, same_row_entities: set,
                                   target_bo_code: str, root_code: str,
                                   target_table: str, root_pk: dict) -> list:
    collapsed = []
    index = 0
    while index < len(path):
        hop = dict(path[index])
        same_row_key = (hop.get("toBoCode"), hop.get("toEntityCode"))
        if index + 1 < len(path):
            next_hop = path[index + 1]
            can_rewrite_same_row = (
                same_row_key in same_row_entities
                and next_hop.get("hopKind") == "CROSS_BO_REF"
                and next_hop.get("fromBoCode") == hop.get("toBoCode")
                and next_hop.get("fromEntityCode") == hop.get("toEntityCode")
            )
            if can_rewrite_same_row:
                hop["toBoCode"] = target_bo_code
                hop["toEntityCode"] = root_code
                hop["toTableName"] = target_table
                hop["toPkFieldCode"] = root_pk["fieldCode"]
                hop["toPkColumnName"] = root_pk["columnName"]
                collapsed.append(hop)
                if next_hop.get("toBoCode") == target_bo_code and next_hop.get("toEntityCode") == root_code:
                    index += 2
                    continue
                rewritten_next = dict(next_hop)
                rewritten_next["fromBoCode"] = target_bo_code
                rewritten_next["fromEntityCode"] = root_code
                rewritten_next["fromTableName"] = target_table
                collapsed.append(rewritten_next)
                index += 2
                continue
        if same_row_key in same_row_entities:
            hop["toBoCode"] = target_bo_code
            hop["toEntityCode"] = root_code
            hop["toTableName"] = target_table
            hop["toPkFieldCode"] = root_pk["fieldCode"]
            hop["toPkColumnName"] = root_pk["columnName"]
        collapsed.append(hop)
        index += 1
    return collapsed


def generate_merged_authz_bo_meta_model(bo_code: str, sv: dict, merge_manifest: dict = None) -> dict:
    """根据 merge manifest 将多个 BO 的 schema_view 合并为单一 authz_bo_meta_model schema_json。"""
    if merge_manifest is None:
        print("❌ merged-authz-bo-meta-model 需要 --merge-manifest 参数")
        sys.exit(1)

    target_bo_code = merge_manifest["targetBoCode"]
    target_table = merge_manifest["targetTableName"]
    sources = merge_manifest["sources"]
    merge_rules = merge_manifest["mergeRules"]

    # 加载所有来源 BO 的 schema_view
    source_svs = {}
    for src in sources:
        src_bo = src["boCode"]
        if src_bo == bo_code:
            source_svs[src_bo] = sv
        else:
            source_svs[src_bo] = load_schema_view(src_bo)

    # PSP 枚举映射
    field_control_map = {"MASKED": "MASK", "HIDDEN": "HIDE"}
    scope_map = {"GLOBAL": "BO"}

    def to_psp_attr(a: dict) -> dict:
        # 过滤非持久化 CROSS_BO_DISPLAY 字段
        sr = a.get("semanticRole", "")
        if sr == "CROSS_BO_DISPLAY" and not a.get("redundant"):
            return None

        fc = a.get("fieldControl")
        has_fc = bool(fc and fc != "OPEN")
        attr = {
            "code": a["code"],
            "name": a.get("name", a["code"]),
            "type": a.get("type", "STRING"),
            "isPk": a.get("isPk", False),
            "fieldName": a.get("fieldName", a["code"]),
            "columnName": a.get("columnName", a["code"]),
            "fieldControl": has_fc,
            "filterable": a.get("filterable", False),
        }
        if has_fc:
            attr["fieldControlStrategy"] = field_control_map.get(fc, fc)
        return attr

    # ── 合并实体 ──
    merged_entities = []
    root_entity = None
    root_code = merge_rules["rootEntity"]["mergedCode"]
    root_pk = _find_merged_root_pk(source_svs, sources, root_code)
    same_row_entities = _collect_same_row_merged_entities(sources)
    merged_source_bo_codes = {src["boCode"] for src in sources}
    existing_col_names = set()

    for src in sources:
        src_bo = src["boCode"]
        src_sv = source_svs[src_bo]
        strategies = src.get("entityMergeStrategy", {})

        for ent in src_sv.get("entities", []):
            ent_code = ent["code"]
            strategy = strategies.get(ent_code, {"mergeType": "PASS_THROUGH"})
            merge_type = strategy["mergeType"]

            if merge_type == "EXCLUDE":
                continue

            if merge_type == "SAME_ROW_COLUMN_SUBSET":
                # 合并到根实体
                merge_into = strategy["mergeInto"]
                shared_pk = strategy.get("sharedPk", False)
                exclude_attrs = set(strategy.get("excludeAttributes", []))

                if root_entity is None:
                    print(f"❌ SAME_ROW_COLUMN_SUBSET 需要先有根实体 (mergeInto={merge_into})")
                    sys.exit(1)

                for a in ent.get("attributes", []):
                    if a["code"] in exclude_attrs:
                        continue
                    psp_attr = to_psp_attr(a)
                    if psp_attr is None:
                        continue

                    col_name = a.get("columnName", a["code"])
                    if col_name in existing_col_names:
                        continue  # PRIMARY_WINS
                    root_entity["attributes"].append(psp_attr)
                    existing_col_names.add(col_name)

            elif merge_type == "PASS_THROUGH":
                psp_attrs = [pa for a in ent.get("attributes", []) if (pa := to_psp_attr(a)) is not None]
                psp_ent = {
                    "code": ent_code,
                    "name": ent.get("name", ent_code),
                    "isPrimary": ent.get("isPrimary", False),
                    "tableName": ent.get("tableName", ""),
                    "rowLevelRuleEntries": ent.get("rowLevelRuleEntries", []),
                    "cascadeDelete": ent.get("cascadeDelete", False),
                    "attributes": psp_attrs,
                }
                # 投影 routeSegment（优先用 merge 策略的，其次用 schema_view 的）
                merged_route = strategy.get("routeSegment") or ent.get("routeSegment")
                if merged_route:
                    psp_ent["routeSegment"] = merged_route
                merged_parent = strategy.get("parentEntityCode") or ent.get("parentEntityCode")
                if merged_parent:
                    psp_ent["parentEntityCode"] = merged_parent

                if ent.get("isPrimary") and root_entity is None:
                    # PRIMARY 根实体
                    root_entity = psp_ent
                    root_entity["code"] = root_code
                    root_entity["tableName"] = target_table
                    existing_col_names = {a.get("columnName", a["code"]) for a in psp_attrs}
                    merged_entities.append(root_entity)
                else:
                    # 子实体：reparentTo
                    reparent = strategy.get("reparentTo")
                    if reparent:
                        psp_ent["parentEntityCode"] = reparent
                    merged_entities.append(psp_ent)

                # 携带 displayFieldMappings（从源实体构建）
                display_mappings = _build_display_field_mappings(ent, src_bo, src_sv.get("entities", []))
                if display_mappings:
                    display_mappings = _rewrite_merged_display_field_mappings(
                        display_mappings,
                        same_row_entities,
                        merged_source_bo_codes,
                        target_bo_code,
                        root_code,
                        target_table,
                        root_pk,
                    )
                    psp_ent["displayFieldMappings"] = display_mappings

    # 合并 rowLevelRuleEntries
    # 收集所有 SAME_ROW_COLUMN_SUBSET 策略的 excludeAttributes，
    # 这些属性不应出现在合并后的 RLS 中
    rls_exclude_set = set()
    for src in sources:
        strategies = src.get("entityMergeStrategy", {})
        for ent_code, strategy in strategies.items():
            if strategy.get("mergeType") == "SAME_ROW_COLUMN_SUBSET":
                rls_exclude_set.update(strategy.get("excludeAttributes", []))

    all_row_entries = set()
    for ent in merged_entities:
        if ent.get("isPrimary"):
            all_row_entries.update(ent.get("rowLevelRuleEntries", []))
    # 从所有来源的 SECURITY rowSecurity 补充
    for src in sources:
        src_bo = src["boCode"]
        src_sv = source_svs[src_bo]
        for ent in src_sv.get("entities", []):
            if ent.get("isPrimary"):
                for entry in ent.get("rowLevelRuleEntries", []):
                    if entry not in rls_exclude_set:
                        all_row_entries.add(entry)
    if root_entity:
        root_entity["rowLevelRuleEntries"] = sorted(all_row_entries)

    # ── 合并后校验：parentEntityCode 悬空引用检测 ──
    all_codes = {e["code"] for e in merged_entities}
    dangling = []
    for ent in merged_entities:
        parent = ent.get("parentEntityCode")
        if parent and parent not in all_codes:
            dangling.append(f"  ❌ entity={ent['code']} parentEntityCode={parent}（目标不存在）")
    if dangling:
        print("⚠️  parentEntityCode 悬空引用检测到以下问题：")
        for line in dangling:
            print(line)
        suggestion_codes = ", ".join(
            sorted(all_codes, key=lambda x: (0 if any(e.get("isPrimary") for e in merged_entities if e["code"] == x) else 1, x))[:5]
        )
        print(f"💡 可用实体: {suggestion_codes}" + ("..." if len(all_codes) > 5 else ""))
        print("💡 修复: 在 merge-manifest 中为相关实体添加 reparentTo")
        sys.exit(1)

    # ── 合并操作 ──
    # 新的 act_aliases 格式:
    #   code = authzAction (规范动作 code)
    #   act_aliases = 该 authzAction 下所有 operation.code 的逗号拼接
    #   去重规则: 同一 authzAction 只保留一条 (PRIMARY_WINS)
    merged_ops = []
    seen_authz = set()
    dedup = merge_rules["operations"].get("deduplicateByAuthzAction", True)

    # 1) 收集: { authzAction -> [ (src_role, operation) ] }
    authz_groups = {}
    for src in sources:
        src_bo = src["boCode"]
        src_sv = source_svs[src_bo]
        src_role = src.get("role", "PRIMARY")
        rename_map = src.get("operationRename", {})
        exclude_ops = set(src.get("operationExclude", []))

        for op in src_sv.get("operations", []):
            if op["code"] in exclude_ops:
                continue
            effective_code = rename_map.get(op["code"], op["code"])
            authz = op["authzAction"]
            if authz not in authz_groups:
                authz_groups[authz] = []
            authz_groups[authz].append((src_role, effective_code, op))

    # 2) 去重 + 聚合 aliases (PRIMARY_WINS)
    for authz, group in authz_groups.items():
        if dedup and authz in seen_authz:
            continue
        seen_authz.add(authz)

        # PRIMARY_WINS: 选第一个 PRIMARY 的操作，否则取第一个
        primary_op = None
        secondary_ops = []
        for src_role, eff_code, op in group:
            if src_role == "PRIMARY" and primary_op is None:
                primary_op = op
            else:
                secondary_ops.append((eff_code, op))
        winner_op = primary_op if primary_op is not None else group[0][2]

        # V2.1: act_aliases 仅包含 kebab-case actionPath，供 ApiUrlBoExtractor 反向匹配 URL。
        # RuntimeLookupService 已改为仅匹配 operations[].code，不再消费 aliases。
        aliases = []
        CRUD_KINDS = {"CREATE", "READ", "UPDATE", "DELETE"}
        for _, _, op in group:
            ap = op.get("actionPath", "")
            if ap:
                alias = ap
                if alias not in aliases:
                    aliases.append(alias)
            elif op.get("operationKind") not in CRUD_KINDS:
                alias = op["code"].replace('_', '-').lower()
                if alias not in aliases:
                    aliases.append(alias)

        new_op = {
            "code": authz,
            "name": winner_op.get("name", winner_op["code"]),
            "scope": scope_map.get(winner_op.get("scope", "BO"), winner_op.get("scope", "BO")),
            "act_aliases": ",".join(aliases),
        }
        if winner_op.get("primaryDataAction"):
            new_op["primaryDataAction"] = winner_op["primaryDataAction"]
        if winner_op.get("entityCode"):
            new_op["entityCode"] = winner_op["entityCode"]
        merged_ops.append(new_op)

    # 权限项
    perm_items = []
    seen_perm = set()
    for op in merged_ops:
        key = f"RES_DATA_BO + {target_bo_code}_bo_meta_id + {op['code']}"
        if key not in seen_perm:
            seen_perm.add(key)
            perm_items.append(key)

    total_attrs = sum(len(e["attributes"]) for e in merged_entities)

    return {
        "_gov_meta": {
            "description": f"PSP authz_bo_meta_model 表 schema_json 字段(merged)，bo_code='{target_bo_code}'，由 {len(sources)} 个 BO 合并",
            "target_table": "authz_bo_meta_model",
            "target_condition": f"bo_code = '{target_bo_code}'",
            "generated_from": f"merge-manifest: {merge_manifest['mergeCode']}",
            "schema_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "merge_manifest": merge_manifest["mergeCode"],
        },
        "schema_json": {"entities": merged_entities, "operations": merged_ops},
        "_sql": {
            "update_statement": f"UPDATE authz_bo_meta_model SET schema_json = '<JSON>', updated_by = 'governance', updated_at = NOW() WHERE bo_code = '{target_bo_code}' AND tenant_id = 'default' AND is_deleted = 0;",
            "verify_statement": f"SELECT id, bo_code, bo_name, adapter_type, resolver, data_domain_id, updated_at FROM authz_bo_meta_model WHERE bo_code = '{target_bo_code}' AND tenant_id = 'default' AND is_deleted = 0;",
            "expected_permission_items_after_publish": perm_items,
        },
    }


# ── 投影生成器映射 ─────────────────────────────────────────────
GENERATORS = {
    "authz_bo_meta_model": generate_authz_bo_meta_model,
    "api-contract": generate_api_contract,
    "authz_projection": generate_authz_projection,
    "ui-model": generate_ui_model,
    "merged-authz-bo-meta-model": generate_merged_authz_bo_meta_model,
}


def generate(bo_code: str, projection_type: str = DEFAULT_TYPE) -> dict:
    """从 schema-view.v2 生成指定类型的投影。

    Args:
        bo_code: 业务对象编码
        projection_type: 投影类型 (authz_bo_meta_model / api-contract / authz_projection / ui-model)

    Returns:
        生成的投影 dict
    """
    if projection_type not in GENERATORS:
        valid = ", ".join(GENERATORS.keys())
        print(f"❌ 未知投影类型: {projection_type}，有效值: {valid}")
        sys.exit(1)

    sv = load_schema_view(bo_code)
    return GENERATORS[projection_type](bo_code, sv)


def generate_auto_merges(requested_bos: set = None) -> dict:
    """扫描 merge-manifests/ 目录，对涉及的 BO 执行合并投影。

    在所有标准投影生成完成后调用此函数，将 PRIMARY + SECONDARY BO
    的 schema_view 按 merge manifest 定义合并为单一 authz_bo_meta_model。

    Args:
        requested_bos: 本次投影涉及的 BO 集合。为 None 时对所有 BO 检查。
                       只有 targetBoCode 在此集合中的 manifest 才会被处理。

    Returns:
        {"merged": [...], "skipped": [...], "errors": [...]}
    """
    manifests_dir = METADATA_DIR / "merge-manifests"
    if not manifests_dir.is_dir():
        return {"merged": [], "skipped": [], "errors": []}

    merged = []
    skipped = []
    errors = []

    for mf in sorted(manifests_dir.glob("*.merge-manifest.json")):
        try:
            manifest = load_merge_manifest(str(mf))
        except Exception as e:
            errors.append({"manifest": mf.name, "error": str(e)})
            continue

        target = manifest.get("targetBoCode", "")
        # 如果指定了 BO 集合，只处理 target 在集合中的 manifest
        if requested_bos is not None and target not in requested_bos:
            continue
        # 检查 target BO 的发布态是否存在
        if not (METADATA_DIR / "release-time" / target).exists():
            skipped.append({"targetBoCode": target, "reason": "发布态不存在"})
            continue

        # 验证所有来源 BO 的发布态都存在
        sources = manifest.get("sources", [])
        all_ready = True
        for src in sources:
            src_bo = src["boCode"]
            if not (METADATA_DIR / "release-time" / src_bo).exists():
                skipped.append({"targetBoCode": target, "reason": f"来源 BO '{src_bo}' 发布态不存在"})
                all_ready = False
                break
        if not all_ready:
            continue

        try:
            sv = load_schema_view(target)
            proj = generate_merged_authz_bo_meta_model(target, sv, manifest)
            proj_dir = METADATA_DIR / "projection-run-time" / target
            proj_dir.mkdir(parents=True, exist_ok=True)
            merged_cfg = PROJECTION_TYPES["merged-authz-bo-meta-model"]
            output_path = proj_dir / f"{target}.{merged_cfg['suffix']}"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(proj, f, indent=2, ensure_ascii=False)
            ops = proj["schema_json"]["operations"]
            ents = proj["schema_json"]["entities"]
            total_attrs = sum(len(e["attributes"]) for e in ents)
            print(f"🔀 {target} → projection-run-time/{target}/{output_path.name} (auto-merged)")
            print(f"   {len(ents)} 实体 · {total_attrs} 属性 · {len(ops)} 操作 · {len(proj['_sql']['expected_permission_items_after_publish'])} 权限项 (merged)")
            merged.append({
                "targetBoCode": target,
                "file": output_path.name,
                "entities": len(ents),
                "attributes": total_attrs,
                "operations": len(ops),
                "permissionItems": len(proj["_sql"]["expected_permission_items_after_publish"]),
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            errors.append({"targetBoCode": target, "manifest": mf.name, "error": str(e)})

    return {"merged": merged, "skipped": skipped, "errors": errors}


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="从 schema-view.v2 发布态生成多种投影产物",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="投影类型:\n  " + "\n  ".join(
            f"{k:25s} {v['name']} — {v['description']}" for k, v in PROJECTION_TYPES.items()
        ),
    )
    parser.add_argument("boCode", nargs="+", help="业务对象编码 (可多个)")
    parser.add_argument(
        "--type", "-t",
        default=DEFAULT_TYPE,
        choices=list(PROJECTION_TYPES.keys()),
        help=f"投影类型 (默认: {DEFAULT_TYPE})",
    )
    parser.add_argument(
        "--merge-manifest", "-m",
        default=None,
        help="merge manifest 文件路径（仅 --type merged-authz-bo-meta-model 时需要）",
    )

    args = parser.parse_args()
    ptype = args.type
    pcfg = PROJECTION_TYPES[ptype]
    suffix = pcfg["suffix"]

    # 手动指定了 --merge-manifest：仅执行合并投影，不自动扫描
    explicit_merge = bool(args.merge_manifest)
    # 是否需要自动扫描 merge-manifests（仅默认投影类型时启用）
    auto_merge = (ptype == "authz_bo_meta_model")

    requested_bos = set(args.boCode)
    success = 0

    # ── Phase 1: 标准投影 ──
    for bo_code in args.boCode:
        release_dir = METADATA_DIR / "release-time" / bo_code
        if not release_dir.exists():
            print(f"⚠ BO '{bo_code}' 发布态未生成，跳过 (请先运行 bo-publish-gen.py {bo_code})")
            continue

        try:
            if explicit_merge:
                manifest = load_merge_manifest(args.merge_manifest)
                sv = load_schema_view(bo_code)
                proj = generate_merged_authz_bo_meta_model(bo_code, sv, manifest)
            else:
                proj = generate(bo_code, ptype)
            proj_dir = METADATA_DIR / "projection-run-time" / bo_code
            proj_dir.mkdir(parents=True, exist_ok=True)
            output_path = proj_dir / f"{bo_code}.{suffix}"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(proj, f, indent=2, ensure_ascii=False)
            print(f"✅ {bo_code} → projection-run-time/{bo_code}/{output_path.name}")

            # 统计摘要
            if ptype == "authz_bo_meta_model":
                ops = proj["schema_json"]["operations"]
                ents = proj["schema_json"]["entities"]
                total_attrs = sum(len(e["attributes"]) for e in ents)
                print(f"   {len(ents)} 实体 · {total_attrs} 属性 · {len(ops)} 操作 · {len(proj['_sql']['expected_permission_items_after_publish'])} 权限项")
            elif ptype == "authz_projection":
                print(f"   {len(proj['attributes'])} 个资源属性")
            elif ptype == "ui-model":
                print(f"   列表 {len(proj['listView']['columns'])} 列")
            elif ptype == "api-contract":
                print(f"   聚合根策略 + {len(proj.get('entityApiPolicies', {}))} 个子实体策略")
            elif ptype == "merged-authz-bo-meta-model":
                ops = proj["schema_json"]["operations"]
                ents = proj["schema_json"]["entities"]
                total_attrs = sum(len(e["attributes"]) for e in ents)
                print(f"   {len(ents)} 实体 · {total_attrs} 属性 · {len(ops)} 操作 · {len(proj['_sql']['expected_permission_items_after_publish'])} 权限项 (merged)")
            success += 1
        except SystemExit:
            raise
        except Exception as e:
            print(f"❌ {bo_code}: {e}")
            import traceback
            traceback.print_exc()

    # ── Phase 2: 自动合并投影 ──
    # 仅在默认 authz_bo_meta_model 类型下，扫描 merge-manifests 目录，
    # 对本次投影中涉及的 BO 自动执行合并投影
    if auto_merge and not explicit_merge:
        result = generate_auto_merges(requested_bos)
        if result["merged"]:
            print(f"\n🔀 自动合并: {len(result['merged'])} 个 BO 的合并投影已生成")
        if result["skipped"]:
            for s in result["skipped"]:
                print(f"⚠ 跳过 {s['targetBoCode']}: {s['reason']}")
        if result["errors"]:
            for e in result["errors"]:
                print(f"❌ {e.get('targetBoCode', e.get('manifest', '?'))}: {e['error']}")

    if success == 0:
        print("\n💡 提示: 请先生成发布态 → python bo-publish-gen.py " + " ".join(args.boCode))
    else:
        print(f"\n🎉 {success}/{len(args.boCode)} BO 的 [{pcfg['name']}] 投影已生成")
