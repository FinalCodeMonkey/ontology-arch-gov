-- BO 元数据治理表结构
-- 设计态 Fragment + 发布态 BO Snapshot

CREATE TABLE IF NOT EXISTS gov_bo_meta_fragment (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    app_code VARCHAR(50) NOT NULL,
    bo_code VARCHAR(100) NOT NULL,
    meta_type VARCHAR(20) NOT NULL,
    content_json TEXT NOT NULL,
    draft_version INT NOT NULL,
    base_release_version INT,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    schema_version VARCHAR(30) NOT NULL,
    checksum CHAR(64) NOT NULL,
    change_note VARCHAR(500),
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_by VARCHAR(100),
    published_at TIMESTAMP,
    is_deleted INT DEFAULT 0,
    CONSTRAINT uk_gov_bo_meta_fragment UNIQUE (tenant_id, app_code, bo_code, meta_type, draft_version)
);

CREATE INDEX idx_gov_bo_meta_fragment_bo
    ON gov_bo_meta_fragment (tenant_id, app_code, bo_code, status);

CREATE INDEX idx_gov_bo_meta_fragment_checksum
    ON gov_bo_meta_fragment (checksum);

CREATE TABLE IF NOT EXISTS gov_bo_meta_release (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    app_code VARCHAR(50) NOT NULL,
    bo_code VARCHAR(100) NOT NULL,
    bo_name VARCHAR(100) NOT NULL,
    release_version INT NOT NULL,
    draft_version INT,
    schema_version VARCHAR(30) NOT NULL,
    schema_view_json TEXT NOT NULL,
    source_fragments_json TEXT NOT NULL,
    checksum CHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PUBLISHED',
    is_current INT NOT NULL DEFAULT 0,
    release_note VARCHAR(500),
    published_by VARCHAR(100),
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted INT DEFAULT 0,
    CONSTRAINT uk_gov_bo_meta_release UNIQUE (tenant_id, app_code, bo_code, release_version)
);

CREATE INDEX idx_gov_bo_meta_release_current
    ON gov_bo_meta_release (tenant_id, app_code, bo_code, is_current, is_deleted);

CREATE INDEX idx_gov_bo_meta_release_checksum
    ON gov_bo_meta_release (checksum);

-- 建议由应用层补充的强约束：
-- 1. gov_bo_meta_fragment.meta_type in (MODEL, VALIDATION, SECURITY, RULE, VIEW, OPERATION)
-- 2. gov_bo_meta_fragment.status in (DRAFT, PUBLISHED, ARCHIVED)
-- 3. gov_bo_meta_release.status in (PUBLISHED, ARCHIVED, ROLLED_BACK)
-- 4. 同一 tenant_id/app_code/bo_code 仅允许一条 is_current=1 的未删除发布记录
