# Windows 自动部署指南

本文档说明如何在Windows环境下自动部署工资管理系统Flask应用。

## 📋 目录

- [环境要求](#环境要求)
- [Jenkins自动部署](#jenkins自动部署)
- [手动部署](#手动部署)
- [Windows服务配置](#windows服务配置)
- [故障排除](#故障排除)

## 🔧 环境要求

### 必需软件
- **Anaconda 或 Miniconda**：Python环境管理
- **OperaEnv_01 Conda环境**：项目专用Python环境
- **Git**：用于代码版本控制
- **curl**：用于健康检查（可选，Windows 10已内置）

### 可选软件
- **Jenkins**：用于自动化CI/CD
- **pywin32**：用于Windows服务支持

### 系统要求
- Windows 10/Windows Server 2016+
- 管理员权限（用于Windows服务安装）
- 至少2GB可用磁盘空间

### Conda环境配置

**重要**：部署使用专用的Conda环境 `OperaEnv_01`

```bash
# 创建新的conda环境（如果尚未创建）
conda create -n OperaEnv_01 python=3.8

# 激活环境
conda activate OperaEnv_01

# 验证环境
conda info --envs
python --version

# 安装基础包（可选）
pip install flask flask-sqlalchemy
```

## 🚀 Jenkins自动部署

### 1. Jenkins配置

#### 安装必需插件
```
- Pipeline Plugin
- Git Plugin  
- Email Extension Plugin (可选)
```

#### 创建Jenkins Pipeline项目
1. 在Jenkins中创建新的Pipeline项目
2. 在"Pipeline"配置中选择"Pipeline script from SCM"
3. 设置Git仓库URL
4. 指定Jenkinsfile路径（项目根目录）

### 2. 配置Windows节点

确保Jenkins有一个标记为`windows`的节点：

```groovy
agent { label 'windows' }
```

### 3. 自定义部署配置

编辑 `deploy.config.yml` 文件来自定义部署参数：

```yaml
deployment:
  app_name: "wage_management_system"
  app_port: 5000
  paths:
    deploy_root: "C:\\Apps\\wage_management_system"
    backup_root: "C:\\Apps\\backups\\wage_management_system"
```

### 4. 触发部署

#### 自动触发
- Git推送到主分支时自动触发
- 默认每5分钟检查代码变化

#### 手动触发
- 在Jenkins界面点击"Build Now"

## 📦 手动部署

### 使用部署脚本

1. **以管理员身份运行PowerShell或命令提示符**
2. **导航到项目目录**
3. **运行部署脚本**：
   ```cmd
   scripts\deploy.bat
   ```

### 部署步骤说明

脚本会自动执行以下步骤：

1. **环境检查**：验证Python、pip等环境
2. **服务停止**：停止现有应用服务
3. **数据备份**：备份数据库和上传文件
4. **应用部署**：复制新版本代码
5. **依赖安装**：更新Python依赖包
6. **数据库迁移**：执行数据库结构更新
7. **服务启动**：启动新版本应用
8. **健康检查**：验证应用正常运行

## 🔧 Windows服务配置

### 安装为Windows服务

1. **安装pywin32依赖**：
   ```cmd
   pip install pywin32
   ```

2. **安装服务**：
   ```cmd
   python scripts\windows_service.py install
   ```

3. **启动服务**：
   ```cmd
   python scripts\windows_service.py start
   ```

### 服务管理命令

```cmd
# 查看服务状态
sc query WageManagementSystem

# 启动服务
sc start WageManagementSystem

# 停止服务  
sc stop WageManagementSystem

# 删除服务
python scripts\windows_service.py remove
```

### 服务日志查看

服务日志记录在Windows事件查看器中：
1. 打开`eventvwr.msc`
2. 导航到：Windows日志 → 应用程序
3. 查找来源为"WageManagementSystem"的事件

## 📁 目录结构

部署后的目录结构：

```
C:\Apps\wage_management_system\
├── app\                    # Flask应用代码
├── venv\                   # Python虚拟环境
├── uploads\                # 上传文件目录
├── app.db                  # SQLite数据库
├── main.py                 # 应用入口
├── requirements.txt        # Python依赖
├── start_app.bat          # 启动脚本
├── .env                   # 环境变量配置
└── deploy.log             # 部署日志

C:\Apps\backups\wage_management_system\
├── db_backups\            # 数据库备份
├── uploads_*\             # 上传文件备份
└── config_*.py            # 配置文件备份
```

## 🐛 故障排除

### 常见问题

#### 1. Conda环境问题
**症状**：找不到conda命令或OperaEnv_01环境
**解决**：
- 确保Anaconda/Miniconda已正确安装
- 将conda添加到系统PATH
- 创建OperaEnv_01环境：`conda create -n OperaEnv_01 python=3.8`
- 验证环境：`conda info --envs`

#### 2. 权限问题
**症状**：无法创建目录或文件
**解决**：
- 确保以管理员权限运行
- 检查目标目录的权限设置

#### 3. 端口占用
**症状**：应用启动失败，端口被占用
**解决**：
```cmd
# 查看端口占用
netstat -ano | findstr :5000

# 终止占用进程
taskkill /pid <PID> /f
```

#### 4. 数据库迁移失败
**症状**：数据库操作错误
**解决**：
- 检查数据库文件权限
- 手动执行迁移命令
- 恢复备份数据库

#### 5. 服务安装失败
**症状**：Windows服务注册失败
**解决**：
```cmd
# 重新安装pywin32
pip uninstall pywin32
pip install pywin32

# 运行postinstall脚本
python Scripts\pywin32_postinstall.py -install
```

### 日志查看

#### 应用日志
- 部署日志：`C:\Apps\wage_management_system\deploy.log`
- Flask应用日志：检查控制台输出或日志文件

#### Jenkins日志
- 在Jenkins构建页面查看"Console Output"
- 下载完整构建日志

#### Windows事件日志
- 使用事件查看器查看系统和应用程序日志
- 重点关注错误和警告事件

## 🔄 回滚策略

### 自动回滚
Jenkinsfile包含自动回滚机制，部署失败时会尝试恢复备份。

### 手动回滚
1. **停止当前服务**
2. **恢复数据库备份**：
   ```cmd
   copy "C:\Apps\backups\wage_management_system\db_backups\app_YYYYMMDD_HHMM.db" "C:\Apps\wage_management_system\app.db"
   ```
3. **恢复应用代码**（从Git）：
   ```cmd
   git checkout <previous-commit>
   ```
4. **重新部署**

## 📧 通知配置

### 邮件通知
在`deploy.config.yml`中配置邮件设置：

```yaml
notifications:
  email:
    enabled: true
    smtp_server: "smtp.company.com"
    recipients:
      - "admin@company.com"
```

### Webhook通知
支持钉钉、企业微信等webhook通知：

```yaml
notifications:
  webhook:
    enabled: true
    url: "https://hooks.example.com/webhook"
```

## 🔒 安全建议

1. **修改默认密钥**：更新`.env`文件中的`SECRET_KEY`
2. **数据库安全**：定期备份，考虑加密敏感数据
3. **网络安全**：配置防火墙规则，限制访问端口
4. **权限管理**：使用最小权限原则配置服务账户

## 📞 技术支持

如果遇到问题：
1. 查看本文档的故障排除部分
2. 检查相关日志文件
3. 联系系统管理员或开发团队

---

**最后更新**：2025年6月11日  
**版本**：1.0.0 