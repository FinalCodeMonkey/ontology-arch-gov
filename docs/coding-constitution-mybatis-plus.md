# MyBatis-Plus DDD 编码宪章

> 本文档将 `governance-profile.default.json` 中的设计意图映射为 MyBatis-Plus 技术栈的具体实现模式。
> 换技术栈时只需替换本宪章，Governance Profile 保持不变。

---

## 1. 分层架构

```
Controller  →  DomainService  →  Mapper (extends BaseMapper)
    ↓                              ↓
  DTO/ApiResponse              @TableName Entity
```

## 2. entityNature=BUSINESS → 实现模式

### 2.1 实体类

```java
// 独立 @TableName 实体类，含业务方法
@Data
@TableName("crm_opportunity_product")
public class OpportunityProduct {
    @TableId(type = IdType.ASSIGN_ID)  // SNOWFLAKE
    private Long id;
    private Long opportunityId;         // PARENT_REF
    private Long sceneId;               // CROSS_BO_REF (单值)
    private String productModel;        // CROSS_BO_REF
    private BigDecimal unitPrice;       // NORMAL 业务字段
    private Integer quantity;           // NORMAL 业务字段

    // 业务方法
    public BigDecimal calculateSubtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

### 2.2 持久化

```java
// 独立 Mapper 接口
@Mapper
public interface OpportunityProductMapper extends BaseMapper<OpportunityProduct> {
}
```

### 2.3 领域服务

```java
// 独立 DomainService
@Service
public class OpportunityProductDomainService {
    private final OpportunityProductMapper productMapper;

    @Transactional
    public void addProduct(Long opportunityId, OpportunityProduct product) { ... }
}
```

### 2.4 API

```java
// 嵌套 REST 端点
@RestController
@RequestMapping("/opportunities/{opportunityId}/products")
public class OpportunityProductController {
    @PostMapping
    public ApiResponse<OpportunityProductDTO> create(...) { }

    @PatchMapping("/{id}")
    public ApiResponse<OpportunityProductDTO> update(...) { }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(...) { }
}
```

### 2.5 DDL

```sql
CREATE TABLE crm_opportunity_product (
    id BIGINT PRIMARY KEY,
    opportunity_id BIGINT NOT NULL,
    scene_id BIGINT,
    product_model VARCHAR(100),
    unit_price DECIMAL(18,2),
    quantity INT,
    -- NORMAL 字段 ...
    KEY idx_opportunity_id (opportunity_id)  -- 普通索引，无唯一约束
);
```

---

## 3. entityNature=ASSOCIATION → 实现模式

### 3.1 方案选择

| 方案 | 适用场景 | Entity | Mapper |
|------|---------|--------|--------|
| **纯 SQL 管理**（推荐） | 无 redundant=true 的 CROSS_BO_DISPLAY | 不建 | 不建 — SQL 写在父 Mapper XML |
| 轻量 Entity + 内部 Mapper | 有 redundant=true 的 CROSS_BO_DISPLAY 需落库 | 建 @TableName | 建但不对外暴露 |

### 3.2 纯 SQL 管理方案（推荐，无冗余字段）

```xml
<!-- OpportunityMapper.xml -->
<mapper namespace="com.example.mapper.OpportunityMapper">

    <!-- 全量替换：先删后插 -->
    <delete id="deleteScenesByOpportunityId">
        DELETE FROM crm_opportunity_scene WHERE opportunity_id = #{opportunityId}
    </delete>

    <insert id="batchInsertScenes">
        INSERT INTO crm_opportunity_scene (id, opportunity_id, scene_id) VALUES
        <foreach collection="sceneIds" item="sceneId" separator=",">
            (#{idGenerator.nextId}, #{opportunityId}, #{sceneId})
        </foreach>
    </insert>

    <!-- 查询场景列表（详情页内嵌） -->
    <select id="selectScenesByOpportunityId" resultType="Long">
        SELECT scene_id FROM crm_opportunity_scene WHERE opportunity_id = #{opportunityId}
    </select>

</mapper>
```

```java
// 聚合根 DomainService 中管理
@Service
public class OpportunityDomainService {
    private final OpportunityMapper opportunityMapper;

    @Transactional
    public void updateScenes(Long opportunityId, List<Long> newSceneIds) {
        List<Long> distinctIds = newSceneIds.stream().distinct().toList();
        opportunityMapper.deleteScenesByOpportunityId(opportunityId);
        if (!distinctIds.isEmpty()) {
            opportunityMapper.batchInsertScenes(opportunityId, distinctIds);
        }
    }
}
```

### 3.3 DDL

两种方案共用同一 DDL：

```sql
CREATE TABLE crm_opportunity_scene (
    id BIGINT PRIMARY KEY,
    opportunity_id BIGINT NOT NULL,
    scene_id BIGINT NOT NULL,
    -- 仅当方案2 + redundant=true 时才有多余列：
    -- scene_name VARCHAR(100)  COMMENT 'CROSS_BO_DISPLAY+redundant',
    UNIQUE KEY uk_opp_scene (opportunity_id, scene_id)
);
```

### 3.4 方案2：轻量 Entity + 内部 Mapper（有冗余展示字段时）

当 `CROSS_BO_DISPLAY` 字段设置了 `redundant: true`，需要在 DB 落库存储展示字段的快照值，此时建轻量 Entity：

```java
// 轻量 Entity — 仅含外键 + 冗余展示字段，无业务方法
@Data
@TableName("crm_opportunity_scene")
public class OpportunityScene {
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;
    private Long opportunityId;       // PARENT_REF
    private Long sceneId;             // CROSS_BO_REF
    private String sceneName;         // CROSS_BO_DISPLAY (redundant=true)
    private String sceneCategory;     // CROSS_BO_DISPLAY (redundant=true)
}

// 内部 Mapper — 仅聚合根 DomainService 引用，不对外暴露
@Mapper
interface OpportunitySceneMapper extends BaseMapper<OpportunityScene> {
    @Delete("DELETE FROM crm_opportunity_scene WHERE opportunity_id = #{opportunityId}")
    int deleteByOpportunityId(Long opportunityId);
}
```

```java
// 聚合根 DomainService — 全量替换
@Service
public class OpportunityDomainService {
    private final OpportunitySceneMapper sceneMapper;  // ← 仅此处引用，不注入到其他 Service/Controller

    @Transactional
    public void updateScenes(Long opportunityId, List<SceneRef> scenes) {
        sceneMapper.deleteByOpportunityId(opportunityId);
        List<OpportunityScene> entities = scenes.stream().map(s -> {
            OpportunityScene e = new OpportunityScene();
            e.setOpportunityId(opportunityId);
            e.setSceneId(s.getSceneId());
            e.setSceneName(s.getSceneName());      // 冗余落库
            e.setSceneCategory(s.getSceneCategory());
            return e;
        }).toList();
        sceneMapper.insert(entities);
    }
}
```

### 3.5 父聚合根 DTO
public class OpportunityUpsertRequest {
    private String opportunityName;
    private List<Long> sceneIds;          // ASSOCIATION: ID 列表
    private List<OpportunityProductDTO> products;  // BUSINESS: 完整嵌套 DTO
}

// 详情响应 DTO
public class OpportunityDetailDTO {
    private Long id;
    private String opportunityName;
    private List<Long> sceneIds;          // ASSOCIATION: 仅 ID
    private List<OpportunityProductDTO> products;  // BUSINESS: 完整嵌套
}
```

---

## 4. 决策速查表

| 设计意图 (Profile) | MyBatis-Plus 实现 |
|---|---|
| 独立持久化接口 | 独立 `@Mapper extends BaseMapper` |
| 无独立持久化接口 | SQL 写在父 Mapper XML，不建独立 Mapper |
| 独立 API 端点 | `@RestController` + `@RequestMapping("/parent/{id}/routeSegment")` |
| 无独立 API 端点 | 通过父聚合根 DTO 的 `List<Long> xxxIds` 字段提交 |
| DB 唯一约束 | `UNIQUE KEY (parent_id, ref_id)` |
| 由父聚合根统一管理 | `DELETE WHERE parent_id=?` + 批量 `INSERT`，同一事务 |
| 全量替换策略 | 先删后插，不去重时依赖 DB UNIQUE 兜底 |
| ID 策略 SNOWFLAKE | `@TableId(type = IdType.ASSIGN_ID)` |
| 逻辑删除 | `@TableLogic` + `is_deleted` 字段 |
| 审计字段 | MyBatis-Plus `MetaObjectHandler` 自动填充 `created_time/updated_time/created_by/updated_by` |
