@echo off
:: Windows部署脚本
:: 用于手动部署工资管理系统到Windows服务器

setlocal enabledelayedexpansion

:: 配置参数
set APP_NAME=wage_management_system
set APP_PORT=5000
set DEPLOY_PATH=C:\Apps\wage_management_system
set BACKUP_PATH=C:\Apps\backups\wage_management_system
set SERVICE_NAME=WageManagementSystem

:: Anaconda环境配置
set CONDA_ENV_NAME=wage
set CONDA_PATH=conda

:: 获取时间戳
for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set mydate=%%d%%b%%c
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set mytime=%%a%%b
set timestamp=%mydate%_%mytime%

echo ================================
echo 工资管理系统部署脚本
echo ================================
echo 应用名称: %APP_NAME%
echo 部署路径: %DEPLOY_PATH%
echo 备份路径: %BACKUP_PATH%
echo 时间戳: %timestamp%
echo ================================

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 错误: 需要管理员权限运行此脚本
    echo 请右键选择"以管理员身份运行"
    pause
    exit /b 1
)

:: 创建必要目录
echo 创建部署目录...
if not exist "%DEPLOY_PATH%" mkdir "%DEPLOY_PATH%"
if not exist "%BACKUP_PATH%" mkdir "%BACKUP_PATH%"
if not exist "%BACKUP_PATH%\db_backups" mkdir "%BACKUP_PATH%\db_backups"

:: 检查Conda和Python环境
echo 检查Conda环境...
%CONDA_PATH% --version >nul 2>&1
if %errorLevel% neq 0 (
    echo 错误: 未找到Conda，请确保Anaconda已正确安装并添加到PATH
    pause
    exit /b 1
)

echo 检查Conda环境列表...
%CONDA_PATH% info --envs | findstr %CONDA_ENV_NAME% >nul 2>&1
if %errorLevel% neq 0 (
    echo 错误: 未找到Conda环境 %CONDA_ENV_NAME%，请确保环境已创建
    pause
    exit /b 1
)

echo 激活Conda环境并检查Python...
call %CONDA_PATH% activate %CONDA_ENV_NAME%
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo 错误: 在Conda环境中未找到Python
    pause
    exit /b 1
)

pip --version >nul 2>&1
if %errorLevel% neq 0 (
    echo 错误: 在Conda环境中未找到pip
    pause
    exit /b 1
)

:: 停止现有服务
echo 停止现有服务...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo 停止Windows服务: %SERVICE_NAME%
    sc stop "%SERVICE_NAME%"
    timeout /t 5 /nobreak >nul
) else (
    echo 服务不存在，检查进程...
    tasklist /fi "imagename eq python.exe" | findstr python >nul
    if %errorlevel% equ 0 (
        echo 终止Python进程...
        taskkill /f /im python.exe >nul 2>&1
    )
)

:: 备份现有数据
echo 备份现有数据...
if exist "%DEPLOY_PATH%\app.db" (
    echo 备份数据库文件...
    copy "%DEPLOY_PATH%\app.db" "%BACKUP_PATH%\db_backups\app_%timestamp%.db" >nul
    if %errorlevel% equ 0 (
        echo 数据库备份成功
    ) else (
        echo 警告: 数据库备份失败
    )
)

if exist "%DEPLOY_PATH%\uploads" (
    echo 备份上传文件...
    xcopy "%DEPLOY_PATH%\uploads" "%BACKUP_PATH%\uploads_%timestamp%\" /E /I /Y >nul
)

:: 复制应用文件
echo 部署应用文件...
xcopy /E /I /Y . "%DEPLOY_PATH%\temp_deploy" >nul
if %errorlevel% neq 0 (
    echo 错误: 文件复制失败
    pause
    exit /b 1
)

:: 清理不需要的文件
if exist "%DEPLOY_PATH%\temp_deploy\.git" rmdir /S /Q "%DEPLOY_PATH%\temp_deploy\.git"
if exist "%DEPLOY_PATH%\temp_deploy\__pycache__" rmdir /S /Q "%DEPLOY_PATH%\temp_deploy\__pycache__"

:: 移动文件到最终位置（保护数据库文件）
echo 更新应用文件...
for %%f in ("%DEPLOY_PATH%\temp_deploy\*") do (
    if not "%%~nxf"=="app.db" (
        if exist "%DEPLOY_PATH%\%%~nxf" (
            del /Q "%DEPLOY_PATH%\%%~nxf" >nul 2>&1
            rmdir /S /Q "%DEPLOY_PATH%\%%~nxf" >nul 2>&1
        )
        move "%%f" "%DEPLOY_PATH%\" >nul
    )
)
rmdir "%DEPLOY_PATH%\temp_deploy" >nul 2>&1

:: 激活Conda环境
echo 激活Conda环境...
cd /d "%DEPLOY_PATH%"

call %CONDA_PATH% activate %CONDA_ENV_NAME%
if %errorlevel% neq 0 (
    echo 错误: 激活Conda环境失败
    pause
    exit /b 1
)

:: 安装依赖
echo 安装依赖包...
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 错误: 依赖安装失败
    pause
    exit /b 1
)

:: 数据库迁移
echo 执行数据库迁移...
if exist migrations (
    echo 执行数据库升级...
    python -c "from flask_migrate import upgrade; from app import create_app; app = create_app(); app.app_context().push(); upgrade()"
) else (
    echo 初始化数据库...
    python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
)

if %errorlevel% neq 0 (
    echo 警告: 数据库迁移可能失败，请检查
)

:: 创建环境配置
echo 配置环境变量...
echo FLASK_APP=main.py > .env
echo FLASK_ENV=production >> .env
:: SECRET_KEY 部署时现生成，仓库里不落占位值/真实值；回滚：删掉 .env 里这行，即回落 config.py 的 dev 默认
python -c "import secrets;open('.env','a').write('SECRET_KEY='+secrets.token_urlsafe(48)+chr(10))"
:: DATABASE_URL 一律由运行环境提供；未提供就不写 .env（应用回落 config.py 默认 sqlite 库），并提示显式设置
if defined DATABASE_URL (echo DATABASE_URL=%DATABASE_URL% >> .env) else (echo 警告: 未设置 DATABASE_URL，生产部署请显式设置数据库连接)

:: 创建启动脚本
echo 创建启动脚本...
echo @echo off > start_app.bat
echo cd /d "%DEPLOY_PATH%" >> start_app.bat
echo call %CONDA_PATH% activate %CONDA_ENV_NAME% >> start_app.bat
echo python main.py >> start_app.bat

:: 安装Windows服务（可选）
echo.
choice /C YN /M "是否安装为Windows服务? "
if errorlevel 2 goto :skip_service

echo 安装Windows服务...
pip install pywin32 >nul 2>&1
if exist scripts\windows_service.py (
    python scripts\windows_service.py install
    if %errorlevel% equ 0 (
        echo Windows服务安装成功
        echo 启动服务...
        sc start "%SERVICE_NAME%"
        goto :health_check
    ) else (
        echo 警告: Windows服务安装失败，将使用后台进程方式启动
    )
)

:skip_service
echo 以后台进程方式启动应用...
start /b call start_app.bat

:health_check
:: 等待应用启动
echo 等待应用启动...
timeout /t 15 /nobreak >nul

:: 健康检查
echo 执行健康检查...
set /a retry_count=0
:check_loop
if %retry_count% geq 5 goto :check_failed

curl -f http://localhost:%APP_PORT%/ >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 应用健康检查通过
    goto :deploy_success
) else (
    set /a retry_count+=1
    echo 健康检查失败，重试 %retry_count%/5
    timeout /t 10 /nobreak >nul
    goto :check_loop
)

:check_failed
echo ❌ 应用健康检查失败，请检查应用状态
goto :deploy_end

:deploy_success
echo.
echo ================================
echo ✅ 部署成功完成！
echo ================================
echo 应用访问地址: http://localhost:%APP_PORT%
echo 部署路径: %DEPLOY_PATH%
echo 备份路径: %BACKUP_PATH%
echo 启动时间: %date% %time%
echo ================================

:: 记录部署日志
echo [%date% %time%] 部署成功完成 >> deploy.log

:deploy_end
echo.
pause 