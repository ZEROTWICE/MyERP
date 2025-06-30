/**
 * 通用分页处理JavaScript
 * 自动处理每页显示数量变化时的表单提交
 */

$(document).ready(function() {
    // 处理每页显示数量变化
    $('#per_page').on('change', function() {
        // 查找最近的表单并提交
        const form = $(this).closest('form');
        if (form.length > 0) {
            form.submit();
        } else {
            // 如果不在表单内，尝试查找页面中的搜索表单
            const searchForm = $('#searchForm');
            if (searchForm.length > 0) {
                searchForm.submit();
            } else {
                // 最后的降级方案：构造URL并跳转
                const currentUrl = new URL(window.location.href);
                currentUrl.searchParams.set('per_page', $(this).val());
                currentUrl.searchParams.set('page', '1'); // 重置到第一页
                window.location.href = currentUrl.toString();
            }
        }
    });
    
    // 处理其他可能的筛选条件变化（如状态筛选、复选框等）
    $('.auto-submit').on('change', function() {
        const form = $(this).closest('form');
        if (form.length > 0) {
            form.submit();
        }
    });
});