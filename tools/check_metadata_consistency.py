#!/usr/bin/env python3
"""
BO 元数据设计态一致性校验工具
逐项检查 metadata/design-time 下所有 BO 的 6 个 Fragment 是否符合 schema 定义
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import jsonschema
from jsonschema import Draft202012Validator

sys.stdout.reconfigure(encoding='utf-8')

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
SCHEMA_DIR = BASE / "schemas" / "design-time"
FRAGMENT_SCHEMA_DIR = SCHEMA_DIR / "fragments"
META_DIR = BASE / "metadata" / "design-time"

# ---------------------------------------------------------------------------
# 加载所有 Schema
# ---------------------------------------------------------------------------
def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

# 信封 schema (bo-meta-fragment.schema.json)
envelope_schema = load_json(SCHEMA_DIR / "bo-meta-fragment.schema.json")

# 子 fragment 独立 schemas
sub_schemas = {
    "MODEL":        load_json(FRAGMENT_SCHEMA_DIR / "model-fragment.schema.json"),
    "OPERATION":    load_json(FRAGMENT_SCHEMA_DIR / "operation-fragment.schema.json"),
    "RULE":         load_json(FRAGMENT_SCHEMA_DIR / "rule-fragment.schema.json"),
    "SECURITY":     load_json(FRAGMENT_SCHEMA_DIR / "security-fragment.schema.json"),
    "VALIDATION":   load_json(FRAGMENT_SCHEMA_DIR / "validation-fragment.schema.json"),
    "VIEW":         load_json(FRAGMENT_SCHEMA_DIR / "view-fragment.schema.json"),
    "LINK":         load_json(FRAGMENT_SCHEMA_DIR / "link-fragment.schema.json"),
    "DERIVATION":   load_json(FRAGMENT_SCHEMA_DIR / "derivation-fragment.schema.json"),
    "TEMPORAL":     load_json(FRAGMENT_SCHEMA_DIR / "temporal-fragment.schema.json"),
    "ACTION_CHAIN": load_json(FRAGMENT_SCHEMA_DIR / "action-chain-fragment.schema.json"),
}

# 构建全量 schemaStore（用于 envelope 内部的 $ref 引用）
# envelope 内部通过 allOf/if/then 引用 fragments/*.schema.json 和 fragments/*.schema.v3.json
schema_store = {}
for f in FRAGMENT_SCHEMA_DIR.glob("*.schema*.json"):
    s = load_json(f)
    schema_store[s.get("$id", f.name)] = s

# 同时也加入 envelope 自身
schema_store[envelope_schema.get("$id", "envelope")] = envelope_schema

# ---------------------------------------------------------------------------
# 收集所有 BO
# ---------------------------------------------------------------------------
BO_LIST = sorted([
    d.name for d in META_DIR.iterdir()
    if d.is_dir() and (d / "bo-info.json").exists() and not d.name.startswith("_")
])

print(f"发现 {len(BO_LIST)} 个 BO: {', '.join(BO_LIST)}")

# ---------------------------------------------------------------------------
# 错误收集器
# ---------------------------------------------------------------------------
class ErrorCollector:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def add(self, bo, fragment, check, msg, level="ERROR"):
        item = f"[{level}] {bo}/{fragment}: {check} — {msg}"
        if level == "WARN":
            self.warnings.append(item)
        else:
            self.errors.append(item)

    def summary(self):
        print("\n" + "=" * 80)
        print(f"  校验完成：{len(self.errors)} 个错误，{len(self.warnings)} 个警告")
        print("=" * 80)
        if self.errors:
            print("\n[ERR] 错误列表：")
            for e in self.errors:
                print(f"  {e}")
        if self.warnings:
            print(f"\n[WARN] 警告列表：")
            for w in self.warnings:
                print(f"  {w}")
        return len(self.errors)

ec = ErrorCollector()

# ===========================================================================
# 阶段 1: JSON 解析 + 信封 Schema 校验
# ===========================================================================
print("\n" + "=" * 80)
print("阶段 1: 信封 Schema 校验 + 子 fragment Schema 校验")
print("=" * 80)

all_fragments = {}  # bo_code -> {metaType -> (envelope_obj, content_obj)}

for bo in BO_LIST:
    all_fragments[bo] = {}
    bo_dir = META_DIR / bo
    bo_info_path = bo_dir / "bo-info.json"
    frag_dir = bo_dir / "fragments"

    # 检查 bo-info.json
    if bo_info_path.exists():
        try:
            bo_info = load_json(bo_info_path)
            # 校验 boCode 一致性
            if bo_info.get("boCode") != bo:
                ec.add(bo, "bo-info.json", "boCode", f"bo-info.json 中 boCode={bo_info.get('boCode')} 与目录名 {bo} 不一致")
        except json.JSONDecodeError as e:
            ec.add(bo, "bo-info.json", "JSON解析", str(e))
    else:
        ec.add(bo, "bo-info.json", "缺失文件", "bo-info.json 不存在")

    # 检查 6 个 fragment 文件
    for meta_type in ["MODEL", "OPERATION", "RULE", "SECURITY", "VALIDATION", "VIEW"]:
        file_expected = f"{bo}-{meta_type.lower()}.fragment.json"
        fpath = frag_dir / file_expected

        if not fpath.exists():
            ec.add(bo, file_expected, "缺失文件", f"Fragment 文件不存在")
            continue

        try:
            data = load_json(fpath)
        except json.JSONDecodeError as e:
            ec.add(bo, file_expected, "JSON解析", str(e))
            continue

        # 1a. 校验 envelope 结构
        try:
            resolver = jsonschema.RefResolver.from_schema(envelope_schema, store=schema_store)
            validator = Draft202012Validator(envelope_schema, resolver=resolver)
            errors = list(validator.iter_errors(data))
            for err in errors:
                ec.add(bo, file_expected, "EnvelopeSchema",
                       f"{'.'.join(str(p) for p in err.absolute_path)}: {err.message}")
        except Exception as e:
            ec.add(bo, file_expected, "EnvelopeValidation", str(e))

        # 1b. 校验 content 对子 schema
        content = data.get("content", {})
        if meta_type in sub_schemas:
            sub_schema = sub_schemas[meta_type]
            try:
                # 如果 sub_schema 有 $ref，需要用 resolver；这里直接校验 content
                s_resolver = jsonschema.RefResolver.from_schema(sub_schema, store=schema_store)
                s_validator = Draft202012Validator(sub_schema, resolver=s_resolver)
                for err in s_validator.iter_errors(content):
                    ec.add(bo, file_expected, "ContentSchema",
                           f"{'.'.join(str(p) for p in err.absolute_path)}: {err.message}")
            except Exception as e:
                ec.add(bo, file_expected, "ContentValidation", str(e))

        # 1c. 检查 envelope 字段与 content 一致性
        if data.get("boCode") != content.get("boCode", data.get("boCode")):
            ec.add(bo, file_expected, "boCode一致性",
                   f"envelope.boCode={data.get('boCode')} ≠ content.boCode={content.get('boCode')}")

        if data.get("boCode") != bo:
            ec.add(bo, file_expected, "boCode一致性",
                   f"envelope.boCode={data.get('boCode')} 与目录名 {bo} 不一致")

        all_fragments[bo][meta_type] = (data, content)

# ===========================================================================
# 阶段 2: 内部交叉引用校验（跨 Fragment 一致性）
# ===========================================================================
print("\n" + "=" * 80)
print("阶段 2: 跨 Fragment 内部引用一致性校验")
print("=" * 80)

for bo in BO_LIST:
    frags = all_fragments.get(bo, {})
    if "MODEL" not in frags:
        continue

    _, model = frags["MODEL"]
    entities = model.get("entities", [])

    # 构建 entity → 信息索引
    entity_index = {}
    root_entity = None
    for ent in entities:
        entity_index[ent["code"]] = ent
        if ent.get("isPrimary") and ent.get("aggregateRole") == "ROOT":
            root_entity = ent

    # 收集所有 attribute code → (entity_code, attr_obj) 映射
    attr_index = {}  # (entityCode, fieldCode) → attr_obj
    for ent in entities:
        for attr in ent.get("attributes", []):
            attr_index[(ent["code"], attr["code"])] = attr

    # Root entity attributes for quick check
    root_attrs = {}
    if root_entity:
        root_attrs = {a["code"]: a for a in root_entity.get("attributes", [])}

    # --- 2a. 检查 ROOT entity 存在性 ---
    if root_entity is None:
        ec.add(bo, "MODEL", "ROOT实体",
               "未找到 isPrimary=true 且 aggregateRole=ROOT 的实体")

    # --- 2b. apiConfig 引用检查 ---
    ac = model.get("apiConfig", {})
    id_field = ac.get("idField", "")
    if id_field and root_attrs and id_field not in root_attrs:
        ec.add(bo, "MODEL", "apiConfig.idField",
               f"idField={id_field} 在 ROOT entity 的 attributes 中不存在")
    if id_field and root_attrs and root_attrs.get(id_field, {}).get("isPk") is not True:
        ec.add(bo, "MODEL", "apiConfig.idField", f"idField={id_field} 未标记 isPk=true")

    bkf = ac.get("businessKeyField", "")
    if bkf and root_attrs and bkf not in root_attrs:
        ec.add(bo, "MODEL", "apiConfig.businessKeyField",
               f"businessKeyField={bkf} 在 ROOT entity 的 attributes 中不存在")

    # apiConfig.resourcePath 校验
    rp = ac.get("resourcePath", "")
    if rp and rp != f"/{bo}":
        ec.add(bo, "MODEL", "apiConfig.resourcePath",
               f"resourcePath={rp} 应与 boCode 一致: /{bo}")

    # --- 2c. boConfig 引用检查 ---
    bc = model.get("boConfig", {})
    name_field = bc.get("nameField", "")
    if name_field and root_attrs and name_field not in root_attrs:
        ec.add(bo, "MODEL", "boConfig.nameField",
               f"nameField={name_field} 在 ROOT entity 的 attributes 中不存在")

    sf = bc.get("statusField", "")
    if sf and root_attrs and sf not in root_attrs:
        ec.add(bo, "MODEL", "boConfig.statusField",
               f"statusField={sf} 在 ROOT entity 的 attributes 中不存在")

    ds = bc.get("defaultSort", {})
    if ds.get("field") and root_attrs:
        if ds["field"] not in root_attrs:
            ec.add(bo, "MODEL", "boConfig.defaultSort.field",
                   f"defaultSort.field={ds['field']} 在 ROOT entity 的 attributes 中不存在")

    # --- 2d. entities 结构检查 ---
    primary_count = sum(1 for ent in entities if ent.get("isPrimary"))
    if primary_count != 1:
        ec.add(bo, "MODEL", "entities.isPrimary",
               f"应有且仅有一个 isPrimary=true 的实体，当前: {primary_count}")

    # entity.code 唯一性
    entity_codes = [ent["code"] for ent in entities]
    dup_codes = [c for c in entity_codes if entity_codes.count(c) > 1]
    if dup_codes:
        ec.add(bo, "MODEL", "entities.code唯一性",
               f"重复的 entity.code: {list(set(dup_codes))}")

    # attribute.code 唯一性（每个 entity 内）
    for ent in entities:
        attr_codes = [a["code"] for a in ent.get("attributes", [])]
        dup_attrs = [c for c in attr_codes if attr_codes.count(c) > 1]
        if dup_attrs:
            ec.add(bo, "MODEL", f"entity.{ent['code']}.attributes唯一性",
                   f"重复的 attribute.code: {list(set(dup_attrs))}")

    # parentEntityCode 引用检查
    for ent in entities:
        pec = ent.get("parentEntityCode", "")
        if pec and pec not in entity_index:
            ec.add(bo, "MODEL", f"entity.{ent['code']}.parentEntityCode",
                   f"parentEntityCode={pec} 指向不存在的实体")

    # parentRefField 检查 (子实体的 parentRefField 必须在子实体自身 attributes 中)
    for ent in entities:
        if ent.get("aggregateRole") == "SUB_ENTITY":
            prf = ent.get("parentRefField", "")
            own_attrs = {a["code"] for a in ent.get("attributes", [])}
            if prf and prf not in own_attrs:
                ec.add(bo, "MODEL", f"entity.{ent['code']}.parentRefField",
                       f"parentRefField={prf} 不在当前子实体自己的 attributes 中")

    # 每个 entity 的 PK 必须为 "id"
    for ent in entities:
        pk_attrs = [a for a in ent.get("attributes", []) if a.get("isPk")]
        for a in pk_attrs:
            if a["code"] != "id":
                ec.add(bo, "MODEL", f"entity.{ent['code']}.PK",
                       f"PK attribute code 必须为 'id'，当前: {a['code']}")

    # 每个 entity 必须有且仅有一个 isPk=true 的属性
    for ent in entities:
        pk_count = sum(1 for a in ent.get("attributes", []) if a.get("isPk"))
        if pk_count != 1:
            ec.add(bo, "MODEL", f"entity.{ent['code']}.PK数量",
                   f"应有且仅有一个 isPk=true 的属性，当前: {pk_count}")

    # --- 2e. CROSS_BO_REF / CROSS_BO_DISPLAY 引用检查 ---
    # semanticRole=CROSS_BO_REF → crossBoRef 必填 (schema 已强制)
    # redundant=true 只允许在 CROSS_BO_DISPLAY 上
    for ent in entities:
        for attr in ent.get("attributes", []):
            if attr.get("redundant") and attr.get("semanticRole") != "CROSS_BO_DISPLAY":
                ec.add(bo, "MODEL", f"entity.{ent['code']}.{attr['code']}.redundant",
                       f"redundant=true 只允许在 semanticRole=CROSS_BO_DISPLAY 上，当前: {attr.get('semanticRole')}")

    # CROSS_BO_DISPLAY 必须被某个 CROSS_BO_REF 的 displayFields 引用
    # Collect all display field localCodes
    display_field_refs = set()  # (entityCode, localCode)
    for ent in entities:
        for attr in ent.get("attributes", []):
            if attr.get("semanticRole") == "CROSS_BO_REF" and "crossBoRef" in attr:
                for df in attr["crossBoRef"].get("displayFields", []):
                    display_field_refs.add((ent["code"], df["localCode"]))

    # Check CROSS_BO_DISPLAY attributes are referenced
    for ent in entities:
        for attr in ent.get("attributes", []):
            if attr.get("semanticRole") == "CROSS_BO_DISPLAY":
                if (ent["code"], attr["code"]) not in display_field_refs:
                    ec.add(bo, "MODEL", f"entity.{ent['code']}.{attr['code']}.CROSS_BO_DISPLAY",
                           f"CROSS_BO_DISPLAY 属性未被任何 CROSS_BO_REF 的 displayFields 引用（孤立属性）")

    # created_by / updated_by 不能标记为 CROSS_BO_REF
    for ent in entities:
        for attr in ent.get("attributes", []):
            if attr.get("semanticRole") == "CROSS_BO_REF" and attr["code"] in ("created_by", "updated_by"):
                ec.add(bo, "MODEL", f"entity.{ent['code']}.{attr['code']}.semanticRole",
                       f"created_by/updated_by 是基础设施审计字段，MUST NOT 标记为 CROSS_BO_REF")

    # crossBoRef.refFieldCode MUST 是目标 BO 的 PK（id）或 businessKeyField
    # 无法在这里完全校验（需要跨 BO 引用），但可检查本 BO 内的
    for ent in entities:
        for attr in ent.get("attributes", []):
            cr = attr.get("crossBoRef", {})
            if cr:
                rfc = cr.get("refFieldCode", "")
                # 只校验引用了自己的情况
                if cr.get("refBoCode") == bo:
                    target_entity_code = cr.get("refEntityCode") or (root_entity["code"] if root_entity else None)
                    if target_entity_code and target_entity_code in entity_index:
                        target_ent = entity_index[target_entity_code]
                        target_attrs = {a["code"]: a for a in target_ent.get("attributes", [])}
                        if rfc in target_attrs:
                            ta = target_attrs[rfc]
                            if not ta.get("isPk") and rfc != (model.get("apiConfig", {}).get("businessKeyField", "")):
                                ec.add(bo, "MODEL", f"entity.{ent['code']}.{attr['code']}.crossBoRef.refFieldCode",
                                       f"refFieldCode={rfc} 必须引用目标 BO 的 PK(id) 或 businessKeyField")

    # --- 2f. aggregateApiPolicy.detailEmbedEntities 引用检查 ---
    ap = ac.get("aggregateApiPolicy", {})
    for dee in ap.get("detailEmbedEntities", []):
        if dee not in entity_index:
            ec.add(bo, "MODEL", f"aggregateApiPolicy.detailEmbedEntities",
                   f"detailEmbedEntities={dee} 在 entities 中不存在")

    # entityApiPolicy.detailEmbedEntities 引用检查
    for ent in entities:
        eap = ent.get("entityApiPolicy", {})
        for dee in eap.get("detailEmbedEntities", []):
            if dee not in entity_index:
                ec.add(bo, "MODEL", f"entity.{ent['code']}.entityApiPolicy.detailEmbedEntities",
                       f"detailEmbedEntities={dee} 在 entities 中不存在")

    # --- VIEW fragment 检查 ---
    if "VIEW" in frags:
        _, view = frags["VIEW"]
        for fv in view.get("fieldViews", []):
            ent_code = fv.get("entityCode", "")
            fld_code = fv.get("fieldCode", "")
            key = (ent_code, fld_code)
            has_computed = "computedField" in fv
            if key not in attr_index and not has_computed:
                ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}",
                       f"引用的属性在 MODEL entities 中不存在")

            # formType=OBJECT_SELECT 检查 refObject
            if fv.get("formType") == "OBJECT_SELECT":
                ro = fv.get("refObject", "")
                if not ro:
                    ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}.refObject",
                           "formType=OBJECT_SELECT 时 refObject 必须配置")

            # formType=SELECT/MULTI_SELECT 检查 dictCode
            if fv.get("formType") in ("SELECT", "MULTI_SELECT"):
                dc = fv.get("dictCode", "")
                if not dc:
                    ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}.dictCode",
                           f"formType={fv['formType']} 时 dictCode 必须配置")

            # exportable 与 SECURITY HIDDEN 的跨 fragment 检查
            if "SECURITY" in frags:
                _, sec = frags["SECURITY"]
                for fs_item in sec.get("fieldSecurity", []):
                    if fs_item.get("entityCode") == ent_code and fs_item.get("fieldCode") == fld_code:
                        if fs_item.get("fieldControl") == "HIDDEN" and fv.get("exportable") is True:
                            ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}.exportable",
                                   "SECURITY 中 fieldControl=HIDDEN 但 VIEW 中 exportable=true")

        # fieldViews 的 (entityCode, fieldCode) 唯一性
        seen_fv = set()
        for fv in view.get("fieldViews", []):
            key = (fv["entityCode"], fv["fieldCode"])
            if key in seen_fv:
                ec.add(bo, "VIEW", f"fieldViews.{key[0]}.{key[1]}",
                       "fieldViews 中 (entityCode, fieldCode) 组合重复")
            seen_fv.add(key)

        # --- VIEW dataType vs MODEL type 兼容性校验 ---
        # MODEL 物理类型 → VIEW dataType 允许值的兼容矩阵
        MODEL_VIEW_TYPE_COMPAT = {
            "STRING":    {"string", "enum"},
            "TEXT":      {"string"},
            "CHAR":      {"string"},
            "LONG":      {"integer", "reference"},
            "BIGINT":    {"integer", "reference"},
            "INT":       {"integer"},
            "INTEGER":   {"integer"},
            "SMALLINT":  {"integer"},
            "DECIMAL":   {"decimal"},
            "NUMERIC":   {"decimal"},
            "FLOAT":     {"decimal"},
            "DOUBLE":    {"decimal"},
            "DATE":      {"date"},
            "DATETIME":  {"datetime"},
            "TIMESTAMP": {"datetime"},
            "BOOLEAN":   {"boolean"},
            "BOOL":      {"boolean"},
        }
        for fv in view.get("fieldViews", []):
            ent_code = fv.get("entityCode", "")
            fld_code = fv.get("fieldCode", "")
            view_dt  = fv.get("dataType")

            # dataType vs MODEL.type 兼容性
            if view_dt and (ent_code, fld_code) in attr_index:
                model_type = attr_index[(ent_code, fld_code)].get("type", "").upper()
                allowed = MODEL_VIEW_TYPE_COMPAT.get(model_type)
                if allowed is not None and view_dt not in allowed:
                    # 豁免：LONG/BIGINT 类型字段 VIEW.dataType="string" 是前端精度保护（JS Number 安全整数限制）
                    # 详见 copilot-instructions.md §3.7 前后端 ID 传递约束
                    if view_dt == "string" and model_type in ("LONG", "BIGINT"):
                        pass  # 合法豁免
                    else:
                        ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}.dataType",
                               f"VIEW.dataType={view_dt} 与 MODEL.type={model_type} 不兼容。"
                               f"{model_type} 允许的 VIEW dataType: {sorted(allowed)}")

            # queryable=true 时必须声明 dataType（schema 已强制，此处补充友好提示）
            if fv.get("queryable") is True and not view_dt:
                ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}.dataType",
                       "queryable=true 时必须声明 dataType，请与 MODEL.type 对齐")

            # queryOperatorOptions label 非空 & 含中文校验
            for op_item in fv.get("queryOperatorOptions", []):
                label = op_item.get("label", "")
                val   = op_item.get("value", "")
                if not label:
                    ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}.queryOperatorOptions",
                           f"操作符 value={val} 的 label 为空", level="WARN")
                elif not re.search(r"[\u4e00-\u9fff]", label):
                    ec.add(bo, "VIEW", f"fieldViews.{ent_code}.{fld_code}.queryOperatorOptions",
                           f"操作符 value={val} 的 label='{label}' 不含中文字符，建议使用中文标签",
                           level="WARN")

    # --- OPERATION fragment 检查 ---
    if "OPERATION" in frags:
        _, op = frags["OPERATION"]
        seen_op_codes = set()
        for oper in op.get("operations", []):
            op_code = oper.get("code")
            if op_code in seen_op_codes:
                ec.add(bo, "OPERATION", f"operation.{op_code}", "operation.code 重复")
            seen_op_codes.add(op_code)

            if oper.get("scope") == "ENTITY":
                ec2 = oper.get("entityCode", "")
                if ec2 and ec2 not in entity_index:
                    ec.add(bo, "OPERATION", f"operation.{op_code}.entityCode",
                           f"entityCode={ec2} 在 MODEL entities 中不存在")

            # CUSTOM + API_CALL/CONFIRM_THEN_API → actionPath 必填 (schema 已强制)
            # httpMethod 检查 (实际实现用 POST 替代 PATCH)
            # 不报错，因为 schema 允许 PATCH

    # --- VALIDATION fragment 检查 ---
    if "VALIDATION" in frags:
        _, val = frags["VALIDATION"]
        seen_val_keys = set()
        for rule in val.get("rules", []):
            ent_code = rule.get("entityCode", "")
            fld_code = rule.get("fieldCode", "")
            key = (ent_code, fld_code)
            if key in seen_val_keys:
                ec.add(bo, "VALIDATION", f"rules.{ent_code}.{fld_code}",
                       "(entityCode, fieldCode) 组合重复")
            seen_val_keys.add(key)

            if key not in attr_index:
                ec.add(bo, "VALIDATION", f"rules.{ent_code}.{fld_code}",
                       "引用的属性在 MODEL entities 中不存在")

            # min <= max 检查
            if "min" in rule and "max" in rule and rule["min"] is not None and rule["max"] is not None:
                if rule["min"] > rule["max"]:
                    ec.add(bo, "VALIDATION", f"rules.{ent_code}.{fld_code}",
                           f"min({rule['min']}) > max({rule['max']})")

    # --- SECURITY fragment 检查 ---
    if "SECURITY" in frags:
        _, sec = frags["SECURITY"]

        # fieldSecurity 引用检查
        seen_fs = set()
        for fs_item in sec.get("fieldSecurity", []):
            ent_code = fs_item.get("entityCode", "")
            fld_code = fs_item.get("fieldCode", "")
            key = (ent_code, fld_code)
            if key in seen_fs:
                ec.add(bo, "SECURITY", f"fieldSecurity.{ent_code}.{fld_code}",
                       "(entityCode, fieldCode) 组合重复")
            seen_fs.add(key)

            if key not in attr_index:
                ec.add(bo, "SECURITY", f"fieldSecurity.{ent_code}.{fld_code}",
                       "引用的属性在 MODEL entities 中不存在")

        # rowSecurity.entriesByEntity key 检查
        for row_key, row_fields in sec.get("rowSecurity", {}).get("entriesByEntity", {}).items():
            if row_key not in entity_index:
                ec.add(bo, "SECURITY", f"rowSecurity.entriesByEntity.{row_key}",
                       f"实体 code={row_key} 在 MODEL entities 中不存在")
            else:
                row_ent_attrs = {a["code"] for a in entity_index[row_key].get("attributes", [])}
                for rf in row_fields:
                    if rf not in row_ent_attrs:
                        ec.add(bo, "SECURITY", f"rowSecurity.entriesByEntity.{row_key}",
                               f"字段 {rf} 在 entity.{row_key} 的 attributes 中不存在")

        # authzProjection.attributes 引用检查
        for attr in sec.get("authzProjection", {}).get("attributes", []):
            src = attr.get("source", {})
            ec2 = src.get("entityCode", "")
            fc = src.get("fieldCode", "")
            if (ec2, fc) not in attr_index:
                ec.add(bo, "SECURITY", f"authzProjection.{attr['code']}",
                       f"source ({ec2}, {fc}) 在 MODEL entities 中不存在")

            # allowedValues 与 valueRef 互斥
            if "allowedValues" in attr and "valueRef" in attr:
                ec.add(bo, "SECURITY", f"authzProjection.{attr['code']}",
                       "allowedValues 与 valueRef 互斥，不得同时出现")

    # --- RULE fragment 检查 ---
    if "RULE" in frags:
        _, rule_frag = frags["RULE"]
        seen_rule_codes = set()
        for r in rule_frag.get("rules", []):
            rc = r.get("code")
            if rc in seen_rule_codes:
                ec.add(bo, "RULE", f"rule.{rc}", "rule.code 重复")
            seen_rule_codes.add(rc)

            scope = r.get("scope", "BO")

            if scope == "ENTITY":
                ec2 = r.get("entityCode", "")
                if ec2 and ec2 not in entity_index:
                    ec.add(bo, "RULE", f"rule.{rc}.entityCode",
                           f"entityCode={ec2} 在 MODEL entities 中不存在")

            if scope == "FIELD":
                ec2 = r.get("entityCode", "")
                fc = r.get("fieldCode", "")
                if (ec2, fc) not in attr_index:
                    ec.add(bo, "RULE", f"rule.{rc}.fieldCode",
                           f"({ec2}, {fc}) 在 MODEL entities 中不存在")

            if scope == "OPERATION":
                op_code_ref = r.get("operationCode", "")
                if "OPERATION" in frags:
                    _, op_data = frags["OPERATION"]
                    op_codes = {o["code"] for o in op_data.get("operations", [])}
                    if op_code_ref and op_code_ref not in op_codes:
                        ec.add(bo, "RULE", f"rule.{rc}.operationCode",
                               f"operationCode={op_code_ref} 在 OPERATION fragment 中不存在")

            if scope == "CROSS_BO":
                cr = r.get("crossBoRef", {})
                lec = cr.get("localEntityCode", "")
                lfc = cr.get("localFieldCode", "")
                if (lec, lfc) not in attr_index:
                    ec.add(bo, "RULE", f"rule.{rc}.crossBoRef.localField",
                           f"({lec}, {lfc}) 在 MODEL entities 中不存在")
                # refBoCode 不能为空
                if not cr.get("refBoCode"):
                    ec.add(bo, "RULE", f"rule.{rc}.crossBoRef.refBoCode",
                           "CROSS_BO scope 时 refBoCode 必填")
                if not cr.get("refFieldCode"):
                    ec.add(bo, "RULE", f"rule.{rc}.crossBoRef.refFieldCode",
                           "CROSS_BO scope 时 refFieldCode 必填")

    # --- 2g. 命名一致性：MODEL entity/attribute name vs SECURITY authzProjection name vs VIEW displayName ---
    if root_entity:
        for attr in root_entity.get("attributes", []):
            acode = attr["code"]
            mname = attr.get("name", "")

            # MODEL.name vs VIEW displayName (name/displayName 语义不同的字段除外: id/status/deleted/tenant/time/by)
            SKIP_DISPLAY_MISMATCH = {"id", "status", "is_deleted", "tenant_code",
                                      "created_time", "updated_time", "created_by", "updated_by"}
            if acode not in SKIP_DISPLAY_MISMATCH and "VIEW" in frags:
                _, view = frags["VIEW"]
                for fv in view.get("fieldViews", []):
                    if fv.get("entityCode") == root_entity["code"] and fv.get("fieldCode") == acode:
                        vdn = fv.get("displayName", "")
                        if vdn and mname and vdn != mname:
                            # 豁免：_id 后缀字段在 VIEW 中去掉 "ID" 是合理的（前端下拉选择器不展示 ID 字样）
                            if mname.endswith("ID") and vdn == mname[:-2].rstrip():
                                pass  # 合法省略
                            else:
                                # direction: VIEW 为权威业务术语源
                                ec.add(bo, "MODEL vs VIEW", f"{acode}",
                                       f"命名不一致: MODEL.name='{mname}' vs VIEW.displayName='{vdn}'",
                                       level="WARN")
                        break

            # SECURITY authzProjection.name vs MODEL.name
            if "SECURITY" in frags:
                _, sec = frags["SECURITY"]
                for ap in sec.get("authzProjection", {}).get("attributes", []):
                    src = ap.get("source", {})
                    if src.get("entityCode") == root_entity["code"] and src.get("fieldCode") == acode:
                        sn = ap.get("name", "")
                        if sn and mname and sn != mname:
                            # direction: VIEW 为权威业务术语源，SECURITY 应与 MODEL 对齐
                            ec.add(bo, "SECURITY vs MODEL", f"{acode}",
                                   f"命名不一致: SECURITY.authzProjection.name='{sn}' vs MODEL.name='{mname}'",
                                   level="WARN")
                        break

    # --- 2h. VALIDATION (entityCode, fieldCode) 不得重复 ---
    # (已在 VALIDATION 节中通过 seen_val_keys 检查，此处不重复)

    # --- 2i. detailEmbedEntities 仅含一级直属于聚合根的子实体 ---
    if "VIEW" in frags:
        _, view = frags["VIEW"]
        for tab in view.get("detailTabs", []):
            for sec_def in tab.get("sections", []):
                ent_code = sec_def.get("entityCode", "")
                if ent_code and ent_code not in entity_index:
                    ec.add(bo, "VIEW", f"detailTabs.{tab['code']}.sections.{sec_def['code']}.entityCode",
                           f"entityCode={ent_code} 在 MODEL entities 中不存在")

        for tab in view.get("detailTabs", []):
            ds = tab.get("dataSource", {})
            if ds.get("type") == "BO_QUERY":
                ref_bo = ds.get("boCode", "")
                if ref_bo and ref_bo != bo:
                    ec.add(bo, "VIEW", f"detailTabs.{tab['code']}.dataSource.boCode",
                           f"跨 BO 查询引用 boCode={ref_bo}，请确认数据来源", level="WARN")

    # --- 2j. CROSS_BO_REF → CROSS_BO_DISPLAY 链完整性 ---
    # 每个 CROSS_BO_REF 若声明了 displayFields，则该组 displayFields.localCode
    # 必须与本 entity 内的 CROSS_BO_DISPLAY 属性一一对应
    for ent in entities:
        display_local_codes = set()
        for attr in ent.get("attributes", []):
            if attr.get("semanticRole") == "CROSS_BO_DISPLAY":
                display_local_codes.add(attr["code"])

        for attr in ent.get("attributes", []):
            if attr.get("semanticRole") == "CROSS_BO_REF" and "crossBoRef" in attr:
                for df in attr["crossBoRef"].get("displayFields", []):
                    lc = df.get("localCode", "")
                    if lc and lc not in display_local_codes:
                        ec.add(bo, "MODEL", f"entity.{ent['code']}.{attr['code']}.crossBoRef.displayFields",
                               f"displayFields.localCode='{lc}' 缺少对应的 CROSS_BO_DISPLAY 属性 ({lc} 未在 entity 中定义为 CROSS_BO_DISPLAY)")

# ===========================================================================
# 阶段 3: bo-info.json 一致性检查
# ===========================================================================
print("\n" + "=" * 80)
print("阶段 3: bo-info.json 与 Fragment 一致性检查")
print("=" * 80)

for bo in BO_LIST:
    bo_info_path = META_DIR / bo / "bo-info.json"
    if not bo_info_path.exists():
        continue
    bo_info = load_json(bo_info_path)

    for meta_type in ["MODEL", "OPERATION", "RULE", "SECURITY", "VALIDATION", "VIEW"]:
        if meta_type not in all_fragments.get(bo, {}):
            continue
        env, _ = all_fragments[bo][meta_type]

        for field in ["appCode", "tenantId"]:
            if env.get(field) != bo_info.get(field):
                ec.add(bo, f"bo-info vs {meta_type.lower()}-fragment", field,
                       f"bo-info.{field}={bo_info.get(field)} ≠ fragment.{field}={env.get(field)}")

# ===========================================================================
# 阶段 4: _ontology 应用级本体 Fragment 校验
# ===========================================================================
print("\n" + "=" * 80)
print("阶段 4: _ontology 应用级本体 Fragment 校验")
print("=" * 80)

ontology_dir = META_DIR / "_ontology"
if ontology_dir.is_dir():
    ontology_frag_dir = ontology_dir / "fragments"
    if ontology_frag_dir.is_dir():
        ONTOLOGY_META_TYPES = ["LINK", "DERIVATION", "TEMPORAL", "ACTION_CHAIN"]
        onto_frags = {}

        for meta_type in ONTOLOGY_META_TYPES:
            file_expected = f"crm-{meta_type.lower().replace('_', '-')}.fragment.json"
            fpath = ontology_frag_dir / file_expected

            if not fpath.exists():
                print(f"  [WARN] _ontology/{file_expected} — 文件不存在，跳过")
                continue

            try:
                data = load_json(fpath)
            except json.JSONDecodeError as e:
                ec.add("_ontology", file_expected, "JSON解析", str(e))
                continue

            # Schema 校验
            try:
                resolver = jsonschema.RefResolver.from_schema(envelope_schema, store=schema_store)
                validator = Draft202012Validator(envelope_schema, resolver=resolver)
                errors = list(validator.iter_errors(data))
                for err in errors:
                    ec.add("_ontology", file_expected, "EnvelopeSchema",
                           f"{'.'.join(str(p) for p in err.absolute_path)}: {err.message}")
            except Exception as e:
                ec.add("_ontology", file_expected, "EnvelopeValidation", str(e))

            content = data.get("content", {})
            if meta_type in sub_schemas:
                try:
                    sub_schema = sub_schemas[meta_type]
                    s_resolver = jsonschema.RefResolver.from_schema(sub_schema, store=schema_store)
                    s_validator = Draft202012Validator(sub_schema, resolver=s_resolver)
                    for err in s_validator.iter_errors(content):
                        ec.add("_ontology", file_expected, "ContentSchema",
                               f"{'.'.join(str(p) for p in err.absolute_path)}: {err.message}")
                except Exception as e:
                    ec.add("_ontology", file_expected, "ContentValidation", str(e))

            onto_frags[meta_type] = (data, content)
            print(f"  [OK] _ontology/{file_expected}")

        # ── LINK 交叉校验 ──
        if "LINK" in onto_frags:
            _, link_content = onto_frags["LINK"]
            for link in link_content.get("links", []):
                code = link.get("code", "?")
                src_bo = link.get("source", {}).get("boCode", "")
                tgt_bo = link.get("target", {}).get("boCode", "")
                if src_bo and src_bo not in BO_LIST:
                    ec.add("_ontology", "LINK", f"{code}.source.boCode",
                           f"source BO '{src_bo}' 不在已注册 BO 集合中")
                if tgt_bo and tgt_bo not in BO_LIST:
                    ec.add("_ontology", "LINK", f"{code}.target.boCode",
                           f"target BO '{tgt_bo}' 不在已注册 BO 集合中")
                card = link.get("cardinality", "")
                mat = link.get("materialization", "")
                if card == "MANY_TO_MANY" and mat not in ("ASSOCIATION_ENTITY", "DERIVED"):
                    ec.add("_ontology", "LINK", f"{code}.cardinality",
                           f"MANY_TO_MANY 必须声明 ASSOCIATION_ENTITY 或 DERIVED，当前 materialization={mat}")

        # ── DERIVATION 交叉校验 ──
        if "DERIVATION" in onto_frags:
            _, deriv_content = onto_frags["DERIVATION"]
            for obj in deriv_content.get("derivedObjects", []):
                obj_code = obj.get("code", "?")
                root_bo = obj.get("root", {}).get("boCode", "")
                if root_bo and root_bo not in BO_LIST:
                    ec.add("_ontology", "DERIVATION", f"{obj_code}.root.boCode",
                           f"根 BO '{root_bo}' 不在已注册 BO 集合中")
                for dep in obj.get("dependencies", []):
                    dep_bo = dep.get("boCode", "")
                    if dep_bo and dep_bo not in BO_LIST:
                        ec.add("_ontology", "DERIVATION", f"{obj_code}.dependencies.boCode",
                               f"依赖 BO '{dep_bo}' 不在已注册 BO 集合中")
                api_exp = obj.get("apiExposure", {})
                if api_exp.get("enabled") is True and not api_exp.get("resourcePath"):
                    ec.add("_ontology", "DERIVATION", f"{obj_code}.apiExposure",
                           "enabled=true 但 resourcePath 缺失")

        # ── TEMPORAL 交叉校验 ──
        if "TEMPORAL" in onto_frags:
            _, temporal_content = onto_frags["TEMPORAL"]
            for tl in temporal_content.get("timelines", []):
                tl_code = tl.get("code", "?")
                tl_bo = tl.get("boCode", "")
                if tl_bo and tl_bo not in BO_LIST:
                    ec.add("_ontology", "TEMPORAL", f"{tl_code}.boCode",
                           f"BO '{tl_bo}' 不在已注册 BO 集合中")
                for es in tl.get("eventSources", []):
                    if es.get("sourceType") == "OPERATION":
                        op_code = es.get("operationCode", "")
                        if op_code:
                            ec.add("_ontology", "TEMPORAL", f"{tl_code}.operationCode",
                                   f"引用了 OPERATION '{op_code}'（需确保对应 BO 的 OPERATION Fragment 中存在）",
                                   level="WARN")

        # ── ACTION_CHAIN 交叉校验 ──
        if "ACTION_CHAIN" in onto_frags:
            _, chain_content = onto_frags["ACTION_CHAIN"]
            for ch in chain_content.get("chains", []):
                ch_code = ch.get("code", "?")
                trig = ch.get("trigger", {})
                trig_bo = trig.get("boCode", "")
                if trig_bo and trig_bo not in BO_LIST:
                    ec.add("_ontology", "ACTION_CHAIN", f"{ch_code}.trigger.boCode",
                           f"触发器 BO '{trig_bo}' 不在已注册 BO 集合中")
                trig_op = trig.get("operationCode", "")
                if trig_op:
                    ec.add("_ontology", "ACTION_CHAIN", f"{ch_code}.trigger.operationCode",
                           f"引用了 OPERATION '{trig_op}'（需确保对应 BO 的 OPERATION Fragment 中存在）",
                           level="WARN")
                for step in ch.get("steps", []):
                    s_code = step.get("code", "?")
                    for dep in step.get("dependsOn", []):
                        step_codes = {s["code"] for s in ch.get("steps", [])}
                        if dep not in step_codes:
                            ec.add("_ontology", "ACTION_CHAIN",
                                   f"{ch_code}.step.{s_code}.dependsOn",
                                   f"依赖步骤 '{dep}' 不在本链步骤中")
                    if step.get("failurePolicy") == "COMPENSATE" and not step.get("compensateStepCode"):
                        ec.add("_ontology", "ACTION_CHAIN",
                               f"{ch_code}.step.{s_code}.failurePolicy",
                               "failurePolicy=COMPENSATE 但 compensateStepCode 未配置")

        # ── LINK ↔ DERIVATION 交叉引用：derivedObject.dependencies.viaLink 必须在 LINK 中存在 ──
        if "LINK" in onto_frags and "DERIVATION" in onto_frags:
            _, link_content = onto_frags["LINK"]
            link_codes = {l["code"] for l in link_content.get("links", [])}
            _, deriv_content = onto_frags["DERIVATION"]
            for obj in deriv_content.get("derivedObjects", []):
                obj_code = obj.get("code", "?")
                for dep in obj.get("dependencies", []):
                    vlink = dep.get("viaLink", "")
                    if vlink and vlink not in link_codes:
                        ec.add("_ontology", "DERIVATION-LINK",
                               f"{obj_code}.dependencies.viaLink",
                               f"viaLink='{vlink}' 在 LINK 中不存在")

print()

# ===========================================================================
# 输出 summary
# ===========================================================================
error_count = ec.summary()

print(f"\n总计: {len(BO_LIST)} 个 BO, {error_count} 个错误, {len(ec.warnings)} 个警告")

sys.exit(0 if error_count == 0 else 1)
