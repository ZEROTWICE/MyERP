#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""直接使用 Alembic API 合并迁移头并升级数据库"""
import os
import sys

# 添加项目路径
project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)
os.chdir(project_path)

print("当前工作目录:", os.getcwd())
print("=" * 60)

# 导入Flask应用
from app import create_app, db
from flask_migrate import Migrate
from alembic import command
from alembic.config import Config as AlembicConfig

# 创建应用
app = create_app()
migrate = Migrate(app, db)

# 获取 Alembic 配置
with app.app_context():
    from flask_migrate import _get_config
    from alembic.script import ScriptDirectory
    
    config = _get_config()
    script = ScriptDirectory.from_config(config)
    
    print("\n【步骤 1】查看当前迁移头...")
    print("-" * 60)
    heads_list = script.get_heads()
    print(f"发现 {len(heads_list)} 个迁移头:")
    for i, head in enumerate(heads_list, 1):
        print(f"  {i}. {head}")
    
    if len(heads_list) > 1:
        print(f"\n【步骤 2】合并 {len(heads_list)} 个迁移头...")
        print("-" * 60)
        try:
            # 合并所有头
            command.merge(config, revisions='heads', message='merge_multiple_heads')
            print("✓ 迁移头已合并")
        except Exception as e:
            print(f"✗ 合并失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print("\n只有一个头，无需合并")
    
    print(f"\n【步骤 3】执行数据库升级到最新版本...")
    print("-" * 60)
    try:
        command.upgrade(config, 'head')
        print("✓ 数据库升级完成")
    except Exception as e:
        print(f"✗ 升级失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print("\n" + "=" * 60)
print("✓ 所有迁移操作完成！")
print("=" * 60)

