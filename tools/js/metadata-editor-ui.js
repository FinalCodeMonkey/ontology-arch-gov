/* ═══════════════════════════════════════════════════════════════════
   metadata-editor-ui.js — Tree component, Picker, Shuttle,
   event binding, preview, resize, file operations, boot
   Dependencies: shared-dicts.js, metadata-editor-core.js, metadata-editor-renderers.js
   ═══════════════════════════════════════════════════════════════════ */

// ══════════════════════════════════════════════ EVENT BINDING ════
function bindAllEvents() {
  document.querySelectorAll('[data-toggle="section"]').forEach(function(el) {
    el.onclick = function() {
      var icon = this.querySelector('.expand-icon');
      var body = this.nextElementSibling;
      var isOpen = body.classList.contains('open');
      var card = this.parentElement;
      if (isOpen) {
        body.classList.remove('open'); icon.classList.remove('open');
        body.style.display = 'none';
        if (card && card.style.display.indexOf('flex') >= 0) { card.style.flex = ''; card.style.minHeight = ''; }
      } else {
        body.classList.add('open'); icon.classList.add('open');
        body.style.display = 'flex';
        if (card && card.style.display.indexOf('flex') >= 0) { card.style.flex = '1'; card.style.minHeight = '0'; }
      }
    };
  });
  document.querySelectorAll('[data-toggle="arr"]').forEach(function(el) {
    el.onclick = function(e) {
      if (e.target.tagName==='BUTTON') return;
      var icon = this.querySelector('.ei');
      var body = this.nextElementSibling;
      if (!body) return;
      var isOpen = body.classList.contains('open');
      if (isOpen) { body.classList.remove('open'); icon.classList.remove('open'); }
      else { body.classList.add('open'); icon.classList.add('open'); }
    };
  });
  document.querySelectorAll('[data-path]').forEach(function(el) {
    if (el.tagName==='INPUT' && el.type==='checkbox') {
      el.onchange = function() { setByPath(el.dataset.path, el.checked); updatePreview(); refreshTreeNode(el.dataset.path); };
    } else {
      el.oninput = function() { setByPath(el.dataset.path, el.value); updatePreview(); refreshTreeNode(el.dataset.path); };
    }
  });
  document.querySelectorAll('select[data-path]').forEach(function(el) {
    el.onchange = function() { setByPath(el.dataset.path, el.value); updatePreview(); refreshTreeNode(el.dataset.path); };
  });
  document.querySelectorAll('textarea[data-path]').forEach(function(el) {
    el.oninput = function() { setByPath(el.dataset.path, el.value); updatePreview(); };
  });

  // Conditional field toggles
  var updateScopeEl = document.querySelector('[data-path="content.apiConfig.aggregateApiPolicy.updateScope"]');
  var replaceRow = document.getElementById('row-aggReplacePath');
  if (updateScopeEl && replaceRow) {
    updateScopeEl.onchange = function() {
      replaceRow.style.display = (this.value === 'FULL_AGGREGATE_REPLACE') ? '' : 'none';
      setByPath(this.dataset.path, this.value);
      updatePreview();
    };
  }
  var selParent = document.getElementById('sel-parentEntityCode');
  if (selParent) {
    selParent.onchange = function() { setByPath(this.dataset.path, this.value); updatePreview(); };
  }
  var selRefBo = document.getElementById('sel-refBoCode');
  if (selRefBo) {
    selRefBo.onchange = function() {
      setByPath(this.dataset.path, this.value);
      var pp = this.dataset.path.replace('.refBoCode','');
      setByPath(pp + '.refEntityCode', '');
      setByPath(pp + '.refFieldCode', '');
      updatePreview(); renderForm();
    };
  }
  var selRefEnt = document.getElementById('sel-refEntityCode');
  if (selRefEnt) {
    selRefEnt.onchange = function() {
      setByPath(this.dataset.path, this.value);
      var pp = this.dataset.path.replace('.refEntityCode','');
      setByPath(pp + '.refFieldCode', '');
      updatePreview(); renderForm();
    };
  }
  var selSemRole = document.querySelector('[data-path$=".semanticRole"]');
  if (selSemRole) {
    selSemRole.onchange = function() {
      var newRole = this.value;
      setByPath(this.dataset.path, newRole);
      var pp = this.dataset.path.replace('.semanticRole','');
      if (newRole !== 'CROSS_BO_REF' && newRole !== 'CROSS_BO_DISPLAY') {
        setByPath(pp + '.crossBoRef', null);
      }
      if (newRole !== 'CROSS_BO_DISPLAY') {
        setByPath(pp + '.redundant', false);
      }
      updatePreview(); renderForm();
    };
  }
  var selAggRole = document.querySelector('[data-path$=".aggregateRole"]');
  if (selAggRole) {
    selAggRole.onchange = function() {
      setByPath(this.dataset.path, this.value);
      var pp = this.dataset.path.replace('.aggregateRole','');
      setByPath(pp + '.isPrimary', this.value === 'ROOT');
      if (this.value === 'ROOT') {
        setByPath(pp + '.parentEntityCode', '');
        setByPath(pp + '.parentRefField', '');
        setByPath(pp + '.routeSegment', '');
      } else {
        var ent = getByPath(formState, pp);
        if (ent && !ent.routeSegment && ent.code) {
          setByPath(pp + '.routeSegment', ent.code);
        }
      }
      updatePreview(); renderForm();
    };
  }
  document.querySelectorAll('[data-path$=".type"]').forEach(function(el) {
    if (el.dataset.path.indexOf('.attributes.') >= 0) {
      el.onchange = function() {
        var newType = this.value;
        setByPath(this.dataset.path, newType);
        if (newType !== 'DECIMAL') {
          var pp = this.dataset.path.replace('.type','');
          setByPath(pp + '.precision', null);
          setByPath(pp + '.scale', null);
        }
        updatePreview(); renderForm();
      };
    }
  });
  document.querySelectorAll('[data-path$=".scope"]').forEach(function(el) {
    if (el.dataset.path.indexOf('.operations.') >= 0) {
      el.onchange = function() {
        var newScope = this.value;
        setByPath(this.dataset.path, newScope);
        if (newScope === 'GLOBAL') {
          var pp = this.dataset.path.replace('.scope','');
          setByPath(pp + '.entityCode', '');
        }
        updatePreview(); renderForm();
      };
    }
  });
  initHelpIcons();
}

// ── Entities add/remove ──────────────────────────────────────
function addEntity() {
  if (!formState.content.entities) formState.content.entities = [];
  var hasPrimary = false;
  formState.content.entities.forEach(function(e) {
    if (e.isPrimary && e.aggregateRole === 'ROOT') hasPrimary = true;
  });
  var defRole = hasPrimary ? 'SUB_ENTITY' : 'ROOT';
  formState.content.entities.push({
    code:'',name:'',isPrimary:!hasPrimary,aggregateRole:defRole,tableName:'',
    parentEntityCode:'',parentRefField:'',routeSegment:'',cascadeDelete:true,
    readOnly:false,entityNature:'BUSINESS',attributes:[]
  });
  g_treeSel = {type:'entity', ei: formState.content.entities.length - 1};
  renderForm(); updatePreview();
}

function addAttribute(ei) {
  var ent = formState.content.entities[ei];
  if (!ent.attributes) ent.attributes = [];
  ent.attributes.push({
    code:'',name:'',type:'STRING',isPk:false,fieldName:'',columnName:'',
    semanticRole:'NORMAL',crossBoRef:null,redundant:false,defaultValue:'',
    filterable:false,i18nKey:'',precision:null,scale:null
  });
  g_treeSel = {type:'attr', ei: ei, ai: ent.attributes.length - 1};
  renderForm(); updatePreview();
}

function addAttributeForSelection() {
  var ei = 0;
  if (g_treeSel) { ei = g_treeSel.ei; }
  if (!formState.content.entities || !formState.content.entities[ei]) {
    addEntity();
    return;
  }
  addAttribute(ei);
}

function deleteSelected() {
  if (!g_treeSel || !formState.content.entities) return;
  var sel = g_treeSel;
  if (sel.type === 'entity') {
    if (!confirm('确定删除实体 "' + (formState.content.entities[sel.ei].name||'(未命名)') + '" 及其所有属性？')) return;
    formState.content.entities.splice(sel.ei, 1);
    g_treeSel = null;
  } else if (sel.type === 'attr') {
    var ent = formState.content.entities[sel.ei];
    if (!ent || !ent.attributes) return;
    if (!confirm('确定删除属性 "' + (ent.attributes[sel.ai].name||'(未命名)') + '"？')) return;
    ent.attributes.splice(sel.ai, 1);
    g_treeSel = {type: 'entity', ei: sel.ei};
  }
  renderForm(); updatePreview();
}

// ── Shuttle box ──────────────────────────────────────────────
function toggleShuttleEntity(ec) {
  var list = document.getElementById('sha-list-' + ec);
  var arrow = document.getElementById('sha-' + ec);
  if (!list || !arrow) return;
  if (list.style.display === 'none') { list.style.display = ''; arrow.classList.add('open'); }
  else { list.style.display = 'none'; arrow.classList.remove('open'); }
}

function toggleShuttleRightEntity(ec) {
  var list = document.getElementById('shr-list-' + ec);
  var arrow = document.getElementById('shr-' + ec);
  if (!list || !arrow) return;
  if (list.style.display === 'none') { list.style.display = ''; arrow.classList.add('open'); }
  else { list.style.display = 'none'; arrow.classList.remove('open'); }
}

function shuttleAdd() {
  var items = document.querySelectorAll('#shuttle-left .shuttle-left-cb:checked');
  if (items.length === 0) return;
  var ee = formState.content.rowSecurity.entriesByEntity || {};
  items.forEach(function(cb) {
    var row = cb.closest('.shuttle-left-item');
    if (!row) return;
    var key = row.getAttribute('data-shuttle-key');
    var parts = key.split('.');
    var ec = parts[0], fc = parts.slice(1).join('.');
    if (!ee[ec]) ee[ec] = [];
    if (ee[ec].indexOf(fc) < 0) ee[ec].push(fc);
  });
  formState.content.rowSecurity.entriesByEntity = ee;
  g_rowSecDirty = true;
  renderForm(); updatePreview();
}

function shuttleRemove() {
  var items = document.querySelectorAll('#shuttle-right .shuttle-right-cb:checked');
  if (items.length === 0) return;
  var ee = formState.content.rowSecurity.entriesByEntity || {};
  items.forEach(function(cb) {
    var row = cb.closest('.shuttle-right-item');
    if (!row) return;
    var key = row.getAttribute('data-shuttle-key');
    var parts = key.split('.');
    var ec = parts[0], fc = parts.slice(1).join('.');
    if (ee[ec]) {
      var idx = ee[ec].indexOf(fc);
      if (idx >= 0) ee[ec].splice(idx, 1);
      if (ee[ec].length === 0) delete ee[ec];
    }
  });
  formState.content.rowSecurity.entriesByEntity = ee;
  g_rowSecDirty = true;
  renderForm(); updatePreview();
}

var g_rowSecEverStashed = false;
function stashRowSec() {
  g_rowSecDirty = false;
  g_rowSecEverStashed = true;
  updatePreview(); renderForm();
  setStatus('✅ 已暂存行级安全（等待保存到项目）', 'ok');
}

// ── Resize handlers ──────────────────────────────────────────
function togglePreview() {
  var panel = document.getElementById('preview-panel');
  var handle = document.getElementById('resize-handle');
  var isCollapsed = panel.classList.toggle('collapsed');
  handle.classList.toggle('collapsed', isCollapsed);
  if (isCollapsed) { panel.style.width = ''; }
  else { panel.style.width = '380px'; }
}

(function(){
  var handle = document.getElementById('resize-handle');
  var panel = document.getElementById('preview-panel');
  var startX, startW;
  handle.addEventListener('mousedown', function(e) {
    if (panel.classList.contains('collapsed')) return;
    startX = e.clientX;
    startW = panel.offsetWidth;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    function onMove(ev) {
      var delta = startX - ev.clientX;
      var newW = Math.max(200, Math.min(800, startW + delta));
      panel.style.width = newW + 'px';
    }
    function onUp() {
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
})();

function startTreeResize(e) {
  var tree = document.getElementById('entity-tree');
  var handle = document.getElementById('entity-tree-resize');
  if (!tree || !handle) return;
  var startX = e.clientX;
  var startW = tree.offsetWidth;
  handle.classList.add('active');
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  function onMove(ev) {
    var delta = ev.clientX - startX;
    var newW = Math.max(200, Math.min(600, startW + delta));
    tree.style.width = newW + 'px';
  }
  function onUp() {
    handle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function startTreeDetailResize(e) {
  var handle = e.target;
  var leftPanel = handle.previousElementSibling;
  if (!leftPanel) return;
  var startX = e.clientX;
  var startW = leftPanel.offsetWidth;
  handle.classList.add('active');
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  function onMove(ev) {
    var delta = ev.clientX - startX;
    var newW = Math.max(260, Math.min(700, startW + delta));
    leftPanel.style.width = newW + 'px';
  }
  function onUp() {
    handle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// ── Help icon tooltips ───────────────────────────────────────
var g_helpTip = null;
function showHelpTip(icon) {
  hideHelpTip();
  var raw = icon.getAttribute('data-help') || '';
  var parts = raw.split('||');
  var desc = parts[0] || '';
  var ex = parts[1] || '';
  var tip = document.createElement('div');
  tip.className = 'help-tip-global';
  tip.innerHTML = desc + (ex ? '<span class="ht-example">' + escHtml(ex) + '</span>' : '');
  document.body.appendChild(tip);
  var rect = icon.getBoundingClientRect();
  var top = rect.top - tip.offsetHeight - 6;
  var left = rect.left + rect.width/2 - tip.offsetWidth/2;
  if (top < 4) top = rect.bottom + 6;
  if (left < 4) left = 4;
  if (left + tip.offsetWidth > window.innerWidth - 4) left = window.innerWidth - tip.offsetWidth - 4;
  tip.style.top = top + 'px';
  tip.style.left = left + 'px';
  g_helpTip = tip;
}
function hideHelpTip() { if (g_helpTip) { g_helpTip.remove(); g_helpTip = null; } }
function initHelpIcons() {
  document.querySelectorAll('.help-icon').forEach(function(icon) {
    icon.addEventListener('mouseenter', function() { showHelpTip(icon); });
    icon.addEventListener('mouseleave', hideHelpTip);
  });
}

// ── File operations ──────────────────────────────────────────
function newDoc() {
  document.getElementById('new-bo-modal').classList.remove('hidden');
  document.getElementById('new-boCode').focus();
}
function closeNewBoModal() { document.getElementById('new-bo-modal').classList.add('hidden'); }

function createNewBo() {
  var boCode = document.getElementById('new-boCode').value.trim();
  var boName = document.getElementById('new-boName').value.trim();
  if (!boCode || !boName) { setStatus('❌ BO 标识和名称不能为空','err'); return; }
  var tenantId = document.getElementById('new-tenantId').value.trim() || 'default';
  var appCode = document.getElementById('new-appCode').value.trim() || 'government';
  var boInfoPayload = { boCode: boCode, tenantId: tenantId, appCode: appCode, draftVersion: '0.1', schemaVersion: g_schemaVersion, changeNote: '' };
  closeNewBoModal();
  setStatus('📡 正在创建 ' + boCode + ' …', '');
  fetch('http://127.0.0.1:8765/api/bo-info', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(boInfoPayload)
  })
  .then(function(resp) { return resp.json().then(function(d){ return {ok:resp.ok, data:d}; }); })
  .then(function(r) {
    if (!r.ok) { setStatus('❌ 创建管理信息失败: ' + (r.data.error||'未知错误'), 'err'); return; }
    var fragPayload = {
      boCode: boCode, metaType: 'MODEL',
      content: {
        boCode: boCode, boName: boName,
        description: document.getElementById('new-description').value.trim(),
        apiConfig: { resourcePath:'/'+boCode, idField:'id', idType:'LONG', businessKeyField:'', aggregateApiPolicy:{ listProjectionScope:'ROOT_SUMMARY',readScope:'FULL_AGGREGATE',createScope:'FULL_AGGREGATE',updateScope:'ROOT_ENTITY_ONLY',deleteScope:'CASCADE_AGGREGATE',orphanPolicy:'DENY_DELETE_WHEN_CHILD_EXISTS',detailEmbedEntities:[] }, searchEnabled:true, batchEnabled:true },
        boConfig: { objectType:'SINGLE', nameField:'', statusField:'', logicDeleteFlag:true, versionFlag:false, idStrategy:'SNOWFLAKE', auditStrategy:'DATABASE' },
        entities: []
      }
    };
    return fetch('http://127.0.0.1:8765/api/save-fragment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fragPayload)
    }).then(function(r2){ return r2.json().then(function(d){ return {ok:r2.ok, data:d}; }); });
  })
  .then(function(r) {
    if (r.ok) {
      setStatus('✅ 已创建 ' + r.data.file, 'ok');
      window.location.href = window.location.pathname + '?boCode=' + encodeURIComponent(boCode);
    } else {
      setStatus('❌ 创建失败: ' + (r.data.error||'未知错误'), 'err');
    }
  })
  .catch(function(err) { setStatus('❌ 创建失败: ' + err.message + ' — API 服务是否已启动？', 'err'); });
}

function saveToServer() {
  var boCode = formState.envelope.boCode;
  if (!boCode) { setStatus('❌ 请先填写 BO 标识','err'); return; }
  var isBoInfo = (currentTab === 'BO_INFO');
  var apiBase = 'http://127.0.0.1:8765';
  var payload, endpoint;
  if (isBoInfo) {
    var env = formState.envelope;
    payload = { boCode: boCode, tenantId: env.tenantId, appCode: env.appCode,
      draftVersion: env.draftVersion, schemaVersion: env.schemaVersion, changeNote: env.changeNote || '' };
    endpoint = '/api/bo-info';
    setStatus('📡 正在保存 bo-info.json …', '');
  } else {
    var mt = formState.envelope.metaType;
    payload = { boCode: boCode, metaType: mt,
      content: JSON.parse(JSON.stringify(formState.content)) };
    endpoint = '/api/save-fragment';
    setStatus('📡 正在保存 ' + boCode + '-' + mt.toLowerCase() + '.fragment.json …', '');
  }
  fetch(apiBase + endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(function(resp) { return resp.json().then(function(d){ return {ok:resp.ok, data:d}; }); })
  .then(function(r) {
    if (r.ok) {
      var file = r.data.file || 'bo-info.json';
      if (currentMetaType === 'VALIDATION') { g_valDirty = {}; }
      if (currentMetaType === 'RULE') { g_ruleDirty = {}; }
      if (currentMetaType === 'VIEW') { g_viewDirty = {}; }
      if (currentMetaType === 'OPERATION') { g_opDirty = {}; }
      if (currentMetaType === 'SECURITY') { g_fsecDirty = {}; g_rowSecDirty = false; }
      var warnings = r.data.schemaWarnings;
      if (warnings && warnings.length > 0) {
        var warnText = '✅ 已保存 ' + file + '\n\n⚠ Schema 校验发现 ' + warnings.length + ' 个问题（已保存，建议修正）：\n\n' +
          warnings.map(function(w, i) { return (i+1) + '. ' + w; }).join('\n');
        setStatus(warnText, 'warn');
      } else {
        setStatus('✅ 已保存 ' + file, 'ok');
      }
      renderForm();
    } else {
      setStatus('❌ 保存失败: ' + (r.data.error||'未知错误'), 'err');
    }
  })
  .catch(function(err) { setStatus('❌ 保存失败: ' + err.message + ' — API 服务是否已启动？', 'err'); });
}

function downloadDoc() {
  var json = buildOutputJson();
  var boCode = formState.envelope.boCode || 'untitled';
  var mt = formState.envelope.metaType;
  var filename = boCode + '-' + mt.toLowerCase() + '.fragment.json';
  var blob = new Blob([json], {type:'application/json'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
  setStatus('⬇ 已下载 ' + filename, 'ok');
}

function saveDoc() { downloadDoc(); }

function openFile(event) {
  var file = event.target.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = function(e) {
    try {
      var data = JSON.parse(e.target.result);
      var mt = data.metaType || 'MODEL';
      var bc = data.boCode || '';
      g_sharedEnvelope.tenantId = data.tenantId || 'default';
      g_sharedEnvelope.appCode = data.appCode || 'government';
      g_sharedEnvelope.boCode = bc;
      g_sharedEnvelope.draftVersion = data.draftVersion || '0.1';
      g_sharedEnvelope.schemaVersion = data.schemaVersion || g_schemaVersion;
      g_sharedEnvelope.changeNote = data.changeNote || '';
      currentMetaType = mt;
      currentTab = (mt === 'MODEL') ? 'MODEL' : mt;
      formState = createDefaultState(mt);
      formState.envelope = Object.assign({}, g_sharedEnvelope, {metaType: mt});
      formState.content = data.content || createDefaultState(mt).content;
      if (mt === 'RULE') { initRuleEverStashed(formState.content); }
      if (mt === 'VIEW') { initViewEverStashed(formState.content); }
      if (mt === 'OPERATION') { initOpEverStashed(formState.content); }
      if (mt === 'SECURITY') { initFsecEverStashed(formState.content); }
      if (formState.content.boCode !== undefined) formState.content.boCode = bc;
      g_formStates = {};
      g_formStates[mt] = formState;
      renderMetaTabs();
      renderForm();
      updatePreview();
      setStatus('📂 已加载 ' + file.name,'ok');
    } catch(err) { setStatus('❌ 解析失败: ' + err.message,'err'); }
  };
  reader.readAsText(file);
  event.target.value = '';
}

// ── View picker modal ────────────────────────────────────────
var g_vpSelEnt = '';
var g_vpSelected = {};
var g_vpExclude = {};
var g_vpConfirmAction = '';

function openViewPicker() {
  g_vpSelEnt = '';
  g_vpSelected = {};
  g_vpExclude = {};
  (formState.content.fieldViews||[]).forEach(function(fv) {
    if (fv.entityCode && fv.fieldCode) g_vpExclude[fv.entityCode + '.' + fv.fieldCode] = true;
  });
  var modelState = g_formStates['MODEL'];
  var entities = (modelState ? modelState.content.entities : []) || [];
  var rootEnt = null;
  entities.forEach(function(e) { if (e.aggregateRole === 'ROOT' && e.isPrimary) rootEnt = e; });
  if (!rootEnt) entities.forEach(function(e) { if (e.aggregateRole === 'ROOT') rootEnt = e; });
  if (rootEnt) g_vpSelEnt = rootEnt.code;
  g_vpConfirmAction = 'view';
  var modal = document.getElementById('view-picker-modal');
  var confirmBtn = modal.querySelector('.modal-footer .btn-primary');
  if (confirmBtn) confirmBtn.setAttribute('onclick', 'confirmViewPicker()');
  var titleEl = modal.querySelector('.modal-header h3');
  if (titleEl) titleEl.textContent = '🖥️ 选择字段视图';
  buildViewPickerTree();
  buildViewPickerTable();
  buildViewPickerSelected();
  modal.classList.remove('hidden');
}

function closeViewPicker() {
  document.getElementById('view-picker-modal').classList.add('hidden');
  g_vpSelEnt = ''; g_vpSelected = {}; g_vpExclude = {};
}

function confirmViewPicker() {
  var keys = Object.keys(g_vpSelected).filter(function(k) { return g_vpSelected[k]; });
  if (keys.length === 0) { closeViewPicker(); return; }
  if (!formState.content.fieldViews) formState.content.fieldViews = [];
  keys.forEach(function(key) {
    var parts = key.split('.');
    var ec = parts[0], fc = parts.slice(1).join('.');
    var exists = false;
    (formState.content.fieldViews||[]).forEach(function(fv) {
      if (fv.entityCode === ec && fv.fieldCode === fc) exists = true;
    });
    if (!exists) {
      formState.content.fieldViews.push({
        entityCode: ec, fieldCode: fc,
        formType: 'INPUT', hidden: false,
        label: '', placeholder: '', sortable: false, width: ''
      });
    }
  });
  closeViewPicker();
  g_viewTreeSel = {type:'view', idx: (formState.content.fieldViews||[]).length - 1};
  renderForm(); updatePreview();
  setStatus('✅ 已添加 ' + keys.length + ' 个视图', 'ok');
}

function buildViewPickerTree() {
  var modelState = g_formStates['MODEL'];
  var entities = (modelState ? modelState.content.entities : []) || [];
  var container = document.getElementById('vp-tree');
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
  function renderNode(ent, level) {
    var ec = ent.code, en = ent.name || ec;
    var isSel = g_vpSelEnt === ec;
    var padLeft = 4 + level * 12;
    var h2 = '<div class="tree-node' + (isSel?' selected':'') + '" style="padding-left:' + padLeft + 'px" onclick="selectViewPickerEntity(\'' + escHtml(ec) + '\')" title="' + escHtml(en) + ' · ' + escHtml(ec) + '">';
    h2 += '<span class="tree-name">' + escHtml(en) + '</span></div>';
    var children = childMap[ec] || [];
    children.forEach(function(child) { h2 += renderNode(child, level + 1); });
    return h2;
  }
  var html = '';
  if (rootEnt) html += renderNode(rootEnt, 0);
  var covered = {};
  function markCovered(ent) { covered[ent.code] = true; (childMap[ent.code]||[]).forEach(markCovered); }
  if (rootEnt) markCovered(rootEnt);
  entities.forEach(function(e) { if (!covered[e.code]) html += renderNode(e, 0); });
  container.innerHTML = html || '<div style="padding:12px;font-size:11px;color:var(--text-tertiary)">无实体数据</div>';
}

function selectViewPickerEntity(ec) { g_vpSelEnt = ec; buildViewPickerTree(); buildViewPickerTable(); }

function buildViewPickerTable() {
  var modelState = g_formStates['MODEL'];
  var entities = (modelState ? modelState.content.entities : []) || [];
  var container = document.getElementById('vp-table');
  var label = document.getElementById('vp-ent-label');
  if (!g_vpSelEnt) { container.innerHTML = '<div class="tree-empty">← 请先选择左侧实体</div>'; label.textContent = '选择实体查看字段'; return; }
  var entMap = {}; entities.forEach(function(e) { entMap[e.code] = e; });
  var targetEnt = entMap[g_vpSelEnt];
  if (!targetEnt) { container.innerHTML = '<div class="tree-empty">实体不存在</div>'; return; }
  label.textContent = (targetEnt.name || g_vpSelEnt) + ' · 字段列表';
  var includeChildren = document.getElementById('vp-include-children').checked;
  var showConfigured = document.getElementById('vp-show-configured').checked;
  var allAttrs = [];
  function collectAttrs(ec) {
    var ent = entMap[ec]; if (!ent) return;
    var en = ent.name || ec;
    (ent.attributes||[]).forEach(function(attr) {
      allAttrs.push({entityCode: ec, entityName: en, attr: attr});
    });
    if (includeChildren) {
      entities.forEach(function(e) { if (e.parentEntityCode === ec) collectAttrs(e.code); });
    }
  }
  collectAttrs(g_vpSelEnt);
  if (allAttrs.length === 0) { container.innerHTML = '<div class="tree-empty">该实体无字段</div>'; return; }
  var h = '<table class="vp-field-table"><thead><tr><th style="width:30px"></th><th>字段名</th><th>字段 Code</th><th>类型</th><th>所属实体</th></tr></thead><tbody>';
  allAttrs.forEach(function(item) {
    var ec = item.entityCode, attr = item.attr;
    var fc = attr.code, fn = attr.name || fc;
    var key = ec + '.' + fc;
    var excluded = g_vpExclude[key];
    if (excluded && !showConfigured) return;
    var checked = g_vpSelected[key] ? ' checked' : '';
    if (excluded) {
      h += '<tr class="vp-row-excluded" title="已配置，不可重复选择">';
      h += '<td><input type="checkbox" disabled></td>';
      h += '<td style="opacity:0.5">' + escHtml(fn) + '</td>';
      h += '<td style="font-family:monospace;font-size:11px;color:var(--text-tertiary);opacity:0.5">' + escHtml(fc) + '</td>';
      h += '<td style="font-size:10px;opacity:0.5">' + escHtml(attr.type||'?') + '</td>';
      h += '<td style="font-size:10px;color:var(--text-tertiary);opacity:0.5">已配置</td>';
    } else {
      h += '<tr class="' + (checked?'vp-row-sel':'') + '" onclick="toggleViewPickerField(\'' + escHtml(ec) + '\',\'' + escHtml(fc) + '\')">';
      h += '<td><input type="checkbox" ' + checked + ' onclick="event.stopPropagation();toggleViewPickerField(\'' + escHtml(ec) + '\',\'' + escHtml(fc) + '\')"></td>';
      h += '<td>' + escHtml(fn) + '</td>';
      h += '<td style="font-family:monospace;font-size:11px;color:var(--text-tertiary)">' + escHtml(fc) + '</td>';
      h += '<td style="font-size:10px;color:var(--accent)">' + escHtml(attr.type||'?') + '</td>';
      h += '<td style="font-size:10px;color:var(--text-tertiary)">' + escHtml(item.entityName) + '</td>';
    }
    h += '</tr>';
  });
  h += '</tbody></table>';
  container.innerHTML = h;
}

function toggleViewPickerField(ec, fc) {
  var key = ec + '.' + fc;
  if (g_vpSelected[key]) { delete g_vpSelected[key]; } else { g_vpSelected[key] = true; }
  buildViewPickerTable();
  buildViewPickerSelected();
}

function buildViewPickerSelected() {
  var container = document.getElementById('vp-selected');
  var count = document.getElementById('vp-sel-count');
  var keys = Object.keys(g_vpSelected).filter(function(k) { return g_vpSelected[k]; });
  count.textContent = keys.length;
  if (keys.length === 0) { container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-tertiary);font-size:11px">勾选中间表格添加</div>'; return; }
  var modelState = g_formStates['MODEL'];
  var entities = (modelState ? modelState.content.entities : []) || [];
  var entMap = {}, attrMap = {};
  entities.forEach(function(e) {
    entMap[e.code] = e.name || e.code;
    (e.attributes||[]).forEach(function(a) { attrMap[e.code + '.' + a.code] = a.name || a.code; });
  });
  var h = '';
  keys.forEach(function(key) {
    var parts = key.split('.');
    var ec = parts[0], fc = parts.slice(1).join('.');
    var eName = entMap[ec] || ec, fName = attrMap[key] || fc;
    h += '<div class="vp-sel-item">';
    h += '<span class="vp-sel-info"><span class="vp-sel-name">' + escHtml(fName) + '</span><span class="vp-sel-code">' + escHtml(ec) + '.' + escHtml(fc) + '</span></span>';
    h += '<button class="vp-sel-del" onclick="event.stopPropagation();removeViewPickerField(\'' + escHtml(ec) + '\',\'' + escHtml(fc) + '\')" title="移除">✕</button>';
    h += '</div>';
  });
  container.innerHTML = h;
}

function removeViewPickerField(ec, fc) {
  delete g_vpSelected[ec + '.' + fc];
  buildViewPickerTable();
  buildViewPickerSelected();
}

// ── VP table styles injection ─────────────────────────────────
(function() {
  var style = document.createElement('style');
  style.textContent = '.vp-field-table{width:100%;border-collapse:collapse;font-size:11px}.vp-field-table th{padding:6px 10px;text-align:left;color:var(--text-tertiary);font-weight:500;font-size:10px;background:var(--bg-surface);position:sticky;top:0;z-index:1}.vp-field-table td{padding:5px 10px;border-bottom:1px solid var(--border-subtle);cursor:pointer}.vp-field-table tr:hover{background:var(--bg-elevated)}.vp-field-table tr.vp-row-sel{background:rgba(59,130,246,.08)}.vp-field-table tr.vp-row-excluded{opacity:.45;cursor:not-allowed;background:rgba(113,113,122,.05)}.vp-field-table tr.vp-row-excluded:hover{background:rgba(113,113,122,.05)}.vp-field-table input[type="checkbox"]{width:13px;height:13px;accent-color:var(--accent);cursor:pointer}.vp-sel-item{display:flex;align-items:center;gap:6px;padding:5px 10px;border-bottom:1px solid var(--border-subtle);font-size:11px}.vp-sel-item:hover{background:var(--bg-elevated)}.vp-sel-info{flex:1;min-width:0;display:flex;flex-direction:column}.vp-sel-name{color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.vp-sel-code{font-size:10px;color:var(--text-tertiary);font-family:monospace}.vp-sel-del{flex-shrink:0;width:18px;height:18px;border:none;border-radius:3px;background:transparent;color:var(--text-tertiary);cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center}.vp-sel-del:hover{background:rgba(239,68,68,.15);color:#ef4444}';
  document.head.appendChild(style);
})();

// ── Beforeunload guard ───────────────────────────────────────
function hasDirtyChanges() {
  if (Object.keys(g_valDirty).length > 0) return true;
  if (Object.keys(g_ruleDirty).length > 0) return true;
  if (Object.keys(g_viewDirty).length > 0) return true;
  if (Object.keys(g_opDirty).length > 0) return true;
  if (Object.keys(g_fsecDirty).length > 0) return true;
  if (g_rowSecDirty) return true;
  return false;
}

window.addEventListener('beforeunload', function(e) {
  if (hasDirtyChanges()) {
    e.preventDefault();
    e.returnValue = '';
  }
});

function fetchSchemaVersion() {
  return fetch('http://127.0.0.1:8765/api/schema-version', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }).then(function(r){ return r.json(); }).then(function(d){
    g_schemaVersion = d.schemaVersion || '2.0';
    g_sharedEnvelope.schemaVersion = g_schemaVersion;
    return g_schemaVersion;
  }).catch(function(){});
}

function preloadSchemas(metaType) {
  var toLoad = ['ENVELOPE'];
  if (metaType) toLoad.push(metaType);
  if (metaType !== 'MODEL') toLoad.push('MODEL');
  return Promise.all(toLoad.map(function(k) { return loadSchema(k).catch(function(){}); }));
}

function autoLoadFragment(boCode, metaType) {
  var apiBase = 'http://127.0.0.1:8765';
  Promise.all([
    fetch(apiBase + '/api/bo-info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: boCode })
    }).then(function(r){ return r.ok ? r.json() : null; }),
    fetch(apiBase + '/api/fragment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: boCode, metaType: metaType })
    }).then(function(r){ if(!r.ok) throw new Error('Fragment not found'); return r.json(); })
  ])
  .then(function(results) {
    var info = results[0] || {};
    var data = results[1];
    g_sharedEnvelope.tenantId = info.tenantId || data.tenantId || 'default';
    g_sharedEnvelope.appCode = info.appCode || data.appCode || 'government';
    g_sharedEnvelope.boCode = data.boCode || boCode;
    g_sharedEnvelope.draftVersion = info.draftVersion || data.draftVersion || '0.1';
    g_sharedEnvelope.schemaVersion = info.schemaVersion || data.schemaVersion || g_schemaVersion;
    g_sharedEnvelope.changeNote = info.changeNote || data.changeNote || '';
    var mt = data.metaType || metaType;
    currentMetaType = mt;
    currentTab = (mt === 'MODEL') ? 'MODEL' : mt;
    formState = createDefaultState(mt);
    formState.envelope = Object.assign({}, g_sharedEnvelope, {metaType: mt});
    formState.content = data.content || createDefaultState(mt).content;
    if (mt === 'RULE') { initRuleEverStashed(formState.content); }
    if (mt === 'VIEW') { initViewEverStashed(formState.content); }
    if (mt === 'OPERATION') { initOpEverStashed(formState.content); }
    if (mt === 'SECURITY') { initFsecEverStashed(formState.content); }
    g_formStates[mt] = formState;
    var boName = (data.content && data.content.boName) || boCode;
    setStatus('✅ 已加载 ' + boName + ' — ' + mt, 'ok');
    renderMetaTabs();
    renderForm();
    updatePreview();
  })
  .catch(function(err) {
    g_sharedEnvelope.boCode = boCode;
    formState.envelope.boCode = boCode;
    currentTab = (metaType === 'MODEL') ? 'MODEL' : metaType;
    currentMetaType = metaType;
    setStatus('⚠ 自动加载失败: ' + err.message + ' — boCode 已预填，请手动编辑', 'err');
    renderMetaTabs();
    renderForm();
    updatePreview();
  });
}

// ── BOOT ─────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function() {
  fetch('graph-data.json')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      g_boList = (data.bos||[]).map(function(b) {
        return {code:b.boCode, name:b.boName, entities:b.entities||[]};
      });
    })
    .catch(function() {});

  document.getElementById('new-bo-modal').addEventListener('click', function(e) {
    if (e.target === this) closeNewBoModal();
  });
  document.getElementById('view-picker-modal').addEventListener('click', function(e) {
    if (e.target === this) closeViewPicker();
  });
  var params = new URLSearchParams(window.location.search);
  var boCode = params.get('boCode');
  var action = params.get('action');
  fetchSchemaVersion().then(function(){
    if (action === 'new') {
      preloadSchemas('MODEL').then(function(){
        renderMetaTabs();
        renderForm();
        updatePreview();
        newDoc();
      });
      return;
    }
    if (boCode) {
      setStatus('📡 正在加载 ' + boCode + ' 的 MODEL fragment…', '');
      preloadSchemas('MODEL').then(function() { autoLoadFragment(boCode, 'MODEL'); });
      return;
    }
    preloadSchemas('MODEL').then(function(){
      renderMetaTabs();
      renderForm();
      updatePreview();
    });
  });
});