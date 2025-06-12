# 易耗品管理功能文档

## 概述

易耗品管理模块是在原材料管理基础上开发的新功能，采用相同的设计模式，提供完整的易耗品生命周期管理。

## 功能特性

### 1. 易耗品品类管理
- **品类创建**: 支持创建易耗品品类，包含名称、编码、描述等信息
- **品类编辑**: 可修改品类信息，支持启用/禁用状态
- **品类删除**: 仅允许删除未被使用的品类
- **唯一性验证**: 品类名称和编码必须唯一

### 2. 易耗品管理
- **入库管理**: 支持易耗品入库，自动生成内部编号和全局流水号
- **库存查询**: 多维度搜索和筛选功能
- **状态管理**: 支持在库、已使用、报废、过期等状态
- **使用记录**: 记录易耗品使用情况，包括使用人、用途、数量等

### 3. 智能预警
- **低库存预警**: 当库存低于设定阈值时显示警告
- **过期预警**: 自动识别已过期和即将过期的易耗品
- **状态标识**: 通过颜色和图标直观显示易耗品状态

### 4. 数据统计
- **总体统计**: 显示总数量、在库数量、低库存、过期等统计信息
- **分类统计**: 按品类统计易耗品数量
- **状态分布**: 展示不同状态的易耗品分布

## 数据库设计

### 易耗品品类表 (consumable_categories)
```sql
CREATE TABLE consumable_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,        -- 品类名称
    code VARCHAR(20) NOT NULL UNIQUE,         -- 品类编码
    description TEXT,                         -- 描述
    is_active BOOLEAN DEFAULT 1,              -- 是否启用
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,                       -- 创建人
    FOREIGN KEY (created_by) REFERENCES users (id)
);
```

### 易耗品表 (consumables)
```sql
CREATE TABLE consumables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    global_sn VARCHAR(50) NOT NULL UNIQUE,    -- 全局流水号
    supplier VARCHAR(100) NOT NULL,           -- 供应商
    category_id INTEGER NOT NULL,             -- 品类ID
    specification VARCHAR(200),               -- 规格型号
    supplier_number VARCHAR(100) NOT NULL,    -- 供应商编号
    internal_number VARCHAR(50) UNIQUE,       -- 内部编号
    quantity DECIMAL(10,3) NOT NULL DEFAULT 0, -- 数量
    unit VARCHAR(20) NOT NULL,                -- 单位
    unit_price DECIMAL(10,2) DEFAULT 0,       -- 单价
    total_price DECIMAL(12,2) DEFAULT 0,      -- 总价
    expiry_date DATE,                         -- 过期日期
    storage_location VARCHAR(100),            -- 存放位置
    min_stock_level DECIMAL(10,3) DEFAULT 0,  -- 最低库存预警
    storage_date DATETIME NOT NULL,           -- 入库时间
    notes TEXT,                               -- 备注
    status VARCHAR(20) DEFAULT 'in_stock',    -- 状态
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES consumable_categories (id),
    CHECK (status IN ('in_stock', 'used', 'scrapped', 'expired')),
    CHECK (quantity >= 0),
    CHECK (unit_price >= 0),
    CHECK (min_stock_level >= 0)
);
```

## 模型设计

### ConsumableCategory 模型
- 继承基础模型功能
- 提供品类管理的核心方法
- 支持关联查询易耗品数量
- 实现 `to_dict()` 方法用于API返回

### Consumable 模型
- 自动生成全局流水号和内部编号
- 计算属性：`consumable_name`、`category_code`
- 状态判断：`is_low_stock`、`is_expired`、`days_to_expiry`
- 自动计算总价：`total_price = unit_price * quantity`

## 表单设计

### ConsumableCategoryForm
- 品类名称验证（必填，最大100字符）
- 品类编码验证（必填，最大20字符）
- 描述信息（可选，最大500字符）
- 启用状态（布尔值）

### ConsumableInboundForm
- 供应商信息（必填）
- 品类选择（下拉选择，必填）
- 规格型号（可选）
- 供应商编号（必填）
- 数量和单位（必填）
- 单价（可选）
- 过期日期（可选）
- 存放位置（可选）
- 最低库存预警（可选）

### ConsumableSearchForm
- 关键词搜索
- 品类筛选
- 状态筛选
- 供应商筛选
- 日期范围筛选
- 特殊条件筛选（低库存、过期、即将过期）

## 路由设计

### 主要路由
- `/consumables` - 易耗品管理主页
- `/consumables/inbound` - 易耗品入库
- `/consumables/<id>` - 易耗品详情/更新/删除
- `/consumables/<id>/use` - 使用易耗品
- `/consumables/categories` - 品类管理
- `/consumables/categories/add` - 添加品类
- `/consumables/categories/<id>` - 品类详情/更新/删除
- `/api/consumable-categories` - 品类列表API

### API设计
所有API遵循RESTful设计原则：
- GET: 获取资源
- POST: 创建资源
- PUT: 更新资源
- DELETE: 删除资源

## 前端界面

### 易耗品管理主页
- 统计信息卡片展示
- 高级搜索表单
- 易耗品列表表格
- 状态颜色标识
- 操作按钮组

### 易耗品入库页面
- 表单验证
- 品类下拉选择
- 自动计算总价
- 日期选择器

### 品类管理页面
- 品类列表展示
- 模态框添加/编辑
- 关联易耗品数量显示
- 状态管理

## 权限控制

### 角色权限
- **管理员**: 所有功能权限
- **普通用户**: 查看、入库、使用权限
- **删除操作**: 仅管理员可执行

### 数据安全
- 所有操作记录审计日志
- 支持操作回滚
- 数据完整性约束
- 输入验证和过滤

## 集成功能

### 审计日志
- 记录所有增删改操作
- 包含操作前后数据对比
- 支持操作回滚
- 操作人员追踪

### 序列号管理
- 自动生成全局流水号
- 自动生成内部编号
- 保证编号唯一性
- 支持自定义编号规则

### 导航集成
- 集成到库存管理菜单
- 三级菜单结构
- 面包屑导航
- 快速访问链接

## 示例数据

系统预置了6个品类和5个易耗品示例：

### 品类示例
1. 工具类 (TOOL) - 各种工具和器具
2. 化学品 (CHEM) - 化学试剂和溶剂
3. 电子元件 (ELEC) - 电子器件和元件
4. 办公用品 (OFFICE) - 办公室日常用品
5. 安全防护 (SAFETY) - 安全防护用品
6. 清洁用品 (CLEAN) - 清洁和维护用品

### 易耗品示例
1. 螺丝刀套装 - 工具类
2. 酒精 - 化学品
3. 电阻器 - 电子元件
4. A4纸 - 办公用品
5. 防护手套 - 安全防护

## 技术特点

### 设计模式
- 模仿原材料管理模式
- 保持代码一致性
- 复用现有组件
- 遵循项目规范

### 响应式设计
- Bootstrap 5框架
- 移动端适配
- 表格响应式
- 模态框优化

### 用户体验
- 直观的状态标识
- 智能搜索筛选
- 批量操作支持
- 实时数据更新

## 扩展性

### 未来功能
- 易耗品采购管理
- 供应商评估
- 成本分析报表
- 库存预测
- 条码/二维码支持
- 移动端APP

### 集成可能
- ERP系统集成
- 财务系统对接
- 采购系统联动
- 报表系统扩展

## 维护说明

### 数据备份
- 定期备份数据库
- 导出重要数据
- 版本控制管理

### 性能优化
- 数据库索引优化
- 查询语句优化
- 缓存策略
- 分页加载

### 故障排除
- 日志记录完整
- 错误处理机制
- 数据恢复方案
- 用户反馈渠道

---

## 总结

易耗品管理模块成功实现了完整的易耗品生命周期管理，从入库到使用的全流程跟踪。通过模仿原材料管理的成功模式，确保了功能的完整性和代码的一致性。该模块不仅满足了当前的业务需求，还为未来的功能扩展奠定了良好的基础。

**主要成就：**
- ✅ 完整的数据库设计和模型实现
- ✅ 用户友好的界面设计
- ✅ 完善的权限控制和安全机制
- ✅ 智能的预警和统计功能
- ✅ 良好的扩展性和维护性

**技术亮点：**
- 🎯 模块化设计，易于维护
- 🔒 完善的数据安全保护
- 📊 丰富的统计和分析功能
- 🚀 优秀的用户体验设计
- 🔧 强大的搜索和筛选能力 