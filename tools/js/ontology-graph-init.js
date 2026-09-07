/* ═══════════════════════════════════════════════════════════════════
   ontology-graph-init.js — Search, event binding, startup entry
   Dependencies: shared-dicts.js, ontology-graph-engine.js
   ═══════════════════════════════════════════════════════════════════ */

// ── 搜索 ────────────────────────────────────────────────────
function setupEvents() {
  var searchBox = document.getElementById('search-box');
  if (searchBox) {
    searchBox.addEventListener('input', function() {
      var q = searchBox.value.toLowerCase().trim();
      if (!q) {
        allNodes.forEach(function(n) { allNodes.update({ id: n.id, hidden: false }); });
        allEdges.forEach(function(e) { allEdges.update({ id: e.id, hidden: false }); });
        if (network) network.fit({ animation: true });
        return;
      }
      var matchedBoCodes = new Set();
      graphData.bos.forEach(function(bo) {
        var match = bo.boName.toLowerCase().includes(q) || bo.boCode.toLowerCase().includes(q);
        if (!match) {
          match = bo.entities.some(function(ent) {
            return ent.name.toLowerCase().includes(q) || ent.code.toLowerCase().includes(q) ||
              ent.attributes.some(function(attr) { return attr.name.toLowerCase().includes(q) || attr.code.toLowerCase().includes(q); });
          });
        }
        if (match) matchedBoCodes.add(bo.boCode);
      });
      allNodes.forEach(function(n) {
        allNodes.update({ id: n.id, hidden: !matchedBoCodes.has(n.id) });
      });
      allEdges.forEach(function(e) {
        allEdges.update({ id: e.id, hidden: !matchedBoCodes.has(e.from) && !matchedBoCodes.has(e.to) });
      });
      if (matchedBoCodes.size === 1) {
        network.focus([...matchedBoCodes][0], { scale: 1.4, animation: true });
      } else if (matchedBoCodes.size > 1) {
        network.fit({ animation: true });
      }
    });
  }

  // Modal 点击 backdrop 关闭
  document.getElementById('json-modal').addEventListener('click', function(e) { if (e.target === this) closeModal(); });
  document.getElementById('db-config-modal').addEventListener('click', function(e) { if (e.target === this) closeDbConfig(); });

  // 点击外部关闭下拉
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.multi-select-dropdown')) {
      document.querySelectorAll('.multi-select-options.open').forEach(function(o) { o.classList.remove('open'); });
      document.querySelectorAll('.dropdown-arrow.open').forEach(function(a) { a.classList.remove('open'); });
    }
  });
}

// ── 启动 ────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function() {
  var params = new URLSearchParams(window.location.search);
  if (params.get('mode') === 'data') {
    initDataGraphMode();
  } else {
    init();
  }
});
