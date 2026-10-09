# MyERP gunicorn 配置
# 容器内由 CMD ["gunicorn", "-c", "docker/gunicorn.conf.py", "main:app"] 使用。
# 全部阈值走环境变量：同一镜像在不同编排环境（docker run / compose / k8s）调整时无需重建。
import os


def _int_env(name, default):
    """取整型环境变量；非法值立刻抛错（fail-fast，不静默用默认值）。"""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return default
    return int(raw)


# 监听地址：PORT 与 Dockerfile 的 EXPOSE 5000 / HEALTHCHECK 的探测端口保持一致
bind = '0.0.0.0:%d' % _int_env('PORT', 5000)

# 工作进程数：2 是容器内小内存场景的保守起点（按 CPU/内存再调 WEB_CONCURRENCY）
workers = _int_env('WEB_CONCURRENCY', 2)

# 请求超时：Excel 导入/大报表可能较慢，默认放宽到 120s
timeout = _int_env('GUNICORN_TIMEOUT', 120)

# 优雅退出：容器 stop 时给在途请求收尾时间，避免 502
graceful_timeout = _int_env('GUNICORN_GRACEFUL_TIMEOUT', 30)
keepalive = _int_env('GUNICORN_KEEPALIVE', 5)

# 日志一律走 stdout/stderr（'-'），交给 Docker / 编排层采集，不落容器内文件
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOGLEVEL', 'info')

# 前置反向代理（Nginx / ALB）下要让 X-Forwarded-* 生效才改；不给默认 '*'
# （gunicorn 自身默认只信任环回代理，直接暴露端口时信任任意来源等于可伪造客户端 IP）。
if os.environ.get('FORWARDED_ALLOW_IPS'):
    forwarded_allow_ips = os.environ['FORWARDED_ALLOW_IPS']
