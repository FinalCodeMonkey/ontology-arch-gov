/* ═══════════════════════════════════════════════════════════════════
   ontology-graph-detail.js — Tab 0-4 detail panel rendering, entity tree
   Dependencies: shared-dicts.js, ontology-graph-engine.js
   ═══════════════════════════════════════════════════════════════════ */

// 取消选中 BO，回到全局推理视图
function deselectBo() {
  selectedBoCode = null;
  if (network) network.unselectAll();
  // 隐藏 BO Tab 按钮
  var tabBoBtn = document.getElementById('top-tab-bo');
  if (tabBoBtn) { tabBoBtn.style.display = 'none'; tabBoBtn.textContent = ''; }
  // 切换到推理 Tab，渲染全局视图
  switchTopTab('reasoning');
  var pane5 = document.getElementById('tab-pane-5');
  if (pane5 && typeof buildTab5GlobalReasoning === 'function') {
    pane5.innerHTML = buildTab5GlobalReasoning();
  }
}

function showBoDetail(boCode, bo) {
  var boMap = {};
  graphData.bos.forEach(function(b) { boMap[b.boCode] = b; });

  // 显示「业务对象详情」Tab 按钮，Tab 名为 BO 名称
  var tabBoBtn = document.getElementById('top-tab-bo');
  if (tabBoBtn) { tabBoBtn.style.display = ''; tabBoBtn.textContent = bo.boName; }

  document.getElementById('panel-bo-name').textContent = bo.boName;
  document.getElementById('panel-bo-meta').innerHTML = '<span style="color:#a1a1aa">' + bo.boCode + '</span>  <span style="color:#60a5fa">' + (OBJTYPE_CN[bo.objectType]||bo.objectType) + '</span>  <span style="color:var(--text-secondary)">' + bo.entities.length + ' 实体</span>';
  selectedBoCode = boCode;
  var editLink = document.getElementById('link-edit-meta');
  if (editLink) { editLink.style.opacity = '1'; editLink.style.pointerEvents = 'auto'; }

  var chipsDiv = document.getElementById('panel-frag-chips');
  if (bo.fragments) {
    chipsDiv.innerHTML = Object.entries(bo.fragments).map(function(kv) {
      var mt = kv[0], f = kv[1];
      return '<span class="frag-chip" style="background:' + FRAG_COLORS[mt] + '22;color:' + FRAG_COLORS[mt] + ';border-color:' + FRAG_COLORS[mt] + '33">' + (FRAG_CN[mt]||mt) + '</span>';
    }).join('');
  } else { chipsDiv.innerHTML = ''; }

  // ── Tab 0: 拓扑概览 ──────────────────────────────────────
  var t0 = '';
  if (bo.description) {
    t0 += '<div class="section"><div class="section-title">📋 概述</div>' +
      '<div class="info-block">' + bo.description + '</div></div>';
  }

  var totalAttrs = bo.entities.reduce(function(s,e) { return s + e.attributes.length; }, 0);
  t0 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">📊 统计摘要</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + bo.entities.length + '实体 ' + totalAttrs + '属性</span></div><div class="entity-attrs open">' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;padding:8px 12px">' +
    '<div>实体: <b>' + bo.entities.length + '</b></div><div>属性: <b>' + totalAttrs + '</b></div>' +
    '<div>操作: <b>' + bo.operations.length + '</b></div><div>规则: <b>' + bo.rules.length + '</b></div>' +
    '<div>校验: <b>' + (bo.validations?bo.validations.length:0) + '</b></div><div>安全策略: <b>' + (bo.fieldSecurity?bo.fieldSecurity.length:0) + '</b></div>' +
    '</div></div>';

  var outRefs = (bo.crossBoRefs || []).filter(function(r) { return r.refBoCode !== boCode; });
  var selfRefs = (bo.crossBoRefs || []).filter(function(r) { return r.refBoCode === boCode; });
  var inRefs = (bo.incomingRefs || []).filter(function(r) { return r.fromBoCode !== boCode; });
  var hasTopo = outRefs.length > 0 || inRefs.length > 0 || selfRefs.length > 0;

  t0 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🔗 关联拓扑</b></span><span style="font-size:10px;color:var(--text-tertiary)">出' + outRefs.length + ' 入' + inRefs.length + ' 自' + selfRefs.length + '</span></div><div class="entity-attrs">';

  if (outRefs.length > 0) {
    t0 += '<div style="padding:8px 12px;font-size:11px;color:var(--text-secondary)">出向引用：</div>';
    var grouped = {};
    outRefs.forEach(function(ref) { if (!grouped[ref.refBoCode]) grouped[ref.refBoCode] = []; grouped[ref.refBoCode].push(ref); });
    for (var refBoCode in grouped) {
      var refs = grouped[refBoCode];
      var targetBo = graphData.bos.find(function(b) { return b.boCode === refBoCode; });
      var boName2 = targetBo ? targetBo.boName : refBoCode;
      t0 += '<span class="rel-badge nav-ref" data-bo="' + refBoCode + '" style="display:block;margin:0 12px 2px">→ ' + boName2 + '</span>';
      refs.forEach(function(ref) {
        t0 += '<span style="display:block;font-size:11px;color:var(--text-secondary);padding-left:24px;margin-bottom:3px">' + ref.fromFieldName + ' ⇨ ' + ref.refFieldCode + '</span>';
      });
    }
  }
  if (inRefs.length > 0) {
    t0 += '<div style="padding:8px 12px;font-size:11px;color:var(--text-secondary)">入向引用：</div>';
    var grouped2 = {};
    inRefs.forEach(function(ref) { if (!grouped2[ref.fromBoCode]) grouped2[ref.fromBoCode] = []; grouped2[ref.fromBoCode].push(ref); });
    for (var fromBoCode in grouped2) {
      var refs2 = grouped2[fromBoCode];
      var boName3 = refs2[0].fromBoName || fromBoCode;
      t0 += '<span class="rel-badge rel-incoming nav-ref" data-bo="' + fromBoCode + '" style="display:block;margin:0 12px 2px">← ' + boName3 + '</span>';
      refs2.forEach(function(ref) {
        var fromBo = graphData.bos.find(function(b) { return b.boCode === fromBoCode; });
        var ent = fromBo ? fromBo.entities.find(function(e) { return e.code === ref.fromEntityCode; }) : null;
        var entName = ent ? ent.name : ref.fromEntityCode;
        var attr = ent ? ent.attributes.find(function(a) { return a.code === ref.fromFieldCode; }) : null;
        var fieldName = attr ? attr.name : ref.fromFieldCode;
        t0 += '<span style="display:block;font-size:11px;color:var(--text-secondary);padding-left:24px;margin-bottom:3px">' + entName + ' · ' + fieldName + '</span>';
      });
    }
  }
  if (selfRefs.length > 0) {
    t0 += '<div style="padding:8px 12px;font-size:11px;color:#fbbf24">自引用：</div>';
    selfRefs.forEach(function(ref) {
      t0 += '<span style="display:block;font-size:11px;color:var(--text-secondary);padding-left:24px;margin-bottom:3px">' + ref.fromFieldName + ' ⇨ ' + ref.refFieldCode + '</span>';
    });
  }
  if (!hasTopo) {
    t0 += '<div style="padding:10px 12px;font-size:11px;color:var(--text-tertiary)">独立节点，无跨对象关联。</div>';
  }
  t0 += '</div></div>';
  document.getElementById('tab-pane-0').innerHTML = t0;

  // ── Tab 1: 实体模型 ──────────────────────────────────────
  var t1 = '';
  bo.entities.forEach(function(ent, ei) {
    var roleBadge = ent.aggregateRole === 'ROOT' ? 'root' : ent.aggregateRole === 'SUB_ENTITY' ? 'sub' : 'vo';
    var roleLabel = { ROOT:'聚合根', SUB_ENTITY:'子实体', VALUE_OBJECT:'值对象', DERIVED_VIEW:'派生视图' }[ent.aggregateRole] || ent.aggregateRole;
    var natureBadge = ent.entityNature === 'ASSOCIATION' ? '<span class="entity-badge assoc">🔗 关联表</span>' : '';
    t1 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon ' + (ei===0?'open':'') + '">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">' + ent.name + '</b> <small style="color:var(--text-tertiary)">' + ent.code + '</small></span>' + natureBadge + '<span class="entity-badge ' + roleBadge + '">' + roleLabel + '</span>' + (ent.tableName ? '<span style="font-size:10px;color:var(--text-tertiary);font-family:monospace">📁 ' + ent.tableName + '</span>' : '') + '</div><div class="entity-attrs ' + (ei===0?'open':'') + '">';
    ent.attributes.forEach(function(attr) {
      var roleColor = ROLE_COLORS[attr.semanticRole] || '#a1a1aa';
      var roleName2 = ROLE_CN[attr.semanticRole] || attr.semanticRole;
      var crLabel = attr.crossBoRef ? ' → ' + attr.crossBoRef.refBoCode : '';
      t1 += '<div class="attr-row"><span style="color:var(--text-tertiary);font-family:monospace;width:20px;text-align:right;flex-shrink:0">' + (attr.isPk ? '🔑' : '│') + '</span><span class="attr-name">' + attr.name + ' <small style="color:var(--text-tertiary)">' + attr.code + '</small>' + (attr.isPk?'<span class="pk-mark">PK</span>':'') + '</span><span class="attr-type">' + attr.type + '</span><span class="attr-role" style="background:' + roleColor + '22;color:' + roleColor + ';border:1px solid ' + roleColor + '33">' + roleName2 + crLabel + '</span></div>';
    });
    t1 += '</div></div>';
  });
  document.getElementById('tab-pane-1').innerHTML = t1 || '<div class="info-block">暂无实体定义</div>';

  // ── Tab 2: 业务操作 ──────────────────────────────────────
  var t2 = '';
  if (bo.operations && bo.operations.length > 0) {
    t2 += '<div class="section"><div class="section-title">⚡ 业务操作</div>';
    bo.operations.forEach(function(op) {
      t2 += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + op.name + '</span><span class="item-code">' + op.code + '</span></div><div class="item-meta"><span class="tag">' + (OPKIND_CN[op.operationKind]||op.operationKind) + '</span><span class="tag">作用域: ' + (SCOPE_CN[op.scope]||op.scope) + '</span><span class="tag" style="color:#a78bfa">' + op.authzAction + '</span></div></div>';
    });
    t2 += '</div>';
  }
  if (!t2) t2 = '<div class="info-block">暂无业务操作定义</div>';
  document.getElementById('tab-pane-2').innerHTML = t2;

  // ── Tab 3: 业务规则 ──────────────────────────────────────
  var t3 = buildTab3Rules(bo);
  document.getElementById('tab-pane-3').innerHTML = t3;

  // ── Tab 4: 数据权限规则 ──────────────────────────────────
  var t4 = buildTab4Security(bo);
  document.getElementById('tab-pane-4').innerHTML = t4;

  // ── Tab 5: 本体推理 ─────────────────────────────────────
  var t5 = buildTab5Reasoning(boCode, bo);
  document.getElementById('tab-pane-5').innerHTML = t5;

  switchTopTab('bo');
  switchTab(0);
  bindNavRefs(boMap);
}

function buildTab3Rules(bo) {
  var t3 = '';
  var hasRules = bo.rules && bo.rules.length > 0;
  var hasValidations = bo.validations && bo.validations.length > 0;
  var hasFieldViews = bo.fieldViews && bo.fieldViews.length > 0;

  // 业务规则区块
  t3 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon' + (hasRules?' open':'') + '">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">📜 复杂业务规则</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + (bo.rules?bo.rules.length:0) + ' 条</span></div><div class="entity-attrs' + (hasRules?' open':'') + '">';
  if (hasRules) {
    bo.rules.forEach(function(rule) {
      var sevClass = rule.severity === 'ERROR' ? 'error' : 'warn';
      t3 += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + rule.name + '</span><span class="item-code">' + rule.code + '</span></div>' + (rule.description ? '<div style="font-size:11px;color:var(--text-tertiary);margin:4px 0">' + rule.description + '</div>' : '') + '<div class="item-meta"><span class="tag">' + (RULETYPE_CN[rule.ruleType]||rule.ruleType) + '</span><span class="tag" style="color:#60a5fa">' + (TRIGGER_CN[rule.trigger]||rule.trigger||rule.triggerTiming||'—') + '</span><span class="rule-severity ' + sevClass + '">' + (SEVERITY_CN[rule.severity]||rule.severity) + '</span></div></div>';
    });
  } else {
    t3 += '<div style="padding:12px;font-size:11px;color:var(--text-tertiary)">暂无业务规则</div>';
  }
  t3 += '</div></div>';

  // 数据校验区块
  t3 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon' + (hasValidations && !hasRules?' open':'') + '">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">✅ 字段校验规则</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + (bo.validations?bo.validations.length:0) + ' 条</span></div><div class="entity-attrs' + (hasValidations && !hasRules?' open':'') + '">';
  if (hasValidations) {
    bo.validations.forEach(function(v) {
      var parts = [];
      if (v.required) parts.push('<span style="color:#ef4444">*必填</span>');
      if (v.unique) parts.push('唯一');
      if (v.min !== undefined && v.min !== null) parts.push('≥' + v.min);
      if (v.max !== undefined && v.max !== null) parts.push('≤' + v.max);
      if (v.pattern) parts.push('<code>' + v.pattern + '</code>');
      if (v.enum && v.enum.length) { var lbls = v.enum.slice(0,3).map(function(e){return typeof e==='object'?e.label:e;}).join(','); parts.push('枚举:[' + lbls + (v.enum.length>3?'…':'') + ']'); }
      t3 += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + fName(bo, v.entityCode, v.fieldCode) + '</span><span class="item-code">' + v.fieldCode + '</span></div><div class="item-meta">' + parts.join(' · ') + '—</div>' + (v.message ? '<div style="font-size:10px;color:#f59e0b;margin-top:4px;padding:4px 8px;background:rgba(245,158,11,0.05);border-left:2px solid #f59e0b;border-radius:2px">' + v.message + '</div>' : '') + '</div>';
    });
  } else {
    t3 += '<div style="padding:12px;font-size:11px;color:var(--text-tertiary)">暂无数据校验</div>';
  }
  t3 += '</div></div>';

  // 视图配置区块
  t3 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon' + (hasFieldViews && !hasRules && !hasValidations?' open':'') + '">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🖥️ 视图配置</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + (bo.fieldViews?bo.fieldViews.length:0) + ' 字段</span></div><div class="entity-attrs' + (hasFieldViews && !hasRules && !hasValidations?' open':'') + '">';
  if (hasFieldViews) {
    var listFields = bo.fieldViews.filter(function(f) { return f.showInList; }).sort(function(a,b){return (a.order||99)-(b.order||99);});
    if (listFields.length > 0) {
      t3 += '<div style="font-size:11px;color:var(--text-tertiary);padding:6px 12px">列表字段：</div><div style="display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 12px">';
      listFields.forEach(function(f) {
        t3 += '<span class="rel-badge" style="background:rgba(16,185,129,0.1);color:#34d399;border-color:rgba(16,185,129,0.2);cursor:default">' + fName(bo, f.entityCode, f.fieldCode) + '</span>';
      });
      t3 += '</div>';
    }
    var lv = bo.listViewConfig;
    if (lv && Object.keys(lv).length > 0) {
      t3 += '<div class="info-block" style="margin:0 12px 12px;display:flex;gap:16px;font-size:11px"><span>分页: <b>' + (lv.defaultPageSize||20) + '</b></span><span>布局: <b>' + (lv.formLayout||'GRID') + '</b></span><span>列数: <b>' + (lv.formColumns||2) + '</b></span></div>';
    }
  } else {
    t3 += '<div style="padding:12px;font-size:11px;color:var(--text-tertiary)">暂无视图配置</div>';
  }
  t3 += '</div></div>';
  return t3;
}

function buildTab4Security(bo) {
  var t4 = '';
  var hasFieldSec = bo.fieldSecurity && bo.fieldSecurity.length > 0;
  var rs = bo.rowSecurity;
  var hasRowSec = rs && rs.entriesByEntity && Object.keys(rs.entriesByEntity).length > 0;

  t4 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon' + (hasFieldSec?' open':'') + '">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🔒 字段级安全</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + (bo.fieldSecurity?bo.fieldSecurity.length:0) + ' 条</span></div><div class="entity-attrs' + (hasFieldSec?' open':'') + '">';
  if (hasFieldSec) {
    bo.fieldSecurity.forEach(function(sec) {
      var ctrlColor = sec.fieldControl === 'OPEN' ? '#10b981' : sec.fieldControl === 'HIDDEN' ? '#ef4444' : '#f59e0b';
      var ctrl = sec.fieldControl || sec.controlPolicy;
      var priv = sec.privacyClass || sec.privacyLevel;
      t4 += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + eName(bo, sec.entityCode) + ' · ' + fName(bo, sec.entityCode, sec.fieldCode) + '</span><span class="item-code">' + sec.fieldCode + '</span></div><div class="item-meta"><span class="tag" style="color:' + ctrlColor + '">' + (FIELDCTRL_CN[ctrl]||ctrl) + '</span><span class="tag" style="color:#c084fc">' + (PRIVACY_CN[priv]||priv) + '</span>' + (sec.reason ? '<span style="font-size:10px;color:var(--text-tertiary)">' + sec.reason + '</span>' : '') + '</div></div>';
    });
  } else {
    t4 += '<div style="padding:12px;font-size:11px;color:var(--text-tertiary)">暂无字段级安全策略</div>';
  }
  t4 += '</div></div>';

  t4 += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon' + (hasRowSec && !hasFieldSec?' open':'') + '">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🛡️ 行级权限</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + (rs&&rs.entriesByEntity?Object.keys(rs.entriesByEntity).length:0) + ' 实体</span></div><div class="entity-attrs' + (hasRowSec && !hasFieldSec?' open':'') + '">';
  if (hasRowSec) {
    t4 += '<div class="info-block">兜底策略：<b>' + (rs.fallbackScope==='ALL'?'全部可见':'全部不可见') + '</b></div>';
    for (var entity in rs.entriesByEntity) {
      var fields = rs.entriesByEntity[entity];
      t4 += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + eName(bo, entity) + '</span><span class="item-code">' + entity + '</span></div><div class="item-meta">鉴权字段：' + fields.map(function(f){return fName(bo,entity,f);}).join('、') + '</div></div>';
    }
  } else {
    t4 += '<div style="padding:12px;font-size:11px;color:var(--text-tertiary)">暂无行级权限策略</div>';
  }
  t4 += '</div></div>';
  return t4;
}

function bindNavRefs(boMap) {
  document.querySelectorAll('.nav-ref').forEach(function(el) {
    el.onclick = function(e) {
      e.stopPropagation();
      var targetBo = el.getAttribute('data-bo');
      if (allNodes.get(targetBo)) {
        network.selectNodes([targetBo]);
        showBoDetail(targetBo, boMap[targetBo]);
        network.focus(targetBo, { scale: 1.2, animation: true });
      }
    };
  });
}

function toggleEntity(header) {
  var icon = header.querySelector('.expand-icon');
  var attrs = header.nextElementSibling;
  var isOpen = attrs.classList.contains('open');
  if (isOpen) { attrs.classList.remove('open'); icon.classList.remove('open'); }
  else { attrs.classList.add('open'); icon.classList.add('open'); }
}

// ════════════════════════════════════════ 顶层 Tab 切换 ═════
function switchTopTab(tabName) {
  var topBo = document.getElementById('top-pane-bo');
  var topReasoning = document.getElementById('top-pane-reasoning');
  var tabBo = document.getElementById('top-tab-bo');
  var tabReasoning = document.getElementById('top-tab-reasoning');

  if (tabName === 'bo' && tabBo && tabBo.style.display !== 'none') {
    topBo.classList.add('active');
    topReasoning.classList.remove('active');
    tabBo.classList.add('active');
    tabReasoning.classList.remove('active');
  } else {
    topBo.classList.remove('active');
    topReasoning.classList.add('active');
    tabBo && tabBo.classList.remove('active');
    tabReasoning.classList.add('active');
  }
}

// ════════════════════════════════════════ Tab 5: 本体推理 ═════

// 未选中 BO 时渲染全局本体推理视图
function buildTab5GlobalReasoning() {
  var h = '';
  h += '<div style="padding:16px 20px 12px;border-bottom:1px solid var(--border-strong)">';
  h += '<div style="font-weight:500;font-size:13px;color:var(--text-secondary)">🧠 本体推理 — 全局视图</div>';
  h += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:4px">在画布中点击 BO 节点可查看围绕该 BO 的推理信息。</div>';
  h += '</div>';

  h += '<div style="padding:16px 20px">';

  // ── 全局显式链路 ──
  var allExplicitEdges = (graphData.edges || []).filter(function(e) { return e.linkSource === 'EXPLICIT'; });
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🔗 显式链路</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + allExplicitEdges.length + ' 条</span></div><div class="entity-attrs">';
  if (allExplicitEdges.length > 0) {
    allExplicitEdges.forEach(function(edge) {
      var fromBo = graphData.bos.find(function(b) { return b.boCode === edge.from; });
      var toBo = graphData.bos.find(function(b) { return b.boCode === edge.to; });
      var fromName = fromBo ? fromBo.boName : edge.from;
      var toName = toBo ? toBo.boName : edge.to;
      h += '<div class="list-item"><div class="list-item-header"><span class="item-title" style="cursor:pointer;color:var(--accent)" onclick="navigateToBo(\'' + edge.from + '\')">' + fromName + '</span><span style="color:var(--text-tertiary);margin:0 4px">→</span><span class="item-title" style="cursor:pointer;color:var(--accent)" onclick="navigateToBo(\'' + edge.to + '\')">' + toName + '</span><span class="item-code">' + (edge.linkCode||'') + '</span></div><div class="item-meta"><span class="tag" style="color:#34d399">显式</span><span class="tag">' + (edge.linkName||'') + '</span><span class="tag">' + (edge.linkKind||'') + '</span><span class="tag">' + (edge.cardinality||'') + '</span></div></div>';
    });
  } else {
    h += '<div style="padding:10px 12px;font-size:11px;color:var(--text-tertiary)">暂无显式链路。在 _ontology/fragments/ 中定义 LINK Fragment 即可建立。</div>';
  }
  h += '</div></div>';

  // ── 全局本体配置（子 Tab UI）──
  h += buildOntologyConfigSubTabs('global', null);

  // ── 全局推理演算 (Dry-Run) ──
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🧪 推理演算 (Dry-Run)</b></span></div><div class="entity-attrs open">';
  h += '<div class="scenario-selector-container">' + buildScenarioSelector() + '</div>';
  h += '<div style="padding:10px 12px 6px;display:flex;flex-wrap:wrap;gap:8px">';
  h += '<button class="btn-icon-text" onclick="runDryRun(\'all\',\'customer-360\')" style="font-size:11px;border-color:var(--border-strong)" title="给定客户ID，从元数据读取派生字段定义，AST 求值输出健康度、流失风险、下一步最佳行动">📊 客户360视图</button>';
  h += '<button class="btn-icon-text" onclick="runDryRun(\'all\',\'opportunity-intelligence\')" style="font-size:11px;border-color:var(--border-strong)" title="给定商机ID，AST 求值输出赢单概率、阶段流速、竞争风险等级、推荐推进动作">📈 商机智能视图</button>';
  h += '<button class="btn-icon-text" onclick="runDryRun(\'all\',\'pipeline-coverage\')" style="font-size:11px;border-color:var(--border-strong)" title="给定销售目标，汇率折算统一CNY口径，硬数据校验输出覆盖率、缺口金额、风险等级">📐 管道覆盖率</button>';
  h += '<button class="btn-icon-text" onclick="runDryRun(\'all\',\'opportunity-timeline\')" style="font-size:11px;border-color:var(--border-strong)" title="给定商机ID，回放阶段变更事件，输出停留天数和阶段流速">⏱️ 商机阶段时间线</button>';
  h += '<button class="btn-icon-text" onclick="runDryRun(\'all\',\'customer-activity-window\')" style="font-size:11px;border-color:var(--border-strong)" title="给定客户ID，按时间窗口统计活动次数和最近活动天数">📅 客户活动窗口</button>';
  h += '</div>';
  h += '<div style="margin:2px 12px;border-top:1px solid var(--border-strong)"></div>';
  h += '<div style="padding:6px 12px 10px;display:flex;flex-wrap:wrap;gap:8px">';
  h += '<button class="btn-icon-text btn-primary" onclick="runDryRun(\'all\',\'reasoning-chain\')" style="font-size:11px" title="给定一条客户记录，基于本体依赖关系自动编排：LINK 发现关联 BO → 拓扑排序解析 DERIVATION/TEMPORAL 依赖 → 依次 AST 求值 → RULE 合规评估 → ACTION_CHAIN 决策 → 汇率预计算 → LLM 生成经营分析报告">🧠 完整推理链</button>';
  h += '<button class="btn-icon-text" onclick="runRuleEval(\'all\')" style="font-size:11px;border-color:#f97316;color:#fb923c" title="加载各 BO 的 RULE Fragment，对含 exprAst 的规则逐一执行 AST 求值，输出通过/违规/跳过统计">⚖️ 规则合规评估</button>';
  h += '</div><div id="dryrun-output-all" style="padding:8px 12px;font-size:11px;color:var(--text-tertiary);min-height:40px;background:var(--bg-base);border-radius:4px;margin:8px 12px;border:1px solid var(--border-strong);font-family:monospace;white-space:pre-wrap">点击上方按钮触发推理演算…</div>';
  h += '<div style="padding:0 12px 12px;text-align:right"><button class="btn-icon-text" onclick="exportDryRunMd(\'all\')" style="font-size:11px;border-color:var(--border-strong)">📥 导出 MD</button></div>';
  h += '</div></div>';

  h += '</div>';
  return h;
}

function buildTab5Reasoning(boCode, bo) {
  var h = '';

  // BO 名称头部
  h += '<div style="padding:16px 20px 12px;border-bottom:1px solid var(--border-strong)">';
  h += '<div style="font-weight:500;font-size:13px;color:var(--text-secondary)">当前 BO: <span style="color:var(--text-primary)">' + bo.boName + '</span> <code style="font-size:11px">' + boCode + '</code></div>';
  h += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:4px">以下展示围绕当前 BO 的跨 BO 推理信息。取消选中 BO 可查看全局视图。</div>';
  h += '</div>';

  h += '<div style="padding:16px 20px">';

  // ── 1. 显式链路 (EXPLICIT LINKs from _ontology) ──
  var explicitEdges = (graphData.edges || []).filter(function(e) {
    return e.linkSource === 'EXPLICIT' && (e.from === boCode || e.to === boCode);
  });
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🔗 显式链路</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + explicitEdges.length + ' 条</span></div><div class="entity-attrs">';
  if (explicitEdges.length > 0) {
    explicitEdges.forEach(function(edge) {
      var isOut = edge.from === boCode;
      var targetBoCode = isOut ? edge.to : edge.from;
      var targetBo = graphData.bos.find(function(b) { return b.boCode === targetBoCode; });
      var targetName = targetBo ? targetBo.boName : targetBoCode;
      h += '<div class="list-item"><div class="list-item-header"><span class="item-title" style="cursor:pointer;color:var(--accent)" onclick="navigateToBo(\'' + targetBoCode + '\')">' + (isOut ? '→ ' : '← ') + targetName + '</span><span class="item-code">' + (edge.linkCode||'') + '</span></div><div class="item-meta"><span class="tag" style="color:#34d399">显式</span><span class="tag">' + (edge.linkName||'') + '</span><span class="tag">' + (edge.linkKind||'') + '</span><span class="tag">' + (edge.cardinality||'') + '</span></div></div>';
    });
  } else {
    h += '<div style="padding:10px 12px;font-size:11px;color:var(--text-tertiary)">暂无显式链路。在 _ontology/fragments/ 中定义 LINK Fragment 即可建立。</div>';
  }
  h += '</div></div>';

  // ── 2. 关联的本体配置（子 Tab UI）──
  h += buildOntologyConfigSubTabs(boCode, bo);

  // ── 3. Dry-run 推理 ──
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🧪 推理演算 (Dry-Run)</b></span></div><div class="entity-attrs open">';
  h += '<div class="scenario-selector-container">' + buildScenarioSelector() + '</div>';
  h += '<div style="padding:10px 12px 6px;display:flex;flex-wrap:wrap;gap:8px">';

  // 客户/商机节点显示专属 dry-run
  if (boCode === 'customers' || boCode === 'opportunities') {
    h += '<button class="btn-icon-text" onclick="runDryRun(\'' + boCode + '\',\'customer-360\')" style="font-size:11px;border-color:var(--border-strong)" title="给定客户ID，从元数据读取派生字段定义，AST 求值输出健康度、流失风险、下一步最佳行动">📊 客户360视图</button>';
    h += '<button class="btn-icon-text" onclick="runDryRun(\'' + boCode + '\',\'opportunity-intelligence\')" style="font-size:11px;border-color:var(--border-strong)" title="给定商机ID，AST 求值输出赢单概率、阶段流速、竞争风险等级、推荐推进动作">📈 商机智能视图</button>';
    h += '<button class="btn-icon-text" onclick="runDryRun(\'' + boCode + '\',\'pipeline-coverage\')" style="font-size:11px;border-color:var(--border-strong)" title="给定销售目标，汇率折算统一CNY口径，硬数据校验输出覆盖率、缺口金额、风险等级">📐 管道覆盖率</button>';
    h += '<button class="btn-icon-text" onclick="runDryRun(\'' + boCode + '\',\'opportunity-timeline\')" style="font-size:11px;border-color:var(--border-strong)" title="给定商机ID，回放阶段变更事件，输出停留天数和阶段流速">⏱️ 商机阶段时间线</button>';
    h += '<button class="btn-icon-text" onclick="runDryRun(\'' + boCode + '\',\'customer-activity-window\')" style="font-size:11px;border-color:var(--border-strong)" title="给定客户ID，按时间窗口统计活动次数和最近活动天数">📅 客户活动窗口</button>';
    h += '</div>';
    h += '<div style="margin:2px 12px;border-top:1px solid var(--border-strong)"></div>';
    h += '<div style="padding:6px 12px 10px;display:flex;flex-wrap:wrap;gap:8px">';
    h += '<button class="btn-icon-text btn-primary" onclick="runDryRun(\'' + boCode + '\',\'reasoning-chain\')" style="font-size:11px" title="给定一条客户记录，基于本体依赖关系自动编排：LINK 发现关联 BO → 拓扑排序解析 DERIVATION/TEMPORAL 依赖 → 依次 AST 求值 → RULE 合规评估 → ACTION_CHAIN 决策 → 汇率预计算 → LLM 生成经营分析报告">🧠 完整推理链</button>';
  }
  h += '<button class="btn-icon-text" onclick="runRuleEval(\'' + boCode + '\')" style="font-size:11px;border-color:#f97316;color:#fb923c" title="加载各 BO 的 RULE Fragment，对含 exprAst 的规则逐一执行 AST 求值，输出通过/违规/跳过统计">⚖️ 规则合规评估</button>';
  h += '</div><div id="dryrun-output-' + boCode + '" style="padding:8px 12px;font-size:11px;color:var(--text-tertiary);min-height:40px;background:var(--bg-base);border-radius:4px;margin:8px 12px;border:1px solid var(--border-strong);font-family:monospace;white-space:pre-wrap">点击上方按钮触发推理演算…</div>';
  h += '<div style="padding:0 12px 12px;text-align:right"><button class="btn-icon-text" onclick="exportDryRunMd(\'' + boCode + '\')" style="font-size:11px;border-color:var(--border-strong)">📥 导出 MD</button></div>';
  h += '</div></div>';

  h += '</div>'; // end padded content
  return h;
}

// ── 导航到其他 BO 节点 ──
function navigateToBo(targetBoCode) {
  var boMap = {};
  graphData.bos.forEach(function(b) { boMap[b.boCode] = b; });
  if (allNodes.get(targetBoCode)) {
    network.selectNodes([targetBoCode]);
    showBoDetail(targetBoCode, boMap[targetBoCode]);
    network.focus(targetBoCode, { scale: 1.2, animation: true });
  }
}

// ════════════════════════════════════════ 演示场景选择器 ═════
var _scenarioDirs = ['education', 'internet'];

async function loadScenarioDirs() {
  try {
    var resp = await fetch(API_BASE + '/api/scenarios');
    var data = await resp.json();
    if (data.scenarios && data.scenarios.length > 0) {
      _scenarioDirs = data.scenarios;
    }
  } catch(e) { /* fallback to hardcoded */ }
}

function buildScenarioSelector() {
  var h = '';
  h += '<div style="padding:8px 12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">';
  h += '<span style="font-size:11px;color:var(--text-tertiary);white-space:nowrap">📁 演示场景:</span>';
  _scenarioDirs.forEach(function(dir) {
    var active = dir === currentScenarioDir;
    h += '<button class="btn-icon-text" onclick="switchScenarioDir(\'' + dir + '\')" style="font-size:11px;' + (active ? 'border-color:var(--accent);color:var(--accent);background:rgba(59,130,246,0.1)' : 'border-color:var(--border-strong)') + '">' + dir + (active ? ' ✓' : '') + '</button>';
  });
  h += '</div>';
  return h;
}

function switchScenarioDir(dir) {
  currentScenarioDir = dir;
  // 重新渲染当前推理视图中的场景选择器
  var selector = document.querySelector('.scenario-selector-container');
  if (selector) selector.innerHTML = buildScenarioSelector();
  // 数据图谱模式下自动重新加载数据
  if (dataGraphMode) {
    reloadDataGraph();
  }
}

// ════════════════════════════════════════ 本体配置子 Tab（内嵌于推理视图）═════
var ontologyReasoningSubTab = 'derivation';

function buildOntologyConfigSubTabs(boCode, bo) {
  var derivs = bo ? filterRelatedDerivations(boCode, bo) : (graphData.derivedObjects || []);
  var timelines = bo ? filterRelatedTimelines(boCode) : (graphData.temporalTimelines || []);
  var chains = bo ? filterRelatedChains(boCode) : (graphData.actionChains || []);
  var total = derivs.length + timelines.length + chains.length;

  var h = '';
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🧩 ' + (bo ? '关联的本体配置' : '全局本体配置') + '</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + total + ' 项</span></div><div class="entity-attrs" style="padding:0">';
  h += '<div class="onto-cfg-tabs" style="margin:0;border-bottom:1px solid var(--border-strong)">';
  h += '<button class="onto-cfg-tab' + (ontologyReasoningSubTab==='derivation'?' active':'') + '" data-tab="derivation" onclick="switchReasoningSubTab(\'derivation\')"><span style="color:#fb923c">📐</span> 派生视图 <span class="onto-cfg-count">(' + derivs.length + ')</span></button>';
  h += '<button class="onto-cfg-tab' + (ontologyReasoningSubTab==='temporal'?' active':'') + '" data-tab="temporal" onclick="switchReasoningSubTab(\'temporal\')"><span style="color:#2dd4bf">⏱️</span> 时态时间线 <span class="onto-cfg-count">(' + timelines.length + ')</span></button>';
  h += '<button class="onto-cfg-tab' + (ontologyReasoningSubTab==='action-chain'?' active':'') + '" data-tab="action-chain" onclick="switchReasoningSubTab(\'action-chain\')"><span style="color:#a78bfa">⚡</span> 动作链 <span class="onto-cfg-count">(' + chains.length + ')</span></button>';
  h += '</div>';
  h += '<div class="onto-cfg-sub-body" id="onto-cfg-sub-body-' + (boCode||'global') + '" style="max-height:400px;overflow-y:auto;padding:8px">';
  h += renderReasoningSubTabContent(ontologyReasoningSubTab, derivs, timelines, chains, boCode);
  h += '</div>';
  if (total === 0) {
    h += '<div style="padding:10px 12px;font-size:11px;color:var(--text-tertiary)">' + (bo ? '该 BO 暂无关联的本体配置。' : '暂无本体配置。在 _ontology/fragments/ 中定义对应 Fragment 即可建立。') + '</div>';
  }
  h += '</div></div>';
  return h;
}

function switchReasoningSubTab(tab) {
  ontologyReasoningSubTab = tab;
  // update tab button active states
  var container = document.querySelector('.onto-cfg-tabs');
  if (container) {
    container.querySelectorAll('.onto-cfg-tab').forEach(function(btn) {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tab);
    });
  }
  // re-render content
  var bodyEl = document.querySelector('.onto-cfg-sub-body');
  if (!bodyEl) return;
  var boCode = selectedBoCode || 'global';
  var derivs = selectedBoCode ? filterRelatedDerivations(selectedBoCode) : (graphData.derivedObjects || []);
  var timelines = selectedBoCode ? filterRelatedTimelines(selectedBoCode) : (graphData.temporalTimelines || []);
  var chains = selectedBoCode ? filterRelatedChains(selectedBoCode) : (graphData.actionChains || []);
  bodyEl.innerHTML = renderReasoningSubTabContent(tab, derivs, timelines, chains, boCode);
}

function renderReasoningSubTabContent(tab, derivs, timelines, chains, boCode) {
  if (tab === 'derivation') {
    if (derivs.length === 0) return '<div class="onto-cfg-empty">暂无派生视图</div>';
    return derivs.map(function(d) {
      var role = (d.rootBoCode === boCode) ? '<span class="tag" style="color:#fb923c">根 BO</span>' : '';
      var h = '<div class="onto-cfg-item" onclick="navigateToOntologyNode(\'' + d.id + '\')">';
      h += '<div class="onto-cfg-item-header"><span class="onto-cfg-item-title" style="color:#fb923c">📐 ' + d.name + '</span><span class="onto-cfg-item-code">' + d.code + '</span></div>';
      h += '<div class="onto-cfg-item-meta">' + role + '<span class="tag">' + (d.objectKind||'') + '</span><span class="tag">根: ' + (d.rootBoCode||'—') + '</span><span class="tag">' + d.fieldCount + ' 字段</span><span class="tag">' + (d.dependencies||[]).length + ' 依赖</span></div>';
      if (d.description) h += '<div class="onto-cfg-item-desc">' + d.description + '</div>';
      if (d.dependencies && d.dependencies.length > 0) {
        h += '<div class="onto-cfg-item-deps">';
        d.dependencies.forEach(function(dep) {
          h += '<span class="onto-cfg-dep' + (dep.required ? ' required' : '') + '">' + dep.boCode + ' <small>via ' + (dep.viaLink||'—') + '</small></span>';
        });
        h += '</div>';
      }
      h += '</div>';
      return h;
    }).join('');
  }
  if (tab === 'temporal') {
    if (timelines.length === 0) return '<div class="onto-cfg-empty">暂无时态时间线</div>';
    return timelines.map(function(t) {
      var h = '<div class="onto-cfg-item" onclick="showTemporalTimelineDetail(\'' + t.timelineCode + '\')">';
      h += '<div class="onto-cfg-item-header"><span class="onto-cfg-item-title" style="color:#2dd4bf">⏱️ ' + t.timelineName + '</span><span class="onto-cfg-item-code">' + t.timelineCode + '</span></div>';
      h += '<div class="onto-cfg-item-meta"><span class="tag">BO: ' + (t.boCode||'—') + '</span><span class="tag">实体: ' + (t.entityCode||'—') + '</span><span class="tag">时间: ' + (t.timeField||'—') + '</span>' + (t.stateField ? '<span class="tag">状态: ' + t.stateField + '</span>' : '') + '<span class="tag">' + t.metricCount + ' 指标</span></div>';
      if (t.description) h += '<div class="onto-cfg-item-desc">' + t.description + '</div>';
      if (t.metrics && t.metrics.length > 0) {
        h += '<div class="onto-cfg-item-deps">';
        t.metrics.forEach(function(m) {
          h += '<span class="onto-cfg-dep" style="border-color:rgba(20,184,166,0.3);color:#2dd4bf">' + (m.code||'') + ' <small>' + (m.metricType||'') + '</small></span>';
        });
        h += '</div>';
      }
      h += '</div>';
      return h;
    }).join('');
  }
  if (tab === 'action-chain') {
    if (chains.length === 0) return '<div class="onto-cfg-empty">暂无动作链</div>';
    return chains.map(function(c) {
      var role = (c.triggerBoCode === boCode) ? '<span class="tag" style="color:#a78bfa">触发方</span>' : '';
      var h = '<div class="onto-cfg-item" onclick="navigateToOntologyNode(\'' + c.id + '\')">';
      h += '<div class="onto-cfg-item-header"><span class="onto-cfg-item-title" style="color:#a78bfa">⚡ ' + c.name + '</span><span class="onto-cfg-item-code">' + c.code + '</span></div>';
      h += '<div class="onto-cfg-item-meta">' + role + '<span class="tag">' + (c.triggerType||'') + '</span>' + (c.triggerBoCode ? '<span class="tag">触发: ' + c.triggerBoCode + '</span>' : '') + (c.triggerOperationCode ? '<span class="tag">' + c.triggerOperationCode + '</span>' : '') + '<span class="tag">' + c.stepCount + ' 步</span><span class="tag">' + (c.executionMode||'') + '</span></div>';
      if (c.description) h += '<div class="onto-cfg-item-desc">' + c.description + '</div>';
      if (c.steps && c.steps.length > 0) {
        h += '<div class="onto-cfg-item-deps">';
        c.steps.forEach(function(s, i) {
          var tgt = s.target || {};
          var tgtStr = tgt.derivedCode || tgt.boCode || tgt.channel || '';
          h += '<span class="onto-cfg-dep" style="border-color:rgba(124,58,237,0.3);color:#a78bfa">' + (i+1) + '. ' + (s.stepType||'') + (tgtStr ? ' → ' + tgtStr : '') + '</span>';
        });
        h += '</div>';
      }
      h += '</div>';
      return h;
    }).join('');
  }
  return '';
}

function filterRelatedDerivations(boCode) {
  return (graphData.derivedObjects || []).filter(function(d) {
    return d.rootBoCode === boCode || (d.dependencies || []).some(function(dep) { return dep.boCode === boCode; });
  });
}
function filterRelatedTimelines(boCode) {
  return (graphData.temporalTimelines || []).filter(function(t) { return t.boCode === boCode; });
}
function filterRelatedChains(boCode) {
  return (graphData.actionChains || []).filter(function(c) {
    if (c.triggerBoCode === boCode) return true;
    return (c.steps || []).some(function(s) {
      var tgt = s.target || {};
      return tgt.boCode === boCode;
    });
  });
}
