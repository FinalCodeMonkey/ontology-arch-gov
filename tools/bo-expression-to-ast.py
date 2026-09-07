#!/usr/bin/env python3
"""
BO Expression-to-AST Converter — 将 RULE.expression 自由文本半自动转换为 exprAst
支持的模式:
  field == 'literal'  → binary(EQ, field, literal)
  field == null       → isNull(field)
  field != null       → isNotNull(field)
  A && B              → logical(AND, [A_ast, B_ast])
  A || B              → logical(OR, [A_ast, B_ast])
不能自动转换的：复杂函数调用（substring/concat）、跨 BO 聚合、注释//等
输出: crm-expr-ast-report.json（转换报告）

用法:
  python bo-expression-to-ast.py                  # 全扫描
  python bo-expression-to-ast.py --bo opportunities  # 只转换指定 BO
"""

import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
META_DIR = TOOLS_DIR.parent / "metadata" / "design-time"
OUTPUT_FILE = TOOLS_DIR / "crm-expr-ast-report.json"


def load_json(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [WARN] skip {path.name}: {e}", file=sys.stderr)
        return None


# ── 词法/语法解析 ────────────────────────────────────────────────

def parse_simple_expression(expr_str: str, bo_code: str) -> dict:
    """尝试将简单表达式转换为 AST。返回 {'ast': {...}} 或 {'reason': '...'}。"""
    expr = expr_str.strip()

    # 跳过注释行
    if expr.startswith("//"):
        return {"reason": "contains comments", "original": expr}

    # 跳过含复杂函数的表达式（非自动转换范围）
    # 注意：count(...) 和 sum(...) 是聚合函数，由 _try_parse_aggregate 处理，不在此跳过
    if re.search(r'\.(substring|length|concat|toUpperCase|toLowerCase|trim|split|isEmpty)\(',
                 expr, re.IGNORECASE):
        return {"reason": "contains unsupported function calls", "original": expr}

    # 跳过 abs() 函数调用
    if re.search(r'\babs\s*\(', expr, re.IGNORECASE):
        return {"reason": "contains unsupported function calls (abs)", "original": expr}

    # 跳过含 ref. / refCount 跨 BO 引用的表达式（需人工编写）
    if re.search(r'\bref\.', expr) or re.search(r'\brefCount\s*\(', expr):
        return {"reason": "contains cross-BO reference (ref./refCount)", "original": expr}

    # 跳过含字符串拼接的表达式
    if "+" in expr and ("'" in expr or '"' in expr):
        return {"reason": "contains string concatenation", "original": expr}

    # try: parse as logical AND / OR (&& / || / and / or 关键字)
    logical = _try_parse_logical(expr)
    if logical:
        return {"ast": logical}

    # try: parse as aggregate (count(...) <= N)
    aggregate = _try_parse_aggregate(expr)
    if aggregate:
        return {"ast": aggregate}

    # try: parse as inSet (field in ('A', 'B', 'C'))
    inset = _try_parse_inset(expr)
    if inset:
        return {"ast": inset}

    # try: parse as single comparison
    comparison = _try_parse_comparison(expr)
    if comparison:
        return {"ast": comparison}

    return {"reason": "unsupported pattern", "original": expr}


def _try_parse_logical(expr: str) -> dict | None:
    """解析 A && B、A || B、A and B、A or B 模式。支持括号分组。"""
    expr = expr.strip()

    # 去除外层括号
    while expr.startswith("(") and expr.endswith(")"):
        # 检查括号是否匹配外层
        depth = 0
        matched = True
        for i, c in enumerate(expr[:-1]):
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            if depth == 0 and i < len(expr) - 1:
                matched = False
                break
        if matched:
            expr = expr[1:-1].strip()
        else:
            break

    # 按顶层 && / || / and / or 分割（不进入括号）
    for op, tokens in [("AND", ["&&", " and "]), ("OR", ["||", " or "])]:
        for token in tokens:
            parts = _split_top_level(expr, token)
            if len(parts) >= 2:
                items = []
                all_ok = True
                for part in parts:
                    part = part.strip()
                    # 每个子部分可能是 logical / comparison / aggregate / inset
                    sub = (_try_parse_logical(part) or
                           _try_parse_aggregate(part) or
                           _try_parse_inset(part) or
                           _try_parse_comparison(part))
                    if sub:
                        items.append(sub)
                    else:
                        all_ok = False
                        break
                if all_ok:
                    return {"type": "logical", "op": op, "items": items}
    return None


def _split_top_level(expr: str, separator: str) -> list:
    """按分隔符分割表达式，不进入括号内部。"""
    parts = []
    depth = 0
    current = ""
    i = 0
    sep_len = len(separator)
    while i < len(expr):
        c = expr[i]
        if c == "(":
            depth += 1
            current += c
            i += 1
        elif c == ")":
            depth -= 1
            current += c
            i += 1
        elif depth == 0 and expr[i:i+sep_len] == separator:
            parts.append(current)
            current = ""
            i += sep_len
        else:
            current += c
            i += 1
    if current.strip():
        parts.append(current)
    return parts


def _try_parse_inset(expr: str) -> dict | None:
    """解析 field in ('A', 'B', 'C') 模式。"""
    expr = expr.strip()
    m = re.match(r"^(\w+)\s+in\s*\(([^)]+)\)$", expr, re.IGNORECASE)
    if m:
        field_path = m.group(1)
        values_str = m.group(2)
        # 提取引号内的值
        values = re.findall(r"'([^']*)'", values_str)
        if not values:
            values = re.findall(r'"([^"]*)"', values_str)
        if values:
            return {
                "type": "inSet",
                "field": {"type": "field", "path": field_path},
                "values": [{"type": "literal", "value": v} for v in values]
            }
    return None


def _try_parse_aggregate(expr: str) -> dict | None:
    """解析 count(...) <= N 模式的唯一性约束。
    支持：
    - count(entity where field == this.field) <= N
    - count(parent.children[field == this.field]) <= N
    """
    expr = expr.strip()

    # count(...) <= N 或 count(...) > N 等
    m = re.match(r'^count\s*\((.+?)\)\s*(<=|>=|<|>|==|!=)\s*(\d+(?:\.\d+)?)$', expr, re.IGNORECASE)
    if m:
        inner = m.group(1).strip()
        op_str = m.group(2)
        threshold = int(m.group(3)) if "." not in m.group(3) else float(m.group(3))

        op_map = {"<=": "LTE", ">=": "GTE", "<": "LT", ">": "GT", "==": "EQ", "!=": "NEQ"}

        # 解析 count 内部：entity where condition 或 parent.children[condition]
        agg_node = _parse_count_inner(inner)
        if agg_node:
            return {
                "type": "binary",
                "op": op_map[op_str],
                "left": agg_node,
                "right": {"type": "literal", "value": threshold}
            }
    return None


def _parse_count_inner(inner: str) -> dict | None:
    """解析 count() 内部表达式，生成 aggregate 节点。"""
    inner = inner.strip()

    # 模式1: entity where field == this.field
    m = re.match(r'^(\w[\w-]*)\s+where\s+(.+)$', inner, re.IGNORECASE)
    if m:
        entity = m.group(1)
        condition = m.group(2).strip()
        where_ast = _try_parse_comparison(condition.replace("this.", ""))
        if where_ast:
            return {
                "type": "aggregate",
                "fn": "count",
                "source": entity,
                "where": where_ast
            }

    # 模式2: parent.children[field == this.field]
    m = re.match(r'^parent\.(\w[\w-]*)\[(.+)\]$', inner)
    if m:
        child_entity = m.group(1)
        condition = m.group(2).strip().replace("this.", "")
        where_ast = _try_parse_comparison(condition)
        if where_ast:
            return {
                "type": "aggregate",
                "fn": "count",
                "source": child_entity,
                "where": where_ast
            }

    # 模式3: 简单 entity 名称（count all）
    if re.match(r'^\w[\w-]*$', inner):
        return {
            "type": "aggregate",
            "fn": "count",
            "source": inner
        }

    return None


def _try_parse_comparison(expr: str) -> dict | None:
    """解析各种比较模式：
    - field == null / field != null
    - field == 'literal' / field != 'literal'
    - field == number / field != number
    - field >= field / field <= field / field > field / field < field
    - field >= number / field <= number / field > number / field < number
    - field == field (字段间比较)
    """
    expr = expr.strip()

    # field == null
    m = re.match(r'^(\w+)\s*==\s*null$', expr)
    if m:
        return {"type": "isNull", "expr": {"type": "field", "path": m.group(1)}}

    # field != null
    m = re.match(r'^(\w+)\s*!=\s*null$', expr)
    if m:
        return {"type": "isNotNull", "expr": {"type": "field", "path": m.group(1)}}

    # field == 'literal' (字符串)
    m = re.match(r"^(\w+)\s*==\s*'([^']*)'$", expr)
    if m:
        return {"type": "binary", "op": "EQ",
                "left": {"type": "field", "path": m.group(1)},
                "right": {"type": "literal", "value": m.group(2)}}

    # field == "literal" (字符串)
    m = re.match(r'^(\w+)\s*==\s*"([^"]*)"$', expr)
    if m:
        return {"type": "binary", "op": "EQ",
                "left": {"type": "field", "path": m.group(1)},
                "right": {"type": "literal", "value": m.group(2)}}

    # field != 'literal' (字符串)
    m = re.match(r"^(\w+)\s*!=\s*'([^']*)'$", expr)
    if m:
        return {"type": "binary", "op": "NEQ",
                "left": {"type": "field", "path": m.group(1)},
                "right": {"type": "literal", "value": m.group(2)}}

    # field != "literal" (字符串)
    m = re.match(r'^(\w+)\s*!=\s*"([^"]*)"$', expr)
    if m:
        return {"type": "binary", "op": "NEQ",
                "left": {"type": "field", "path": m.group(1)},
                "right": {"type": "literal", "value": m.group(2)}}

    # field == number (数字 literal)
    m = re.match(r'^(\w+)\s*==\s*(-?\d+(?:\.\d+)?)$', expr)
    if m:
        val = float(m.group(2)) if "." in m.group(2) else int(m.group(2))
        return {"type": "binary", "op": "EQ",
                "left": {"type": "field", "path": m.group(1)},
                "right": {"type": "literal", "value": val}}

    # field != number (数字 literal)
    m = re.match(r'^(\w+)\s*!=\s*(-?\d+(?:\.\d+)?)$', expr)
    if m:
        val = float(m.group(2)) if "." in m.group(2) else int(m.group(2))
        return {"type": "binary", "op": "NEQ",
                "left": {"type": "field", "path": m.group(1)},
                "right": {"type": "literal", "value": val}}

    # field >= / <= / > / < field (字段间比较)
    for op, ast_op in [(">=", "GTE"), ("<=", "LTE"), (">", "GT"), ("<", "LT")]:
        m = re.match(r'^(\w+)\s*' + re.escape(op) + r'\s*(\w+)$', expr)
        if m and m.group(2) != "null":
            right = m.group(2)
            # 判断右侧是数字还是字段
            if re.match(r'^-?\d+(?:\.\d+)?$', right):
                val = float(right) if "." in right else int(right)
                return {"type": "binary", "op": ast_op,
                        "left": {"type": "field", "path": m.group(1)},
                        "right": {"type": "literal", "value": val}}
            else:
                return {"type": "binary", "op": ast_op,
                        "left": {"type": "field", "path": m.group(1)},
                        "right": {"type": "field", "path": right}}

    # field == field (字段间相等比较)
    m = re.match(r'^(\w+)\s*==\s*(\w+)$', expr)
    if m and m.group(2) != "null":
        right = m.group(2)
        if not re.match(r'^-?\d+(?:\.\d+)?$', right):
            return {"type": "binary", "op": "EQ",
                    "left": {"type": "field", "path": m.group(1)},
                    "right": {"type": "field", "path": right}}

    # field != field (字段间不等比较)
    m = re.match(r'^(\w+)\s*!=\s*(\w+)$', expr)
    if m and m.group(2) != "null":
        right = m.group(2)
        if not re.match(r'^-?\d+(?:\.\d+)?$', right):
            return {"type": "binary", "op": "NEQ",
                    "left": {"type": "field", "path": m.group(1)},
                    "right": {"type": "field", "path": right}}

    return None


def convert_all(bo_filter: str = None, write_back: bool = False) -> dict:
    report = {
        "generatedAt": __import__("datetime").datetime.now().isoformat(),
        "generatedBy": "bo-expression-to-ast.py",
        "totalExpressions": 0,
        "autoConverted": 0,
        "needsManual": 0,
        "writtenBack": 0,
        "boRules": {}
    }

    for bo_dir in sorted(META_DIR.iterdir()):
        if not bo_dir.is_dir() or bo_dir.name.startswith("_"):
            continue
        if bo_filter and bo_dir.name != bo_filter:
            continue

        rule_file = bo_dir / "fragments" / f"{bo_dir.name}-rule.fragment.json"
        if not rule_file.exists():
            continue

        data = load_json(rule_file)
        if not data:
            continue

        bo_code = data.get("boCode", bo_dir.name)
        rules = data.get("content", {}).get("rules", [])
        if not rules:
            continue

        bo_results = []
        modified = False

        for rule in rules:
            rcode = rule.get("code", "?")
            rname = rule.get("name", "")
            expr = rule.get("expression", "").strip()
            if not expr:
                continue

            report["totalExpressions"] += 1
            result = parse_simple_expression(expr, bo_code)

            if "ast" in result:
                report["autoConverted"] += 1
                bo_results.append({
                    "code": rcode,
                    "name": rname,
                    "ruleType": rule.get("ruleType", ""),
                    "originalExpression": expr,
                    "autoConverted": True,
                    "exprAst": result["ast"]
                })
                # 回写 exprAst 到 RULE Fragment
                if write_back:
                    existing_ast = rule.get("exprAst")
                    if existing_ast != result["ast"]:
                        rule["exprAst"] = result["ast"]
                        modified = True
                        report["writtenBack"] += 1
            else:
                report["needsManual"] += 1
                bo_results.append({
                    "code": rcode,
                    "name": rname,
                    "ruleType": rule.get("ruleType", ""),
                    "originalExpression": expr,
                    "autoConverted": False,
                    "reason": result.get("reason", "unknown"),
                    "suggestion": "需要人工编写 exprAst"
                })

        if bo_results:
            report["boRules"][bo_code] = bo_results

        # 如果有修改，写回文件
        if write_back and modified:
            with open(rule_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  [WRITE] {bo_code}: exprAst written back to {rule_file.name}")

    return report


def main():
    bo_filter = None
    write_back = False
    args = sys.argv[1:]
    if "--bo" in args:
        idx = args.index("--bo")
        if idx + 1 < len(args):
            bo_filter = args[idx + 1]
    if "--write-back" in args:
        write_back = True

    mode_label = "WRITE-BACK" if write_back else "REPORT-ONLY"
    print(f"[SRCH] Scanning RULE expressions for auto-conversion ({mode_label}) ...\n")
    report = convert_all(bo_filter, write_back)

    auto = report["autoConverted"]
    manual = report["needsManual"]
    total = report["totalExpressions"]
    written = report.get("writtenBack", 0)
    print(f"  [DATA] Total: {total}  |  [OK] Auto: {auto}  |  🖊️ Manual: {manual}  |  [WRITE] Written back: {written}\n")

    for bo_code, rules in report["boRules"].items():
        for r in rules:
            status = "[OK]" if r["autoConverted"] else "🖊️"
            print(f"  {status} {bo_code} {r['code']}: {r.get('reason', '') or 'ok'}")
            if r["autoConverted"]:
                ast_str = json.dumps(r["exprAst"], ensure_ascii=False)
                if len(ast_str) > 120:
                    ast_str = ast_str[:117] + "..."
                print(f"       → {ast_str}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[RSLT] Report written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
