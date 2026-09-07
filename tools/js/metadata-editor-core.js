/* ═══════════════════════════════════════════════════════════════════
   metadata-editor-core.js — Constants, global state, tab switching,
   schema-driven form engine, JSON preview
   Dependencies: shared-dicts.js
   ═══════════════════════════════════════════════════════════════════ */

// ── Constants ──────────────────────────────────────────────────
var META_TYPES = ['MODEL','VALIDATION','SECURITY','RULE','VIEW','OPERATION','LINK','DERIVATION','TEMPORAL','ACTION_CHAIN'];
var UI_TABS = ['BO_INFO','API_CONFIG','MODEL','VALIDATION','SECURITY','RULE','VIEW','OPERATION','LINK','DERIVATION','TEMPORAL','ACTION_CHAIN'];
var META_COLORS = { BO_INFO:'#a1a1aa',MODEL:'#3b82f6',API_CONFIG:'#0ea5e9',VALIDATION:'#ef4444',SECURITY:'#f59e0b',RULE:'#8b5cf6',VIEW:'#10b981',OPERATION:'#0ea5e9',LINK:'#ec4899',DERIVATION:'#f97316',TEMPORAL:'#14b8a6',ACTION_CHAIN:'#7c3aed' };
var META_CN = { BO_INFO:'业务对象管理信息',MODEL:'模型',API_CONFIG:'API配置',VALIDATION:'校验',SECURITY:'安全',RULE:'规则',VIEW:'视图',OPERATION:'操作',LINK:'关系',DERIVATION:'派生',TEMPORAL:'时态',ACTION_CHAIN:'动作链' };
var TAB_META = { BO_INFO:null,API_CONFIG:'MODEL',MODEL:'MODEL',VALIDATION:'VALIDATION',SECURITY:'SECURITY',RULE:'RULE',VIEW:'VIEW',OPERATION:'OPERATION',LINK:'LINK',DERIVATION:'DERIVATION',TEMPORAL:'TEMPORAL',ACTION_CHAIN:'ACTION_CHAIN' };

// ── Schema version (fetched from API on load) ──────────────────
var g_schemaVersion = '2.0';
var g_schemaCache = {};

function loadSchema(schemaKey) {
  if (g_schemaCache[schemaKey]) return Promise.resolve(g_schemaCache[schemaKey]);
  return fetch('http://127.0.0.1:8765/api/schema/' + schemaKey, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }).then(function(r) { return r.json(); }).then(function(s) {
    g_schemaCache[schemaKey] = s;
    return s;
  });
}

// ── Global state ──────────────────────────────────────────────
var currentTab = 'MODEL';
var currentMetaType = 'MODEL';
var g_formStates = {};
var g_sharedEnvelope = {
  tenantId: 'default',
  appCode: 'government',
  boCode: '',
  metaType: 'MODEL',
  draftVersion: '0.1',
  schemaVersion: g_schemaVersion,
  changeNote: ''
};
var formState = createDefaultState('MODEL');

// ── Tree selection states ────────────────────────────────────
var g_treeSel = null;
var g_valTreeSel = null;
var g_valDirty = {};
var g_pickerCallback = null;
var g_pickerSelected = {};
var g_pickerExclude = {};
var g_boList = [];

function currentFormState() {
  var mt = currentMetaType;
  if (!g_formStates[mt]) {
    g_formStates[mt] = createDefaultState(mt);
    g_formStates[mt].envelope = Object.assign({}, g_sharedEnvelope, {metaType: mt});
  }
  return g_formStates[mt];
}

function createDefaultState(mt) {
  var env = {
    tenantId: 'default',
    appCode: 'government',
    boCode: '',
    metaType: mt,
    draftVersion: '0.1',
    schemaVersion: g_schemaVersion,
    changeNote: ''
  };
  var c = {};
  switch(mt) {
    case 'MODEL':
      c.boCode = ''; c.boName = ''; c.description = '';
      c.apiConfig = { resourcePath:'', idField:'id', idType:'LONG', businessKeyField:'', aggregateApiPolicy:{ listProjectionScope:'ROOT_SUMMARY',readScope:'FULL_AGGREGATE',createScope:'FULL_AGGREGATE',updateScope:'ROOT_ENTITY_ONLY',deleteScope:'CASCADE_AGGREGATE',orphanPolicy:'DENY_DELETE_WHEN_CHILD_EXISTS',detailEmbedEntities:[],aggregateReplaceActionPath:'',alternateAggregateApis:[] }, searchEnabled:true, batchEnabled:true };
      c.boConfig = { objectType:'SINGLE', nameField:'', statusField:'', logicDeleteFlag:true, versionFlag:false, idStrategy:'SNOWFLAKE', auditStrategy:'DATABASE', defaultSort:null };
      c.entities = [];
      break;
    case 'VALIDATION': c.rules = []; break;
    case 'SECURITY': c.rowSecurity = { fallbackScope:'NONE', entriesByEntity:{} }; c.fieldSecurity = []; c.authzProjection = null; break;
    case 'RULE': c.rules = []; break;
    case 'VIEW': c.listViewConfig = null; c.fieldViews = []; break;
    case 'OPERATION': c.operations = []; break;
    case 'LINK': c.linkCode = ''; c.linkName = ''; c.sourceBoCode = ''; c.targetBoCode = ''; c.cardinality = 'MANY_TO_ONE'; c.direction = 'SOURCE_TO_TARGET'; c.linkKind = 'MASTER_DATA'; c.description = ''; break;
    case 'DERIVATION': c.derivationCode = ''; c.derivationName = ''; c.objectType = 'AGGREGATED'; c.sourceBos = []; c.computeFields = []; break;
    case 'TEMPORAL': c.temporalCode = ''; c.temporalName = ''; c.entityCode = ''; c.timeFieldCode = ''; c.eventSources = []; c.metrics = []; break;
    case 'ACTION_CHAIN': c.chainCode = ''; c.chainName = ''; c.trigger = { triggerType: 'ON_STATE_CHANGE' }; c.steps = []; break;
  }
  return { envelope:env, content:c };
}

// ── Status bar ─────────────────────────────────────────────────
function setStatus(msg, cls) {
  var el = document.getElementById('status-msg');
  if (!el) return;
  el.textContent = msg;
  el.className = cls||'';
  var timeout = (cls === 'warn') ? 15000 : 3000;
  setTimeout(function(){ if(el.textContent===msg){ el.textContent='就绪'; el.className=''; } }, timeout);
}

// ── Tab switching ──────────────────────────────────────────────
function renderMetaTabs() {
  var tabs = document.getElementById('meta-tabs');
  var html = '';
  UI_TABS.forEach(function(mt) {
    var active = mt === currentTab ? ' active' : '';
    var color = mt === currentTab ? '' : META_COLORS[mt];
    html += '<button class="meta-tab' + active + '" onclick="switchTab_(\'' + mt + '\')" style="color:' + color + '">' + META_CN[mt] + '</button>';
  });
  tabs.innerHTML = html;
}

function switchTab_(tab) {
  if (tab === currentTab) return;
  if (currentMetaType) {
    g_formStates[currentMetaType] = formState;
  }
  if (formState && formState.envelope) {
    var env = formState.envelope;
    g_sharedEnvelope.tenantId = env.tenantId;
    g_sharedEnvelope.appCode = env.appCode;
    g_sharedEnvelope.boCode = env.boCode;
    g_sharedEnvelope.draftVersion = env.draftVersion;
    g_sharedEnvelope.schemaVersion = env.schemaVersion;
    g_sharedEnvelope.changeNote = env.changeNote;
  }
  currentTab = tab;
  if (currentTab !== 'VALIDATION' && formState._tempValRule) {
    formState._tempValRule = null;
  }
  if (tab === 'BO_INFO') {
    currentMetaType = null;
    formState = { envelope: Object.assign({}, g_sharedEnvelope), content: {} };
  } else {
    currentMetaType = TAB_META[tab];
    if (g_formStates[currentMetaType]) {
      formState = g_formStates[currentMetaType];
      Object.assign(formState.envelope, g_sharedEnvelope, {metaType: currentMetaType});
    } else {
      formState = createDefaultState(currentMetaType);
      formState.envelope = Object.assign({}, g_sharedEnvelope, {metaType: currentMetaType});
      g_formStates[currentMetaType] = formState;
      var boCode = g_sharedEnvelope.boCode;
      if (boCode && currentMetaType !== 'MODEL') {
        setStatus('📡 正在加载 ' + boCode + ' 的 ' + currentMetaType + ' fragment…', '');
        fetchFragment(boCode, currentMetaType);
      }
    }
  }
  renderMetaTabs();
  renderForm();
  updatePreview();
}

function fetchFragment(boCode, metaType) {
  fetch('http://127.0.0.1:8765/api/fragment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ boCode: boCode, metaType: metaType })
  }).then(function(r) {
    if (!r.ok) throw new Error('Fragment not found');
    return r.json();
  }).then(function(data) {
    var mt = data.metaType || metaType;
    if (!g_formStates[mt]) g_formStates[mt] = createDefaultState(mt);
    g_formStates[mt].envelope = Object.assign({}, g_sharedEnvelope, {
      tenantId: data.tenantId || g_sharedEnvelope.tenantId,
      appCode: data.appCode || g_sharedEnvelope.appCode,
      boCode: data.boCode || boCode,
      metaType: mt,
      draftVersion: data.draftVersion || g_sharedEnvelope.draftVersion,
      schemaVersion: data.schemaVersion || g_sharedEnvelope.schemaVersion,
      changeNote: data.changeNote || g_sharedEnvelope.changeNote
    });
    g_formStates[mt].content = data.content || createDefaultState(mt).content;
    if (mt === 'RULE') { initRuleEverStashed(g_formStates[mt].content); }
    if (mt === 'VIEW') { initViewEverStashed(g_formStates[mt].content); }
    if (mt === 'OPERATION') { initOpEverStashed(g_formStates[mt].content); }
    if (mt === 'SECURITY') { initFsecEverStashed(g_formStates[mt].content); }
    if (currentMetaType === mt) {
      formState = g_formStates[mt];
      renderForm();
      updatePreview();
      setStatus('✅ 已加载 ' + boCode + ' — ' + mt, 'ok');
    }
  }).catch(function(err) {
    if (currentMetaType === metaType) {
      setStatus('⚠ ' + metaType + ' fragment 尚未创建，请手动编辑', '');
    }
  });
}

// ═══════════════════════ SCHEMA-DRIVEN FORM ENGINE ══════════════
function propLabel(key) {
  var map = {
    boCode:'BO 标识', boName:'BO 名称', tenantId:'租户标识', appCode:'应用代码',
    metaType:'元数据类型', draftVersion:'草稿版本', schemaVersion:'Schema 版本',
    changeNote:'变更说明', description:'描述',
    resourcePath:'资源路径', idField:'ID 字段', idType:'ID 类型',
    businessKeyField:'业务键字段', searchEnabled:'启用搜索', batchEnabled:'启用批量',
    aggregateApiPolicy:'聚合 API 策略', apiConfig:'API 配置', boConfig:'BO 配置',
    objectType:'对象类型', nameField:'名称字段', statusField:'状态字段',
    logicDeleteFlag:'逻辑删除', versionFlag:'乐观锁', idStrategy:'ID 策略',
    auditStrategy:'审计策略', defaultSort:'默认排序', entities:'实体定义',
    listProjectionScope:'列表返回范围', readScope:'详情返回范围', createScope:'创建请求范围',
    updateScope:'普通更新范围', deleteScope:'删除范围', orphanPolicy:'孤儿子实体策略',
    detailEmbedEntities:'内嵌实体', aggregateReplaceActionPath:'替换动作路径',
    alternateAggregateApis:'备选聚合API', responseWrapper:'统一响应封装', batchResultType:'批量结果类型',
    field:'排序字段', direction:'排序方向',
    code:'代码', name:'名称', isPrimary:'主实体', aggregateRole:'聚合角色',
    tableName:'表名', parentEntityCode:'父实体代码', parentRefField:'父引用字段',
    routeSegment:'路由段', cascadeDelete:'级联删除', readOnly:'只读', entityNature:'实体性质',
    entityApiPolicy:'实体API策略', attributes:'属性列表',
    type:'类型', isPk:'主键', fieldName:'Java字段名', columnName:'列名',
    semanticRole:'语义角色', crossBoRef:'跨对象引用', redundant:'冗余存储',
    defaultValue:'默认值', filterable:'可筛选', i18nKey:'国际化标识',
    precision:'精度', scale:'小数位',
    refBoCode:'目标BO Code', refFieldCode:'目标字段', refEntityCode:'目标实体',
    localEntityCode:'本地实体', localFieldCode:'本地字段',
    relationType:'关系类型', referenceNature:'引用性质', displayFields:'展示字段',
    required:'必填', min:'最小值', max:'最大值', pattern:'正则', unique:'唯一', message:'消息',
    rules:'规则列表', rowSecurity:'行级安全', fieldSecurity:'字段级安全',
    fallbackScope:'兜底策略', entriesByEntity:'行级控制字段映射', authzProjection:'授权投影',
    fieldControl:'字段控制', privacyClass:'隐私分级', reason:'原因',
    ruleType:'规则类型', scope:'作用范围', entityCode:'实体代码', fieldCode:'字段代码',
    operationCode:'操作代码', crossBoRuleRef:'跨BO规则引用', trigger:'触发时机',
    expression:'表达式', action:'动作', severity:'严重级别',
    listViewConfig:'列表视图配置', fieldViews:'字段视图配置', displayName:'显示名称',
    sortable:'可排序', columnWidth:'列宽', format:'格式化', hidden:'隐藏', order:'排序号',
    showInList:'列表显示', showInDetail:'详情显示', editableInForm:'表单可编辑',
    instantValidate:'即时校验', formType:'表单控件', placeholder:'占位提示',
    queryable:'可查询', queryOperatorOptions:'查询操作符', dataType:'数据类型', exportable:'可导出', importable:'可导入',
    disabled:'默认禁用', dictCode:'字典代码', refObject:'引用对象', refField:'引用字段',
    operations:'操作列表', operationKind:'操作类型', authzAction:'授权动作',
    httpMethod:'HTTP方法', actionPath:'动作路径', supportsBatch:'支持批量',
    async:'异步', singleResultType:'单结果类型', position:'按钮位置',
    triggerEvent:'触发事件', defaultPageSize:'默认分页', formLayout:'表单布局',
    formColumns:'列数', formLabelWidth:'标签宽度', searchCollapsible:'搜索可折叠',
  };
  if (map[key]) return map[key];
  return key.replace(/([A-Z])/g,' $1').replace(/_/g,' ').replace(/^./,function(c){return c.toUpperCase();});
}

function enumLabel(v) {
  var map = {
    ROOT_SUMMARY:'主实体摘要 + 汇总字段', ROOT_ENTITY_ONLY:'仅主实体', FULL_AGGREGATE:'完整聚合',
    FULL_AGGREGATE_PATCH:'完整聚合增量更新', FULL_AGGREGATE_REPLACE:'完整聚合替换',
    CASCADE_AGGREGATE:'聚合级联删除', DENY_DELETE_WHEN_CHILD_EXISTS:'存在子实体则禁止删除',
    KEEP_CHILDREN_AS_HISTORY:'保留为历史', DETACH_CHILDREN:'解除关联',
    MANUAL_CLEANUP_REQUIRED:'人工清理',
    ENTITY_SUMMARY:'实体摘要 + 汇总字段', ENTITY_ONLY:'仅实体本体', ENTITY_AGGREGATE:'局部聚合',
    ENTITY_AGGREGATE_PATCH:'局部聚合增量更新', ENTITY_AGGREGATE_REPLACE:'局部聚合替换',
    CASCADE_CHILDREN:'级联删除下级',
    SINGLE:'单表', TREE:'树形结构', MASTER_DETAIL:'主从结构',
    AUTO_INCREMENT:'数据库自增', SNOWFLAKE:'雪花算法',
    DATABASE:'数据库层', APPLICATION:'应用层',
    ROOT:'聚合根', SUB_ENTITY:'子实体', VALUE_OBJECT:'值对象', DERIVED_VIEW:'派生视图',
    BUSINESS:'业务实体', ASSOCIATION:'关联表',
    STRING:'字符串', INTEGER:'整数', LONG:'长整数', DECIMAL:'定点数',
    BOOLEAN:'布尔', DATE:'日期', DATETIME:'日期时间',
    TECHNICAL_ID:'技术ID', BUSINESS_KEY:'业务键', NAME:'名称', STATUS:'状态',
    PARENT_REF:'父引用', CROSS_BO_REF:'跨BO引用', CROSS_BO_DISPLAY:'跨BO展示', NORMAL:'普通',
    asc:'升序', desc:'降序',
    MANY_TO_ONE:'多对一', ONE_TO_ONE:'一对一',
    MASTER_DATA:'主数据', BUSINESS_FLOW:'业务流',
    OPEN:'开放', RESTRICTED:'受限', MASKED:'脱敏', HIDDEN:'隐藏',
    PUBLIC:'公开', SENSITIVE:'敏感', PII:'个人隐私', CONFIDENTIAL:'机密',
    ALL:'全部', NONE:'无',
    BO:'级联实体', ENTITY:'单实体', FIELD:'字段级', OPERATION:'操作级', CROSS_BO:'跨BO',
    BEFORE_VALIDATE:'校验前', BEFORE_OPERATION:'操作前', AFTER_OPERATION:'操作后',
    ON_STATE_CHANGE:'状态变更时', ON_PUBLISH:'发布时', ON_READ:'读取时',
    INFO:'提示', WARN:'警告', ERROR:'错误',
    GRID:'网格', VERTICAL:'垂直', HORIZONTAL:'水平',
    currency:'货币', date:'日期', datetime:'日期时间', percent:'百分比', text:'文本',
    INPUT:'输入框', TEXTAREA:'文本域', NUMBER:'数字', SELECT:'下拉选择',
    MULTI_SELECT:'多选', SWITCH:'开关', RADIO:'单选', CHECKBOX:'复选框',
    USER_SELECT:'用户选择', ORG_SELECT:'组织选择', OBJECT_SELECT:'对象选择',
    FILE_UPLOAD:'文件上传', RICH_TEXT:'富文本',
    EQ:'等于', NEQ:'不等于', GT:'大于', GTE:'大于等于', LT:'小于', LTE:'小于等于',
    LIKE:'包含', NOT_LIKE:'不包含', STARTS_WITH:'开头是', ENDS_WITH:'结尾是',
    IN:'属于', NOT_IN:'不属于', BETWEEN:'区间', IS_NULL:'为空', IS_NOT_NULL:'不为空',
    CREATE:'创建', UPDATE:'更新', DELETE:'删除', STATE_CHANGE:'状态变更',
    IMPORT:'导入', EXPORT:'导出', MERGE:'合并', CUSTOM:'自定义',
    GLOBAL:'全局', GET:'GET', POST:'POST', PATCH:'PATCH',
    TOOLBAR:'工具栏', ROW:'行内', DETAIL:'详情', FLOATING:'浮动',
    OPEN_FORM:'打开表单', API_CALL:'API调用', REDIRECT:'跳转', CONFIRM_THEN_API:'确认后API',
  };
  if (map[v] !== undefined) return map[v];
  return v;
}

// ── Field-level help text ──────────────────────────────────────
var FIELD_HELP = {
  resourcePath:'API 资源路径，固定为 /{boCode} 单段形式，发布服务据此生成 REST 端点。|例：/scenes、/opportunities',
  idField:'聚合根主键字段，必须在主实体属性中声明且 isPk=true。|例：id',
  idType:'主键 Java 类型。长整数=雪花算法（默认），字符串=UUID 或业务编码。|例：长整数 → Java Long 类型',
  businessKeyField:'业务唯一标识字段，用于导入匹配和对外展示编号。|例：scene_no、customer_code',
  searchEnabled:'是否生成 /{boCode}/search 全文检索端点。|例：开启 → 生成 search 端点',
  batchEnabled:'是否生成批量创建/更新/删除端点。|例：开启 → 生成 POST /scenes/batch',
  listProjectionScope:'列表查询返回哪些字段。|例：主实体摘要+汇总字段 → 返回主实体字段和汇总',
  readScope:'详情查询返回范围。|例：完整聚合 → 返回主实体+所有子实体',
  createScope:'POST 创建是否允许一次提交主实体和子实体。|例：完整聚合 → 请求体可含子实体数组',
  updateScope:'PATCH 更新默认范围。|例：仅主实体 → PATCH 只更新主实体，子实体通过专用接口维护',
  deleteScope:'DELETE 删除主实体时对子实体的处理。|例：聚合级联删除 → 删除场景时同步删除场景行',
  orphanPolicy:'仅删除主实体时对已有子实体的保护策略。|例：存在子实体则禁止删除 → 有子实体时返回 409',
  objectType:'BO 结构化类型。|例：主从结构 → 场景主表 + 场景行子表',
  nameField:'BO 名称字段，用于列表展示和引用显示。|例：scene_name',
  statusField:'BO 状态字段，用于工作流和生命周期管理。|例：status',
  idStrategy:'主键生成策略。|例：雪花算法 → MyBatis-Plus IdType.ASSIGN_ID',
  auditStrategy:'审计时间戳维护方。|例：数据库层 → DDL 含 DEFAULT CURRENT_TIMESTAMP',
  field:'默认排序字段。|例：created_at',
  direction:'默认排序方向。|例：降序 → ORDER BY created_at DESC',
  fieldControl:'字段访问控制级别。|例：隐藏 → 接口不返回该字段',
  privacyClass:'数据隐私分级。|例：个人隐私 → 含身份证号，需合规处理',
  fallbackScope:'用户无策略命中时的默认行级权限。|例：无 → 无策略时返回空列表',
  trigger:'规则触发时机。|例：操作前 → 创建前校验必填字段',
  severity:'规则严重级别。|例：错误 → 校验失败返回 400',
  ruleType:'规则类型。|例：状态规则 → 状态流转规则',
  scope:'规则/操作作用范围。|例：实体级 → 作用于 scene_lines 实体',
  operationKind:'操作类型。|例：状态变更 → 提交审批',
  authzAction:'授权动作代码。|例：SUBMIT_APPROVAL',
  httpMethod:'操作触发的 HTTP 方法。|例：POST → POST /scenes/{id}/submit-approval',
  actionPath:'自定义操作的 URL 路径段。|例：submit-approval → POST /scenes/{id}/submit-approval',
  triggerEvent:'操作触发方式。|例：API调用 → 前端直接 fetch',
  position:'操作按钮位置。|例：行内 → 每行数据旁的操作按钮',
  defaultPageSize:'列表默认每页条数。|例：20 → GET /scenes?page=1&size=20',
  entityNature:'实体数据库映射性质。|例：关联表 → 纯关联联结表，仅 aggregateRole=SUB_ENTITY 时有效',
  code:'实体/属性唯一标识码，推荐 snake_case 小写。|例：scene_header',
  type:'属性 Java/DB 类型。|例：STRING → VARCHAR',
  isPk:'是否为主键。|例：true → DDL 含 PRIMARY KEY',
  semanticRole:'属性的业务语义角色。|例：CROSS_BO_REF → ref_opportunity_id',
  redundant:'是否冗余存储。|例：true → 冗余存储客户名称',
  refBoCode:'引用的目标 BO 的 boCode。|例：opportunities → 引用商机',
  refFieldCode:'目标 BO 中被引用的字段 code。|例：id',
  refEntityCode:'目标 BO 中具体被引用的实体 code。|例：opportunity_header',
};

function schemaFieldHtml(schema, key, val, prefix, opts) {
  opts = opts || {};
  var ps = schema.properties || {};
  var prop = ps[key] || {};
  var req = (schema.required||[]).indexOf(key) >= 0;
  var label = prop.title || propLabel(key);
  var hint = prop.description || '';
  var disabled = opts.disabledFields && opts.disabledFields.indexOf(key) >= 0;
  var hidden = opts.hiddenFields && opts.hiddenFields.indexOf(key) >= 0;
  if (hidden) return '';
  var helpRaw = FIELD_HELP[key] || '';
  var helpHtml = '';
  if (helpRaw) {
    var parts = helpRaw.split('|');
    var helpDesc = parts[0] || '';
    var helpEx = parts[1] || '';
    var tipContent = helpDesc;
    if (helpEx) tipContent += '||' + helpEx;
    helpHtml = '<i class="help-icon" data-help="' + escHtml(tipContent) + '">?</i>';
  }
  var path = prefix ? prefix + '.' + key : key;
  var type = prop.type || 'string';
  var html = '';
  var reqMark = req ? '<span class="req">*</span>' : '';
  var hintSpan = (!helpHtml && hint) ? '<span class="hint">' + hint.split(/[；;]/)[0].substring(0,120) + '</span>' : '';
  var da = disabled ? ' disabled' : '';

  if (type === 'boolean') {
    html = '<div class="f-cb-row"><input type="checkbox" data-path="' + path + '"' + (val ? ' checked' : '') + da + '><label>' + label + helpHtml + reqMark + hintSpan + '</label></div>';
    return '<div class="field-group">' + html + '</div>';
  }
  if (prop.enum) {
    var optsHtml = prop.enum.map(function(v) {
      var lbl = enumLabel(String(v));
      return '<option value="' + v + '"' + (val === v ? ' selected' : '') + '>' + lbl + '</option>';
    }).join('');
    html = '<label class="f-label">' + label + helpHtml + reqMark + hintSpan + '</label>';
    html += '<select class="f-select" data-path="' + path + '"' + da + '>' + optsHtml + '</select>';
    return '<div class="field-group">' + html + '</div>';
  }
  if (type === 'integer' || type === 'number') {
    var min = prop.minimum !== undefined ? ' min="' + prop.minimum + '"' : '';
    var max = prop.maximum !== undefined ? ' max="' + prop.maximum + '"' : '';
    html = '<label class="f-label">' + label + helpHtml + reqMark + hintSpan + '</label>';
    html += '<input class="f-input" data-path="' + path + '" type="number"' + min + max + ' value="' + escHtml(String(val||'')) + '"' + da + '>';
    return '<div class="field-group">' + html + '</div>';
  }
  var maxlen = prop.maxLength ? ' maxlength="' + prop.maxLength + '"' : '';
  var mono = (prop.pattern || key==='boCode' || key.indexOf('Code')>=0 || key.indexOf('Field')>=0) ? ' f-mono' : '';
  html = '<label class="f-label">' + label + helpHtml + reqMark + hintSpan + '</label>';
  html += '<input class="f-input' + mono + '" data-path="' + path + '" type="text" value="' + escHtml(String(val||'')) + '"' + maxlen + da + '>';
  return '<div class="field-group">' + html + '</div>';
}

function schemaObjectForm(schema, data, prefix, opts) {
  opts = opts || {};
  var ps = schema.properties || {};
  var keys = Object.keys(ps);
  var html = '';
  keys.forEach(function(key) {
    var prop = ps[key];
    if (prop.type === 'object' || prop.type === 'array') return;
    html += schemaFieldHtml(schema, key, data ? data[key] : undefined, prefix, opts);
  });
  return '<div class="form-grid">' + html + '</div>';
}

function schemaSection(schema, data, prefix, sectionTitle, opts) {
  opts = opts || {};
  var html = schemaObjectForm(schema, data, prefix, opts);
  return secCard(sectionTitle, html, opts.collapsed !== true);
}

// ════════════════════════════════ HELPERS ═══════════════════════
function secCard(title, body, open) {
  if (open === undefined) open = true;
  return '<div class="section-card"><div class="section-head" data-toggle="section">' +
    '<span class="expand-icon ' + (open?'open':'') + '">▶</span><span class="section-head-title">' + title + '</span></div>' +
    '<div class="section-body ' + (open?'open':'') + '">' + body + '</div></div>';
}

function sel() {
  var vals = Array.prototype.slice.call(arguments);
  return vals.map(function(v) { return typeof v==='string' ? {v:v,l:v} : v; });
}

function formGrid(fields) {
  var rows = '';
  fields.forEach(function(f) {
    var path = f[0], label = f[1], type = f[2], val = f[3], opts = f[4] || {};
    var req = opts.req ? '<span class="req">*</span>' : '';
    var hint = opts.hint ? '<span class="hint">' + opts.hint + '</span>' : '';
    var cls = opts.full ? 'f-full' : '';
    var mono = opts.mono ? ' f-mono' : '';
    var disabled = opts.disabled ? ' disabled' : '';
    var inputHtml = '';
    if (type === 'text' || type === 'number') {
      inputHtml = '<input class="f-input' + mono + ' ' + cls + '" data-path="' + path + '" type="' + type + '" value="' + escHtml(val||'') + '" placeholder="' + (opts.placeholder||'') + '"' + disabled + '>';
    } else if (type === 'select') {
      inputHtml = '<select class="f-select ' + cls + '" data-path="' + path + '"' + disabled + '>' + (opts.opts||[]).map(function(o){ return '<option value="' + o.v + '"' + ((val||'')===o.v?' selected':'') + '>' + (o.l||o.v) + '</option>'; }).join('') + '</select>';
    } else if (type === 'bool') {
      inputHtml = '<div class="f-cb-row ' + cls + '"><input type="checkbox" data-path="' + path + '"' + (val?' checked':'') + disabled + '><label>' + label + '</label></div>';
      rows += '<div class="field-group ' + cls + '">' + inputHtml + '</div>';
      return;
    }
    if (type !== 'bool') {
      rows += '<div class="field-group ' + cls + '"><label class="f-label">' + label + req + hint + '</label>' + inputHtml + '</div>';
    }
  });
  return '<div class="form-grid">' + rows + '</div>';
}

function escHtml(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ═══════════════════════════ PATH-BASED STATE ACCESS ═════════════
function getByPath(obj, path) {
  var parts = path.split('.');
  var cur = obj;
  for (var i = 0; i < parts.length; i++) {
    var p = parts[i];
    if (/^\d+$/.test(p)) {
      if (!Array.isArray(cur)) return undefined;
      cur = cur[parseInt(p)];
    } else {
      if (cur === null || cur === undefined) return undefined;
      cur = cur[p];
    }
  }
  return cur;
}

function setByPath(path, value) {
  var parts = path.split('.');
  var cur = formState;
  for (var i = 0; i < parts.length - 1; i++) {
    var p = parts[i];
    if (/^\d+$/.test(p)) {
      if (!Array.isArray(cur)) cur = [];
      var idx = parseInt(p);
      if (cur[idx] === undefined) cur[idx] = {};
      cur = cur[idx];
    } else {
      if (cur[p] === undefined) {
        cur[p] = /^\d+$/.test(parts[i+1]) ? [] : {};
      }
      cur = cur[p];
    }
  }
  var last = parts[parts.length-1];
  if (last.startsWith('key.') || last.startsWith('val.')) return;
  if (typeof getByPath(formState, path) === 'number' || (last==='min'||last==='max'||last==='precision'||last==='scale'||last==='order'||last==='columnWidth'||last==='formLabelWidth'||last==='defaultPageSize'||last==='formColumns')) {
    value = value === '' ? undefined : Number(value);
  } else if (typeof getByPath(formState, path) === 'boolean') {
    value = value === 'true' ? true : value === 'false' ? false : value;
  }
  cur[last] = value;
}

// ═══════════════════════════════════════════════ JSON PREVIEW ═══
function buildOutputJson() {
  syncEnumFields();
  var output = {
    $schema: 'https://authz.xbac/schemas/gov/bo-meta-fragment.schema.json',
    tenantId: formState.envelope.tenantId,
    appCode: formState.envelope.appCode,
    boCode: formState.envelope.boCode,
    metaType: formState.envelope.metaType,
    draftVersion: formState.envelope.draftVersion,
    schemaVersion: formState.envelope.schemaVersion,
    changeNote: formState.envelope.changeNote,
    content: JSON.parse(JSON.stringify(formState.content))
  };
  return JSON.stringify(output, null, 2);
}

function syncEnumFields() {
  document.querySelectorAll('[data-path$=".enum"]').forEach(function(el) {
    var path = el.dataset.path;
    var raw = (el.value||'').split(',').map(function(s){return s.trim();}).filter(Boolean);
    var parsed = raw.map(function(item) {
      var colonIdx = item.indexOf(':');
      if (colonIdx > 0) {
        return { value: item.substring(0, colonIdx), label: item.substring(colonIdx + 1) };
      }
      return { value: item, label: item };
    });
    setByPath(path, parsed.length>0 ? parsed : []);
  });
  syncEmbEntities();
}

function syncEmbEntities() {
  var visEl = document.getElementById('inp-embEntities');
  var hidEl = document.getElementById('hid-embEntities');
  if (!visEl || !hidEl) return;
  var nameToCode = {};
  var ents = formState.content.entities || [];
  ents.forEach(function(e) { if (e.name && e.code) nameToCode[e.name.trim()] = e.code; });
  var names = (visEl.value||'').split(',').map(function(s){return s.trim();}).filter(Boolean);
  var codes = names.map(function(n){return nameToCode[n] || n;});
  var codeStr = codes.join(',');
  hidEl.value = codeStr;
  setByPath(hidEl.dataset.path, codes.length > 0 ? codes : []);
}

function updatePreview() {
  try {
    syncEnumFields();
    var json = buildOutputJson();
    var pre = document.getElementById('json-preview');
    if (pre) pre.textContent = json;
  } catch(e) {
    var pre2 = document.getElementById('json-preview');
    if (pre2) pre2.textContent = '// 编辑中...';
  }
}

function copyJson() {
  var pre = document.getElementById('json-preview');
  if (!pre) return;
  var text = pre.textContent;
  navigator.clipboard.writeText(text).then(function(){setStatus('✅ 已复制到剪贴板','ok');}).catch(function(){setStatus('复制失败','err');});
}
