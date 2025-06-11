"""
Windows服务配置脚本
用于将Flask应用注册为Windows服务

使用方法:
1. 安装依赖: pip install pywin32
2. 安装服务: python windows_service.py install
3. 启动服务: python windows_service.py start
4. 停止服务: python windows_service.py stop
5. 删除服务: python windows_service.py remove
"""

import sys
import os
import socket
import win32serviceutil
import win32service
import win32event
import servicemanager

# 添加项目路径到Python路径
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_path)

class WageManagementService(win32serviceutil.ServiceFramework):
    """工资管理系统Windows服务"""
    
    _svc_name_ = "WageManagementSystem"
    _svc_display_name_ = "工资管理系统服务"
    _svc_description_ = "工资管理系统Flask应用服务"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_alive = True
        
    def SvcStop(self):
        """停止服务"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                            servicemanager.PYS_SERVICE_STOPPED,
                            (self._svc_name_, ''))
        
    def SvcDoRun(self):
        """运行服务"""
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                            servicemanager.PYS_SERVICE_STARTED,
                            (self._svc_name_, ''))
        
        try:
            # 设置工作目录
            os.chdir(project_path)
            
            # 导入Flask应用
            from app import create_app
            
            app = create_app()
            
            # 记录服务启动
            servicemanager.LogInfoMsg(f"工资管理系统服务已启动，监听端口: 5000")
            
            # 启动Flask应用
            app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
            
        except Exception as e:
            servicemanager.LogErrorMsg(f"服务启动失败: {str(e)}")
            self.SvcStop()

def setup_service():
    """设置服务配置"""
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WageManagementService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(WageManagementService)

if __name__ == '__main__':
    setup_service() 