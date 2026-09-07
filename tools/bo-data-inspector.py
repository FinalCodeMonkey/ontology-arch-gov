#!/usr/bin/env python3
"""
BO 数据检查器 — 基于 BO 元数据连接数据库，提供 DDL漂移检测 / 数据画像 / 校验执行 / 引用完整性 服务。
配置优先从 application-dev.properties 读取，可通过命令行参数覆盖。

用法:
  python bo-data-inspector.py drift customers          # DDL 漂移检测
  python bo-data-inspector.py profile customers         # 数据画像
  python bo-data-inspector.py validate customers        # 校验规则执行
  python bo-data-inspector.py ref-integrity customers   # 跨BO引用完整性
  python bo-data-inspector.py all customers             # 全部检查
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import pymysql

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
METADATA_DIR = PROJECT_DIR / "metadata"

# ── 默认数据库配置 ──────────────────────────────────────────────
DEFAULT_CONFIG = {
    "host": "k8s-bj-test-nodeports.kaijie.com.cn",
    "port": 31762,
    "user": "system",
    "password": "7c0162289b9444faa90211fae9d2f9a6",
    "database": "cbg_internet_sales",
    "charset": "utf8mb4",
}

# ── 运行时配置覆盖（由 API 服务通过 set_config_override() 注入）──
_config_override = None


def set_config_override(config: dict):
    """设置运行时配置覆盖。传入 None 则清除覆盖。"""
    global _config_override
    _config_override = config


def get_config_override() -> dict:
    """获取当前运行时配置覆盖。"""
    return _config_override


def load_properties(path: Path) -> dict:
    """从 properties 文件提取数据源配置。"""
    if not path.exists():
        return {}
    config = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            # rj.unify.engine.datasource.url → 解析 host/port/database
            if k == "rj.unify.engine.datasource.url" and "jdbc:mysql://" in v:
                url = v.replace("jdbc:mysql://", "")
                host_part, _, rest = url.partition("/")
                if ":" in host_part:
                    config["host"], config["port"] = host_part.split(":")
                    config["port"] = int(config["port"])
                else:
                    config["host"] = host_part
                db = rest.split("?")[0] if "?" in rest else rest
                if db:
                    config["database"] = db
            elif k == "rj.unify.engine.datasource.username":
                config["user"] = v
            elif k == "rj.unify.engine.datasource.password":
                config["password"] = v
    return config


def get_connection():
    """获取数据库连接。优先使用运行时覆盖配置，其次 application-dev.properties，最后 DEFAULT_CONFIG。"""
    cfg = dict(DEFAULT_CONFIG)

    # 1) 加载 properties 文件
    for candidate in [
        PROJECT_DIR.parent / "enterprise-app-platform" / "demo-verifier" / "src" / "main" / "resources" / "application-dev.properties",
        PROJECT_DIR.parent / "demo-verifier" / "src" / "main" / "resources" / "application-dev.properties",
    ]:
        props = load_properties(candidate)
        if props:
            cfg.update(props)
            break

    # 2) 应用运行时覆盖（最高优先级）
    if _config_override:
        cfg.update(_config_override)

    return pymysql.connect(**cfg, cursorclass=pymysql.cursors.DictCursor)


def load_bo_metadata(bo_code: str = None) -> dict:
    """加载所有 BO 的 MODEL Fragment 元数据。"""
    bos = {}
    for bo_dir in (METADATA_DIR / "design-time").iterdir():
        if not bo_dir.is_dir():
            continue
        bc = bo_dir.name
        if bo_code and bc != bo_code:
            continue
        model_path = bo_dir / "fragments" / f"{bc}-model.fragment.json"
        if not model_path.exists():
            continue
        with open(model_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        content = data.get("content", {})
        ent_list = []
        for ent in content.get("entities", []):
            attrs = []
            for a in ent.get("attributes", []):
                attrs.append({
                    "code": a["code"],
                    "name": a.get("name", a["code"]),
                    "type": a.get("type", "STRING"),
                    "isPk": a.get("isPk", False),
                    "columnName": a.get("columnName", a["code"]),
                    "semanticRole": a.get("semanticRole", "NORMAL"),
                    "filterable": a.get("filterable", False),
                    "crossBoRef": a.get("crossBoRef"),
                })
            ent_list.append({
                "code": ent["code"],
                "name": ent.get("name", ent["code"]),
                "tableName": ent.get("tableName", ""),
                "isPrimary": ent.get("isPrimary", False),
                "attributes": attrs,
            })
        bos[bc] = {
            "boCode": bc,
            "boName": content.get("boName", bc),
            "entities": ent_list,
        }
    return bos


# ═══════════════════════════════════════════════════════════════
#  1. DDL 漂移检测
# ═══════════════════════════════════════════════════════════════

TYPE_TO_SQL = {
    "STRING": "varchar", "LONG": "bigint", "INTEGER": "int",
    "DECIMAL": "decimal", "BOOLEAN": "tinyint", "DATE": "date",
    "DATETIME": "datetime",
}

def detect_drift(bo_code: str = None):
    """对比 MODEL Fragment 定义 vs INFORMATION_SCHEMA 实际结构。"""
    bos = load_bo_metadata(bo_code)
    conn = get_connection()
    issues = []

    with conn.cursor() as cur:
        for bc, bo in bos.items():
            print(f"\n{'='*60}\n  📦 {bc} ({bo['boName']})\n{'='*60}")
            for ent in bo["entities"]:
                table = ent["tableName"]
                if not table:
                    print(f"  ⚠ {ent['code']}: 无 tableName，跳过")
                    continue

                # 检查表是否存在
                cur.execute(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                    (table,),
                )
                if not cur.fetchone():
                    msg = f"  ❌ 缺表: {table}"
                    print(msg)
                    issues.append(msg)
                    continue

                # 获取实际列
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY "
                    "FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                    (table,),
                )
                actual_cols = {row["COLUMN_NAME"]: row for row in cur.fetchall()}

                print(f"  📋 {table} ({len(ent['attributes'])} def / {len(actual_cols)} actual)")

                for attr in ent["attributes"]:
                    col = attr["columnName"]
                    actual = actual_cols.get(col)
                    if not actual:
                        msg = f"    ❌ 缺列: {table}.{col} ({attr['name']})"
                        print(msg)
                        issues.append(msg)
                        continue

                    # 类型对比
                    expected_type = TYPE_TO_SQL.get(attr["type"], "varchar").lower()
                    actual_type = actual["DATA_TYPE"].lower()
                    if expected_type not in actual_type and actual_type not in expected_type:
                        # 模糊匹配：bigint≈int, varchar≈char
                        is_close = False
                        if expected_type in ("bigint", "int") and actual_type in ("bigint", "int"):
                            is_close = True
                        if expected_type == "varchar" and "char" in actual_type:
                            is_close = True
                        if not is_close:
                            msg = f"    ⚠ 类型不匹配: {table}.{col} 期望 {attr['type']}({expected_type}) 实际 {actual['COLUMN_TYPE']}"
                            print(msg)
                            issues.append(msg)

                # 检查多余列（不在 MODEL 定义中）
                defined_cols = {a["columnName"] for a in ent["attributes"]}
                extra = set(actual_cols.keys()) - defined_cols
                if extra:
                    print(f"    ℹ 多余列: {', '.join(sorted(extra))}")

    conn.close()
    print(f"\n{'='*60}")
    print(f"📊 总计 {len(issues)} 个问题")
    return issues


# ═══════════════════════════════════════════════════════════════
#  2. 数据画像
# ═══════════════════════════════════════════════════════════════

def profile_data(bo_code: str):
    """对指定 BO 的所有表做数据画像（仅查询物理表中实际存在的列）。"""
    bos = load_bo_metadata(bo_code)
    if bo_code not in bos:
        print(f"❌ BO '{bo_code}' 不存在")
        return
    bo = bos[bo_code]
    conn = get_connection()

    print(f"\n📊 {bo['boName']} ({bo_code}) 数据画像")
    print(f"{'='*60}")

    with conn.cursor() as cur:
        for ent in bo["entities"]:
            table = ent["tableName"]
            if not table:
                continue

            # 先查表是否存在
            cur.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (table,)
            )
            if not cur.fetchone():
                print(f"\n  ⚠ {table}: 表不存在，跳过画像")
                continue

            # 获取实际列清单
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (table,)
            )
            actual_cols = {row["COLUMN_NAME"] for row in cur.fetchall()}

            try:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM `{table}`")
                row_count = cur.fetchone()["cnt"]
            except Exception as e:
                print(f"\n  ⚠ {table}: 查询失败 — {e}")
                continue

            print(f"\n  📋 {table} ({ent['name']}): {row_count} 行")

            for attr in ent["attributes"]:
                col = attr["columnName"]
                if col not in actual_cols:
                    # 列不存在则跳过，已在 drift 阶段报告
                    continue

                try:
                    # 空值率
                    cur.execute(
                        f"SELECT SUM(CASE WHEN `{col}` IS NULL THEN 1 ELSE 0 END) AS nulls, "
                        f"COUNT(*) AS total FROM `{table}`"
                    )
                    row = cur.fetchone()
                    null_rate = (row["nulls"] / row["total"] * 100) if row["total"] > 0 else 0
                    if null_rate > 0:
                        print(f"    {col}: {null_rate:.1f}% 空值")

                    # 枚举分布（仅前5个值，小表才做）
                    if 0 < row_count <= 100000:
                        try:
                            cur.execute(
                                f"SELECT `{col}` AS val, COUNT(*) AS cnt FROM `{table}` "
                                f"WHERE `{col}` IS NOT NULL GROUP BY `{col}` ORDER BY cnt DESC LIMIT 5"
                            )
                            dist = cur.fetchall()
                            if dist and len(dist) < 20:
                                items = ", ".join(f"{r['val']}:{r['cnt']}" for r in dist)
                                print(f"    {col} 分布: {items}")
                        except Exception:
                            pass
                except Exception as e:
                    print(f"    ⚠ {col}: 画像失败 — {e}")

    conn.close()


# ═══════════════════════════════════════════════════════════════
#  3. 校验规则执行
# ═══════════════════════════════════════════════════════════════

def run_validations(bo_code: str):
    """加载 VALIDATION Fragment 并对真实数据执行校验。"""
    val_path = METADATA_DIR / "design-time" / bo_code / "fragments" / f"{bo_code}-validation.fragment.json"
    if not val_path.exists():
        print(f"❌ {bo_code} 无 VALIDATION Fragment")
        return

    with open(val_path, "r", encoding="utf-8") as f:
        val_data = json.load(f)

    rules = val_data.get("content", {}).get("rules", [])
    if not rules:
        print(f"  ℹ 无校验规则")
        return

    conn = get_connection()
    bos = load_bo_metadata(bo_code)
    bo = bos.get(bo_code)
    if not bo:
        conn.close()
        return

    entity_map = {e["code"]: e for e in bo["entities"]}

    print(f"\n✅ {bo['boName']} ({bo_code}) 校验规则执行")
    print(f"{'='*60}")

    with conn.cursor() as cur:
        for rule in rules:
            ec = rule.get("entityCode")
            fc = rule.get("fieldCode")
            ent = entity_map.get(ec)
            if not ent:
                continue
            table = ent["tableName"]
            if not table:
                continue
            attr = next((a for a in ent["attributes"] if a["code"] == fc), None)
            col = attr["columnName"] if attr else fc

            conditions = []
            label_parts = []

            if rule.get("required"):
                conditions.append(f"`{col}` IS NULL OR `{col}` = ''")
                label_parts.append("必填")
            if rule.get("min") is not None:
                conditions.append(f"LENGTH(`{col}`) < {rule['min']}")
                label_parts.append(f"最短{rule['min']}")
            if rule.get("max") is not None:
                conditions.append(f"LENGTH(`{col}`) > {rule['max']}")
                label_parts.append(f"最长{rule['max']}")
            if rule.get("enum"):
                # enum 现在是 [{value, label}] 对象数组，value 用于 SQL 查询，label 用于显示
                vals = ", ".join(f"'{v['value']}'" for v in rule["enum"])
                conditions.append(f"`{col}` IS NOT NULL AND `{col}` NOT IN ({vals})")
                labels = ",".join(v.get("label", v["value"]) for v in rule["enum"][:3])
                label_parts.append(f"枚举:[{labels}...]")

            if not conditions:
                continue

            where = " OR ".join(conditions)
            try:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM `{table}` WHERE ({where})")
                cnt = cur.fetchone()["cnt"]
                label = " + ".join(label_parts)
                icon = "✅" if cnt == 0 else "❌"
                msg = f"  {icon} {table}.{col} ({label}): {cnt} 行违规"
                if rule.get("message"):
                    msg += f" — {rule['message']}"
                print(msg)
            except Exception as e:
                print(f"  ⚠ {table}.{col}: 执行失败 — {e}")

    conn.close()


# ═══════════════════════════════════════════════════════════════
#  4. 跨 BO 引用完整性
# ═══════════════════════════════════════════════════════════════

def check_ref_integrity(bo_code: str):
    """检查指定 BO 的 CROSS_BO_REF 字段引用完整性。"""
    bos = load_bo_metadata()
    if bo_code not in bos:
        print(f"❌ BO '{bo_code}' 不存在")
        return
    bo = bos[bo_code]
    conn = get_connection()

    print(f"\n🔗 {bo['boName']} ({bo_code}) 跨BO引用完整性")
    print(f"{'='*60}")

    with conn.cursor() as cur:
        for ent in bo["entities"]:
            table = ent["tableName"]
            if not table:
                continue
            for attr in ent["attributes"]:
                cr = attr.get("crossBoRef")
                if not cr:
                    continue
                ref_bo_code = cr["refBoCode"]
                ref_field = cr.get("refFieldCode", "id")
                ref_bo = bos.get(ref_bo_code)
                if not ref_bo:
                    print(f"  ⚠ {table}.{attr['columnName']}: 目标 BO '{ref_bo_code}' 不存在")
                    continue

                # 找目标表（取主实体）
                ref_table = None
                for e in ref_bo["entities"]:
                    if e.get("isPrimary"):
                        ref_table = e["tableName"]
                        break
                if not ref_table and ref_bo["entities"]:
                    ref_table = ref_bo["entities"][0]["tableName"]

                if not ref_table:
                    print(f"  ⚠ {table}.{attr['columnName']}: 目标表未找到")
                    continue

                col = attr["columnName"]
                try:
                    cur.execute(
                        f"SELECT COUNT(*) AS cnt FROM `{table}` t "
                        f"LEFT JOIN `{ref_table}` r ON t.`{col}` = r.`{ref_field}` "
                        f"WHERE t.`{col}` IS NOT NULL AND r.`{ref_field}` IS NULL"
                    )
                    orphans = cur.fetchone()["cnt"]
                    icon = "✅" if orphans == 0 else "❌"
                    print(f"  {icon} {table}.{col} → {ref_table}.{ref_field}: {orphans} 悬空引用")
                except Exception as e:
                    print(f"  ⚠ {table}.{col} → {ref_table}.{ref_field}: 查询失败 — {e}")

    conn.close()


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

COMMANDS = {
    "drift": detect_drift,
    "profile": profile_data,
    "validate": run_validations,
    "ref-integrity": check_ref_integrity,
}

def main():
    if len(sys.argv) < 2:
        print("用法: python bo-data-inspector.py <命令> [boCode]")
        print(f"  命令: {', '.join(COMMANDS.keys())} | all")
        print("  示例: python bo-data-inspector.py drift")
        print("        python bo-data-inspector.py profile customers")
        print("        python bo-data-inspector.py all customers")
        sys.exit(1)

    cmd = sys.argv[1]
    bo_code = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "all":
        print(f"\n{'#'*60}")
        print(f"#  全量检查: {bo_code or '所有BO'}")
        print(f"#{'#'*60}")
        detect_drift(bo_code)
        if bo_code:
            profile_data(bo_code)
            run_validations(bo_code)
            check_ref_integrity(bo_code)
        return

    if cmd not in COMMANDS:
        print(f"❌ 未知命令: {cmd}")
        print(f"   可用: {', '.join(COMMANDS.keys())} | all")
        sys.exit(1)

    COMMANDS[cmd](bo_code)


if __name__ == "__main__":
    main()
