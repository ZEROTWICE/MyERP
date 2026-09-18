// ==================== 移动端优化脚本 ====================
//
// 侧边栏菜单**不再由本文件重建**：base.html 里已经用 can()/can_any() 渲染好唯一一份
// 按权限过滤的导航（#mainNavMenu），这里只做「结构搬运 + CSS class 映射」。
// 因此移动端与桌面端看到的菜单项天然一致，且本文件不含任何硬编码 URL/角色判断。
// 少量非权限信息（首页/登录/通知中心/退出/用户名）由 base.html 以 JSON
// （#mobileNavMeta，全部由 url_for 生成）注入。

document.addEventListener('DOMContentLoaded', function() {
    // 检测移动设备
    const isMobile = window.innerWidth <= 768;
    
    // 如果是移动设备，执行优化
    if (isMobile) {
        initMobileOptimizations();
    }
    
    // 窗口大小改变时重新检测
    window.addEventListener('resize', function() {
        const newIsMobile = window.innerWidth <= 768;
        if (newIsMobile !== isMobile) {
            location.reload(); // 简单重载页面以重新应用样式
        }
    });
});

function initMobileOptimizations() {
    // 1. 优化表格显示
    optimizeTables();
    
    // 2. 添加移动端导航
    addMobileNavigation();
    
    // 3. 优化表单输入
    optimizeForms();
    
    // 4. 添加触摸友好的按钮
    optimizeButtons();
    
    // 5. 优化模态框
    optimizeModals();
    
    // 6. 添加回到顶部按钮
    addBackToTop();
    
    // 7. 优化搜索和筛选
    optimizeFilters();
}

// 表格优化
function optimizeTables() {
    const tables = document.querySelectorAll('.table-responsive table');
    
    tables.forEach(table => {
        // 添加水平滚动提示
        const wrapper = table.closest('.table-responsive');
        if (wrapper && !wrapper.querySelector('.table-scroll-hint')) {
            const hint = document.createElement('div');
            hint.className = 'table-scroll-hint text-muted text-center py-2';
            hint.innerHTML = '<small><i class="fas fa-hand-point-right"></i> 左右滑动查看更多内容</small>';
            wrapper.appendChild(hint);
        }
        
        // 为表格添加触摸滚动优化
        if (wrapper) {
            wrapper.style.webkitOverflowScrolling = 'touch';
        }
    });
}

// 移动端侧边栏导航
function addMobileNavigation() {
    const body = document.body;
    
    // 检查是否已存在移动导航
    if (document.querySelector('.mobile-sidebar') || document.querySelector('.mobile-menu-toggle')) {
        return;
    }
    
    // 创建汉堡菜单按钮
    const menuToggle = document.createElement('button');
    menuToggle.className = 'mobile-menu-toggle';
    menuToggle.innerHTML = '<i class="fas fa-bars"></i>';
    menuToggle.setAttribute('aria-label', '打开菜单');
    
    // 创建遮罩层
    const overlay = document.createElement('div');
    overlay.className = 'mobile-sidebar-overlay';
    
    // 创建侧边栏
    const sidebar = document.createElement('div');
    sidebar.className = 'mobile-sidebar';
    
    // 导航内容复用服务端按权限渲染的菜单
    const navContent = generateSidebarNavigation();
    
    sidebar.innerHTML = `
        <div class="mobile-sidebar-header">
            <h3 class="mobile-sidebar-title">综合管理系统</h3>
            <button class="mobile-sidebar-close" aria-label="关闭菜单">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <nav class="mobile-sidebar-nav">
            ${navContent}
        </nav>
        ${generateUserSection()}
    `;
    
    // 添加到页面
    body.appendChild(menuToggle);
    body.appendChild(overlay);
    body.appendChild(sidebar);
    
    // 绑定事件
    setupSidebarEvents(menuToggle, sidebar, overlay);
    
    // 为主内容添加底部padding，避免被菜单按钮遮挡
    const mainContent = document.querySelector('.container, .container-fluid');
    if (mainContent) {
        mainContent.style.paddingBottom = '80px';
        // 移除可能存在的顶部padding
        mainContent.style.paddingTop = '';
    }
}

// 读取 base.html 注入的导航元数据（url 全部由服务端 url_for 生成）
function getMobileNavMeta() {
    const el = document.getElementById('mobileNavMeta');
    if (!el) {
        return { authenticated: false };
    }
    try {
        return JSON.parse(el.textContent) || { authenticated: false };
    } catch (e) {
        return { authenticated: false };
    }
}

// 菜单图标：纯展示映射，键为服务端渲染出来的菜单文字；找不到就用默认图标。
var MOBILE_NAV_ICONS = {
    '员工管理': 'fa-users',
    '工序管理': 'fa-cogs',
    '工序分配': 'fa-sitemap',
    '生产记录': 'fa-clipboard-list',
    '任务管理': 'fa-tasks',
    '生产订单': 'fa-file-alt',
    '设备台账': 'fa-tools',
    '工作中心': 'fa-industry',
    '煅烧炉次': 'fa-fire',
    '工件溯源': 'fa-qrcode',
    '组装扣料': 'fa-puzzle-piece',
    '生产中心（产品）': 'fa-cubes',
    '库存查询': 'fa-warehouse',
    '半成品库': 'fa-boxes',
    '未通过库': 'fa-ban',
    '报废库': 'fa-trash-alt',
    '成品库': 'fa-box',
    '原材料入库': 'fa-dolly',
    '原材料品类管理': 'fa-tags',
    '易耗品管理': 'fa-toolbox',
    '易耗品入库': 'fa-dolly',
    '易耗品品类管理': 'fa-tags',
    '成品入库': 'fa-box-open',
    '物料领用': 'fa-clipboard-check',
    '物料归还': 'fa-undo',
    '库存盘点': 'fa-clipboard-list',
    '产品管理': 'fa-box',
    '客户管理': 'fa-user-tie',
    '销售订单': 'fa-file-invoice',
    '发货出库': 'fa-shipping-fast',
    '供应商': 'fa-truck',
    '采购单': 'fa-file-invoice-dollar',
    '请购单': 'fa-file-signature',
    '质量看板': 'fa-medal',
    '不合格处置': 'fa-exclamation-triangle',
    '编码管理': 'fa-code',
    '审计日志': 'fa-history',
    '通知规则': 'fa-bell-slash',
    '系统配置': 'fa-cog',
    '我的任务': 'fa-tasks',
    '奖惩管理': 'fa-award',
    '工资管理': 'fa-calculator',
    '首页': 'fa-home',
    '通知中心': 'fa-bell',
    '登录': 'fa-sign-in-alt',
    '注册': 'fa-user-plus'
};

function mobileNavIcon(text, fallback) {
    return MOBILE_NAV_ICONS[text] || fallback;
}

// 生成侧边栏导航内容：直接搬运 #mainNavMenu（服务端 can()/can_any() 过滤后的菜单）
function generateSidebarNavigation() {
    const meta = getMobileNavMeta();
    const currentPath = window.location.pathname;
    const parts = [];

    const directItem = function(href, text) {
        const active = href === currentPath ? ' active' : '';
        return `<a href="${href}" class="mobile-sidebar-item${active}">
            <i class="fas ${mobileNavIcon(text, 'fa-circle')}"></i>
            <span>${text}</span>
        </a>`;
    };

    const subItem = function(href, text) {
        const active = href === currentPath ? ' active' : '';
        return `<a href="${href}" class="mobile-sidebar-subitem${active}">
            <i class="fas ${mobileNavIcon(text, 'fa-angle-right')}"></i>
            <span>${text}</span>
        </a>`;
    };

    if (meta.home) {
        parts.push(directItem(meta.home, '首页'));
    }

    if (!meta.authenticated) {
        // 未登录：与桌面端一致，只给登录/注册入口
        if (meta.login) parts.push(directItem(meta.login, '登录'));
        if (meta.register) parts.push(directItem(meta.register, '注册'));
        return parts.join('');
    }

    const menu = document.getElementById('mainNavMenu');
    if (menu) {
        let groupIndex = 0;
        Array.prototype.forEach.call(menu.children, function(li) {
            if (!li.classList || !li.classList.contains('nav-item')) {
                return;
            }
            const toggle = li.querySelector('a.dropdown-toggle');
            const direct = li.querySelector('a.nav-link');
            if (toggle) {
                const label = toggle.textContent.trim();
                const subLinks = [];
                Array.prototype.forEach.call(li.querySelectorAll('ul.dropdown-menu a.dropdown-item'), function(a) {
                    const href = a.getAttribute('href');
                    if (href) {
                        subLinks.push(subItem(href, a.textContent.trim()));
                    }
                });
                if (!subLinks.length) {
                    return; // 空分组（例如该项当前角色看不到任何子项）不渲染
                }
                const key = 'group-' + (groupIndex++);
                parts.push(`<div class="mobile-sidebar-expandable" data-toggle="${key}">
                    <div class="mobile-sidebar-item">
                        <i class="fas ${mobileNavIcon(label, 'fa-folder')}"></i>
                        <span>${label}</span>
                        <i class="fas fa-chevron-right toggle-icon"></i>
                    </div>
                    <div class="mobile-sidebar-submenu" data-submenu="${key}">
                        ${subLinks.join('')}
                    </div>
                </div>`);
            } else if (direct && direct.getAttribute('href')) {
                parts.push(directItem(direct.getAttribute('href'), direct.textContent.trim()));
            }
        });
    }

    if (meta.notifications) {
        parts.push(directItem(meta.notifications, '通知中心'));
    }

    return parts.join('');
}

// 生成用户信息区域
function generateUserSection() {
    const meta = getMobileNavMeta();
    
    if (!meta.authenticated) {
        return '';
    }
    
    return `
        <div class="mobile-sidebar-user">
            <div class="mobile-sidebar-user-info">
                <div class="mobile-sidebar-user-name">欢迎，${meta.username || ''}</div>
            </div>
            <a href="${meta.logout}" class="mobile-sidebar-logout">
                <i class="fas fa-sign-out-alt"></i>
                <span>退出登录</span>
            </a>
        </div>
    `;
}

// 设置侧边栏事件
function setupSidebarEvents(toggle, sidebar, overlay) {
    // 打开侧边栏
    function openSidebar() {
        sidebar.classList.add('open');
        overlay.classList.add('show');
        toggle.classList.add('active');
        toggle.innerHTML = '<i class="fas fa-times"></i>';
        toggle.setAttribute('aria-label', '关闭菜单');
        document.body.style.overflow = 'hidden';
    }
    
    // 关闭侧边栏
    function closeSidebar() {
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
        toggle.classList.remove('active');
        toggle.innerHTML = '<i class="fas fa-bars"></i>';
        toggle.setAttribute('aria-label', '打开菜单');
        document.body.style.overflow = '';
    }
    
    // 菜单按钮点击事件
    toggle.addEventListener('click', function() {
        if (sidebar.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });
    
    // 遮罩层点击关闭
    overlay.addEventListener('click', closeSidebar);
    
    // 关闭按钮点击事件
    const closeBtn = sidebar.querySelector('.mobile-sidebar-close');
    closeBtn.addEventListener('click', closeSidebar);
    
    // 直接导航项点击后关闭侧边栏（不包括可展开项的容器）
    const directNavItems = sidebar.querySelectorAll('a.mobile-sidebar-item');
    directNavItems.forEach(item => {
        item.addEventListener('click', function(e) {
            // 允许链接正常跳转
            closeSidebar();
        });
    });
    
    // 子菜单项点击后关闭侧边栏
    const subNavItems = sidebar.querySelectorAll('.mobile-sidebar-subitem');
    subNavItems.forEach((item) => {
        item.addEventListener('click', function(e) {
            // 允许链接正常跳转
            setTimeout(() => {
                closeSidebar();
            }, 100); // 延迟关闭，确保链接跳转
        });
    });
    
    // 可展开菜单的点击事件（只绑定到 .mobile-sidebar-item div，不是链接）
    const expandableItems = sidebar.querySelectorAll('.mobile-sidebar-expandable');
    expandableItems.forEach(item => {
        const toggleDiv = item.querySelector('.mobile-sidebar-item');
        if (toggleDiv) {
            toggleDiv.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                const toggleName = item.getAttribute('data-toggle');
                const submenu = sidebar.querySelector(`[data-submenu="${toggleName}"]`);
                const isExpanded = item.classList.contains('expanded');
                
                // 关闭其他展开的菜单
                expandableItems.forEach(otherItem => {
                    if (otherItem !== item) {
                        otherItem.classList.remove('expanded');
                        const otherToggleName = otherItem.getAttribute('data-toggle');
                        const otherSubmenu = sidebar.querySelector(`[data-submenu="${otherToggleName}"]`);
                        if (otherSubmenu) {
                            otherSubmenu.classList.remove('show');
                        }
                    }
                });
                
                // 切换当前菜单
                if (isExpanded) {
                    item.classList.remove('expanded');
                    if (submenu) submenu.classList.remove('show');
                } else {
                    item.classList.add('expanded');
                    if (submenu) submenu.classList.add('show');
                }
            });
        }
    });
    
    // ESC键关闭侧边栏
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidebar.classList.contains('open')) {
            closeSidebar();
        }
    });
}

// 表单优化
function optimizeForms() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        // 防止iOS缩放
        const inputs = form.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input[type="number"], input[type="password"], textarea');
        inputs.forEach(input => {
            if (!input.style.fontSize) {
                input.style.fontSize = '16px';
            }
        });
        
        // 优化选择框
        const selects = form.querySelectorAll('select');
        selects.forEach(select => {
            if (!select.style.fontSize) {
                select.style.fontSize = '16px';
            }
        });
    });
}

// 按钮优化
function optimizeButtons() {
    const buttons = document.querySelectorAll('.btn');
    
    buttons.forEach(button => {
        // 确保按钮有足够的触摸目标大小
        const rect = button.getBoundingClientRect();
        if (rect.height < 44) {
            button.style.minHeight = '44px';
            button.style.display = 'flex';
            button.style.alignItems = 'center';
            button.style.justifyContent = 'center';
        }
        
        // 添加触摸反馈
        button.addEventListener('touchstart', function(e) {
            this.style.transform = 'scale(0.98)';
        });
        
        button.addEventListener('touchend', function() {
            this.style.transform = 'scale(1)';
        });
    });
}

// 模态框优化
function optimizeModals() {
    const modals = document.querySelectorAll('.modal');
    
    modals.forEach(modal => {
        // 确保模态框在移动端正确显示
        modal.addEventListener('shown.bs.modal', function() {
            const modalDialog = this.querySelector('.modal-dialog');
            if (modalDialog) {
                modalDialog.style.margin = '1rem';
                modalDialog.style.maxWidth = 'calc(100% - 2rem)';
            }
            
            // 防止背景滚动
            document.body.style.overflow = 'hidden';
        });
        
        modal.addEventListener('hidden.bs.modal', function() {
            // 恢复背景滚动
            document.body.style.overflow = '';
        });
    });
}

// 回到顶部按钮
function addBackToTop() {
    // 检查是否已存在
    if (document.querySelector('.back-to-top')) {
        return;
    }
    
    const backToTopBtn = document.createElement('button');
    backToTopBtn.className = 'mobile-action-btn back-to-top';
    backToTopBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    backToTopBtn.style.display = 'none';
    backToTopBtn.style.bottom = '1rem'; // 移动端底部位置
    backToTopBtn.style.alignItems = 'center';
    backToTopBtn.style.justifyContent = 'center';
    
    document.body.appendChild(backToTopBtn);
    
    // 监听滚动事件
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            backToTopBtn.style.display = 'flex';
        } else {
            backToTopBtn.style.display = 'none';
        }
    });
    
    // 点击回到顶部
    backToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

// 筛选器优化
function optimizeFilters() {
    const filterForms = document.querySelectorAll('.mobile-filters form');
    
    filterForms.forEach(form => {
        // 添加展开/收起功能
        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'btn btn-outline-secondary btn-sm mb-3 w-100';
        toggleBtn.innerHTML = '<i class="fas fa-filter"></i> 筛选条件 <i class="fas fa-chevron-down ms-2"></i>';
        
        const formContent = form.cloneNode(true);
        form.innerHTML = '';
        form.appendChild(toggleBtn);
        
        const collapsibleDiv = document.createElement('div');
        collapsibleDiv.className = 'filter-content';
        collapsibleDiv.style.display = 'none';
        collapsibleDiv.appendChild(formContent);
        form.appendChild(collapsibleDiv);
        
        // 切换显示/隐藏
        toggleBtn.addEventListener('click', function() {
            const isVisible = collapsibleDiv.style.display !== 'none';
            collapsibleDiv.style.display = isVisible ? 'none' : 'block';
            
            const icon = this.querySelector('.fa-chevron-down, .fa-chevron-up');
            icon.className = isVisible ? 'fas fa-chevron-down ms-2' : 'fas fa-chevron-up ms-2';
        });
    });
}

// 工具函数：显示移动端加载状态
function showMobileLoading(message = '加载中...') {
    const existingLoader = document.querySelector('.mobile-loading-overlay');
    if (existingLoader) {
        return;
    }
    
    const loader = document.createElement('div');
    loader.className = 'mobile-loading-overlay';
    loader.innerHTML = `
        <div class="mobile-loading">
            <div class="mobile-loading-spinner"></div>
            <div class="mobile-loading-text">${message}</div>
        </div>
    `;
    
    document.body.appendChild(loader);
    return loader;
}

// 工具函数：隐藏移动端加载状态
function hideMobileLoading() {
    const loader = document.querySelector('.mobile-loading-overlay');
    if (loader) {
        loader.remove();
    }
}

// 工具函数：显示移动端提示
function showMobileToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} mobile-toast`;
    toast.style.cssText = `
        position: fixed;
        top: 1rem;
        left: 1rem;
        right: 1rem;
        z-index: 9999;
        margin: 0;
        opacity: 0;
        transform: translateY(-100%);
        transition: all 0.3s ease;
    `;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    // 显示动画
    setTimeout(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    }, 100);
    
    // 自动隐藏
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-100%)';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, duration);
}

// 工具函数：格式化移动端时间显示
function formatMobileTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (minutes < 1) {
        return '刚刚';
    } else if (minutes < 60) {
        return `${minutes}分钟前`;
    } else if (hours < 24) {
        return `${hours}小时前`;
    } else if (days < 7) {
        return `${days}天前`;
    } else {
        return date.toLocaleDateString('zh-CN');
    }
}

// 导出函数供其他脚本使用
window.MobileOptimization = {
    showLoading: showMobileLoading,
    hideLoading: hideMobileLoading,
    showToast: showMobileToast,
    formatTime: formatMobileTime,
    isMobile: () => window.innerWidth <= 768
};
