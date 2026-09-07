#!/usr/bin/env python3
"""
BO DDL Generator — 从 MODEL Fragment 生成 Flyway 建表 SQL
读取 metadata/design-time/*/fragments/*-model.fragment.json，结合校验规则，
生成对应数据库的 CREATE TABLE 语句。
"""

import json
import sys
from pathlib import Path
from collections import OrderedDict
from datetime import date

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
METADATA_DIR = PROJECT_DIR / "metadata"
OUTPUT_DIR = PROJECT_DIR / "generated-sql"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 类型映射 ──────────────────────────────────────────────────
TYPE_MAP = {
    "STRING":   "VARCHAR",
    "LONG":     "BIGINT",
    "INTEGER":  "INT",
    "DECIMAL":  "DECIMAL(18,2)",
    "BOOLEAN":  "TINYINT(1)",
    "DATE":     "DATE",
    "DATETIME": "DATETIME",
}

# ── 审计字段相关的代码名（用于 auditStrategy 策略判断和自动索引）─────────
_TIMESTAMP_FIELDS = {"created_time", "updated_time"}
_AUDIT_CODE_NAMES = {"is_deleted", "created_time", "updated_time", "created_by", "updated_by", "tenant_code"}
# 审计字段中需要自动建索引的
_AUDIT_INDEX_CODES = {"tenant_code", "created_time"}

# auditStrategy == "DATABASE" 时 created_time/updated_time 的默认值覆盖
_AUDIT_STRATEGY_DEFAULTS = {
    "created_time": "DEFAULT CURRENT_TIMESTAMP",
    "updated_time": "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
}

def load_json(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ skip {path.name}: {e}", file=sys.stderr)
        return None

def load_validation_rules(bo_code: str) -> dict:
    """加载 BO 的校验规则，key = (entityCode, fieldCode)。"""
    rules = {}
    val_path = METADATA_DIR / "design-time" / bo_code / "fragments" / f"{bo_code}-validation.fragment.json"
    data = load_json(val_path)
    if not data:
        return rules
    for r in data.get("content", {}).get("rules", []):
        key = (r.get("entityCode"), r.get("fieldCode"))
        rules[key] = r
    return rules

def sql_type(attr: dict, val_rule: dict | None) -> str:
    """将 BO 属性类型映射为 SQL 类型。

    VARCHAR 宽度规则（优先级从高到低）：
    1. VALIDATION Fragment 中声明的 max：
       - max ≤ 2000 → VARCHAR(max)
       - max > 2000 → TEXT（MySQL VARCHAR 上限 65535，超 2000 用 TEXT 更合理）
    2. semanticRole 为 BUSINESS_KEY/NAME → VARCHAR(200)
    3. semanticRole 为 STATUS → VARCHAR(32)
    4. 其余 STRING → VARCHAR(100)（匹配实际表规范）
    """
    bo_type = attr.get("type", "STRING")
    sql = TYPE_MAP.get(bo_type, "VARCHAR(100)")

    if bo_type == "STRING":
        code = attr.get("code", "")
        semantic = attr.get("semanticRole", "NORMAL")

        # 0) model 属性显式声明的 length（最高优先级，覆盖所有默认规则）
        model_length = attr.get("length")
        if model_length is not None:
            return "TEXT" if model_length > 2000 else f"VARCHAR({model_length})"

        # 1) 校验规则显式声明的 max
        max_len = None
        if val_rule:
            max_len = val_rule.get("max")
        if max_len:
            # 阈值：max > 2000 → VARCHAR 不适用，改用 TEXT
            if max_len > 2000:
                return "TEXT"
            return f"VARCHAR({max_len})"

        # 2) 按语义角色给默认宽度
        if semantic in ("BUSINESS_KEY", "NAME"):
            return "VARCHAR(200)"
        if semantic == "STATUS":
            return "VARCHAR(32)"

        # 3) 默认 VARCHAR(100)（对齐实际 Flyway 规范，而非 255）
        return "VARCHAR(100)"

    # DECIMAL：若 attr 声明了 precision/scale，覆盖默认 DECIMAL(18,2)
    if bo_type == "DECIMAL":
        precision = attr.get("precision")
        scale = attr.get("scale")
        if precision is not None and scale is not None:
            return f"DECIMAL({precision},{scale})"

    return sql

def column_default(attr: dict) -> str:
    """生成 DEFAULT 子句。"""
    dv = attr.get("defaultValue")
    if dv is None or dv == "":
        return ""
    t = attr.get("type", "STRING")
    if t == "BOOLEAN":
        return "DEFAULT 0" if dv in ("false", "0", False) else "DEFAULT 1"
    if t in ("INTEGER", "LONG", "DECIMAL"):
        return f"DEFAULT {dv}"
    return f"DEFAULT '{dv}'"

def column_nullable(attr: dict, val_rule: dict | None) -> str:
    """生成 NULL / NOT NULL。"""

    code = attr.get("code", "")
    is_pk = attr.get("isPk", False)

    if is_pk:
        return "NOT NULL"

    required = False
    if val_rule:
        required = val_rule.get("required", False)

    semantic = attr.get("semanticRole", "NORMAL")
    if semantic == "BUSINESS_KEY" and not required:
        required = True  # 业务键默认非空

    return "NOT NULL" if required else "DEFAULT NULL"

def cross_ref_comment(attr: dict) -> str:
    """为 CROSS_BO_REF 字段生成关联注释。"""
    cr = attr.get("crossBoRef")
    if not cr:
        return ""
    ref_bo = cr.get("refBoCode", "?")
    ref_field = cr.get("refFieldCode", "id")
    nature = cr.get("referenceNature", "MASTER_DATA")
    nature_hint = "上游BO" if nature == "BUSINESS_FLOW" else "关联"
    return f"（{nature_hint}{ref_bo}表.{ref_field}）"

def col_name(attr: dict) -> str:
    """返回物理列名：优先取 columnName，否则取 code。"""
    return attr.get("columnName") or attr.get("code", "")


def generate_table_sql(entity: dict, val_rules: dict, bo_config: dict = None, pk_field: str = "id") -> str:
    """为单个 entity 生成 CREATE TABLE 语句。"""
    if bo_config is None:
        bo_config = {}
    table = entity.get("tableName", "")
    if not table:
        return ""

    entity_name = entity.get("name", table)
    entity_code = entity.get("code", table)
    audit_strategy = bo_config.get("auditStrategy", "DATABASE")
    lines = []
    lines.append(f"-- 实体：{entity_name}（{entity.get('code', '')}）")
    lines.append(f"-- 角色：{entity.get('aggregateRole', 'ROOT')}")
    if entity.get("parentEntityCode"):
        lines.append(f"-- 父实体：{entity['parentEntityCode']}，外键：{entity.get('parentRefField', '')}")
    lines.append(f"CREATE TABLE IF NOT EXISTS `{table}` (")

    columns = []
    indexes = []
    pk_col = "id"
    pk_type = "BIGINT"
    # entity.indexes 显式定义时跳过语义角色自动推导，避免与元数据冲突
    use_entity_indexes = bool(entity.get("indexes"))

    for attr in entity.get("attributes", []):
        code = attr.get("code", "")
        db_col = col_name(attr)                 # 物理列名（优先 columnName）
        name = attr.get("name", code)
        val_rule = val_rules.get((entity.get("code"), code))
        semantic = attr.get("semanticRole", "NORMAL")

        # ── CROSS_BO_DISPLAY（名称伴生字段）：redundant=false（默认）时不生成 DB 列 ──
        # 参见 copilot-instructions.md §6.2.1：CROSS_BO_DISPLAY 仅在 redundant=true 时建列
        if semantic == "CROSS_BO_DISPLAY":
            if not attr.get("redundant"):
                continue  # 跳过，不生成列
            # redundant=true：生成列（作为普通字段处理，继续后续逻辑）

        # ── 普通字段处理 ──────────────────────────────────
        col_type = sql_type(attr, val_rule)
        nullable = column_nullable(attr, val_rule)
        default = column_default(attr)
        comment = name
        ref_hint = cross_ref_comment(attr)
        if ref_hint:
            comment += ref_hint

        col_def = f"    `{db_col}` {col_type}"
        if default:
            col_def += f" NOT NULL {default}"
        elif audit_strategy == "APPLICATION" and code in _TIMESTAMP_FIELDS:
            # 应用层审计策略：时间戳不由 DB 自动填充
            col_def += " DEFAULT NULL"
        else:
            col_def += f" {nullable}"
        col_def += f" COMMENT '{comment}'"
        columns.append(col_def)

        if attr.get("isPk"):
            pk_col = db_col
            pk_type = col_type

        # ── 索引规则：entity.indexes 未定义时按语义角色自动推导 ──────
        if not use_entity_indexes:
            # 1) 业务键 → UNIQUE KEY
            if semantic == "BUSINESS_KEY":
                indexes.append((f"uk_{db_col}", f"UNIQUE KEY `uk_{db_col}` (`{db_col}`)"))
            # 2) CROSS_BO_REF + filterable → 普通索引
            if semantic == "CROSS_BO_REF" and attr.get("filterable"):
                idx_name = f"idx_{db_col}"
                if not any(i[0] == idx_name for i in indexes):
                    indexes.append((idx_name, f"KEY `{idx_name}` (`{db_col}`)"))
            # 3) STATUS + filterable → 普通索引
            if semantic == "STATUS" and attr.get("filterable"):
                idx_name = f"idx_{db_col}"
                if not any(i[0] == idx_name for i in indexes):
                    indexes.append((idx_name, f"KEY `{idx_name}` (`{db_col}`)"))
            # 4) 审计字段自动建索引（tenant_code / created_time）
            if code in _AUDIT_INDEX_CODES:
                idx_name = f"idx_{db_col}"
                if not any(i[0] == idx_name for i in indexes):
                    indexes.append((idx_name, f"KEY `{idx_name}` (`{db_col}`)"))

    # 父实体外键索引
    parent_ref = entity.get("parentRefField")
    if parent_ref and parent_ref != pk_col:
        idx_name = f"idx_{parent_ref}"
        if not any(i[0] == idx_name for i in indexes):
            indexes.append((idx_name, f"KEY `{idx_name}` (`{parent_ref}`)"))

    # ── entity.indexes 显式定义的业务索引（优先级高于自动推导）──────
    for idx_def in entity.get("indexes", []):
        idx_name = idx_def.get("name", "")
        if not idx_name:
            continue
        idx_cols = idx_def.get("columns", [])
        is_unique = idx_def.get("unique", False)
        cols_sql = ", ".join(f"`{c}`" for c in idx_cols)
        idx_sql = f"UNIQUE KEY `{idx_name}` ({cols_sql})" if is_unique else f"KEY `{idx_name}` ({cols_sql})"
        if not any(i[0] == idx_name for i in indexes):
            indexes.append((idx_name, idx_sql))

    # 主键（AUTO_INCREMENT 仅当 pk_col=id 且非 SNOWFLAKE 策略时添加）
    id_strategy = bo_config.get("idStrategy", "SNOWFLAKE")
    pk_def = f"    PRIMARY KEY (`{pk_col}`)"
    if not any(a.get("isPk") for a in entity.get("attributes", [])):
        # 自动加 id 主键
        auto_inc = " AUTO_INCREMENT" if id_strategy != "SNOWFLAKE" else ""
        columns.insert(0, f"    `id` BIGINT NOT NULL{auto_inc} COMMENT '{entity_name}ID（主键）'")
        pk_col = "id"
        pk_type = "BIGINT"
    else:
        # 查找 PK 列并加 AUTO_INCREMENT（仅当非 SNOWFLAKE 且类型为 BIGINT/INT 且名为 id 时）
        if id_strategy != "SNOWFLAKE":
            for i, col in enumerate(columns):
                if col.startswith(f"    `{pk_col}` "):
                    if pk_col == "id" and ("BIGINT" in col or "INT" in col):
                        columns[i] = col.replace(" NOT NULL ", " NOT NULL AUTO_INCREMENT ")
                    break

    if columns:
        lines.append(",\n".join(columns) + ",")
    lines.append(pk_def)

    # 索引
    if indexes:
        lines[-1] += ","
        lines.append(",\n".join(i[1] for i in indexes))

    lines.append(f") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='{entity_name}';")
    return "\n".join(lines)

def generate_flyway_migration(bo_code: str, bo_name: str, tables: list[str]) -> str:
    """生成完整的 Flyway 迁移脚本（单个 BO）。"""
    today = date.today().strftime("%Y-%m-%d")
    lines = []
    lines.append("-- ============================================================")
    lines.append(f"-- {bo_name}管理模块建表脚本")
    lines.append(f"-- BO  : {bo_code}")
    lines.append(f"-- date: {today}（由 bo-ddl-gen.py 自动生成）")
    lines.append("-- ============================================================")
    lines.append("")
    for i, table_sql in enumerate(tables):
        if i > 0:
            lines.append("")
        lines.append(table_sql)
    lines.append("")
    return "\n".join(lines)

def generate_all(bo_code_filter: str | None = None):
    """遍历所有 BO，为每个 BO 生成一个 Flyway 迁移文件。
    若指定 bo_code_filter，则仅生成该 BO 的 DDL。
    返回 (summary_list, combined_sql_string)。"""
    all_sql = []
    summary = []

    for bo_dir in sorted((METADATA_DIR / "design-time").iterdir()):
        if not bo_dir.is_dir():
            continue
        # 跳过元容器目录（如 _ontology），它们不是业务对象
        if bo_dir.name.startswith("_"):
            continue
        bo_code = bo_dir.name
        if bo_code_filter and bo_code != bo_code_filter:
            continue
        fragments_dir = bo_dir / "fragments"
        if not fragments_dir.is_dir():
            continue

        model_path = fragments_dir / f"{bo_code}-model.fragment.json"
        data = load_json(model_path)
        if not data:
            continue

        content = data.get("content", {})
        bo_name = content.get("boName", bo_code)
        bo_config = content.get("boConfig", {})
        val_rules = load_validation_rules(bo_code)

        tables = []
        for entity in content.get("entities", []):
            sql = generate_table_sql(entity, val_rules, bo_config)
            if sql:
                tables.append(sql)

        if not tables:
            continue

        migration = generate_flyway_migration(bo_code, bo_name, tables)

        filename = f"V_{bo_code}__create_tables.sql"
        output_path = OUTPUT_DIR / filename
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(migration)
            f.write("\n")

        all_sql.append(migration)
        entity_count = len(content.get("entities", []))
        attr_count = sum(len(e.get("attributes", [])) for e in content.get("entities", []))
        summary.append((bo_code, bo_name, entity_count, attr_count, filename))

    # 输出汇总
    print(f"📦 生成完成：{len(summary)} 个 BO")
    for bo_code, bo_name, ec, ac, fn in summary:
        print(f"   {bo_name}({bo_code}) → {fn}  ({ec}表, {ac}列)")
    print(f"\n📁 输出目录：{OUTPUT_DIR}")

    # 也生成一个合并文件
    combined = f"-- Auto-generated by bo-ddl-gen.py\n-- {date.today()}\n\n" + "\n\n".join(all_sql)
    combined_path = OUTPUT_DIR / "_all_tables.sql"
    with open(combined_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(combined)
        f.write("\n")
    print(f"📁 合并文件：{combined_path}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="BO DDL Generator")
    parser.add_argument("--bo", type=str, default=None, help="仅生成指定 BO 的 DDL")
    args = parser.parse_args()

    if args.bo:
        print(f"🔧 从 BO MODEL Fragment 生成 {args.bo} DDL ...")
    else:
        print("🔧 从 BO MODEL Fragment 生成 DDL ...")
    generate_all(bo_code_filter=args.bo)

if __name__ == "__main__":
    main()
