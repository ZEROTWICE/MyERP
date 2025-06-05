// ==================== 移动端优化脚本 ====================

document.addEventListener('DOMContentLoaded', function() {
    // 检测移动设备
    const isMobile = window.innerWidth <= 768;
    const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    
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
    console.log('🔧 初始化移动端优化...');
    
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
    
    console.log('✅ 移动端优化完成');
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

// 移动端导航
function addMobileNavigation() {
    const body = document.body;
    
    // 检查是否已存在移动导航
    if (document.querySelector('.mobile-nav-menu')) {
        return;
    }
    
    // 创建移动端底部导航
    const mobileNav = document.createElement('div');
    mobileNav.className = 'mobile-nav-menu';
    
    const navItems = [
        { href: '/', icon: 'fas fa-home', text: '首页' },
        { href: '/customers', icon: 'fas fa-users', text: '客户' },
        { href: '/products', icon: 'fas fa-box', text: '产品' },
        { href: '/production', icon: 'fas fa-industry', text: '生产' },
        { href: '/notifications', icon: 'fas fa-bell', text: '通知' }
    ];
    
    const navItemsHtml = navItems.map(item => `
        <a href="${item.href}" class="mobile-nav-item ${window.location.pathname === item.href ? 'active' : ''}">
            <i class="${item.icon}"></i>
            <span>${item.text}</span>
        </a>
    `).join('');
    
    mobileNav.innerHTML = `
        <div class="mobile-nav-items">
            ${navItemsHtml}
        </div>
    `;
    
    body.appendChild(mobileNav);
    
    // 为主内容添加底部padding，避免被导航栏遮挡
    const mainContent = document.querySelector('.container, .container-fluid');
    if (mainContent) {
        mainContent.style.paddingBottom = '80px';
    }
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
        
        button.addEventListener('touchend', function(e) {
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
    backToTopBtn.style.bottom = '5rem'; // 避免与底部导航重叠
    
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