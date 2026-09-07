#!/usr/bin/env python3
"""
Ontology Expression Evaluator — 结构化规则 AST 解释器
支持 literal / field / metric / binary / logical / isNull / isNotNull / aggregate / exists / temporalAggregate 节点类型。
DEMO 阶段仅做 dry-run（不实际执行数据库查询），输出执行计划和模拟结果。
"""

import json
from datetime import datetime, timedelta
from typing import Any


class ExprEvalError(Exception):
    pass


def resolve_field_value(path: str, context: dict, data_sources: dict) -> Any:
    """从 data sources 按路径解析字段值。路径格式：entity_code.field_code 或 bare field_code。"""
    parts = path.split(".")
    if len(parts) == 1:
        field_code = parts[0]
        # Search all data sources
        for ds_name, ds_data in data_sources.items():
            if field_code in ds_data:
                return ds_data[field_code]
        raise ExprEvalError(f"Field '{field_code}' not found in any data source (context: {context.get('_root','')})")
    elif len(parts) == 2:
        entity_code, field_code = parts[0], parts[1]
        for ds_name, ds_data in data_sources.items():
            if isinstance(ds_data, dict) and field_code in ds_data:
                return ds_data[field_code]
        raise ExprEvalError(f"Field '{field_code}' not found in data sources")
    raise ExprEvalError(f"Invalid path: {path}")


def evaluate(node: dict, context: dict, data_sources: dict) -> Any:
    """递归评估 AST 节点。"""
    if not isinstance(node, dict):
        return node

    node_type = node.get("type", "")

    if node_type == "literal":
        return node.get("value")

    elif node_type == "field":
        path = node.get("path", "")
        return resolve_field_value(path, context, data_sources) if context.get("_eval", False) else f"{{field:{path}}}"

    elif node_type == "metric":
        code = node.get("code", "")
        return context.get("_metrics", {}).get(code, f"{{metric:{code}}}")

    elif node_type == "binary":
        return _eval_binary(node, context, data_sources)

    elif node_type == "logical":
        return _eval_logical(node, context, data_sources)

    elif node_type == "isNull":
        expr_val = evaluate(node.get("expr", {}), context, data_sources)
        return expr_val is None

    elif node_type == "isNotNull":
        expr_val = evaluate(node.get("expr", {}), context, data_sources)
        return expr_val is not None

    elif node_type == "inSet":
        return _eval_in_set(node, context, data_sources)

    elif node_type == "exists":
        return {
            "_dryRun": "exists",
            "source": node.get("source"),
            "viaLink": node.get("viaLink"),
            "result": "DRY_RUN — real evaluation requires DB access"
        }

    elif node_type == "aggregate":
        return _eval_aggregate(node, context, data_sources)

    elif node_type == "temporalAggregate":
        return _eval_temporal(node, context, data_sources)

    elif node_type == "weightedScore":
        return _eval_weighted_score(node, context, data_sources)

    elif node_type == "scalarOp":
        return _eval_scalar_op(node, context, data_sources)

    elif node_type == "scalarFunc":
        return _eval_scalar_func(node, context, data_sources)

    elif node_type == "caseWhen":
        return _eval_case_when(node, context, data_sources)

    elif node_type == "pipelineAggregate":
        return _eval_pipeline_aggregate(node, context, data_sources)

    else:
        raise ExprEvalError(f"Unknown node type: {node_type}")


def _safe_cmp(a, b, cmp_fn):
    """安全比较：当 a 或 b 为 dict（如 temporalAggregate dry-run 结果）时，
    先尝试提取可比较值；若无法比较则返回 False 而非抛异常。"""
    # 如果是 dry-run dict 结果，提取其 result 字段
    if isinstance(a, dict):
        a = a.get("result", a) if "_dryRun" in a else a
    if isinstance(b, dict):
        b = b.get("result", b) if "_dryRun" in b else b
    # 如果仍有不可比较的类型，返回 False
    try:
        return cmp_fn(a, b)
    except TypeError:
        return False


def _eval_binary(node: dict, context: dict, data_sources: dict) -> Any:
    op = node.get("op", "EQ")
    left = evaluate(node.get("left", {}), context, data_sources) if context.get("_eval", False) else f"{{expr:left}}"
    right = evaluate(node.get("right", {}), context, data_sources) if context.get("_eval", False) else f"{{expr:right}}"

    if not context.get("_eval", False):
        return f"{{binary:{op}}}"

    # DEMO 运行时：实际计算
    ops = {
        "EQ": lambda a, b: a == b,
        "NEQ": lambda a, b: a != b,
        "GT": lambda a, b: _safe_cmp(a, b, lambda x, y: x > y),
        "GTE": lambda a, b: _safe_cmp(a, b, lambda x, y: x >= y),
        "LT": lambda a, b: _safe_cmp(a, b, lambda x, y: x < y),
        "LTE": lambda a, b: _safe_cmp(a, b, lambda x, y: x <= y),
        "IN": lambda a, b: a in (b if isinstance(b, list) else [b]),
        "NOT_IN": lambda a, b: a not in (b if isinstance(b, list) else [b]),
        "CONTAINS": lambda a, b: b in str(a),
        "LIKE": lambda a, b: b in str(a),
        "STARTS_WITH": lambda a, b: str(a).startswith(str(b)),
        "ENDS_WITH": lambda a, b: str(a).endswith(str(b)),
    }
    fn = ops.get(op)
    if fn is None:
        raise ExprEvalError(f"Unknown binary operator: {op}")
    return fn(left, right)


def _eval_logical(node: dict, context: dict, data_sources: dict) -> Any:
    op = node.get("op", "AND")
    items = node.get("items", [])
    if op == "AND":
        return all(evaluate(item, context, data_sources) for item in items)
    elif op == "OR":
        return any(evaluate(item, context, data_sources) for item in items)
    elif op == "NOT":
        return not evaluate(items[0], context, data_sources) if items else True
    raise ExprEvalError(f"Unknown logical operator: {op}")


def _eval_in_set(node: dict, context: dict, data_sources: dict) -> Any:
    left = evaluate(node.get("left", {}), context, data_sources)
    right = evaluate(node.get("right", {}), context, data_sources)
    return left in (right if isinstance(right, list) else [right])


def _eval_aggregate(node: dict, context: dict, data_sources: dict) -> dict:
    return {
        "_dryRun": "aggregate",
        "fn": node.get("fn", "count"),
        "source": node.get("source"),
        "viaLink": node.get("viaLink"),
        "result": "DRY_RUN — requires cross-BO DB query via LINK"
    }


def _get_reference_date():
    """Get the reference date for temporal calculations.
    In demo mode, uses the same fixed date as bo-ontology-demo-eval.py's _DEMO_REFERENCE_DATE.
    In production, uses datetime.now()."""
    # Detect if running in demo context (via context key)
    return datetime.now()


def _eval_temporal(node: dict, context: dict, data_sources: dict) -> dict:
    window = node.get("window", "")
    demo_events = context.get("_demo_events", [])
    fn = node.get("fn", "count")

    if not demo_events:
        return {
            "_dryRun": "temporalAggregate",
            "fn": fn, "window": window,
            "result": "DRY_RUN — no demo events provided"
        }

    # Simple DEMO temporal window calculation
    # P5 修复：使用 context 中传入的 _reference_date 作为基准日（demo 场景应与 _DEMO_REFERENCE_DATE 一致），
    # 避免 datetime.now() 导致活动日期落在窗口边界时 off-by-1 误差。
    now = context.get("_reference_date", datetime.now())
    window_days = _parse_window_days(window)
    cutoff = now - timedelta(days=window_days)

    relevant = [
        e for e in demo_events
        if isinstance(e.get("eventTime"), str)
        and datetime.fromisoformat(e["eventTime"]) >= cutoff
    ]

    if fn == "count":
        return len(relevant)
    elif fn == "sum":
        field = node.get("field", "amount")
        return sum(e.get("snapshot", {}).get(field, 0) for e in relevant if isinstance(e, dict))
    elif fn == "avg":
        field = node.get("field", "amount")
        vals = [e.get("snapshot", {}).get(field, 0) for e in relevant if isinstance(e, dict)]
        return sum(vals) / len(vals) if vals else 0
    elif fn == "max":
        field = node.get("field", "amount")
        vals = [e.get("snapshot", {}).get(field, 0) for e in relevant if isinstance(e, dict)]
        return max(vals) if vals else None
    elif fn == "min":
        field = node.get("field", "amount")
        vals = [e.get("snapshot", {}).get(field, 0) for e in relevant if isinstance(e, dict)]
        return min(vals) if vals else None
    elif fn == "dateDiff":
        # Compute how long ago the most recent event was
        if relevant:
            latest = max(
                (datetime.fromisoformat(e["eventTime"]) for e in relevant
                 if isinstance(e.get("eventTime"), str)),
                default=None
            )
            if latest:
                # P5 修复：date() 级别比较，与 _compute_stage_metrics_per_opp 口径对齐
                return (now.date() - latest.date()).days
        return 999  # very old / no data
    elif fn == "velocityLevel":
        # P7 修复：根据最近事件距今天数与阈值判定 STAGNANT/NORMAL
        # 与 _compute_stage_metrics_per_opp 使用相同逻辑和默认 30 天阈值
        stall_threshold = node.get("stalledThresholdDays", 30)
        if relevant:
            latest = max(
                (datetime.fromisoformat(e["eventTime"]) for e in relevant
                 if isinstance(e.get("eventTime"), str)),
                default=None
            )
            if latest:
                age = (now.date() - latest.date()).days
                return "STAGNANT" if age >= stall_threshold else "NORMAL"
        return "NORMAL"  # 无事件数据，默认正常
    return len(relevant)


def _eval_weighted_score(node: dict, context: dict, data_sources: dict) -> Any:
    """Compute weighted score from itemsForWeight.
    Each scoreRef is looked up in context._metrics (score registry).
    If _eval is True, returns the actual computed float.
    If _eval is False, returns a description string."""
    items = node.get("itemsForWeight", [])
    if not items:
        return 0.0

    if not context.get("_eval", False):
        weights_desc = ", ".join(f"{i['weight']}*{i['scoreRef']}" for i in items)
        return f"{{weightedScore: {weights_desc}}}"

    metrics = context.get("_metrics", {})
    total = 0.0
    for item in items:
        weight = item.get("weight", 0)
        score_ref = item.get("scoreRef", "")
        score_val = metrics.get(score_ref, 0)
        try:
            total += weight * float(score_val)
        except (ValueError, TypeError):
            total += 0  # non-numeric scoreRef contributes 0
    return total


def _eval_scalar_func(node: dict, context: dict, data_sources: dict) -> Any:
    """Evaluate scalar functions: min(val, cap), max(val, floor), round. 
    expr: sub-expression to evaluate, args: positional args (for cap/floor/round)."""
    fn = node.get("fn", "min")
    inner = evaluate(node.get("expr", {}), context, data_sources)

    if not context.get("_eval", False):
        return f"{{scalarFunc:{fn}}}"

    try:
        iv = float(inner) if not isinstance(inner, (int, float)) else inner
    except (TypeError, ValueError):
        raise ExprEvalError(f"Cannot evaluate scalarFunc {fn}: inner={inner}")

    args = node.get("args", [])
    if fn == "min":
        cap = float(args[0]) if args else 100
        return min(iv, cap)
    elif fn == "max":
        floor = float(args[0]) if args else 0
        return max(iv, floor)
    elif fn == "round":
        precision = int(args[0]) if args else 1
        return round(iv, precision)
    raise ExprEvalError(f"Unknown scalarFunc: {fn}")


def _eval_scalar_op(node: dict, context: dict, data_sources: dict) -> Any:
    """Evaluate scalar arithmetic operations (ADD/SUB/MUL/DIV/MOD)."""
    op = node.get("op")
    left = evaluate(node.get("left", {}), context, data_sources)
    right = evaluate(node.get("right", {}), context, data_sources)

    if not context.get("_eval", False):
        return f"{{scalarOp:{op}}}"

    try:
        lv = float(left) if not isinstance(left, (int, float)) else left
        rv = float(right) if not isinstance(right, (int, float)) else right
    except (TypeError, ValueError):
        raise ExprEvalError(f"Cannot evaluate scalarOp {op}: left={left}, right={right}")

    ops = {
        "ADD": lambda a, b: a + b,
        "SUB": lambda a, b: a - b,
        "MUL": lambda a, b: a * b,
        "DIV": lambda a, b: a / b if b != 0 else 0,
        "MOD": lambda a, b: a % b if b != 0 else 0,
    }
    fn = ops.get(op)
    if fn is None:
        raise ExprEvalError(f"Unknown scalar operator: {op}")
    return fn(lv, rv)


def _eval_case_when(node: dict, context: dict, data_sources: dict) -> Any:
    """Evaluate CASE..WHEN branching logic."""
    cases = node.get("cases", [])
    default = node.get("defaultResult")

    for case in cases:
        condition = evaluate(case.get("condition", {}), context, data_sources)
        if condition:
            result_node = case.get("result")
            if isinstance(result_node, dict) and "type" in result_node:
                return evaluate(result_node, context, data_sources)
            return result_node

    if default is not None:
        if isinstance(default, dict) and "type" in default:
            return evaluate(default, context, data_sources)
        return default

    return {"_dryRun": "caseWhen", "result": "DRY_RUN — no branch matched and no default"}


def _eval_pipeline_aggregate(node: dict, context: dict, data_sources: dict) -> Any:
    """pipelineAggregate: 逐商机按阶段概率独立加权后汇总。
    从 context._pipeline_opps 读取商机列表，对每条商机按 stageField 映射
    stageProbabilityMap 获取独立概率，计算 amountField × prob 后汇总。
    P11 修复：非 CNY 币种商机金额需折算为 CNY 后再加权，确保输出统一人民币口径。
    若 context 中无 _pipeline_opps，返回 dry-run 标记供引擎预计算覆盖。"""
    if not context.get("_eval", False):
        return f"{{pipelineAggregate}}"

    opps = context.get("_pipeline_opps")
    if not opps:
        return {"_dryRun": "pipelineAggregate",
                "amountField": node.get("amountField"),
                "result": "DRY_RUN — requires precomputed _pipeline_opps"}

    amount_field = node.get("amountField", "expected_order_amount")
    stage_field = node.get("stageField", "project_stage")
    prob_map = node.get("stageProbabilityMap", {})

    # P11: 加载汇率表用于非 CNY 商机折算
    exchange_rates = context.get("_exchange_rates", [])

    total = 0.0
    for opp in opps:
        amount = opp.get(amount_field, 0) or 0
        # 非 CNY 币种按 ACTIVE 汇率折算
        currency = opp.get("currency", "CNY")
        if currency and currency != "CNY" and exchange_rates:
            rate = next((r for r in exchange_rates
                         if r.get("base_currency") == currency
                         and r.get("target_currency") == "CNY"
                         and r.get("status") == "ACTIVE"), None)
            if rate:
                amount = amount * rate.get("rate", 1)
        raw_stage = (opp.get(stage_field, "") or "").split(",")[0].strip()
        prob = prob_map.get(raw_stage, 0.5)
        total += amount * prob
    return total


def _parse_window_days(window: str) -> int:
    """解析 ISO-8601 Duration 或语义窗口到天数。"""
    semantic = {
        "CURRENT_QUARTER": 90, "LAST_QUARTER": 180,
        "CURRENT_MONTH": 30, "LAST_MONTH": 60,
        "CURRENT_YEAR": 365, "LAST_YEAR": 730,
    }
    if window in semantic:
        return semantic[window]
    # Parse P7D, P30D, P90D, P1Y etc
    if window.startswith("P"):
        num = int(window[1:-1])
        unit = window[-1].upper()
        if unit == "D":
            return num
        elif unit == "W":
            return num * 7
        elif unit == "M":
            return num * 30
        elif unit == "Y":
            return num * 365
    return 90  # default


def evaluate_tree(node: dict, context: dict, data_sources: dict) -> dict:
    """Evaluates a complete expression AST and returns a result summary."""
    try:
        ctx = dict(context)
        ctx["_eval"] = True
        result = evaluate(node, ctx, data_sources)
        return {"success": True, "result": result, "dryRun": isinstance(result, dict) and result.get("_dryRun")}
    except ExprEvalError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected: {e}"}
