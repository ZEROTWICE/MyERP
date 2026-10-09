// 统一 fetch 封装（B16-02）：非 GET 自动注入 CSRF 令牌。
// 模板里的写操作一律用 apiFetch(...)，不要在调用点各自贴 X-CSRFToken。
// 令牌来源与 base.html 中 jQuery 的 $.ajaxSetup 一致：meta[name="csrf-token"]。
window.apiFetch = function (url, options) {
    options = options || {};
    var method = String(options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS' && method !== 'TRACE') {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) {
            var headers = new Headers(options.headers || {});
            headers.set('X-CSRFToken', meta.getAttribute('content'));
            options.headers = headers;
        }
    }
    return fetch(url, options);
};
