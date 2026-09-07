/* ═══════════════════════════════════════════════════════════════════
   data-graph-engine.js — 数据知识图谱引擎
   从 /api/data-graph 加载实例数据，构建 vis.js 图谱
   依赖: shared-dicts.js, vis-network
   ═══════════════════════════════════════════════════════════════════ */

// ── 数据图谱全局状态 ────────────────────────────────────────
var dataGraphData = null;       // 后端返回的 {nodes, edges, boConfig, ...}
var dataNetwork = null;          // vis.js Network 实例
var dataAllNodes = null;         // vis.DataSet nodes
var dataAllEdges = null;         // vis.DataSet edges
var dataSelectedNode = null;     // 当前选中的节点
var dataGraphMode = false;       // 是否在数据图谱模式
var dataMasterNodes = null;      // 全量节点（用于图层过滤）
var dataMasterEdges = null;      // 全量边（用于图层过滤）
var dataVisibleBOs = {};         // BO 可见性开关 {boCode: true/false}

// 从节点数据动态派生 BO 颜色/标签映射（替代硬编码）
function getDataBOColor(boCode) {
  // 优先从已有节点中查找
  if (dataGraphData && dataGraphData.nodes) {
    for (var i = 0; i < dataGraphData.nodes.length; i++) {
      var n = dataGraphData.nodes[i];
      if (n.boCode === boCode && n.color && n.color.border) return n.color.border;
    }
  }
  return '#71717a';
}

function getDataBOLabel(boCode) {
  // 优先从已有节点中查找
  if (dataGraphData && dataGraphData.nodes) {
    for (var i = 0; i < dataGraphData.nodes.length; i++) {
      var n = dataGraphData.nodes[i];
      if (n.boCode === boCode) {
        // 从 title 提取 BO 中文名（title 格式："icon label: ..."）
        var title = n.title || '';
        var parts = title.split(': ');
        if (parts.length >= 2) {
          // 去掉 icon 前缀
          var label = parts[0].replace(/^[^\s]+ /, '');
          if (label) return label;
        }
      }
    }
  }
  return boCode;
}

// 获取所有有数据的 BO 列表（去重，按 boCode 排序）
function getDataBOList() {
  if (!dataGraphData || !dataGraphData.nodes) return [];
  var boMap = {};
  dataGraphData.nodes.forEach(function(n) {
    var bo = n.boCode;
    if (bo && !boMap[bo]) {
      boMap[bo] = {
        boCode: bo,
        label: getDataBOLabel(bo),
        color: getDataBOColor(bo),
        count: 0,
      };
    }
    if (bo && boMap[bo]) boMap[bo].count++;
  });
  return Object.values(boMap).sort(function(a, b) { return a.boCode.localeCompare(b.boCode); });
}

// ── 在新页签中打开数据图谱 ──────────────────────────────────
function openDataGraphInNewTab() {
  window.open('bo-ontology-graph.html?mode=data', '_blank');
}

// ── 切换到数据图谱模式 ──────────────────────────────────────
async function switchToDataGraph() {
  dataGraphMode = true;

  // 隐藏本体图谱画布控件
  if (network) { network.destroy(); network = null; }

  // 隐藏 BO Tab，取消选中
  var tabBo = document.getElementById('top-tab-bo');
  if (tabBo) tabBo.style.display = 'none';
  dataSelectedNode = null;

  // 加载数据图谱
  await loadDataGraph();

  // 显示数据图谱全局面板
  var pane5 = document.getElementById('tab-pane-5');
  if (pane5) pane5.innerHTML = buildDataGraphPanel();
  switchTopTab('reasoning');

  // 隐藏本体图层控制面板和图例
  var layerToggle = document.getElementById('layer-toggle');
  if (layerToggle) layerToggle.style.display = 'none';
  var legend = document.getElementById('legend');
  if (legend) legend.style.display = 'none';
}

// ── 切换回本体图谱模式 ──────────────────────────────────────
async function switchToOntologyGraph() {
  // 独立页签模式：直接跳转回本体图谱主页
  var params = new URLSearchParams(window.location.search);
  if (params.get('mode') === 'data') {
    window.location.href = 'bo-ontology-graph.html';
    return;
  }

  dataGraphMode = false;

  // 销毁数据图谱
  if (dataNetwork) { dataNetwork.destroy(); dataNetwork = null; }

  // 恢复图层控制
  var layerToggle = document.getElementById('layer-toggle');
  if (layerToggle) layerToggle.style.display = '';
  var legend = document.getElementById('legend');
  if (legend) legend.style.display = '';

  // 重新初始化本体图谱
  await init();
}

// ── 加载数据图谱 ────────────────────────────────────────────
async function loadDataGraph() {
  var canvas = document.getElementById('graph-canvas');
  if (!canvas) return;

  try {
    var resp = await fetch(API_BASE + '/api/data-graph', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenarioDir: currentScenarioDir }),
    });
    dataGraphData = await resp.json();

    if (dataGraphData.error) {
      canvas.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-tertiary);font-size:13px">⚠ ' + dataGraphData.error + '</div>';
      return;
    }

    buildDataGraph();
    updateDataGraphStatus();
  } catch (e) {
    canvas.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-tertiary);font-size:13px">⚠ 加载失败: ' + e.message + '<br>请确认 API 服务已启动</div>';
  }
}

// ── 构建数据图谱 vis.js ─────────────────────────────────────
function buildDataGraph() {
  var nodes = dataGraphData.nodes || [];
  var edges = dataGraphData.edges || [];

  // 为 vis.js 格式化节点
  var visNodes = nodes.map(function(n) {
    return {
      id: n.id,
      label: n.label,
      shape: n.shape || 'dot',
      size: n.size || 18,
      font: n.font || { size: 11, color: '#e4e4e7' },
      color: n.color,
      borderWidth: n.borderWidth || 2,
      title: n.title,
      _boCode: n.boCode,
      _recordId: n.recordId,
      _recordData: n.recordData,
    };
  });

  var visEdges = edges.map(function(e) {
    return {
      id: e.id,
      from: e.from,
      to: e.to,
      label: e.label,
      arrows: e.arrows || 'to',
      color: e.color,
      dashes: e.dashes,
      font: { size: 9, color: '#71717a', background: 'rgba(9,9,11,0.85)', strokeWidth: 0 },
      smooth: { type: 'curvedCW', roundness: 0.15 },
    };
  });

  dataAllNodes = new vis.DataSet(visNodes);
  dataAllEdges = new vis.DataSet(visEdges);
  dataMasterNodes = visNodes;
  dataMasterEdges = visEdges;

  // 初始化 BO 可见性（全部可见）
  dataVisibleBOs = {};
  getDataBOList().forEach(function(bo) {
    dataVisibleBOs[bo.boCode] = true;
  });

  var container = document.getElementById('graph-canvas');
  var data = { nodes: dataAllNodes, edges: dataAllEdges };

  var options = {
    nodes: { shape: 'dot', scaling: { min: 12, max: 28 } },
    edges: { width: 1.2, selectionWidth: 2, smooth: { type: 'curvedCW', roundness: 0.15 } },
    physics: {
      enabled: true,
      barnesHut: { gravitationalConstant: -8000, springLength: 120, springConstant: 0.04, damping: 0.4 },
      stabilization: { iterations: 150, updateInterval: 25 },
    },
    interaction: { hover: true, tooltipDelay: 200, navigationButtons: false, keyboard: false },
    layout: { improvedLayout: true },
  };

  dataNetwork = new vis.Network(container, data, options);

  // 点击节点 → 更新推理演算上下文，显示数据详情 Tab
  dataNetwork.on('click', function(params) {
    if (params.nodes.length > 0) {
      var nodeId = params.nodes[0];
      var node = dataAllNodes.get(nodeId);
      if (node) {
        dataSelectedNode = node;
        // 显示"数据详情"Tab 按钮（不自动切换）
        var tabBo = document.getElementById('top-tab-bo');
        if (tabBo) { tabBo.style.display = ''; tabBo.textContent = '📋 ' + (node.label || nodeId); }
        // 渲染数据详情到 bo pane
        var topBo = document.getElementById('top-pane-bo');
        if (topBo) topBo.innerHTML = buildDataRecordDetailPane(node);
        // 刷新推理演算面板（按钮会带上 objId）
        var pane5 = document.getElementById('tab-pane-5');
        if (pane5) pane5.innerHTML = buildDataGraphPanel();
      }
    } else {
      dataSelectedNode = null;
      // 取消选中 → 隐藏数据详情 Tab
      var tabBo = document.getElementById('top-tab-bo');
      if (tabBo) tabBo.style.display = 'none';
      // 刷新推理演算面板（按钮恢复全量模式）
      var pane5 = document.getElementById('tab-pane-5');
      if (pane5) pane5.innerHTML = buildDataGraphPanel();
    }
  });

  // 自动冻结（与物理引擎按钮状态同步）
  dataNetwork.once('stabilizationIterationsDone', function() {
    setTimeout(function() {
      if (dataNetwork) { dataNetwork.setOptions({ physics: { enabled: false } }); physicsFrozen = true; }
      var b = document.getElementById('btn-physics');
      if (b) { b.classList.remove('active'); b.innerHTML = '🧊'; b.title = '物理引擎已冻结 (点击释放)'; }
      document.getElementById('status-physics').textContent = 'Frozen';
    }, 1000);
  });
}

// ── 更新状态栏 ──────────────────────────────────────────────
function updateDataGraphStatus() {
  var statusNodes = document.getElementById('status-nodes');
  if (statusNodes && dataGraphData) {
    statusNodes.textContent = dataGraphData.summary.totalNodes + ' 条记录';
  }
}

// ── 数据图谱图层过滤（按 BO 显示/隐藏）─────────────────────
function toggleDataBO(boCode) {
  dataVisibleBOs[boCode] = !dataVisibleBOs[boCode];
  applyDataLayerFilter();
}

function applyDataLayerFilter() {
  if (!dataMasterNodes || !dataNetwork) return;
  var visNodes = dataMasterNodes.filter(function(n) {
    return dataVisibleBOs[n._boCode || n.boCode] !== false;
  });
  var visNodeIds = {};
  visNodes.forEach(function(n) { visNodeIds[n.id] = true; });
  var visEdges = dataMasterEdges.filter(function(e) {
    if (!visNodeIds[e.from] || !visNodeIds[e.to]) return false;
    return true;
  });
  dataAllNodes = new vis.DataSet(visNodes);
  dataAllEdges = new vis.DataSet(visEdges);
  dataNetwork.setData({ nodes: dataAllNodes, edges: dataAllEdges });
}

// ── 数据图谱面板（右侧 Inspector）────────────────────────────
function buildDataGraphPanel() {
  var h = '';
  h += '<div style="padding:16px 20px 12px;border-bottom:1px solid var(--border-strong)">';
  h += '<div style="font-weight:500;font-size:13px;color:var(--text-secondary)">📊 数据知识图谱 — 实例视图</div>';
  h += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:4px">展示 demo-data 中的实例记录及其跨 BO 引用关系。点击节点查看详情。</div>';
  h += '</div>';

  h += '<div style="padding:16px 20px">';

  // ── BO 图层控制（类似本体图谱的图层切换）──
  var boList = getDataBOList();
  if (boList.length > 0) {
    h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🎛️ BO 图层控制</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + boList.length + ' 类</span></div><div class="entity-attrs open">';
    h += '<div style="padding:8px 12px;display:flex;flex-wrap:wrap;gap:6px">';
    boList.forEach(function(bo) {
      var checked = dataVisibleBOs[bo.boCode] !== false ? 'checked' : '';
      h += '<label class="layer-toggle-item" style="font-size:11px;cursor:pointer;display:inline-flex;align-items:center;gap:4px">';
      h += '<input type="checkbox" ' + checked + ' onchange="toggleDataBO(\'' + bo.boCode + '\')"> ';
      h += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + bo.color + '33;border:1px solid ' + bo.color + '"></span>';
      h += bo.label + ' <span style="color:var(--text-tertiary);font-size:10px">(' + bo.count + ')</span>';
      h += '</label>';
    });
    h += '</div></div></div>';
  }

  // ── 统计概览 ──
  if (dataGraphData && dataGraphData.summary) {
    var s = dataGraphData.summary;
    h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">📈 统计概览</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + s.totalNodes + ' 节点 / ' + s.totalEdges + ' 边</span></div><div class="entity-attrs open">';
    h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;padding:8px 12px">';
    // 只显示有数据的 BO（count > 0）
    boList.forEach(function(bo) {
      h += '<div><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + bo.color + ';margin-right:4px"></span>' + bo.label + ': <b>' + bo.count + '</b></div>';
    });
    h += '</div></div></div>';
  }

  // ── 图例 ──
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🎨 图例</b></span></div><div class="entity-attrs">';
  h += '<div style="padding:8px 12px;display:flex;flex-wrap:wrap;gap:8px">';
  boList.forEach(function(bo) {
    h += '<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--text-secondary)"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + bo.color + '33;border:1px solid ' + bo.color + '"></span>' + bo.label + '</span>';
  });
  h += '</div>';
  h += '<div style="padding:4px 12px 8px;font-size:10px;color:var(--text-tertiary)">';
  h += '<div><span style="color:#4f46e588">━━</span> 外键引用 &nbsp;&nbsp; <span style="color:#71717a88">┄┄</span> 逻辑关联</div>';
  h += '</div>';
  h += '</div></div>';

  // ── 推理演算 (Dry-Run) ──
  var selNode = dataSelectedNode;
  var selBo = selNode ? selNode._boCode : 'all';
  var selObjId = selNode ? selNode._recordId : null;
  var scopeLabel = selNode ? ('仅对 ' + getDataBOLabel(selBo) + ':' + selObjId) : '遍历全部 demo 记录';
  var scopeTitle = selNode ? ('仅对当前选中记录 ' + selObjId) : '遍历全部 demo 记录';

  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🧪 推理演算 (Dry-Run)</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + scopeLabel + '</span></div><div class="entity-attrs open">';

  // ── 场景选择器 ──
  h += '<div class="scenario-selector-container">' + (typeof buildScenarioSelector === 'function' ? buildScenarioSelector() : '') + '</div>';

  var makeBtn = function(scenario, icon, label, title, isPrimary) {
    var args = selObjId
      ? ("('" + selBo + "','" + scenario + "','" + selObjId + "')")
      : ("('" + selBo + "','" + scenario + "')");
    var cls = isPrimary ? 'btn-icon-text btn-primary' : 'btn-icon-text';
    var extraStyle = isPrimary ? '' : 'border-color:var(--border-strong)';
    return '<button class="' + cls + '" onclick="runDryRun' + args + '" style="font-size:11px;' + extraStyle + '" title="' + scopeTitle + '，' + title + '">' + icon + ' ' + label + '</button>';
  };

  h += '<div style="padding:10px 12px 6px;display:flex;flex-wrap:wrap;gap:8px">';
  h += makeBtn('customer-360', '📊', '客户360视图', 'AST 求值输出健康度、流失风险、下一步最佳行动');
  h += makeBtn('opportunity-intelligence', '📈', '商机智能视图', 'AST 求值输出赢单概率、阶段流速、竞争风险等级、推荐推进动作');
  h += makeBtn('pipeline-coverage', '📐', '管道覆盖率', '汇率折算统一CNY口径，硬数据校验输出覆盖率、缺口金额、风险等级');
  h += makeBtn('opportunity-timeline', '⏱️', '商机阶段时间线', '回放阶段变更事件，输出停留天数和阶段流速');
  h += makeBtn('customer-activity-window', '📅', '客户活动窗口', '按时间窗口统计活动次数和最近活动天数');
  h += '</div>';
  h += '<div style="margin:2px 12px;border-top:1px solid var(--border-strong)"></div>';
  h += '<div style="padding:6px 12px 10px;display:flex;flex-wrap:wrap;gap:8px">';
  h += makeBtn('reasoning-chain', '🧠', '完整推理链', '基于本体依赖关系自动编排：LINK发现关联BO → 拓扑排序解析依赖 → 依次AST求值 → RULE → ACTION_CHAIN → LLM叙事', true);
  h += '<button class="btn-icon-text" onclick="runRuleEval(\'all\')" style="font-size:11px;border-color:#f97316;color:#fb923c" title="使用各 BO 的 RULE Fragment 中定义的业务规则，对所有 demo 数据实例逐条校验，输出通过/违规/跳过统计">⚖️ 规则合规评估</button>';
  h += '</div><div id="dryrun-output-all" style="padding:8px 12px;font-size:11px;color:var(--text-tertiary);min-height:40px;background:var(--bg-base);border-radius:4px;margin:8px 12px;border:1px solid var(--border-strong);font-family:monospace;white-space:pre-wrap">点击上方按钮触发推理演算 — ' + scopeTitle + '…</div>';
  h += '<div style="padding:0 12px 12px;text-align:right"><button class="btn-icon-text" onclick="exportDryRunMd(\'all\')" style="font-size:11px;border-color:var(--border-strong)">📥 导出 MD</button></div>';
  h += '</div></div>';

  // ── 操作按钮 ──
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🔧 视图操作</b></span></div><div class="entity-attrs">';
  h += '<div style="padding:10px 12px;display:flex;flex-wrap:wrap;gap:8px">';
  h += '<button class="btn-icon-text" onclick="dataNetwork.fit({animation:true})" style="font-size:11px;border-color:var(--border-strong)">📐 适应视图</button>';
  h += '<button class="btn-icon-text" onclick="reloadDataGraph()" style="font-size:11px;border-color:var(--border-strong)">🔄 重新加载</button>';
  h += '<button class="btn-icon-text" onclick="switchToOntologyGraph()" style="font-size:11px;border-color:var(--accent);color:var(--accent)">🧠 切换到本体图谱</button>';
  h += '</div></div></div>';

  h += '</div>';
  return h;
}

// ── 重新加载数据图谱 ────────────────────────────────────────
async function reloadDataGraph() {
  if (dataNetwork) { dataNetwork.destroy(); dataNetwork = null; }
  await loadDataGraph();
  var pane5 = document.getElementById('tab-pane-5');
  if (pane5) pane5.innerHTML = buildDataGraphPanel();
}

// ── 数据详情独立面板（渲染到 #top-pane-bo，独立 Tab）───
function buildDataRecordDetailPane(node) {
  var rec = node._recordData || {};
  var boCode = node._boCode;
  var boLabel = getDataBOLabel(boCode);
  var boColor = getDataBOColor(boCode);

  var h = '';
  h += '<div class="inspector-header">';
  h += '<div class="bo-title-bar">';
  h += '<div style="display:flex;align-items:center;gap:10px">';
  h += '<div id="panel-bo-name">' + (node.label || node._recordId) + '</div>';
  h += '</div>';
  h += '<div id="panel-bo-meta"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + boColor + ';margin-right:4px"></span>' + boLabel + ' <code>' + boCode + ':' + node._recordId + '</code></div>';
  h += '</div>';
  h += '<div class="frag-chips" id="panel-frag-chips"><span class="frag-chip" style="background:' + boColor + '22;color:' + boColor + ';border-color:' + boColor + '33">数据记录</span></div>';
  h += '<div class="inspector-actions">';
  h += '<button class="btn-icon-text" onclick="dataNetwork.fit({animation:true})" title="适应视图">📐 适应</button>';
  h += '<button class="btn-icon-text" onclick="switchToOntologyGraph()" title="切换回本体业务对象图谱">🧠 本体图谱</button>';
  h += '</div>';
  h += '</div>';

  h += '<div style="padding:16px 20px;overflow-y:auto;max-height:calc(100vh - 140px)">';

  // ── 字段详情 ──
  h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">📋 字段信息</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + Object.keys(rec).length + ' 字段</span></div><div class="entity-attrs open">';
  var fields = Object.keys(rec).sort();
  fields.forEach(function(key) {
    var val = rec[key];
    var valStr = '';
    var isLink = (key.endsWith('_id') || key.endsWith('_ids_snapshot') || key === 'currency');
    if (val === null || val === undefined) {
      valStr = '<span style="color:var(--text-tertiary)">null</span>';
    } else if (typeof val === 'object') {
      var jsonStr = JSON.stringify(val);
      valStr = '<span style="color:#a78bfa;font-family:monospace;font-size:10px">' + jsonStr.substring(0, 60) + (jsonStr.length > 60 ? '...' : '') + '</span>';
    } else if (typeof val === 'number') {
      valStr = '<span style="color:#2dd4bf">' + val + '</span>';
    } else if (typeof val === 'boolean') {
      valStr = '<span style="color:#f59e0b">' + val + '</span>';
    } else {
      valStr = '<span style="color:var(--text-secondary)">' + String(val).substring(0, 80) + (String(val).length > 80 ? '...' : '') + '</span>';
    }
    var linkIcon = isLink ? ' <span style="color:#f59e0b;font-size:9px">🔗</span>' : '';
    h += '<div class="attr-row"><span style="color:var(--text-tertiary);font-family:monospace;width:20px;text-align:right;flex-shrink:0">│</span><span class="attr-name" style="font-size:11px">' + key + linkIcon + '</span><span class="attr-type" style="font-size:10px">' + valStr + '</span></div>';
  });
  h += '</div></div>';

  // ── 关联记录 ──
  var relatedEdges = (dataGraphData.edges || []).filter(function(e) { return e.from === node.id || e.to === node.id; });
  if (relatedEdges.length > 0) {
    h += '<div class="entity-card"><div class="entity-header" onclick="toggleEntity(this)"><span class="expand-icon open">▶</span><span style="flex:1"><b style="color:var(--text-primary);font-size:13px">🔗 关联记录</b></span><span style="font-size:10px;color:var(--text-tertiary)">' + relatedEdges.length + ' 条</span></div><div class="entity-attrs open">';
    relatedEdges.forEach(function(edge) {
      var isOut = edge.from === node.id;
      var targetId = isOut ? edge.to : edge.from;
      var targetNode = dataAllNodes.get(targetId);
      var targetLabel = targetNode ? targetNode.label : targetId;
      var targetBo = targetNode ? targetNode._boCode : '';
      var targetBoLabel = getDataBOLabel(targetBo);
      var targetColor = getDataBOColor(targetBo);
      h += '<div class="list-item"><div class="list-item-header"><span class="item-title" style="cursor:pointer;color:var(--accent)" onclick="focusDataNode(\'' + targetId + '\')">' + (isOut ? '→ ' : '← ') + targetLabel + '</span><span class="item-code">' + targetBoLabel + '</span></div><div class="item-meta"><span class="tag" style="color:' + targetColor + '">' + (edge.label || '') + '</span>' + (edge.dashes ? '<span class="tag" style="color:#71717a">逻辑关联</span>' : '<span class="tag" style="color:#f59e0b">外键</span>') + '</div></div>';
    });
    h += '</div></div>';
  }

  h += '</div>';
  return h;
}

// ── 聚焦到某个数据节点 ──────────────────────────────────────
function focusDataNode(nodeId) {
  if (!dataNetwork) return;
  dataNetwork.selectNodes([nodeId]);
  dataNetwork.focus(nodeId, { scale: 1.3, animation: true });
  var node = dataAllNodes.get(nodeId);
  if (node) {
    dataSelectedNode = node;
    var tabBo = document.getElementById('top-tab-bo');
    if (tabBo) { tabBo.style.display = ''; tabBo.textContent = '📋 ' + (node.label || nodeId); }
    var topBo = document.getElementById('top-pane-bo');
    if (topBo) topBo.innerHTML = buildDataRecordDetailPane(node);
  }
}

// ── 独立数据图谱模式初始化（?mode=data 页签入口）──────────
function initDataGraphMode() {
  dataGraphMode = true;

  // 隐藏本体图谱专属 UI
  var tabBo = document.getElementById('top-tab-bo');
  if (tabBo) tabBo.style.display = 'none';

  var topTabsNav = document.getElementById('top-tabs-nav');
  if (topTabsNav) {
    // 隐藏"本体推理" tab，改为纯数据图谱面板
    var reasoningTab = document.getElementById('top-tab-reasoning');
    if (reasoningTab) { reasoningTab.style.display = 'none'; }
    var dataTitle = document.createElement('button');
    dataTitle.className = 'tab-btn active';
    dataTitle.id = 'top-tab-data';
    dataTitle.textContent = '📊 数据知识图谱';
    topTabsNav.appendChild(dataTitle);
  }

  // 隐藏本体图层控制面板和图例
  var layerToggle = document.getElementById('layer-toggle');
  if (layerToggle) layerToggle.style.display = 'none';
  var legend = document.getElementById('legend');
  if (legend) legend.style.display = 'none';

  // 隐藏本体专属按钮
  var btnsToHide = ['btn-new-bo', 'btn-reparse', 'btn-validate', 'btn-link-candidates', 'btn-expr-ast', 'btn-ontology-publish', 'btn-data-graph'];
  btnsToHide.forEach(function(id) {
    var btn = document.getElementById(id);
    if (btn) btn.style.display = 'none';
  });

  // 显示数据图谱专属按钮
  var btnNewData = document.getElementById('btn-new-data');
  if (btnNewData) btnNewData.style.display = '';

  // 改造搜索框 → 搜索数据实例记录
  var searchBox = document.getElementById('search-box');
  if (searchBox) {
    searchBox.placeholder = '搜索数据记录 (ID / 名称 / 字段值) ...';
    // 移除本体图谱绑定的 input 事件（设为空克隆）
    var newSearchBox = searchBox.cloneNode(true);
    searchBox.parentNode.replaceChild(newSearchBox, searchBox);
    searchBox = newSearchBox;
    // 改为按数据图谱记录搜索
    searchBox.addEventListener('input', function() {
      var q = this.value.toLowerCase().trim();
      if (!dataNetwork || !dataMasterNodes) return;
      if (!q) {
        // 恢复全部可见
        dataAllNodes = new vis.DataSet(dataMasterNodes);
        dataAllEdges = new vis.DataSet(dataMasterEdges);
        dataNetwork.setData({ nodes: dataAllNodes, edges: dataAllEdges });
        dataNetwork.fit({ animation: true });
        return;
      }
      var matchedIds = {};
      dataMasterNodes.forEach(function(n) {
        var t = n.title || '';
        var l = (n.label || '').toLowerCase();
        if (l.indexOf(q) >= 0) { matchedIds[n.id] = true; return; }
        // 搜 recordData 中的字段值
        var rd = n._recordData;
        if (rd) {
          var matched = false;
          Object.keys(rd).forEach(function(k) {
            var v = rd[k];
            if (v !== null && v !== undefined && String(v).toLowerCase().indexOf(q) >= 0) matched = true;
          });
          if (matched) matchedIds[n.id] = true;
        }
      });
      var filteredNodes = dataMasterNodes.filter(function(n) { return matchedIds[n.id]; });
      var filteredEdges = dataMasterEdges.filter(function(e) { return matchedIds[e.from] || matchedIds[e.to]; });
      dataAllNodes = new vis.DataSet(filteredNodes);
      dataAllEdges = new vis.DataSet(filteredEdges);
      dataNetwork.setData({ nodes: dataAllNodes, edges: dataAllEdges });
      if (Object.keys(matchedIds).length === 1) {
        dataNetwork.focus(Object.keys(matchedIds)[0], { scale: 1.4, animation: true });
      } else if (Object.keys(matchedIds).length > 1) {
        dataNetwork.fit({ animation: true });
      }
    });
  }

  // 隐藏本体专属的分隔线及后续按钮（全量发布/投影/DDL/探查）
  var globalActions = document.querySelector('.global-actions');
  if (globalActions) {
    var allChildren = globalActions.children;
    var hideNext = false;
    for (var i = 0; i < allChildren.length; i++) {
      var el = allChildren[i];
      var txt = el.textContent || '';
      if (txt.indexOf('全量发布') !== -1 || txt.indexOf('全量投影') !== -1 || txt.indexOf('全量DDL') !== -1 || txt.indexOf('全量探查') !== -1 || hideNext) {
        el.style.display = 'none';
      }
      if (el.tagName === 'DIV' && el.style.width === '1px') {
        hideNext = true;
      }
    }
  }

  // 修改底部状态栏标识
  var statusRight = document.getElementById('status-right');
  if (statusRight) {
    statusRight.innerHTML = '<span>📊 数据图谱模式</span><span>UI Version: 3.0</span>';
  }

  // 启动：加载数据图谱
  document.title = 'EAP | Data Graph';
  loadDataGraph().then(function() {
    var pane5 = document.getElementById('tab-pane-5');
    if (pane5) pane5.innerHTML = buildDataGraphPanel();
  });
}

// ── 新建数据记录 ────────────────────────────────────────────
var newDataBoCache = null;  // 缓存 /api/bo-info 返回的 BO 元数据

function openNewDataForm() {
  // 1. 填充 BO 下拉
  var sel = document.getElementById('new-data-bo');
  if (!sel) return;
  sel.innerHTML = '<option value="">— 选择业务对象 —</option>';
  var boList = getDataBOList();
  boList.forEach(function(bo) {
    var opt = document.createElement('option');
    opt.value = bo.boCode;
    opt.textContent = bo.label + ' (' + bo.boCode + ')';
    sel.appendChild(opt);
  });
  // 如果当前有选中节点，预选其 BO
  if (dataSelectedNode && dataSelectedNode._boCode) {
    sel.value = dataSelectedNode._boCode;
  }
  // 2. 显示弹窗
  document.getElementById('new-data-modal').classList.remove('hidden');
  document.getElementById('new-data-fields').innerHTML = '<div style="font-size:11px;color:var(--text-tertiary);text-align:center;padding:20px">请先选择业务对象</div>';
  document.getElementById('new-data-status').textContent = '';
  document.getElementById('btn-new-data-submit').disabled = true;
  newDataBoCache = null;
  // 如果已预选，自动触发
  if (sel.value) onNewDataBoChange();
  // 点击 backdrop 关闭
  document.getElementById('new-data-modal').addEventListener('click', function(e) {
    if (e.target === document.getElementById('new-data-modal')) closeNewDataForm();
  });
}

function closeNewDataForm() {
  document.getElementById('new-data-modal').classList.add('hidden');
}

async function onNewDataBoChange() {
  var boCode = document.getElementById('new-data-bo').value;
  var fieldsEl = document.getElementById('new-data-fields');
  var submitBtn = document.getElementById('btn-new-data-submit');
  if (!boCode) {
    fieldsEl.innerHTML = '<div style="font-size:11px;color:var(--text-tertiary);text-align:center;padding:20px">请先选择业务对象</div>';
    submitBtn.disabled = true;
    newDataBoCache = null;
    return;
  }
  // 加载 BO 元数据获取属性列表
  fieldsEl.innerHTML = '<div style="font-size:11px;color:var(--text-tertiary);text-align:center;padding:20px">⏳ 加载 ' + boCode + ' 元数据…</div>';
  try {
    var resp = await fetch(API_BASE + '/api/fragment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: boCode, metaType: 'MODEL' }),
    });
    var frag = await resp.json();
    newDataBoCache = frag;
    renderNewDataFields(boCode, frag);
    submitBtn.disabled = false;
  } catch (e) {
    fieldsEl.innerHTML = '<div style="font-size:11px;color:#ef4444;text-align:center;padding:20px">加载失败: ' + e.message + '</div>';
    submitBtn.disabled = true;
  }
}

function renderNewDataFields(boCode, frag) {
  var fieldsEl = document.getElementById('new-data-fields');
  if (!fieldsEl) return;

  // 从 fragment 中提取 MODEL content
  var modelContent = (frag && frag.content) ? frag.content : (frag || {});
  var entities = modelContent.entities || [];
  if (!entities.length) {
    // fallback：从 dataGraphData 已有节点的 recordData 提取字段名
    fieldsEl.innerHTML = renderNewDataFieldsFromRecords(boCode);
    return;
  }

  var h = '';
  var autoIdHint = '（自动生成，留空则自动分配）';
  entities.forEach(function(ent) {
    var attrs = ent.attributes || [];
    if (attrs.length > 0) {
      h += '<div style="font-size:10px;color:var(--text-tertiary);margin-bottom:2px;font-weight:600">📦 ' + (ent.name || ent.code) + '</div>';
      attrs.forEach(function(attr) {
        var isId = (attr.code === 'id');
        var isRequired = attr.required || isId || (attr.semanticRole && attr.semanticRole === 'BUSINESS_KEY');
        var isRef = !!attr.crossBoRef;
        var placeholder = isId ? autoIdHint : attr.name || '';
        var labelExtra = isRequired ? ' <span style="color:#ef4444">*</span>' : '';
        var refHint = '';
        if (isRef && attr.crossBoRef) {
          refHint = ' <span style="font-size:9px;color:#f59e0b">→ ' + attr.crossBoRef.refBoCode + '.' + (attr.crossBoRef.refFieldCode || 'id') + '</span>';
        }
        h += '<div style="display:flex;flex-direction:column;gap:3px">';
        h += '<label style="font-size:10px;color:var(--text-secondary)">' + (attr.name || attr.code) + labelExtra + refHint + ' <code style="font-size:9px;color:var(--text-tertiary)">' + attr.code + '</code></label>';
        h += '<input class="new-data-field" data-code="' + attr.code + '" data-type="' + (attr.type || 'string') + '" ';
        h += 'style="background:var(--bg-base);border:1px solid var(--border-strong);color:var(--text-primary);padding:6px 10px;border-radius:4px;font-family:monospace;font-size:11px;outline:none" ';
        h += 'type="text" placeholder="' + placeholder + '" /></div>';
      });
    }
  });

  fieldsEl.innerHTML = h || '<div style="font-size:11px;color:var(--text-tertiary);text-align:center;padding:20px">该 BO 暂无实体模型定义</div>';
}

function renderNewDataFieldsFromRecords(boCode) {
  // Fallback: 从已有记录中提取字段
  var fields = {};
  if (dataGraphData && dataGraphData.nodes) {
    dataGraphData.nodes.forEach(function(n) {
      if (n.boCode === boCode && n.recordData) {
        Object.keys(n.recordData).forEach(function(k) { fields[k] = true; });
      }
    });
  }
  var keys = Object.keys(fields).sort();
  if (!keys.length) return '<div style="font-size:11px;color:var(--text-tertiary);text-align:center;padding:20px">无可用字段信息</div>';
  var h = '';
  keys.forEach(function(k) {
    var isId = (k === 'id');
    h += '<div style="display:flex;flex-direction:column;gap:3px">';
    h += '<label style="font-size:10px;color:var(--text-secondary)">' + k + (isId ? ' <span style="color:#ef4444">*</span>' : '') + '</label>';
    h += '<input class="new-data-field" data-code="' + k + '" data-type="string" ';
    h += 'style="background:var(--bg-base);border:1px solid var(--border-strong);color:var(--text-primary);padding:6px 10px;border-radius:4px;font-family:monospace;font-size:11px;outline:none" ';
    h += 'type="text" placeholder="' + (isId ? '（自动生成）' : '') + '" /></div>';
  });
  return h;
}

async function submitNewData() {
  var boCode = document.getElementById('new-data-bo').value;
  if (!boCode) return;
  var statusEl = document.getElementById('new-data-status');
  var submitBtn = document.getElementById('btn-new-data-submit');

  // 收集字段值
  var record = {};
  var inputs = document.querySelectorAll('#new-data-fields .new-data-field');
  inputs.forEach(function(inp) {
    var code = inp.getAttribute('data-code');
    var type = inp.getAttribute('data-type');
    var val = inp.value.trim();
    if (!val) return;
    // 类型转换
    if (type === 'int' || type === 'integer' || type === 'number' || type === 'decimal') {
      var num = Number(val);
      record[code] = isNaN(num) ? val : num;
    } else if (type === 'boolean') {
      record[code] = val === 'true' || val === '1';
    } else {
      record[code] = val;
    }
  });

  if (Object.keys(record).length === 0) {
    statusEl.textContent = '⚠ 请至少填写一个字段';
    statusEl.style.color = '#f59e0b';
    return;
  }

  submitBtn.disabled = true;
  statusEl.textContent = '⏳ 正在创建…';
  statusEl.style.color = '#60a5fa';

  try {
    var resp = await fetch(API_BASE + '/api/data/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boCode: boCode, record: record, scenarioDir: currentScenarioDir }),
    });
    var result = await resp.json();
    if (result.ok) {
      statusEl.textContent = '✅ 创建成功！ID: ' + result.recordId + ' | 文件: ' + result.file;
      statusEl.style.color = '#34d399';
      // 刷新数据图谱
      setTimeout(function() {
        reloadDataGraph();
        closeNewDataForm();
      }, 1500);
    } else {
      statusEl.textContent = '❌ ' + (result.error || '未知错误');
      statusEl.style.color = '#ef4444';
      submitBtn.disabled = false;
    }
  } catch (e) {
    statusEl.textContent = '❌ 请求失败: ' + e.message;
    statusEl.style.color = '#ef4444';
    submitBtn.disabled = false;
  }
}
