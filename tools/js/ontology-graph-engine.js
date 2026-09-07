/* ═══════════════════════════════════════════════════════════════════
   ontology-graph-engine.js — Graph construction, Vis.js config, physics
   Dependencies: shared-dicts.js
   ═══════════════════════════════════════════════════════════════════ */

// ── 页面单例检测：相同 URL 只保留一个页签 ──────────────────
(function() {
  var CH = 'bo-gov-singleton-' + location.href.replace(/[^a-zA-Z0-9]/g,'_');
  var bc;
  try { bc = new BroadcastChannel(CH); } catch(e) { return; }
  bc.onmessage = function(e) {
    if (e.data && e.data.type === 'hello') {
      bc.postMessage({ type: 'ack' });
      try { window.focus(); } catch(ignore) {}
    }
  };
  setTimeout(function() {
    bc.postMessage({ type: 'hello' });
    var responded = false;
    var onAck = function(e) {
      if (e.data && e.data.type === 'ack') { responded = true; }
    };
    bc.addEventListener('message', onAck);
    setTimeout(function() {
      bc.removeEventListener('message', onAck);
      if (responded) {
        document.body.innerHTML = '<div style="position:fixed;inset:0;background:#09090b;color:#a1a1aa;display:flex;align-items:center;justify-content:center;font-size:14px;font-family:sans-serif;z-index:99999">已有打开的页签，正在自动切换...</div>';
        setTimeout(function() { window.close(); }, 200);
      }
    }, 600);
  }, 100);
})();

// ── 全局状态 ────────────────────────────────────────────────
var graphData = null, network = null, allNodes = null, allEdges = null;
var currentScenarioDir = 'education';
var selectedBoCode = null, currentTab = 0;
var publishedStates = {};
var modalJsonData = null, modalDownloadName = '', modalFilePath = '';
var physicsFrozen = false, autoFreezeTimer = null;
var edgeLabelsVisible = true;
var visibleLayers = { BO_REF: true, LINK: true, CONSISTENCY: true, DISPLAY: true, DERIVATION: false, ACTION_CHAIN: false, TEMPORAL_BADGE: true };
var masterNodes = null, masterEdges = null;
var API_BASE = 'http://127.0.0.1:8765';
var DB_CONFIG_KEY = 'bo_gov_db_config';
var PROJ_LABELS = { 'authz_bo_meta_model':'支持权限引擎', 'api-contract':'API契约', 'ui-model':'UI模型' };
var PROJ_EMOJI = { 'authz_bo_meta_model':'🔐', 'api-contract':'📡', 'ui-model':'🖥️' };

// ── 工具函数 ────────────────────────────────────────────────
function fName(bo, ec, fc) { var e=bo.entities.find(function(x){return x.code===ec}); if(!e) return fc; var a=e.attributes.find(function(x){return x.code===fc}); return a?a.name:fc; }
function eName(bo, ec) { var e=bo.entities.find(function(x){return x.code===ec}); return e?e.name:ec; }

// ── 物理引擎控制 ────────────────────────────────────────────
function _activeNetwork() {
  return (typeof dataGraphMode !== 'undefined' && dataGraphMode) ? dataNetwork : network;
}
function freezeGraph() {
  physicsFrozen = true;
  var net = _activeNetwork();
  if (net) net.setOptions({ physics: { enabled: false } });
  var b = document.getElementById('btn-physics');
  if (b) { b.classList.remove('active'); b.innerHTML = '🧊'; b.title = '物理引擎已冻结 (点击释放)'; }
  document.getElementById('status-physics').textContent = 'Frozen';
}
function thawGraph() {
  physicsFrozen = false;
  var net = _activeNetwork();
  if (net) net.setOptions({ physics: { enabled: true } });
  var b = document.getElementById('btn-physics');
  if (b) { b.classList.add('active'); b.innerHTML = '⚡'; b.title = '物理引擎运行中 (点击冻结)'; }
  document.getElementById('status-physics').textContent = 'Running';
  if (autoFreezeTimer) clearTimeout(autoFreezeTimer);
  autoFreezeTimer = setTimeout(function() { if (!physicsFrozen) freezeGraph(); }, 5000);
}

// ── 连线标签显隐 ──────────────────────────────────────────
function toggleEdgeLabels() {
  edgeLabelsVisible = !edgeLabelsVisible;
  var btn = document.getElementById('btn-labels');
  var isDataMode = (typeof dataGraphMode !== 'undefined' && dataGraphMode);
  var edgeDS = isDataMode ? (typeof dataAllEdges !== 'undefined' ? dataAllEdges : null) : allEdges;
  if (!edgeDS) return;
  var edgeList = edgeDS.get();
  if (edgeLabelsVisible) {
    edgeList.forEach(function(e) { edgeDS.update({ id: e.id, font: { size: 9, color: isDataMode ? '#71717a' : '#cbd5e1', background: 'rgba(9,9,11,0.9)', strokeWidth: isDataMode ? 0 : 1, strokeColor: 'rgba(9,9,11,0.9)' } }); });
    if (btn) { btn.classList.add('active'); btn.title = '隐藏连线标签'; }
  } else {
    edgeList.forEach(function(e) { edgeDS.update({ id: e.id, font: { size: 0 } }); });
    if (btn) { btn.classList.remove('active'); btn.title = '显示连线标签'; }
  }
}

// ── Tab 切换 ────────────────────────────────────────────────
function switchTab(idx) {
  currentTab = idx;
  var subTabs = document.querySelectorAll('#top-pane-bo .tabs-nav .tab-btn');
  subTabs.forEach(function(b, i) { b.classList.toggle('active', i === idx); });
  for (var i = 0; i < 5; i++) {
    var pane = document.getElementById('tab-pane-' + i);
    if (pane) pane.classList.toggle('active', i === idx);
  }
}

// ── 初始化 ──────────────────────────────────────────────────
async function init() {
  try {
    var resp = await fetch('graph-data.json');
    graphData = await resp.json();
    document.getElementById('status-nodes').textContent = graphData.bos.length;
    buildGraph();
    setupEvents();
    // 加载演示场景目录列表
    if (typeof loadScenarioDirs === 'function') await loadScenarioDirs();
    // 初始化全局本体推理视图（未选中 BO 时显示）
    var pane5 = document.getElementById('tab-pane-5');
    if (pane5 && typeof buildTab5GlobalReasoning === 'function') {
      pane5.innerHTML = buildTab5GlobalReasoning();
    }
  } catch (err) {
    console.error('graph-data.json 加载失败:', err);
  }
}

function buildGraph() {
  var nodes = [];
  var edges = [];
  var boMap = {};
  var temporalBadges = graphData.temporalBadges || {};

  graphData.bos.forEach(function(bo) {
    var totalAttrs = bo.entities.reduce(function(s,e) { return s + e.attributes.length; }, 0);
    var size = Math.max(35, 25 + totalAttrs * 0.5);
    boMap[bo.boCode] = bo;

    var typeColor = bo.objectType === 'MASTER_DETAIL'
      ? { bg: '#4f46e5', border: '#3730a3', hl: '#818cf8', hover: '#6366f1' }
      : bo.objectType === 'TREE'
      ? { bg: '#d97706', border: '#92400e', hl: '#fbbf24', hover: '#f59e0b' }
      : { bg: '#0d9488', border: '#0f766e', hl: '#2dd4bf', hover: '#14b8a6' };

    var entityNames = bo.entities.slice(0, 3).map(function(e) { return e.name; }).join(' · ');
    var moreHint = bo.entities.length > 3 ? ' +' + (bo.entities.length - 3) : '';

    var hasTemporal = temporalBadges[bo.boCode] && temporalBadges[bo.boCode].length > 0;
    nodes.push({
      id: bo.boCode,
      label: (hasTemporal && visibleLayers.TEMPORAL_BADGE ? '🕐 ' : '') + bo.boName,
      shape: 'box',
      size: size,
      font: { size: 12, face: 'Inter, Segoe UI, sans-serif', color: '#f4f4f5', multi: false, strokeWidth: 1, strokeColor: 'rgba(9,9,11,0.8)' },
      color: {
        background: typeColor.bg, border: typeColor.border,
        highlight: { background: typeColor.hl, border: typeColor.border },
        hover: { background: typeColor.hover, border: typeColor.hl },
      },
      borderWidth: 2,
      mass: 1 + totalAttrs * 0.1,
      boData: bo,
      nodeLayer: 'BO_REF',
    });
  });

  // ── 派生对象虚拟节点 ──
  (graphData.derivedObjects || []).forEach(function(dobj) {
    nodes.push({
      id: dobj.id,
      label: '📐 ' + dobj.name,
      shape: 'box',
      size: 30,
      font: { size: 11, face: 'Inter, Segoe UI, sans-serif', color: '#fed7aa', multi: false, strokeWidth: 1, strokeColor: 'rgba(9,9,11,0.8)' },
      color: { background: 'rgba(249,115,22,0.15)', border: '#f97316', highlight: { background: 'rgba(249,115,22,0.25)', border: '#fb923c' }, hover: { background: 'rgba(249,115,22,0.2)', border: '#fb923c' } },
      borderWidth: 2, shapeProperties: { borderDashes: [8, 4] }, mass: 1.5,
      derivedData: dobj, nodeLayer: 'DERIVATION',
    });
  });

  // ── 动作链虚拟节点 ──
  (graphData.actionChains || []).forEach(function(chain) {
    nodes.push({
      id: chain.id,
      label: '⚡ ' + chain.name,
      shape: 'diamond',
      size: 28,
      font: { size: 10, face: 'Inter, Segoe UI, sans-serif', color: '#ddd6fe', multi: false, strokeWidth: 1, strokeColor: 'rgba(9,9,11,0.8)' },
      color: { background: 'rgba(124,58,237,0.15)', border: '#7c3aed', highlight: { background: 'rgba(124,58,237,0.25)', border: '#8b5cf6' }, hover: { background: 'rgba(124,58,237,0.2)', border: '#8b5cf6' } },
      borderWidth: 2, mass: 1.5,
      chainData: chain, nodeLayer: 'ACTION_CHAIN',
    });
  });

  var selfRefCounter = {};
  graphData.edges.forEach(function(edge) {
    var isFlow = edge.referenceNature === 'BUSINESS_FLOW';
    var isSelf = edge.from === edge.to;
    if (isSelf) { selfRefCounter[edge.from] = (selfRefCounter[edge.from] || 0) + 1; }

    // EXPLICIT 链路（_ontology LINK fragment）用绿色突出显示
    var isExplicit = edge.linkSource === 'EXPLICIT';
    var isConsistency = edge.relationType === 'CONSISTENCY_RULE';
    var isDisplay = edge.relationType === 'DISPLAY_DEPENDENCY';
    var boRefLayer = isExplicit ? 'LINK' : isConsistency ? 'CONSISTENCY' : isDisplay ? 'DISPLAY' : 'BO_REF';
    var color = isExplicit
      ? { color: '#10b981', highlight: '#34d399', hover: '#6ee7b7' }
      : isConsistency
      ? { color: '#8b5cf6', highlight: '#a78bfa', hover: '#a78bfa' }
      : isDisplay
      ? { color: '#10b981', highlight: '#34d399', hover: '#6ee7b7' }
      : edge.relationType === 'ONE_TO_ONE'
      ? { color: '#ec4899', highlight: '#f472b6', hover: '#f9a8d4' }
      : isFlow
      ? { color: '#06b6d4', highlight: '#22d3ee', hover: '#67e8f9' }
      : { color: '#f59e0b', highlight: '#fbbf24', hover: '#fbbf24' };

    var selfAngle = isSelf ? (selfRefCounter[edge.from] * (2 * Math.PI / 4) + Math.PI / 6) : undefined;

    var linkLabel = edge.linkSource === 'EXPLICIT'
      ? (edge.linkName ? ' [' + edge.linkName + ']' : ' [显式链路]')
      : (edge.relationType === 'CONSISTENCY_RULE' ? ' [一致性规则]' : edge.relationType === 'DISPLAY_DEPENDENCY' ? ' [展示依赖]' : edge.relationType === 'ONE_TO_ONE' ? ' [1:1关联]' : isFlow ? ' [业务流]' : ' [N:1引用]');

    edges.push({
      from: edge.from, to: edge.to,
      label: isExplicit ? (edge.linkName||'') : (edge.fromField || ''),
      title: (edge.linkSource === 'EXPLICIT' ? '🔗 显式链路 · ' : (edge.linkSource === 'INFERRED' ? '🔍 派生链路 · ' : '')) + edge.from + ' → ' + edge.to + (edge.fromField ? ' (' + edge.fromField + ')' : '') + linkLabel,
      arrows: isSelf ? undefined : (edge.relationType === 'ONE_TO_ONE' ? 'to, from' : 'to'),
      color: color,
      width: isExplicit ? 3.5 : (isConsistency ? 3 : isDisplay ? 1.5 : 2.5),
      font: { size: 9, color: '#cbd5e1', background: 'rgba(9,9,11,0.9)', strokeWidth: 1, strokeColor: 'rgba(9,9,11,0.9)' },
      dashes: isExplicit ? [15, 5] : (isConsistency || isDisplay),
      smooth: isSelf ? { type: 'curvedCW', roundness: 0.5 } : { type: 'curvedCW', roundness: 0.3 },
      selfReference: isSelf ? { size: 45, angle: selfAngle } : undefined,
      edgeLayer: boRefLayer,
    });
  });

  // ── 本体边（DERIVATION / ACTION_CHAIN）──
  (graphData.ontologyEdges || []).forEach(function(oedge) {
    var isTrigger = oedge.linkSource === 'TRIGGERS';
    var isExecutes = oedge.linkSource === 'EXECUTES';
    var isDerDep = oedge.linkSource === 'DERIVATION_DEP';
    var edgeColor = (isTrigger || isExecutes)
      ? { color: '#7c3aed', highlight: '#8b5cf6', hover: '#a78bfa' }
      : { color: '#f97316', highlight: '#fb923c', hover: '#fdba74' };
    edges.push({
      from: oedge.from, to: oedge.to,
      label: oedge.label || '',
      title: oedge.linkSourceLabel + ': ' + oedge.from + ' → ' + oedge.to + (oedge.label ? ' (' + oedge.label + ')' : ''),
      arrows: 'to', color: edgeColor,
      width: isTrigger ? 2.5 : 2,
      font: { size: 9, color: '#cbd5e1', background: 'rgba(9,9,11,0.9)', strokeWidth: 1, strokeColor: 'rgba(9,9,11,0.9)' },
      dashes: (isDerDep || isExecutes) ? [10, 6] : false,
      smooth: { type: 'curvedCW', roundness: 0.3 },
      edgeLayer: (isTrigger || isExecutes) ? 'ACTION_CHAIN' : 'DERIVATION',
    });
  });

  // ── 存储主数组并按图层过滤 ──
  masterNodes = nodes;
  masterEdges = edges;
  var visNodes = nodes.filter(isNodeVisible);
  var visNodeIds = {};
  visNodes.forEach(function(n) { visNodeIds[n.id] = true; });
  var visEdges = edges.filter(function(e) {
    if (!isEdgeVisible(e)) return false;
    if (!visNodeIds[e.from] || !visNodeIds[e.to]) return false;
    return true;
  });

  allNodes = new vis.DataSet(visNodes);
  allEdges = new vis.DataSet(visEdges);

  var container = document.getElementById('graph-canvas');
  network = new vis.Network(container, { nodes: allNodes, edges: allEdges }, {
    physics: {
      enabled: true, solver: 'forceAtlas2Based',
      forceAtlas2Based: { gravitationalConstant: -25, centralGravity: 0.005, springLength: 180, springConstant: 0.05, damping: 0.7 },
      stabilization: { enabled: true, iterations: 250 },
    },
    interaction: { hover: true, tooltipDelay: 80, zoomView: true, dragView: true },
    nodes: { shapeProperties: { borderRadius: 8 } },
    edges: { smooth: { type: 'continuous' } },
  });

  var EDGE_FONT_DEFAULT = { size: 9, color: '#cbd5e1', background: 'rgba(9,9,11,0.9)', strokeWidth: 1, strokeColor: 'rgba(9,9,11,0.9)' };
  var EDGE_FONT_HL = { size: 10, color: '#fff', background: 'rgba(9,9,11,0.95)', strokeWidth: 2, strokeColor: '#60a5fa' };
  network.on('hoverEdge', function(params) {
    if (params.edge && edgeLabelsVisible) allEdges.update({ id: params.edge, font: EDGE_FONT_HL });
  });
  network.on('blurEdge', function(params) {
    if (params.edge && edgeLabelsVisible) allEdges.update({ id: params.edge, font: EDGE_FONT_DEFAULT });
  });

  network.on('click', function(params) {
    if (params.nodes.length > 0) {
      var nodeId = params.nodes[0];
      if (boMap[nodeId]) {
        showBoDetail(nodeId, boMap[nodeId]);
      } else {
        showOntologyNodeDetail(nodeId);
      }
    } else {
      // 点击空白区域：取消选中，回到全局推理视图
      deselectBo();
    }
  });

  network.on('hoverNode', function(params) {
    var tooltip = document.getElementById('tooltip');
    if (params.node) {
      var bo = boMap[params.node];
      var pos = network.canvasToDOM(network.getPosition(params.node));
      if (bo) {
        var totalAttrs2 = bo.entities.reduce(function(s,e) { return s + e.attributes.length; }, 0);
        tooltip.innerHTML = '<b>' + bo.boName + '</b> <small style="color:var(--text-tertiary)">' + bo.boCode + '</small><br>' +
          '<span style="color:var(--text-secondary)">' + (OBJTYPE_CN[bo.objectType]||bo.objectType) + '</span><br>' +
          bo.entities.length + ' 实体 · ' + totalAttrs2 + ' 属性 · ' + bo.operations.length + ' 操作 · ' + bo.rules.length + ' 规则';
      } else if (params.node.indexOf('derived:') === 0) {
        var dobj = (graphData.derivedObjects||[]).find(function(d){return d.id===params.node;});
        if (dobj) tooltip.innerHTML = '<b>📐 ' + dobj.name + '</b> <small style="color:var(--text-tertiary)">' + dobj.code + '</small><br><span style="color:#fb923c">派生对象</span><br>根 BO: ' + (dobj.rootBoCode||'—') + ' · ' + dobj.fieldCount + ' 字段';
      } else if (params.node.indexOf('chain:') === 0) {
        var chain = (graphData.actionChains||[]).find(function(c){return c.id===params.node;});
        if (chain) tooltip.innerHTML = '<b>⚡ ' + chain.name + '</b> <small style="color:var(--text-tertiary)">' + chain.code + '</small><br><span style="color:#a78bfa">动作链</span><br>触发: ' + (chain.triggerType||'—') + ' · ' + chain.stepCount + ' 步骤';
      } else { tooltip.style.opacity = '0'; return; }
      tooltip.style.opacity = '1';
      tooltip.style.left = (pos.x + 15) + 'px';
      tooltip.style.top = (pos.y + 15) + 'px';
    }
  });

  network.on('blurNode', function() { document.getElementById('tooltip').style.opacity = '0'; });

  autoFreezeTimer = setTimeout(function() { if (!physicsFrozen) freezeGraph(); }, 6000);

  network.on('doubleClick', function(params) {
    if (params.nodes.length > 0) network.focus(params.nodes[0], { scale: 1.3, animation: true });
  });
}

// ── 图层过滤 ────────────────────────────────────────────────
function isNodeVisible(n) {
  if (n.nodeLayer === 'DERIVATION') return visibleLayers.DERIVATION;
  if (n.nodeLayer === 'ACTION_CHAIN') return visibleLayers.ACTION_CHAIN;
  return true;
}

function isEdgeVisible(e) {
  if (e.edgeLayer === 'DERIVATION') return visibleLayers.DERIVATION;
  if (e.edgeLayer === 'ACTION_CHAIN') return visibleLayers.ACTION_CHAIN;
  if (e.edgeLayer === 'CONSISTENCY') return visibleLayers.CONSISTENCY;
  if (e.edgeLayer === 'DISPLAY') return visibleLayers.DISPLAY;
  if (e.edgeLayer === 'LINK') return visibleLayers.LINK;
  return visibleLayers.BO_REF;
}

function toggleLayer(layerName) {
  visibleLayers[layerName] = !visibleLayers[layerName];
  applyLayerFilter();
}

function applyLayerFilter() {
  if (!masterNodes || !network) return;
  var temporalBadges = graphData.temporalBadges || {};
  var visNodes = masterNodes.filter(isNodeVisible);
  // 更新 BO 标签的时序徽标
  visNodes = visNodes.map(function(n) {
    if (n.boData) {
      var hasTemporal = temporalBadges[n.boData.boCode] && temporalBadges[n.boData.boCode].length > 0;
      var newLabel = (hasTemporal && visibleLayers.TEMPORAL_BADGE ? '🕐 ' : '') + n.boData.boName;
      return Object.assign({}, n, { label: newLabel });
    }
    return n;
  });
  var visNodeIds = {};
  visNodes.forEach(function(n) { visNodeIds[n.id] = true; });
  var visEdges = masterEdges.filter(function(e) {
    if (!isEdgeVisible(e)) return false;
    if (!visNodeIds[e.from] || !visNodeIds[e.to]) return false;
    return true;
  });
  allNodes = new vis.DataSet(visNodes);
  allEdges = new vis.DataSet(visEdges);
  network.setData({ nodes: allNodes, edges: allEdges });
  if (!physicsFrozen) {
    if (autoFreezeTimer) clearTimeout(autoFreezeTimer);
    autoFreezeTimer = setTimeout(function() { if (!physicsFrozen) freezeGraph(); }, 6000);
  }
}

// ── 虚拟节点详情面板 ────────────────────────────────────────
function showOntologyNodeDetail(nodeId) {
  document.getElementById('panel-empty').style.display = 'none';
  document.getElementById('inspector-content').style.display = 'flex';
  var editLink = document.getElementById('link-edit-meta');
  if (editLink) { editLink.style.opacity = '0'; editLink.style.pointerEvents = 'none'; }

  if (nodeId.indexOf('derived:') === 0) {
    var dobj = (graphData.derivedObjects||[]).find(function(d){return d.id===nodeId;});
    if (!dobj) return;
    document.getElementById('panel-bo-name').textContent = '📐 ' + dobj.name;
    document.getElementById('panel-bo-meta').innerHTML = '<span style="color:#fb923c">' + dobj.code + '</span> <span style="color:var(--text-secondary)">派生对象 · ' + (dobj.objectKind||'') + '</span>';
    document.getElementById('panel-frag-chips').innerHTML = '<span class="frag-chip" style="background:rgba(249,115,22,0.15);color:#fb923c;border-color:rgba(249,115,22,0.2)">DERIVATION</span>';
    var h = '<div class="section"><div class="section-title">📋 概述</div><div class="info-block">' + (dobj.description||'') + '</div></div>';
    h += '<div class="section"><div class="section-title">🔗 依赖关系</div><div class="info-block">根 BO: <b>' + (dobj.rootBoCode||'—') + '</b>' + (dobj.rootEntityCode ? ' · 实体: <b>' + dobj.rootEntityCode + '</b>' : '') + '<br>';
    (dobj.dependencies||[]).forEach(function(dep) {
      h += '依赖: <b>' + dep.boCode + '</b> via ' + (dep.viaLink||'—') + (dep.required ? ' <span style="color:#ef4444">[必需]</span>' : ' <span style="color:var(--text-tertiary)">[可选]</span>') + '<br>';
    });
    h += '</div></div>';
    // 计算字段详情
    h += '<div class="section"><div class="section-title">📐 计算字段 (' + dobj.fieldCount + ')</div>';
    if (dobj.fields && dobj.fields.length > 0) {
      dobj.fields.forEach(function(f) {
        var exprStr = f.expression && Object.keys(f.expression).length > 0 ? JSON.stringify(f.expression) : '—';
        h += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + (f.name||f.code) + '</span><span class="item-code">' + f.code + '</span></div><div class="item-meta"><span class="tag" style="color:#0ea5e9">' + (f.type||'—') + '</span>' + (f.cacheable ? '<span class="tag" style="color:#34d399">可缓存</span>' : '') + (f.requiredForScoring ? '<span class="tag" style="color:#fbbf24">评分必需</span>' : '') + '</div>' + (exprStr !== '—' ? '<div style="font-size:10px;color:var(--text-tertiary);margin-top:4px;font-family:monospace;word-break:break-all">' + exprStr + '</div>' : '') + '</div>';
      });
    } else {
      h += '<div class="info-block">共 ' + dobj.fieldCount + ' 个计算字段</div>';
    }
    h += '</div>';
    // 物化与 API 暴露
    if (dobj.materialization || dobj.apiExposure) {
      h += '<div class="section"><div class="section-title">⚙️ 物化与暴露</div><div class="info-block">';
      if (dobj.materialization) h += '物化模式: <b>' + (dobj.materialization.mode||'—') + '</b>' + (dobj.materialization.ttlSeconds ? ' · TTL: ' + dobj.materialization.ttlSeconds + 's' : '') + '<br>';
      if (dobj.apiExposure) h += 'API 暴露: <b>' + (dobj.apiExposure.enabled ? '是' : '否') + '</b>' + (dobj.apiExposure.resourcePath ? ' · 路径: <code>' + dobj.apiExposure.resourcePath + '</code>' : '');
      h += '</div></div>';
    }
    document.getElementById('tab-pane-0').innerHTML = h;
    for (var i = 1; i < 6; i++) { var p = document.getElementById('tab-pane-'+i); if (p) p.innerHTML = '<div class="info-block">暂无数据</div>'; }
    switchTab(0);
  } else if (nodeId.indexOf('chain:') === 0) {
    var chain = (graphData.actionChains||[]).find(function(c){return c.id===nodeId;});
    if (!chain) return;
    document.getElementById('panel-bo-name').textContent = '⚡ ' + chain.name;
    document.getElementById('panel-bo-meta').innerHTML = '<span style="color:#a78bfa">' + chain.code + '</span> <span style="color:var(--text-secondary)">动作链 · ' + (chain.triggerType||'') + '</span>';
    document.getElementById('panel-frag-chips').innerHTML = '<span class="frag-chip" style="background:rgba(124,58,237,0.15);color:#a78bfa;border-color:rgba(124,58,237,0.2)">ACTION_CHAIN</span>';
    var h2 = '<div class="section"><div class="section-title">📋 概述</div><div class="info-block">' + (chain.description||'') + '</div></div>';
    h2 += '<div class="section"><div class="section-title">⚡ 触发条件</div><div class="info-block">触发类型: <b>' + (chain.triggerType||'—') + '</b><br>';
    if (chain.triggerBoCode) h2 += '触发 BO: <b>' + chain.triggerBoCode + '</b><br>';
    if (chain.triggerOperationCode) h2 += '触发操作: <b>' + chain.triggerOperationCode + '</b><br>';
    if (chain.triggerCron) h2 += 'Cron: <code>' + chain.triggerCron + '</code><br>';
    if (chain.triggerEventCode) h2 += '事件: <b>' + chain.triggerEventCode + '</b><br>';
    h2 += '执行模式: <b>' + (chain.executionMode||'—') + '</b></div></div>';
    h2 += '<div class="section"><div class="section-title">📝 执行步骤 (' + chain.stepCount + ')</div>';
    (chain.steps||[]).forEach(function(s, i) {
      h2 += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + (i+1) + '. ' + (s.name||'') + '</span><span class="item-code">' + (s.code||'') + '</span></div><div class="item-meta"><span class="tag">' + (s.stepType||'') + '</span>';
      var tgt = s.target || {};
      if (tgt.boCode) h2 += '<span class="tag">→ ' + tgt.boCode + '</span>';
      if (tgt.derivedCode) h2 += '<span class="tag">→ ' + tgt.derivedCode + '</span>';
      if (tgt.channel) h2 += '<span class="tag">📡 ' + tgt.channel + '</span>';
      if (s.failurePolicy) h2 += '<span class="tag" style="color:#fbbf24">' + s.failurePolicy + '</span>';
      h2 += '</div>';
      if (s.dependsOn && s.dependsOn.length > 0) h2 += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:4px">依赖: ' + s.dependsOn.join(', ') + '</div>';
      if (s.inputMapping && Object.keys(s.inputMapping).length > 0) {
        h2 += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:4px;font-family:monospace">输入映射: ' + JSON.stringify(s.inputMapping) + '</div>';
      }
      h2 += '</div>';
    });
    h2 += '</div>';
    document.getElementById('tab-pane-0').innerHTML = h2;
    for (var i = 1; i < 6; i++) { var p = document.getElementById('tab-pane-'+i); if (p) p.innerHTML = '<div class="info-block">暂无数据</div>'; }
    switchTab(0);
  }
}

// ── 导航到本体虚拟节点（派生对象 / 动作链）──
function navigateToOntologyNode(nodeId) {
  if (!nodeId) return;
  // 如果图层未开启，自动开启对应图层
  if (nodeId.indexOf('derived:') === 0 && !visibleLayers.DERIVATION) {
    visibleLayers.DERIVATION = true;
    var cb = document.querySelector('.layer-toggle-item input[onchange*="DERIVATION"]');
    if (cb) cb.checked = true;
    applyLayerFilter();
  }
  if (nodeId.indexOf('chain:') === 0 && !visibleLayers.ACTION_CHAIN) {
    visibleLayers.ACTION_CHAIN = true;
    var cb2 = document.querySelector('.layer-toggle-item input[onchange*="ACTION_CHAIN"]');
    if (cb2) cb2.checked = true;
    applyLayerFilter();
  }
  if (allNodes.get(nodeId)) {
    network.selectNodes([nodeId]);
    network.focus(nodeId, { scale: 1.3, animation: true });
  }
  showOntologyNodeDetail(nodeId);
}

// ── 时态时间线详情（在 inspector 面板中展示）──
function showTemporalTimelineDetail(timelineCode) {
  var tl = (graphData.temporalTimelines || []).find(function(t) { return t.timelineCode === timelineCode; });
  if (!tl) return;
  document.getElementById('panel-empty').style.display = 'none';
  document.getElementById('inspector-content').style.display = 'flex';
  var editLink = document.getElementById('link-edit-meta');
  if (editLink) { editLink.style.opacity = '0'; editLink.style.pointerEvents = 'none'; }

  document.getElementById('panel-bo-name').textContent = '⏱️ ' + tl.timelineName;
  document.getElementById('panel-bo-meta').innerHTML = '<span style="color:#2dd4bf">' + tl.timelineCode + '</span> <span style="color:var(--text-secondary)">时态时间线 · BO: ' + (tl.boCode||'—') + '</span>';
  document.getElementById('panel-frag-chips').innerHTML = '<span class="frag-chip" style="background:rgba(20,184,166,0.15);color:#2dd4bf;border-color:rgba(20,184,166,0.2)">TEMPORAL</span>';

  var h = '<div class="section"><div class="section-title">📋 概述</div><div class="info-block">' + (tl.description||'') + '</div></div>';
  h += '<div class="section"><div class="section-title">⚙️ 时间线配置</div><div class="info-block">';
  h += '所属 BO: <b>' + (tl.boCode||'—') + '</b> · 实体: <b>' + (tl.entityCode||'—') + '</b><br>';
  h += '标识字段: <code>' + (tl.identityField||'id') + '</code> · 时间字段: <code>' + (tl.timeField||'—') + '</code><br>';
  if (tl.stateField) h += '状态字段: <code>' + tl.stateField + '</code><br>';
  if (tl.statusField) h += '生命周期字段: <code>' + tl.statusField + '</code><br>';
  h += '</div></div>';

  // 事件源
  if (tl.eventSources && tl.eventSources.length > 0) {
    h += '<div class="section"><div class="section-title">📡 事件源 (' + tl.eventSources.length + ')</div>';
    tl.eventSources.forEach(function(es) {
      h += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + (es.eventType||'—') + '</span><span class="item-code">' + (es.sourceType||'') + '</span></div><div class="item-meta">';
      if (es.operationCode) h += '<span class="tag">操作: ' + es.operationCode + '</span>';
      if (es.entityCode) h += '<span class="tag">实体: ' + es.entityCode + '</span>';
      h += '</div></div>';
    });
    h += '</div>';
  }

  // 快照字段
  if (tl.snapshots && tl.snapshots.length > 0) {
    h += '<div class="section"><div class="section-title">📸 快照字段 (' + tl.snapshots.length + ')</div><div class="info-block" style="display:flex;flex-wrap:wrap;gap:6px">';
    tl.snapshots.forEach(function(s) { h += '<span class="tag" style="font-family:monospace">' + s + '</span>'; });
    h += '</div></div>';
  }

  // 指标
  if (tl.metrics && tl.metrics.length > 0) {
    h += '<div class="section"><div class="section-title">📊 时态指标 (' + tl.metrics.length + ')</div>';
    tl.metrics.forEach(function(m) {
      h += '<div class="list-item"><div class="list-item-header"><span class="item-title">' + (m.name||m.code) + '</span><span class="item-code">' + (m.code||'') + '</span></div><div class="item-meta"><span class="tag" style="color:#2dd4bf">' + (m.metricType||'—') + '</span>' + (m.unit ? '<span class="tag">单位: ' + m.unit + '</span>' : '') + '</div></div>';
    });
    h += '</div>';
  }

  document.getElementById('tab-pane-0').innerHTML = h;
  for (var i = 1; i < 6; i++) { var p = document.getElementById('tab-pane-'+i); if (p) p.innerHTML = '<div class="info-block">暂无数据</div>'; }
  switchTab(0);
}
