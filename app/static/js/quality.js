// 质量管理模块的JavaScript代码

// 模板管理
function showCreateTemplateModal() {
    $('#templateModal').modal('show');
    $('#templateForm')[0].reset();
    $('#templateModalTitle').text('新建质检模板');
    $('#templateId').val('');
}

function editTemplate(id) {
    $.get(`/api/quality/inspection_template/${id}`, function(response) {
        if (response.success) {
            const template = response.data;
            $('#templateId').val(template.id);
            $('#templateCode').val(template.template_code);
            $('#templateName').val(template.name);
            $('#templateType').val(template.type);
            $('#templateDescription').val(template.description);
            $('#templateIsActive').prop('checked', template.is_active);
            
            // 填充基本信息项目
            $('#baseItemsContainer').empty();
            template.base_items.forEach(item => {
                addBaseItem(item);
            });
            
            // 填充检验项目
            $('#itemsContainer').empty();
            template.items.forEach(item => {
                addInspectionItem(item);
            });
            
            $('#templateModal').modal('show');
            $('#templateModalTitle').text('编辑质检模板');
        } else {
            showToast('error', response.message);
        }
    });
}

function deleteTemplate(id) {
    if (confirm('确定要删除这个模板吗？')) {
        $.ajax({
            url: `/api/quality/inspection_template/${id}`,
            type: 'DELETE',
            success: function(response) {
                if (response.success) {
                    showToast('success', response.message);
                    refreshTemplateList();
                } else {
                    showToast('error', response.message);
                }
            }
        });
    }
}

function saveTemplate() {
    const templateId = $('#templateId').val();
    const isNew = !templateId;
    
    const formData = {
        template_code: $('#templateCode').val(),
        name: $('#templateName').val(),
        type: $('#templateType').val(),
        description: $('#templateDescription').val(),
        is_active: $('#templateIsActive').is(':checked'),
        base_items: [],
        items: []
    };
    
    // 收集基本信息项目
    $('.base-item').each(function() {
        formData.base_items.push({
            name: $(this).find('.base-item-name').val(),
            description: $(this).find('.base-item-description').val(),
            notes: $(this).find('.base-item-notes').val(),
            input_type: $(this).find('.base-item-input-type').val(),
            default_value: $(this).find('.base-item-default-value').val(),
            options: $(this).find('.base-item-options').val(),
            is_required: $(this).find('.base-item-is-required').is(':checked'),
            validation_rules: $(this).find('.base-item-validation-rules').val(),
            order_num: $(this).index()
        });
    });
    
    // 收集检验项目
    $('.inspection-item').each(function() {
        formData.items.push({
            name: $(this).find('.item-name').val(),
            description: $(this).find('.item-description').val(),
            notes: $(this).find('.item-notes').val(),
            inspection_method: $(this).find('.item-inspection-method').val(),
            standard: $(this).find('.item-standard').val(),
            standard_value: $(this).find('.item-standard-value').val(),
            linked_base_item_id: $(this).find('.item-linked-base-item').val(),
            use_linked_value: $(this).find('.item-use-linked-value').is(':checked'),
            value_extraction_rule: $(this).find('.item-value-extraction-rule').val(),
            deviation_type: $(this).find('.item-deviation-type').val(),
            upper_deviation_value: $(this).find('.item-upper-deviation-value').val(),
            lower_deviation_value: $(this).find('.item-lower-deviation-value').val(),
            upper_deviation_percentage: $(this).find('.item-upper-deviation-percentage').val(),
            lower_deviation_percentage: $(this).find('.item-lower-deviation-percentage').val(),
            unit: $(this).find('.item-unit').val(),
            order_num: $(this).index()
        });
    });
    
    $.ajax({
        url: isNew ? '/api/quality/templates' : `/api/quality/inspection_template/${templateId}`,
        type: isNew ? 'POST' : 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(formData),
        success: function(response) {
            if (response.success) {
                $('#templateModal').modal('hide');
                showToast('success', response.message);
                refreshTemplateList();
            } else {
                showToast('error', response.message);
            }
        }
    });
}

// 任务管理
function showCreateTaskModal() {
    $('#taskModal').modal('show');
    $('#taskForm')[0].reset();
    $('#taskModalTitle').text('新建质检任务');
    $('#taskId').val('');
}

function editTask(id) {
    $.get(`/api/quality/inspection_task/${id}`, function(response) {
        if (response.success) {
            const task = response.data;
            $('#taskId').val(task.id);
            $('#taskTemplateId').val(task.template_id);
            $('#taskStatus').val(task.status);
            $('#taskCompletedQuantity').val(task.completed_quantity);
            $('#taskTotalQuantity').val(task.total_quantity);
            $('#taskInspectionDate').val(task.inspection_date);
            $('#taskNotes').val(task.notes);
            
            $('#taskModal').modal('show');
            $('#taskModalTitle').text('编辑质检任务');
        } else {
            showToast('error', response.message);
        }
    });
}

function deleteTask(id) {
    if (confirm('确定要删除这个任务吗？')) {
        $.ajax({
            url: `/api/quality/inspection_task/${id}`,
            type: 'DELETE',
            success: function(response) {
                if (response.success) {
                    showToast('success', response.message);
                    refreshTaskList();
                } else {
                    showToast('error', response.message);
                }
            }
        });
    }
}

function saveTask() {
    const taskId = $('#taskId').val();
    const isNew = !taskId;
    
    const formData = {
        template_id: $('#taskTemplateId').val(),
        status: $('#taskStatus').val(),
        completed_quantity: $('#taskCompletedQuantity').val(),
        total_quantity: $('#taskTotalQuantity').val(),
        inspection_date: $('#taskInspectionDate').val(),
        notes: $('#taskNotes').val()
    };
    
    $.ajax({
        url: isNew ? '/api/quality/tasks' : `/api/quality/inspection_task/${taskId}`,
        type: isNew ? 'POST' : 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(formData),
        success: function(response) {
            if (response.success) {
                $('#taskModal').modal('hide');
                showToast('success', response.message);
                refreshTaskList();
            } else {
                showToast('error', response.message);
            }
        }
    });
}

// 记录管理
function exportRecords() {
    const searchParams = new URLSearchParams({
        type: $('#recordType').val(),
        result: $('#recordResult').val(),
        start_date: $('#startDate').val(),
        end_date: $('#endDate').val()
    });
    
    window.location.href = `/api/quality/records/export?${searchParams.toString()}`;
}

function printRecord(id) {
    window.open(`/api/quality/records/${id}/print`, '_blank');
}

// 辅助函数
function showToast(type, message) {
    const toast = $(`<div class="toast" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header">
            <strong class="me-auto">${type === 'success' ? '成功' : '错误'}</strong>
            <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body">${message}</div>
    </div>`);
    
    $('.toast-container').append(toast);
    const bsToast = new bootstrap.Toast(toast[0]);
    bsToast.show();
    
    toast.on('hidden.bs.toast', function() {
        toast.remove();
    });
}

function refreshTemplateList() {
    // 重新加载模板列表
    $('#templateTable').DataTable().ajax.reload();
}

function refreshTaskList() {
    // 重新加载任务列表
    $('#taskTable').DataTable().ajax.reload();
}

// 初始化
$(document).ready(function() {
    // 初始化日期选择器
    $('.datepicker').datepicker({
        format: 'yyyy-mm-dd',
        autoclose: true,
        language: 'zh-CN'
    });
    
    // 初始化DataTables
    if ($('#templateTable').length) {
        $('#templateTable').DataTable({
            ajax: '/api/quality/templates',
            columns: [
                { data: 'template_code' },
                { data: 'name' },
                { data: 'type' },
                { data: 'created_at' },
                {
                    data: null,
                    render: function(data, type, row) {
                        return `
                            <button class="btn btn-sm btn-primary" onclick="editTemplate(${row.id})">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteTemplate(${row.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        `;
                    }
                }
            ],
            language: {
                url: '/static/plugins/datatables/zh-CN.json'
            }
        });
    }
    
    if ($('#taskTable').length) {
        $('#taskTable').DataTable({
            ajax: '/api/quality/tasks',
            columns: [
                { data: 'task_code' },
                { data: 'type' },
                { data: 'inspection_target' },
                { data: 'inspector_name' },
                { data: 'status' },
                { data: 'inspection_date' },
                {
                    data: null,
                    render: function(data, type, row) {
                        return `
                            <button class="btn btn-sm btn-primary" onclick="editTask(${row.id})">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteTask(${row.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        `;
                    }
                }
            ],
            language: {
                url: '/static/plugins/datatables/zh-CN.json'
            }
        });
    }
    
    if ($('#recordTable').length) {
        $('#recordTable').DataTable({
            ajax: '/api/quality/records',
            columns: [
                { data: 'record_code' },
                { data: 'type' },
                { data: 'inspection_target' },
                { data: 'inspector_name' },
                { data: 'inspection_date' },
                { data: 'result' },
                {
                    data: null,
                    render: function(data, type, row) {
                        return `
                            <button class="btn btn-sm btn-info" onclick="printRecord(${row.id})">
                                <i class="fas fa-print"></i>
                            </button>
                        `;
                    }
                }
            ],
            language: {
                url: '/static/plugins/datatables/zh-CN.json'
            }
        });
    }
}); 