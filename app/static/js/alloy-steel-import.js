/**
 * 合金钢辙叉数据导入的前端共用渲染器。
 *
 * 「合金钢辙叉计件工价标准」（process_prices.html）与「48页表格 BOM」（products.html）
 * 两个入口各自负责取文件与 POST（URL、字段名不同），报告的结构也分成
 * kind='process_price' 与 kind='bom' 两套计数字段，但渲染口径完全一致，
 * 因此把报告渲染收敛到这一个函数，避免两份模板各写一份易漂移的副本。
 *
 * 报告可能很长（源数据提示可达 284 条），所以用 SweetAlert2 的可滚动弹窗，
 * 而不是会自动消失的 alert。
 */
function showAlloyImportReport(data, dryRun, sourceLabel) {
    const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const rep = data.data || {};
    const lines = [];
    lines.push(`<b>${dryRun ? '试运行（未写入数据库）' : '导入完成'}</b>　${escapeHtml(data.message || '')}`);
    if (rep.kind === 'process_price') {
        lines.push(`明细行 <b>${rep.total_rows}</b>：普通工序 新建 ${rep.normal_created} / 升版 ${rep.normal_versioned} / 未变 ${rep.normal_unchanged}`);
        lines.push(`小计 新建 ${rep.subtotal_created} / 升版 ${rep.subtotal_versioned} / 未变 ${rep.subtotal_unchanged}，小计成员关系 ${rep.groups_created} 条`);
    } else {
        lines.push(`明细行 <b>${rep.total_rows}</b>（${rep.file_count} 个文件 / ${rep.sheet_count} 个工作表）：父件 ${rep.parents_total}（新建 ${rep.parents_created} / 复用 ${rep.parents_reused}）`);
        lines.push(`子件 ${rep.children_total}（新建 ${rep.children_created} / 复用 ${rep.children_reused}）`);
        lines.push(`BOM 明细 写入 ${rep.bom_rows_created} 条（合并 ${rep.bom_rows_merged}，清理旧明细 ${rep.bom_rows_removed}，仅凭名称定位 ${rep.rows_without_key}）`);
    }
    lines.push(`错误 <b>${rep.errors ? rep.errors.count : 0}</b> 条 · 导入警告 ${rep.warnings ? rep.warnings.count : 0} 条 · 源数据提示 ${(rep.source_warnings || []).length} 条 · 无法解析 ${(rep.error_sheets || []).length} 个`);
    const block = (title, items) => {
        if (!items || !items.length) return;
        lines.push('', `<b>${title}</b>`);
        items.forEach(x => lines.push('· ' + escapeHtml(x)));
    };
    block('错误（前 10 条）', (rep.errors && rep.errors.items || []).slice(0, 10));
    block('导入警告（前 10 条）', (rep.warnings && rep.warnings.items || []).slice(0, 10));
    const sourceWarnings = rep.source_warnings || [];
    block(`源数据提示（前 15 / 共 ${sourceWarnings.length} 条）`, sourceWarnings.slice(0, 15));
    if (rep.key_conflicts && rep.key_conflicts.length) {
        lines.push('', '<b>同一编号对应多个名称/材料（前 5 组，未自动合并）</b>');
        rep.key_conflicts.slice(0, 5).forEach(c => lines.push(`· ${escapeHtml(c.key)} → ${c.values.length} 种${escapeHtml(c.field || '名称')}`));
    }
    block('无法解析的工作表', (rep.error_sheets || []).map(e => `${e.file_name || ''} ${e.sheet_name || ''}：${e.error_type || ''} ${e.detail || ''}`));
    return Swal.fire({
        title: `${sourceLabel} ${dryRun ? '试运行报告' : '导入报告'}`,
        html: `<div style="text-align:left;max-height:60vh;overflow:auto;font-size:.9em;line-height:1.7;font-family:monospace">${lines.join('<br>')}</div>`,
        width: '900px',
        showCloseButton: true,
        confirmButtonText: dryRun ? '知道了' : '刷新列表'
    }).then(() => { if (!dryRun) location.reload(); });
}
