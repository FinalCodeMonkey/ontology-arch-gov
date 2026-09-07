#!/usr/bin/env python3
"""
BO 发布态生成器
从设计态 Fragment（MODEL / OPERATION / SECURITY / VALIDATION / VIEW / RULE）
合成为符合 bo-schema-view.v2.schema.json 的发布态完整快照。
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

TOOLS_DIR = Path(__file__).resolve().parent
METADATA_DIR = TOOLS_DIR.parent / "metadata"

# ── 默认值 ──────────────────────────────────────────────────────
DEFAULT_RESPONSE_WRAPPER = "ApiResponse"
DEFAULT_BATCH_RESULT_TYPE = "BatchResultDTO"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def merge_attribute(attr: dict, sec_map: dict, val_map: dict, view_map: dict) -> dict:
    """将 MODEL 属性与 SECURITY / VALIDATION / VIEW 片段合并。"""
    code = attr["code"]
    out = {
        "code": code,
        "name": attr.get("name", code),
        "type": attr.get("type", "STRING"),
        "isPk": attr.get("isPk", False),
        "fieldName": attr.get("fieldName", code),
        "columnName": attr.get("columnName", code),
        "semanticRole": attr.get("semanticRole", "NORMAL"),
        "filterable": attr.get("filterable", False),
    }

    # redundant: CROSS_BO_DISPLAY 属性仅冗余时显式写出
    if attr.get("redundant") is True:
        out["redundant"] = True

    # crossBoRef
    cr = attr.get("crossBoRef")
    if cr:
        out["crossBoRef"] = {
            "refBoCode": cr["refBoCode"],
            "refFieldCode": cr["refFieldCode"],
            "relationType": cr.get("relationType", "MANY_TO_ONE"),
        }
        if cr.get("displayFields"):
            out["crossBoRef"]["displayFields"] = [
                {
                    "refFieldCode": d["refFieldCode"],
                    "localCode": d["localCode"],
                    "displayRole": d.get("displayRole", "EXTRA"),
                }
                for d in cr["displayFields"]
            ]

    # SECURITY: fieldControl, privacyClass, reason
    fs = sec_map.get(code)
    if fs:
        out["fieldControl"] = fs.get("fieldControl", "OPEN")
        out["privacyClass"] = fs.get("privacyClass", "PUBLIC")
        out["reason"] = fs.get("reason", "")

    # VALIDATION
    v = val_map.get(code)
    if v:
        vr = {}
        if v.get("required") is not None:
            vr["required"] = v["required"]
        if v.get("min") is not None:
            vr["min"] = v["min"]
        if v.get("max") is not None:
            vr["max"] = v["max"]
        if v.get("pattern"):
            vr["pattern"] = v["pattern"]
        if v.get("enum"):
            vr["enum"] = v["enum"]
        if v.get("unique") is not None:
            vr["unique"] = v["unique"]
        if v.get("message"):
            vr["message"] = v["message"]
        if vr:
            out["validation"] = vr

        # conditionalEnum: VALIDATION fragment 的条件枚举，投影到发布态
        cond_enum = v.get("conditionalEnum") if v else None
        if cond_enum:
            out["validation"]["conditionalEnum"] = cond_enum

        # semanticMapping: VALIDATION fragment 的枚举字段语义映射，投影到发布态
        sem_map = v.get("semanticMapping") if v else None
        if sem_map:
            out["semanticMapping"] = sem_map

    # VIEW
    vw = view_map.get(code)
    if vw:
        out["view"] = {
            k: v
            for k, v in {
                "displayName": vw.get("displayName"),
                "sortable": vw.get("sortable"),
                "columnWidth": vw.get("columnWidth"),
                "format": vw.get("format"),
                "hidden": vw.get("hidden"),
                "order": vw.get("order"),
                "showInList": vw.get("showInList"),
                "showInDetail": vw.get("showInDetail"),
                "editableInForm": vw.get("editableInForm"),
                "instantValidate": vw.get("instantValidate"),
                "formType": vw.get("formType"),
                "placeholder": vw.get("placeholder"),
                "queryable": vw.get("queryable"),
                "queryOperatorOptions": vw.get("queryOperatorOptions"),
                "dataType": vw.get("dataType"),
                "exportable": vw.get("exportable"),
                "importable": vw.get("importable"),
                "disabled": vw.get("disabled"),
                "dictCode": vw.get("dictCode"),
                "refObject": vw.get("refObject"),
                "refField": vw.get("refField"),
            }.items()
            if v is not None
        }

    return out


def generate(bo_code: str) -> dict:
    """为指定 BO 生成发布态。"""
    frag_dir = METADATA_DIR / "design-time" / bo_code / "fragments"

    # 加载所有 Fragment
    model = load_json(frag_dir / f"{bo_code}-model.fragment.json")
    operation = load_json(frag_dir / f"{bo_code}-operation.fragment.json")
    security = load_json(frag_dir / f"{bo_code}-security.fragment.json")
    validation = load_json(frag_dir / f"{bo_code}-validation.fragment.json")
    view = load_json(frag_dir / f"{bo_code}-view.fragment.json")
    rule = load_json(frag_dir / f"{bo_code}-rule.fragment.json") if (frag_dir / f"{bo_code}-rule.fragment.json").exists() else None

    mc = model["content"]
    sc = security["content"]
    vc = validation["content"]
    wc = view["content"]

    # ── 顶层字段 ──────────────────────────────────────────────
    result = {
        "$schema": "https://authz.xbac/schemas/gov/bo-schema-view.v2.schema.json",
        "boCode": mc["boCode"],
        "boName": mc["boName"],
        "description": mc.get("description", ""),
        "schemaVersion": "2.0",
        "apiConfig": build_api_config(mc.get("apiConfig", {})),
        "boConfig": mc.get("boConfig", {}),
    }

    # listViewConfig
    lvc = wc.get("listViewConfig")
    if lvc:
        result["listViewConfig"] = lvc

    # ── 构建安全/校验/视图索引 ──────────────────────────────────
    sec_by_entity = {}
    for fs in sc.get("fieldSecurity", []):
        sec_by_entity.setdefault(fs["entityCode"], {})[fs["fieldCode"]] = fs

    val_by_entity = {}
    for v in vc.get("rules", []):
        val_by_entity.setdefault(v["entityCode"], {})[v["fieldCode"]] = v

    view_by_entity = {}
    for fv in wc.get("fieldViews", []):
        view_by_entity.setdefault(fv["entityCode"], {})[fv["fieldCode"]] = fv

    row_sec = sc.get("rowSecurity", {})

    # ── 构建实体 ──────────────────────────────────────────────
    entities = []
    for ent in mc.get("entities", []):
        ec = ent["code"]
        sec_map = sec_by_entity.get(ec, {})
        val_map = val_by_entity.get(ec, {})
        view_map = view_by_entity.get(ec, {})

        attributes = [merge_attribute(a, sec_map, val_map, view_map) for a in ent.get("attributes", [])]

        entity_out = {
            "code": ec,
            "name": ent["name"],
            "isPrimary": ent.get("isPrimary", False),
            "aggregateRole": ent.get("aggregateRole", "ROOT"),
            "tableName": ent.get("tableName", ""),
            "attributes": attributes,
        }

        # rowLevelRuleEntries
        entries = row_sec.get("entriesByEntity", {}).get(ec, [])
        if entries:
            entity_out["rowLevelRuleEntries"] = entries

        # rowFallbackScope
        fallback = row_sec.get("fallbackScope")
        if fallback:
            entity_out["rowFallbackScope"] = fallback

        # 子实体专用
        if ent.get("parentEntityCode"):
            entity_out["parentEntityCode"] = ent["parentEntityCode"]
        if ent.get("parentRefField"):
            entity_out["parentRefField"] = ent["parentRefField"]
        if ent.get("routeSegment"):
            entity_out["routeSegment"] = ent["routeSegment"]
        if ent.get("cascadeDelete") is not None:
            entity_out["cascadeDelete"] = ent["cascadeDelete"]
        if ent.get("readOnly") is not None:
            entity_out["readOnly"] = ent["readOnly"]
        if ent.get("entityApiPolicy"):
            entity_out["entityApiPolicy"] = ent["entityApiPolicy"]
        if ent.get("policyDerivedFields"):
            entity_out["policyDerivedFields"] = ent["policyDerivedFields"]

        entities.append(entity_out)

    result["entities"] = entities

    # ── operations ────────────────────────────────────────────
    ops = list(operation.get("content", {}).get("operations", []))
    existing_codes = {op["code"] for op in ops}

    # 根据 apiConfig 自动补齐标准 CRUD（标记 derived）
    api = mc.get("apiConfig", {})
    policy = api.get("aggregateApiPolicy", {}) if api else {}

    def add_derived(code, name, kind, authz, source, scope="BO", entity=None, primary_data_action=None):
        if code not in existing_codes:
            op = {
                "code": code,
                "name": name,
                "scope": scope,
                "operationKind": kind,
                "primaryDataAction": primary_data_action or {
                    "CREATE": "CREATE",
                    "UPDATE": "UPDATE",
                    "DELETE": "DELETE",
                }.get(kind, "READ"),
                "authzAction": authz,
                "derived": True,
                "derivedFrom": source,
            }
            if entity:
                op["entityCode"] = entity
            ops.append(op)
            existing_codes.add(code)

    def entity_operation_exists(entity_code, kind):
        return any(
            op.get("scope") == "ENTITY"
            and op.get("entityCode") == entity_code
            and op.get("operationKind") == kind
            for op in ops
        )

    def operation_code_suffix(code):
        return code.upper().replace("-", "_")

    if api.get("searchEnabled"):
        add_derived("LIST", "列表查询", "CUSTOM", "LIST", "apiConfig.searchEnabled", primary_data_action="READ")
        add_derived("SEARCH", "高级搜索", "CUSTOM", "LIST", "apiConfig.searchEnabled", primary_data_action="READ")

    if policy.get("readScope"):
        add_derived("READ", "查看详情", "CUSTOM", "READ", "apiConfig.aggregateApiPolicy.readScope", primary_data_action="READ")

    if policy.get("createScope") and "CREATE" not in existing_codes:
        add_derived("CREATE", "创建", "CREATE", "CREATE", "apiConfig.aggregateApiPolicy.createScope")

    if policy.get("updateScope") and "UPDATE" not in existing_codes:
        add_derived("UPDATE", "更新", "UPDATE", "UPDATE", "apiConfig.aggregateApiPolicy.updateScope")

    if policy.get("deleteScope") and "DELETE" not in existing_codes:
        add_derived("DELETE", "删除", "DELETE", "DELETE", "apiConfig.aggregateApiPolicy.deleteScope")

    # 子实体的标准 CRUD
    for ent in mc.get("entities", []):
        ep = ent.get("entityApiPolicy")
        if not ep:
            continue
        ec = ent["code"]
        suffix = operation_code_suffix(ec)

        if ep.get("listProjectionScope"):
            code = f"LIST_{suffix}"
            add_derived(
                code, f"查询{ent['name']}列表", "CUSTOM", code,
                f"entityApiPolicy({ec}).listProjectionScope", "ENTITY", ec, "READ"
            )

        if ep.get("readScope"):
            code = f"READ_{suffix}"
            add_derived(
                code, f"查看{ent['name']}详情", "CUSTOM", code,
                f"entityApiPolicy({ec}).readScope", "ENTITY", ec, "READ"
            )

        if ep.get("createScope") and not entity_operation_exists(ec, "CREATE"):
            code = f"CREATE_{suffix}"
            add_derived(
                code, f"新建{ent['name']}", "CREATE", code,
                f"entityApiPolicy({ec}).createScope", "ENTITY", ec
            )

        if ep.get("updateScope") and not entity_operation_exists(ec, "UPDATE"):
            code = f"UPDATE_{suffix}"
            add_derived(
                code, f"更新{ent['name']}", "UPDATE", code,
                f"entityApiPolicy({ec}).updateScope", "ENTITY", ec
            )

        if ep.get("deleteScope") and not entity_operation_exists(ec, "DELETE"):
            code = f"DELETE_{suffix}"
            add_derived(
                code, f"删除{ent['name']}", "DELETE", code,
                f"entityApiPolicy({ec}).deleteScope", "ENTITY", ec
            )

    result["operations"] = ops

    # ── rules ────────────────────────────────────────────────
    if rule and rule.get("content", {}).get("rules"):
        result["rules"] = []
        for r in rule["content"]["rules"]:
            rule_out = {
                "code": r["code"],
                "name": r["name"],
                "ruleType": r.get("ruleType", "CONSISTENCY"),
                "scope": r.get("scope", "BO"),
                "trigger": r.get("trigger", "BEFORE_OPERATION"),
                "severity": r.get("severity", "ERROR"),
                "message": r.get("message", ""),
                "description": r.get("description", ""),
            }
            # 按需投影可选字段
            if r.get("entityCode"):
                rule_out["entityCode"] = r["entityCode"]
            if r.get("fieldCode"):
                rule_out["fieldCode"] = r["fieldCode"]
            if r.get("operationCode"):
                rule_out["operationCode"] = r["operationCode"]
            if r.get("expression"):
                rule_out["expression"] = r["expression"]
            if r.get("exprAst"):
                rule_out["exprAst"] = r["exprAst"]
            if r.get("polarity"):
                rule_out["polarity"] = r["polarity"]
            if r.get("crossBoRef"):
                rule_out["crossBoRef"] = {
                    "refBoCode": r["crossBoRef"]["refBoCode"],
                    "refFieldCode": r["crossBoRef"]["refFieldCode"],
                    "localEntityCode": r["crossBoRef"]["localEntityCode"],
                    "localFieldCode": r["crossBoRef"]["localFieldCode"],
                }
            result["rules"].append(rule_out)

    # ── governance ────────────────────────────────────────────
    result["governance"] = {
        "sourceFragmentVersion": model.get("draftVersion", 1),
        "releaseVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "generatedBy": "bo-publish-gen.py",
    }

    return result


def build_api_config(api: dict) -> dict:
    """构建 apiConfig，补齐必填字段。"""
    out = {
        "resourcePath": api.get("resourcePath", ""),
        "idField": api.get("idField", "id"),
        "idType": api.get("idType", "LONG"),
        "responseWrapper": DEFAULT_RESPONSE_WRAPPER,
        "batchResultType": DEFAULT_BATCH_RESULT_TYPE,
    }
    if api.get("businessKeyField"):
        out["businessKeyField"] = api["businessKeyField"]
    if api.get("aggregateApiPolicy"):
        out["aggregateApiPolicy"] = api["aggregateApiPolicy"]
    if api.get("searchEnabled") is not None:
        out["searchEnabled"] = api["searchEnabled"]
    if api.get("batchEnabled") is not None:
        out["batchEnabled"] = api["batchEnabled"]
    return out


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bo-publish-gen.py <boCode> [boCode ...]")
        print("Example: python bo-publish-gen.py customers scenes")
        sys.exit(1)

    for bo_code in sys.argv[1:]:
        design_dir = METADATA_DIR / "design-time" / bo_code
        if not design_dir.exists():
            print(f"[WARN] BO '{bo_code}' not found in metadata/design-time/, skipping")
            continue

        try:
            published = generate(bo_code)
            release_dir = METADATA_DIR / "release-time" / bo_code
            release_dir.mkdir(parents=True, exist_ok=True)
            output_path = release_dir / f"{bo_code}.schema-view.v2.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(published, f, indent=2, ensure_ascii=False)
            print(f"[OK] {bo_code} -> {output_path.name}")
        except Exception as e:
            print(f"[ERR] {bo_code}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
