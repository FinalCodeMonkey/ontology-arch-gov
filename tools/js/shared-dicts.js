// ═══════════════════════════════════════════════════════════════════
// Shared Dictionaries — Common labels & constants for both pages
// ═══════════════════════════════════════════════════════════════════
const ROLE_COLORS = { TECHNICAL_ID:'#a1a1aa',BUSINESS_KEY:'#60a5fa',NAME:'#34d399',NORMAL:'#71717a',CROSS_BO_REF:'#f59e0b',CROSS_BO_DISPLAY:'#fbbf24',PARENT_REF:'#c084fc',STATUS:'#fb923c' };
const FRAG_COLORS = { MODEL:'#3b82f6',VALIDATION:'#ef4444',SECURITY:'#f59e0b',RULE:'#8b5cf6',VIEW:'#10b981',OPERATION:'#0ea5e9',LINK:'#ec4899',DERIVATION:'#f97316',TEMPORAL:'#14b8a6',ACTION_CHAIN:'#7c3aed' };
const ROLE_CN = { TECHNICAL_ID:'技术主键',BUSINESS_KEY:'业务键',NAME:'名称',NORMAL:'普通',CROSS_BO_REF:'跨对象引用',CROSS_BO_DISPLAY:'引用展示',PARENT_REF:'父级引用',STATUS:'状态' };
const RULETYPE_CN = { COMPLEX_VALIDATION:'复杂校验',STATE:'状态约束',DERIVATION:'派生计算',PERMISSION:'权限规则',AUTOMATION:'自动化',CONSISTENCY:'一致性' };
const OPKIND_CN = { CREATE:'新建',UPDATE:'更新',DELETE:'删除',STATE_CHANGE:'状态变更',IMPORT:'导入',EXPORT:'导出',MERGE:'合并',CUSTOM:'自定义' };
const SCOPE_CN = { BO:'对象级',ENTITY:'实体级',FIELD:'字段级',OPERATION:'操作级',CROSS_BO:'跨对象',GLOBAL:'全局' };
const OBJTYPE_CN = { MASTER_DETAIL:'主从结构',SINGLE:'单表结构',TREE:'树形结构' };
const FRAG_CN = { MODEL:'模型',VALIDATION:'校验',SECURITY:'安全',RULE:'规则',VIEW:'视图',OPERATION:'操作',LINK:'关系',DERIVATION:'派生',TEMPORAL:'时态',ACTION_CHAIN:'动作链' };
const RELTYPE_CN = { MANY_TO_ONE:'N:1 关联',CONSISTENCY_RULE:'一致性规则',DISPLAY_DEPENDENCY:'展示依赖',ONE_TO_ONE:'1:1 关联' };
const TRIGGER_CN = { BEFORE_VALIDATE:'校验前',BEFORE_OPERATION:'操作前',AFTER_OPERATION:'操作后',ON_STATE_CHANGE:'状态变更时',ON_PUBLISH:'发布时',ON_READ:'读取时' };
const SEVERITY_CN = { ERROR:'阻断',WARN:'警告',INFO:'提示' };
const FIELDCTRL_CN = { OPEN:'公开',RESTRICTED:'受限',MASKED:'脱敏',HIDDEN:'隐藏' };
const PRIVACY_CN = { PUBLIC:'公开',SENSITIVE:'敏感',PII:'个人隐私',CONFIDENTIAL:'机密' };
const LINK_SOURCE_CN = { EXPLICIT:'显式LINK',INFERRED:'派生LINK',DISPLAY_DEPENDENCY:'展示依赖',CONSISTENCY_RULE:'一致性规则' };
const LINK_SOURCE_COLORS = { EXPLICIT:'#10b981',INFERRED:'#94a3b8',DISPLAY_DEPENDENCY:'#fbbf24',CONSISTENCY_RULE:'#ef4444' };
