/* ═══════════════════════════════════════════════════════════════════
   ontology-graph-actions.js — Modal, publish/projection/DDL/inspect/reparse
   Dependencies: shared-dicts.js, ontology-graph-engine.js
   ═══════════════════════════════════════════════════════════════════ */

// ── 元数据编辑器桥接 ─────────────────────────────────────────
function openMetadataEditor(event) {
  if (event) event.preventDefault();
  if (!selectedBoCode) return;
  var editorUrl = window.location.href;
  if (editorUrl.indexOf('bo-ontology-graph.html') >= 0) {
    editorUrl = editorUrl.replace('bo-ontology-graph.html', 'bo-metadata-editor.html');
  } else {
    editorUrl = 'bo-metadata-editor.html';
  }
  editorUrl = editorUrl.split('?')[0] + '?boCode=' + encodeURIComponent(selectedBoCode);
  window.open(editorUrl, 'bo-editor-' + selectedBoCode);
}

function openNewBoEditor() {
  var editorUrl = window.location.href;
  if (editorUrl.indexOf('bo-ontology-graph.html') >= 0) {
    editorUrl = editorUrl.replace('bo-ontology-graph.html', 'bo-metadata-editor.html');
  } else {
    editorUrl = 'bo-metadata-editor.html';
  }
  editorUrl = editorUrl.split('?')[0] + '?action=new';
  window.open(editorUrl, 'bo-editor-new');
}

// ── 带超时的 fetch ──────────────────────────────────────────
function fetchWithTimeout(url, timeoutMs, options) {
  var controller = new AbortController();
  var timer = setTimeout(function() { controller.abort(); }, timeoutMs);
  return fetch(url, Object.assign({}, options, { signal: controller.signal })).finally(function() {
    clearTimeout(timer);
  });
}

// ── 弹窗系统 ────────────────────────────────────────────────
function showModal(title, jsonStr, downloadName, filePath) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-json').textContent = jsonStr;
  document.getElementById('json-modal').classList.remove('hidden');
  modalJsonData = jsonStr;
  modalDownloadName = downloadName || 'output.json';
  modalFilePath = filePath || '';
}
function closeModal() { document.getElementById('json-modal').classList.add('hidden'); }
function copyModalJson() {
  navigator.clipboard.writeText(modalJsonData).catch(function() {
    var pre = document.getElementById('modal-json');
    var range = document.createRange(); range.selectNodeContents(pre);
    var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
    document.execCommand('copy');
  });
}
function downloadModalJson() {
  if (modalFilePath) {
    var a = document.createElement('a');
    a.href = API_BASE + '/api/file?path=' + encodeURIComponent(modalFilePath) + '&download=1';
    a.download = modalDownloadName;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    return;
  }
  var blob = new Blob([modalJsonData], { type: 'application/json' });
  var url = URL.createObjectURL(blob);
  var a2 = document.createElement('a'); a2.href = url; a2.download = modalDownloadName;
  document.body.appendChild(a2); a2.click(); document.body.removeChild(a2);
  URL.revokeObjectURL(url);
}

// ── DB 配置 ─────────────────────────────────────────────────
function openDbConfig() {
  document.getElementById('db-config-modal').classList.remove('hidden');
  var cfg = loadDbConfig();
  document.getElementById('db-host').value = cfg.host || '';
  document.getElementById('db-port').value = cfg.port || '';
  document.getElementById('db-user').value = cfg.user || '';
  document.getElementById('db-password').value = cfg.password || '';
  document.getElementById('db-database').value = cfg.database || '';
  document.getElementById('db-config-status').className = 'db-config-status';
}
function closeDbConfig() { document.getElementById('db-config-modal').classList.add('hidden'); }
function loadDbConfig() {
  try { var raw = localStorage.getItem(DB_CONFIG_KEY); if (raw) return JSON.parse(raw); } catch(e) {}
  return { host: '', port: 3306, user: '', password: '', database: '' };
}
function saveDbConfig() {
  var config = {
    host: document.getElementById('db-host').value.trim(),
    port: parseInt(document.getElementById('db-port').value) || 3306,
    user: document.getElementById('db-user').value.trim(),
    password: document.getElementById('db-password').value,
    database: document.getElementById('db-database').value.trim(),
  };
  if (!config.host || !config.database) {
    var s = document.getElementById('db-config-status');
    s.className = 'db-config-status';
    s.style.display = 'block';
    s.textContent = '⚠ 主机地址和数据库名不能为空';
    s.style.color = '#fca5a5';
    return;
  }
  localStorage.setItem(DB_CONFIG_KEY, JSON.stringify(config));
  var s2 = document.getElementById('db-config-status');
  s2.className = 'db-config-status success';
  s2.textContent = '✅ 配置已保存';
  setTimeout(closeDbConfig, 1200);
}

// ── 多选投影下拉 ──────────────────────────────────────────
function toggleProjDropdown(id) {
  var dd = document.getElementById(id);
  if (!dd) return;
  var opts = dd.querySelector('.multi-select-options');
  var arrow = dd.querySelector('.dropdown-arrow');
  var isOpen = opts.classList.contains('open');
  document.querySelectorAll('.multi-select-options.open').forEach(function(o) { o.classList.remove('open'); });
  document.querySelectorAll('.dropdown-arrow.open').forEach(function(a) { a.classList.remove('open'); });
  if (!isOpen) { opts.classList.add('open'); arrow.classList.add('open'); }
  setTimeout(function() { syncProjCheckboxes(); }, 0);
}

function syncProjCheckboxes() {
  var globalChecks = document.querySelectorAll('#global-proj-dropdown input[type="checkbox"]');
  var panelChecks = document.querySelectorAll('#panel-proj-dropdown input[type="checkbox"]');
  var changed = document.activeElement;
  if (changed && changed.closest('#global-proj-dropdown')) {
    panelChecks.forEach(function(cb) {
      var gcb = document.querySelector('#global-proj-dropdown input[value="' + cb.value + '"]');
      if (gcb) cb.checked = gcb.checked;
    });
  } else {
    globalChecks.forEach(function(cb) {
      var pcb = document.querySelector('#panel-proj-dropdown input[value="' + cb.value + '"]');
      if (pcb) cb.checked = pcb.checked;
    });
  }
  updateProjSelection('both');
}

function updateProjSelection(which) {
  syncProjCheckboxes();
}

function getSelectedProjTypes() {
  var dd = document.getElementById('global-proj-dropdown');
  if (!dd) return ['authz_bo_meta_model'];
  var selected = Array.from(dd.querySelectorAll('input[type="checkbox"]:checked')).map(function(cb) { return cb.value; });
  return selected.length > 0 ? selected : ['authz_bo_meta_model'];
}

// ── 全量操作函数 (作用于所有 BO) ──────────────────────────────
async function generateAllPublishedStates() {
  if (!graphData || !graphData.bos.length) return;
  var btn = document.querySelector('.global-actions button[onclick*="generateAllPublishedStates"]');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 发布中…'; btn.disabled = true; }
  try {
    var fullReport = '═══════════════════════════════════════════════════════════\n  全量发布态报告 — ' + graphData.bos.length + ' BOs\n  时间: ' + new Date().toLocaleString() + '\n═══════════════════════════════════════════════════════════\n';
    for (var i = 0; i < graphData.bos.length; i++) {
      var bo = graphData.bos[i];
      try {
        var resp = await fetchWithTimeout(API_BASE + '/api/publish', 60000, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ boCode: bo.boCode }),
        });
        if (!resp.ok) {
          var err = await resp.json();
          fullReport += '\n⚠ ' + bo.boName + ' (' + bo.boCode + '): ' + (err.error || '未知错误') + '\n';
          continue;
        }
        var fileResp = await fetchWithTimeout(API_BASE + '/api/file?type=publish&boCode=' + encodeURIComponent(bo.boCode), 30000);
        if (fileResp.ok) {
          var fileData = await fileResp.json();
          publishedStates[bo.boCode] = fileData;
          fullReport += '\n✅ ' + bo.boName + ' (' + bo.boCode + ') — 已生成\n' + JSON.stringify(fileData, null, 2) + '\n';
        } else {
          fullReport += '\n⚠ ' + bo.boName + ' (' + bo.boCode + '): 文件读取失败\n';
        }
      } catch (e) {
        fullReport += '\n❌ ' + bo.boName + ' (' + bo.boCode + '): ' + e.message + '\n';
      }
    }
    fullReport += '\n🎉 全量发布完成 (' + graphData.bos.length + ' BOs)。\n';
    showModal('📦 全量发布态 (' + graphData.bos.length + ' BOs)', fullReport, 'all_bos_published.json');
  } catch (e) {
    showModal('⚠ 发布失败', '请确认 API 服务已启动\n\n' + (e.name === 'AbortError' ? '请求超时' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function generateAllPspProjections() {
  if (!graphData || !graphData.bos.length) return;
  var ptypes = getSelectedProjTypes();
  var PROJ_SUFFIX = { 'authz_bo_meta_model': 'authz_bo_meta_model.schema_json.v2.json', 'api-contract': 'api-contract.json', 'authz_projection': 'authz_projection.json', 'ui-model': 'ui-model.json' };
  var btn = document.querySelector('#global-proj-dropdown .multi-select-trigger');
  var oldHtml = btn ? btn.innerHTML : '';
  if (btn) { btn.querySelector('#global-proj-display').textContent = '⏳ 投影中…'; btn.disabled = true; }
  try {
    var fullReport = '═══════════════════════════════════════════════════════════\n  全量 PSP 投影报告 — ' + graphData.bos.length + ' BOs\n  类型: ' + ptypes.map(function(t){return PROJ_LABELS[t]||t;}).join(' + ') + '\n  时间: ' + new Date().toLocaleString() + '\n═══════════════════════════════════════════════════════════\n';
    for (var i = 0; i < graphData.bos.length; i++) {
      var bo = graphData.bos[i];
      fullReport += '\n── ' + bo.boName + ' (' + bo.boCode + ') ──\n';
      for (var j = 0; j < ptypes.length; j++) {
        var ptype = ptypes[j];
        try {
          var resp = await fetchWithTimeout(API_BASE + '/api/projection', 60000, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ boCode: bo.boCode, projectionType: ptype }),
          });
          if (!resp.ok) {
            var err2 = await resp.json();
            fullReport += '  ⚠ ' + (PROJ_LABELS[ptype]||ptype) + ': ' + (err2.error || '未知错误') + '\n';
            continue;
          }
          var suffix = PROJ_SUFFIX[ptype] || (ptype + '.json');
          var fileResp2 = await fetchWithTimeout(API_BASE + '/api/file?type=projection&boCode=' + encodeURIComponent(bo.boCode) + '&projType=' + encodeURIComponent(ptype), 30000);
          if (fileResp2.ok) {
            var fileData2 = await fileResp2.json();
            fullReport += '  ✅ ' + (PROJ_LABELS[ptype]||ptype) + ' → projection-run-time/' + bo.boCode + '/' + bo.boCode + '.' + suffix + '\n' + JSON.stringify(fileData2, null, 2).split('\n').map(function(l){return '  ' + l;}).join('\n') + '\n';
          } else {
            fullReport += '  ⚠ ' + (PROJ_LABELS[ptype]||ptype) + ': 文件读取失败\n';
          }
        } catch (e) {
          fullReport += '  ❌ ' + (PROJ_LABELS[ptype]||ptype) + ': ' + e.message + '\n';
        }
      }
    }
    // ── 自动合并投影：在所有 BO 的标准投影完成后，触发 merge manifest 合并 ──
    fullReport += '\n── 🔀 自动合并投影 ──\n';
    try {
      var mergeResp = await fetchWithTimeout(API_BASE + '/api/projection/merge', 30000, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (mergeResp.ok) {
        var mergeData = await mergeResp.json();
        if (mergeData.merged && mergeData.merged.length > 0) {
          fullReport += '  ✅ ' + mergeData.merged.length + ' 个 BO 合并投影已生成:\n';
          for (var k = 0; k < mergeData.merged.length; k++) {
            var m = mergeData.merged[k];
            fullReport += '    🔀 ' + m.targetBoCode + ' → ' + m.file + ' (' + m.entities + ' 实体 · ' + m.attributes + ' 属性 · ' + m.operations + ' 操作 · ' + m.permissionItems + ' 权限项)\n';
          }
        } else {
          fullReport += '  ℹ 无需合并 (无匹配的 merge manifest)\n';
        }
        if (mergeData.skipped && mergeData.skipped.length > 0) {
          for (var k = 0; k < mergeData.skipped.length; k++) {
            fullReport += '  ⚠ 跳过 ' + mergeData.skipped[k].targetBoCode + ': ' + mergeData.skipped[k].reason + '\n';
          }
        }
        if (mergeData.errors && mergeData.errors.length > 0) {
          for (var k = 0; k < mergeData.errors.length; k++) {
            fullReport += '  ❌ ' + (mergeData.errors[k].targetBoCode || mergeData.errors[k].manifest) + ': ' + mergeData.errors[k].error + '\n';
          }
        }
      } else {
        fullReport += '  ⚠ 合并失败\n';
      }
    } catch (e) {
      fullReport += '  ❌ 合并异常: ' + e.message + '\n';
    }
    fullReport += '\n🎉 全量投影完成 (' + graphData.bos.length + ' BOs × ' + ptypes.length + ' 类型)。\n';
    showModal('🎯 全量投影 (' + graphData.bos.length + ' BOs)', fullReport, 'all_bos_projection.json');
  } catch (e) {
    showModal('⚠ 投影失败', '请确认 API 服务已启动\n\n' + (e.name === 'AbortError' ? '请求超时' : e.message), null);
  } finally {
    if (btn) { btn.innerHTML = oldHtml; btn.disabled = false; }
  }
}

async function generateAllDdl() {
  if (!graphData || !graphData.bos.length) return;
  var btn = document.querySelector('.global-actions button[onclick*="generateAllDdl"]');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ DDL中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/ddl', 120000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    if (!resp.ok) {
      var err = await resp.json();
      throw new Error(err.error || '未知错误');
    }
    var fileResp = await fetchWithTimeout(API_BASE + '/api/file?type=ddl', 30000);
    var output, fileName;
    if (fileResp.ok) {
      var fileData = await fileResp.json();
      output = fileData.content;
      fileName = fileData.fileName || '_all_tables.sql';
    } else {
      var data = await resp.json();
      output = (data.stdout || '') + (data.stderr ? '\n' + data.stderr : '');
      fileName = '_all_tables.sql';
    }
    showModal('🗄️ 全量 DDL (' + graphData.bos.length + ' BOs)', output, fileName, 'generated-sql/_all_tables.sql');
  } catch (e) {
    showModal('⚠ DDL 生成失败', '请确认 API 服务已启动\n\n' + (e.name === 'AbortError' ? '请求超时 (120s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function inspectAllDatabases() {
  if (!graphData || !graphData.bos.length) return;
  var cfg = loadDbConfig();
  var dbConfig = (cfg.host && cfg.database) ? cfg : null;
  var btn = document.querySelector('.global-actions button[onclick*="inspectAll"]');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 探查中…'; btn.disabled = true; }
  try {
    var fullReport = '=================================================================\n  Full Data Profiling Report — ALL ' + graphData.bos.length + ' BOs\n  Timestamp: ' + new Date().toLocaleString() + '\n=================================================================\n';
    for (var i = 0; i < graphData.bos.length; i++) {
      var bo = graphData.bos[i];
      fullReport += '\n── ' + bo.boName + ' (' + bo.boCode + ') ──\n';
      try {
        var resp = await fetchWithTimeout(API_BASE + '/api/inspect', 60000, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ boCode: bo.boCode, cmd: 'all', dbConfig }),
        });
        var data = await resp.json();
        fullReport += data.output || data.stderr || '(无输出)';
      } catch (e) {
        fullReport += '  ⚠ 探查失败: ' + e.message + '\n';
      }
    }
    fullReport += '\n🎉 All ' + graphData.bos.length + ' BOs profiling complete.\n';
    showModal('🔬 全量数据探查 (' + graphData.bos.length + ' BOs)', fullReport, 'all_bos_inspect.txt');
  } catch (e) {
    showModal('⚠ 探查失败', '请确认 API 服务已启动\n\n' + (e.name === 'AbortError' ? '请求超时 (60s/BO)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

// ── 单对象操作函数 ──────────────────────────────────────────
async function generatePublishedStateForSelected() {
  if (!selectedBoCode || !graphData) return;
  var bo = graphData.bos.find(function(x) { return x.boCode === selectedBoCode; });
  if (!bo) return;
  var btn = document.querySelector('.inspector-actions button[onclick*="generatePublishedStateForSelected"]');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 发布中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/publish', 60000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: selectedBoCode }),
    });
    if (!resp.ok) {
      var err = await resp.json();
      throw new Error(err.error || JSON.stringify(err));
    }
    var fileResp = await fetchWithTimeout(API_BASE + '/api/file?type=publish&boCode=' + encodeURIComponent(selectedBoCode), 30000);
    if (fileResp.ok) {
      var fileData = await fileResp.json();
      publishedStates[selectedBoCode] = fileData;
      showModal('📦 ' + bo.boName + ' — 发布态 Schema', JSON.stringify(fileData, null, 2), bo.boCode + '.schema-view.v2.json', 'metadata/release-time/' + bo.boCode + '/' + bo.boCode + '.schema-view.v2.json');
    } else {
      showModal('⚠ ' + bo.boName + ' — 发布完成但文件读取失败', '请检查 metadata/release-time/ 目录', null);
    }
  } catch (e) {
    showModal('⚠ 发布失败', '请确认 API 服务已启动\n\n' + (e.name === 'AbortError' ? '请求超时 (60s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function generatePspProjectionForSelected() {
  if (!selectedBoCode) return;
  var bo = graphData.bos.find(function(x) { return x.boCode === selectedBoCode; });
  if (!bo) return;
  var ptypes = getSelectedProjTypes();
  var PROJ_SUFFIX = { 'authz_bo_meta_model': 'authz_bo_meta_model.schema_json.v2.json', 'api-contract': 'api-contract.json', 'authz_projection': 'authz_projection.json', 'ui-model': 'ui-model.json' };
  var btn = document.querySelector('#panel-proj-dropdown .multi-select-trigger');
  var oldHtml = btn ? btn.innerHTML : '';
  if (btn) { btn.querySelector('#panel-proj-display').textContent = '⏳ 投影中…'; btn.disabled = true; }
  try {
    var fullReport = '';
    for (var j = 0; j < ptypes.length; j++) {
      var ptype = ptypes[j];
      try {
        var resp = await fetchWithTimeout(API_BASE + '/api/projection', 60000, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ boCode: selectedBoCode, projectionType: ptype }),
        });
        if (!resp.ok) {
          var err = await resp.json();
          fullReport += '\n⚠ ' + (PROJ_LABELS[ptype]||ptype) + ': ' + (err.error || '未知错误') + '\n';
          continue;
        }
        var suffix = PROJ_SUFFIX[ptype] || (ptype + '.json');
        var fileResp = await fetchWithTimeout(API_BASE + '/api/file?type=projection&boCode=' + encodeURIComponent(selectedBoCode) + '&projType=' + encodeURIComponent(ptype), 30000);
        if (fileResp.ok) {
          var fileData = await fileResp.json();
          fullReport += '\n✅ ' + (PROJ_LABELS[ptype]||ptype) + ' — projection-run-time/' + selectedBoCode + '/' + selectedBoCode + '.' + suffix + '\n' + JSON.stringify(fileData, null, 2) + '\n';
        } else {
          fullReport += '\n⚠ ' + (PROJ_LABELS[ptype]||ptype) + ': 文件读取失败\n';
        }
      } catch (e) {
        fullReport += '\n❌ ' + (PROJ_LABELS[ptype]||ptype) + ': ' + e.message + '\n';
      }
    }
    showModal('🎯 ' + bo.boName + ' — 投影 (' + ptypes.map(function(t){return PROJ_LABELS[t]||t;}).join('+') + ')', fullReport || '(无输出)', bo.boCode + '_projection.json');
  } catch (e) {
    showModal('⚠ 投影失败', '请确认 API 服务已启动 (python bo-api-server.py)\n\n' + (e.name === 'AbortError' ? '请求超时 (60s)' : e.message), null);
  } finally {
    if (btn) { btn.innerHTML = oldHtml; btn.disabled = false; }
  }
}

async function generateDdlForSelected() {
  if (!selectedBoCode) return;
  var bo = graphData.bos.find(function(x) { return x.boCode === selectedBoCode; });
  if (!bo) return;
  var btn = document.querySelector('.inspector-actions button[onclick*="generateDdlForSelected"]');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ DDL中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/ddl', 120000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: selectedBoCode }),
    });
    if (!resp.ok) {
      var err = await resp.json();
      throw new Error(err.error || '未知错误');
    }
    var filePath = 'generated-sql/V_' + selectedBoCode + '__create_tables.sql';
    var fileResp = await fetchWithTimeout(API_BASE + '/api/file?type=ddl&boCode=' + encodeURIComponent(selectedBoCode), 30000);
    var output, fileName;
    if (fileResp.ok) {
      var fileData = await fileResp.json();
      output = fileData.content;
      fileName = fileData.fileName || 'V_' + selectedBoCode + '__create_tables.sql';
    } else {
      var data = await resp.json();
      output = (data.stdout || '') + (data.stderr ? '\n' + data.stderr : '');
      fileName = 'V_' + selectedBoCode + '__create_tables.sql';
    }
    showModal('🗄️ ' + bo.boName + ' — DDL', output, fileName, filePath);
  } catch (e) {
    showModal('⚠ DDL 生成失败', '请确认 API 服务已启动\n\n' + (e.name === 'AbortError' ? '请求超时 (120s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function inspectDatabase() {
  if (!selectedBoCode) return;
  var bo = graphData.bos.find(function(x) { return x.boCode === selectedBoCode; });
  if (!bo) return;
  var btn = document.querySelector('.inspector-actions button[onclick*="inspectDatabase"]');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 探查中…'; btn.disabled = true; }
  try {
    var cfg = loadDbConfig();
    var dbConfig = (cfg.host && cfg.database) ? cfg : null;
    var resp = await fetchWithTimeout(API_BASE + '/api/inspect', 60000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: selectedBoCode, cmd: 'all', dbConfig }),
    });
    var data = await resp.json();
    showModal('🔬 ' + bo.boName + ' — 数据探查报告', data.output || data.stderr || JSON.stringify(data, null, 2), bo.boCode + '_inspect.txt');
  } catch (e) {
    showModal('⚠ 探查失败', '请确认 API 服务已启动 (python bo-api-server.py)\n\n' + (e.name === 'AbortError' ? '请求超时 (60s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function reparseGraphData() {
  var btn = document.getElementById('btn-reparse');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 解析中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/graph', 120000, { method: 'POST' });
    var data = await resp.json();
    if (!resp.ok) {
      var stderrInfo = data.stderr ? '\n\n── 服务器输出 (stderr) ──\n' + data.stderr : '';
      throw new Error(data.error || 'Unknown error' + stderrInfo);
    }
    if (network) { network.destroy(); network = null; }
    var panelEmpty = document.getElementById('panel-empty');
    var inspectorContent = document.getElementById('inspector-content');
    if (panelEmpty) panelEmpty.style.display = 'flex';
    if (inspectorContent) inspectorContent.style.display = 'none';
    selectedBoCode = null;
    var editLink = document.getElementById('link-edit-meta');
    if (editLink) { editLink.style.opacity = '0'; editLink.style.pointerEvents = 'none'; }
    document.getElementById('panel-bo-name').textContent = '选择一个业务对象 (BO)';
    document.getElementById('panel-bo-meta').textContent = '请通过左侧拓扑图谱选择对应的节点查看详细元数据定义。';
    document.getElementById('panel-frag-chips').innerHTML = '';
    await init();
    document.getElementById('status-nodes').textContent = data.boCount || graphData.bos.length;
    if (data.stderr) {
      showModal('⚠ 重构完成（有警告）', '✅ ' + data.boCount + ' BOs, ' + data.edgeCount + ' 条关系边\n\n部分文件存在问题：\n\n' + data.stderr, null);
    } else {
      showModal('✅ 重构完成', data.boCount + ' BOs, ' + data.edgeCount + ' edges — 一切正常', null);
    }
  } catch (e) {
    showModal('⚠ 重构解析失败', '请确认 API 服务已启动 (python bo-api-server.py)\n\n' + (e.name === 'AbortError' ? '请求超时 (120s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

// ── LLM 配置管理 (localStorage) ─────────────────────────────
var LLM_CONFIG_KEY = 'bo_gov_llm_config';
var DEFAULT_LLM_BASE = 'https://uniapi.kaijie.com.cn/v1';
var DEFAULT_LLM_MODEL = 'glm-5.2';

function getLlmConfig() {
  try {
    var raw = localStorage.getItem(LLM_CONFIG_KEY);
    if (raw) return JSON.parse(raw);
  } catch(e) {}
  return null;
}

function openLlmConfig() {
  var modal = document.getElementById('llm-config-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  var config = getLlmConfig() || {};
  document.getElementById('llm-enabled').checked = config.enabled !== false;
  document.getElementById('llm-api-key').value = config.apiKey || '';
  document.getElementById('llm-api-base').value = config.apiBase || DEFAULT_LLM_BASE;
  document.getElementById('llm-model').value = config.model || DEFAULT_LLM_MODEL;
  var status = document.getElementById('llm-config-status');
  if (status) { status.textContent = ''; status.className = ''; }
}

function closeLlmConfig() {
  var modal = document.getElementById('llm-config-modal');
  if (modal) modal.classList.add('hidden');
}

function saveLlmConfig() {
  var config = {
    enabled: document.getElementById('llm-enabled').checked,
    apiKey: document.getElementById('llm-api-key').value.trim(),
    apiBase: document.getElementById('llm-api-base').value.trim() || DEFAULT_LLM_BASE,
    model: document.getElementById('llm-model').value || DEFAULT_LLM_MODEL,
  };
  try {
    localStorage.setItem(LLM_CONFIG_KEY, JSON.stringify(config));
    var status = document.getElementById('llm-config-status');
    if (status) {
      status.textContent = '✅ 配置已保存（存储在浏览器 localStorage）';
      status.className = 'db-config-status success';
    }
    setTimeout(closeLlmConfig, 800);
  } catch(e) {
    var status2 = document.getElementById('llm-config-status');
    if (status2) { status2.textContent = '❌ 保存失败: ' + e.message; status2.style.color = '#fca5a5'; }
  }
}

// ── 工具链操作 (E1/E2/E3) ──────────────────────────────────
async function runLinkCandidates() {
  var btn = document.getElementById('btn-link-candidates');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 生成中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/tools/link-candidates', 120000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    var data = await resp.json();
    var report = (data.stdout || '') + (data.stderr ? '\n\n── 诊断 ──\n' + data.stderr : '');
    showModal(data.ok ? '✅ LINK 候选生成完成' : '❌ 生成失败', report || '(无输出)', 'crm-link-candidates.json');
  } catch (e) {
    showModal('⚠ 操作失败', '请确认 API 服务已启动 (python bo-api-server.py)\n\n' + (e.name === 'AbortError' ? '请求超时 (120s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function runExprAst() {
  var btn = document.getElementById('btn-expr-ast');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 转换中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/tools/expr-ast', 120000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ writeBack: true }),
    });
    var data = await resp.json();
    var report = (data.stdout || '') + (data.stderr ? '\n\n── 诊断 ──\n' + data.stderr : '');
    showModal(data.ok ? '✅ exprAst 转换+回写完成' : '❌ 转换失败', report || '(无输出)', 'crm-expr-ast-report.json');
  } catch (e) {
    showModal('⚠ 操作失败', '请确认 API 服务已启动 (python bo-api-server.py)\n\n' + (e.name === 'AbortError' ? '请求超时 (120s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function runOntologyPublish() {
  var btn = document.getElementById('btn-ontology-publish');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 发布中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/tools/ontology-publish', 120000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    var data = await resp.json();
    var report = (data.stdout || '') + (data.stderr ? '\n\n── 诊断 ──\n' + data.stderr : '');
    showModal(data.ok ? '✅ 本体发布完成' : '❌ 发布失败', report || '(无输出)', 'ontology-publish-report.txt');
  } catch (e) {
    showModal('⚠ 操作失败', '请确认 API 服务已启动 (python bo-api-server.py)\n\n' + (e.name === 'AbortError' ? '请求超时 (120s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

async function runValidation() {
  var btn = document.getElementById('btn-validate');
  var oldText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ 校验中…'; btn.disabled = true; }
  try {
    var resp = await fetchWithTimeout(API_BASE + '/api/validate', 120000, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    var data = await resp.json();
    var stdout = data.stdout || '';
    var stderr = data.stderr || '';
    var report = (stdout + '\n' + stderr).trim() || '(无输出)';
    var ok = data.ok !== false && resp.ok;
    showModal(ok ? '✅ 全局校验通过' : '❌ 校验发现问题', report, 'deep_check_report.txt');
  } catch (e) {
    showModal('⚠ 校验失败', '请确认 API 服务已启动 (python bo-api-server.py)\n\n' + (e.name === 'AbortError' ? '请求超时 (120s)' : e.message), null);
  } finally {
    if (btn) { btn.textContent = oldText; btn.disabled = false; }
  }
}

// ── 本体推理 Dry-Run ───────────────────────────────────────
async function runDryRun(boCode, scenario, objId) {
  var outputEl = document.getElementById('dryrun-output-' + boCode);
  // 数据图谱面板使用统一的 dryrun-output-all 容器
  if (!outputEl) outputEl = document.getElementById('dryrun-output-all');
  if (outputEl) { outputEl.textContent = '⏳ 正在执行 dry-run: ' + scenario + '…'; outputEl.style.color = '#60a5fa'; }

  // 'all' 展开为全部子场景依次执行（保留兼容，当前 UI 已无按钮调用此路径）
  var scenarios;
  if (scenario === 'all') {
    scenarios = ['reasoning-chain', 'customer-360', 'opportunity-intelligence', 'pipeline-coverage', 'opportunity-timeline', 'customer-activity-window'];
  } else {
    scenarios = [scenario];
  }

  var allOutput = '';
  try {
    var llmConfig = getLlmConfig();
    for (var si = 0; si < scenarios.length; si++) {
      var sc = scenarios[si];
      var label;
      if (objId) {
        label = '⏳ (' + (si+1) + '/' + scenarios.length + ') 对记录 ' + objId + ' 执行 ' + sc + '…';
      } else if (boCode === 'all') {
        label = '⏳ 全量 ' + sc + '（遍历全部 demo 记录中，请稍候…）';
      } else {
        label = '⏳ (' + (si+1) + '/' + scenarios.length + ') 执行 ' + sc + '…';
      }
      if (outputEl) { outputEl.textContent = label; }
      var body = { boCode: boCode, scenario: sc, llmConfig: llmConfig, scenarioDir: currentScenarioDir };
      if (objId) body.obj_id = objId;
      var resp = await fetch(API_BASE + '/api/ontology/derive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      var data = await resp.json();
      var part = (data.stdout || data.output || data.message || '');
      if (data.stderr) part += '\n── 诊断 ──\n' + data.stderr;
      if (!part.trim()) part = JSON.stringify(data, null, 2);
      allOutput += '════════════════════════════════════════\n';
      allOutput += '  📌 ' + sc + '\n';
      allOutput += '════════════════════════════════════════\n';
      allOutput += part + '\n\n';
    }
    if (outputEl) {
      // 生成 AI 总结后拼接输出
      if (outputEl) { outputEl.textContent = '⏳ 推理完成，正在生成 AI 总结…'; outputEl.style.color = '#60a5fa'; }
      var summary = await summarizeDryRun(allOutput.trim(), scenario, boCode);

      // 从原始输出中分离 LLM 叙事化报告，放到 AI 总结之后
      var llmNarrative = '';
      var cleanedOutput = allOutput.trim();
      var llmMarker = '🤖 LLM 叙事化报告';
      var llmIdx = cleanedOutput.indexOf(llmMarker);
      if (llmIdx >= 0) {
        llmNarrative = cleanedOutput.substring(llmIdx);  // 从标记开始到末尾
        cleanedOutput = cleanedOutput.substring(0, llmIdx).trim();  // JSON 部分
      }

      var finalOutput = '';
      if (summary) {
        finalOutput += '┌─────────────────────────────────────────┐\n';
        finalOutput += '  🤖 AI 总结\n';
        finalOutput += '└─────────────────────────────────────────┘\n';
        finalOutput += summary + '\n\n';
      }
      if (llmNarrative) {
        finalOutput += llmNarrative + '\n\n';
      }
      finalOutput += cleanedOutput;
      outputEl.textContent = finalOutput.trim();
      outputEl.style.color = '#34d399';
    }
  } catch (e) {
    if (outputEl) {
      outputEl.textContent = '⚠ API 服务未启动 (python bo-api-server.py)\n\n可在终端直接运行:\n  python bo-ontology-demo-eval.py --scenario ' + scenario + ' --bo ' + boCode;
      outputEl.style.color = '#fbbf24';
    }
  }
}

// ── 导出推理结果为 Markdown ──────────────────────────────────
function exportDryRunMd(boCode) {
  var outputEl = document.getElementById('dryrun-output-' + boCode);
  if (!outputEl) return;
  var text = outputEl.textContent || '';
  if (!text.trim() || text.indexOf('点击上方按钮') === 0) {
    alert('请先执行推理演算，再导出结果。');
    return;
  }
  var now = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  var filename = 'dryrun-' + boCode + '-' + now + '.md';
  var blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── AI 总结推理结果 ─────────────────────────────────────────
async function summarizeDryRun(rawOutput, scenario, boCode) {
  var llmConfig = getLlmConfig();
  if (!llmConfig || llmConfig.enabled === false || !llmConfig.apiKey) return '';

  var scenarioLabel = {
    'reasoning-chain': '完整推理链',
    'customer-360': '客户360派生',
    'opportunity-intelligence': '商机智能派生',
    'opportunity-timeline': '商机阶段时间线',
    'customer-activity-window': '客户活动窗口指标',
    'all': '全量推理',
    'eval-rules': '规则评估'
  }[scenario] || scenario;

  var prompt = '以下是CRM本体推理引擎的「' + scenarioLabel + '」dry-run 输出结果。'
    + '请用3-5句话总结核心内容，包括：处理了什么数据、得出了什么关键指标或结论、发现了什么风险或异常。'
    + '要求简洁、专业、一目了然，不要罗列细节，只提炼要点。输出纯文本，不要用 markdown 格式。\n\n'
    + rawOutput.substring(0, 4000);

  try {
    var resp = await fetch((llmConfig.apiBase || 'https://uniapi.kaijie.com.cn/v1') + '/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + llmConfig.apiKey },
      body: JSON.stringify({
        model: llmConfig.model || 'glm-5.2',
        messages: [
          { role: 'system', content: '你是一位CRM数据分析助手。请简洁地总结推理引擎的输出结果核心内容。' },
          { role: 'user', content: prompt }
        ],
        temperature: 0.3,
        max_tokens: 500,
      }),
    });
    var data = await resp.json();
    var content = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
    return content ? content.trim() : '';
  } catch (e) {
    return '';
  }
}

// ── 规则 exprAst Dry-Run 评估 ───────────────────────────────
async function runRuleEval(boCode) {
  var outputEl = document.getElementById('dryrun-output-' + boCode);
  if (outputEl) { outputEl.textContent = '⏳ 正在评估规则 exprAst…'; outputEl.style.color = '#60a5fa'; }

  try {
    var resp = await fetch(API_BASE + '/api/ontology/eval-rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: boCode, scenarioDir: currentScenarioDir }),
    });
    var data = await resp.json();
    if (outputEl) {
      var output = (data.stdout || '');
      if (data.stderr) output += '\n\n── 诊断 ──\n' + data.stderr;
      if (!output.trim()) output = JSON.stringify(data, null, 2);
      // 生成 AI 总结
      if (outputEl) { outputEl.textContent = '⏳ 规则评估完成，正在生成 AI 总结…'; outputEl.style.color = '#60a5fa'; }
      var summary = await summarizeDryRun(output, 'eval-rules', boCode);
      var finalOutput = '';
      if (summary) {
        finalOutput += '┌─────────────────────────────────────────┐\n';
        finalOutput += '  🤖 AI 总结\n';
        finalOutput += '└─────────────────────────────────────────┘\n';
        finalOutput += summary + '\n\n';
      }
      finalOutput += output;
      outputEl.textContent = finalOutput;
      outputEl.style.color = resp.ok ? '#34d399' : '#fca5a5';
    }
  } catch (e) {
    if (outputEl) {
      outputEl.textContent = '⚠ API 服务未启动 (python bo-api-server.py)\n\n可在终端直接运行:\n  python bo-ontology-demo-eval.py --eval-rules ' + boCode;
      outputEl.style.color = '#fbbf24';
    }
  }
}

// ── 导出推理结果为 Markdown ──────────────────────────────────
