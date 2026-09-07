#!/usr/bin/env python3
"""
BO LINK Candidate Generator — 从 CROSS_BO_REF 自动派生候选 LINK
扫描 metadata/design-time 下所有 BO 的 MODEL Fragment，提取 CROSS_BO_REF 字段，
按规则派生候选 LINK。输出 crm-link-candidates.json 供人工审核和增强。
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
META_DIR = PROJECT_DIR / "metadata" / "design-time"
OUTPUT_FILE = TOOLS_DIR / "crm-link-candidates.json"


def load_json(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [WARN] skip {path.name}: {e}", file=sys.stderr)
        return None


def derive_link_code(source_bo: str, ref_bo: str, relation_type: str, ref_nature: str) -> str:
    """根据源 BO、目标 BO、关系类型推导 LINK code。"""
    verbs = {
        ("CROSS_BO_REF", "MASTER_DATA"): "REFERENCES",
        ("CROSS_BO_REF", "BUSINESS_FLOW"): "HAS",
        ("PARENT_REF", ""): "BELONGS_TO",
    }
    verb = verbs.get((relation_type, ref_nature), "LINKS_TO")
    return f"{source_bo.upper().replace('-','_')}_{verb}_{ref_bo.upper().replace('-','_')}"


def derive_cardinality_from_relation_type(rel_type: str) -> str:
    if rel_type == "ONE_TO_ONE":
        return "ONE_TO_ONE"
    return "MANY_TO_ONE"


def infer_link_kind(ref_nature: str) -> str:
    kind_map = {
        "MASTER_DATA": "MASTER_DATA",
        "BUSINESS_FLOW": "BUSINESS_FLOW",
    }
    return kind_map.get(ref_nature, "BUSINESS_FLOW")


def generate_candidates() -> dict:
    candidates = []
    seen = set()

    for bo_dir in sorted(META_DIR.iterdir()):
        if not bo_dir.is_dir() or bo_dir.name.startswith("_"):
            continue
        frag_dir = bo_dir / "fragments"
        if not frag_dir.is_dir():
            continue
        model_file = frag_dir / f"{bo_dir.name}-model.fragment.json"
        if not model_file.exists():
            continue

        data = load_json(model_file)
        if not data:
            continue

        bo_code = data.get("boCode", bo_dir.name)
        content = data.get("content", {})
        entities = content.get("entities", [])
        if not entities:
            continue

        for ent in entities:
            ent_code = ent.get("code", "")
            for attr in ent.get("attributes", []):
                if attr.get("semanticRole") == "CROSS_BO_REF":
                    cr = attr.get("crossBoRef")
                    if not cr:
                        continue
                    ref_bo = cr.get("refBoCode")
                    ref_field = cr.get("refFieldCode", "id")
                    rel_type = cr.get("relationType", "MANY_TO_ONE")
                    ref_nature = cr.get("referenceNature", "MASTER_DATA")
                    link_code = derive_link_code(bo_code, ref_bo, "CROSS_BO_REF", ref_nature)

                    if (bo_code, ref_bo, attr["code"]) in seen:
                        continue
                    seen.add((bo_code, ref_bo, attr["code"]))

                    candidates.append({
                        "code": link_code,
                        "name": f"{bo_code} → {ref_bo}",
                        "source": {
                            "boCode": ref_bo,
                            "entityCode": "",
                            "fieldCode": ref_field
                        },
                        "target": {
                            "boCode": bo_code,
                            "entityCode": ent_code,
                            "fieldCode": attr["code"]
                        },
                        "direction": "TARGET_TO_SOURCE",
                        "cardinality": derive_cardinality_from_relation_type(rel_type),
                        "linkKind": infer_link_kind(ref_nature),
                        "materialization": "FIELD_REF",
                        "queryable": True,
                        "traversable": True,
                        "authzMode": "BOTH_ENDPOINTS",
                        "sourceType": "INFERRED",
                        "derivedFrom": {
                            "modelFile": model_file.name,
                            "entity": ent_code,
                            "field": attr["code"],
                            "refBoCode": ref_bo
                        }
                    })

    candidates.sort(key=lambda c: c["code"])
    return {
        "generatedAt": __import__("datetime").datetime.now().isoformat(),
        "candidateCount": len(candidates),
        "candidates": candidates
    }


def main():
    print("[SRCH] Scanning CROSS_BO_REF fields for LINK candidates ...")
    candidates = generate_candidates()
    print(f"\n[OK] Found {candidates['candidateCount']} LINK candidates from CROSS_BO_REF")

    for c in candidates["candidates"]:
        print(f"  [REF] {c['code']} ({c['source']['boCode']} ← {c['target']['boCode']}) — INFERRED")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print(f"\n[RSLT] Candidates: {OUTPUT_FILE}")
    print(f"[RSLT] Candidates: {OUTPUT_FILE}")
    print("       Review and enhance in _ontology/crm-link.fragment.json before publishing.")


if __name__ == "__main__":
    main()
