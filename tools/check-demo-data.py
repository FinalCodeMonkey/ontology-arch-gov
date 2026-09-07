#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo-data 示例数据 vs BO 元数据字段一致性检查工具。

逐个文件检查 demo-data/*.sample.json 中的字段是否与对应 BO model fragment
中定义的属性（attributes）对齐。

输出三类问题：
  [MISSING_IN_META]  示例数据有字段，但元数据中未定义
  [MISSING_IN_DATA]  元数据有字段，但示例数据中缺失（仅检查必填/业务关键字段）
  [TYPE_MISMATCH]    字段类型不匹配（如元数据 LONG 但数据是字符串）

用法:
  python check-demo-data.py                          # 检查 demo-data/education/
  python check-demo-data.py --dir internet           # 检查 demo-data/internet/
  python check-demo-data.py --dir education          # 显式指定 education
"""

import json
import os
import sys
from pathlib import Path
from collections import OrderedDict

# ── 路径 ──
BASE = Path(__file__).resolve().parent
DESIGN_TIME = BASE.parent / "metadata" / "design-time"
DEMO_DATA = BASE / "demo-data"

# ── demo-data 文件 → BO 映射 ──
FILE_BO_MAP = OrderedDict([
    ("customers.sample.json",       "customers"),
    ("opportunities.sample.json",   "opportunities"),
    ("sales-activities.sample.json","sales-activities"),
    ("exchange-rates.sample.json",  "exchange-rates"),
    ("competitors.sample.json",     "competitors"),
    ("sales-targets.sample.json",   "sales-targets"),
    ("contacts.sample.json",        "contacts"),
    ("scenes.sample.json",          "scenes"),
    # temporal-events 是推理引擎专用事件流，不对应单一 BO
])

# ── 元数据中需要跳过的系统/审计字段（不要求 demo-data 必须包含）──
SYSTEM_FIELDS = {
    "is_deleted", "created_time", "updated_time",
    "created_by", "updated_by", "tenant_code",
}

# ── demo-data 中允许的元数据字段（非 BO 属性）──
DEMO_META_FIELDS = {"_scenario", "_scenarioDescription", "records", "stageHistory", "stageEvents", "activityEvents"}

# ── 聚合子实体嵌套字段名（demo-data 中用嵌套数组表示子实体，非 BO 属性）──
AGGREGATE_CHILD_FIELDS = {
    "scene_products", "annual_estimates",  # scenes 子实体
    "scene_rival_summaries", "scene_rival_details",
    "scene_team_members",
}

# ── 类型检查规则 ──
TYPE_RULES = {
    "LONG":    lambda v: isinstance(v, int) and not isinstance(v, bool) or v is None,
    "STRING":  lambda v: isinstance(v, str) or v is None or isinstance(v, bool),
    "INTEGER": lambda v: isinstance(v, int) and not isinstance(v, bool) or v is None,
    "DECIMAL": lambda v: isinstance(v, (int, float)) or v is None,
    "BOOLEAN": lambda v: isinstance(v, bool) or v is None,
    "DATE":    lambda v: v is None or (isinstance(v, str) and len(v) >= 8),
    "DATETIME":lambda v: v is None or (isinstance(v, str) and "T" in v),
}


def load_json(path):
    with open(str(path), "r", encoding="utf-8-sig") as f:
        return json.load(f)


def get_root_attributes(bo_code):
    """从 BO model fragment 中提取根实体的所有属性 code → type 映射"""
    frag_path = DESIGN_TIME / bo_code / "fragments" / f"{bo_code}-model.fragment.json"
    if not frag_path.exists():
        return None, f"Fragment not found: {frag_path}"
    frag = load_json(frag_path)
    entities = frag.get("content", {}).get("entities", [])
    root_entity = None
    for ent in entities:
        if ent.get("aggregateRole") == "ROOT" or ent.get("isPrimary") is True:
            root_entity = ent
            break
    if not root_entity:
        return None, "No ROOT entity found"
    attrs = OrderedDict()
    for a in root_entity.get("attributes", []):
        attrs[a["code"]] = a.get("type", "STRING")
    return attrs, None


def get_all_entity_attrs(bo_code):
    """获取 BO 所有实体（含子实体）的属性 code → type 映射"""
    frag_path = DESIGN_TIME / bo_code / "fragments" / f"{bo_code}-model.fragment.json"
    if not frag_path.exists():
        return None, f"Fragment not found: {frag_path}"
    frag = load_json(frag_path)
    entities = frag.get("content", {}).get("entities", [])
    all_attrs = OrderedDict()
    for ent in entities:
        for a in ent.get("attributes", []):
            code = a["code"]
            if code not in all_attrs:
                all_attrs[code] = a.get("type", "STRING")
    return all_attrs, None


def check_file(filename, bo_code, demo_dir=None):
    """检查单个 demo-data 文件"""
    if demo_dir is None:
        demo_dir = DEMO_DATA
    print(f"\n{'='*80}")
    print(f"📋 检查: {filename}  ↔  BO: {bo_code}")
    print(f"{'='*80}")

    data_path = demo_dir / filename
    if not data_path.exists():
        print(f"  ❌ 文件不存在: {data_path}")
        return

    data = load_json(data_path)

    # 获取元数据属性
    root_attrs, err = get_root_attributes(bo_code)
    if err:
        print(f"  ❌ 元数据加载失败: {err}")
        return

    all_attrs, _ = get_all_entity_attrs(bo_code)

    # 提取 records
    records = data.get("records", [])
    if not records:
        # temporal-events 等特殊文件
        print(f"  ⚠️  无 records 字段（可能是事件流文件，跳过字段级检查）")
        _check_temporal_events(data, all_attrs)
        return

    print(f"  记录数: {len(records)}")
    print(f"  元数据根实体字段数: {len(root_attrs)}")
    print(f"  元数据全部实体字段数: {len(all_attrs)}")

    # 收集所有数据字段
    all_data_fields = set()
    for rec in records:
        all_data_fields.update(rec.keys())

    # ── 1. MISSING_IN_META: 数据有但元数据没有 ──
    missing_in_meta = []
    for field in sorted(all_data_fields):
        if field not in all_attrs and field not in AGGREGATE_CHILD_FIELDS:
            missing_in_meta.append(field)

    if missing_in_meta:
        print(f"\n  🔴 [MISSING_IN_META] 数据中有 {len(missing_in_meta)} 个字段在元数据中未定义:")
        for f in missing_in_meta:
            print(f"     • {f}")
    else:
        print(f"\n  ✅ [MISSING_IN_META] 无 — 所有数据字段均在元数据中定义")

    # ── 2. MISSING_IN_DATA: 元数据有但数据没有（仅检查非系统字段）──
    missing_in_data = []
    for code, typ in root_attrs.items():
        if code in SYSTEM_FIELDS:
            continue
        if code not in all_data_fields:
            missing_in_data.append((code, typ))

    if missing_in_data:
        print(f"\n  🟡 [MISSING_IN_DATA] 元数据根实体有 {len(missing_in_data)} 个非系统字段在数据中缺失:")
        for code, typ in missing_in_data:
            print(f"     • {code} ({typ})")
    else:
        print(f"\n  ✅ [MISSING_IN_DATA] 无 — 所有根实体非系统字段均在数据中存在")

    # ── 3. TYPE_MISMATCH: 类型不匹配 ──
    type_issues = []
    for rec in records:
        for field, value in rec.items():
            if field not in all_attrs:
                continue
            if value is None:
                continue
            expected_type = all_attrs[field]
            checker = TYPE_RULES.get(expected_type)
            if checker and not checker(value):
                type_issues.append((field, expected_type, value, type(value).__name__))

    if type_issues:
        print(f"\n  🟠 [TYPE_MISMATCH] 发现 {len(type_issues)} 个类型不匹配:")
        seen = set()
        for field, exp_type, val, actual_type in type_issues:
            key = f"{field}|{exp_type}|{actual_type}"
            if key not in seen:
                seen.add(key)
                display_val = str(val)[:60]
                print(f"     • {field}: 期望 {exp_type}, 实际 {actual_type} (示例值: {display_val})")
    else:
        print(f"\n  ✅ [TYPE_MISMATCH] 无 — 所有字段类型匹配")

    # ── 4. 检查 stageHistory / stageEvents 等特殊结构 ──
    if "stageHistory" in data:
        print(f"\n  📝 [stageHistory] {len(data['stageHistory'])} 条阶段历史记录")
        _check_stage_history(data["stageHistory"], all_attrs)

    if "stageEvents" in data or "activityEvents" in data:
        _check_temporal_events(data, all_attrs)


def _check_stage_history(stage_history, all_attrs):
    """检查 stageHistory 结构"""
    expected_fields = {"opportunity_id", "from_stage", "to_stage", "promoter", "event_time",
                       "predict_category_snapshot", "amount_snapshot", "status_snapshot"}
    for i, rec in enumerate(stage_history):
        missing = expected_fields - set(rec.keys())
        if missing:
            print(f"     记录 #{i}: 缺少字段 {missing}")


def _check_temporal_events(data, all_attrs):
    """检查 temporal-events 结构"""
    stage_events = data.get("stageEvents", [])
    activity_events = data.get("activityEvents", [])

    if stage_events:
        print(f"\n  📝 [stageEvents] {len(stage_events)} 条阶段事件")
        expected_fields = {"boCode", "objectId", "eventType", "fromState", "toState", "eventTime", "actorId", "snapshot"}
        for i, ev in enumerate(stage_events):
            missing = expected_fields - set(ev.keys())
            if missing:
                print(f"     事件 #{i}: 缺少字段 {missing}")

    if activity_events:
        print(f"\n  📝 [activityEvents] {len(activity_events)} 条活动事件")
        expected_fields = {"boCode", "objectId", "eventType", "eventTime", "snapshot"}
        for i, ev in enumerate(activity_events):
            missing = expected_fields - set(ev.keys())
            if missing:
                print(f"     事件 #{i}: 缺少字段 {missing}")


def main():
    # 解析 --dir 参数，默认 education
    subdir = "education"
    args = sys.argv[1:]
    if "--dir" in args:
        idx = args.index("--dir")
        if idx + 1 < len(args):
            subdir = args[idx + 1]

    demo_dir = DEMO_DATA / subdir

    print("╔══════════════════════════════════════════════════════════════╗")
    print(f"║   Demo-Data vs BO 元数据字段一致性检查                       ║")
    print(f"║   目录: demo-data/{subdir:<44}║")
    print("╚══════════════════════════════════════════════════════════════╝")

    total_files = 0

    for filename, bo_code in FILE_BO_MAP.items():
        total_files += 1
        check_file(filename, bo_code, demo_dir)

    # temporal-events 单独处理
    te_path = demo_dir / "temporal-events.sample.json"
    if te_path.exists():
        total_files += 1
        print(f"\n{'='*80}")
        print(f"📋 检查: temporal-events.sample.json  ↔  (事件流，跨BO)")
        print(f"{'='*80}")
        data = load_json(te_path)
        all_attrs = {}
        # 合并 opportunities + sales-activities 的属性
        for bo in ["opportunities", "sales-activities"]:
            attrs, _ = get_all_entity_attrs(bo)
            if attrs:
                all_attrs.update(attrs)
        _check_temporal_events(data, all_attrs)

    print(f"\n{'='*80}")
    print(f"📊 总结: 检查了 {total_files} 个文件")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
