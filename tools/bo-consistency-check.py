"""
BO 元数据深度全面检查 —— 一站式校验工具。

Phases:
  0. JSON Schema 形式化校验（governance profile + fragment envelope + 6 sub-schemas）
  1. Fragment 加载 + 基础规范检查（boCode / metaType / 重复等）
  2. 逐 BO 深度结构/语义/引用完整性检查（含 8 种 metaType 交叉引用）
  3. 跨 BO 命名一致性分析（同名不同码、displayFields 统一性、同 BO 内类型一致性）

用法:
  python bo-consistency-check.py                  # 全量检查（含 JSON Schema）
  python bo-consistency-check.py --no-json-schema # 跳过 JSON Schema 校验（快速模式）
"""
import json, os, re, sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

BASE = str(Path(__file__).resolve().parent.parent)
METADATA = os.path.join(BASE, 'metadata')
SCHEMAS_DIR = os.path.join(BASE, 'schemas')

# ── CLI args ──────────────────────────────────────────────────────
NO_JSON_SCHEMA = '--no-json-schema' in sys.argv

# ── Track all issues ──
errors = []
warnings = []
infos = []


def load_json(fp):
    with open(fp, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════
# Phase 0 — JSON Schema 形式化校验
# ══════════════════════════════════════════════════════════════════
def run_json_schema_validation():
    """Governance Profile + Fragment envelope + 6 sub-schemas JSON Schema 校验。"""
    try:
        from jsonschema import Draft202012Validator, RefResolver
    except ImportError:
        print('⚠️  jsonschema 未安装，跳过 JSON Schema 校验')
        print('   安装: pip install jsonschema')
        return False

    print('=' * 70)
    print('Phase 0 — JSON Schema 形式化校验')
    print('=' * 70)
    ok = True

    # ── 0a. Governance Profile ──────────────────────────────────
    profile_schema = load_json(os.path.join(SCHEMAS_DIR, 'design-time', 'governance-profile.schema.json'))
    profile_instance = load_json(os.path.join(BASE, 'config', 'governance-profile.default.json'))

    def _noop_resolver(uri):
        return {}

    try:
        resolver = RefResolver(base_uri=profile_schema.get('$id', ''), referrer=profile_schema, store={}, handlers={'https': _noop_resolver, 'http': _noop_resolver})
        Draft202012Validator(profile_schema, resolver=resolver).validate(profile_instance)
        print('  ✅ governance-profile.default.json')
    except Exception as e:
        print(f'  ❌ governance-profile.default.json: {e}')
        errors.append('governance-profile.default.json schema validation failed')
        ok = False

    # ── 0b. Fragment JSON Schema ────────────────────────────────
    envelope_schema = load_json(os.path.join(SCHEMAS_DIR, 'design-time', 'bo-meta-fragment.schema.json'))

    fragment_schemas = {}
    for fname in ['model-fragment.schema.json', 'validation-fragment.schema.json',
                  'security-fragment.schema.json', 'rule-fragment.schema.json',
                  'view-fragment.schema.json', 'operation-fragment.schema.json',
                  'link-fragment.schema.json', 'derivation-fragment.schema.json',
                  'temporal-fragment.schema.json', 'action-chain-fragment.schema.json']:
        s = load_json(os.path.join(SCHEMAS_DIR, 'design-time', 'fragments', fname))
        fragment_schemas[s['$id']] = s

    store = {s['$id']: s for s in fragment_schemas.values()}
    eid = envelope_schema.get('$id', '')
    if eid:
        store[eid] = envelope_schema

    # 拦截远程 $schema URL 解析，避免 SSL/网络错误
    # 所有 schema 已在 store 中预注册，RefResolver 优先从 store 查找
    def _local_resolver(uri):
        # 如果 URI 在 store 中，RefResolver 会自动命中；否则返回空 schema 避免网络请求
        return {}

    fragment_errors = 0
    for dirpath, _dirnames, filenames in os.walk(os.path.join(METADATA, 'design-time')):
        for fname in filenames:
            if not fname.endswith('.fragment.json'):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, BASE)
            try:
                instance = load_json(fpath)
            except Exception as e:
                print(f'  ❌ {rel}: JSON parse error - {e}')
                fragment_errors += 1
                errors.append(f'{rel}: JSON parse error')
                continue
            try:
                resolver2 = RefResolver(base_uri=envelope_schema.get('$id', ''), referrer=envelope_schema, store=store, handlers={'https': _local_resolver, 'http': _local_resolver})
                Draft202012Validator(envelope_schema, resolver=resolver2).validate(instance)
            except Exception as e:
                msg = str(e).split('\n')[0][:150]
                print(f'  ❌ {rel}: {msg}')
                fragment_errors += 1
                errors.append(f'{rel}: {msg}')

    if fragment_errors == 0:
        print('  ✅ All fragments pass JSON Schema validation')
    else:
        print(f'  ❌ {fragment_errors} fragment(s) failed JSON Schema validation')
        ok = False

    print()
    return ok


# ── CLI: skip JSON Schema if requested ───────────────────────────
if NO_JSON_SCHEMA:
    print('⚡ 快速模式 — 跳过 JSON Schema 校验')
    print()
else:
    run_json_schema_validation()


# ══════════════════════════════════════════════════════════════════
# Phase 1 — Load all fragments + basic envelope checks
# ══════════════════════════════════════════════════════════════════

bo_code_pattern = re.compile(r'^[a-z][a-z0-9-]*$')
entity_code_pattern = re.compile(r'^[a-z][a-z0-9-]*$')      # entity.code 允许 kebab-case
table_name_pattern = re.compile(r'^[a-z][a-z0-9_]*$')       # tableName 仅允许 snake_case，禁止连字符
ALL_META_TYPES = {'MODEL', 'VALIDATION', 'SECURITY', 'RULE', 'VIEW', 'OPERATION'}

fragments_by_bo = defaultdict(dict)  # boCode -> { metaType: (filepath, data) }
all_bos = set()

for dirpath, _dirnames, filenames in os.walk(os.path.join(METADATA, 'design-time')):
    # 跳过元容器目录（_ 前缀），它们不是业务对象
    rel_dir = os.path.relpath(dirpath, os.path.join(METADATA, 'design-time'))
    if rel_dir.startswith('_') or rel_dir.startswith('.') or os.path.sep + '_' in rel_dir:
        continue
    for f in filenames:
        if f.endswith('.json') and 'fragments' in dirpath:
            fp = os.path.join(dirpath, f)
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
            except Exception as e:
                print(f'  ❌ PARSE: {os.path.relpath(fp, BASE)} - {e}')
                errors.append(f'{os.path.relpath(fp, BASE)}: JSON parse error - {e}')
                continue

            bc = data.get('boCode', '')
            mt = data.get('metaType', '')

            # boCode pattern check
            if not bo_code_pattern.match(bc):
                errors.append(f'{os.path.relpath(fp, BASE)}: boCode "{bc}" 不符合 pattern ^[a-z][a-z0-9-]*$')
                continue

            # metaType validity
            if mt not in ALL_META_TYPES:
                errors.append(f'{os.path.relpath(fp, BASE)}: 未知 metaType "{mt}"')
                continue

            # duplicate metaType for same boCode
            if mt in fragments_by_bo[bc]:
                errors.append(f'{os.path.relpath(fp, BASE)}: boCode "{bc}" 存在重复 metaType "{mt}"')

            fragments_by_bo[bc][mt] = (fp, data)
            all_bos.add(bc)


print('=' * 70)
print('Phase 1+2 — BO 元数据深度全面检查')
print('=' * 70)
print(f'共发现 {len(all_bos)} 个 BO\n')


# ══════════════════════════════════════════════════════════════════
# Phase 2 — Per-BO deep checks
# ══════════════════════════════════════════════════════════════════

for bc in sorted(all_bos):
    frags = fragments_by_bo[bc]
    print(f'\n{"="*70}')
    print(f'  📦 {bc}')
    print(f'{"="*70}')

    # Fragment inventory
    present_types = set(frags.keys())
    missing = ALL_META_TYPES - present_types
    if missing:
        warnings.append(f'{bc}: 缺失 Fragment 类型: {sorted(missing)}')

    model = frags.get('MODEL')
    if not model:
        errors.append(f'{bc}: 缺少 MODEL fragment，跳过后续检查')
        continue

    model_fp, model_data = model

    # ── A. MODEL Envelope ──
    content = model_data.get('content', {})
    content_bc = content.get('boCode', '')
    if bc != content_bc:
        errors.append(f'{bc}/MODEL: envelope boCode "{bc}" != content boCode "{content_bc}"')

    rp = content.get('apiConfig', {}).get('resourcePath', '')
    if rp != '/' + bc:
        errors.append(f'{bc}/MODEL: resourcePath "{rp}" 应为 "/{bc}"')

    # Check all required envelope fields
    for field in ['tenantId', 'appCode', 'boCode', 'metaType', 'draftVersion', 'schemaVersion', 'content']:
        if field not in model_data:
            errors.append(f'{bc}/MODEL: 缺少 envelope 必填字段 "{field}"')

    dv = model_data.get('draftVersion')
    try:
        dv_num = float(dv) if not isinstance(dv, (int, float)) else dv
        if dv_num < 1:
            errors.append(f'{bc}/MODEL: draftVersion 必须 >=1, 当前 {dv}')
    except (ValueError, TypeError):
        errors.append(f'{bc}/MODEL: draftVersion 格式非法, 当前 {dv}')

    sv = model_data.get('schemaVersion', '')
    if not re.match(r'^v?[0-9]+(\.[0-9]+){0,2}$', sv):
        errors.append(f'{bc}/MODEL: schemaVersion "{sv}" 不符合格式')

    # ── B. MODEL entities ──
    entities = content.get('entities', [])
    entity_index = {}
    entity_pk_field = {}
    entity_roles = defaultdict(list)

    for ent in entities:
        ec = ent.get('code', '')
        if ec in entity_index:
            errors.append(f'{bc}/MODEL: 重复 entity code "{ec}"')
        entity_index[ec] = {}
        role = ent.get('aggregateRole', '')
        entity_roles[role].append(ec)

        # Check entity required fields
        for f in ['code', 'name', 'isPrimary', 'aggregateRole', 'attributes']:
            if f not in ent:
                errors.append(f'{bc}/MODEL: entity "{ec}" 缺少必填字段 "{f}"')

        # Check entity code pattern (entity.code 允许连字符, kebab-case)
        if not entity_code_pattern.match(ec):
            errors.append(f'{bc}/MODEL: entity code "{ec}" 不符合 pattern ^[a-z][a-z0-9-]*$')

        # Check tableName pattern (仅允许 snake_case，禁止连字符)
        tn = ent.get('tableName', '')
        if tn and not table_name_pattern.match(tn):
            errors.append(f'{bc}/MODEL: entity "{ec}" tableName "{tn}" 不符合 pattern ^[a-z][a-z0-9_]*$')

        # Check aggregateRole
        valid_roles = {'ROOT', 'SUB_ENTITY', 'VALUE_OBJECT', 'DERIVED_VIEW'}
        if role not in valid_roles:
            errors.append(f'{bc}/MODEL: entity "{ec}" aggregateRole "{role}" 不在 {valid_roles}')

        # Check entityNature
        nature = ent.get('entityNature', '')
        valid_natures = {'BUSINESS', 'ASSOCIATION', 'EXTERNAL_REF'}
        if nature and nature not in valid_natures:
            errors.append(f'{bc}/MODEL: entity "{ec}" entityNature "{nature}" 不在 {valid_natures}')

        # Check attributes
        attrs = ent.get('attributes', [])
        seen_attr_codes = set()
        for attr in attrs:
            ac = attr.get('code', '')
            if ac in seen_attr_codes:
                errors.append(f'{bc}/MODEL: entity "{ec}" 重复 attribute code "{ac}"')
            seen_attr_codes.add(ac)
            entity_index[ec][ac] = attr

            # Check attribute required fields
            for f in ['code', 'name', 'type']:
                if f not in attr:
                    errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" 缺少必填字段 "{f}"')

            # Check type
            valid_types = {'STRING', 'INTEGER', 'LONG', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME'}
            at = attr.get('type', '')
            if at and at not in valid_types:
                errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" type "{at}" 不在 {valid_types}')

            # Check semanticRole
            valid_semantic = {'TECHNICAL_ID', 'BUSINESS_KEY', 'NAME', 'STATUS', 'PARENT_REF',
                              'CROSS_BO_REF', 'CROSS_BO_DISPLAY', 'NORMAL'}
            sr = attr.get('semanticRole', 'NORMAL')
            if sr not in valid_semantic:
                errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" semanticRole "{sr}" 不在 {valid_semantic}')

            # Check CROSS_BO_REF consistency
            cbr = attr.get('crossBoRef')
            if sr == 'CROSS_BO_REF' and not cbr:
                errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" semanticRole=CROSS_BO_REF 但缺少 crossBoRef')
            if cbr and sr != 'CROSS_BO_REF':
                errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" 有 crossBoRef 但 semanticRole="{sr}" (应为 CROSS_BO_REF)')

            # Check crossBoRef internals
            if cbr:
                for crf in ['refBoCode', 'refFieldCode']:
                    if crf not in cbr:
                        errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" crossBoRef 缺少必填字段 "{crf}"')
                ref_bo = cbr.get('refBoCode', '')
                if ref_bo:
                    if not bo_code_pattern.match(ref_bo):
                        errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" crossBoRef.refBoCode "{ref_bo}" 不符合 pattern')
                    elif ref_bo not in all_bos:
                        errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" crossBoRef.refBoCode "{ref_bo}" 指向不存在的 BO')

            # Check extra properties (model schema has additionalProperties:false)
            valid_attr_props = {'code', 'name', 'type', 'isPk', 'fieldName', 'columnName',
                                'semanticRole', 'crossBoRef', 'redundant', 'defaultValue', 'filterable', 'i18nKey',
                                'precision', 'scale', '_derivationPath', '_resolution'}
            extra = set(attr.keys()) - valid_attr_props
            if extra:
                errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" 含非法属性: {extra}')

            if attr.get('isPk'):
                entity_pk_field[ec] = ac
                if ac != 'id':
                    errors.append(f'{bc}/MODEL: entity "{ec}" PK attribute code="{ac}" 必须为 "id"')

            # redundant 只能在 CROSS_BO_DISPLAY
            if attr.get('redundant') and sr != 'CROSS_BO_DISPLAY':
                errors.append(f'{bc}/MODEL: entity "{ec}" attribute "{ac}" redundant=true 但 semanticRole="{sr}" (仅允许 CROSS_BO_DISPLAY)')

    # Check exactly one ROOT and one isPrimary, and they match
    roots = entity_roles.get('ROOT', [])
    primaries = [e.get('code') for e in entities if e.get('isPrimary')]
    if len(roots) != 1:
        errors.append(f'{bc}/MODEL: 期望 1 个 aggregateRole=ROOT, 实际 {len(roots)}: {roots}')
    if len(primaries) != 1:
        errors.append(f'{bc}/MODEL: 期望 1 个 isPrimary=true, 实际 {len(primaries)}: {primaries}')
    if len(roots) == 1 and len(primaries) == 1 and roots[0] != primaries[0]:
        errors.append(f'{bc}/MODEL: ROOT entity "{roots[0]}" != isPrimary entity "{primaries[0]}"')

    # Check apiConfig field references
    api_config = content.get('apiConfig', {})
    root_ec = roots[0] if len(roots) == 1 else None
    if root_ec and root_ec in entity_index:
        root_attrs = entity_index[root_ec]
        id_field = api_config.get('idField', '')
        if id_field:
            if id_field not in root_attrs:
                errors.append(f'{bc}/MODEL: apiConfig.idField "{id_field}" 不在 ROOT entity "{root_ec}" 中')
            elif not root_attrs[id_field].get('isPk'):
                errors.append(f'{bc}/MODEL: apiConfig.idField "{id_field}" isPk 不为 true')

        bk = api_config.get('businessKeyField', '')
        if bk and bk not in root_attrs:
            errors.append(f'{bc}/MODEL: apiConfig.businessKeyField "{bk}" 不在 ROOT entity "{root_ec}" 中')

        bo_config = content.get('boConfig', {})
        for cfg_field in ['nameField', 'statusField']:
            v = bo_config.get(cfg_field, '')
            if v and v not in root_attrs:
                errors.append(f'{bc}/MODEL: boConfig.{cfg_field} "{v}" 不在 ROOT entity "{root_ec}" 中')

        sort_field = bo_config.get('defaultSort', {}).get('field', '')
        if sort_field and sort_field not in root_attrs:
            errors.append(f'{bc}/MODEL: boConfig.defaultSort.field "{sort_field}" 不在 ROOT entity "{root_ec}" 中')

    # Check SUB_ENTITY parent references
    for ent in entities:
        ec = ent.get('code', '')
        role = ent.get('aggregateRole', '')
        pec = ent.get('parentEntityCode', '')
        prf = ent.get('parentRefField', '')
        if role == 'SUB_ENTITY':
            if not pec:
                errors.append(f'{bc}/MODEL: SUB_ENTITY "{ec}" 缺少 parentEntityCode')
            elif pec not in entity_index:
                errors.append(f'{bc}/MODEL: SUB_ENTITY "{ec}" parentEntityCode "{pec}" 不在 entities 中')
            if not prf:
                errors.append(f'{bc}/MODEL: SUB_ENTITY "{ec}" 缺少 parentRefField')
            elif prf and prf not in entity_index.get(ec, {}):
                errors.append(f'{bc}/MODEL: SUB_ENTITY "{ec}" parentRefField "{prf}" 不在自身 attributes 中')

    # ── C. VALIDATION fragment ──
    validation = frags.get('VALIDATION')
    if validation:
        v_fp, v_data = validation
        for rule in v_data.get('content', {}).get('rules', []):
            ec = rule.get('entityCode', '')
            fc = rule.get('fieldCode', '')
            if not ec or not fc:
                errors.append(f'{bc}/VALIDATION: 规则缺少 entityCode 或 fieldCode')
                continue
            if ec not in entity_index:
                errors.append(f'{bc}/VALIDATION: entityCode "{ec}" 不在 MODEL entities 中')
            elif fc not in entity_index.get(ec, {}):
                errors.append(f'{bc}/VALIDATION: fieldCode "{fc}" 不在 entity "{ec}" 中')
            mn = rule.get('min')
            mx = rule.get('max')
            if mn is not None and mx is not None and mn > mx:
                errors.append(f'{bc}/VALIDATION: {ec}.{fc} min ({mn}) > max ({mx})')

    # ── D. SECURITY fragment ──
    security = frags.get('SECURITY')
    if security:
        s_fp, s_data = security
        # rowSecurity
        entries = s_data.get('content', {}).get('rowSecurity', {}).get('entriesByEntity', {})
        for ec, fields in entries.items():
            if ec not in entity_index:
                errors.append(f'{bc}/SECURITY: rowSecurity key "{ec}" 不在 MODEL entities 中')
            else:
                for fc in fields:
                    if fc not in entity_index.get(ec, {}):
                        errors.append(f'{bc}/SECURITY: rowSecurity field "{fc}" 不在 entity "{ec}" 中')

        # fieldSecurity
        for fs in s_data.get('content', {}).get('fieldSecurity', []):
            ec = fs.get('entityCode', '')
            fc = fs.get('fieldCode', '')
            if ec not in entity_index:
                errors.append(f'{bc}/SECURITY: fieldSecurity entityCode "{ec}" 不在 MODEL entities 中')
            elif fc not in entity_index.get(ec, {}):
                errors.append(f'{bc}/SECURITY: fieldSecurity fieldCode "{fc}" 不在 entity "{ec}" 中')
            else:
                attr = entity_index[ec][fc]
                sr = attr.get('semanticRole', '')
                if sr in ('CROSS_BO_REF', 'TECHNICAL_ID', 'PARENT_REF', 'BUSINESS_KEY'):
                    errors.append(f'{bc}/SECURITY: fieldSecurity 不应覆盖 {sr} 字段 "{ec}.{fc}" — 该字段为外键/技术键，不包含业务敏感内容；行级安全通过 rowSecurity 控制，名称脱敏应在目标 BO 的 SECURITY 中处理')

        # authzProjection
        for attr in s_data.get('content', {}).get('authzProjection', {}).get('attributes', []):
            src = attr.get('source', {})
            ec = src.get('entityCode', '')
            fc = src.get('fieldCode', '')
            if ec not in entity_index:
                errors.append(f'{bc}/SECURITY: authzProjection source.entityCode "{ec}" 不在 MODEL entities 中')
            elif fc not in entity_index.get(ec, {}):
                errors.append(f'{bc}/SECURITY: authzProjection source.fieldCode "{fc}" 不在 entity "{ec}" 中')

    # ── E. VIEW fragment ──
    view = frags.get('VIEW')
    if view:
        v_fp, v_data = view
        # 判断 BO 是否只读：OPERATION 中无 CREATE/UPDATE/DELETE 主数据操作。
        # 只读 BO（如外部系统同步的映射视图）的 CROSS_BO_REF/CROSS_BO_DISPLAY
        # 字段不可编辑、不可导入，豁免 editableInForm/importable/formType/showInList 硬性要求。
        operation = frags.get('OPERATION')
        is_readonly_bo = False
        if operation:
            ops = operation[1].get('content', {}).get('operations', [])
            write_actions = {'CREATE', 'UPDATE', 'DELETE'}
            is_readonly_bo = bool(ops) and all(
                op.get('primaryDataAction', op.get('operationKind', '')) not in write_actions
                for op in ops
            )
        for fv in v_data.get('content', {}).get('fieldViews', []):
            ec = fv.get('entityCode', '')
            fc = fv.get('fieldCode', '')
            computed = fv.get('computedField')
            if ec not in entity_index:
                errors.append(f'{bc}/VIEW: entityCode "{ec}" 不在 MODEL entities 中')
            elif fc not in entity_index.get(ec, {}):
                if computed:
                    for src in computed.get('sources', []):
                        src_ec = src.get('entityCode', '')
                        src_fc = src.get('fieldCode', '')
                        if src_ec not in entity_index:
                            errors.append(f'{bc}/VIEW: computedField {ec}.{fc} source.entityCode "{src_ec}" 不在 MODEL entities 中')
                        elif src_fc not in entity_index.get(src_ec, {}):
                            errors.append(f'{bc}/VIEW: computedField {ec}.{fc} source.fieldCode "{src_fc}" 不在 entity "{src_ec}" 中')
                    if fv.get('editableInForm', False):
                        errors.append(f'{bc}/VIEW: computedField {ec}.{fc} editableInForm 不得为 true')
                    if fv.get('importable', False):
                        errors.append(f'{bc}/VIEW: computedField {ec}.{fc} importable 不得为 true')
                else:
                    errors.append(f'{bc}/VIEW: fieldCode "{fc}" 不在 entity "{ec}" 中')

            # OBJECT_SELECT: check refObject vs MODEL crossBoRef
            ft = fv.get('formType', '')
            ro = fv.get('refObject', '')
            if ft == 'OBJECT_SELECT':
                if ec in entity_index and fc in entity_index.get(ec, {}):
                    attr = entity_index[ec][fc]
                    cbr = attr.get('crossBoRef', {})
                    expected = cbr.get('refBoCode', '') if cbr else ''
                    if expected and ro != expected:
                        errors.append(f'{bc}/VIEW: {ec}.{fc} OBJECT_SELECT refObject "{ro}" != MODEL crossBoRef.refBoCode "{expected}"')
                    elif expected and not ro:
                        warnings.append(f'{bc}/VIEW: {ec}.{fc} OBJECT_SELECT 但 refObject 未设置 (期望 "{expected}")')
                    elif not expected:
                        warnings.append(f'{bc}/VIEW: {ec}.{fc} OBJECT_SELECT 但 MODEL 中该字段无 CROSS_BO_REF')

            # Check refObject pattern
            if ro and not bo_code_pattern.match(ro):
                errors.append(f'{bc}/VIEW: {ec}.{fc} refObject "{ro}" 不符合 pattern ^[a-z][a-z0-9-]*$')

            # SELECT/MULTI_SELECT must have dictCode
            if ft in ('SELECT', 'MULTI_SELECT') and not fv.get('dictCode'):
                errors.append(f'{bc}/VIEW: {ec}.{fc} formType={ft} 缺少 dictCode')

            # ── CROSS_BO_REF / CROSS_BO_DISPLAY VIEW pattern checks ──
            if ec in entity_index and fc in entity_index.get(ec, {}):
                attr = entity_index[ec][fc]
                sr = attr.get('semanticRole', '')
                if sr == 'CROSS_BO_REF':
                    cbr = attr.get('crossBoRef', {})
                    ref_bo = cbr.get('refBoCode', '')
                    display_fields = cbr.get('displayFields', [])
                    name_ref = next((df['refFieldCode'] for df in display_fields if df.get('displayRole') == 'NAME'), '')
                    expected_ft = 'USER_SELECT' if ref_bo == 'users' else 'OBJECT_SELECT'
                    if fv.get('showInList') is not True:
                        warnings.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} showInList 建议为 true（若 CROSS_BO_DISPLAY 字段已覆盖列表展示可忽略）')
                    if fv.get('showInDetail') is not True:
                        warnings.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} showInDetail 建议为 true（若 CROSS_BO_DISPLAY 字段已覆盖详情展示可忽略）')
                    if fv.get('editableInForm') is not True and not is_readonly_bo:
                        errors.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} editableInForm 应为 true')
                    if fv.get('formType', '') != expected_ft:
                        errors.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} formType 应为 {expected_ft}（refBoCode={ref_bo}），实际为 {fv.get("formType", "")}')
                    if ref_bo and fv.get('refObject', '') != ref_bo:
                        errors.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} refObject "{fv.get("refObject", "")}" != MODEL crossBoRef.refBoCode "{ref_bo}"')
                    if name_ref and fv.get('refField', '') != name_ref:
                        errors.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} refField "{fv.get("refField", "")}" != MODEL displayField NAME refFieldCode "{name_ref}"')
                    if fv.get('queryable') is not True:
                        warnings.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} queryable 建议为 true（若通过 CROSS_BO_DISPLAY 字段搜索可忽略）')
                    if fv.get('dataType', '') != 'string':
                        errors.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} dataType 应为 string（Snowflake 精度保护），实际为 {fv.get("dataType", "")}')
                    if fv.get('importable') is not True and not is_readonly_bo:
                        errors.append(f'{bc}/VIEW: CROSS_BO_REF {ec}.{fc} importable 应为 true')
                elif sr == 'CROSS_BO_DISPLAY':
                    # redundant: true 时 dataType 应跟随本地 MODEL 属性 type；
                    # redundant: false 时 dataType 取决于目标 BO 对应字段类型，
                    # 校验器不做跨 BO 类型查询，仅给出 INFO 提示。
                    is_redundant = attr.get('redundant', False)
                    attr_type = attr.get('type', 'STRING')
                    type_map = {
                        'STRING': 'string', 'INTEGER': 'integer', 'LONG': 'long',
                        'DECIMAL': 'decimal', 'BOOLEAN': 'boolean',
                        'DATE': 'date', 'DATETIME': 'datetime'
                    }
                    expected_dt = type_map.get(attr_type, 'string') if is_redundant else None
                    if fv.get('showInList') is not True and not is_readonly_bo:
                        warnings.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} showInList 建议为 true（若已有 NORMAL 同义字段覆盖列表展示可忽略）')
                    if fv.get('showInDetail') is not True:
                        errors.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} showInDetail 应为 true')
                    if fv.get('editableInForm') is not False:
                        errors.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} editableInForm 应为 false（后端解析，前端只读）')
                    # formType 对只读展示字段语义模糊：展示形态由 format 字段权威承载，
                    # formType 允许 INPUT（纯文本）或跟随 dataType 的控件类型，仅提示不一致。
                    display_form_type_map = {
                        'string': 'INPUT', 'datetime': 'DATETIME', 'date': 'DATE',
                        'integer': 'NUMBER', 'decimal': 'NUMBER', 'boolean': 'SWITCH',
                    }
                    dt = fv.get('dataType', '')
                    expected_form_type = display_form_type_map.get(dt)
                    if expected_form_type and fv.get('formType', '') not in ('INPUT', expected_form_type):
                        warnings.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} formType="{fv.get("formType", "")}" 与 dataType={dt} 不一致（建议 INPUT 或 {expected_form_type}，展示形态由 format 字段承载）')
                    if fv.get('queryable') is not True:
                        errors.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} queryable 应为 true（支持按名称模糊搜索）')
                    if is_redundant and fv.get('dataType', '') != expected_dt:
                        errors.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} dataType 应为 {expected_dt}（跟随冗余列 MODEL type），实际为 {fv.get("dataType", "")}')
                    elif not is_redundant and fv.get('dataType', '') != 'string':
                        infos.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} redundant=false 且 dataType="{fv.get("dataType", "")}"，请确认是否与目标 BO 字段类型一致')
                    if fv.get('importable') is not False:
                        errors.append(f'{bc}/VIEW: CROSS_BO_DISPLAY {ec}.{fc} importable 应为 false（不接收名称输入）')

    # Cross-fragment: SECURITY HIDDEN vs VIEW exportable
    _sec = frags.get('SECURITY')
    _view = frags.get('VIEW')
    if _sec and _view:
        hidden_fields = {
            (fs.get('entityCode', ''), fs.get('fieldCode', ''))
            for fs in _sec[1].get('content', {}).get('fieldSecurity', [])
            if fs.get('fieldControl') == 'HIDDEN'
        }
        for fv in _view[1].get('content', {}).get('fieldViews', []):
            key = (fv.get('entityCode', ''), fv.get('fieldCode', ''))
            if key in hidden_fields and fv.get('exportable', True):
                errors.append(f'{bc}: SECURITY fieldControl=HIDDEN 但 VIEW exportable=true [{key[0]}.{key[1]}]')

    # ── F. RULE fragment ──
    rule = frags.get('RULE')
    if rule:
        r_fp, r_data = rule
        seen_rule_codes = set()
        for r in r_data.get('content', {}).get('rules', []):
            rc = r.get('code', '')
            if rc in seen_rule_codes:
                errors.append(f'{bc}/RULE: 重复 rule code "{rc}"')
            seen_rule_codes.add(rc)

            rt = r.get('ruleType', '')
            valid_rule_types = {'COMPLEX_VALIDATION', 'STATE', 'DERIVATION', 'PERMISSION', 'AUTOMATION', 'CONSISTENCY'}
            if rt not in valid_rule_types:
                errors.append(f'{bc}/RULE: rule "{rc}" ruleType "{rt}" 不在 {valid_rule_types}')

            sev = r.get('severity', '')
            if sev and sev not in ('ERROR', 'WARN', 'INFO'):
                errors.append(f'{bc}/RULE: rule "{rc}" severity "{sev}" 不在 [ERROR,WARN,INFO]')

            trig = r.get('trigger') or r.get('triggerTiming', '')
            valid_triggers = {'BEFORE_VALIDATE', 'BEFORE_OPERATION', 'AFTER_OPERATION', 'ON_STATE_CHANGE', 'ON_PUBLISH', 'ON_READ'}
            if trig and trig not in valid_triggers:
                errors.append(f'{bc}/RULE: rule "{rc}" trigger "{trig}" 不在 {valid_triggers}')

            scope = r.get('scope', 'BO')
            ec = r.get('entityCode', '')
            fc = r.get('fieldCode', '')

            if scope == 'ENTITY' and not ec:
                errors.append(f'{bc}/RULE: rule "{rc}" scope=ENTITY 缺少 entityCode')
            if scope == 'FIELD' and (not ec or not fc):
                errors.append(f'{bc}/RULE: rule "{rc}" scope=FIELD 缺少 entityCode 或 fieldCode')

            if ec and ec not in entity_index:
                errors.append(f'{bc}/RULE: rule "{rc}" entityCode "{ec}" 不在 MODEL entities 中')
            if ec and fc and fc not in entity_index.get(ec, {}):
                errors.append(f'{bc}/RULE: rule "{rc}" fieldCode "{fc}" 不在 entity "{ec}" 中')

            cbr = r.get('crossBoRef')
            if scope == 'CROSS_BO' and not cbr:
                errors.append(f'{bc}/RULE: rule "{rc}" scope=CROSS_BO 缺少 crossBoRef')
            if cbr:
                lec = cbr.get('localEntityCode', '')
                lfc = cbr.get('localFieldCode', '')
                if lec and lec not in entity_index:
                    errors.append(f'{bc}/RULE: rule "{rc}" crossBoRef.localEntityCode "{lec}" 不在 MODEL entities 中')
                elif lec and lfc and lfc not in entity_index.get(lec, {}):
                    errors.append(f'{bc}/RULE: rule "{rc}" crossBoRef.localFieldCode "{lfc}" 不在 entity "{lec}" 中')
                ref_bo = cbr.get('refBoCode', '')
                if ref_bo and ref_bo not in all_bos:
                    errors.append(f'{bc}/RULE: rule "{rc}" crossBoRef.refBoCode "{ref_bo}" 指向不存在的 BO')

    # ── G. OPERATION fragment ──
    operation = frags.get('OPERATION')
    op_codes_set = set()
    if operation:
        o_fp, o_data = operation
        seen_op_codes = set()
        for op in o_data.get('content', {}).get('operations', []):
            oc = op.get('code', '')
            if oc in seen_op_codes:
                errors.append(f'{bc}/OPERATION: 重复 operation code "{oc}"')
            seen_op_codes.add(oc)
            op_codes_set.add(oc)

            kind = op.get('operationKind', '')
            valid_kinds = {'CREATE', 'UPDATE', 'DELETE', 'STATE_CHANGE', 'IMPORT', 'EXPORT', 'MERGE', 'CUSTOM'}
            if kind and kind not in valid_kinds:
                errors.append(f'{bc}/OPERATION: "{oc}" operationKind "{kind}" 不在 {valid_kinds}')

            scope = op.get('scope', '')
            valid_scopes = {'BO', 'ENTITY', 'GLOBAL'}
            if scope and scope not in valid_scopes:
                errors.append(f'{bc}/OPERATION: "{oc}" scope "{scope}" 不在 {valid_scopes}')

            if not op.get('authzAction'):
                errors.append(f'{bc}/OPERATION: "{oc}" 缺少 authzAction')

            scope = op.get('scope', '')
            ec = op.get('entityCode', '')
            if scope == 'ENTITY' and not ec:
                errors.append(f'{bc}/OPERATION: operation "{oc}" scope=ENTITY 缺少 entityCode')
            if ec and ec not in entity_index:
                errors.append(f'{bc}/OPERATION: operation "{oc}" entityCode "{ec}" 不在 MODEL entities 中')

        # authzAction merge report (INFO level)
        authz_action_counts = defaultdict(list)
        for op in o_data.get('content', {}).get('operations', []):
            aa = op.get('authzAction', '')
            if aa:
                authz_action_counts[aa].append(op.get('code', '?'))
        for aa, codes in authz_action_counts.items():
            if len(codes) > 1:
                msg = f'{bc}/OPERATION: authzAction "{aa}" 合并了 {len(codes)} 个操作 → {codes}'
                infos.append(msg)
                print(f'     ℹ️  {msg}')

    # Check RULE operationCode references
    if rule and operation:
        for r in r_data.get('content', {}).get('rules', []):
            oc = r.get('operationCode', '')
            if oc and oc not in op_codes_set:
                errors.append(f'{bc}/RULE: rule "{r.get("code")}" operationCode "{oc}" 引用了不存在的 OPERATION')

    # ── Print summary for this BO ──
    bo_errs = [e for e in errors if bc in e.split('/')[0] or e.startswith(bc + ':')]
    bo_warns = [w for w in warnings if bc in w.split('/')[0] or w.startswith(bc + ':')]
    if bo_errs:
        print(f'  🔴 {len(bo_errs)} 个错误:')
        for e in bo_errs:
            print(f'     ❌ {e}')
    if bo_warns:
        print(f'  🟡 {len(bo_warns)} 个警告:')
        for w in bo_warns:
            print(f'     ⚠️  {w}')
    if not bo_errs and not bo_warns:
        print(f'  ✅ 全部通过')

# ══════════════════════════════════════════════════════════════════
# Phase 3 — Cross-BO Naming Consistency
# ══════════════════════════════════════════════════════════════════
print(f'\n{"="*70}')
print(f'  Phase 3 — 跨 BO 命名一致性')
print(f'{"="*70}')

# 收集所有 MODEL 数据
all_models = {}
for bc_code in sorted(all_bos):
    model_frag = fragments_by_bo[bc_code].get('MODEL')
    if model_frag:
        all_models[bc_code] = model_frag[1].get('content', {})

# ── 3a. 同名不同码 ──
name_to_codes = defaultdict(set)
for bc_code, model in all_models.items():
    for ent in model.get('entities', []):
        for attr in ent.get('attributes', []):
            an = attr.get('name', '').strip()
            ac = attr.get('code', '')
            if an:
                name_to_codes[an].add(ac)

naming_conflicts = 0
for name, codes in sorted(name_to_codes.items()):
    if len(codes) > 1:
        naming_conflicts += 1
        msg = f'同名不同码: "{name}" → {sorted(codes)}'
        warnings.append(msg)
        print(f'  ⚠ {msg}')

# ── 3b. CROSS_BO_REF displayFields localCode 一致性 ──
display_refs = defaultdict(list)
for bc_code, model in all_models.items():
    for ent in model.get('entities', []):
        for attr in ent.get('attributes', []):
            cr = attr.get('crossBoRef')
            if cr and cr.get('displayFields'):
                target = cr.get('refBoCode', '?')
                for df in cr['displayFields']:
                    remote = df.get('refFieldCode', '')
                    local = df.get('localCode', '')
                    display_refs[(target, remote)].append({'bo': bc_code, 'local_code': local})

for (target, remote), refs in display_refs.items():
    local_codes = set(r['local_code'] for r in refs)
    if len(local_codes) > 1:
        detail = ', '.join(f'{lc}←{",".join(r["bo"] for r in refs if r["local_code"]==lc)}' for lc in sorted(local_codes))
        msg = f'displayFields 不统一: 目标 {target}.{remote} → {detail}'
        warnings.append(msg)
        print(f'  ⚠ {msg}')

# ── 3c. 同 BO 内跨 entity 同名属性类型一致性 ──
for bc_code, model in all_models.items():
    entities = model.get('entities', [])
    if len(entities) < 2:
        continue
    attr_types = defaultdict(dict)
    for ent in entities:
        ec = ent['code']
        for attr in ent.get('attributes', []):
            ac = attr['code']
            at = attr.get('type', '')
            attr_types[ac][ec] = at
    for ac, type_map in attr_types.items():
        if len(type_map) >= 2 and len(set(type_map.values())) > 1:
            detail = ', '.join(f'{ec}={t}' for ec, t in type_map.items())
            errors.append(f'{bc_code}/MODEL: 属性 "{ac}" 类型不一致 — {detail}')
            print(f'  ❌ {bc_code}: "{ac}" 类型不一致 — {detail}')

if naming_conflicts == 0 and not [e for e in errors if '类型不一致' in e]:
    print(f'  ✅ 命名一致性检查通过')

# ══════════════════════════════════════════════════════════════════
# Final summary
# ══════════════════════════════════════════════════════════════════
print(f'\n{"="*70}')
print(f'  总结')
print(f'{"="*70}')
if errors:
    print(f'  🔴 {len(errors)} 个错误')
if warnings:
    print(f'  🟡 {len(warnings)} 个警告')
if infos:
    print(f'  ℹ️  {len(infos)} 个信息')
if not errors and not warnings:
    print(f'  ✅ 所有 BO 全部通过!')
elif not errors:
    print(f'  ✅ 所有强制检查通过 ({len(warnings)} 个建议)')

sys.exit(0 if not errors else 1)
