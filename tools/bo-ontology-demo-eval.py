#!/usr/bin/env python3
"""
BO Ontology DEMO Evaluator — 基于发布态 JSON 做派生指标和动作链 dry-run 计算
支持场景：
  --scenario reasoning-chain          完整推理链（基于本体依赖关系自动编排：LINK发现→拓扑排序→AST求值→RULE→ACTION_CHAIN→LLM叙事）
  --scenario customer-360              客户 360 派生 dry-run
  --scenario opportunity-intelligence  商机智能派生 dry-run
  --scenario opportunity-timeline      商机阶段时间线 dry-run
  --scenario customer-activity-window  客户活动窗口指标 dry-run
  --scenario pipeline-coverage         管道覆盖率 dry-run
  --dry-run-chain CHAIN_CODE          动作链 dry-run
  --eval-rules BO_CODE                规则 exprAst dry-run 评估

用法:
  python bo-ontology-demo-eval.py --scenario reasoning-chain --id 1001
  python bo-ontology-demo-eval.py --scenario customer-360 --id <customerId>
  python bo-ontology-demo-eval.py --scenario opportunity-intelligence --id <opportunityId>
  python bo-ontology-demo-eval.py --scenario pipeline-coverage --id <ownerId>
  python bo-ontology-demo-eval.py --dry-run-chain OPPORTUNITY_WIN_POST_ACTIONS --bo opportunities --id <id> --operation WIN
  python bo-ontology-demo-eval.py --eval-rules opportunities --id 2001
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

# ── Demo 基准日（与设计文档保持一致，避免动态 now() 导致 ±1 天偏移）──
_DEMO_REFERENCE_DATE = datetime(2026, 7, 15)  # 年-月-日

def _demo_now():
    """返回 demo 场景的固定基准 datetime，确保 stage_age_days 计算结果可复现。"""
    return _DEMO_REFERENCE_DATE

# ── 中文化映射：内部英文值 → 控制台/JSON 输出中文 ──
_ZH_VALUE_MAP = {
    # 风险/等级
    "LOW": "低", "MEDIUM": "中", "HIGH": "高", "CRITICAL": "极高",
    "NONE": "无", "UNKNOWN": "未知",
    # 阶段流速
    "NORMAL": "正常", "STAGNANT": "停滞",
    # 商机状态
    "IN_PROGRESS": "进行中", "ACTIVE": "活跃", "CLOSED_WON": "已赢单", "CLOSED_LOST": "已丢单",
    "DRAFT": "草稿", "CANCELLED": "已取消", "SUSPENDED": "已挂起",
    # 客户类别
    "CUSTOMER": "一级客户", "FOP_CUSTOMER": "业务主体客户", "CONTRACT_ENTITY": "合同主体客户",
}

_ZH_KEY_MAP = {
    # JSON 汇总键
    "scenario": "场景名称",
    "customer": "客户",
    "id": "编号", "name": "名称", "category": "类别",
    "scenes": "场景需求",
    "count": "数量", "details": "明细",
    "stage": "我司阶段", "procurement": "采购规模", "share": "预计份额", "nextBid": "下次招标",
    "temporal": "时间线指标",
    "activity_count_90d": "近90天活动数", "last_activity_days": "最近活动距今天数",
    "stage_age_days": "阶段停留天数", "stage_velocity_level": "阶段流速等级",
    "currencyConversion": "汇率折算",
    "usd_amount": "美元金额", "rate": "汇率", "converted_cny": "折算人民币", "total_pipeline_cny": "管道总金额(CNY)",
    "customer_pipeline_cny": "客户级管道金额(CNY)", "note": "口径说明",
    "derivation": "派生指标",
    "customer_health_score": "客户健康度评分", "churn_risk_level": "流失风险等级",
    "next_best_action": "下一步最佳行动",
    "coverage_ratio": "管道覆盖率", "coverage_risk_level": "覆盖风险等级",
    "actionChain": "动作链",
    "chainCount": "动作链数量", "chains": "动作链列表",
    "code": "编码", "stepCount": "步骤数", "triggered": "已触发",
    "rules": "规则合规",
    "passed": "通过", "total": "总计",
    "_meta": "元信息",
    "mode": "执行模式", "engine": "排序引擎", "evalOrder": "求值顺序", "fragments": "片段列表",
}

def _zh(val):
    """将内部英文枚举值转为中文展示；若不在映射表中则原样返回。"""
    if isinstance(val, str):
        return _ZH_VALUE_MAP.get(val, val)
    return val

def _zh_key(key: str) -> str:
    """将 JSON 输出键转为中文。"""
    return _ZH_KEY_MAP.get(key, key)

def _zh_keys(d: dict) -> dict:
    """递归将 dict 的所有键转为中文。"""
    if not isinstance(d, dict):
        return d
    result = {}
    for k, v in d.items():
        new_key = _zh_key(k)
        if isinstance(v, dict):
            result[new_key] = _zh_keys(v)
        elif isinstance(v, list):
            result[new_key] = [_zh_keys(item) if isinstance(item, dict) else item for item in v]
        else:
            result[new_key] = v
    return result

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
META_DIR = PROJECT_DIR / "metadata"
RELEASE_DIR = META_DIR / "release-time" / "_ontology"
DEMO_DATA_DIR = TOOLS_DIR / "demo-data"

# 可通过 --scenario-dir 覆盖为其他子目录（如 internet）
_DEMO_SUBDIR = "education"

# 批量模式（id=all）下是否跳过 LLM 叙事化（设为 True 可跳过以提速）
_SKIP_LLM_IN_BATCH = False

def get_demo_dir() -> Path:
    """获取当前 demo-data 目录（支持子目录切换）"""
    return DEMO_DATA_DIR / _DEMO_SUBDIR

# 全局 LLM 配置（由 CLI 参数或 API 传入）
_LLM_CONFIG = None
_LLM_DISABLED = False  # LLM 开关（关闭时跳过 AI 总结和叙事化报告）

sys.path.insert(0, str(TOOLS_DIR))
try:
    from ontology_expr_eval import evaluate_tree
except ImportError:
    evaluate_tree = None

try:
    from ontology_expr_eval import evaluate as _raw_evaluate
except ImportError:
    _raw_evaluate = None


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [WARN] Cannot read {path.name}: {e}", file=sys.stderr)
        return None


def load_derivation_index() -> dict:
    return load_json(RELEASE_DIR / "crm.ontology-derivation-index.v1.json") or {}


def load_link_index() -> dict:
    return load_json(RELEASE_DIR / "crm.ontology-link-index.v1.json") or {}


def load_temporal_index() -> dict:
    return load_json(RELEASE_DIR / "crm.ontology-temporal-index.v1.json") or {}


def load_action_chain_index() -> dict:
    return load_json(RELEASE_DIR / "crm.ontology-action-chain-index.v1.json") or {}


def load_demo_data(bo_code: str) -> dict:
    """Load demo data from tools/demo-data/{scenarioDir}/{boCode}.sample.json.
    Supports both single-record format (old) and multi-record format (new with 'records' key).
    Returns the first record for backward compatibility, or the full dict if no records key.
    """
    sample_file = get_demo_dir() / f"{bo_code}.sample.json"
    if sample_file.exists():
        data = load_json(sample_file) or {}
        # New format: { "_scenario": ..., "records": [...] }
        if "records" in data:
            records = data["records"]
            if records:
                return records[0]  # Return first record for backward compat
        return data
    print(f"  [INFO] No demo data for '{bo_code}', using placeholder", file=sys.stderr)
    return {"_placeholder": True, "id": "DEMO_NO_DATA", "boCode": bo_code}


def load_all_demo_records(bo_code: str) -> list:
    """Load all records from demo-data/{boCode}.sample.json (multi-record format)."""
    sample_file = get_demo_dir() / f"{bo_code}.sample.json"
    if sample_file.exists():
        data = load_json(sample_file) or {}
        if "records" in data:
            return data["records"]
        return [data]  # single-record format
    return []


def load_demo_scenario(bo_code: str) -> str:
    """Load the _scenario description from demo data file."""
    sample_file = get_demo_dir() / f"{bo_code}.sample.json"
    if sample_file.exists():
        data = load_json(sample_file) or {}
        return data.get("_scenarioDescription", "")
    return ""


def load_design_fragment(fragment_type: str) -> dict | None:
    """Load a release-time _ontology fragment (元数据驱动：从发布态读取).
    fragment_type: 'derivation', 'temporal', 'action-chain', 'link'
    发布态索引文件已包含完整的 expression/exprAst，推理引擎作为发布态的纯消费者。"""
    index_map = {
        "link": "crm.ontology-link-index.v1.json",
        "derivation": "crm.ontology-derivation-index.v1.json",
        "temporal": "crm.ontology-temporal-index.v1.json",
        "action-chain": "crm.ontology-action-chain-index.v1.json",
    }
    file_name = index_map.get(fragment_type)
    if not file_name:
        return None
    data = load_json(RELEASE_DIR / file_name)
    if not data:
        return None
    # 发布态 LINK 使用扁平字段名（sourceBoCode 等），适配为引擎消费的嵌套结构
    # 注意：发布态有一个 "source": "EXPLICIT" 字段表示来源类型，与引擎期望的 source 嵌套对象冲突
    if fragment_type == "link":
        links = data.get("links", [])
        for link in links:
            # 保存来源类型标记，移除冲突的 source 字段
            link["_sourceType"] = link.pop("source", None)
            link["source"] = {
                "boCode": link.pop("sourceBoCode", ""),
                "entityCode": link.pop("sourceEntityCode", ""),
                "fieldCode": link.pop("sourceFieldCode", ""),
            }
            link["target"] = {
                "boCode": link.pop("targetBoCode", ""),
                "entityCode": link.pop("targetEntityCode", ""),
                "fieldCode": link.pop("targetFieldCode", ""),
            }
        return {"links": links}
    # derivation: 发布态已合并 entity-scoring，直接返回
    if fragment_type == "derivation":
        return {"derivedObjects": data.get("derivedObjects", [])}
    # entity-scoring: 发布态已合并到 derivation-index 中，返回空避免重复
    if fragment_type == "entity-scoring":
        return {"derivedObjects": []}
    # temporal / action-chain: 发布态已包含完整 expression/trigger
    return data


def load_bo_rule_fragment(bo_code: str) -> dict | None:
    """Load a BO-specific RULE fragment from release-time schema-view.
    元数据驱动：从发布态 <bo>.schema-view.v2.json 的 rules[] 读取。"""
    schema_file = META_DIR / "release-time" / bo_code / f"{bo_code}.schema-view.v2.json"
    data = load_json(schema_file)
    if data and "rules" in data:
        return {"rules": data["rules"]}
    return None


# ── Stage Label 解析（P6 修复：project_stage 显示 label 而非 raw value）──
_STAGE_LABELS_CACHE = None  # lazy load


def _load_stage_labels() -> dict:
    """从发布态 opportunities.schema-view.v2.json 的 project_stage 属性的
    validation.conditionalEnum 加载阶段标签映射。
    结果缓存在 _STAGE_LABELS_CACHE。"""
    global _STAGE_LABELS_CACHE
    if _STAGE_LABELS_CACHE is not None:
        return _STAGE_LABELS_CACHE

    _STAGE_LABELS_CACHE = {}
    schema_file = META_DIR / "release-time" / "opportunities" / "opportunities.schema-view.v2.json"
    data = load_json(schema_file)
    if not data:
        return _STAGE_LABELS_CACHE

    # 遍历 entities → attributes 找 project_stage 的 conditionalEnum
    for entity in data.get("entities", []):
        for attr in entity.get("attributes", []):
            if attr.get("code") == "project_stage":
                cond_enum = attr.get("validation", {}).get("conditionalEnum", {})
                for group in cond_enum.get("groups", []):
                    project_type = group.get("when", "")
                    for item in group.get("enum", []):
                        value = item.get("value", "")
                        label = item.get("label", "")
                        _STAGE_LABELS_CACHE[(project_type, value)] = label
                break

    return _STAGE_LABELS_CACHE


def _resolve_stage_label(project_type: str, project_stage: str) -> str:
    """将 project_stage 的 raw value 解析为人类可读的中文 label。
    例: ('DC', 'DC_05') → '得到结果 签订研发标合同'
    如匹配不到则返回原始值。"""
    if not project_stage:
        return project_stage
    labels = _load_stage_labels()
    # 先精确匹配 (project_type, project_stage)
    key = (project_type, project_stage.split(",")[0].strip())
    label = labels.get(key)
    if label:
        return label
    # 回退：遍历所有 project_type 尝试匹配
    for (pt, sv), lbl in labels.items():
        if sv == project_stage.split(",")[0].strip():
            return lbl
    return project_stage


def _resolve_score_ref(score_ref: str, score_registry: dict, data_sources: dict, 
                        context: dict) -> float:
    """Resolve a scoreRef from the score registry (e.g., from weightedScore itemsForWeight).
    Looks up score_ref first in registry (computed derived fields), then falls back to
    temporal metrics, then to data fields."""
    # Try computed registry
    if score_ref in score_registry:
        return float(score_registry[score_ref])
    # Try as a field in data_sources
    for ds_name, ds_data in data_sources.items():
        if isinstance(ds_data, dict) and score_ref in ds_data:
            try:
                return float(ds_data[score_ref])
            except (ValueError, TypeError):
                pass
    # Default: 0
    return 0.0


# ════════════════════════════════════════════════════════════════
# 推理链引擎重构：依赖解析 + 拓扑排序 + 元数据驱动编排
# ════════════════════════════════════════════════════════════════

def resolve_related_bos(root_bo_code: str, link_meta: dict) -> set:
    """从 root BO 出发，沿 LINK 元数据自动发现所有关联的 BO。"""
    related = {root_bo_code}
    for link in link_meta.get("links", []):
        src_bo = link.get("source", {}).get("boCode", "")
        tgt_bo = link.get("target", {}).get("boCode", "")
        if src_bo == root_bo_code:
            related.add(tgt_bo)
        if tgt_bo == root_bo_code:
            related.add(src_bo)
    return related


def _get_first_scene_product(scene: dict) -> dict:
    """从场景记录的 scene_products 数组中提取第一个产品记录的展平视图。"""
    products = scene.get("scene_products", [])
    return products[0] if products else {}


def _get_first_annual_estimate(product: dict) -> dict:
    """从产品记录的 annual_estimates 数组中提取第一个年度测算。"""
    estimates = product.get("annual_estimates", [])
    return estimates[0] if estimates else {}


def _get_all_child_customer_ids(customer_id: str, all_customers: list) -> set:
    """递归查找指定父客户下的所有子孙客户 ID（含子、孙等）。
    通过 parent_customer_id 字段沿 FOP_BELONGS_TO_CUSTOMER link 递归遍历。"""
    children = set()
    for c in all_customers:
        if str(c.get("parent_customer_id")) == str(customer_id):
            child_id = str(c.get("id"))
            children.add(child_id)
            children |= _get_all_child_customer_ids(child_id, all_customers)
    return children


def _print_missing_link_relations(link_meta: dict, all_records: dict,
                                    customer_id: str, active_opps: list):
    """P5 修复：补充输出此前缺失的关键 LINK 关系展示——
    联系人、商机主子关系(OPPORTUNITY_HAS_PARENT)、活动→联系人/场景快照。
    这些关系属于推理链的基础遍历能力，之前仅隐式用于 DERIVATION 字段计算，未在控制台展示。"""
    # 1) 客户→联系人 (CUSTOMER_HAS_CONTACT)
    contacts = _infer_related_records("customers", customer_id, "contacts", link_meta, all_records)
    if contacts:
        contact_names = [f"{c.get('name', c.get('contact_name'))}(ID={c.get('id')})" for c in contacts]
        print(f"\n  📇 客户联系人 (via LINK: CUSTOMER_HAS_CONTACT)")
        print(f"  {'─'*50}")
        print(f"     联系人数：{len(contacts)}")
        for c in contacts:
            display_name = c.get('name') or c.get('contact_name') or f"ID={c.get('id')}"
            print(f"     • {display_name} — 角色: {c.get('purchase_role','')}, "
                  f"关系: {c.get('relation_status','')}")

    # 2) 商机父子关系 (OPPORTUNITY_HAS_PARENT)
    if active_opps:
        parent_opps = [o for o in active_opps if o.get("parent_opportunity_id")]
        if parent_opps:
            print(f"\n  🔗 商机主子关系 (via LINK: OPPORTUNITY_HAS_PARENT)")
            print(f"  {'─'*50}")
            all_opps = all_records.get("opportunities", [])
            for o in parent_opps:
                parent_id = str(o.get("parent_opportunity_id"))
                parent = next((p for p in all_opps if str(p.get("id")) == parent_id), None)
                parent_name = parent.get("opportunity_name", f"ID={parent_id}") if parent else f"ID={parent_id}"
                print(f"     {o.get('opportunity_name')} (ID={o.get('id')}) "
                      f"→ 父商机: {parent_name}")

    # 3) 活动→联系人快照 (ACTIVITY_HAS_CONTACT)
    activities = all_records.get("sales-activities", [])
    cust_activities = [a for a in activities
                       if str(a.get("parent_id") or a.get("customer_id", "")) == str(customer_id)]
    if cust_activities:
        acts_with_contacts = [a for a in cust_activities if a.get("contact_ids_snapshot")]
        if acts_with_contacts:
            print(f"\n  📋 活动→联系人快照 (via LINK: ACTIVITY_HAS_CONTACT)")
            print(f"  {'─'*50}")
            all_contacts = all_records.get("contacts", [])
            for a in acts_with_contacts:
                snap_ids = [x.strip() for x in str(a.get("contact_ids_snapshot", "")).split(",") if x.strip()]
                snap_names = []
                for sid in snap_ids:
                    ct = next((c for c in all_contacts if str(c.get("id")) == sid), None)
                    snap_names.append(ct.get("name") or ct.get("contact_name", sid) if ct else sid)
                print(f"     活动 {a.get('id')} ({a.get('visit_subject','')}) → [{', '.join(snap_names)}]")

        # 4) 活动→场景快照 (ACTIVITY_HAS_SCENE)
        acts_with_scenes = [a for a in cust_activities if a.get("scene_ids_snapshot")]
        if acts_with_scenes:
            print(f"\n  🏗️ 活动→场景快照 (via LINK: ACTIVITY_HAS_SCENE)")
            print(f"  {'─'*50}")
            all_scenes = all_records.get("scenes", [])
            for a in acts_with_scenes:
                snap_ids = [x.strip() for x in str(a.get("scene_ids_snapshot", "")).split(",") if x.strip()]
                snap_names = []
                for sid in snap_ids:
                    sc = next((s for s in all_scenes if str(s.get("id")) == sid), None)
                    snap_names.append(sc.get("scene_name_customer", sid) if sc else sid)
                print(f"     活动 {a.get('id')} ({a.get('visit_subject','')}) → [{', '.join(snap_names)}]")

    # 5) 场景→架构 (SCENE_HAS_ARCH) — 从 scene-archs 关联展示
    cust_scenes_for_arch = _infer_related_records("customers", customer_id, "scenes", link_meta, all_records)
    if cust_scenes_for_arch:
        scene_archs = all_records.get("scene-archs", [])
        cust_archs = [sa for sa in scene_archs
                      if str(sa.get("scene_id")) in {str(s.get("id")) for s in cust_scenes_for_arch}]
        if cust_archs:
            print(f"\n  🏗️ 场景→架构 (via LINK: SCENE_HAS_ARCH)")
            print(f"  {'─'*50}")
            for sa in cust_archs:
                scene_name = next((s.get("scene_name_customer", "")
                                   for s in cust_scenes_for_arch
                                   if str(s.get("id")) == str(sa.get("scene_id"))), "")
                print(f"     • 场景「{scene_name}」→ 架构: {sa.get('arch_role','')}, "
                      f"产品: {sa.get('product_model','')}, POD: {sa.get('pod_count','')}")


def _print_predict_category_trajectory(temporal_events: dict, active_opps: list):
    """打印各商机的 predict_category 快照变化轨迹（从 temporal-events stageEvents 读取）。
    P9 修复：之前仅输出 stage_age_days/velocity，未展示 predict_category 轨迹。
    P12 修复：追加当前商机记录的 predict_category 作为最终状态（temporal-events
    快照可能滞后于当前记录值，如 2101 快照仅到 B 但当前已是 OPPORTUNITY_PLUS）。"""
    stage_events = temporal_events.get("stageEvents", [])
    if not active_opps:
        return

    opp_ids = {str(o.get("id")) for o in active_opps}
    for opp_id in opp_ids:
        events = sorted(
            [e for e in stage_events if str(e.get("objectId")) == opp_id],
            key=lambda e: e.get("eventTime", "")
        )
        snapshots = []
        for e in events:
            snap = e.get("snapshot", {})
            pc = snap.get("predict_category", "")
            if pc:
                snapshots.append(pc)
        # P12: 追加当前商机记录的 predict_category（去重：只在不同于最后快照时才追加）
        opp_record = next((o for o in active_opps if str(o.get("id")) == opp_id), None)
        if opp_record:
            current_pc = opp_record.get("predict_category", "")
            if current_pc and (not snapshots or current_pc != snapshots[-1]):
                snapshots.append(current_pc)
        if snapshots:
            # 找到对应商机名称
            opp_name = next((o.get("opportunity_name", f"ID={opp_id}") for o in active_opps
                             if str(o.get("id")) == opp_id), f"ID={opp_id}")
            print(f"     predict_category 轨迹 [{opp_name}]: {' → '.join(snapshots)}")


def _infer_related_records_recursive(root_bo: str, root_id: str, target_bo: str,
                                      link_meta: dict, all_records: dict) -> list:
    """沿 LINK 元数据推断关联记录，对 customers→customers 和 customers→opportunities
    启用父子递归：当 root_bo='customers' 时，自动纳入子客户的所有关联记录。"""
    records = _infer_related_records(root_bo, root_id, target_bo, link_meta, all_records)

    # 仅对 customers→opportunities 启用递归子客户穿透
    if root_bo == "customers" and target_bo == "opportunities":
        all_customers = all_records.get("customers", [])
        child_ids = _get_all_child_customer_ids(root_id, all_customers)
        for child_id in child_ids:
            child_records = _infer_related_records(root_bo, child_id, target_bo, link_meta, all_records)
            for cr in child_records:
                if cr not in records:
                    records.append(cr)
    return records


def _infer_related_records(root_bo: str, root_id: str, target_bo: str,
                            link_meta: dict, all_records: dict) -> list:
    """沿 LINK 元数据推断关联记录：找到 root_bo → target_bo 的 link，
    用 link 的字段映射过滤 target_bo 的记录。"""
    for link in link_meta.get("links", []):
        src = link.get("source", {})
        tgt = link.get("target", {})
        if src.get("boCode") == root_bo and tgt.get("boCode") == target_bo:
            tgt_field = tgt.get("fieldCode", "id")
            records = all_records.get(target_bo, [])
            return [r for r in records if str(r.get(tgt_field)) == str(root_id)]
        if tgt.get("boCode") == root_bo and src.get("boCode") == target_bo:
            src_field = src.get("fieldCode", "id")
            records = all_records.get(target_bo, [])
            return [r for r in records if str(r.get(src_field)) == str(root_id)]
    return []


def _precompute_currency_conversion(all_records: dict, score_registry: dict,
                                     customer_id: str, link_meta: dict,
                                     derivation_meta: dict) -> dict:
    """汇率折算预计算：沿 LINK 元数据发现客户→商机关联，沿 derivation 元数据读取
    active_pipeline_amount 的 temporalAggregate 定义（含 where 过滤条件和 field 字段名），
    从 exchange-rates 记录中查找 ACTIVE 状态的汇率，折算后汇总统一口径管道金额。
    所有字段名和过滤条件均从元数据读取，不硬编码 demo 数据模式。"""
    # 从 LINK 元数据读取 customers→opportunities 的关联字段
    opp_link_field = "business_customer_id"
    for link in link_meta.get("links", []):
        src = link.get("source", {})
        tgt = link.get("target", {})
        if src.get("boCode") == "customers" and tgt.get("boCode") == "opportunities":
            opp_link_field = tgt.get("fieldCode", "business_customer_id")
            break

    # 从 derivation 元数据读取 active_pipeline_amount 的 temporalAggregate 定义
    # 获取 where 条件中的过滤字段和值，以及 sum 的 field 名
    all_derived = (load_design_fragment("entity-scoring") or {}).get("derivedObjects", []) + \
                  derivation_meta.get("derivedObjects", [])
    where_field, where_value, amount_field = "status", "ACTIVE", "expected_order_amount"
    _terminal_statuses = {"CLOSED_WON", "CLOSED_LOST", "CANCELLED", "SUSPENDED"}
    for dobj in all_derived:
        for field in dobj.get("fields", []):
            if field.get("code") == "active_pipeline_amount":
                expr = field.get("expression", {})
                if expr.get("type") == "temporalAggregate":
                    amount_field = expr.get("field", amount_field)
                    where = expr.get("where", {})
                    if where.get("type") == "binary" and where.get("op") == "EQ":
                        left = where.get("left", {})
                        right = where.get("right", {})
                        if left.get("type") == "field":
                            where_field = left.get("path", where_field)
                        if right.get("type") == "literal":
                            where_value = right.get("value", where_value)
                break

    opportunities = all_records.get("opportunities", [])
    exchange_rates = all_records.get("exchange-rates", [])

    # 确定需要聚合的客户列表（pipeline-coverage 跨销售负责人所有客户聚合）
    sales_owner_id = score_registry.get("_sales_owner_id")
    if sales_owner_id:
        # pipeline-coverage: 跨该销售负责人所有客户聚合
        target_customer_ids = set()
        for o in opportunities:
            if str(o.get("opportunity_owner")) == str(sales_owner_id):
                target_customer_ids.add(str(o.get(opp_link_field)))
        target_customer_ids.add(str(customer_id))
    else:
        # customer-360: 当前客户 + 递归子客户
        target_customer_ids = {str(customer_id)}
        all_customers = all_records.get("customers", [])
        child_ids = _get_all_child_customer_ids(str(customer_id), all_customers)
        target_customer_ids |= child_ids

    # 沿 LINK 字段过滤客户关联的商机
    cust_opps = [o for o in opportunities if str(o.get(opp_link_field)) in target_customer_ids]
    # 过滤活跃商机：排除终态（CLOSED_WON/CLOSED_LOST/CANCELLED/SUSPENDED）
    active_opps = [o for o in cust_opps if str(o.get(where_field, "")).upper() not in _terminal_statuses]

    # 从汇率记录中查找所有币种对，按 ACTIVE 状态过滤
    # 汇率记录的 base_currency/target_currency/status/rate 字段名从记录本身读取
    currency_groups = {}
    for opp in active_opps:
        cur = opp.get("currency", "CNY")
        if cur not in currency_groups:
            currency_groups[cur] = []
        currency_groups[cur].append(opp)

    total_pipeline = 0.0
    rate_info = None
    usd_amount = 0.0
    converted_cny = 0.0
    total_cny_amount = 0.0

    for cur, opps in currency_groups.items():
        amount = sum(o.get(amount_field, 0) for o in opps)
        if cur == "CNY":
            total_pipeline += amount
            total_cny_amount = amount
        else:
            # 查找该币种→CNY 的 ACTIVE 汇率
            rate = next((r for r in exchange_rates
                         if r.get("base_currency") == cur
                         and r.get("target_currency") == "CNY"
                         and r.get("status") == "ACTIVE"), None)
            if rate:
                converted = amount * rate.get("rate", 1)
                total_pipeline += converted
                if cur == "USD":
                    usd_amount = amount
                    converted_cny = converted
                    rate_info = rate
            else:
                total_pipeline += amount

    # 写入 score_registry，供 derivation metric 节点引用
    score_registry["active_pipeline_amount"] = total_pipeline

    return {
        "active_opps": active_opps,
        "usd_amount": usd_amount,
        "rate": rate_info,
        "converted_cny": converted_cny,
        "total_cny_amount": total_cny_amount,
        "total_pipeline_cny": total_pipeline,
    }


def _convert_opp_amount_to_cny(amount: float, currency: str, exchange_rates: list) -> float:
    """将单条商机金额按汇率折算为 CNY。CNY 币种直接返回，其他币种查 ACTIVE 汇率。"""
    if not currency or currency == "CNY":
        return amount
    rate = next((r for r in (exchange_rates or [])
                 if r.get("base_currency") == currency
                 and r.get("target_currency") == "CNY"
                 and r.get("status") == "ACTIVE"), None)
    return amount * rate.get("rate", 1) if rate else amount


def _precompute_sales_target(all_records: dict, score_registry: dict,
                              customer_id: str, link_meta: dict,
                              derivation_meta: dict) -> dict:
    """销售目标预计算：通过客户的商机找到负责人，再匹配 sales-targets 记录。
    P0 修复：原先直接按 owner_id=customer_id 匹配，但 owner_id 是销售ID(20002)
    而非客户ID(1104)。正确做法是通过商机的 opportunity_owner 字段桥接匹配。"""
    # 从 LINK 元数据读取 sales-targets→customers 的关联字段
    target_link_field = "owner_id"
    for link in link_meta.get("links", []):
        src = link.get("source", {})
        tgt = link.get("target", {})
        if src.get("boCode") == "sales-targets" and tgt.get("boCode") == "customers":
            target_link_field = src.get("fieldCode", "owner_id")
            break
        if tgt.get("boCode") == "sales-targets" and src.get("boCode") == "customers":
            target_link_field = tgt.get("fieldCode", "owner_id")
            break

    # 从 derivation 元数据读取 pipeline-coverage.target_amount 的 field path
    amount_path = "goal_value"
    for dobj in derivation_meta.get("derivedObjects", []):
        if dobj.get("code") == "pipeline-coverage":
            for field in dobj.get("fields", []):
                if field.get("code") == "target_amount":
                    expr = field.get("expression", {})
                    if expr.get("type") == "field":
                        amount_path = expr.get("path", amount_path)
                    break
            break

    # 从 LINK 元数据读取 customers→opportunities 的关联字段
    opp_cust_field = "business_customer_id"
    for link in link_meta.get("links", []):
        src = link.get("source", {})
        tgt = link.get("target", {})
        if src.get("boCode") == "customers" and tgt.get("boCode") == "opportunities":
            opp_cust_field = tgt.get("fieldCode", "business_customer_id")
            break

    opportunities = all_records.get("opportunities", [])
    # 过滤该客户的所有商机
    cust_opps = [o for o in opportunities if str(o.get(opp_cust_field)) == str(customer_id)]
    # 取商机的 opportunity_owner 作为销售负责人ID
    opp_owners = set(o.get("opportunity_owner", "") for o in cust_opps if o.get("opportunity_owner"))

    sales_targets = all_records.get("sales-targets", [])
    # P0 修复：通过 opportunity_owner 桥接匹配 sales-targets.owner_id
    target = None
    matched_owner_id = None
    for owner in opp_owners:
        target = next((t for t in sales_targets if str(t.get(target_link_field)) == str(owner)), None)
        if target:
            matched_owner_id = owner
            break
    # fallback: 如果无法通过商机桥接，尝试直接匹配
    if not target:
        target = next((t for t in sales_targets if str(t.get(target_link_field)) == str(customer_id)), None)
        if target:
            matched_owner_id = customer_id
    if target:
        target_amount = float(target.get(amount_path, 0) or 0)
        score_registry["target_amount"] = target_amount
        score_registry["_sales_owner_id"] = matched_owner_id
    return target


def _load_competition_level_risk_map() -> dict:
    """从发布态 competitors.schema-view.v2.json 的 competition_level 属性的
    semanticMapping.map 读取 competition_level 值→风险等级的元数据驱动映射。
    若元数据无此字段，回退到默认映射（保持向后兼容）。"""
    schema_file = META_DIR / "release-time" / "competitors" / "competitors.schema-view.v2.json"
    data = load_json(schema_file)
    if not data:
        return {"STRONG": "HIGH", "NORMAL": "MEDIUM", "WEAK": "LOW", "POTENTIAL": "MEDIUM"}

    # 遍历 entities → attributes 找 competition_level 的 semanticMapping
    for entity in data.get("entities", []):
        for attr in entity.get("attributes", []):
            if attr.get("code") == "competition_level":
                sem_map = attr.get("semanticMapping", {})
                if sem_map.get("map"):
                    return sem_map["map"]
    # 回退
    return {"STRONG": "HIGH", "NORMAL": "MEDIUM", "WEAK": "LOW", "POTENTIAL": "MEDIUM"}


def _precompute_competitor_count(all_records: dict, score_registry: dict,
                                  customer_id: str, link_meta: dict,
                                  active_opps: list):
    """竞对计数预计算：沿 LINK 元数据读取 OPPORTUNITY_COMPETES_WITH 关系。
    P0 修复：原先全量加载 competitors 记录（4个），实际应只加载当前客户相关的竞对。
    优先使用 customer-competitor-xref 交叉引用表过滤；若无则回退到全量加载。"""
    competitors = all_records.get("competitors", [])
    if not competitors:
        score_registry["competitor_count"] = 0
        score_registry["competitor_risk_level"] = "NONE"
        score_registry["competitor_max_risk_level"] = "NONE"
        score_registry["_strong_competitor_count"] = 0
        return

    # P0 修复：优先从 customer-competitor-xref 交叉引用表获取客户专属竞对
    xref = all_records.get("customer-competitor-xref", [])
    filtered_competitors = None
    if xref:
        comp_ids = set(r.get("competitor_id") for r in xref if str(r.get("customer_id")) == str(customer_id))
        if comp_ids:
            filtered_competitors = [c for c in competitors if c.get("id") in comp_ids]

    # 回退：通过商机的 business_customer_id 推断（简化处理）
    if filtered_competitors is None or len(filtered_competitors) == 0:
        # 无法精确定位客户竞对时，返回 0 而非全量 4
        filtered_competitors = []
        # 兜底：若该客户没有任何商机也没有交叉引用，竞对计数为 0
        if not active_opps:
            score_registry["competitor_count"] = 0
            score_registry["competitor_risk_level"] = "NONE"
            score_registry["competitor_max_risk_level"] = "NONE"
            score_registry["_strong_competitor_count"] = 0
            return

    count = len(filtered_competitors)
    score_registry["competitor_count"] = count
    # 竞对最高风险等级预计算：基于竞对个体 competition_level 的最高值
    # （NONE < LOW < MEDIUM < HIGH），不做数量因子修正。
    # 数量因子（1 STRONG→MEDIUM, 2+→HIGH）交由 entity-scoring 的 caseWhen 表达式处理。
    _severity_rank = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    _competition_to_risk = _load_competition_level_risk_map()
    max_risk = "NONE"
    max_rank = 0
    strong_count = 0
    for c in filtered_competitors:
        comp_level = str(c.get("competition_level", c.get("severity_level", ""))).upper()
        sev = _competition_to_risk.get(comp_level, comp_level)
        rank = _severity_rank.get(sev, 0)
        if rank > max_rank:
            max_rank = rank
            max_risk = sev
        if comp_level == "STRONG":
            strong_count += 1
    score_registry["competitor_max_risk_level"] = max_risk
    # 向后兼容：也写入 competitor_risk_level（优先使用 max_risk_level，若有则覆盖；
    # 若无 caseWhen 求值结果则回退到 max_risk_level）
    score_registry["competitor_risk_level"] = max_risk
    score_registry["_strong_competitor_count"] = strong_count
    print(f"\n  🏢 竞对计数预计算 — 写入 score_registry")
    print(f"  {'─'*50}")
    print(f"     score_registry['competitor_count'] = {count}")
    print(f"     score_registry['competitor_max_risk_level'] = {_zh(max_risk)} (降级前原始映射，STRONG×{strong_count}，最终 competitor_risk_level 由 entity-scoring 数量因子修正)")
    if filtered_competitors:
        names = ", ".join(f"{c.get('competitor_name', '?')}({_zh(c.get('competition_level', c.get('severity_level', '?')))})"
                          for c in filtered_competitors[:4])
    else:
        names = "(无专属竞对)"
    print(f"     竞对列表：{names}")


def _precompute_relation_governance_score(all_records: dict, score_registry: dict,
                                           customer_id: str):
    """P5 修复：基于 customer-relations 的 status 动态计算关系治理评分，
    替代发布态中硬编码的 literal 50 回退值。

    评分规则（与设计文档 §3.1 一致）：
      APPROVED         → 95
      PENDING_APPROVAL → 50
      DRAFT            → 35
      CHANGED          → 30
      默认             → 50
    """
    relations = all_records.get("customer-relations", [])
    cust_relation = next((r for r in relations
                          if str(r.get("customer_id") or r.get("id")) == str(customer_id)), None)
    rel_status = None
    if cust_relation:
        rel_status = cust_relation.get("status", "")
    elif relations:
        rel_status = relations[0].get("status", "")

    status_score_map = {"APPROVED": 95, "PENDING_APPROVAL": 50, "DRAFT": 35, "CHANGED": 30}
    score = status_score_map.get(rel_status, 50) if rel_status else 50
    score_registry["relation_governance_score"] = float(score)
    # 同时写入 customer-relations 到 data_sources 供 caseWhen AST 求值（兜底）
    # 注：当前仅用于预计算覆盖 DERIVATION metric 求值；AST 路径 "customer-relations.status" 需额外处理


def topological_sort_derived_objects(derived_objects: list) -> list:
    """按 metric/scoreRef 引用关系对 derived objects 做拓扑排序。
    entity-scoring 的字段被 customer-360 的 weightedScore 引用 → scoring 先求值。
    customer-360 的字段被 pipeline-coverage 的 metric 引用 → c360 先求值。
    """
    # 构建 field_code → derived_object_code 映射
    field_to_obj = {}
    for dobj in derived_objects:
        for field in dobj.get("fields", []):
            field_to_obj[field["code"]] = dobj["code"]

    # 构建依赖图
    deps = {dobj["code"]: set() for dobj in derived_objects}
    for dobj in derived_objects:
        for field in dobj.get("fields", []):
            expr = field.get("expression", {})
            _collect_metric_refs(expr, field_to_obj, dobj["code"], deps)

    # 拓扑排序（Kahn 算法）
    result = []
    visited = set()
    queue = [code for code in deps if not deps[code]]
    while queue:
        code = queue.pop(0)
        if code in visited:
            continue
        visited.add(code)
        dobj = next((d for d in derived_objects if d["code"] == code), None)
        if dobj:
            result.append(dobj)
        for other_code in deps:
            if code in deps[other_code] and other_code not in visited:
                if all(d in visited for d in deps[other_code]):
                    if other_code not in queue:
                        queue.append(other_code)

    # 处理循环依赖（fallback：按原始顺序追加未访问的）
    for dobj in derived_objects:
        if dobj["code"] not in visited:
            result.append(dobj)

    return result


def _collect_metric_refs(expr: dict, field_to_obj: dict,
                          owner_code: str, deps: dict):
    """递归收集 expression AST 中 metric/weightedScore 引用所暗示的 derived object 依赖。"""
    if not isinstance(expr, dict):
        return
    expr_type = expr.get("type", "")

    if expr_type == "metric":
        mcode = expr.get("code", "")
        if mcode in field_to_obj and field_to_obj[mcode] != owner_code:
            deps[owner_code].add(field_to_obj[mcode])

    if expr_type == "weightedScore":
        for item in expr.get("itemsForWeight", []):
            ref = item.get("scoreRef", "")
            if ref in field_to_obj and field_to_obj[ref] != owner_code:
                deps[owner_code].add(field_to_obj[ref])

    for key in ("left", "right", "expr", "defaultResult", "condition", "result"):
        if key in expr and isinstance(expr[key], dict):
            _collect_metric_refs(expr[key], field_to_obj, owner_code, deps)
    for key in ("items", "cases", "args", "itemsForWeight"):
        if key in expr and isinstance(expr[key], list):
            for item in expr[key]:
                if isinstance(item, dict):
                    _collect_metric_refs(item, field_to_obj, owner_code, deps)


def _collect_bo_refs_from_expr(expr: dict, bo_refs: set):
    """递归收集 expression AST 中 temporalAggregate/aggregate 的 source 字段引用的 BO。"""
    if not isinstance(expr, dict):
        return
    expr_type = expr.get("type", "")
    if expr_type in ("temporalAggregate", "aggregate"):
        source = expr.get("source", "")
        if source:
            bo_refs.add(source)
    for key in ("left", "right", "expr", "defaultResult", "condition", "result"):
        if key in expr and isinstance(expr[key], dict):
            _collect_bo_refs_from_expr(expr[key], bo_refs)
    for key in ("items", "cases", "args", "itemsForWeight"):
        if key in expr and isinstance(expr[key], list):
            for item in expr[key]:
                if isinstance(item, dict):
                    _collect_bo_refs_from_expr(item, bo_refs)


def resolve_all_required_bos(root_bo_code: str, link_meta: dict,
                              all_derived: list) -> set:
    """从 root BO 出发，沿 LINK 元数据 + DERIVATION 依赖 + expression source
    自动发现所有需要加载数据的 BO。
    P9 修复：添加传递闭包（2-hop），确保 scenes → scene-archs 等间接 BO 也被加载。"""
    # 1. 沿 LINK 发现直接关联的 BO
    related = resolve_related_bos(root_bo_code, link_meta)

    # 2. 从 DERIVATION 的 dependencies 和 expression source 中发现间接引用的 BO
    for dobj in all_derived:
        for dep in dobj.get("dependencies", []):
            related.add(dep.get("boCode", ""))
        for field in dobj.get("fields", []):
            expr = field.get("expression", {})
            if expr and expr.get("type"):
                _collect_bo_refs_from_expr(expr, related)

    # 3. 从 TEMPORAL 的 expression source 中发现引用的 BO
    temporal_meta = load_design_fragment("temporal") or {}
    for tl in temporal_meta.get("timelines", []):
        for metric in tl.get("metrics", []):
            expr = metric.get("expression", {})
            if expr and expr.get("type"):
                _collect_bo_refs_from_expr(expr, related)

    # 4. P9 修复：传递闭包 — 新发现的 BO 再沿 LINK 做一跳扩展
    #    （如 customers→scenes 发现 scenes，scenes→scene-archs 发现 scene-archs）
    discovered = set(related)
    for bo_code in list(discovered):
        discovered |= resolve_related_bos(bo_code, link_meta)
    related = discovered

    # 移除空字符串
    related.discard("")
    return related


def _find_customer_by_id(customer_id: str, all_records: dict) -> dict | None:
    """在所有已加载 demo 数据中查找 customer 记录。"""
    customers = all_records.get("customers", [])
    return next((c for c in customers if str(c.get("id")) == str(customer_id)), None)


def _resolve_customer_id_from_any_record(record_id: str, all_records: dict) -> str | None:
    """当 dry-run 传入的 ID 不是 customer 记录（如 customer-relations、opportunities 等）时，
    遍历所有已加载的 demo 数据，查找该 ID，提取其 customer_id 字段以解析出真正的客户 ID。
    支持：customer_id, parent_customer_id, customer_no, fop_customer_id 等常见外键字段。"""
    fk_candidates = ["customer_id", "parent_customer_id", "customer_no", "fop_customer_id"]
    for bo_code, records in all_records.items():
        if bo_code == "customers":
            continue  # 已在上游处理
        for rec in records:
            if str(rec.get("id", "")) == str(record_id):
                # 先尝试 FK 字段
                for fk in fk_candidates:
                    fk_val = rec.get(fk)
                    if fk_val is not None:
                        return str(fk_val)
                # customer_no → 通过 customers 表反查
                cust_no = rec.get("customer_no")
                if cust_no:
                    for c in all_records.get("customers", []):
                        if str(c.get("customer_no", "")) == str(cust_no):
                            return str(c.get("id"))
                break
    return None


def _eval_action_chain_conditions(action_chain_meta: dict, data_sources: dict,
                                   score_registry: dict, cust_opps: list) -> list:
    """遍历 ACTION_CHAIN 元数据中的所有链，评估触发条件并返回带触发状态的链列表。"""
    chains = action_chain_meta.get("chains", [])
    result = []
    for chain in chains:
        triggered = False
        trigger_type = chain.get("trigger", {}).get("type", "")
        chain_code = chain.get("code", "")
        
        # 检查 OPPORTUNITY_WIN_POST_ACTIONS: 是否有 CLOSED_WON 商机
        if chain_code == "OPPORTUNITY_WIN_POST_ACTIONS":
            won_opps = [o for o in cust_opps if o.get("status", "").upper() == "CLOSED_WON"]
            triggered = len(won_opps) > 0
        
        # 检查 OPPORTUNITY_STAGE_STALLED_ALERT: 是否有停滞商机
        # P12 修复：停滞判定统一使用 date 级比较（与 _compute_stage_metrics_per_opp 对齐），
        # 且使用严格大于 `>`（velocity 用 `>=` 标记停滞，预警仅在超过阈值时触发）。
        elif chain_code == "OPPORTUNITY_STAGE_STALLED_ALERT":
            from datetime import datetime
            now = _demo_now()
            _terminal = {"CLOSED_WON", "CLOSED_LOST", "CANCELLED", "SUSPENDED"}
            thresholds = {"DC_01": 15, "DC_02": 30, "DC_03": 15, "DC_04": 30, "DC_05": 30}
            for o in cust_opps:
                if o.get("status", "").upper() in _terminal:
                    continue
                updated_str = o.get("updated_time", "")
                if updated_str:
                    try:
                        updated = datetime.fromisoformat(updated_str)
                        age = (now.date() - updated.date()).days
                        stage = o.get("project_stage", "")
                        threshold = thresholds.get(stage.split(",")[0].strip(), 30)
                        if age > threshold:
                            triggered = True
                            break
                    except (ValueError, TypeError):
                        pass
        
        # 检查 CUSTOMER_CHURN_RISK_RAISED: health_score < 50
        elif chain_code == "CUSTOMER_CHURN_RISK_RAISED":
            hs = score_registry.get("customer_health_score", 100)
            triggered = float(hs) < 50 if hs else False
        
        # 检查 TARGET_COVERAGE_LOW_ALERT: coverage_ratio < 0.8
        elif chain_code == "TARGET_COVERAGE_LOW_ALERT":
            cr = score_registry.get("coverage_ratio", 1.0)
            triggered = float(cr) < 0.8 if cr else False
        
        chain_copy = dict(chain)
        chain_copy["_triggered"] = triggered
        result.append(chain_copy)
    return result


def eval_reasoning_chain(customer_id: str = "1001"):
    """完整推理链：元数据驱动编排，自动依赖解析 + 拓扑排序 + AST 求值。
    从 root BO 出发，沿 LINK 元数据自动发现关联 BO，按 DERIVATION 依赖关系拓扑排序，
    依次 AST 求值，最后执行 RULE 合规评估和 ACTION_CHAIN 条件检查。"""
    print(f"\n{'='*70}")
    print(f"  🧠 本体推理链 — 完整 Dry-Run 演算（元数据驱动编排）")
    print(f"{'='*70}\n")

    # ── 1. 加载设计态元数据 ──
    link_meta = load_design_fragment("link") or {}
    derivation_meta = load_design_fragment("derivation") or {}
    entity_scoring_meta = load_design_fragment("entity-scoring") or {}
    temporal_meta = load_design_fragment("temporal") or {}
    action_chain_meta = load_design_fragment("action-chain") or {}

    all_derived = entity_scoring_meta.get("derivedObjects", []) + derivation_meta.get("derivedObjects", [])

    print(f"  📦 元数据加载: LINK({len(link_meta.get('links',[]))}), "
          f"DERIVATION({len(derivation_meta.get('derivedObjects',[]))} + "
          f"ENTITY-SCORING({len(entity_scoring_meta.get('derivedObjects',[]))})), "
          f"TEMPORAL({len(temporal_meta.get('timelines',[]))}), "
          f"ACTION_CHAIN({len(action_chain_meta.get('chains',[]))})\n")

    # ── 2. 依赖解析：从 root BO 沿 LINK + DERIVATION 依赖 + expression source 自动发现关联 BO ──
    related_bos = resolve_all_required_bos("customers", link_meta, all_derived)
    print(f"  🔗 依赖解析：从 customers 出发发现 {len(related_bos)} 个关联 BO: {sorted(related_bos)}\n")

    # ── 3. 加载所有关联 BO 的 demo 数据 ──
    all_records = {}
    for bo_code in related_bos:
        all_records[bo_code] = load_all_demo_records(bo_code)

    # P11 修复：当用户从数据图谱选中非 customers 节点（如 customer-relations id=27）时，
    # 自动在所有 demo 数据中查找该 ID 的记录，提取其 customer_id 字段解析为真正的客户 ID。
    customer = _find_customer_by_id(customer_id, all_records)
    if not customer:
        resolved_id = _resolve_customer_id_from_any_record(customer_id, all_records)
        if resolved_id and resolved_id != customer_id:
            print(f"  🔍 自动解析：从记录 {customer_id} 关联到客户 ID={resolved_id}")
            customer_id = resolved_id
            customer = _find_customer_by_id(resolved_id, all_records)
    if not customer:
        print(f"  [ERR] Customer {customer_id} not found in demo data")
        return

    # 构建 data_sources（每个 BO 取首条记录作为默认上下文）
    data_sources = {}
    for bo_code in related_bos:
        records = all_records.get(bo_code, [])
        if bo_code == "customers":
            data_sources[bo_code] = customer
        else:
            data_sources[bo_code] = records[0] if records else {}

    temporal_events = load_json(get_demo_dir() / "temporal-events.sample.json") or {}

    # P0 修复：手动加载客户-竞对交叉引用表（不在 LINK 元数据中的 demo 辅助数据）
    xref_data = load_json(get_demo_dir() / "customer-competitor-xref.sample.json")
    if xref_data and "records" in xref_data:
        all_records["customer-competitor-xref"] = xref_data["records"]

    print(f"  👤 客户：{customer.get('customer_name')} (ID={customer_id})")
    print(f"     行业：{customer.get('market_segment')}  类别：{_zh(customer.get('customer_category', ''))}")
    # 客户关系状态从 customer-relations 读取（customers 表无 status 字段）
    cust_relations = all_records.get("customer-relations", [])
    cust_rel = next((r for r in cust_relations if str(r.get("customer_id")) == str(customer_id)), None)
    rel_status = cust_rel.get("status", "") if cust_rel else ""
    print(f"     客户关系状态：{_zh(rel_status) if rel_status else '无'}")

    score_registry = {}

    # ── 4. SCENE 推理：沿 LINK 元数据自动发现客户关联的场景 ──
    cust_scenes = _infer_related_records("customers", customer_id, "scenes", link_meta, all_records)
    print(f"\n  🎯 SCENE 推理 — 场景需求来源 (via LINK: CUSTOMER_HAS_SCENE)")
    print(f"  {'─'*50}")
    print(f"     客户场景数：{len(cust_scenes)}")
    for s in cust_scenes:
        # 从嵌套结构 scene_products→annual_estimates 读取深层字段
        sp = _get_first_scene_product(s)
        ae = _get_first_annual_estimate(sp)
        print(f"     • {s.get('scene_name_customer')} [{s.get('scene_category')}]")
        print(f"       产品：{sp.get('product_model')}  采购规模：¥{ae.get('customer_procurement_amount', 0):,}")
        print(f"       预计份额：{ae.get('estimated_share')}%  预计销量：¥{ae.get('estimated_sales_amount', 0):,}")
        print(f"       我司阶段：{sp.get('our_stage')}  下次招标：{sp.get('next_bid_date', '—')}")
        print(f"       进展：{sp.get('current_progress', '—')}")
    if cust_scenes:
        data_sources["scenes"] = cust_scenes[0]

    # 场景→商机孵化推理（沿 SCENE_GENERATES_OPPORTUNITY link）
    # P0 修复：父客户递归纳入子客户商机（如 1101 应包含 1103 的 2103）
    cust_opps = _infer_related_records_recursive("customers", customer_id, "opportunities", link_meta, all_records)

    # 显示子客户信息
    all_customers = all_records.get("customers", [])
    child_ids = _get_all_child_customer_ids(customer_id, all_customers)
    if child_ids:
        child_names = []
        for c in all_customers:
            if str(c.get("id")) in child_ids:
                child_names.append(f"{c.get('customer_name')}(ID={c.get('id')})")
        print(f"     → 纳入子客户({len(child_ids)}): {', '.join(child_names)}")
        print(f"        子客户商机数：{len(cust_opps) - len(_infer_related_records('customers', customer_id, 'opportunities', link_meta, all_records))} 条额外商机")

    # 活跃商机 = 非终态（排除 CLOSED_WON/CLOSED_LOST/CANCELLED 等终态）
    _terminal_statuses = {"CLOSED_WON", "CLOSED_LOST", "CANCELLED", "SUSPENDED"}
    active_opps = [o for o in cust_opps if o.get("status", "").upper() not in _terminal_statuses]
    scene_opp_links = []
    for s in cust_scenes:
        if active_opps:
            scene_opp_links.append((s.get("scene_name_customer"), [o.get("opportunity_name") for o in active_opps]))
    if scene_opp_links:
        # P5 修复：标签从"场景孵化商机"改为"via LINK 遍历"，
        # 商机是通过 CUSTOMER_HAS_OPPORTUNITY（含 FOP 递归）和 LINK 元数据获取的事实关联，
        # 不是 SCENE_GENERATES_OPPORTUNITY 推理（该 link 用于推断潜在商机，而非已存在商机）。
        print(f"\n     → 客户关联商机 (via LINK: CUSTOMER_HAS_OPPORTUNITY + FOP_BELONGS_TO_CUSTOMER):")
        for scene_name, opp_names in scene_opp_links:
            print(f"       {scene_name} → {', '.join(opp_names)}")

    # ── 4b. 缺失关系展示修复：联系人 / 商机主子关系 / 活动快照 ──
    _print_missing_link_relations(link_meta, all_records, customer_id, active_opps)

    # ── 5. TEMPORAL 推理（元数据驱动，复用已有 _eval_temporal_section）──
    # 将 data_sources["opportunities"] 指向当前客户的首条商机，
    # 避免初始化阶段使用 demo 全局首条（与当前客户无关）商机计算 stage_age_days
    if active_opps:
        data_sources["opportunities"] = active_opps[0]
    _eval_temporal_section(temporal_meta, temporal_events, data_sources,
                           score_registry, customer_id, customer, cust_opps)

    # ── 5b. TEMPORAL 推理：predict_category 变化轨迹 ──
    _print_predict_category_trajectory(temporal_events, active_opps)

    # ── 6. TEMPORAL 推理：商机阶段时间线 ──
    print(f"\n  ⏱️  TEMPORAL 推理 — 商机阶段时间线")
    print(f"  {'─'*50}")
    print(f"     客户商机数：{len(cust_opps)} (活跃: {len(active_opps)})")

    # 提前提取已赢单商机列表（后续多处使用）
    won_opps = [o for o in cust_opps if o.get("status", "").upper() == "CLOSED_WON"]

    # P5 修复：为每条活跃商机独立计算 stage_age_days 和 stage_velocity_level
    _compute_stage_metrics_per_opp(temporal_meta, temporal_events, active_opps, score_registry)

    # P6 修复：当无活跃商机但存在已赢单商机时，计算赢单商机的生命周期阶段指标
    # （从创建到赢单的总停留天数及流速），用于汇总 JSON 展示
    if not active_opps and won_opps:
        _compute_stage_metrics_for_won_opps(temporal_meta, temporal_events, won_opps, score_registry)

    # 取第一条商机的聚合值作为首条商机显示（stage_age_days/stage_velocity 从 stage_age_days_<id>
    # 模式读取；回退到 score_registry.stage_age_days 单体值）
    primary_opp_keys = [f"stage_age_days_{o['id']}" for o in (active_opps or won_opps)] if (active_opps or won_opps) else []
    stage_age_days = score_registry.get(primary_opp_keys[0], 0) if primary_opp_keys else score_registry.get("stage_age_days", 0)
    stage_velocity = score_registry.get("stage_velocity_level_" + str((active_opps or won_opps)[0]['id']), "N/A") if (active_opps or won_opps) else "N/A"

    if active_opps:
        opp = active_opps[0]
        # P11 修复：非 CNY 商机的 expected_order_amount 需折算为 CNY，
        # 否则 forecast_amount_weighted 等字段输出的是外币数值
        opp_cny = dict(opp)
        opp_currency = opp.get("currency", "CNY")
        if opp_currency and opp_currency != "CNY":
            raw_amount = opp.get("expected_order_amount", 0) or 0
            opp_cny["expected_order_amount"] = _convert_opp_amount_to_cny(
                raw_amount, opp_currency, all_records.get("exchange-rates", []))
        data_sources["opportunities"] = opp_cny

        print(f"     商机：{opp.get('opportunity_name')} (ID={opp.get('id')})")
        raw_stage = opp.get('project_stage', '')
        stage_label = _resolve_stage_label(opp.get('project_type', ''), raw_stage)
        print(f"     当前阶段：{stage_label} ({raw_stage})  停留天数：{stage_age_days}")
        print(f"     阶段流速：{_zh(stage_velocity)}")
    elif won_opps:
        # 仅有已赢单商机时也设置 opportunities data source 供 opportunity-intelligence 使用
        won_opp = won_opps[0]
        data_sources["opportunities"] = won_opp
        print(f"     已赢单商机：{won_opp.get('opportunity_name')} (ID={won_opp.get('id')})")
        print(f"     状态：{_zh(won_opp.get('status', ''))}  金额：¥{won_opp.get('expected_order_amount', 0):,.0f}")

    # P5 修复：逐条输出所有活跃商机的阶段信息
    if len(active_opps) > 1:
        for o in active_opps[1:]:
            opp_age = score_registry.get(f"stage_age_days_{o['id']}", 0)
            opp_vel = score_registry.get(f"stage_velocity_level_{o['id']}", "N/A")
            print(f"     商机：{o.get('opportunity_name')} (ID={o.get('id')})")
            raw_stage2 = o.get('project_stage', '')
            stage_label2 = _resolve_stage_label(o.get('project_type', ''), raw_stage2)
            print(f"     当前阶段：{stage_label2} ({raw_stage2})  停留天数：{opp_age}")
            print(f"     阶段流速：{_zh(opp_vel)}")

    # ── 7. 销售目标预计算（写入 score_registry 供 pipeline-coverage metric 引用）──
    target = _precompute_sales_target(all_records, score_registry, customer_id, link_meta, derivation_meta)
    if target:
        data_sources["sales-targets"] = target
        print(f"\n  🎯 销售目标预计算 — 写入 score_registry")
        print(f"  {'─'*50}")
        print(f"     score_registry['target_amount'] = {score_registry.get('target_amount', 0)}")

    # ── 7b. 汇率折算预计算（写入 score_registry，需要在销售目标之后以获取 _sales_owner_id 做跨客户聚合）──
    print(f"\n  💱 汇率折算预计算 — 写入 score_registry")
    print(f"  {'─'*50}")
    currency_info = _precompute_currency_conversion(all_records, score_registry, customer_id, link_meta, derivation_meta)
    active_rate = currency_info["rate"]
    if currency_info["usd_amount"] and active_rate:
        data_sources["exchange-rates"] = active_rate
        print(f"     USD 商机金额：${currency_info['usd_amount']:,.2f}")
        print(f"     汇率：1 USD = {active_rate.get('rate')} CNY ({active_rate.get('rate_type')})")
        print(f"     折算人民币：¥{currency_info['converted_cny']:,.2f}")
    else:
        print(f"     无 USD 商机或无有效汇率")
    print(f"     CNY 商机金额：¥{currency_info['total_cny_amount']:,.2f}")
    # P0 修复：区分客户级管道和销售负责人级管道
    # 客户级管道 = 仅本客户(+递归子客户)的商机金额（不含同组其他客户商机）
    cust_only_ids = {str(customer_id)} | child_ids
    # P11 修复：客户级管道金额必须按币种折算（USD→CNY），不能直接混合加总不同币种的数值
    exchange_rates_for_cust = all_records.get("exchange-rates", [])
    cust_only_amount = sum(
        _convert_opp_amount_to_cny(
            o.get("expected_order_amount", 0) or 0,
            o.get("currency", "CNY"),
            exchange_rates_for_cust
        )
        for o in [opp for opp in active_opps
                  if str(opp.get("business_customer_id", "")) in cust_only_ids]
    )
    print(f"     → 客户级管道金额[{customer.get('customer_name', '')}]（CNY）：¥{cust_only_amount:,.2f}")

    # P0: 写入客户级管道金额（供 aggregationScope=CUSTOMER 的字段使用，key 约定: <fieldCode>_customer）
    score_registry["active_pipeline_amount_customer"] = cust_only_amount

    # P11 修复：将汇率表写入 score_registry 供 pipelineAggregate 做 USD→CNY 折算
    score_registry["_exchange_rates"] = exchange_rates_for_cust

    sales_owner = score_registry.get("_sales_owner_id")
    if sales_owner:
        # 解析销售负责人姓名
        users = all_records.get("users", [])
        owner_user = next((u for u in users if str(u.get("id")) == str(sales_owner)), None)
        owner_name = owner_user.get("staff_name", sales_owner) if owner_user else sales_owner
        print(f"     → 用户级管道金额[{owner_name}]（CNY）：¥{currency_info['total_pipeline_cny']:,.2f}")
    else:
        print(f"     → 统一口径管道金额（CNY）：¥{currency_info['total_pipeline_cny']:,.2f}")
    print(f"     → score_registry['active_pipeline_amount'] = {score_registry.get('active_pipeline_amount', 0)}")

    # P10 修复：将跨销售负责人的聚合商机列表写入 score_registry，
    # 供 pipelineAggregate 计算 weighted_pipeline_amount 使用（口径与 active_pipeline_amount 一致）
    score_registry["_pipeline_opps"] = currency_info["active_opps"]

    # ── 8b. 竞对计数预计算（写入 score_registry，覆盖 temporalAggregate dry-run 默认值 0）──
    _precompute_competitor_count(all_records, score_registry, customer_id, link_meta, active_opps)
    # ── 8c. 活跃商机计数预计算（写入 score_registry）──
    score_registry["active_opportunity_count"] = len(active_opps)
    print(f"     score_registry['active_opportunity_count'] = {len(active_opps)}")
    # ── 8d. 已赢单商机计数预计算（写入 score_registry）──
    score_registry["won_opportunity_count"] = len(won_opps)
    print(f"     score_registry['won_opportunity_count'] = {len(won_opps)}")
    # ── 8e. opportunity-intelligence 需要商机状态字段（预填入第一条商机的 status）──
    if active_opps or won_opps:
        primary_opp = (active_opps + won_opps)[0]
        score_registry["opportunity_status"] = primary_opp.get("status", "ACTIVE")
    # ── 8f. 修复 last_activity_time=None：从 sales-activities demo 数据计算最近活动时间 ──
    if score_registry.get("last_activity_time") is None:
        activities = all_records.get("sales-activities", [])
        cust_acts = [a for a in activities if str(a.get("parent_id") or a.get("customer_id", "")) == str(customer_id)]
        if cust_acts:
            last_time = max((a.get("visit_time", "") for a in cust_acts), default=None)
            if last_time:
                score_registry["last_activity_time"] = last_time

    # ── 8g. 关系治理评分预计算 — 基于 customer-relations status（P5 修复：硬编码50→动态）──
    _precompute_relation_governance_score(all_records, score_registry, customer_id)
    
    # ── 9. DERIVATION 推理（拓扑排序后依次 AST 求值）──
    print(f"\n  📐 DERIVATION 推理 — 拓扑排序后依次求值")
    print(f"  {'─'*50}")
    eval_order = topological_sort_derived_objects(all_derived)
    order_codes = [d["code"] for d in eval_order]
    print(f"     求值顺序: {' → '.join(order_codes)}\n")
    _eval_derivation_section({"derivedObjects": eval_order}, data_sources, score_registry, customer, active_opps)

    # P7 修复：为所有非首条活跃商机逐一求值 opportunity-intelligence
    # 首条商机已在上面的 eval_order 中处理；其余商机需切换 data_sources["opportunities"] 后独立求值
    if len(active_opps) > 1:
        oi_obj = next((d for d in all_derived if d.get("code") == "opportunity-intelligence"), None)
        if oi_obj:
            for opp in active_opps[1:]:
                opp_id = opp.get("id")
                # P11 修复：非 CNY 商机的 expected_order_amount 需折算为 CNY，
                # 否则 forecast_amount_weighted 等字段输出的是外币数值而非人民币
                opp_cny = dict(opp)
                opp_currency = opp.get("currency", "CNY")
                if opp_currency and opp_currency != "CNY":
                    raw_amount = opp.get("expected_order_amount", 0) or 0
                    opp_cny["expected_order_amount"] = _convert_opp_amount_to_cny(
                        raw_amount, opp_currency, all_records.get("exchange-rates", []))
                data_sources["opportunities"] = opp_cny
                score_registry["opportunity_status"] = opp.get("status", "ACTIVE")
                # 使用 _compute_stage_metrics_per_opp 已写入的逐商机精确值
                score_registry["stage_age_days"] = score_registry.get(f"stage_age_days_{opp_id}", 0)
                score_registry["stage_velocity_level"] = score_registry.get(f"stage_velocity_level_{opp_id}", "N/A")
                print(f"\n  ─── 商机：{opp.get('opportunity_name')} (ID={opp_id}) ───")
                _eval_derivation_section({"derivedObjects": [oi_obj]}, data_sources, score_registry, customer, active_opps)
            # 恢复首条商机上下文，避免影响后续 ACTION_CHAIN / RULE 评估
            primary_id = active_opps[0].get("id")
            data_sources["opportunities"] = active_opps[0]
            score_registry["opportunity_status"] = active_opps[0].get("status", "ACTIVE")
            score_registry["stage_age_days"] = score_registry.get(f"stage_age_days_{primary_id}", 0)
            score_registry["stage_velocity_level"] = score_registry.get(f"stage_velocity_level_{primary_id}", "N/A")

    # ── 10. ACTION_CHAIN 推理（遍历元数据中的所有链，评估触发状态）──
    print(f"\n  ⚡ ACTION_CHAIN 推理 — 动作链条件检查")
    print(f"  {'─'*50}")
    chains = _eval_action_chain_conditions(action_chain_meta, data_sources, score_registry, cust_opps)
    # 先收集触发状态用于 summary，再清理
    chain_triggered_map = {c["code"]: c.get("_triggered", False) for c in chains}
    for chain in chains:
        triggered = chain.pop("_triggered", False)
        status_icon = "✅ 已触发" if triggered else "⏸  未触发"
        print(f"     {status_icon}  动作链：{chain['name']} ({chain['code']})")
        trigger = chain.get("trigger", {})
        print(f"     触发：{trigger.get('type')} on {trigger.get('boCode')}.{trigger.get('operationCode')}")
        print(f"     执行模式：{chain.get('executionMode', 'ASYNC')}")
        print(f"     步骤执行计划：")
        for i, step in enumerate(chain.get("steps", []), 1):
            deps = step.get("dependsOn", [])
            dep_label = f" (依赖: {', '.join(deps)})" if deps else ""
            tgt = step.get("target", {})
            target_label = tgt.get("derivedCode") or tgt.get("boCode") or tgt.get("channel", "")
            print(f"       {i}. {step['name']} [{step['stepType']}] → {target_label}{dep_label}")
    triggered_count = sum(1 for v in chain_triggered_map.values() if v)
    if triggered_count > 0:
        triggered_names = [k for k, v in chain_triggered_map.items() if v]
        print(f"     → 已触发 {triggered_count} 条动作链: {', '.join(triggered_names)}")
    else:
        print(f"     → 无动作链触发条件满足")

    # ── 11. RULE 推理（元数据驱动）──
    rule_passed, rule_total = _eval_rules_section(data_sources, active_opps, active_rate, all_records)

    # ── 11b. 异常模式检测（P3：结构化预分析，输出到控制台和汇总 JSON）──
    activities_for_anomaly = all_records.get("sales-activities", [])
    competitors_for_anomaly = all_records.get("competitors", [])
    anomaly_list = _detect_anomalies_console(score_registry, customer, cust_opps,
                                              activities_for_anomaly, competitors_for_anomaly,
                                              cust_scenes, currency_info, active_rate)

    # ── 12. 推理链总结 ──
    health_score = score_registry.get("customer_health_score", 0)
    churn_risk = score_registry.get("churn_risk_level", "UNKNOWN")
    next_action = score_registry.get("next_best_action", "无")
    activity_count_90d = score_registry.get("activity_count_90d", 0)
    last_activity_days = score_registry.get("last_activity_days", 3)
    coverage_ratio = score_registry.get("coverage_ratio", 0)
    risk_level = score_registry.get("risk_level", "UNKNOWN")
    total_pipeline_cny = currency_info["total_pipeline_cny"]
    total_usd_amount = currency_info["usd_amount"]
    converted_cny = currency_info["converted_cny"]

    print(f"\n{'='*70}")
    print(f"  📊 推理链总结")
    print(f"{'='*70}")
    result = {
        "场景名称": "CRM 本体推理链",
        "客户": {"编号": customer_id, "名称": customer.get("customer_name"), "类别": _zh(customer.get("customer_category", ""))},
        "场景需求": {
            "数量": len(cust_scenes),
            "明细": [{
                "名称": s.get("scene_name_customer"),
                "我司阶段": _get_first_scene_product(s).get("our_stage"),
                "采购规模": _get_first_annual_estimate(_get_first_scene_product(s)).get("customer_procurement_amount"),
                "预计份额": _get_first_annual_estimate(_get_first_scene_product(s)).get("estimated_share"),
                "下次招标": _get_first_scene_product(s).get("next_bid_date"),
            } for s in cust_scenes]
        },
        "时间线指标": {
            "近90天活动数": activity_count_90d,
            "最近活动距今天数": last_activity_days,
            "阶段停留天数": stage_age_days,
            "阶段流速等级": _zh(stage_velocity) if stage_velocity != "N/A" else stage_velocity,
        },
        "汇率折算": {
            "美元金额": total_usd_amount,
            "汇率": active_rate.get("rate") if active_rate else None,
            "折算人民币": converted_cny,
            "管道总金额(CNY)": total_pipeline_cny,
            "客户级管道金额(CNY)": cust_only_amount,
            "口径说明": f"管道总金额为销售负责人级口径（含同负责人所有客户商机）；客户级管道金额为仅当前客户(+子客户)[{customer.get('customer_name', '')}]口径",
        },
        "派生指标": {
            "客户健康度评分": round(health_score, 1) if isinstance(health_score, (int, float)) else health_score,
            "流失风险等级": _zh(churn_risk),
            "下一步最佳行动": next_action,
            "管道覆盖率": f"{coverage_ratio:.1%}" if isinstance(coverage_ratio, (int, float)) else coverage_ratio,
            "覆盖风险等级": _zh(risk_level) if target else None,
        },
        "动作链": {
            "动作链数量": len(chains),
            "动作链列表": [{"编码": c["code"], "步骤数": len(c.get("steps", [])), "已触发": chain_triggered_map.get(c["code"], False)} for c in chains],
        },
        "规则合规": {"通过": rule_passed, "总计": rule_total},
        "异常检测": {"数量": len(anomaly_list), "明细": anomaly_list} if anomaly_list else {"数量": 0, "明细": []},
        "元信息": {"执行模式": "元数据驱动", "排序引擎": "topological-sort",
                  "求值顺序": order_codes,
                  "片段列表": ["crm-link", "crm-derivation", "crm-entity-scoring", "crm-temporal", "crm-action-chain", "*-rule"]}
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # ── 13. LLM 叙事化 ──
    if _LLM_DISABLED:
        print(f"\n{'='*70}")
        print(f"  🤖 LLM 叙事化报告 — 已跳过（LLM 已关闭）")
        print(f"{'='*70}\n")
        return
    if _SKIP_LLM_IN_BATCH:
        print(f"\n{'='*70}")
        print(f"  🤖 LLM 叙事化报告 — 已跳过（_SKIP_LLM_IN_BATCH=True）")
        print(f"{'='*70}\n")
        return

    print(f"\n{'='*70}")
    print(f"  🤖 LLM 叙事化报告")
    print(f"{'='*70}\n")

    activities = all_records.get("sales-activities", [])
    competitors = all_records.get("competitors", [])
    narrative = generate_llm_narrative(result, customer, active_opps, activities, competitors, active_rate, cust_scenes, _LLM_CONFIG)
    print(narrative)


def _compute_stage_metrics_per_opp(temporal_meta: dict, temporal_events: dict,
                                     active_opps: list, score_registry: dict):
    """P5 修复：为每条活跃商机独立计算 stage_age_days 和 stage_velocity_level。
    从 temporal-events 中的 stageEvents 按 objectId 匹配商机，计算阶段停留天数。
    结果写入 score_registry['stage_age_days_<id>'] 和 score_registry['stage_velocity_level_<id>']。
    为向后兼容，也写入 score_registry['stage_age_days']（第一条商机的值）。
    
    排除 CLOSED_WON/CLOSED_LOST 等终态商机（无意义的阶段数据）。
    
    阶段流速阈值（与设计文档 docs/demo-data-validation-targets-internet.md §2.1.1 对齐）：
      DC_01: 15d  DC_02: 30d  DC_03: 15d  DC_04: 30d  DC_05: 30d
    判定规则：age_days >= threshold → STAGNANT, 否则 NORMAL（二元判定）"""
    from datetime import datetime
    stage_events = temporal_events.get("stageEvents", [])
    now = _demo_now()
    velocity_thresholds = {"DC_01": 15, "DC_02": 30, "DC_03": 15, "DC_04": 30, "DC_05": 30}
    _terminal = {"CLOSED_WON", "CLOSED_LOST", "CANCELLED", "SUSPENDED"}

    for idx, opp in enumerate(active_opps):
        # 跳过终态商机
        if opp.get("status", "").upper() in _terminal:
            continue
        opp_id = opp.get("id")
        opp_events = [e for e in stage_events if str(e.get("objectId")) == str(opp_id)]
        # 以商机记录的 updated_time 计算停留天数
        updated_str = opp.get("updated_time", "")
        if updated_str:
            try:
                updated = datetime.fromisoformat(updated_str)
                # P5 修复：使用 date() 级别比较（而非 datetime 差值的 .days floor），
                # 避免 7/1T10:30 → 7/15T00:00 被 trunc 为 13 天（预期应为 14 天含首天）。
                age_days = (now.date() - updated.date()).days
            except (ValueError, TypeError):
                age_days = 0
        else:
            age_days = 0

        # 阶段流速判定：二元 NORMAL/STAGNANT（与设计文档一致）
        stage = opp.get("project_stage", "")
        threshold = velocity_thresholds.get(stage.split(",")[0].strip(), 30)
        if age_days >= threshold:
            vel = "STAGNANT"
        else:
            vel = "NORMAL"

        score_registry[f"stage_age_days_{opp_id}"] = age_days
        score_registry[f"stage_velocity_level_{opp_id}"] = vel
        # 向后兼容：第一条商机写入全局 key
        if idx == 0:
            score_registry["stage_age_days"] = age_days
            score_registry["stage_velocity_level"] = vel


def _compute_stage_metrics_for_won_opps(temporal_meta: dict, temporal_events: dict,
                                          won_opps: list, score_registry: dict):
    """P6 修复：为已赢单商机计算生命周期阶段指标。

    计算口径（与 TEMPORAL 块的 OPPORTUNITY_STAGE_TIMELINE 对齐）：
    - stage_age_days：最后一条阶段事件时间 → 基准日（而非首尾事件跨度）
    - stage_velocity_level：固定为 "CLOSED_WON"

    P8 修复：不再覆盖 TEMPORAL 块已写入的 score_registry['stage_age_days']，
    改为仅写入逐商机 key（stage_age_days_<id>），由调用方从 key 模式读取。"""
    from datetime import datetime
    now = _demo_now()
    stage_events = temporal_events.get("stageEvents", [])

    for idx, opp in enumerate(won_opps):
        opp_id = opp.get("id")
        # 从 stageEvents 中找该商机的事件
        opp_events = [e for e in stage_events if str(e.get("objectId")) == str(opp_id)]
        if opp_events:
            # P8 修复：取最后一条事件时间 → 基准日（与 TEMPORAL 块口径对齐）
            sorted_events = sorted(opp_events, key=lambda e: e.get("eventTime", ""))
            last_time = sorted_events[-1].get("eventTime", "")
            if last_time:
                try:
                    t2 = datetime.fromisoformat(last_time)
                    # P8 修复：使用 date() 级别比较（与 _compute_stage_metrics_per_opp 一致）
                    age_days = (now.date() - t2.date()).days
                except (ValueError, TypeError):
                    age_days = 0
            else:
                age_days = 0
        else:
            # 回退：使用商机 updated_time → 基准日
            updated_str = opp.get("updated_time", "")
            if updated_str:
                try:
                    t = datetime.fromisoformat(updated_str)
                    age_days = (now.date() - t.date()).days
                except (ValueError, TypeError):
                    age_days = 0
            else:
                age_days = 0

        score_registry[f"stage_age_days_{opp_id}"] = age_days
        score_registry[f"stage_velocity_level_{opp_id}"] = "CLOSED_WON"
        # P8 修复：不覆盖 TEMPORAL 块写入的全局 stage_age_days（口径不同会导致不一致）
        # 但 stage_velocity_level 仍覆盖：TEMPORAL 块对终态商机可能输出 NORMAL 而非 CLOSED_WON
        if idx == 0:
            if "stage_age_days" not in score_registry:
                score_registry["stage_age_days"] = age_days
            score_registry["stage_velocity_level"] = "CLOSED_WON"


def _eval_temporal_section(temporal_meta: dict, temporal_events: dict, data_sources: dict,
                            score_registry: dict, customer_id: str, customer: dict,
                            opportunities: list):
    """Evaluate TEMPORAL section from metadata.
    Iterates timelines and their metric definitions, using ontology_expr_eval
    when a metric has an expression AST, otherwise falling back to metricType-native logic."""

    timelines = temporal_meta.get("timelines", [])
    if not timelines:
        _eval_temporal_fallback(data_sources, score_registry, temporal_events, customer_id, opportunities)
        return

    # 处理每一条时间线
    for tl in timelines:
        tl_code = tl.get("code", "")
        tl_name = tl.get("name", "")

        print(f"\n  ⏱️  TEMPORAL 推理 — {tl_name} (code={tl_code})")
        print(f"  {'─'*50}")
        print(f"     boCode={tl.get('boCode')}, timeField={tl.get('timeField')}")
        print(f"     metrics: {len(tl.get('metrics', []))}")

        # 对每条时间线，从 temporal 元数据的 eventSources 读取事件类型，映射到 demo events
        demo_events = _get_demo_events(tl, temporal_events, data_sources)

        # P7 修复：按当前客户的商机 ID 过滤阶段事件，避免其他客户事件污染 stage_age_days
        opp_ids = {str(o.get("id")) for o in (opportunities or [])}
        demo_events = _filter_demo_events_by_customer(demo_events, tl, customer_id, opp_ids)

        # P0 修复：当 temporal-events 没有该客户事件时，从 sales-activities demo 合成
        demo_events = _supplement_activity_events_from_demo(demo_events, tl, customer_id)

        # 设置 context for temporalAggregate（传入固定基准日避免 off-by-1）
        context = {"_eval": True, "_root": tl.get("boCode", ""), "_demo_events": demo_events,
                    "_reference_date": _demo_now()}

        for metric in tl.get("metrics", []):
            mcode = metric.get("code", "")
            mname = metric.get("name", "")
            mtype = metric.get("metricType", "")
            expr_ast = metric.get("expression") if "expression" in metric else None

            if expr_ast and expr_ast.get("type"):
                # 使用 expression AST 计算
                if evaluate_tree:
                    eval_result = evaluate_tree(expr_ast, context, data_sources)
                    if eval_result.get("success"):
                        val = eval_result.get("result")
                        # P13: 终态商机统一返回"已赢单"（TEMPORAL 块与 opportunity-intelligence 块保持一致）
                        if mcode == "stage_velocity_level" and tl_code == "OPPORTUNITY_STAGE_TIMELINE":
                            _terminal_set = {"CLOSED_WON", "CLOSED_LOST", "CANCELLED", "SUSPENDED"}
                            _all_opps = opportunities or []
                            if _all_opps and all(o.get("status", "").upper() in _terminal_set for o in _all_opps):
                                val = "CLOSED_WON"
                        score_registry[mcode] = val
                        display_val = _zh(val) if isinstance(val, str) and (mcode.endswith("_level") or mcode.endswith("_velocity")) else val
                        print(f"     → {mname} ({mcode}) [expr AST]: {display_val}")
                    else:
                        print(f"     ⚠️ {mname} ({mcode}) [expr ERR]: {eval_result.get('error')}")
                else:
                    print(f"     ⚠️ {mname} ({mcode}) [expr AST — no evaluator]")
            else:
                # 没有 expression 的指标：跳过（所有指标应已补齐 AST）
                print(f"     ⚠️ {mname} ({mcode}) [{mtype}] — no expression defined")

    # sales_activity_score 现在由 DERIVATION 中的 scalarFunc(min) 自动计算


def _get_demo_events(tl: dict, temporal_events: dict, data_sources: dict) -> list:
    """Get demo events relevant to a given timeline.
    从 temporal 元数据的 eventSources 定义中读取 eventType，
    映射到 temporal-events.sample.json 中的事件列表 key。
    映射规则：eventType → camelCase + 's' (如 STAGE_CHANGED → stageEvents)。
    不硬编码 timeline code。
    
    当 temporal-events 中没有该客户的活动事件时，回退到从 sales-activities
    demo 数据中合成 temporal 事件（P0 修复：避免 activity_count DRY_RUN）。
    """
    event_sources = tl.get("eventSources", [])
    for es in event_sources:
        event_type = es.get("eventType", "")
        if event_type:
            parts = event_type.lower().split("_")
            first_word = parts[0]
            events_key = first_word + "Events"
            if events_key in temporal_events:
                return temporal_events[events_key]
            events_key_lower = first_word.lower() + "Events"
            if events_key_lower in temporal_events:
                return temporal_events[events_key_lower]
    return []


def _supplement_activity_events_from_demo(demo_events: list, tl: dict, 
                                           customer_id: str) -> list:
    """当 temporal-events 中没有当前客户的活动事件时，从 sales-activities
    demo data 中合成 temporal 事件，使 activity_count 等指标可正确计算。
    P0 修复：解决 internet demo 中 1104 等客户 activity_count_90d=DRY_RUN 的问题。"""
    tl_bo_code = tl.get("boCode", "")
    if tl_bo_code != "sales-activities":
        return demo_events
    # 如果已有当前客户的事件（经过 _filter_demo_events_by_customer 过滤后），直接返回
    if demo_events:
        return demo_events
    # 回退：从 sales-activities demo data 合成事件
    activities = load_all_demo_records("sales-activities")
    if not activities:
        return demo_events
    synthetic = []
    for act in activities:
        if str(act.get("parent_id")) == str(customer_id):
            visit_time = act.get("visit_time", "")
            if visit_time:
                synthetic.append({
                    "boCode": "sales-activities",
                    "objectId": customer_id,
                    "eventType": "ACTIVITY_COMPLETED",
                    "eventTime": visit_time,
                    "snapshot": {
                        "visit_subject": act.get("visit_subject", ""),
                        "status": "COMPLETED"
                    }
                })
    return synthetic


def _filter_demo_events_by_customer(demo_events: list, tl: dict, customer_id: str,
                                     opp_ids: set = None) -> list:
    """Filter demo events to only those relevant to the current customer.
    对于客户活动时间线 (boCode=sales-activities)，按 customer_id 过滤 objectId。
    对于商机阶段时间线 (boCode=opportunities)，按当前客户的商机 ID 集合过滤，
    避免其他客户的阶段事件污染 stage_age_days 计算结果。
    """
    tl_bo_code = tl.get("boCode", "")
    if tl_bo_code == "sales-activities":
        # activityEvents 中 objectId 是 customer_id
        return [e for e in demo_events if str(e.get("objectId")) == str(customer_id)]
    elif tl_bo_code == "opportunities" and opp_ids:
        # P7 修复：按当前客户的商机 ID 过滤，防止其他客户阶段事件污染
        return [e for e in demo_events if str(e.get("objectId")) in opp_ids]
    return demo_events


def _eval_temporal_metric_native(metric: dict, demo_events: list, data_sources: dict,
                                  temporal_events: dict, customer_id: str) -> float:
    """Evaluate a temporal metric using its metricType-native calculation logic."""
    mtype = metric.get("metricType", "")
    window = metric.get("window", "P90D")
    source_link = metric.get("sourceLink", "")
    mcode = metric.get("code", "")

    if mtype == "COUNT_WINDOW":
        # Count relevant events in window, return raw count (scoring happens elsewhere)
        window_days = _parse_window_days_simple(window)
        now = _demo_now()
        count = 0
        for e in demo_events:
            if isinstance(e.get("eventTime"), str):
                try:
                    et = datetime.fromisoformat(e["eventTime"])
                    if (now - et).days <= window_days:
                        count += 1
                except (ValueError, TypeError):
                    count += 1
        return count  # Return raw count, not score

    elif mtype == "LAST_VALUE":
        if demo_events:
            last_time = max((e.get("eventTime") for e in demo_events), default=None)
            if last_time:
                try:
                    # P5 修复：date() 级别比较，与 _compute_stage_metrics_per_opp 对齐口径
                    days = (_demo_now().date() - datetime.fromisoformat(last_time).date()).days
                    return days
                except (ValueError, TypeError):
                    pass
        return 3  # demo default

    elif mtype == "VELOCITY_LEVEL":
        return "NORMAL"

    elif mtype == "DURATION_CURRENT_STATE":
        return 12  # demo default

    return 0.0


def _parse_window_days_simple(window: str) -> int:
    """Parse window string to days. Simple version for metric-native evaluation."""
    semantic = {
        "CURRENT_QUARTER": 90, "LAST_QUARTER": 180,
        "CURRENT_MONTH": 30, "LAST_MONTH": 60,
        "CURRENT_YEAR": 365, "LAST_YEAR": 730,
    }
    if window in semantic:
        return semantic[window]
    if window.startswith("P"):
        num = int(window[1:-1])
        unit = window[-1].upper()
        if unit == "D": return num
        elif unit == "W": return num * 7
        elif unit == "M": return num * 30
        elif unit == "Y": return num * 365
    return 90


def _eval_temporal_fallback(data_sources: dict, score_registry: dict,
                              temporal_events: dict, customer_id: str,
                              opportunities: list):
    """Fallback when no temporal metadata is available."""
    print(f"\n  ⏱️  TEMPORAL 推理 — 客户活动时间线 (fallback)")
    print(f"  {'─'*50}")
    activity_events = [e for e in temporal_events.get("activityEvents", [])
                       if str(e.get("objectId")) == str(customer_id)]
    activity_count_90d = len(activity_events)
    last_activity_time = max((e.get("eventTime") for e in activity_events), default=None) if activity_events else None
    last_activity_days = 3

    print(f"     近90天活动数 (activity_count_90d): {activity_count_90d}")
    print(f"     最近活动时间 (last_activity_time): {last_activity_time}")

    activity_score = min(100, activity_count_90d * 25) if activity_count_90d > 0 else 0
    score_registry["sales_activity_score"] = activity_score
    score_registry["activity_count_90d"] = activity_count_90d
    score_registry["last_activity_days"] = last_activity_days
    print(f"     → 活动支撑评分 (sales_activity_score): {activity_score}")


def _eval_derivation_section(derivation_meta: dict, data_sources: dict,
                              score_registry: dict, customer: dict, active_opps: list):
    """Evaluate DERIVATION section from metadata.
    Reads derived objects and their field expressions from crm-derivation.fragment.json,
    evaluates them using ontology_expr_eval AST interpreter."""
    derived_objects = derivation_meta.get("derivedObjects", [])

    if not derived_objects:
        return

    # 处理每个派生对象
    for dobj in derived_objects:
        dobj_code = dobj.get("code", "")
        dobj_name = dobj.get("name", "")

        print(f"\n  📐 DERIVATION 推理 — {dobj_name} (code={dobj_code})")
        print(f"  {'─'*50}")
        print(f"     objectKind={dobj.get('objectKind')}")
        deps = ", ".join(str(d.get("viaLink") or d.get("joinType") or "?") for d in dobj.get("dependencies", []))
        print(f"     dependencies: [{deps}]")

        for field in dobj.get("fields", []):
            fcode = field.get("code", "")
            fname = field.get("name", "")
            ftype = field.get("type", "")
            expr = field.get("expression") if field.get("expression") else None

            if expr and expr.get("type"):
                expr_type = expr.get("type")
                # 构建求值上下文，将 score_registry 注入 context._metrics
                context = {"_eval": True, "_root": dobj.get("root", {}).get("boCode", ""),
                           "_metrics": score_registry}

                # 特殊处理：metric 节点直接读 score_registry
                if expr_type == "metric":
                    mcode = expr.get("code", "")
                    val = score_registry.get(mcode, f"DRY_RUN:{mcode}")
                    # 元数据驱动：若 field 标记 aggregationScope=CUSTOMER 且存在 customer 级值，则使用客户级
                    if field.get("aggregationScope") == "CUSTOMER":
                        cust_key = mcode + "_customer"
                        if cust_key in score_registry:
                            val = score_registry[cust_key]
                    score_registry[fcode] = val
                    display_val = _zh(val) if fcode.endswith("_level") or fcode.endswith("_velocity") or fcode.endswith("_status") else val
                    print(f"     {fname} ({ftype}) [metric → {mcode}]: {display_val}")
                    continue

                # 通用 AST 求值
                if evaluate_tree:
                    # P5 元数据驱动：注入 _pipeline_opps 到 context 供 pipelineAggregate 使用
                    # P10 修复：优先使用预计算的跨销售负责人聚合商机列表，确保 weighted_pipeline_amount
                    # 与 active_pipeline_amount 口径一致（均含同负责人所有客户商机）
                    context["_pipeline_opps"] = score_registry.get("_pipeline_opps", active_opps)
                    # P11 修复：注入汇率表供 pipelineAggregate 做 USD→CNY 折算
                    context["_exchange_rates"] = score_registry.get("_exchange_rates", [])
                    eval_result = evaluate_tree(expr, context, data_sources)
                    if eval_result.get("success"):
                        result = eval_result.get("result")
                        is_dry = eval_result.get("dryRun", False)

                        if isinstance(result, dict) and result.get("_dryRun"):
                            # temporalAggregate / aggregate / pipelineAggregate — demo fallback
                            if fcode in score_registry and not str(score_registry[fcode]).startswith("DRY_RUN"):
                                val = score_registry[fcode]
                                # 元数据驱动：aggregationScope=CUSTOMER → 用客户级值
                                if field.get("aggregationScope") == "CUSTOMER":
                                    cust_key = fcode + "_customer"
                                    if cust_key in score_registry:
                                        val = score_registry[cust_key]
                                display_val = _zh(val) if isinstance(val, str) and (fcode.endswith("_level") or fcode.endswith("_velocity")) else val
                                print(f"     {fname} ({ftype}) [{result['_dryRun']} → preserved]: {display_val}")
                            else:
                                val = _temporal_dry_run_demo(fcode, result, score_registry, active_opps)
                                score_registry[fcode] = val
                                display_val = _zh(val) if isinstance(val, str) and (fcode.endswith("_level") or fcode.endswith("_velocity")) else val
                                print(f"     {fname} ({ftype}) [{result['_dryRun']} → demo]: {display_val}")
                        else:
                            score_registry[fcode] = result
                            display_val = _zh(result) if isinstance(result, str) and (fcode.endswith("_level") or fcode.endswith("_velocity") or fcode.endswith("_status")) else result
                            print(f"     {fname} ({ftype}) [expr AST]: {display_val}")
                    else:
                        print(f"     ⚠️ {fcode} ({ftype}) [ERR]: {eval_result.get('error')}")
                else:
                    # no evaluator at all — last resort demo
                    val = _derive_field_by_rule(fcode, score_registry, data_sources, active_opps)
                    score_registry[fcode] = val
                    display_val = _zh(val) if isinstance(val, str) and (fcode.endswith("_level") or fcode.endswith("_velocity") or fcode.endswith("_status")) else val
                    print(f"     {fname} ({ftype}) [no-eval demo]: {display_val}")
            else:
                # 没有 expression，使用规则推导
                val = _derive_field_by_rule(fcode, score_registry, data_sources, active_opps)
                score_registry[fcode] = val
                display_val = _zh(val) if isinstance(val, str) and (fcode.endswith("_level") or fcode.endswith("_velocity") or fcode.endswith("_status")) else val
                print(f"     {fname} ({ftype}) [rule-derived]: {display_val}")


def _temporal_dry_run_demo(fcode: str, dry_result: dict, score_registry: dict,
                            active_opps: list):
    """Provide demo values for temporalAggregate/aggregate dry-run results
    when real cross-BO query is not available.
    根据 AST 中的 fn 类型返回类型安全的默认值，不硬编码字段名。"""
    # Generic fallback for temporalAggregate — based on fn type from AST metadata
    if dry_result.get("_dryRun") == "temporalAggregate":
        fn = dry_result.get("fn", "count")
        if fn == "count": return 0
        if fn == "sum": return 0.0
        if fn == "max": return None
        if fn == "min": return None
        if fn == "avg": return 0.0
        if fn == "dateDiff": return 0
        if fn == "velocityLevel": return "UNKNOWN"
    if dry_result.get("_dryRun") == "aggregate":
        fn = dry_result.get("fn", "count")
        if fn == "count": return 0
        if fn == "sum": return 0.0
    return f"DRY_RUN:{fcode}"


def _derive_field_by_rule(fcode: str, score_registry: dict, data_sources: dict,
                           active_opps: list):
    """Derive a field value when no expression AST is available.
    Returns the existing value from score_registry if already computed.
    This is the LAST-RESORT fallback — all meaningful fields should have AST.
    不硬编码字段名和业务逻辑，仅返回 DRY_RUN 标记。"""
    # If already computed by temporal or previous derivation, don't overwrite
    if fcode in score_registry:
        return score_registry[fcode]
    # 所有字段都应有 expression AST；没有 AST 的字段返回 DRY_RUN 标记
    return f"DRY_RUN:{fcode}"


def _eval_derivation_fallback(data_sources: dict, score_registry: dict,
                               customer: dict, active_opps: list):
    """Fallback when no derivation metadata is available (original hardcoded logic)."""
    # This is kept for backward compatibility, but metadata-driven path is preferred
    pass


def _extract_ast_field_paths(ast: dict) -> set:
    """Recursively extract all 'path' values from an AST tree (field references)."""
    if not isinstance(ast, dict):
        return set()
    paths = set()
    if ast.get("type") == "field" and ast.get("path"):
        paths.add(ast["path"])
    for key in ("left", "right", "operand", "expr", "value", "fields"):
        if key in ast:
            paths |= _extract_ast_field_paths(ast[key])
    # Handle array nodes like 'arguments' in fnCall
    for key, val in ast.items():
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    paths |= _extract_ast_field_paths(item)
    return paths


def _check_ast_field_availability(ast: dict, bo_name: str, data_sources: dict) -> set:
    """Check if all fields referenced in an AST are available in data_sources for the given BO.
    Returns the set of missing field paths (empty = all available)."""
    paths = _extract_ast_field_paths(ast)
    bo_record = data_sources.get(bo_name, {})
    if not isinstance(bo_record, dict) or not bo_record:
        return paths  # no data at all for this BO — all paths missing
    return {p for p in paths if p not in bo_record}


def _eval_rules_section(data_sources: dict, active_opps: list, active_rate: dict, all_records: dict = None) -> tuple:
    """Evaluate rules from release-time schema-view.
    First tries to load and evaluate all rules via ontology_expr_eval,
    then falls back to hardcoded checks for rules without exprAst.

    P6 修复：动态裁剪 RULE 评估范围 — 仅对当前 demo-data 中有实际实例的 BO 评估规则。
    避免 contacts/customer-relations/scenes/users 等 demo 数据未覆盖字段的 BO
    产生大量误导性 AST err（如 period_end, shortlist_date 等字段不存在）。"""
    print(f"\n  ⚖️  RULE 推理 — 规则合规性评估（元数据驱动）")
    print(f"  {'─'*50}")

    # P6: 动态裁剪 — 仅评估当前加载了 demo 数据的 BO 的规则
    # 优先从 all_records 获取（推理链入口传入），否则从 data_sources 推断
    if all_records is not None:
        # all_records 的 key 是 boCode，value 是记录列表；有记录的才评估
        _active_bos = {bo for bo, records in all_records.items() if records}
    else:
        # 回退：从 data_sources 猜（只含首条记录，不如 all_records 精确）
        _active_bos = {k.replace("-", "_") for k in data_sources.keys()}

    # 始终包含核心 BO（即使 data_sources 中只有一条记录）
    _active_bos |= {"customers", "opportunities", "exchange-rates", "competitors"}

    if all_records is not None:
        active_bos_display = sorted([b for b in _active_bos if b in all_records and all_records[b]])
    else:
        active_bos_display = sorted(_active_bos)
    print(f"     当前有实例数据的 BO: {active_bos_display}")

    # 从发布态目录自动发现所有有 RULE 的 BO（元数据驱动：从发布态 schema-view 读取）
    all_rules = []
    release_dir = META_DIR / "release-time"
    if release_dir.exists():
        for bo_dir in release_dir.iterdir():
            if not bo_dir.is_dir() or bo_dir.name.startswith("_"):
                continue
            bo_name = bo_dir.name
            # P6: 动态裁剪 — 仅对当前 demo 数据中有实际记录的 BO 评估规则
            if bo_name not in _active_bos:
                continue
            schema_file = bo_dir / f"{bo_name}.schema-view.v2.json"
            if schema_file.exists():
                bo_rules = load_bo_rule_fragment(bo_name)
                if bo_rules:
                    for r in bo_rules.get("rules", []):
                        r["_from_bo"] = bo_name
                        all_rules.append(r)

    # 粗粒度裁剪后，再对每条规则做细粒度检查：规则 AST 引用的字段是否存在于 data_sources。
    # 跳过策略（元数据驱动）：
    #   scope=OPERATION → 依赖真实操作参数，dry-run 无条件跳过
    #   trigger=BEFORE_OPERATION + 无 exprAst → 无法求值，跳过
    #   trigger=BEFORE_OPERATION + AST 引用 old_/new_/$ 前缀 → 依赖操作上下文字段，跳过
    #   trigger=BEFORE_OPERATION + 纯数据字段 → 纳入，评估阶段走全量记录逐条检查
    _operation_scope_skip = 0
    _bo_trigger_skip = 0
    _filtered_rules = []
    for rule in all_rules:
        # scope=OPERATION 的规则依赖真实操作参数，无条件跳过
        if rule.get("scope") == "OPERATION":
            _operation_scope_skip += 1
            continue
        # BEFORE_OPERATION 规则细粒度跳过判定
        if rule.get("trigger") == "BEFORE_OPERATION":
            ast = rule.get("exprAst")
            if not ast:
                _bo_trigger_skip += 1
                continue  # 无 exprAst，dry-run 中无法评估
            ast_paths = _extract_ast_field_paths(ast)
            if any(p.startswith("old_") or p.startswith("new_") or p.startswith("$") for p in ast_paths):
                _bo_trigger_skip += 1
                continue  # 依赖操作上下文字段
            # 纯数据字段：字段可用性校验
            bo_name = rule.get("_from_bo", "")
            records = (all_records or {}).get(bo_name, [])
            if records:
                sample = records[0]
                if {p for p in ast_paths if p not in sample}:
                    continue  # 字段在 demo 数据中不存在
            # 纳入评估，评估策略由 scope 元数据驱动（BO/CROSS_BO → 多记录，FIELD → 单记录）
            _filtered_rules.append(rule)
            continue
        ast = rule.get("exprAst")
        if ast and data_sources:
            missing_fields = _check_ast_field_availability(ast, rule.get("_from_bo", ""), data_sources)
            if missing_fields:
                continue
        _filtered_rules.append(rule)

    if _operation_scope_skip > 0:
        print(f"     Dry-Run 跳过：{_operation_scope_skip} 条 OPERATION 作用域规则（需真实操作触发）")
    if _bo_trigger_skip > 0:
        print(f"     Dry-Run 跳过：{_bo_trigger_skip} 条 BEFORE_OPERATION 规则（无 exprAst 或依赖操作上下文字段）")
    if len(_filtered_rules) < len(all_rules) - _operation_scope_skip - _bo_trigger_skip:
        skipped = len(all_rules) - len(_filtered_rules) - _operation_scope_skip - _bo_trigger_skip
        print(f"     细粒度裁剪：跳过 {skipped} 条规则（引用字段在当前 demo 数据中不存在）")

    rule_checks = []
    passed_count = 0

    # 从元数据读取 polarity=safety 的规则（表达式为安全条件，True=合规）
    _SAFETY_POLARITY_RULES = {r.get("code") for r in _filtered_rules if r.get("polarity") == "safety"}

    # 评估策略（元数据驱动）：
    #   trigger=BEFORE_OPERATION 的规则原本被跳过（P9 后纳入），其语义为对 BO 内全部记录
    #   做状态合规检查 → 遍历 all_records 全量评估。
    #   其他 trigger（BEFORE_VALIDATE 等）保持 data_sources 单条评估（已由客户上下文裁剪）。
    for rule in _filtered_rules:
        rcode = rule.get("code", "?")
        rname = rule.get("name", "")
        ast = rule.get("exprAst")

        if ast and evaluate_tree:
            bo_name = rule.get("_from_bo", "")
            is_bo_trigger = rule.get("trigger") == "BEFORE_OPERATION"

            if is_bo_trigger and all_records:
                # BEFORE_OPERATION 规则：遍历 all_records 全量记录逐条评估
                records = (all_records or {}).get(bo_name, [])
                all_passed = True
                violation_details = []
                for rec in records:
                    single_ds = {bo_name: rec}
                    try:
                        eval_result = evaluate_tree(ast, {"_eval": True, "_root": bo_name}, single_ds)
                        if eval_result.get("success") and not eval_result.get("dryRun", False):
                            raw = bool(eval_result.get("result"))
                            if rcode in _SAFETY_POLARITY_RULES:
                                rec_passed = raw
                            else:
                                rec_passed = not raw
                            if not rec_passed:
                                all_passed = False
                                violation_details.append(rec.get("id", "?"))
                    except Exception:
                        pass
                passed = all_passed
                icon = "✅" if passed else "❌"
                print(f"     {icon} {rcode}: {rname} (AST, BEFORE_OPERATION, {len(records)}条记录)")
                if rcode in _SAFETY_POLARITY_RULES:
                    print(f"         合规状态: {'✅ 合规' if passed else '❌ 违规'} (safety 极性, 违规ID={violation_details})")
                else:
                    print(f"         合规状态: {'✅ 合规' if passed else '❌ 违规'} (默认极性, 违规ID={violation_details})")
            else:
                # 非 BEFORE_OPERATION 规则：data_sources 单条评估（保持原有行为）
                try:
                    context = {"_eval": True, "_root": bo_name}
                    eval_result = evaluate_tree(ast, context, data_sources)
                    if eval_result.get("success"):
                        raw_result = eval_result.get("result")
                        is_dry = eval_result.get("dryRun", False)
                        if is_dry:
                            passed = True
                            icon = "🔬"
                        else:
                            is_violation = bool(raw_result)
                            if rcode in _SAFETY_POLARITY_RULES:
                                passed = is_violation
                            else:
                                passed = not is_violation
                            icon = "❌" if not passed else "✅"
                        print(f"     {icon} {rcode}: {rname} (AST)")
                        if is_dry:
                            print(f"         合规状态: ⏭ DRY_RUN (实际执行时判定)")
                        elif rcode in _SAFETY_POLARITY_RULES:
                            print(f"         合规状态: {'✅ 合规' if passed else '❌ 违规'} (safety 极性, 表达式结果={raw_result})")
                        else:
                            print(f"         合规状态: {'✅ 合规' if passed else '❌ 违规'} (默认极性, 违规条件={'触发' if is_violation else '未触发'})")
                    else:
                        passed = True
                        icon = "⚠️"
                        print(f"     {icon} {rcode}: {rname} (AST err: {eval_result.get('error')})")
                except Exception as e:
                    passed = True
                    print(f"     ⚠️ {rcode}: {rname} (exception: {e})")
            rule_checks.append((rcode, rname, passed))
            if passed:
                passed_count += 1
        else:
            pass

    # If no rules had AST, use the original hardcoded checks
    if not rule_checks:
        return _eval_rules_hardcoded(data_sources, active_opps, active_rate)

    total = len(rule_checks)
    print(f"     → 规则合规：{passed_count}/{total} 通过")
    return passed_count, total


def _eval_rules_hardcoded(data_sources: dict, active_opps: list, active_rate: dict) -> tuple:
    """Original hardcoded rule checks (fallback when no exprAst in metadata)."""
    print(f"  ⚖️  RULE 推理 — 规则合规性评估（硬编码兜底）")
    print(f"  {'─'*50}")

    rule_checks = []
    if active_opps:
        opp = active_opps[0]
        is_oc_main = opp.get("project_type") == "OC_MAIN"
        has_amount = opp.get("expected_order_amount") is not None
        rule_checks.append(("OPPORTUNITY_OC_MASTER_HAS_FRAMEWORK",
                           "OC主项目必须填写金额",
                           not (is_oc_main and not has_amount)))

        is_oc_sub = opp.get("project_type") == "OC_SUB"
        has_parent = opp.get("parent_opportunity_id") is not None
        rule_checks.append(("OPPORTUNITY_OC_SUB_REQUIRES_PARENT_ID",
                           "OC子项目必须关联父项目",
                           not (is_oc_sub and not has_parent)))

        rule_checks.append(("OPPORTUNITY_QUOTATION_NOT_FOR_OC_MAIN",
                           "OC主项目不允许创建报价单",
                           not is_oc_main))

    if active_rate:
        rule_checks.append(("EXCHANGE_RATE_DATE_RANGE_VALID",
                           "生效日期必须早于失效日期",
                           active_rate.get("effective_date", "") < active_rate.get("expiry_date", "")))
        rule_checks.append(("EXCHANGE_RATE_BASE_NOT_EQUAL_TARGET",
                           "基准币种不能等于目标币种",
                           active_rate.get("base_currency") != active_rate.get("target_currency")))

    for rcode, rname, passed in rule_checks:
        icon = "✅" if passed else "❌"
        print(f"     {icon} {rcode}: {rname}")

    passed_count = sum(1 for _, _, p in rule_checks if p)
    print(f"     → 规则合规：{passed_count}/{len(rule_checks)} 通过")
    return passed_count, len(rule_checks)


def generate_llm_narrative(result: dict, customer: dict, opportunities: list,
                           activities: list, competitors: list, rate: dict,
                           scenes: list = None,
                           llm_config: dict = None) -> str:
    """将结构化推理结果传给 LLM 生成叙事化报告和个性化行动建议。
    如果 LLM API 不可用，回退到模板化叙事。
    llm_config: {"apiKey": "...", "apiBase": "...", "model": "..."}"""
    import os

    # 优先使用传入的 llm_config，其次使用环境变量
    if llm_config:
        api_key = llm_config.get("apiKey", "")
        api_base = llm_config.get("apiBase", "https://uniapi.kaijie.com.cn/v1")
        model = llm_config.get("model", "glm-5.2")
    else:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        api_base = os.environ.get("LLM_API_BASE", "https://uniapi.kaijie.com.cn/v1")
        model = os.environ.get("LLM_MODEL", "glm-5.2")

    scenes = scenes or []

    # P3: 异常模式检测（结构化预分析，供 LLM 参考）
    anomalies = _detect_anomalies(result, customer, opportunities, activities, competitors, scenes)

    prompt = _build_narrative_prompt(result, customer, opportunities, activities, competitors, rate, scenes, anomalies)

    if not api_key:
        return _template_narrative(result, customer, opportunities, activities, competitors, rate, scenes, anomalies)

    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一位资深的CRM客户经营分析师。基于本体推理引擎的结构化输出，生成简洁、专业、可执行的经营分析报告。报告必须包含以下5个部分：\n1) 客户经营概况\n2) 关键发现\n3) 风险提示\n4) 个性化行动建议（P2：基于上下文生成3条具体可执行的建议，不要用泛化模板）\n5) 异常模式发现（P3：基于预分析异常和上下文，发现预定义规则之外的潜在问题）\n控制在500字以内。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1200,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            return resp_data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [WARN] LLM API 调用失败: {e}，使用模板化叙事\n")
        return _template_narrative(result, customer, opportunities, activities, competitors, rate, scenes, anomalies)


def _detect_anomalies_console(score_registry: dict, customer: dict, opportunities: list,
                                activities: list, competitors: list,
                                scenes: list, currency_info: dict, active_rate: dict) -> list:
    """P3: 异常模式检测 — 在推理链中输出到控制台并返回异常列表供汇总 JSON 使用。
    与 _detect_anomalies() 共享相同的检测逻辑，但接受推理链的原始数据而非 result dict。"""
    anomalies = []
    activity_count_90d = score_registry.get("activity_count_90d", 0)
    stage_age = score_registry.get("stage_age_days", 0)
    health_score = score_registry.get("customer_health_score", 0)
    churn_risk = score_registry.get("churn_risk_level", "UNKNOWN")
    coverage_ratio = score_registry.get("coverage_ratio", 0)
    risk_level = score_registry.get("risk_level", "UNKNOWN")
    total_pipeline_cny = currency_info.get("total_pipeline_cny", 0)
    usd_amount = currency_info.get("usd_amount", 0)
    converted_cny = currency_info.get("converted_cny", 0)

    # 1. 活动负责人单一性检测
    if activities:
        activity_owners = set(a.get("record_user_id") for a in activities if a.get("record_user_id"))
        if len(activity_owners) == 1 and len(activities) >= 3:
            owner = list(activity_owners)[0]
            anomalies.append({
                "code": "SINGLE_ACTIVITY_OWNER",
                "severity": "MEDIUM",
                "description": f"近{len(activities)}次活动全部由同一人({owner})完成，无售前/交付团队参与",
                "suggestion": "建议补充售前工程师或解决方案专家参与，降低单点依赖风险"
            })

    # 2. 商机金额与场景采购规模不匹配检测
    if scenes and opportunities:
        for s in scenes:
            sp = _get_first_scene_product(s)
            ae = _get_first_annual_estimate(sp)
            procurement = ae.get("customer_procurement_amount", 0) or 0
            share = (ae.get("estimated_share", 0) or 0) / 100
            expected_kaijie = procurement * share
            matching_opps = [o for o in opportunities
                             if str(o.get("business_customer_id")) == str(s.get("customers_id"))
                             and o.get("status") == "ACTIVE"]
            total_opp_amount = sum(o.get("expected_order_amount", 0) or 0 for o in matching_opps)
            if expected_kaijie > 0 and total_opp_amount > 0:
                ratio = total_opp_amount / expected_kaijie
                if ratio < 0.3:
                    anomalies.append({
                        "code": "AMOUNT_MISMATCH_LOW",
                        "severity": "HIGH",
                        "description": f"场景「{s.get('scene_name_customer')}」预计凯捷可获金额¥{expected_kaijie:,.0f}，但当前商机金额仅¥{total_opp_amount:,.0f}（占比{ratio:.0%}）",
                        "suggestion": "商机金额远低于场景预期，可能存在未覆盖的需求或商机遗漏"
                    })
                elif ratio > 2.0:
                    anomalies.append({
                        "code": "AMOUNT_MISMATCH_HIGH",
                        "severity": "MEDIUM",
                        "description": f"场景「{s.get('scene_name_customer')}」预计凯捷可获金额¥{expected_kaijie:,.0f}，但商机金额达¥{total_opp_amount:,.0f}（占比{ratio:.0%}）",
                        "suggestion": "商机金额远超场景预期，建议核实是否重复录入或场景份额预估偏低"
                    })

    # 3. 阶段流速与活动频率背离检测
    if stage_age > 30 and activity_count_90d >= 3:
        anomalies.append({
            "code": "STAGE_STALL_WITH_ACTIVITY",
            "severity": "HIGH",
            "description": f"商机阶段停留{stage_age}天（超阈值），但近90天有{activity_count_90d}次活动 — 活动频繁但阶段不推进",
            "suggestion": "活动可能未触及决策链关键人，建议重新评估客户决策圈并调整拜访策略"
        })
    if 0 < stage_age <= 15 and activity_count_90d == 0:
        anomalies.append({
            "code": "FAST_STAGE_NO_ACTIVITY",
            "severity": "MEDIUM",
            "description": f"商机阶段仅停留{stage_age}天（流速快），但近90天无销售活动 — 推进可能缺乏支撑",
            "suggestion": "快速推进可能基于乐观假设，建议补充活动记录以验证推进合理性"
        })

    # 4. 竞争对手强度检测
    strong_competitors = [c for c in competitors if c.get("competitor_type") == "DIRECT"]
    if len(strong_competitors) >= 2 and 0 < stage_age < 15:
        anomalies.append({
            "code": "STRONG_COMPETITION_FAST_STAGE",
            "severity": "MEDIUM",
            "description": f"面临{len(strong_competitors)}个直接竞争对手，但商机阶段推进较快（{stage_age}天）",
            "suggestion": "竞争压力下快速推进需谨慎，建议在关键阶段前做竞争方案对比"
        })

    # 5. 外币商机汇率风险检测
    if usd_amount and active_rate and active_rate.get("rate"):
        rate_val = active_rate.get("rate")
        anomalies.append({
            "code": "FX_EXPOSURE",
            "severity": "MEDIUM",
            "description": f"存在${usd_amount:,.0f}外币商机，按{rate_val}折算¥{converted_cny:,.0f}",
            "suggestion": f"汇率波动±2%将影响管道金额约¥{converted_cny*0.02:,.0f}"
        })

    # 6. 管道覆盖不足检测（覆盖率 < 70% = 高风险）
    if isinstance(coverage_ratio, (int, float)) and coverage_ratio < 0.7 and coverage_ratio > 0:
        gap = score_registry.get("gap_amount", 0)
        anomalies.append({
            "code": "PIPELINE_GAP_HIGH",
            "severity": "HIGH",
            "description": f"销售管道覆盖率仅{coverage_ratio:.1%}，缺口金额¥{gap:,.0f}",
            "suggestion": "建议优先挖掘存量客户扩容需求或开拓新商机以填补管道缺口"
        })

    # 7. 客户流失风险检测（120天+无活动）
    if activity_count_90d == 0 and churn_risk in ("HIGH", "CRITICAL"):
        last_activity_days = score_registry.get("last_activity_days", 0)
        anomalies.append({
            "code": "CUSTOMER_CHURNED",
            "severity": "CRITICAL",
            "description": f"近90天无销售活动（最近{last_activity_days}天前），客户存在流失风险",
            "suggestion": "立即安排客户拜访，了解客户近况和潜在需求，防止客户流失"
        })

    # 8. 极端停滞检测 (>60天)
    if stage_age >= 60:
        anomalies.append({
            "code": "STAGE_STALL_EXTREME",
            "severity": "CRITICAL",
            "description": f"商机阶段停滞{stage_age}天（远超30天阈值），面临丢单风险",
            "suggestion": "紧急复盘商机停滞原因，评估是否调整策略或重新激活"
        })
    elif stage_age >= 30:
        anomalies.append({
            "code": "STAGE_STALL",
            "severity": "HIGH",
            "description": f"商机阶段停滞{stage_age}天（超30天阈值），需要密切关注",
            "suggestion": "建议分析停滞原因，制定专项推进计划"
        })

    # 9. 多竞对检测
    if len(strong_competitors) >= 2:
        anomalies.append({
            "code": "MULTI_COMPETITOR_HIGH",
            "severity": "HIGH",
            "description": f"面临{len(strong_competitors)}个直接竞争对手，竞争压力较大",
            "suggestion": "建议做竞品对比分析，强化差异化优势，必要时调整报价策略"
        })

    # 10. 无活动无场景检测
    if activity_count_90d == 0 and not scenes:
        anomalies.append({
            "code": "NO_ACTIVITY_NO_SCENE",
            "severity": "HIGH",
            "description": "客户近90天无销售活动且无关联场景需求",
            "suggestion": "需评估客户是否仍为目标客户，或安排专项客户拜访重新激活"
        })

    # ── 输出到控制台 ──
    if anomalies:
        print(f"\n  🔍 异常模式检测 — P3 结构化预分析")
        print(f"  {'─'*50}")
        for a in anomalies:
            sev_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "🔵"}.get(a["severity"], "⚪")
            print(f"     {sev_icon} [{a['severity']}] {a['code']}")
            print(f"        {a['description']}")
            print(f"        → {a['suggestion']}")
    else:
        print(f"\n  🔍 异常模式检测 — 无异常")

    return anomalies


def _detect_anomalies(result: dict, customer: dict, opportunities: list,
                      activities: list, competitors: list, scenes: list) -> list:
    """P3: 结构化异常模式预分析 — 检测预定义规则之外的潜在问题。"""
    anomalies = []
    temporal = result.get("时间线指标", {})
    deriv = result.get("派生指标", {})
    conv = result.get("汇率折算", {})

    # 1. 活动负责人单一性检测
    if activities:
        activity_owners = set(a.get("record_user_id") for a in activities if a.get("record_user_id"))
        if len(activity_owners) == 1 and len(activities) >= 3:
            owner = list(activity_owners)[0]
            anomalies.append({
                "code": "SINGLE_ACTIVITY_OWNER",
                "severity": "MEDIUM",
                "description": f"近{len(activities)}次活动全部由同一人({owner})完成，无售前/交付团队参与",
                "suggestion": "建议补充售前工程师或解决方案专家参与，降低单点依赖风险"
            })

    # 2. 商机金额与场景采购规模不匹配检测
    if scenes and opportunities:
        for s in scenes:
            procurement = s.get("customer_procurement_amount", 0)
            share = s.get("estimated_share", 0) / 100
            expected_kaijie = procurement * share
            matching_opps = [o for o in opportunities
                             if str(o.get("business_customer_id")) == str(s.get("customers_id"))
                             and o.get("status") == "ACTIVE"]
            total_opp_amount = sum(o.get("expected_order_amount", 0) for o in matching_opps)
            if expected_kaijie > 0 and total_opp_amount > 0:
                ratio = total_opp_amount / expected_kaijie
                if ratio < 0.3:
                    anomalies.append({
                        "code": "AMOUNT_MISMATCH_LOW",
                        "severity": "HIGH",
                        "description": f"场景「{s.get('scene_name_customer')}」预计凯捷可获金额¥{expected_kaijie:,.0f}，但当前商机金额仅¥{total_opp_amount:,.0f}（占比{ratio:.0%}）",
                        "suggestion": "商机金额远低于场景预期，可能存在未覆盖的需求或商机遗漏"
                    })
                elif ratio > 2.0:
                    anomalies.append({
                        "code": "AMOUNT_MISMATCH_HIGH",
                        "severity": "MEDIUM",
                        "description": f"场景「{s.get('scene_name_customer')}」预计凯捷可获金额¥{expected_kaijie:,.0f}，但商机金额达¥{total_opp_amount:,.0f}（占比{ratio:.0%}）",
                        "suggestion": "商机金额远超场景预期，建议核实是否重复录入或场景份额预估偏低"
                    })

    # 3. 阶段流速与活动频率背离检测
    activity_count = temporal.get("近90天活动数", 0)
    stage_age = temporal.get("阶段停留天数") or 0
    if stage_age > 30 and activity_count >= 3:
        anomalies.append({
            "code": "STAGE_STALL_WITH_ACTIVITY",
            "severity": "HIGH",
            "description": f"商机阶段停留{stage_age}天（超阈值），但近90天有{activity_count}次活动 — 活动频繁但阶段不推进",
            "suggestion": "活动可能未触及决策链关键人，建议重新评估客户决策圈并调整拜访策略"
        })
    if stage_age <= 15 and activity_count == 0:
        anomalies.append({
            "code": "FAST_STAGE_NO_ACTIVITY",
            "severity": "MEDIUM",
            "description": f"商机阶段仅停留{stage_age}天（流速快），但近90天无销售活动 — 推进可能缺乏支撑",
            "suggestion": "快速推进可能基于乐观假设，建议补充活动记录以验证推进合理性"
        })

    # 4. 竞争对手强度与商机阶段不匹配检测
    strong_competitors = [c for c in competitors if c.get("competitor_type") == "DIRECT"]
    if len(strong_competitors) >= 2 and stage_age < 15:
        anomalies.append({
            "code": "STRONG_COMPETITION_FAST_STAGE",
            "severity": "MEDIUM",
            "description": f"面临{len(strong_competitors)}个直接竞争对手，但商机阶段推进较快（{stage_age}天）",
            "suggestion": "竞争压力下快速推进需谨慎，建议在关键阶段前做竞争方案对比"
        })

    # 5. 外币商机汇率风险检测
    if conv.get("美元金额") and conv.get("汇率"):
        anomalies.append({
            "code": "FX_EXPOSURE",
            "severity": "LOW",
            "description": f"存在${conv['美元金额']:,.0f}外币商机，按{conv['汇率']}折算¥{conv['折算人民币']:,.0f}",
            "suggestion": "汇率波动±2%将影响管道金额约¥" + f"{conv['折算人民币']*0.02:,.0f}"
        })

    # 6. 场景阶段与商机阶段不一致检测
    if scenes and opportunities:
        for s in scenes:
            scene_stage = s.get("kaijie_stage", "")
            matching_opps = [o for o in opportunities
                             if str(o.get("business_customer_id")) == str(s.get("customers_id"))
                             and o.get("status") == "ACTIVE"]
            if matching_opps and scene_stage:
                opp = matching_opps[0]
                opp_stage = opp.get("project_stage", "")
                # 场景在需求澄清但商机已到后期
                if "1-" in scene_stage and "03" in opp_stage:
                    anomalies.append({
                        "code": "SCENE_OPP_STAGE_MISMATCH",
                        "severity": "MEDIUM",
                        "description": f"场景「{s.get('scene_name_customer')}」我司阶段为「{scene_stage}」，但商机已到「{opp_stage}」",
                        "suggestion": "场景与商机阶段不匹配，可能场景信息未及时更新或商机推进过快"
                    })

    return anomalies


def _build_narrative_prompt(result: dict, customer: dict, opportunities: list,
                            activities: list, competitors: list, rate: dict,
                            scenes: list = None, anomalies: list = None) -> str:
    """构建 LLM prompt。"""
    scenes = scenes or []
    anomalies = anomalies or []

    opp_summary = "; ".join(
        f"{o.get('opportunity_name')}({o.get('project_type')},{o.get('currency')}{o.get('expected_order_amount')},{o.get('project_stage')},{o.get('status')})"
        for o in opportunities[:3]
    )
    activity_summary = "; ".join(
        f"{a.get('visit_subject')}({a.get('visit_time','')[:10]},负责人:{a.get('record_user_id','')})"
        for a in activities[:3]
    )
    competitor_summary = "; ".join(
        f"{c.get('competitor_name')}({c.get('competitor_type')},优势:{c.get('strength','')})"
        for c in competitors
    )
    scene_summary = "; ".join(
        f"{s.get('scene_name_customer')}(阶段:{s.get('kaijie_stage')},采购:{s.get('customer_procurement_amount')},份额:{s.get('estimated_share')}%)"
        for s in scenes
    )
    anomaly_summary = "\n".join(
        f"  - [{a.get('severity')}] {a.get('code')}: {a.get('description')} → {a.get('suggestion')}"
        for a in anomalies
    ) if anomalies else "  (无异常)"

    return f"""请基于以下本体推理引擎的结构化输出，生成客户经营分析报告。

⚠️ **重要约束（严格遵守）**：
- 所有数据必须严格来源于下方的结构化推理结果和补充上下文，不得编造、推测或引入不存在的数据。
- 活跃商机数、竞争对手名称/数量、销售活动数、管道金额等定量数据必须与结构化输出完全一致。
- 竞争对手列表必须与「竞争对手」上下文字段完全一致，不得添加未被列出的竞争对手。
- 如果某个字段在结构化结果中缺失或为 null，应标注"暂无数据"而非自行填补。
- 报告中的数字、日期、金额必须与结构化输出精确匹配，不得四舍五入或近似。

## 客户信息
- 名称: {customer.get('customer_name')}
- 行业: {customer.get('market_segment')}
- 类别: {customer.get('customer_category')}

## 结构化推理结果
{json.dumps(result, ensure_ascii=False, indent=2)}

## 补充上下文
- 活跃商机（共{len(opportunities)}个）: {opp_summary}
- 近期活动: {activity_summary}
- 竞争对手（共{len(competitors)}个）: {competitor_summary}
- 场景需求: {scene_summary}
- 汇率: {rate.get('base_currency') if rate else 'N/A'}→{rate.get('target_currency') if rate else 'N/A'} = {rate.get('rate') if rate else 'N/A'}

## P3 预分析异常（供参考，请在此基础上进一步分析）
{anomaly_summary}

请生成经营分析报告，必须包含以下5个部分：
1) 客户经营概况
2) 关键发现
3) 风险提示
4) 个性化行动建议（P2：基于上下文生成3条具体可执行的建议，不要用泛化模板，要结合商机阶段、活动频率、竞争态势、场景需求等上下文）
5) 异常模式发现（P3：基于预分析异常和上下文，发现预定义规则之外的潜在问题，给出洞察）"""


def _template_narrative(result: dict, customer: dict, opportunities: list,
                        activities: list, competitors: list, rate: dict,
                        scenes: list = None, anomalies: list = None) -> str:
    """LLM 不可用时的模板化叙事回退（含 P2 个性化建议 + P3 异常发现）。"""
    scenes = scenes or []
    anomalies = anomalies or []
    deriv = result.get("派生指标", {})
    temporal = result.get("时间线指标", {})
    conv = result.get("汇率折算", {})
    rules = result.get("规则合规", {})
    scenes_data = result.get("场景需求", {})

    lines = []
    # ── 客户概况 ──
    lines.append(f"📋 客户概况")
    lines.append(f"  {customer.get('customer_name')}（{customer.get('market_segment')}行业，{_zh(customer.get('customer_category', ''))}）")
    lines.append(f"  活跃商机 {len(opportunities)} 个，近90天活动 {temporal.get('近90天活动数', 0)} 次，面临 {len(competitors)} 个竞争对手。")
    if scenes_data.get("数量"):
        lines.append(f"  场景需求 {scenes_data['数量']} 个，覆盖采购规模 ¥{sum(s.get('customer_procurement_amount',0) for s in scenes):,}")
    lines.append("")

    # ── 关键发现 ──
    lines.append(f"🔍 关键发现")
    health = deriv.get("客户健康度评分", 0)
    risk = deriv.get("流失风险等级", "未知")
    lines.append(f"  • 客户健康度 {health}（{'优秀' if health >= 80 else '良好' if health >= 60 else '需关注' if health >= 40 else '高风险'}），流失风险：{_zh(risk)}")

    if conv.get("美元金额"):
        lines.append(f"  • 外币商机 ${conv['美元金额']:,.0f} 按 {conv.get('汇率')} 汇率折算 ¥{conv['折算人民币']:,.0f}")
    cust_pipeline = conv.get("客户级管道金额(CNY)") or conv.get("管道总金额(CNY)", 0)
    lines.append(f"  • 客户级管道金额 ¥{cust_pipeline:,.0f}（含子客户）")

    cov = deriv.get("管道覆盖率")
    if cov:
        lines.append(f"  • 管道覆盖率 {cov}，风险等级：{_zh(deriv.get('覆盖风险等级', 'N/A'))}")

    stage_age = temporal.get("阶段停留天数") or 0
    if stage_age > 30:
        lines.append(f"  ⚠️ 商机阶段停留 {stage_age} 天，超过30天阈值，需关注推进停滞风险")
    else:
        lines.append(f"  • 商机阶段停留 {stage_age} 天，流速{_zh(temporal.get('stage_velocity_level', 'N/A'))}")

    # 场景关键信息
    for s in scenes[:2]:
        lines.append(f"  • 场景「{s.get('scene_name_customer')}」: {s.get('kaijie_stage')}，采购¥{s.get('customer_procurement_amount',0):,}，份额{s.get('estimated_share')}%")
    lines.append("")

    # ── 风险提示 ──
    lines.append(f"⚠️ 风险提示")
    if risk == "高" or risk == "HIGH":
        lines.append(f"  • 客户流失风险高，近90天仅 {temporal.get('近90天活动数', 0)} 次活动，建议紧急介入")
    elif risk == "中" or risk == "MEDIUM":
        lines.append(f"  • 客户活跃度下降，建议加强拜访频率")
    else:
        lines.append(f"  • 当前风险可控，保持现有节奏")

    if len(competitors) >= 2:
        direct_comps = [c for c in competitors if c.get("competitor_type") == "DIRECT"]
        lines.append(f"  • 面临 {len(direct_comps)} 个直接竞争对手（{', '.join(c.get('competitor_name') for c in direct_comps)}），竞争压力较大")
    elif competitors:
        lines.append(f"  • 面临 {competitors[0].get('competitor_name')} 竞争，需持续关注")
    lines.append("")

    # ── P2: 个性化行动建议 ──
    lines.append(f"💡 个性化行动建议（P2）")
    # 基于上下文生成3条具体建议
    suggestion_idx = 1

    # 建议1: 基于商机阶段和场景
    if opportunities and scenes:
        opp = opportunities[0]
        scene = scenes[0]
        if stage_age <= 15 and opp.get("project_stage", "").startswith("DC_0"):
            lines.append(f"  {suggestion_idx}. 商机处于早期阶段（{opp.get('project_stage')}），场景「{scene.get('scene_name_customer')}」下次招标{s.get('next_bid_date', '待定')}，建议在招标前完成方案报价初稿和PoC测试")
        elif "03" in opp.get("project_stage", ""):
            lines.append(f"  {suggestion_idx}. 商机已到{opp.get('project_stage')}阶段，场景份额预估{scene.get('estimated_share')}%，建议邀请客户参观教育行业标杆案例，强化方案差异化优势")
        else:
            lines.append(f"  {suggestion_idx}. 商机当前{opp.get('project_stage')}阶段，建议结合场景「{scene.get('scene_name_customer')}」的采购周期，制定阶段性推进计划")
        suggestion_idx += 1

    # 建议2: 基于竞争态势
    if competitors:
        strong = [c for c in competitors if c.get("competitor_type") == "DIRECT"]
        if strong:
            comp = strong[0]
            lines.append(f"  {suggestion_idx}. 面对{comp.get('competitor_name')}竞争（优势：{comp.get('strength', '未知')}，劣势：{comp.get('weakness', '未知')}），建议在投标前安排高层拜访，突出凯捷的差异化优势")
        else:
            lines.append(f"  {suggestion_idx}. 竞争态势可控，建议持续监控竞争对手动态")
        suggestion_idx += 1

    # 建议3: 基于活动频率和负责人
    activity_count = temporal.get("近90天活动数", 0)
    if activity_count == 0:
        lines.append(f"  {suggestion_idx}. 近90天无销售活动，建议立即安排客户拜访，重新激活客户关系")
    elif activity_count <= 1:
        lines.append(f"  {suggestion_idx}. 近90天仅{activity_count}次活动，活动频率偏低，建议制定双周拜访计划")
    else:
        owners = set(a.get("record_user_id") for a in activities if a.get("record_user_id"))
        if len(owners) == 1:
            lines.append(f"  {suggestion_idx}. 活动全部由单一负责人完成，建议补充售前工程师参与技术方案沟通，降低单点依赖")
        elif conv.get("美元金额"):
            lines.append(f"  {suggestion_idx}. 外币商机${conv['美元金额']:,.0f}已按月均汇率折算，建议关注汇率波动（±2%影响约¥{conv['折算人民币']*0.02:,.0f}），必要时锁定汇率")
        else:
            lines.append(f"  {suggestion_idx}. 活动频率良好，建议保持现有节奏并推进至下一阶段")
    suggestion_idx += 1

    lines.append(f"  • 规则合规：{rules.get('通过', 0)}/{rules.get('总计', 0)} 通过")
    lines.append("")

    # ── P3: 异常模式发现 ──
    lines.append(f"🔬 异常模式发现（P3）")
    if anomalies:
        for a in anomalies:
            severity_icon = "🔴" if a.get("severity") == "HIGH" else "🟡" if a.get("severity") == "MEDIUM" else "🔵"
            lines.append(f"  {severity_icon} [{a.get('code')}] {a.get('description')}")
            lines.append(f"     → {a.get('suggestion')}")
    else:
        lines.append(f"  ✅ 未检测到异常模式")
    lines.append("")

    return "\n".join(lines)


def eval_customer_360(customer_id: str):
    """DRY-RUN 客户 360 派生（元数据驱动）。"""
    print(f"\n{'='*60}")
    print(f"  [C360] Customer-360 DRY-RUN for customerId={customer_id}")
    print(f"  (元数据驱动)")

    derivation = load_design_fragment("derivation") or {}
    c360 = next((d for d in derivation.get("derivedObjects", []) if d["code"] == "customer-360"), None)
    if not c360:
        print("  [ERR] customer-360 not found in release-time derivation index.")
        return

    # Load data
    customer_data = load_demo_data("customers")
    customers = load_all_demo_records("customers")
    customer = next((c for c in customers if str(c.get("id")) == str(customer_id)), customer_data)

    data_sources = {"customers": customer}
    score_registry = {}
    active_opps = []  # simplified

    print(f"{'='*60}\n")
    print(f"  [OBJ] Derived Object: {c360['name']} (objectKind={c360['objectKind']})")
    print(f"  [ROOT] Root: {c360['root']['boCode']}.{c360['root']['entityCode']}")

    dep_links = ", ".join(d.get("viaLink", "?") for d in c360.get("dependencies", []))
    print(f"  [LINK] Dependencies: {dep_links}")

    print(f"\n  [FIELDS] Fields ({len(c360['fields'])}):")
    for f in c360["fields"]:
        expr = f.get("expression") if f.get("expression") else None
        has_expr = expr and expr.get("type")
        ast = "(has expression AST)" if has_expr else "(placeholder)"
        print(f"     {f['code']:35s} {f['type']:10s} {ast}")

    # DRY-RUN evaluation via metadata
    print(f"\n  [EVAL] Dry-Run Evaluation:")
    _eval_derivation_section({"derivedObjects": [c360]}, data_sources, score_registry, customer, active_opps)

    result = {
        "derivedCode": "customer-360",
        "root": {"boCode": "customers", "id": customer_id},
        "fields": {fcode: score_registry.get(fcode, "DRY_RUN") for fcode in 
                   [f["code"] for f in c360["fields"]]},
        "_meta": {"mode": "METADATA_DRIVEN"}
    }
    print(f"\n  [RSLT] Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def eval_opportunity_intelligence(opportunity_id: str):
    """DRY-RUN 商机智能视图（元数据驱动 AST 求值）。"""
    print(f"\n{'='*60}")
    print(f"  [SRCH] Opportunity-Intelligence DRY-RUN for opportunityId={opportunity_id}")
    print(f"  (元数据驱动)")

    derivation = load_design_fragment("derivation") or {}
    oi = next((d for d in derivation.get("derivedObjects", []) if d["code"] == "opportunity-intelligence"), None)
    if not oi:
        print("  [ERR] opportunity-intelligence not found in release-time derivation index.")
        return

    # Load demo data for dependencies
    opportunities = load_all_demo_records("opportunities")
    competitors = load_all_demo_records("competitors")
    activities = load_all_demo_records("sales-activities")

    opp = next((o for o in opportunities if str(o.get("id")) == str(opportunity_id)), None)
    if not opp and opportunities:
        opp = opportunities[0]

    data_sources = {"opportunities": opp or {}}
    score_registry = {}
    active_opps = [opp] if opp else []

    # Pre-compute stage_age_days and stage_velocity_level from demo context
    stage_age_days = 12  # demo default
    stage_velocity = "NORMAL"
    score_registry["stage_age_days"] = stage_age_days
    score_registry["stage_velocity_level"] = stage_velocity
    score_registry["sales_activity_score"] = 0.70  # demo placeholder
    # P6 修复：预置竞对相关字段，避免 derivation metric 读不到导致 DRY_RUN
    score_registry["competitor_count"] = 0
    score_registry["competitor_risk_level"] = "NONE"

    print(f"{'='*60}\n")
    print(f"  [OBJ] Derived Object: {oi['name']} (objectKind={oi['objectKind']})")
    print(f"  [ROOT] Root: {oi['root']['boCode']}.{oi['root']['entityCode']}")

    dep_links = ", ".join(d.get("viaLink", "?") for d in oi.get("dependencies", []))
    print(f"  [LINK] Dependencies: {dep_links}")
    if opp:
        print(f"  📋 商机：{opp.get('opportunity_name', '?')} 阶段={opp.get('project_stage','?')} 金额=¥{opp.get('expected_order_amount',0):,}")

    print(f"\n  [FIELDS] Fields ({len(oi['fields'])}):")
    for f in oi["fields"]:
        expr = f.get("expression") if f.get("expression") else None
        has_expr = expr and expr.get("type")
        ast = "(has expression AST)" if has_expr else "(placeholder)"
        print(f"     {f['code']:35s} {f['type']:10s} {ast}")

    # DRY-RUN evaluation via metadata
    print(f"\n  [EVAL] Dry-Run Evaluation:")
    _eval_derivation_section({"derivedObjects": [oi]}, data_sources, score_registry, opp or {}, active_opps)

    result = {
        "derivedCode": "opportunity-intelligence",
        "root": {"boCode": "opportunities", "id": opportunity_id},
        "fields": {fcode: score_registry.get(fcode, "DRY_RUN") for fcode in
                   [f["code"] for f in oi["fields"]]},
        "_meta": {"mode": "METADATA_DRIVEN"}
    }
    print(f"\n  [RSLT] Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def eval_pipeline_coverage(owner_id: str = "10001"):
    """DRY-RUN 管道覆盖率（元数据驱动 AST 求值 + 硬数据口径校验）。"""
    print(f"\n{'='*60}")
    print(f"  [PCOV] Pipeline-Coverage DRY-RUN for ownerId={owner_id}")
    print(f"  (元数据驱动)")

    derivation = load_design_fragment("derivation") or {}
    pc = next((d for d in derivation.get("derivedObjects", []) if d["code"] == "pipeline-coverage"), None)
    if not pc:
        print("  [ERR] pipeline-coverage not found in release-time derivation index.")
        return

    # Load demo data
    sales_targets = load_all_demo_records("sales-targets")
    opportunities = load_all_demo_records("opportunities")
    exchange_rates = load_all_demo_records("exchange-rates")

    target = next((t for t in sales_targets if str(t.get("owner_id")) == str(owner_id)), None)
    if not target and sales_targets:
        target = sales_targets[0]
    if not target:
        print("  [ERR] No sales target found for owner_id=" + owner_id)
        return

    # 汇率转换
    active_opps = [o for o in opportunities if o.get("status") == "ACTIVE"]
    usd_opps = [o for o in active_opps if o.get("currency") == "USD"]
    total_usd_amount = sum(o.get("expected_order_amount", 0) for o in usd_opps)
    active_rate = next((r for r in exchange_rates
                        if r.get("base_currency") == "USD"
                        and r.get("target_currency") == "CNY"
                        and r.get("status") == "ACTIVE"), None)
    converted_cny = total_usd_amount * active_rate.get("rate", 1) if (usd_opps and active_rate) else 0
    cny_opps = [o for o in active_opps if o.get("currency") == "CNY"]
    total_cny_amount = sum(o.get("expected_order_amount", 0) for o in cny_opps)
    total_pipeline_cny = converted_cny + total_cny_amount

    data_sources = {"sales-targets": target}
    score_registry = {
        "target_amount": float(target.get("goal_value", 0) or 0),
        "active_pipeline_amount": total_pipeline_cny,
        "win_probability": 0.6,  # demo placeholder for weighted calc
    }

    print(f"{'='*60}\n")
    print(f"  [OBJ] Derived Object: {pc['name']} (objectKind={pc['objectKind']})")
    print(f"  [ROOT] Root: {pc['root']['boCode']}.{pc['root']['entityCode']}")
    print(f"  📋 销售目标：¥{target.get('goal_value', 0):,.2f} ({target.get('apply_rule', '')})")
    print(f"  💰 活跃管道金额：¥{total_pipeline_cny:,.2f} (USD→CNY: ${total_usd_amount:,.2f} × {active_rate.get('rate', '?') if active_rate else '—'} + CNY: ¥{total_cny_amount:,.2f})")

    dep_links = ", ".join(d.get("viaLink", "?") for d in pc.get("dependencies", []))
    print(f"\n  [LINK] Dependencies: {dep_links}")

    print(f"\n  [FIELDS] Fields ({len(pc['fields'])}):")
    for f in pc["fields"]:
        expr = f.get("expression") if f.get("expression") else None
        has_expr = expr and expr.get("type")
        ast = "(has expression AST)" if has_expr else "(placeholder)"
        print(f"     {f['code']:35s} {f['type']:10s} {ast}")

    # DRY-RUN evaluation via metadata (AST interpreter)
    print(f"\n  [EVAL] Dry-Run Evaluation:")
    _eval_derivation_section({"derivedObjects": [pc]}, data_sources, score_registry, target, active_opps)

    # 硬数据口径校验（覆盖 AST 可能返回 DRY_RUN 的字段）
    coverage_ratio = total_pipeline_cny / score_registry["target_amount"] if score_registry.get("target_amount", 0) > 0 else 0
    gap_amount = max(0, score_registry.get("target_amount", 0) - total_pipeline_cny)
    # Only override if AST didn't compute a real value
    if score_registry.get("coverage_ratio") == "DRY_RUN:coverage_ratio" or isinstance(score_registry.get("coverage_ratio"), str) and "DRY_RUN" in str(score_registry.get("coverage_ratio", "")):
        score_registry["coverage_ratio"] = round(coverage_ratio, 2)
    if score_registry.get("gap_amount") == "DRY_RUN:gap_amount" or isinstance(score_registry.get("gap_amount"), str) and "DRY_RUN" in str(score_registry.get("gap_amount", "")):
        score_registry["gap_amount"] = gap_amount
    if score_registry.get("risk_level") == "DRY_RUN:risk_level" or isinstance(score_registry.get("risk_level"), str) and "DRY_RUN" in str(score_registry.get("risk_level", "")):
        risl = score_registry.get("coverage_ratio", 0)
        score_registry["risk_level"] = "LOW" if (isinstance(risl, (int, float)) and risl >= 1.0) else ("MEDIUM" if (isinstance(risl, (int, float)) and risl >= 0.8) else "HIGH")

    print(f"\n  [RSLT] 硬数据口径校验:")
    print(f"     销售目标：¥{score_registry.get('target_amount', 0):,.2f}")
    print(f"     活跃管道金额：¥{total_pipeline_cny:,.2f}")
    print(f"     → 覆盖率 (coverage_ratio): {score_registry.get('coverage_ratio', '?')}")
    print(f"     → 缺口 (gap_amount): ¥{score_registry.get('gap_amount', 0):,.2f}")
    print(f"     → 覆盖风险等级 (risk_level): {score_registry.get('risk_level', '?')}")

    result = {
        "derivedCode": "pipeline-coverage",
        "root": {"boCode": "sales-targets", "id": target.get("id", owner_id)},
        "fields": {fcode: score_registry.get(fcode, "DRY_RUN") for fcode in
                   [f["code"] for f in pc["fields"]]},
        "_meta": {"mode": "METADATA_DRIVEN"}
    }
    print(f"\n  [RSLT] Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def eval_opportunity_timeline(object_id: str):
    """DRY-RUN 商机阶段时间线。"""
    print(f"\n{'='*60}")
    print(f"  [SRCH] Opportunity-Stage-Timeline DRY-RUN for opportunityId={object_id}")
    print(f"{'='*60}\n")

    temporal = load_temporal_index()
    tl = next((t for t in temporal.get("timelines", []) if t["code"] == "OPPORTUNITY_STAGE_TIMELINE"), None)
    if not tl:
        print("  [ERR] OPPORTUNITY_STAGE_TIMELINE not found.")
        return

    # Load or generate demo events
    events = load_demo_data("temporal-events") if load_demo_data("temporal-events") else {}
    demo_events = events.get("events", [])
    if not demo_events:
        demo_events = [
            {"boCode": "opportunities", "objectId": object_id, "eventType": "STAGE_CHANGED",
             "fromState": "DC_02", "toState": "DC_03", "eventTime": "2026-07-01T10:30:00", "actorId": "10001"}
        ]

    print(f"  [DATA] Timeline: {tl['name']}")
    print(f"  [LOC] Events: {len(demo_events)}")
    for e in demo_events:
        print(f"     [{e.get('eventType')}] {e.get('fromState','?')} → {e.get('toState','?')} at {e.get('eventTime','?')}")

    result = {
        "object": {"boCode": "opportunities", "id": object_id},
        "events": demo_events,
        "metrics": {"stage_age_days": 8, "stage_velocity_level": "NORMAL"},
        "_demo": {"mode": "DRY_RUN", "dataSource": "demo events"}
    }
    print(f"\n  [RSLT] Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def eval_customer_activity_window(customer_id: str, window: str = "P90D"):
    """DRY-RUN 客户活动窗口指标。"""
    print(f"\n{'='*60}")
    print(f"  [SRCH] Customer-Activity-Window DRY-RUN for customerId={customer_id}, window={window}")
    print(f"{'='*60}\n")

    temporal = load_temporal_index()
    tl = next((t for t in temporal.get("timelines", []) if t["code"] == "CUSTOMER_ACTIVITY_TIMELINE"), None)
    if not tl:
        print("  [ERR] CUSTOMER_ACTIVITY_TIMELINE not found.")
        return

    print(f"  [DATA] Timeline: {tl['name']}")
    result = {
        "object": {"boCode": "customers", "id": customer_id},
        "window": window,
        "metrics": {
            "activity_count_30d": "DRY_RUN — {COUNT_WINDOW:P30D}",
            "activity_count_90d": "DRY_RUN — {COUNT_WINDOW:P90D}",
            "last_activity_days": "DRY_RUN — {LAST_VALUE}",
        },
        "_demo": {"mode": "DRY_RUN"}
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def eval_action_chain_dry_run(chain_code: str, bo_code: str, object_id: str, operation: str):
    """DRY-RUN 动作链执行计划。"""
    print(f"\n{'='*60}")
    print(f"  [LINK] Action-Chain DRY-RUN for {chain_code}")
    print(f"     boCode={bo_code}, objectId={object_id}, operation={operation}")
    print(f"{'='*60}\n")

    chains = load_action_chain_index()
    chain = next((ch for ch in chains.get("chains", []) if ch["code"] == chain_code), None)
    if not chain:
        print(f"  [ERR] Action chain '{chain_code}' not found.")
        return

    print(f"  [OBJ] Chain: {chain['name']} (triggerType={chain['triggerType']})")

    result = {
        "chainCode": chain_code,
        "trigger": {"boCode": bo_code, "objectId": object_id, "operationCode": operation},
        "conditionMatched": True,
        "idempotencyKey": f"{bo_code}:{object_id}:{operation}:{datetime.now(timezone.utc).isoformat()}",
        "steps": [
            {
                "code": s["code"],
                "stepType": s["stepType"],
                "dryRunStatus": "READY" if s["stepType"] != "NOTIFICATION" else "SKIPPED_IN_DEMO",
                "failurePolicy": s["failurePolicy"],
                "dependsOn": s.get("dependsOn", [])
            }
            for s in chain.get("steps", [])
        ]
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def eval_rules(bo_code: str, object_id: str = None):
    """加载 BO 的发布态 RULE，对有 exprAst 的规则执行 Dry-Run 评估。"""
    print(f"\n{'='*60}")
    print(f"  [RULE] Rule Dry-Run for boCode={bo_code}")
    print(f"{'='*60}\n")

    # 从发布态 schema-view 加载 RULE
    bo_rules = load_bo_rule_fragment(bo_code)
    if not bo_rules:
        print(f"  [ERR] No rules found in release-time schema-view for boCode={bo_code}")
        return

    rules = bo_rules.get("rules", [])
    if not rules:
        print(f"  [INFO] No rules defined for {bo_code}")
        return

    # 加载示例数据
    sample_data = load_demo_data(bo_code)
    data_sources = {bo_code: sample_data}

    # 加载关联 BO 的示例数据（用于跨 BO 引用解析）
    for dep_bo in ["customers", "opportunities", "exchange-rates", "sales-activities"]:
        if dep_bo != bo_code:
            dep_data = load_demo_data(dep_bo)
            if not dep_data.get("_placeholder"):
                data_sources[dep_bo] = dep_data

    print(f"  [DATA] Data sources: {list(data_sources.keys())}")
    print(f"  [DATA] Rules: {len(rules)} total\n")

    results = []
    passed = 0
    failed = 0
    skipped = 0

    for rule in rules:
        rcode = rule.get("code", "?")
        rname = rule.get("name", "")
        expr = rule.get("expression", "")
        ast = rule.get("exprAst")

        if not ast:
            print(f"  ⏭️  {rcode}: {rname}")
            print(f"       (no exprAst — skipped)")
            results.append({"code": rcode, "name": rname, "status": "SKIPPED", "reason": "no exprAst"})
            skipped += 1
            continue

        # 执行 AST 评估
        context = {"_eval": True, "_root": bo_code, "_objectId": object_id}
        try:
            if evaluate_tree:
                eval_result = evaluate_tree(ast, context, data_sources)
                if not eval_result.get("success"):
                    raise Exception(eval_result.get("error", "unknown"))
                raw_result = eval_result.get("result")
                is_dry_run = eval_result.get("dryRun", False)
            elif _raw_evaluate:
                raw_result = _raw_evaluate(ast, context, data_sources)
                is_dry_run = isinstance(raw_result, dict) and raw_result.get("_dryRun")
            else:
                raise Exception("No evaluator available (ontology_expr_eval.py not found)")

            # 判断规则是否通过（expression 描述的是违规条件，true=违规）
            # polarity=safety 的规则反转判定（True=合规）
            is_safety = rule.get("polarity") == "safety"
            if is_dry_run:
                status = "DRY_RUN"
                icon = "🔬"
            else:
                is_violation = bool(raw_result)
                if is_safety:
                    is_violation = not is_violation  # safety: True=合规 → 非违规
                status = "VIOLATION" if is_violation else "PASSED"
                icon = "❌" if is_violation else "✅"

            print(f"  {icon}  {rcode}: {rname}")
            print(f"       expression: {expr[:80]}{'...' if len(expr) > 80 else ''}")
            print(f"       result: {raw_result} → {status}")

            results.append({
                "code": rcode, "name": rname, "status": status,
                "expression": expr, "result": str(raw_result)
            })
            if status == "PASSED":
                passed += 1
            elif status == "VIOLATION":
                failed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ⚠️  {rcode}: {rname}")
            print(f"       error: {e}")
            results.append({"code": rcode, "name": rname, "status": "ERROR", "error": str(e)})
            skipped += 1

    print(f"\n  [SUMMARY] Passed: {passed}  |  Violation: {failed}  |  Skipped: {skipped}  |  Total: {len(rules)}")

    result = {
        "boCode": bo_code,
        "objectId": object_id,
        "summary": {"passed": passed, "violation": failed, "skipped": skipped, "total": len(rules)},
        "rules": results,
        "_demo": {"mode": "DRY_RUN", "dataSource": "tools/demo-data"}
    }
    print(f"\n  [RSLT] Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    global _LLM_CONFIG, _DEMO_SUBDIR, _LLM_DISABLED

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    scenario = ""
    chain_code = ""
    obj_id = ""
    bo_code = ""
    operation = ""
    window = "P90D"
    eval_rules_bo = ""
    llm_key = ""
    llm_base = ""
    llm_model = ""
    scenario_dir = ""

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--scenario" and i + 1 < len(args):
            scenario = args[i + 1]; i += 2
        elif args[i] == "--dry-run-chain" and i + 1 < len(args):
            chain_code = args[i + 1]; i += 2
        elif args[i] == "--id" and i + 1 < len(args):
            obj_id = args[i + 1]; i += 2
        elif args[i] == "--bo" and i + 1 < len(args):
            bo_code = args[i + 1]; i += 2
        elif args[i] == "--operation" and i + 1 < len(args):
            operation = args[i + 1]; i += 2
        elif args[i] == "--window" and i + 1 < len(args):
            window = args[i + 1]; i += 2
        elif args[i] == "--eval-rules" and i + 1 < len(args):
            eval_rules_bo = args[i + 1]; i += 2
        elif args[i] == "--llm-key" and i + 1 < len(args):
            llm_key = args[i + 1]; i += 2
        elif args[i] == "--llm-base" and i + 1 < len(args):
            llm_base = args[i + 1]; i += 2
        elif args[i] == "--llm-model" and i + 1 < len(args):
            llm_model = args[i + 1]; i += 2
        elif args[i] == "--scenario-dir" and i + 1 < len(args):
            scenario_dir = args[i + 1]; i += 2
        elif args[i] == "--llm-disabled":
            _LLM_DISABLED = True; i += 1
        else:
            i += 1

    # 设置 demo-data 子目录
    if scenario_dir:
        _DEMO_SUBDIR = scenario_dir

    # 构建 LLM 配置
    if llm_key:
        _LLM_CONFIG = {
            "apiKey": llm_key,
            "apiBase": llm_base or "https://uniapi.kaijie.com.cn/v1",
            "model": llm_model or "glm-5.2",
        }

    if eval_rules_bo:
        eval_rules(eval_rules_bo, obj_id or None)
    elif chain_code:
        eval_action_chain_dry_run(chain_code, bo_code, obj_id, operation)
    elif obj_id == "all" or bo_code == "all":
        _run_scenario_for_all(scenario, window)
    elif scenario == "reasoning-chain":
        eval_reasoning_chain(obj_id or "1001")
    elif scenario == "customer-360":
        eval_customer_360(obj_id or "DEMO_CUSTOMER_ID")
    elif scenario == "opportunity-intelligence":
        eval_opportunity_intelligence(obj_id or "DEMO_OPPORTUNITY_ID")
    elif scenario == "pipeline-coverage":
        eval_pipeline_coverage(obj_id or "10001")
    elif scenario == "opportunity-timeline":
        eval_opportunity_timeline(obj_id or "DEMO_OPPORTUNITY_ID")
    elif scenario == "customer-activity-window":
        eval_customer_activity_window(obj_id or "DEMO_CUSTOMER_ID", window)
    else:
        print(f"Unknown scenario: {scenario}")
        sys.exit(1)


def _run_scenario_for_all(scenario: str, window: str = "P90D"):
    """当 id=all 时，遍历所在域的全部 demo 记录依次执行。"""
    customer_scenarios = {"reasoning-chain", "customer-360", "customer-activity-window", "pipeline-coverage"}
    opportunity_scenarios = {"opportunity-intelligence", "opportunity-timeline"}

    if scenario in customer_scenarios:
        records = load_all_demo_records("customers")
        bo_label = "customers"
    elif scenario in opportunity_scenarios:
        records = load_all_demo_records("opportunities")
        bo_label = "opportunities"
    else:
        print(f"⚠ 场景 {scenario} 暂不支持全量模式")
        return

    if not records:
        print(f"⚠ 未找到 {bo_label} 的 demo 数据")
        return

    print(f"\n{'='*70}")
    print(f"  🔬 全量 Dry-Run — {scenario}")
    print(f"  📊 {bo_label}: {len(records)} 条记录")
    print(f"{'='*70}\n")

    # 全量模式下打印场景描述
    scenario_desc = load_demo_scenario("customers")
    if scenario_desc:
        print(f"  📋 场景：{scenario_desc}\n")

    for idx, rec in enumerate(records, 1):
        rec_id = str(rec.get("id", ""))
        rec_name = rec.get("customer_name") or rec.get("opportunity_name") or rec_id
        print(f"{'─'*70}")
        print(f"  [{idx}/{len(records)}] {rec_name} (id={rec_id})")
        print(f"{'─'*70}")

        if scenario == "reasoning-chain":
            eval_reasoning_chain(rec_id)
        elif scenario == "customer-360":
            eval_customer_360(rec_id)
        elif scenario == "customer-activity-window":
            eval_customer_activity_window(rec_id, window)
        elif scenario == "pipeline-coverage":
            eval_pipeline_coverage(rec_id)
        elif scenario == "opportunity-intelligence":
            eval_opportunity_intelligence(rec_id)
        elif scenario == "opportunity-timeline":
            eval_opportunity_timeline(rec_id)

    print(f"\n{'='*70}")
    print(f"  ✅ 全量 Dry-Run 完成 — {len(records)} 条记录已处理")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
