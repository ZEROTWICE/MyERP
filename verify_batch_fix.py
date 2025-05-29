#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证批次开始生产功能修复
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import ProductionBatch, ProductionBatchItem

def verify_batch_fix():
    """验证批次开始生产功能修复"""
    app = create_app()
    
    with app.app_context():
        print("=== 验证批次开始生产功能修复 ===")
        
        # 查找所有批次
        batches = ProductionBatch.query.all()
        print(f"📊 总批次数量: {len(batches)}")
        
        # 统计各状态的批次
        pending_batches = [b for b in batches if b.status == 'pending']
        in_progress_batches = [b for b in batches if b.status == 'in_progress']
        completed_batches = [b for b in batches if b.status == 'completed']
        
        print(f"   待开始批次: {len(pending_batches)}")
        print(f"   进行中批次: {len(in_progress_batches)}")
        print(f"   已完成批次: {len(completed_batches)}")
        
        # 检查进行中的批次是否有正确的项目状态
        print("\n🔍 检查进行中批次的项目状态:")
        for batch in in_progress_batches:
            items = ProductionBatchItem.query.filter_by(batch_id=batch.id).all()
            pending_items = [item for item in items if item.status == 'pending']
            in_progress_items = [item for item in items if item.status == 'in_progress']
            completed_items = [item for item in items if item.status == 'completed']
            
            print(f"   批次 {batch.batch_number}:")
            print(f"     总项目: {len(items)}")
            print(f"     待生产: {len(pending_items)}")
            print(f"     进行中: {len(in_progress_items)}")
            print(f"     已完成: {len(completed_items)}")
            
            if len(pending_items) > 0 and len(in_progress_items) == 0:
                print(f"     ⚠️  警告: 批次状态为进行中，但所有项目都是待生产状态")
            elif len(in_progress_items) > 0 or len(completed_items) > 0:
                print(f"     ✅ 正常: 批次状态与项目状态一致")
        
        print("\n📋 修复功能说明:")
        print("   - 当点击'开始生产'按钮时，批次状态会更新为'进行中'")
        print("   - 同时，所有'待生产'的批次项目会自动更新为'进行中'")
        print("   - 这确保了批次状态与项目状态的一致性")
        
        print("\n✅ 修复验证完成！")

if __name__ == '__main__':
    verify_batch_fix() 