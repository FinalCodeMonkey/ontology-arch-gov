#!/usr/bin/env python3
"""
BO Ontology Publish Generator — 应用级本体发布态合成器
从 metadata/design-time/_ontology 和 BO Fragment 合成应用级：
  1. ontology-snapshot.v1.json     — 跨 BO 本体总快照
  2. ontology-link-index.v1.json   — LINK 边索引（显式 LINK + 从 CROSS_BO_REF 自动派生）
  3. ontology-derivation-index.v1.json — 派生对象索引
  4. ontology-temporal-index.v1.json   — 时态时间线索引
  5. ontology-action-chain-index.v1.json — 动作链索引

用法:  python bo-ontology-publish-gen.py [--app crm] [--type links|derivations|temporal|action-chains|all]
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
META_DIR = PROJECT_DIR / "metadata" / "design-time"
RELEASE_DIR = PROJECT_DIR / "metadata" / "release-time" / "_ontology"


def load_json(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [WARN] skip {path.name}: {e}", file=sys.stderr)
        return None


def save_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {path.name}")


def build_base_meta(app_code: str) -> dict:
    return {
        "tenantId": "cbg",
        "appCode": app_code,
        "releaseVersion": "1.0.0",
        "releasedAt": datetime.now(timezone.utc).isoformat(),
        "generatedBy": "bo-ontology-publish-gen.py"
    }


# ═══════════════════════════════════════════════════════════════════
#  LINK Index: 显式 LINK 优先，自动派生 CROSS_BO_REF 补充
# ═══════════════════════════════════════════════════════════════════

def collect_explicit_links(ontology_dir: Path) -> list[dict]:
    frag_file = ontology_dir / "fragments" / "crm-link.fragment.json"
    if not frag_file.exists():
        return []
    data = load_json(frag_file)
    if not data:
        return []
    links = data.get("content", {}).get("links", [])
    result = []
    for link in links:
        # 完整透传设计态 link 的所有字段，同时补充扁平化字段供发布态消费
        out = dict(link)  # 浅拷贝全部字段（name, inverseName, traversable, queryable 等）
        # 补充扁平化字段（从嵌套 source/target 提取）
        src = link.get("source", {})
        tgt = link.get("target", {})
        out["sourceBoCode"] = src.get("boCode", "")
        out["sourceEntityCode"] = src.get("entityCode", "")
        out["sourceFieldCode"] = src.get("fieldCode", "")
        out["targetBoCode"] = tgt.get("boCode", "")
        out["targetEntityCode"] = tgt.get("entityCode", "")
        out["targetFieldCode"] = tgt.get("fieldCode", "")
        out["source"] = "EXPLICIT"
        result.append(out)
    return result


def collect_inferred_links(meta_dir: Path) -> list[dict]:
    """从 BO MODEL 的 CROSS_BO_REF 推导候选 LINK（与 bo-link-candidates-gen.py 协同）。"""
    inferred = []
    seen = set()

    for bo_dir in sorted(meta_dir.iterdir()):
        if not bo_dir.is_dir() or bo_dir.name.startswith("_"):
            continue
        frag_dir = bo_dir / "fragments"
        model_file = frag_dir / f"{bo_dir.name}-model.fragment.json"
        if not model_file.exists():
            continue
        data = load_json(model_file)
        if not data:
            continue
        bo_code = data.get("boCode", bo_dir.name)
        entities = data.get("content", {}).get("entities", [])
        for ent in entities:
            ent_code = ent.get("code", "")
            for attr in ent.get("attributes", []):
                if attr.get("semanticRole") != "CROSS_BO_REF":
                    continue
                cr = attr.get("crossBoRef")
                if not cr:
                    continue
                ref_bo = cr.get("refBoCode")
                ref_field = cr.get("refFieldCode", "id")
                rel_type = cr.get("relationType", "MANY_TO_ONE")
                ref_nature = cr.get("referenceNature", "MASTER_DATA")
                link_code = _derive_inferred_code(bo_code, ref_bo, ent_code, attr["code"])
                if link_code in seen:
                    continue
                seen.add(link_code)

                inferred.append({
                    "code": link_code,
                    "sourceBoCode": ref_bo,
                    "sourceEntityCode": "",
                    "sourceFieldCode": ref_field,
                    "targetBoCode": bo_code,
                    "targetEntityCode": ent_code,
                    "targetFieldCode": attr["code"],
                    "cardinality": "MANY_TO_ONE" if rel_type == "MANY_TO_ONE" else rel_type,
                    "direction": "TARGET_TO_SOURCE",
                    "materialization": "FIELD_REF",
                    "authzMode": "BOTH_ENDPOINTS",
                    "linkKind": "MASTER_DATA" if ref_nature == "MASTER_DATA" else "BUSINESS_FLOW",
                    "source": "INFERRED",
                    "description": f"自动派生自 {bo_code}.{ent_code}.{attr['code']} CROSS_BO_REF → {ref_bo}.{ref_field}"
                })
    return inferred


def _derive_inferred_code(source_bo: str, ref_bo: str, entity: str, field: str) -> str:
    verb = "HAS" if entity != field else "REFERENCES"
    return f"INFERRED_{source_bo.upper().replace('-','_')}_{verb}_{ref_bo.upper().replace('-','_')}"


def generate_link_index(app_code: str, meta_dir: Path, ontology_dir: Path) -> dict:
    meta = build_base_meta(app_code)
    explicit = collect_explicit_links(ontology_dir)
    inferred = collect_inferred_links(meta_dir)

    explicit_codes = {l["code"] for l in explicit}
    merged = list(explicit)
    for inf in inferred:
        if inf["code"] not in explicit_codes:
            merged.append(inf)

    meta["links"] = merged
    meta["linkCount"] = len(merged)
    meta["explicitCount"] = len(explicit)
    meta["inferredCount"] = len(merged) - len(explicit)
    return meta


# ═══════════════════════════════════════════════════════════════════
#  DERIVATION Index: 从 _ontology/crm-derivation.fragment.json
# ═══════════════════════════════════════════════════════════════════

def generate_derivation_index(app_code: str, ontology_dir: Path) -> dict:
    meta = build_base_meta(app_code)

    # 加载 derivation fragment 和 entity-scoring fragment（均为 DERIVATION 类型）
    frag_files = [
        ontology_dir / "fragments" / "crm-derivation.fragment.json",
        ontology_dir / "fragments" / "crm-entity-scoring.fragment.json",
    ]

    derived = []
    for frag_file in frag_files:
        if not frag_file.exists():
            continue
        data = load_json(frag_file)
        if not data:
            continue
        for obj in data.get("content", {}).get("derivedObjects", []):
            # 完整透传设计态 derivedObject 的所有字段
            out = dict(obj)  # 浅拷贝全部字段（code, name, objectKind, root, dependencies, materialization 等）
            # 对 fields 做完整透传 + 补充 hasExpression 标记
            out_fields = []
            for f in obj.get("fields", []):
                f_out = dict(f)  # 完整透传（expression, cacheable, requiredForScoring 等）
                f_out["hasExpression"] = bool(f.get("expression"))
                out_fields.append(f_out)
            out["fields"] = out_fields
            out["apiExposed"] = obj.get("apiExposure", {}).get("enabled", False)
            derived.append(out)

    meta["derivedObjects"] = derived
    meta["derivedCount"] = len(derived)
    return meta


# ═══════════════════════════════════════════════════════════════════
#  TEMPORAL Index: 从 _ontology/crm-temporal.fragment.json
# ═══════════════════════════════════════════════════════════════════

def generate_temporal_index(app_code: str, ontology_dir: Path) -> dict:
    meta = build_base_meta(app_code)
    frag_file = ontology_dir / "fragments" / "crm-temporal.fragment.json"
    if not frag_file.exists():
        meta["timelines"] = []
        return meta

    data = load_json(frag_file)
    if not data:
        meta["timelines"] = []
        return meta

    timelines = []
    for tl in data.get("content", {}).get("timelines", []):
        # 完整透传设计态 timeline 的所有字段
        out = dict(tl)  # 浅拷贝全部字段（code, name, boCode, entityCode, stateField, eventSources 等）
        # 对 metrics 做完整透传
        out["metrics"] = [dict(m) for m in tl.get("metrics", [])]  # 完整透传（expression, window, sourceLink, unit 等）
        timelines.append(out)

    meta["timelines"] = timelines
    meta["timelineCount"] = len(timelines)
    return meta


# ═══════════════════════════════════════════════════════════════════
#  ACTION_CHAIN Index: 从 _ontology/crm-action-chain.fragment.json
# ═══════════════════════════════════════════════════════════════════

def generate_action_chain_index(app_code: str, ontology_dir: Path) -> dict:
    meta = build_base_meta(app_code)
    frag_file = ontology_dir / "fragments" / "crm-action-chain.fragment.json"
    if not frag_file.exists():
        meta["chains"] = []
        return meta

    data = load_json(frag_file)
    if not data:
        meta["chains"] = []
        return meta

    chains = []
    for ch in data.get("content", {}).get("chains", []):
        # 完整透传设计态 chain 的所有字段
        out = dict(ch)  # 浅拷贝全部字段（code, name, trigger, condition, description, idempotencyKey, maxRetries 等）
        out["triggerType"] = ch.get("trigger", {}).get("type")
        out["executionMode"] = ch.get("executionMode", "ASYNC")
        out["stepCount"] = len(ch.get("steps", []))
        # 对 steps 做完整透传
        out["steps"] = [dict(s) for s in ch.get("steps", [])]  # 完整透传（code, name, stepType, failurePolicy, dependsOn, target, inputMapping 等）
        chains.append(out)

    meta["chains"] = chains
    meta["chainCount"] = len(chains)
    return meta


# ═══════════════════════════════════════════════════════════════════
#  Ontology Snapshot: 汇总
# ═══════════════════════════════════════════════════════════════════

def generate_all(app_code: str):
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    meta_dir = META_DIR
    ontology_dir = meta_dir / "_ontology"

    print(f"\n[GEN] Generating Ontology publish artifacts for appCode='{app_code}' ...\n")

    link_index = generate_link_index(app_code, meta_dir, ontology_dir)
    save_json(link_index, RELEASE_DIR / f"{app_code}.ontology-link-index.v1.json")

    derivation_index = generate_derivation_index(app_code, ontology_dir)
    save_json(derivation_index, RELEASE_DIR / f"{app_code}.ontology-derivation-index.v1.json")

    temporal_index = generate_temporal_index(app_code, ontology_dir)
    save_json(temporal_index, RELEASE_DIR / f"{app_code}.ontology-temporal-index.v1.json")

    action_chain_index = generate_action_chain_index(app_code, ontology_dir)
    save_json(action_chain_index, RELEASE_DIR / f"{app_code}.ontology-action-chain-index.v1.json")

    snapshot = build_base_meta(app_code)
    snapshot["links"] = link_index.get("links", [])
    snapshot["derivedObjects"] = derivation_index.get("derivedObjects", [])
    snapshot["timelines"] = temporal_index.get("timelines", [])
    snapshot["chains"] = action_chain_index.get("chains", [])
    save_json(snapshot, RELEASE_DIR / f"{app_code}.ontology-snapshot.v1.json")

    print(f"\n[OK] All Ontology publish artifacts written to: {RELEASE_DIR}")


def main():
    app_code = "crm"
    gen_type = "all"

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--app" and i + 1 < len(args):
            app_code = args[i + 1]
            i += 2
        elif args[i] == "--type" and i + 1 < len(args):
            gen_type = args[i + 1]
            i += 2
        else:
            i += 1

    if gen_type == "all":
        generate_all(app_code)
    elif gen_type in ("links", "link"):
        idx = generate_link_index(app_code, META_DIR, META_DIR / "_ontology")
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        save_json(idx, RELEASE_DIR / f"{app_code}.ontology-link-index.v1.json")
    elif gen_type in ("derivations", "derivation"):
        idx = generate_derivation_index(app_code, META_DIR / "_ontology")
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        save_json(idx, RELEASE_DIR / f"{app_code}.ontology-derivation-index.v1.json")
    elif gen_type in ("temporal",):
        idx = generate_temporal_index(app_code, META_DIR / "_ontology")
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        save_json(idx, RELEASE_DIR / f"{app_code}.ontology-temporal-index.v1.json")
    elif gen_type in ("action-chains", "action-chain"):
        idx = generate_action_chain_index(app_code, META_DIR / "_ontology")
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        save_json(idx, RELEASE_DIR / f"{app_code}.ontology-action-chain-index.v1.json")
    else:
        print(f"Unknown type: {gen_type}. Use: links, derivations, temporal, action-chains, all")
        sys.exit(1)


if __name__ == "__main__":
    main()
