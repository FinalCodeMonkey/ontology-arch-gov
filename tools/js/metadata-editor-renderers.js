/* ═══════════════════════════════════════════════════════════════════
   metadata-editor-renderers.js — Fragment form rendering engine
   MODEL/VALIDATION/SECURITY/RULE/VIEW/OPERATION plus tree+detail
   Dependencies: shared-dicts.js, metadata-editor-core.js
   ═══════════════════════════════════════════════════════════════════ */

// ── Form rendering engine ──────────────────────────────────────
function renderForm() {
  var root = document.getElementById('form-root');
  var mt = currentMetaType;
  var env = formState.envelope;
  var c = formState.content;
  var html = '';

  if (currentTab === 'BO_INFO') {
    html += renderBOINFO();
  } else switch(mt) {
    case 'MODEL':
      if (currentTab === 'API_CONFIG') { html += renderAPICONFIG(c); }
      else { html += renderMODEL(c); }
      break;
    case 'VALIDATION': html += renderVALIDATION(c); break;
    case 'SECURITY': html += renderSECURITY(c); break;
    case 'RULE': html += renderRULE(c); break;
    case 'VIEW': html += renderVIEW(c); break;
    case 'OPERATION': html += renderOPERATION(c); break;
    case 'LINK': html += renderLINK(c); break;
    case 'DERIVATION': html += renderDERIVATION(c); break;
    case 'TEMPORAL': html += renderTEMPORAL(c); break;
    case 'ACTION_CHAIN': html += renderACTIONCHAIN(c); break;
  }

  if (currentTab === 'MODEL' && !g_treeSel) {
    var ents = (c.entities||[]);
    for (var i = 0; i < ents.length; i++) {
      if (ents[i].isPrimary && ents[i].aggregateRole === 'ROOT') {
        g_treeSel = {type: 'entity', ei: i};
        break;
      }
    }
  }

  root.innerHTML = html;
  var formInner = document.getElementById('form-root');
  var isTreeTab = (currentTab === 'VALIDATION' || currentTab === 'RULE' || currentTab === 'VIEW' || currentTab === 'OPERATION');
  if (formInner) { formInner.classList.toggle('tree-mode', isTreeTab); }
  bindAllEvents();
  restoreTreeSelection();
}

// ═══════════════════════════════════════════════ 管理信息 Tab ═══
function renderBOINFO() {
  var env = formState.envelope;
  var schema = g_schemaCache['ENVELOPE'];
  if (!schema) {
    loadSchema('ENVELOPE').then(function() { renderForm(); });
    return secCard('📧 BO 管理信息（bo-info.json）', '<div class="empty-hint">⏳ 正在加载 schema…</div>');
  }
  var h = schemaSection(schema, env, 'envelope', '📧 BO 管理信息（bo-info.json）', {
    hiddenFields: ['$schema', 'metaType'],
    disabledFields: ['boCode', 'schemaVersion']
  });
  return h;
}

// ═══════════════════════════════════════════════ API 配置 Tab ═══
function renderAPICONFIG(c) {
  var schema = g_schemaCache['MODEL'];
  if (!schema) {
    loadSchema('MODEL').then(function() { renderForm(); });
    return secCard('🔌 API 配置', '<div class="empty-hint">⏳ 正在加载 schema…</div>');
  }
  var acSchema = (schema.properties.apiConfig || {});
  var ac = c.apiConfig || {};
  var rootEnt = null;
  (c.entities||[]).forEach(function(e) {
    if (e.isPrimary && e.aggregateRole === 'ROOT') rootEnt = e;
  });
  if (!rootEnt) {
    (c.entities||[]).forEach(function(e) {
      if (e.aggregateRole === 'ROOT' && !rootEnt) rootEnt = e;
    });
  }
  var rootAttrs = rootEnt ? (rootEnt.attributes||[]) : [];
  var entNameMap = {};
  (c.entities||[]).forEach(function(e) { if (e.code) entNameMap[e.code] = e.name || e.code; });

  var h = '<div style="flex:1;min-height:0">';
  h += schemaSection(acSchema, ac, 'content.apiConfig', '🔌 API 配置', {
    hiddenFields: ['responseWrapper','batchResultType','idField','businessKeyField','aggregateApiPolicy','alternateAggregateApis'],
    disabledFields: ['resourcePath']
  });
  h += '<div class="sub-sec"><div class="sub-sec-title">字段映射（来自主实体属性）</div>';
  h += '<div class="form-grid">';
  h += '<div class="field-group"><label class="f-label">ID 字段 <span class="req">*</span><i class="help-icon" data-help="聚合根主键字段，必须在主实体属性中声明且 isPk=true。||例：id">?</i></label>';
  h += '<select class="f-select" data-path="content.apiConfig.idField">';
  h += '<option value="">-- 选择属性 --</option>';
  rootAttrs.forEach(function(a) {
    var sel = ac.idField === a.code ? ' selected' : '';
    h += '<option value="' + escHtml(a.code) + '"' + sel + '>' + escHtml(a.name||a.code) + ' (' + escHtml(a.code) + ')</option>';
  });
  h += '</select></div>';
  h += '<div class="field-group"><label class="f-label">业务键字段 <span class="hint">可选</span><i class="help-icon" data-help="业务唯一标识字段，用于导入匹配和对外展示编号。||例：scene_no">?</i></label>';
  h += '<select class="f-select" data-path="content.apiConfig.businessKeyField">';
  h += '<option value="">-- 无 --</option>';
  rootAttrs.forEach(function(a) {
    var sel = ac.businessKeyField === a.code ? ' selected' : '';
    h += '<option value="' + escHtml(a.code) + '"' + sel + '>' + escHtml(a.name||a.code) + ' (' + escHtml(a.code) + ')</option>';
  });
  h += '</select></div>';
  h += '</div></div>';

  var apSchema = acSchema.properties.aggregateApiPolicy || {};
  var ap = ac.aggregateApiPolicy || {};
  h += '<div class="sub-sec"><div class="sub-sec-title">聚合 API 策略</div>';
  h += schemaObjectForm(apSchema, ap, 'content.apiConfig.aggregateApiPolicy', {hiddenFields:['aggregateReplaceActionPath','alternateAggregateApis']});
  var showReplace = (ap.updateScope === 'FULL_AGGREGATE_REPLACE');
  h += '<div id="row-aggReplacePath" style="' + (showReplace ? '' : 'display:none') + '">';
  h += schemaFieldHtml(apSchema, 'aggregateReplaceActionPath', ap.aggregateReplaceActionPath, 'content.apiConfig.aggregateApiPolicy', {});
  h += '</div>';
  var embCodes = (ap.detailEmbedEntities||[]).join(',');
  var embNames = (ap.detailEmbedEntities||[]).map(function(code) {
    return entNameMap[code] || code;
  }).join(', ');
  h += '<div class="f-label" style="margin-top:6px">内嵌实体 <span class="hint">(由模型实体自动推导)</span><i class="help-icon" data-help="详情接口返回时内嵌的子实体列表，值由模型中的实体 code 自动推导，不可手动编辑。||例：lines, attachments">?</i></div>';
  h += '<input class="f-input" id="inp-embEntities" value="' + escHtml(embNames) + '" disabled>';
  h += '<input type="hidden" data-path="content.apiConfig.aggregateApiPolicy.detailEmbedEntities" id="hid-embEntities" value="' + escHtml(embCodes) + '">';
  h += '</div>';
  h += '</div>';
  return h;
}

// ════════════════════════════════════════════════════════ MODEL ═
function renderMODEL(c) {
  var schema = g_schemaCache['MODEL'];
  if (!schema) {
    loadSchema('MODEL').then(function() { renderForm(); });
    return secCard('📋 基本信息', '<div class="empty-hint">⏳ 正在加载 schema…</div>');
  }
  var rootEnt = null;
  (c.entities||[]).forEach(function(e) {
    if (e.isPrimary && e.aggregateRole === 'ROOT') rootEnt = e;
  });
  if (!rootEnt) {
    (c.entities||[]).forEach(function(e) {
      if (e.aggregateRole === 'ROOT' && !rootEnt) rootEnt = e;
    });
  }
  var rootAttrs = rootEnt ? (rootEnt.attributes||[]) : [];
  var h = '';
  h += schemaSection(schema, c, 'content', '📋 基本信息', {
    hiddenFields: ['apiConfig','boConfig','entities'],
    disabledFields: ['boCode']
  });
  var bcSchema = schema.properties.boConfig || {};
  var bc = c.boConfig || {};
  var bcBody = schemaObjectForm(bcSchema, bc, 'content.boConfig', {
    hiddenFields: ['nameField','statusField','defaultSort']
  });
  bcBody += '<div class="sub-sec"><div class="sub-sec-title">字段映射（来自主实体属性）</div>';
  bcBody += '<div class="form-grid">';
  bcBody += '<div class="field-group"><label class="f-label">名称字段 <span class="req">*</span><i class="help-icon" data-help="BO 的名称字段，用于列表展示和引用显示。必须在主实体属性中存在。||例：scene_name">?</i></label>';
  bcBody += '<select class="f-select" data-path="content.boConfig.nameField">';
  bcBody += '<option value="">-- 选择属性 --</option>';
  rootAttrs.forEach(function(a) {
    var sel = bc.nameField === a.code ? ' selected' : '';
    bcBody += '<option value="' + escHtml(a.code) + '"' + sel + '>' + escHtml(a.name||a.code) + ' (' + escHtml(a.code) + ')</option>';
  });
  bcBody += '</select></div>';
  bcBody += '<div class="field-group"><label class="f-label">状态字段<i class="help-icon" data-help="BO 的状态字段，用于工作流和生命周期管理。必须在主实体属性中存在。||例：status、scene_status">?</i></label>';
  bcBody += '<select class="f-select" data-path="content.boConfig.statusField">';
  bcBody += '<option value="">-- 无 --</option>';
  rootAttrs.forEach(function(a) {
    var sel = bc.statusField === a.code ? ' selected' : '';
    bcBody += '<option value="' + escHtml(a.code) + '"' + sel + '>' + escHtml(a.name||a.code) + ' (' + escHtml(a.code) + ')</option>';
  });
  bcBody += '</select></div>';
  bcBody += '</div></div>';
  var dsSchema = (bcSchema.properties.defaultSort || {});
  var ds = bc.defaultSort || {};
  bcBody += '<div class="sub-sec"><div class="sub-sec-title">默认排序</div><div class="form-grid">';
  bcBody += '<div class="field-group"><label class="f-label">排序字段<i class="help-icon" data-help="默认排序字段，必须在主实体属性中存在。||例：created_at">?</i></label>';
  bcBody += '<select class="f-select" data-path="content.boConfig.defaultSort.field">';
  bcBody += '<option value="">-- 选择属性 --</option>';
  rootAttrs.forEach(function(a) {
    var sel2 = (ds.field === a.code) ? ' selected' : '';
    bcBody += '<option value="' + escHtml(a.code) + '"' + sel2 + '>' + escHtml(a.name||a.code) + ' (' + escHtml(a.code) + ')</option>';
  });
  bcBody += '</select></div>';
  bcBody += schemaFieldHtml(dsSchema, 'direction', ds.direction, 'content.boConfig.defaultSort', {});
  bcBody += '</div></div>';
  h += secCard('⚙️ BO 配置', bcBody, false);
  h += renderEntities(c.entities);
  return h;
}

function renderEntities(entities) {
  var h = '<div class="section-card" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden"><div class="section-head" data-toggle="section"><span class="expand-icon open">▶</span><span class="section-head-title">🏗️ 实体定义 <span class="section-badge">' + entities.length + '</span></span></div><div class="section-body open" style="flex:1;display:flex;flex-direction:column"><div class="entity-split" style="flex:1;min-height:0">';
  h += '<div class="entity-tree" id="entity-tree">';
  h += '<div class="entity-tree-toolbar">';
  h += '<button onclick="addEntity()">+ 添加实体</button>';
  h += '<button onclick="addAttributeForSelection()">+ 添加属性</button>';
  h += '<button class="tb-del" onclick="deleteSelected()">🗑 删除</button>';
  h += '</div>';
  entities.forEach(function(ent, ei) {
    var aggCls = ent.aggregateRole==='ROOT'?'eb-root':ent.aggregateRole==='SUB_ENTITY'?'eb-sub':ent.aggregateRole==='VALUE_OBJECT'?'eb-vo':'eb-derv';
    h += '<div class="tree-node lv-ent" data-ei="' + ei + '" onclick="selectTreeNode(event, this, \'entity\',' + ei + ')"><span class="tn-arrow" id="tna-' + ei + '">▶</span><span class="tn-name">' + escHtml(ent.name||'(未命名)') + '</span><span class="tn-code">' + escHtml(ent.code||'') + '</span><span class="tn-badge ' + aggCls + '">' + enumLabel(ent.aggregateRole||'ROOT') + '</span></div>';
    var attrDivId = 'tna-list-' + ei;
    h += '<div id="' + attrDivId + '" style="display:none">';
    (ent.attributes||[]).forEach(function(attr, ai) {
      var sr = attr.semanticRole||'NORMAL';
      var rbCls = {TECHNICAL_ID:'rb-TID',BUSINESS_KEY:'rb-BK',NAME:'rb-NAME',NORMAL:'rb-NRM',CROSS_BO_REF:'rb-XREF',CROSS_BO_DISPLAY:'rb-XDSP',PARENT_REF:'rb-PREF',STATUS:'rb-STS'}[sr]||'rb-NRM';
      h += '<div class="tree-node lv-attr" data-ei="' + ei + '" data-ai="' + ai + '" onclick="selectTreeNode(event, this, \'attr\',' + ei + ',' + ai + ')"><span class="tn-name">' + escHtml(attr.name||'(未命名)') + '</span><span class="tn-code">' + escHtml(attr.code||'') + '</span><span style="font-size:9px;color:#0ea5e9;font-family:monospace">' + escHtml(attr.type||'?') + '</span>' + (attr.isPk?'<span style="color:#fbbf24;font-size:9px;margin-left:2px">🔑</span>':'') + '<span class="tn-badge ' + rbCls + '">' + enumLabel(sr) + '</span></div>';
    });
    h += '</div>';
  });
  h += '</div>';
  h += '<div class="entity-tree-resize" id="entity-tree-resize" onmousedown="startTreeResize(event)"></div>';
  h += '<div class="entity-detail" id="entity-detail">';
  if (g_treeSel) {
    h += renderTreeDetail(g_treeSel);
  } else {
    h += '<div class="ed-empty">← 从左侧选择实体或属性节点查看配置</div>';
  }
  h += '</div></div></div></div>';
  return h;
}

// ── Entity tree selection & detail ───────────────────────────
function selectTreeNode(e, el, type, ei, ai) {
  e.stopPropagation();
  if (type === 'entity') {
    var list = document.getElementById('tna-list-' + ei);
    var arrow = document.getElementById('tna-' + ei);
    if (list && arrow) {
      var isOpen = list.style.display !== 'none';
      if (isOpen) { list.style.display = 'none'; arrow.classList.remove('open'); }
      else { list.style.display = ''; arrow.classList.add('open'); }
    }
  }
  g_treeSel = {type: type, ei: ei, ai: ai};
  applyTreeSelection();
  var detail = document.getElementById('entity-detail');
  if (detail) detail.innerHTML = renderTreeDetail(g_treeSel);
  bindAllEvents();
}

function applyTreeSelection() {
  document.querySelectorAll('#entity-tree .tree-node.selected').forEach(function(n) { n.classList.remove('selected'); });
  if (!g_treeSel) return;
  var sel;
  if (g_treeSel.type === 'entity') {
    sel = document.querySelector('#entity-tree .tree-node.lv-ent[data-ei="' + g_treeSel.ei + '"]');
  } else {
    sel = document.querySelector('#entity-tree .tree-node.lv-attr[data-ei="' + g_treeSel.ei + '"][data-ai="' + g_treeSel.ai + '"]');
    var list = document.getElementById('tna-list-' + g_treeSel.ei);
    if (list) list.style.display = '';
    var arrow = document.getElementById('tna-' + g_treeSel.ei);
    if (arrow) arrow.classList.add('open');
  }
  if (sel) sel.classList.add('selected');
}

function restoreTreeSelection() {
  if (!g_treeSel) return;
  applyTreeSelection();
  var detail = document.getElementById('entity-detail');
  if (detail) detail.innerHTML = renderTreeDetail(g_treeSel);
  bindAllEvents();
}

function refreshTreeNode(dataPath) {
  var parts = dataPath.split('.');
  var ei = -1, ai = -1, field = '';
  if (parts.length >= 3 && parts[0] === 'content' && parts[1] === 'entities') {
    ei = parseInt(parts[2]);
    field = parts[3] || '';
    if (parts.length >= 5 && parts[3] === 'attributes') {
      ai = parseInt(parts[4]);
      field = parts[5] || '';
    }
  }
  if (parts.length >= 3 && parts[0] === 'content' && parts[1] === 'operations') {
    var oi = parseInt(parts[2]);
    syncOpTreeNode(oi);
    return;
  }
  if (parts.length >= 3 && parts[0] === 'content' && parts[1] === 'fieldViews') {
    var vi = parseInt(parts[2]);
    syncViewTreeNode(vi);
    return;
  }
  if (ei < 0) return;
  if (ai >= 0) {
    var node = document.querySelector('#entity-tree .tree-node.lv-attr[data-ei="' + ei + '"][data-ai="' + ai + '"]');
    if (!node) return;
    var ent2 = (formState.content.entities||[])[ei];
    var attr = ent2 ? (ent2.attributes||[])[ai] : null;
    if (!attr) return;
    if (field === 'name' || !field) {
      var nameEl = node.querySelector('.tn-name');
      if (nameEl) nameEl.textContent = attr.name || '(未命名)';
    }
    if (field === 'code' || !field) {
      var codeEl = node.querySelector('.tn-code');
      if (codeEl) codeEl.textContent = attr.code || '';
    }
    if (field === 'type' || !field) {
      var typeEl = node.querySelector('span[style*="color:#0ea5e9"]');
      if (typeEl) typeEl.textContent = attr.type || '?';
    }
    if (field === 'semanticRole' || !field) {
      var sr = attr.semanticRole||'NORMAL';
      var badgeEl = node.querySelector('.tn-badge');
      if (badgeEl) {
        var rbCls = {TECHNICAL_ID:'rb-TID',BUSINESS_KEY:'rb-BK',NAME:'rb-NAME',NORMAL:'rb-NRM',CROSS_BO_REF:'rb-XREF',CROSS_BO_DISPLAY:'rb-XDSP',PARENT_REF:'rb-PREF',STATUS:'rb-STS'}[sr]||'rb-NRM';
        badgeEl.className = 'tn-badge ' + rbCls;
        badgeEl.textContent = enumLabel(sr);
      }
    }
  } else {
    var node2 = document.querySelector('#entity-tree .tree-node.lv-ent[data-ei="' + ei + '"]');
    if (!node2) return;
    var ent3 = (formState.content.entities||[])[ei];
    if (!ent3) return;
    if (field === 'name' || !field) {
      var nameEl2 = node2.querySelector('.tn-name');
      if (nameEl2) nameEl2.textContent = ent3.name || '(未命名)';
    }
    if (field === 'code' || !field) {
      var codeEl2 = node2.querySelector('.tn-code');
      if (codeEl2) codeEl2.textContent = ent3.code || '';
    }
    if (field === 'aggregateRole' || !field) {
      var aggCls = ent3.aggregateRole==='ROOT'?'eb-root':ent3.aggregateRole==='SUB_ENTITY'?'eb-sub':ent3.aggregateRole==='VALUE_OBJECT'?'eb-vo':'eb-derv';
      var badgeEl2 = node2.querySelector('.tn-badge');
      if (badgeEl2) {
        badgeEl2.className = 'tn-badge ' + aggCls;
        badgeEl2.textContent = enumLabel(ent3.aggregateRole||'ROOT');
      }
    }
    if (field === 'aggregateRole') {
      var detail = document.getElementById('entity-detail');
      if (detail && g_treeSel && g_treeSel.type === 'entity' && g_treeSel.ei === ei) {
        detail.innerHTML = renderTreeDetail(g_treeSel);
        bindAllEvents();
      }
    }
  }
}

function renderTreeDetail(sel) {
  var h = '';
  if (sel.type === 'entity') {
    var ent = (formState.content.entities||[])[sel.ei];
    if (!ent) return '<div class="ed-empty">实体不存在</div>';
    var ei = sel.ei;
    h += '<div style="font-weight:600;font-size:13px;margin-bottom:10px;color:var(--text-primary)">' + escHtml(ent.name||'(未命名)') + ' <span style="color:var(--text-tertiary);font-size:11px;font-family:monospace">' + escHtml(ent.code||'') + '</span></div>';
    var schema = g_schemaCache['MODEL'];
    var entSchema = schema ? ((schema.properties.entities||{}).items||{}) : {};
    h += schemaObjectForm(entSchema, ent, 'content.entities.' + ei, {
      hiddenFields: ['attributes','entityApiPolicy','parentEntityCode','parentRefField','routeSegment','isPrimary']
    });
    var isPrimary = ent.isPrimary === true;
    var allEnts = (formState.content.entities||[]);
    h += '<div class="form-grid"><div class="field-group">';
    h += '<label class="f-label">主实体<i class="help-icon" data-help="由聚合角色自动推导。聚合根=自动勾选，子实体/值对象/派生视图=自动取消。||不可手动编辑。">?</i></label>';
    h += '<label class="f-check"><input type="checkbox" id="chk-isPrimary" data-path="content.entities.' + ei + '.isPrimary"'
      + (isPrimary ? ' checked' : '') + ' disabled> <span>' + (isPrimary ? '是（聚合根）' : '否') + '</span></label>';
    h += '</div></div>';
    h += '<div id="row-parentFields" style="' + (isPrimary ? 'display:none' : '') + '">';
    var parentCode = ent.parentEntityCode || '';
    h += '<div class="form-grid"><div class="field-group">';
    h += '<label class="f-label">父实体代码<i class="help-icon" data-help="当前实体的父实体 code，用于建立聚合内父子关系。||例：header（如果当前实体是 lines）">?</i></label>';
    h += '<select class="f-select" id="sel-parentEntityCode" data-path="content.entities.' + ei + '.parentEntityCode">';
    h += '<option value="">-- 选择父实体 --</option>';
    allEnts.forEach(function(e, i) {
      if (i === ei) return;
      var sel = (parentCode === e.code) ? ' selected' : '';
      h += '<option value="' + escHtml(e.code) + '"' + sel + '>' + escHtml(e.name||e.code) + ' (' + escHtml(e.code) + ')</option>';
    });
    h += '</select></div>';
    var curRef = ent.parentRefField || '';
    h += '<div class="field-group">';
    h += '<label class="f-label">父引用字段<i class="help-icon" data-help="当前实体中引用父实体的外键字段，从当前实体的属性中选择。||例：header_id">?</i></label>';
    h += '<select class="f-select" id="sel-parentRefField" data-path="content.entities.' + ei + '.parentRefField">';
    h += '<option value="">-- 选择属性 --</option>';
    var matched = false;
    (ent.attributes||[]).forEach(function(a) {
      var sel2 = (curRef === a.code) ? ' selected' : '';
      if (curRef === a.code) matched = true;
      h += '<option value="' + escHtml(a.code) + '"' + sel2 + '>' + escHtml(a.name||a.code) + ' (' + escHtml(a.code) + ')</option>';
    });
    if (curRef && !matched) {
      h += '<option value="' + escHtml(curRef) + '" selected>' + escHtml(curRef) + ' (当前值)</option>';
    }
    if ((ent.attributes||[]).length === 0) {
      h += '<option value="" disabled>⚠ 当前实体无属性，请先添加属性</option>';
    }
    h += '</select></div></div>';
    if (!isPrimary) {
      h += '<div class="form-grid"><div class="field-group">';
      h += '<label class="f-label">路由段<i class="help-icon" data-help="REST 路由中的子路径片段。主实体无需配置（直接使用 BO 的 resourcePath），子实体默认使用 entity.code，可手动修改。||例：products、team-members">?</i></label>';
      h += '<input class="f-input" id="inp-routeSegment" data-path="content.entities.' + ei + '.routeSegment"'
        + ' value="' + escHtml(ent.routeSegment||ent.code) + '"'
        + ' placeholder="' + escHtml(ent.code||'子实体code') + '">';
      h += '</div></div>';
    }
    h += '</div>';
  } else {
    var ent2 = (formState.content.entities||[])[sel.ei];
    var attr = ent2 ? (ent2.attributes||[])[sel.ai] : null;
    if (!attr) return '<div class="ed-empty">属性不存在</div>';
    var sr = attr.semanticRole||'NORMAL';
    h += '<div style="font-weight:600;font-size:13px;margin-bottom:4px;color:var(--text-primary)">' + escHtml(attr.name||'(未命名)') + ' <span style="color:var(--text-tertiary);font-size:11px;font-family:monospace">' + escHtml(attr.code||'') + '</span></div>';
    h += '<div style="font-size:10px;color:var(--text-tertiary);margin-bottom:10px">属于 ' + escHtml(ent2.name||ent2.code||'?') + '</div>';
    var prefix = 'content.entities.' + sel.ei + '.attributes.' + sel.ai;
    var schema2 = g_schemaCache['MODEL'];
    var entSchema2 = schema2 ? ((schema2.properties.entities||{}).items||{}) : {};
    var attrSchema = ((entSchema2.properties||{}).attributes||{}).items || {};
    h += '<div class="form-grid">';
    h += schemaFieldHtml(attrSchema, 'semanticRole', sr, prefix, {});
    h += '</div>';
    var hiddenByRole = {
      TECHNICAL_ID:    ['crossBoRef','redundant','defaultValue','filterable','i18nKey'],
      BUSINESS_KEY:    ['crossBoRef','redundant','i18nKey'],
      NAME:            ['crossBoRef','isPk','redundant','defaultValue','precision','scale'],
      NORMAL:          ['crossBoRef','redundant'],
      CROSS_BO_REF:    ['isPk','redundant','defaultValue','filterable','i18nKey','precision','scale'],
      CROSS_BO_DISPLAY:['isPk','defaultValue','filterable','i18nKey','precision','scale'],
      PARENT_REF:      ['crossBoRef','isPk','redundant','defaultValue','filterable','i18nKey','precision','scale'],
      STATUS:          ['crossBoRef','isPk','redundant','i18nKey','precision','scale']
    };
    var hiddenFields = (hiddenByRole[sr] || []).slice();
    hiddenFields.push('semanticRole');
    if (attr.type !== 'DECIMAL') {
      hiddenFields.push('precision', 'scale');
    }
    h += '<div id="attr-detail-fields">';
    h += schemaObjectForm(attrSchema, attr, prefix, { hiddenFields: hiddenFields });
    h += '</div>';
    var showCrossBo = (sr === 'CROSS_BO_REF' || sr === 'CROSS_BO_DISPLAY');
    h += '<div id="row-crossBoRef" style="' + (showCrossBo ? '' : 'display:none') + '">';
    if (showCrossBo) {
      var crSchema = (attrSchema.properties.crossBoRef || {});
      var cr = attr.crossBoRef || {};
      var derivedFromRef = null;
      if (sr === 'CROSS_BO_DISPLAY' && (!cr.refBoCode || !cr.refFieldCode)) {
        (ent2.attributes||[]).forEach(function(a) {
          if (a.semanticRole === 'CROSS_BO_REF' && a.crossBoRef) {
            (a.crossBoRef.displayFields||[]).forEach(function(df) {
              if (df.localCode === attr.code) {
                derivedFromRef = { ref: a.crossBoRef, displayField: df };
              }
            });
          }
        });
        if (derivedFromRef) {
          cr = {
            refBoCode: derivedFromRef.ref.refBoCode || cr.refBoCode || '',
            refEntityCode: derivedFromRef.ref.refEntityCode || cr.refEntityCode || '',
            refFieldCode: derivedFromRef.displayField.refFieldCode || cr.refFieldCode || ''
          };
        }
      }
      h += '<div class="sub-sec xbo-sec"><div class="sub-sec-title xbo-title">🔗 跨对象引用配置' + (derivedFromRef ? ' <span style="font-size:10px;color:var(--text-tertiary);font-weight:400">(来自 CROSS_BO_REF)</span>' : '') + '</div>';
      var tgtBo = null;
      g_boList.forEach(function(b) { if (b.code === cr.refBoCode) tgtBo = b; });
      var tgtEnts = tgtBo ? (tgtBo.entities||[]) : [];
      h += '<div class="form-grid">';
      h += '<div class="field-group">';
      h += '<label class="f-label">目标BO Code<span class="req">*</span><i class="help-icon" data-help="引用的目标 BO 的 boCode，选项来自图谱中已加载的全部 BO。||例：opportunities → 引用商机">?</i></label>';
      h += '<select class="f-select" data-path="' + prefix + '.crossBoRef.refBoCode" id="sel-refBoCode">';
      h += '<option value="">-- 选择目标 BO --</option>';
      g_boList.forEach(function(b) {
        var sel3 = (cr.refBoCode === b.code) ? ' selected' : '';
        h += '<option value="' + escHtml(b.code) + '"' + sel3 + '>' + escHtml(b.name||b.code) + ' (' + escHtml(b.code) + ')</option>';
      });
      h += '</select></div>';
      var tgtPrimaryEnt = null;
      tgtEnts.forEach(function(e) {
        if (e.isPrimary && e.aggregateRole === 'ROOT') tgtPrimaryEnt = e;
      });
      if (!tgtPrimaryEnt && tgtEnts.length > 0) {
        tgtEnts.forEach(function(e) {
          if (e.aggregateRole === 'ROOT' && !tgtPrimaryEnt) tgtPrimaryEnt = e;
        });
      }
      var effEntityCode = cr.refEntityCode || (tgtPrimaryEnt ? tgtPrimaryEnt.code : '');
      h += '<div class="field-group">';
      h += '<label class="f-label">目标实体<i class="help-icon" data-help="目标 BO 中具体被引用的实体 code。留空则默认使用目标 BO 的主实体。||例：opportunity_header">?</i></label>';
      h += '<select class="f-select" data-path="' + prefix + '.crossBoRef.refEntityCode" id="sel-refEntityCode">';
      h += '<option value="">-- 默认主实体' + (tgtPrimaryEnt ? ' (' + escHtml(tgtPrimaryEnt.name||tgtPrimaryEnt.code) + ')' : '') + ' --</option>';
      var entMatched = false;
      tgtEnts.forEach(function(e) {
        var sel4 = (cr.refEntityCode === e.code) ? ' selected' : '';
        if (cr.refEntityCode === e.code) entMatched = true;
        h += '<option value="' + escHtml(e.code) + '"' + sel4 + '>' + escHtml(e.name||e.code) + ' (' + escHtml(e.code) + ')' + (e === tgtPrimaryEnt ? ' ★' : '') + '</option>';
      });
      if (cr.refEntityCode && !entMatched) {
        h += '<option value="' + escHtml(cr.refEntityCode) + '" selected>' + escHtml(cr.refEntityCode) + ' (当前值)</option>';
      }
      if (tgtEnts.length === 0 && cr.refBoCode) {
        h += '<option value="" disabled>⚠ 目标 BO 无实体数据</option>';
      }
      h += '</select></div></div>';
      var tgtAttrs = [];
      var tgtEffEnt = tgtEnts.find(function(e) { return e.code === effEntityCode; });
      if (tgtEffEnt) { tgtAttrs = tgtEffEnt.attributes || []; }
      h += '<div class="form-grid">';
      h += '<div class="field-group">';
      h += '<label class="f-label">目标字段<i class="help-icon" data-help="目标 BO 中被引用的字段 code，根据选定的目标 BO 和目标实体动态生成。||例：id、opportunity_no">?</i></label>';
      h += '<select class="f-select" data-path="' + prefix + '.crossBoRef.refFieldCode" id="sel-refFieldCode">';
      h += '<option value="">-- 选择目标字段 --</option>';
      var refMatched = false;
      tgtAttrs.forEach(function(a) {
        var sel5 = (cr.refFieldCode === a.code) ? ' selected' : '';
        if (cr.refFieldCode === a.code) refMatched = true;
        h += '<option value="' + escHtml(a.code) + '"' + sel5 + '>' + escHtml(a.name||a.code) + ' (' + escHtml(a.code) + ')</option>';
      });
      if (cr.refFieldCode && !refMatched) {
        h += '<option value="' + escHtml(cr.refFieldCode) + '" selected>' + escHtml(cr.refFieldCode) + ' (当前值)</option>';
      }
      if (tgtAttrs.length === 0 && cr.refBoCode) {
        h += '<option value="" disabled>⚠ 目标 BO 无属性数据</option>';
      }
      h += '</select></div></div>';
      h += schemaObjectForm(crSchema, cr, prefix + '.crossBoRef', { hiddenFields: ['refBoCode','refEntityCode','refFieldCode'] });
      h += '</div>';
    }
    h += '</div>';
  }
  return h;
}

// ── PICKER MODAL ─────────────────────────────────────────────
function openPicker(pickerType, existingKeys, onConfirm) {
  g_pickerCallback = onConfirm;
  g_pickerSelected = {};
  g_pickerExclude = {};
  existingKeys.forEach(function(k) { g_pickerExclude[k] = true; });
  var modal = document.getElementById('picker-modal');
  var title = {rule:'选择实体字段 → 添加规则',view:'选择实体字段 → 添加视图',operation:'选择实体 → 添加操作'}[pickerType] || '选择配置项';
  document.getElementById('picker-modal-title').textContent = title;
  buildPickerTree(pickerType);
  document.getElementById('picker-detail').innerHTML = '<div class="ed-empty">← 勾选左侧项目（可多选），已配置的置灰不可选</div>';
  document.getElementById('picker-selected-count').textContent = '已选 0 项';
  modal.classList.remove('hidden');
}

function closePickerModal() {
  document.getElementById('picker-modal').classList.add('hidden');
  g_pickerCallback = null;
  g_pickerSelected = {};
  g_pickerExclude = {};
}

function confirmPicker() {
  var sel = Object.keys(g_pickerSelected).filter(function(k) { return g_pickerSelected[k]; });
  if (sel.length === 0) return;
  if (g_pickerCallback) g_pickerCallback(sel);
  closePickerModal();
}

function buildPickerTree(pickerType) {
  var entities = formState.content.entities || [];
  var container = document.getElementById('picker-tree');
  var h = '';
  entities.forEach(function(ent, ei) {
    var ec = ent.entityCode || ('entity_' + ei);
    var en = ent.entityName || ec;
    h += '<div class="tree-node lv-ent" style="padding-left:8px"><span class="tree-arrow" id="pkar-' + ec + '" onclick="togglePickerEntity(\'' + escHtml(ec) + '\')">▶</span>';
    if (pickerType === 'operation') {
      var ekey = ec;
      var edisabled = g_pickerExclude[ekey];
      h += '<label class="picker-cb-lbl' + (edisabled?' disabled':'') + '" title="' + escHtml(en) + ' · ' + escHtml(ec) + '"><input type="checkbox" ' + (edisabled?'disabled':'') + ' onchange="togglePickerCheck(\'' + ekey + '\',this.checked)" onclick="event.stopPropagation()"><span class="tree-name">' + escHtml(en) + '</span><span class="tree-code">' + escHtml(ec) + '</span></label>';
      h += '</div>';
    } else {
      h += '<span class="tree-name" onclick="togglePickerEntity(\'' + escHtml(ec) + '\')">' + escHtml(en) + '</span><span class="tree-code">' + escHtml(ec) + '</span></div>';
      h += '<div id="pkar-list-' + escHtml(ec) + '" class="tree-children" style="display:none">';
      (ent.attributes || []).forEach(function(attr, ai) {
        var fc = attr.fieldCode || ('field_' + ai);
        var fn = attr.fieldName || fc;
        var fkey = ec + '.' + fc;
        var fdisabled = g_pickerExclude[fkey];
        h += '<div class="tree-node lv-attr" style="padding-left:28px"><label class="picker-cb-lbl' + (fdisabled?' disabled':'') + '" title="' + escHtml(ec) + '.' + escHtml(fc) + ' · ' + escHtml(fn) + '"><input type="checkbox" ' + (fdisabled?'disabled':'') + ' onchange="togglePickerCheck(\'' + fkey + '\',this.checked)" onclick="event.stopPropagation()"><span class="tree-name">' + escHtml(fn) + '</span><span class="tree-code">' + escHtml(fc) + '</span></label></div>';
      });
      h += '</div>';
    }
  });
  container.innerHTML = h;
}

function togglePickerEntity(ec) {
  var list = document.getElementById('pkar-list-' + ec);
  var arrow = document.getElementById('pkar-' + ec);
  if (!list || !arrow) return;
  if (list.style.display === 'none') { list.style.display = ''; arrow.classList.add('open'); }
  else { list.style.display = 'none'; arrow.classList.remove('open'); }
}

function togglePickerCheck(key, checked) {
  if (checked) { g_pickerSelected[key] = true; } else { delete g_pickerSelected[key]; }
  var count = Object.keys(g_pickerSelected).filter(function(k) { return g_pickerSelected[k]; }).length;
  document.getElementById('picker-selected-count').textContent = '已选 ' + count + ' 项';
}

// ═══════════════════════════════════════════════════ VALIDATION ═
function renderVALIDATION(c) {
  var schema = g_schemaCache['VALIDATION'];
  if (!schema) { loadSchema('VALIDATION').then(function(){ renderForm(); }); return secCard('✅ 字段校验规则','<div class="empty-hint">⏳ 加载…</div>'); }
  var itemSchema = (schema.properties.rules||{}).items || {};
  var rules = c.rules || [];
  var modelState = g_formStates['MODEL'];
  var modelContent = modelState ? modelState.content : {};
  var entities = modelContent.entities || [];
  var ruleMap = {};
  rules.forEach(function(r, i) {
    var key = (r.entityCode||'') + '.' + (r.fieldCode||'');
    ruleMap[key] = i;
  });
  var h = '<div class="section-card" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden"><div class="section-head" data-toggle="section"><span class="expand-icon open">▶</span><span class="section-head-title">✅ 字段校验规则 <span class="section-badge">' + rules.length + '</span></span></div><div class="section-body open" style="flex:1;display:flex;flex-direction:column"><div class="entity-split" style="flex:1;min-height:0">';
  h += '<div class="entity-tree" id="entity-tree">';
  entities.forEach(function(ent) {
    var hasRules = false;
    (ent.attributes||[]).forEach(function(a) {
      if (ruleMap[ent.code + '.' + a.code] !== undefined) hasRules = true;
    });
    h += '<div class="tree-node lv-ent" onclick="selectValTreeNode(event, this, \'entity\',\'' + escHtml(ent.code) + '\',\'\')"><span class="tn-arrow" id="vtna-' + escHtml(ent.code) + '">▶</span><span class="tn-name">' + escHtml(ent.name||ent.code) + '</span><span class="tn-code">' + escHtml(ent.code) + '</span>' + (hasRules ? '<span class="tn-badge" style="background:rgba(16,185,129,.15);color:#34d399">✓</span>' : '') + '</div>';
    h += '<div id="vtna-list-' + escHtml(ent.code) + '" style="display:none">';
    (ent.attributes||[]).forEach(function(attr) {
      var ruleIdx = ruleMap[ent.code + '.' + attr.code];
      var hasRule = ruleIdx !== undefined;
      var dirtyKey = ent.code + '.' + attr.code;
      var isDirty = g_valDirty[dirtyKey];
      var statusHtml;
      if (hasRule) {
        if (isDirty) { statusHtml = '<span class="tn-badge" style="background:rgba(245,158,11,.15);color:#fbbf24">已暂存</span>'; }
        else { statusHtml = '<span class="tn-badge" style="background:rgba(16,185,129,.15);color:#34d399">已保存</span>'; }
      } else {
        if (isDirty) { statusHtml = '<span class="tn-badge" style="background:rgba(239,68,68,.15);color:#fca5a5">已重置</span>'; }
        else { statusHtml = '<span style="font-size:9px;color:var(--text-tertiary)">未配置</span>'; }
      }
      h += '<div class="tree-node lv-attr" data-ent="' + escHtml(ent.code) + '" data-field="' + escHtml(attr.code) + '" onclick="selectValTreeNode(event, this, \'attr\',\'' + escHtml(ent.code) + '\',\'' + escHtml(attr.code) + '\')"><span class="tn-name">' + escHtml(attr.name||attr.code) + '</span><span class="tn-code">' + escHtml(attr.code) + '</span>' + statusHtml + '</div>';
    });
    h += '</div>';
  });
  if (entities.length === 0) { h += '<div style="padding:12px;font-size:11px;color:var(--text-tertiary)">请在模型 Tab 中先添加实体和属性</div>'; }
  h += '</div>';
  h += '<div class="entity-detail" id="entity-detail">';
  h += renderValDetail(g_valTreeSel, rules, ruleMap, itemSchema, entities);
  h += '</div></div></div></div>';
  return h;
}

function selectValTreeNode(e, el, type, entityCode, fieldCode) {
  e.stopPropagation();
  if (type === 'entity') {
    var list = document.getElementById('vtna-list-' + entityCode);
    var arrow = document.getElementById('vtna-' + entityCode);
    if (list && arrow) {
      var isOpen = list.style.display !== 'none';
      if (isOpen) { list.style.display = 'none'; arrow.classList.remove('open'); }
      else { list.style.display = ''; arrow.classList.add('open'); }
    }
  }
  g_valTreeSel = {type: type, entityCode: entityCode, fieldCode: fieldCode};
  applyValTreeSelection();
  var detail = document.getElementById('entity-detail');
  var schema = g_schemaCache['VALIDATION'];
  var itemSchema = (schema ? (schema.properties.rules||{}).items : {}) || {};
  var entities = ((g_formStates['MODEL']||{}).content||{}).entities || [];
  if (detail) detail.innerHTML = renderValDetail(g_valTreeSel, formState.content.rules||[], {}, itemSchema, entities);
  bindAllEvents();
}

function applyValTreeSelection() {
  document.querySelectorAll('#entity-tree .tree-node.selected').forEach(function(n) { n.classList.remove('selected'); });
  if (!g_valTreeSel || g_valTreeSel.type !== 'attr') return;
  var sel = document.querySelector('#entity-tree .tree-node.lv-attr[data-ent="' + g_valTreeSel.entityCode + '"][data-field="' + g_valTreeSel.fieldCode + '"]');
  if (sel) {
    sel.classList.add('selected');
    var parentDiv = document.getElementById('vtna-list-' + g_valTreeSel.entityCode);
    if (parentDiv) parentDiv.style.display = '';
    var arrow = document.getElementById('vtna-' + g_valTreeSel.entityCode);
    if (arrow) arrow.classList.add('open');
  }
}

function renderValDetail(sel, rules, ruleMap, itemSchema, entities) {
  if (!sel || sel.type !== 'attr') return '<div class="ed-empty">← 从左侧选择字段查看或编辑校验规则</div>';
  var rulesArr = rules;
  var lookup = {};
  rulesArr.forEach(function(r, i) { lookup[(r.entityCode||'') + '.' + (r.fieldCode||'')] = i; });
  var key = sel.entityCode + '.' + sel.fieldCode;
  var ridx = lookup[key];
  var isNew = (ridx === undefined);
  var ruleIdx = isNew ? rulesArr.length : ridx;
  var rule = isNew
    ? { entityCode:sel.entityCode, fieldCode:sel.fieldCode, required:false, min:null, max:null, pattern:'', enum:[], unique:false, message:'' }
    : rulesArr[ridx];
  var h = '<div style="margin-bottom:12px;display:flex;gap:6px;align-items:center">';
  if (isNew) {
    h += '<button class="btn btn-primary" onclick="event.stopPropagation();commitValRule(\'' + escHtml(sel.entityCode) + '\',\'' + escHtml(sel.fieldCode) + '\')" style="font-size:11px">💾 暂存</button>';
  } else {
    h += '<button class="btn btn-primary" onclick="event.stopPropagation();g_valDirty[\'' + escHtml(key) + '\']=true;updatePreview();setStatus(\'✅ 已暂存\',\'ok\')" style="font-size:11px">💾 暂存</button>';
    h += '<button class="btn btn-danger" onclick="event.stopPropagation();if(confirm(\'确定重置该字段的校验规则？\')){formState.content.rules.splice(' + ridx + ',1);g_valDirty[\'' + escHtml(key) + '\']=true;g_valTreeSel=null;renderForm();updatePreview();}" style="font-size:11px">🔄 重置</button>';
  }
  h += '</div>';
  var prefix = 'content.rules.' + ruleIdx;
  if (isNew) {
    if (!formState._tempValRule) formState._tempValRule = {};
    formState._tempValRule.rule = rule;
    prefix = '_tempValRule.rule';
  }
  h += schemaObjectForm(itemSchema, rule, prefix, {hiddenFields:['entityCode','fieldCode','enum']});
  h += '<div class="f-label">枚举值 <span class="hint">(格式: value:label, 逗号分隔)</span></div>';
  var enumStr = '';
  if (rule.enum && rule.enum.length) {
    enumStr = rule.enum.map(function(e) { return (typeof e === 'object') ? (e.value + ':' + e.label) : e; }).join(',');
  }
  h += '<input class="f-input" data-path="' + prefix + '.enum" value="' + escHtml(enumStr) + '" placeholder="val1:标签1,val2:标签2">';
  return h;
}

function commitValRule(entityCode, fieldCode) {
  if (!formState._tempValRule || !formState._tempValRule.rule) return;
  var rule = formState._tempValRule.rule;
  if (!formState.content.rules) formState.content.rules = [];
  var found = -1;
  formState.content.rules.forEach(function(r, i) {
    if ((r.entityCode||'') + '.' + (r.fieldCode||'') === entityCode + '.' + fieldCode) found = i;
  });
  if (found >= 0) { formState.content.rules[found] = rule; }
  else { formState.content.rules.push(Object.assign({}, rule)); }
  formState._tempValRule = null;
  g_valTreeSel = {type:'attr', entityCode: entityCode, fieldCode: fieldCode};
  g_valDirty[entityCode + '.' + fieldCode] = true;
  renderForm(); updatePreview();
  setStatus('✅ 已暂存（等待保存到项目）', 'ok');
}

// ════════════════════════════════════════════════════ SECURITY ═
var g_fsecTreeSel = null;
var g_fsecDirty = {};
var g_fsecEverStashed = {};
var g_rowSecDirty = false;

function toggleFsecEntity(ec) {
  var list = document.getElementById('fseca-list-' + ec);
  var arrow = document.getElementById('fseca-' + ec);
  if (!list || !arrow) return;
  if (list.style.display === 'none') { list.style.display = ''; arrow.classList.add('open'); }
  else { list.style.display = 'none'; arrow.classList.remove('open'); }
}

function selectFsec(idx) { g_fsecTreeSel = idx; renderForm(); updatePreview(); }

function renderFsecDetail(selIdx, fsecList, itemSchema, entNameMap, attrNameMap) {
  if (selIdx === null || selIdx === undefined) return '<div class="ed-empty">← 从左侧选择字段查看或编辑</div>';
  var i = selIdx;
  if (i < 0 || i >= fsecList.length) return '<div class="ed-empty">⚠ 索引无效</div>';
  var fs = fsecList[i];
  var ec = fs.entityCode || '?', fc = fs.fieldCode || '?';
  var eName = (entNameMap||{})[ec] || ec;
  var fName = (attrNameMap||{})[ec + '.' + fc] || fc;
  var h = '<div class="detail-panel">';
  h += '<div class="detail-head" style="display:flex;align-items:center;gap:8px"><span class="detail-title">' + escHtml(eName) + ' · ' + escHtml(fName) + '</span>';
  h += '<button class="btn btn-primary" onclick="stashFsec(' + i + ')" style="font-size:11px;margin-left:auto">💾 暂存</button>';
  h += '</div><div class="detail-body">';
  h += schemaObjectForm(itemSchema, fs, 'content.fieldSecurity.'+i, {});
  h += '</div></div>';
  return h;
}

function openFsecPicker() {
  var modelState = g_formStates['MODEL'];
  var entities = (modelState ? modelState.content.entities : []) || [];
  var rootEnt = null;
  entities.forEach(function(e) { if (e.aggregateRole === 'ROOT' && e.isPrimary) rootEnt = e; });
  if (!rootEnt) entities.forEach(function(e) { if (e.aggregateRole === 'ROOT') rootEnt = e; });
  g_vpSelEnt = rootEnt ? rootEnt.code : '';
  g_vpSelected = {};
  g_vpExclude = {};
  (formState.content.fieldSecurity||[]).forEach(function(fs) {
    if (fs.entityCode && fs.fieldCode) g_vpExclude[fs.entityCode + '.' + fs.fieldCode] = true;
  });
  g_vpConfirmAction = 'fsec';
  document.getElementById('picker-modal-title').textContent = '🔒 选择字段安全';
  var modal = document.getElementById('view-picker-modal');
  var confirmBtn = modal.querySelector('.modal-footer .btn-primary');
  if (confirmBtn) confirmBtn.setAttribute('onclick', 'confirmFsecPicker()');
  var titleEl = modal.querySelector('.modal-header h3');
  if (titleEl) titleEl.textContent = '🔒 选择字段安全';
  buildViewPickerTree();
  buildViewPickerTable();
  buildViewPickerSelected();
  modal.classList.remove('hidden');
}

function confirmFsecPicker() {
  var keys = Object.keys(g_vpSelected).filter(function(k) { return g_vpSelected[k]; });
  if (keys.length === 0) { closeViewPicker(); return; }
  if (!formState.content.fieldSecurity) formState.content.fieldSecurity = [];
  keys.forEach(function(key) {
    var parts = key.split('.');
    var ec = parts[0], fc = parts.slice(1).join('.');
    var exists = false;
    (formState.content.fieldSecurity||[]).forEach(function(fs) {
      if (fs.entityCode === ec && fs.fieldCode === fc) exists = true;
    });
    if (!exists) {
      formState.content.fieldSecurity.push({
        entityCode: ec, fieldCode: fc,
        fieldControl: 'OPEN', privacyClass: 'PUBLIC', reason: ''
      });
    }
  });
  closeViewPicker();
  g_fsecTreeSel = (formState.content.fieldSecurity||[]).length - 1;
  renderForm(); updatePreview();
  setStatus('✅ 已添加 ' + keys.length + ' 个字段安全', 'ok');
}

function stashFsec(idx) {
  g_fsecDirty[idx] = true;
  g_fsecEverStashed[idx] = true;
  updatePreview();
  renderForm();
  g_fsecTreeSel = idx;
  setStatus('✅ 已暂存字段安全 #' + (idx+1), 'ok');
}

function deleteFsec() {
  if (g_fsecTreeSel === null || g_fsecTreeSel === undefined) return;
  var i = g_fsecTreeSel;
  var fsecList = formState.content.fieldSecurity || [];
  if (i < 0 || i >= fsecList.length) return;
  var fs = fsecList[i];
  if (!confirm('确定删除字段安全 "' + (fs.entityCode||'?') + '.' + (fs.fieldCode||'?') + '"？')) return;
  fsecList.splice(i, 1);
  delete g_fsecDirty[i]; delete g_fsecEverStashed[i];
  var newDirty = {}, newEver = {};
  Object.keys(g_fsecDirty).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newDirty[ki-1] = true; else if (ki < i) newDirty[ki] = true;
  });
  Object.keys(g_fsecEverStashed).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newEver[ki-1] = true; else if (ki < i) newEver[ki] = true;
  });
  g_fsecDirty = newDirty; g_fsecEverStashed = newEver;
  g_fsecTreeSel = null;
  renderForm(); updatePreview();
}

function initFsecEverStashed(content) {
  (content.fieldSecurity||[]).forEach(function(r, i) { g_fsecEverStashed[i] = true; });
}

function renderSECURITY(c) {
  var schema = g_schemaCache['SECURITY'];
  if (!schema) { loadSchema('SECURITY').then(function(){ renderForm(); }); return secCard('🛡️ 行级安全','<div class="empty-hint">⏳ 加载…</div>'); }
  var h = '';
  var rs = c.rowSecurity||{};
  var rsSchema = schema.properties.rowSecurity || {};
  h += '<div style="display:flex;gap:10px;align-items:stretch;flex:1;min-height:0">';
  h += '<div class="section-card" style="flex:4;min-width:0;display:flex;flex-direction:column"><div class="section-head" data-toggle="section"><span class="expand-icon open">▶</span><span class="section-head-title">🛡️ 行级安全</span></div><div class="section-body open" style="flex:1;display:flex;flex-direction:column">';
  h += schemaFieldHtml(rsSchema, 'fallbackScope', rs.fallbackScope, 'content.rowSecurity', {});
  var modelState = g_formStates['MODEL'];
  var modelEntities = (modelState ? modelState.content.entities : []) || [];
  var ee = rs.entriesByEntity||{};
  h += '<div class="sub-sec"><div class="sub-sec-title">行级控制字段映射（实体 → 受控字段列表）</div>';
  h += '<div class="shuttle-wrap" id="shuttle-wrap">';
  h += '<div class="shuttle-panel"><div class="shuttle-panel-title">📋 可选实体字段</div><div class="shuttle-panel-body" id="shuttle-left">';
  modelEntities.forEach(function(ent) {
    var ec = ent.code, en = ent.name || ec;
    h += '<div class="tree-node lv-ent"><span class="tree-arrow open" id="sha-' + escHtml(ec) + '" onclick="toggleShuttleEntity(\'' + escHtml(ec) + '\')">▶</span>';
    h += '<span class="tree-name" onclick="toggleShuttleEntity(\'' + escHtml(ec) + '\')">' + escHtml(en) + '</span></div>';
    h += '<div id="sha-list-' + escHtml(ec) + '" style="display:block">';
    (ent.attributes||[]).forEach(function(attr) {
      var fc = attr.code, fn = attr.name || fc;
      var key = ec + '.' + fc;
      var inRight = ee[ec] && ee[ec].indexOf(fc) >= 0;
      if (inRight) return;
      h += '<div class="tree-node lv-attr shuttle-left-item" data-shuttle-key="' + escHtml(key) + '">';
      h += '<input type="checkbox" class="shuttle-left-cb" onclick="event.stopPropagation()">';
      h += '<span class="tree-name">' + escHtml(fn) + '</span></div>';
    });
    h += '</div>';
  });
  h += '</div></div>';
  h += '<div class="shuttle-btns">';
  h += '<button class="shuttle-btn" onclick="shuttleAdd()">→ 添加</button>';
  h += '<button class="shuttle-btn" onclick="shuttleRemove()">← 移除</button>';
  h += '<button class="shuttle-btn" style="color:#34d399;border-color:rgba(16,185,129,.3)" onclick="stashRowSec()">💾 暂存</button>';
  var rsStatus = g_rowSecDirty ? '<span style="font-size:9px;color:#fbbf24;margin-top:6px;text-align:center">已修改</span>' : (g_rowSecEverStashed ? '<span style="font-size:9px;color:#34d399;margin-top:6px;text-align:center">已暂存</span>' : '');
  if (rsStatus) h += rsStatus;
  h += '</div>';
  var fieldNameMap = {};
  modelEntities.forEach(function(ent) {
    (ent.attributes||[]).forEach(function(attr) {
      fieldNameMap[ent.code + '.' + attr.code] = attr.name || attr.code;
    });
  });
  h += '<div class="shuttle-panel"><div class="shuttle-panel-title">✅ 已选映射</div><div class="shuttle-panel-body" id="shuttle-right">';
  Object.keys(ee).forEach(function(ec) {
    var fields = ee[ec] || [];
    var entName = ec;
    modelEntities.forEach(function(e) { if (e.code === ec) entName = e.name || ec; });
    h += '<div class="tree-node lv-ent"><span class="tree-arrow open" id="shr-' + escHtml(ec) + '" onclick="toggleShuttleRightEntity(\'' + escHtml(ec) + '\')">▶</span>';
    h += '<span class="tree-name" onclick="toggleShuttleRightEntity(\'' + escHtml(ec) + '\')">' + escHtml(entName) + '</span>';
    h += '<span class="tree-badge" style="background:rgba(156,163,175,.08);color:#71717a">' + fields.length + '</span></div>';
    h += '<div id="shr-list-' + escHtml(ec) + '" style="display:block">';
    fields.forEach(function(fc) {
      var key = ec + '.' + fc;
      var fName = fieldNameMap[key] || fc;
      h += '<div class="tree-node lv-attr shuttle-right-item" data-shuttle-key="' + escHtml(key) + '">';
      h += '<input type="checkbox" class="shuttle-right-cb" onclick="event.stopPropagation()">';
      h += '<span class="tree-name">' + escHtml(fName) + '</span></div>';
    });
    h += '</div>';
  });
  if (Object.keys(ee).length === 0) {
    h += '<div style="padding:16px;text-align:center;color:var(--text-tertiary);font-size:11px">从左侧选择字段添加</div>';
  }
  h += '</div></div></div></div></div></div>';

  var fsecSchema = schema.properties.fieldSecurity || {};
  var itemSchema = fsecSchema.items || {};
  var fsecList = c.fieldSecurity || [];
  var entNameMap2 = {}, attrNameMap2 = {};
  modelEntities.forEach(function(ent) {
    entNameMap2[ent.code] = ent.name || ent.code;
    (ent.attributes||[]).forEach(function(attr) {
      attrNameMap2[ent.code + '.' + attr.code] = attr.name || attr.code;
    });
  });
  h += '<div class="section-card" style="flex:6;min-width:0;display:flex;flex-direction:column"><div class="section-head" data-toggle="section"><span class="expand-icon open">▶</span><span class="section-head-title">🔒 字段级安全 <span class="section-badge">' + fsecList.length + '</span></span></div><div class="section-body open" style="flex:1;display:flex;flex-direction:column"><div class="tree-detail-layout" style="flex:1;min-height:0">';
  h += '<div class="tree-left-panel" style="flex:4;min-width:200px">';
  h += '<div class="tree-toolbar"><span class="tree-toolbar-title">🔒 已配置字段</span>';
  h += '<div class="tree-toolbar-actions">';
  h += '<button class="tb-btn tb-btn-add" onclick="openFsecPicker()" title="添加字段安全">+ 添加</button>';
  h += '<button class="tb-btn tb-btn-del" onclick="deleteFsec()" title="删除字段安全">🗑</button>';
  h += '</div></div>';
  h += '<div class="tree-scroll" id="fsec-tree">';
  if (fsecList.length === 0) {
    h += '<div class="tree-empty">暂无配置，点击 [+ 添加] 选择字段</div>';
  } else {
    var fsecGroups = {};
    fsecList.forEach(function(fs, i) {
      var ec = fs.entityCode || '__other__';
      if (!fsecGroups[ec]) fsecGroups[ec] = [];
      fsecGroups[ec].push({idx: i, fs: fs});
    });
    Object.keys(fsecGroups).forEach(function(ec) {
      var items = fsecGroups[ec];
      var eName = entNameMap2[ec] || ec;
      h += '<div class="tree-node lv-ent" style="padding-left:8px;font-weight:500">';
      h += '<span class="tree-arrow open" id="fseca-' + escHtml(ec) + '" onclick="toggleFsecEntity(\'' + escHtml(ec) + '\')">▶</span>';
      h += '<span class="tree-name" onclick="toggleFsecEntity(\'' + escHtml(ec) + '\')">' + escHtml(eName) + '</span>';
      h += '<span class="tree-code">' + escHtml(ec) + '</span>';
      h += '<span class="tree-badge" style="background:rgba(156,163,175,.08);color:#71717a">' + items.length + '</span></div>';
      h += '<div id="fseca-list-' + escHtml(ec) + '" style="display:block">';
      items.forEach(function(item) {
        var i2 = item.idx, fs2 = item.fs;
        var fName2 = attrNameMap2[ec + '.' + fs2.fieldCode] || fs2.fieldCode || '?';
        var isSel = g_fsecTreeSel === i2;
        var fc = fs2.fieldControl||'OPEN';
        var fcColor = fc==='OPEN'?'#10b981':fc==='HIDDEN'?'#ef4444':'#f59e0b';
        var isDirty = g_fsecDirty[i2];
        var statusBadge = '';
        if (isDirty) { statusBadge = '<span class="tree-badge" style="background:rgba(245,158,11,.15);color:#fbbf24">已暂存</span>'; }
        else if (g_fsecEverStashed[i2]) { statusBadge = '<span class="tree-badge" style="background:rgba(16,185,129,.15);color:#34d399">已保存</span>'; }
        h += '<div class="tree-node lv-attr' + (isSel?' selected':'') + '" id="fsec-node-' + i2 + '" onclick="selectFsec(' + i2 + ')">';
        h += '<span class="tree-arrow-spacer"></span>';
        h += '<span class="tree-name">' + escHtml(fName2) + '</span>';
        h += '<span class="tree-code">' + escHtml(fs2.fieldCode||'?') + '</span>';
        h += '<span class="tree-badge" style="background:rgba(' + (fc==='OPEN'?'16,185,129':fc==='HIDDEN'?'239,68,68':'245,158,11') + ',.15);color:' + fcColor + '">' + enumLabel(fc) + '</span>';
        h += statusBadge;
        h += '</div>';
      });
      h += '</div>';
    });
  }
  h += '</div></div>';
  h += '<div class="tree-right-panel" id="fsec-detail" style="flex:6">';
  h += renderFsecDetail(g_fsecTreeSel, fsecList, itemSchema, entNameMap2, attrNameMap2);
  h += '</div></div></div></div></div>';
  return h;
}

// ═══════════════════════════════════════════════════════ RULE ══
var g_ruleTreeSel = null;
var g_ruleDirty = {};
var g_ruleEverStashed = {};

function renderRULE(c) {
  var rules = c.rules || [];
  var schema = g_schemaCache['RULE'];
  if (!schema) { loadSchema('RULE').then(function(){ renderForm(); }); return secCard('📜 业务规则','<div class="empty-hint">⏳ 加载…</div>'); }
  var itemSchema = ((schema.$defs||{}).Rule) || ((schema.properties.rules||{}).items) || {};
  var h = '<div class="tree-detail-layout">';
  h += '<div class="tree-left-panel">';
  h += '<div class="tree-toolbar"><span class="tree-toolbar-title">📜 已配置规则</span>';
  h += '<div class="tree-toolbar-actions">';
  h += '<button class="tb-btn tb-btn-add" onclick="addRule()" title="添加规则">+ 添加</button>';
  h += '<button class="tb-btn tb-btn-del" onclick="deleteRuleTree()" title="删除规则">🗑</button>';
  h += '</div></div>';
  h += '<div class="tree-scroll" id="rule-tree">';
  if (rules.length === 0) {
    h += '<div class="tree-empty">暂无规则，点击 [+ 添加] 新建规则</div>';
  } else {
    rules.forEach(function(r, i) {
      var sev = r.severity||'ERROR';
      var sevColor = sev==='ERROR'?'#fca5a5':sev==='WARN'?'#fcd34d':'#60a5fa';
      var isSel = g_ruleTreeSel && g_ruleTreeSel.type==='rule' && g_ruleTreeSel.idx===i;
      var isDirty = g_ruleDirty[i];
      var statusBadge = '';
      if (isDirty) { statusBadge = '<span class="tree-badge" style="background:rgba(245,158,11,.15);color:#fbbf24">已暂存</span>'; }
      else if (g_ruleEverStashed[i]) { statusBadge = '<span class="tree-badge" style="background:rgba(16,185,129,.15);color:#34d399">已保存</span>'; }
      h += '<div class="tree-node' + (isSel?' selected':'') + '" id="rule-node-' + i + '" data-rule-idx="' + i + '" onclick="selectRuleTreeNode(' + i + ')" title="' + escHtml(r.name||'(未命名)') + ' · ' + escHtml(r.code||'') + ' · ' + enumLabel(sev) + '">';
      h += '<span class="tree-arrow-spacer"></span>';
      h += '<span class="tree-name">' + escHtml(r.name||'(未命名)') + '</span>';
      h += '<span class="tree-code">' + escHtml(r.code||'') + '</span>';
      h += '<span class="tree-badge" style="background:rgba(' + (sev==='ERROR'?'239,68,68':sev==='WARN'?'245,158,11':'59,130,246') + ',.15);color:' + sevColor + '">' + enumLabel(sev) + '</span>';
      h += statusBadge;
      h += '</div>';
    });
  }
  h += '</div></div>';
  h += '<div class="tree-detail-resize" onmousedown="startTreeDetailResize(event)"></div>';
  h += '<div class="tree-right-panel" id="rule-detail">';
  h += renderRuleDetail(g_ruleTreeSel, rules, itemSchema);
  h += '</div></div>';
  return h;
}

function selectRuleTreeNode(idx) { g_ruleTreeSel = {type:'rule', idx: idx}; renderForm(); updatePreview(); }

function renderRuleDetail(sel, rules, itemSchema) {
  if (!sel || sel.type !== 'rule') return '<div class="ed-empty">← 从左侧选择规则查看或编辑</div>';
  var i = sel.idx;
  if (i < 0 || i >= rules.length) return '<div class="ed-empty">⚠ 规则索引无效</div>';
  var r = rules[i];
  var h = '<div class="detail-panel">';
  h += '<div class="detail-head" style="display:flex;align-items:center;gap:8px"><span class="detail-title">规则 ' + (i+1) + '</span>';
  h += '<button class="btn btn-primary" onclick="stashRule(' + i + ')" style="font-size:11px;margin-left:auto">💾 暂存</button>';
  h += '</div><div class="detail-body">';
  h += schemaObjectForm(itemSchema, r, 'content.rules.'+i, {hiddenFields:['expression','action']});
  h += '<div class="f-label" style="margin-top:6px">表达式</div><textarea class="f-textarea" id="rule-expr-' + i + '" data-path="content.rules.'+i+'.expression" rows="3" oninput="syncRuleTreeNode(' + i + ')">' + escHtml(r.expression||'') + '</textarea>';
  h += '<div class="f-label" style="margin-top:6px">动作</div><textarea class="f-textarea" id="rule-act-' + i + '" data-path="content.rules.'+i+'.action" rows="3">' + escHtml(r.action||'') + '</textarea>';
  if (r.scope==='CROSS_BO_REF'||r.scope==='CROSS_BO') {
    var crSchema = (itemSchema.properties.crossBoRef || {});
    var cr = r.crossBoRef||{};
    h += '<div class="sub-sec xbo-sec"><div class="sub-sec-title xbo-title">🔗 跨对象引用</div>';
    h += schemaObjectForm(crSchema, cr, 'content.rules.'+i+'.crossBoRef', {});
    h += '</div>';
  }
  h += '</div></div>';
  return h;
}

function addRule() {
  if (!formState.content.rules) formState.content.rules = [];
  formState.content.rules.push({
    code:'RULE_' + (formState.content.rules.length + 1),
    name:'新规则', entityCode:'', fieldCode:'',
    scope:'FIELD', severity:'ERROR', expression:'', action:''
  });
  var idx = formState.content.rules.length - 1;
  g_ruleTreeSel = {type:'rule', idx: idx};
  renderForm(); updatePreview();
  setStatus('✅ 已创建新规则，请编辑后点击暂存', 'ok');
}

function stashRule(idx) {
  g_ruleDirty[idx] = true;
  g_ruleEverStashed[idx] = true;
  updatePreview();
  renderForm();
  g_ruleTreeSel = {type:'rule', idx: idx};
  setStatus('✅ 已暂存规则 #' + (idx+1) + '（等待保存到项目）', 'ok');
}

function initRuleEverStashed(content) {
  (content.rules||[]).forEach(function(r, i) { g_ruleEverStashed[i] = true; });
}

function deleteRuleTree() {
  if (!g_ruleTreeSel || g_ruleTreeSel.type !== 'rule') return;
  var i = g_ruleTreeSel.idx;
  var rules = formState.content.rules || [];
  if (i < 0 || i >= rules.length) return;
  var r = rules[i];
  if (!confirm('确定删除规则 "' + (r.name||'(未命名)') + '"？')) return;
  rules.splice(i, 1);
  delete g_ruleDirty[i]; delete g_ruleEverStashed[i];
  var newDirty = {}, newEver = {};
  Object.keys(g_ruleDirty).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newDirty[ki-1] = true; else if (ki < i) newDirty[ki] = true;
  });
  Object.keys(g_ruleEverStashed).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newEver[ki-1] = true; else if (ki < i) newEver[ki] = true;
  });
  g_ruleDirty = newDirty; g_ruleEverStashed = newEver;
  g_ruleTreeSel = null;
  renderForm(); updatePreview();
}

function syncRuleTreeNode(idx) {
  var node = document.getElementById('rule-node-' + idx);
  if (!node) return;
  var r = (formState.content.rules||[])[idx];
  if (!r) return;
  var nameEl = node.querySelector('.tree-name');
  if (nameEl) nameEl.textContent = r.name || '(未命名)';
  var codeEl = node.querySelector('.tree-code');
  if (codeEl) codeEl.textContent = r.code || '';
  var sev = r.severity||'ERROR';
  var sevColor = sev==='ERROR'?'#fca5a5':sev==='WARN'?'#fcd34d':'#60a5fa';
  var badges = node.querySelectorAll('.tree-badge');
  if (badges.length > 0) {
    badges[0].style.background = 'rgba(' + (sev==='ERROR'?'239,68,68':sev==='WARN'?'245,158,11':'59,130,246') + ',.15)';
    badges[0].style.color = sevColor;
    badges[0].textContent = enumLabel(sev);
  }
}

// ════════════════════════════════════════════════════════ VIEW ══
var g_viewTreeSel = null;
var g_viewConfigCollapsed = true;
var g_viewDirty = {};
var g_viewEverStashed = {};

function renderVIEW(c) {
  var fieldViews = c.fieldViews || [];
  var schema = g_schemaCache['VIEW'];
  if (!schema) { loadSchema('VIEW').then(function(){ renderForm(); }); return secCard('📋 列表视图','<div class="empty-hint">⏳ 加载…</div>'); }
  var itemSchema = (schema.properties.fieldViews||{}).items || {};
  var modelState = g_formStates['MODEL'];
  var modelContent = modelState ? modelState.content : {};
  var entities = modelContent.entities || [];
  var entNameMap = {}, attrNameMap = {};
  entities.forEach(function(ent) {
    entNameMap[ent.code] = ent.name || ent.code;
    (ent.attributes||[]).forEach(function(attr) {
      attrNameMap[ent.code + '.' + attr.code] = attr.name || attr.code;
    });
  });
  var groups = {};
  fieldViews.forEach(function(fv, i) {
    var ec = fv.entityCode || '__other__';
    if (!groups[ec]) groups[ec] = [];
    groups[ec].push({idx: i, fv: fv});
  });
  var groupKeys = Object.keys(groups);
  var h = '';
  var lvSchema = schema.properties.listViewConfig || {};
  var lv = c.listViewConfig||{};
  h += schemaSection(lvSchema, lv, 'content.listViewConfig', '📋 列表视图配置', {collapsed: g_viewConfigCollapsed});
  h += '<div class="section-card" style="margin-top:12px;flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden">';
  h += '<div class="tree-detail-layout" style="border-radius:0">';
  h += '<div class="tree-left-panel">';
  h += '<div class="tree-toolbar"><span class="tree-toolbar-title">🖥️ 字段视图</span>';
  h += '<div class="tree-toolbar-actions">';
  h += '<button class="tb-btn tb-btn-add" onclick="addViewViaPicker()" title="添加视图">+ 添加</button>';
  h += '<button class="tb-btn tb-btn-del" onclick="deleteViewTree()" title="删除视图">🗑</button>';
  h += '</div></div>';
  h += '<div class="tree-scroll" id="view-tree">';
  if (fieldViews.length === 0) {
    h += '<div class="tree-empty">暂无视图，点击 [+ 添加] 选择字段</div>';
  } else {
    groupKeys.forEach(function(ec) {
      var items = groups[ec];
      var eName = entNameMap[ec] || ec;
      var isExpanded = true;
      h += '<div class="tree-node lv-ent" style="padding-left:8px;font-weight:500">';
      h += '<span class="tree-arrow' + (isExpanded?' open':'') + '" id="vwa-' + escHtml(ec) + '" onclick="toggleViewEntity(\'' + escHtml(ec) + '\')">▶</span>';
      h += '<span class="tree-name" onclick="toggleViewEntity(\'' + escHtml(ec) + '\')">' + escHtml(eName) + '</span>';
      h += '<span class="tree-code">' + escHtml(ec) + '</span>';
      h += '<span class="tree-badge" style="background:rgba(156,163,175,.08);color:#71717a">' + items.length + '</span></div>';
      h += '<div id="vwa-list-' + escHtml(ec) + '" style="display:' + (isExpanded?'':'none') + '">';
      items.forEach(function(item) {
        var i = item.idx, fv = item.fv;
        var fName = attrNameMap[ec + '.' + fv.fieldCode] || fv.fieldCode || '?';
        var isSel = g_viewTreeSel && g_viewTreeSel.type==='view' && g_viewTreeSel.idx===i;
        var isDirty = g_viewDirty[i];
        var statusBadge = '';
        if (isDirty) { statusBadge = '<span class="tree-badge" style="background:rgba(245,158,11,.15);color:#fbbf24">已暂存</span>'; }
        else if (g_viewEverStashed[i]) { statusBadge = '<span class="tree-badge" style="background:rgba(16,185,129,.15);color:#34d399">已保存</span>'; }
        h += '<div class="tree-node lv-attr' + (isSel?' selected':'') + '" id="view-node-' + i + '" data-view-idx="' + i + '" onclick="selectViewTreeNode(' + i + ')" title="' + escHtml(eName) + ' · ' + escHtml(fName) + ' · ' + enumLabel(fv.formType||'INPUT') + (fv.hidden?' · 隐藏':'') + '">';
        h += '<span class="tree-arrow-spacer"></span>';
        h += '<span class="tree-name">' + escHtml(fName) + '</span>';
        h += '<span class="tree-code">' + escHtml(fv.fieldCode||'?') + '</span>';
        h += '<span class="tree-badge" style="background:rgba(156,163,175,.15);color:#9ca3af">' + enumLabel(fv.formType||'INPUT') + '</span>';
        if (fv.hidden) h += '<span class="tree-badge" style="background:rgba(239,68,68,.15);color:#fca5a5">隐藏</span>';
        h += statusBadge;
        h += '</div>';
      });
      h += '</div>';
    });
  }
  h += '</div></div>';
  h += '<div class="tree-detail-resize" onmousedown="startTreeDetailResize(event)"></div>';
  h += '<div class="tree-right-panel" id="view-detail">';
  h += renderViewDetail(g_viewTreeSel, fieldViews, itemSchema, entNameMap, attrNameMap);
  h += '</div></div></div></div>';
  return h;
}

function toggleViewEntity(ec) {
  var list = document.getElementById('vwa-list-' + ec);
  var arrow = document.getElementById('vwa-' + ec);
  if (!list || !arrow) return;
  if (list.style.display === 'none') { list.style.display = ''; arrow.classList.add('open'); }
  else { list.style.display = 'none'; arrow.classList.remove('open'); }
}

function selectViewTreeNode(idx) { g_viewTreeSel = {type:'view', idx: idx}; renderForm(); updatePreview(); }

function renderViewDetail(sel, fieldViews, itemSchema, entNameMap, attrNameMap) {
  if (!sel || sel.type !== 'view') return '<div class="ed-empty">← 从左侧选择字段视图查看或编辑</div>';
  var i = sel.idx;
  if (i < 0 || i >= fieldViews.length) return '<div class="ed-empty">⚠ 视图索引无效</div>';
  var fv = fieldViews[i];
  var ec = fv.entityCode || '?', fc = fv.fieldCode || '?';
  var eName = (entNameMap||{})[ec] || ec;
  var fName = (attrNameMap||{})[ec + '.' + fc] || fc;
  var h = '<div class="detail-panel">';
  h += '<div class="detail-head" style="display:flex;align-items:center;gap:8px"><span class="detail-title">' + escHtml(eName) + ' · ' + escHtml(fName) + '</span>';
  h += '<button class="btn btn-primary" onclick="stashView(' + i + ')" style="font-size:11px;margin-left:auto">💾 暂存</button></div>';
  h += '<div class="detail-body">';
  h += schemaObjectForm(itemSchema, fv, 'content.fieldViews.'+i, {});
  h += '</div></div>';
  return h;
}

function addViewViaPicker() { openViewPicker(); }

function deleteViewTree() {
  if (!g_viewTreeSel || g_viewTreeSel.type !== 'view') return;
  var i = g_viewTreeSel.idx;
  var fvs = formState.content.fieldViews || [];
  if (i < 0 || i >= fvs.length) return;
  var fv = fvs[i];
  if (!confirm('确定删除字段视图 "' + (fv.entityCode||'?') + '.' + (fv.fieldCode||'?') + '"？')) return;
  fvs.splice(i, 1);
  delete g_viewDirty[i]; delete g_viewEverStashed[i];
  var newDirty = {}, newEver = {};
  Object.keys(g_viewDirty).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newDirty[ki-1] = true; else if (ki < i) newDirty[ki] = true;
  });
  Object.keys(g_viewEverStashed).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newEver[ki-1] = true; else if (ki < i) newEver[ki] = true;
  });
  g_viewDirty = newDirty; g_viewEverStashed = newEver;
  g_viewTreeSel = null;
  renderForm(); updatePreview();
}

function stashView(idx) {
  g_viewDirty[idx] = true;
  g_viewEverStashed[idx] = true;
  updatePreview(); renderForm();
  g_viewTreeSel = {type:'view', idx: idx};
  setStatus('✅ 已暂存视图 #' + (idx+1) + '（等待保存到项目）', 'ok');
}

function initViewEverStashed(content) {
  (content.fieldViews||[]).forEach(function(r, i) { g_viewEverStashed[i] = true; });
}

function syncViewTreeNode(idx) {
  var node = document.getElementById('view-node-' + idx);
  if (!node) return;
  var fv = (formState.content.fieldViews||[])[idx];
  if (!fv) return;
  var nameEl = node.querySelector('.tree-name');
  if (nameEl) nameEl.textContent = fv.fieldCode || '?';
  var codeEl = node.querySelector('.tree-code');
  if (codeEl) codeEl.textContent = fv.fieldCode || '';
  var badges = node.querySelectorAll('.tree-badge');
  if (badges.length > 0) { badges[0].textContent = enumLabel(fv.formType||'INPUT'); }
}

// ════════════════════════════════════════════════════ OPERATION ═
var g_opTreeSel = null;
var g_opDirty = {};
var g_opEverStashed = {};

function renderOPERATION(c) {
  var ops = c.operations || [];
  var schema = g_schemaCache['OPERATION'];
  if (!schema) { loadSchema('OPERATION').then(function(){ renderForm(); }); return secCard('⚡ 业务操作','<div class="empty-hint">⏳ 加载…</div>'); }
  var itemSchema = (schema.properties.operations||{}).items || {};
  var modelState = g_formStates['MODEL'];
  var modelContent = modelState ? modelState.content : {};
  var entities = modelContent.entities || [];
  var entNameMap = {};
  entities.forEach(function(e) { entNameMap[e.code] = e.name || e.code; });
  var boName = (modelContent.boName) || formState.envelope.boCode || '当前BO';
  var rootEnt = null, childMap = {};
  entities.forEach(function(e) {
    if (e.aggregateRole === 'ROOT' && e.isPrimary) rootEnt = e;
    else if (e.aggregateRole === 'ROOT' && !rootEnt) rootEnt = e;
  });
  entities.forEach(function(e) {
    var parent = e.parentEntityCode || '__root__';
    if (!childMap[parent]) childMap[parent] = [];
    childMap[parent].push(e);
  });
  var globalOps = [];
  var entityOps = {};
  ops.forEach(function(op, i) {
    if (op.scope === 'GLOBAL' && !op.entityCode) { globalOps.push({idx: i, op: op}); }
    else {
      var ec = op.entityCode || (rootEnt ? rootEnt.code : '');
      if (!entityOps[ec]) entityOps[ec] = [];
      entityOps[ec].push({idx: i, op: op});
    }
  });

  function renderEntityTree(ent, level) {
    var ec = ent.code, en = ent.name || ec;
    var items = entityOps[ec] || [];
    var children = childMap[ec] || [];
    var hasContent = items.length > 0 || children.length > 0;
    var h2 = '';
    if (hasContent) {
      h2 += '<div class="tree-node lv-ent" style="font-weight:500">';
      h2 += '<span class="tree-arrow open" id="opa-' + escHtml(ec) + '" onclick="toggleOpEntity(\'' + escHtml(ec) + '\')">▶</span>';
      h2 += '<span class="tree-name" onclick="toggleOpEntity(\'' + escHtml(ec) + '\')">' + escHtml(en) + '</span>';
      h2 += '<span class="tree-code">' + escHtml(ec) + '</span>';
      h2 += '<span class="tree-badge" style="background:rgba(156,163,175,.08);color:#71717a">' + (items.length + children.length) + '</span>';
      h2 += '</div>';
      h2 += '<div id="opa-list-' + escHtml(ec) + '" class="opa-subtree" style="display:block">';
    } else {
      h2 += '<div class="tree-node lv-ent" style="font-weight:500;opacity:0.5">';
      h2 += '<span class="tree-arrow-spacer"></span>';
      h2 += '<span class="tree-name">' + escHtml(en) + '</span>';
      h2 += '<span class="tree-code">' + escHtml(ec) + '</span></div>';
    }
    items.forEach(function(item) { h2 += renderOpNode(item, entNameMap); });
    children.forEach(function(child) { h2 += renderEntityTree(child, level + 1); });
    if (hasContent) h2 += '</div>';
    return h2;
  }

  var h = '<div class="tree-detail-layout">';
  h += '<div class="tree-left-panel">';
  h += '<div class="tree-toolbar"><span class="tree-toolbar-title">⚡ 业务操作</span>';
  h += '<div class="tree-toolbar-actions">';
  h += '<button class="tb-btn tb-btn-add" onclick="addOp()" title="添加操作">+ 添加</button>';
  h += '<button class="tb-btn tb-btn-del" onclick="deleteOpTree()" title="删除操作">🗑</button>';
  h += '</div></div>';
  h += '<div class="tree-scroll" id="op-tree">';
  if (ops.length === 0) {
    h += '<div class="tree-empty">暂无操作，点击 [+ 添加] 新建</div>';
  } else {
    h += '<div class="tree-node lv-ent" style="font-weight:500">';
    h += '<span class="tree-arrow open" id="opa-bo" onclick="toggleOpEntity(\'bo\')">▶</span>';
    h += '<span class="tree-name" onclick="toggleOpEntity(\'bo\')">' + escHtml(boName) + '</span>';
    h += '<span class="tree-badge" style="background:rgba(14,165,233,.08);color:#38bdf8">' + ops.length + '</span></div>';
    h += '<div id="opa-list-bo" class="opa-subtree" style="display:block">';
    h += '<div class="tree-node lv-ent" style="font-weight:500">';
    h += '<span class="tree-arrow open" id="opa-global" onclick="toggleOpEntity(\'global\')">▶</span>';
    h += '<span class="tree-name" onclick="toggleOpEntity(\'global\')">🌐 全局</span>';
    h += '<span class="tree-badge" style="background:rgba(59,130,246,.08);color:#60a5fa">' + globalOps.length + '</span></div>';
    h += '<div id="opa-list-global" class="opa-subtree" style="display:block">';
    if (globalOps.length === 0) {
      h += '<div style="padding:4px 10px;font-size:10px;color:var(--text-tertiary)">无全局操作</div>';
    } else {
      globalOps.forEach(function(item) { h += renderOpNode(item, entNameMap); });
    }
    h += '</div>';
    if (rootEnt) { h += renderEntityTree(rootEnt, 0); }
    var covered = {};
    function markCovered(e) { covered[e.code] = true; (childMap[e.code]||[]).forEach(markCovered); }
    if (rootEnt) markCovered(rootEnt);
    entities.forEach(function(e) { if (!covered[e.code]) h += renderEntityTree(e, 0); });
    h += '</div>';
  }
  h += '</div></div>';
  h += '<div class="tree-detail-resize" onmousedown="startTreeDetailResize(event)"></div>';
  h += '<div class="tree-right-panel" id="op-detail">';
  h += renderOpDetail(g_opTreeSel, ops, itemSchema, entNameMap);
  h += '</div></div>';
  return h;
}

function toggleOpEntity(ec) {
  var list = document.getElementById('opa-list-' + ec);
  var arrow = document.getElementById('opa-' + ec);
  if (!list || !arrow) return;
  if (list.style.display === 'none') { list.style.display = ''; arrow.classList.add('open'); }
  else { list.style.display = 'none'; arrow.classList.remove('open'); }
}

function selectOpTreeNode(idx) { g_opTreeSel = {type:'op', idx: idx}; renderForm(); updatePreview(); }

function renderOpNode(item, entNameMap) {
  var i = item.idx, op = item.op;
  var isSel = g_opTreeSel && g_opTreeSel.type==='op' && g_opTreeSel.idx===i;
  var isDirty = g_opDirty[i];
  var statusBadge = '';
  if (isDirty) { statusBadge = '<span class="tree-badge" style="background:rgba(245,158,11,.15);color:#fbbf24">已暂存</span>'; }
  else if (g_opEverStashed[i]) { statusBadge = '<span class="tree-badge" style="background:rgba(16,185,129,.15);color:#34d399">已保存</span>'; }
  var h = '<div class="tree-node lv-attr' + (isSel?' selected':'') + '" id="op-node-' + i + '" data-op-idx="' + i + '" onclick="selectOpTreeNode(' + i + ')" title="' + escHtml(op.name||'(未命名)') + ' · ' + escHtml(op.code||'') + ' · ' + enumLabel(op.operationKind||'CUSTOM') + '">';
  h += '<span class="tree-arrow-spacer"></span>';
  h += '<span class="tree-name">' + escHtml(op.name||'(未命名)') + '</span>';
  h += '<span class="tree-code">' + escHtml(op.code||'') + '</span>';
  h += '<span class="tree-badge" style="background:rgba(14,165,233,.15);color:#38bdf8">' + enumLabel(op.operationKind||'CUSTOM') + '</span>';
  h += statusBadge;
  h += '</div>';
  return h;
}

function renderOpDetail(sel, ops, itemSchema, entNameMap) {
  if (!sel || sel.type !== 'op') return '<div class="ed-empty">← 从左侧选择操作查看或编辑</div>';
  var i = sel.idx;
  if (i < 0 || i >= ops.length) return '<div class="ed-empty">⚠ 操作索引无效</div>';
  var op = ops[i];
  var eName = (entNameMap||{})[op.entityCode] || op.entityCode || '?';
  var h = '<div class="detail-panel">';
  h += '<div class="detail-head" style="display:flex;align-items:center;gap:8px"><span class="detail-title">' + escHtml(eName) + ' · ' + escHtml(op.name||'(未命名)') + '</span>';
  h += '<button class="btn btn-primary" onclick="stashOp(' + i + ')" style="font-size:11px;margin-left:auto">💾 暂存</button></div>';
  h += '<div class="detail-body">';
  h += schemaObjectForm(itemSchema, op, 'content.operations.'+i, {hiddenFields:['entityCode','prototypeRefs','batchResultType']});
  var entities = ((g_formStates['MODEL']||{}).content||{}).entities || [];
  var curEc = op.entityCode || '';
  h += '<div class="form-grid"><div class="field-group">';
  h += '<label class="f-label">实体代码<i class="help-icon" data-help="操作归属的实体。级联/全局无需选择（自动清空），单实体必选。||例：opportunity_product">?</i></label>';
  h += '<select class="f-select" id="sel-opEntityCode" data-path="content.operations.'+i+'.entityCode">';
  h += '<option value="">-- ' + (op.scope==='GLOBAL'?'全局无需实体':'选择实体') + ' --</option>';
  entities.forEach(function(e) {
    var sel = curEc === e.code ? ' selected' : '';
    h += '<option value="' + escHtml(e.code) + '"' + sel + '>' + escHtml(e.name||e.code) + ' (' + escHtml(e.code) + ')</option>';
  });
  h += '</select></div></div>';
  h += '</div></div>';
  return h;
}

function addOp() {
  if (!formState.content.operations) formState.content.operations = [];
  formState.content.operations.push({
    code:'OP_' + (formState.content.operations.length + 1),
    name:'新操作', entityCode:'', operationKind:'CUSTOM', description:''
  });
  var idx = formState.content.operations.length - 1;
  g_opTreeSel = {type:'op', idx: idx};
  renderForm(); updatePreview();
  setStatus('✅ 已创建新操作，请编辑后点击暂存', 'ok');
}

function stashOp(idx) {
  g_opDirty[idx] = true;
  g_opEverStashed[idx] = true;
  updatePreview(); renderForm();
  g_opTreeSel = {type:'op', idx: idx};
  setStatus('✅ 已暂存操作 #' + (idx+1) + '（等待保存到项目）', 'ok');
}

function initOpEverStashed(content) {
  (content.operations||[]).forEach(function(r, i) { g_opEverStashed[i] = true; });
}

function syncOpTreeNode(idx) {
  var node = document.getElementById('op-node-' + idx);
  if (!node) return;
  var op = (formState.content.operations||[])[idx];
  if (!op) return;
  var nameEl = node.querySelector('.tree-name');
  if (nameEl) nameEl.textContent = op.name || '(未命名)';
  var codeEl = node.querySelector('.tree-code');
  if (codeEl) codeEl.textContent = op.code || '';
  var badges = node.querySelectorAll('.tree-badge');
  if (badges.length > 0) { badges[0].textContent = enumLabel(op.operationKind||'CUSTOM'); }
}

function deleteOpTree() {
  if (!g_opTreeSel || g_opTreeSel.type !== 'op') return;
  var i = g_opTreeSel.idx;
  var ops = formState.content.operations || [];
  if (i < 0 || i >= ops.length) return;
  var op = ops[i];
  if (!confirm('确定删除操作 "' + (op.name||'(未命名)') + '"？')) return;
  ops.splice(i, 1);
  delete g_opDirty[i]; delete g_opEverStashed[i];
  var newDirty = {}, newEver = {};
  Object.keys(g_opDirty).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newDirty[ki-1] = true; else if (ki < i) newDirty[ki] = true;
  });
  Object.keys(g_opEverStashed).forEach(function(k) {
    var ki = parseInt(k); if (ki > i) newEver[ki-1] = true; else if (ki < i) newEver[ki] = true;
  });
  g_opDirty = newDirty; g_opEverStashed = newEver;
  g_opTreeSel = null;
  renderForm(); updatePreview();
}

// ════════════════════════════════════════════════════════ LINK ═
function renderLINK(c) {
  var schema = g_schemaCache['LINK'];
  if (!schema) { loadSchema('LINK').then(function(){ renderForm(); }); return secCard('🔗 显式关系','<div class="empty-hint">⏳ 加载…</div>'); }
  var h = '';
  h += schemaSection(schema, c, 'content', '🔗 显式关系 (LINK)', {
    disabledFields: ['linkCode']
  });
  return h;
}

// ═══════════════════════════════════════════════════ DERIVATION ═
function renderDERIVATION(c) {
  var schema = g_schemaCache['DERIVATION'];
  if (!schema) { loadSchema('DERIVATION').then(function(){ renderForm(); }); return secCard('📐 派生视图','<div class="empty-hint">⏳ 加载…</div>'); }
  var h = '';
  h += schemaSection(schema, c, 'content', '📐 派生视图 (DERIVATION)', {
    disabledFields: ['derivationCode']
  });
  return h;
}

// ════════════════════════════════════════════════════ TEMPORAL ═
function renderTEMPORAL(c) {
  var schema = g_schemaCache['TEMPORAL'];
  if (!schema) { loadSchema('TEMPORAL').then(function(){ renderForm(); }); return secCard('⏱️ 时态配置','<div class="empty-hint">⏳ 加载…</div>'); }
  var h = '';
  h += schemaSection(schema, c, 'content', '⏱️ 时态配置 (TEMPORAL)', {
    disabledFields: ['temporalCode']
  });
  return h;
}

// ═════════════════════════════════════════════════ ACTION_CHAIN ═
function renderACTIONCHAIN(c) {
  var schema = g_schemaCache['ACTION_CHAIN'];
  if (!schema) { loadSchema('ACTION_CHAIN').then(function(){ renderForm(); }); return secCard('⚡ 动作链','<div class="empty-hint">⏳ 加载…</div>'); }
  var h = '';
  h += schemaSection(schema, c, 'content', '⚡ 动作链 (ACTION_CHAIN)', {
    disabledFields: ['chainCode']
  });
  return h;
}
