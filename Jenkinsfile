pipeline {
    agent { label 'windows' }  // 指定Windows节点
    
    environment {
        // 应用配置
        APP_NAME = 'wage_management_system'
        APP_PORT = '5000'
        
        // 部署路径 - 根据实际情况修改
        DEPLOY_PATH = 'C:\\Deployed\\wage_management_system'
        BACKUP_PATH = 'C:\\Deployed\\backups\\wage_management_system'
        
        // Anaconda环境配置
        CONDA_ENV_NAME = 'wage'
        CONDA_PATH = 'conda'  // 或者指定完整路径如 'C:\\Users\\%USERNAME%\\anaconda3\\Scripts\\conda.exe'
        
        // Python环境（使用conda环境中的python）
        PYTHON_PATH = 'python'  // 在激活conda环境后使用
        
        // 数据库配置
        DB_BACKUP_DIR = "${BACKUP_PATH}\\db_backups"
        
        // 服务名称（如果使用Windows服务）
        SERVICE_NAME = 'WageManagementSystem'
    }
    
    stages {
        stage('准备工作') {
            steps {
                echo '开始部署流水线...'
                
                // 创建必要的目录
                bat """
                if not exist "${DEPLOY_PATH}" mkdir "${DEPLOY_PATH}"
                if not exist "${BACKUP_PATH}" mkdir "${BACKUP_PATH}"
                if not exist "${DB_BACKUP_DIR}" mkdir "${DB_BACKUP_DIR}"
                """
                
                // 检查Conda和Python环境
                bat """
                echo 检查Conda环境...
                ${CONDA_PATH} --version
                ${CONDA_PATH} info --envs
                
                echo 激活Conda环境并检查Python...
                call ${CONDA_PATH} activate ${CONDA_ENV_NAME}
                python --version
                pip --version
                """
            }
        }
        
        stage('代码检出') {
            steps {
                echo '检出最新代码...'
                checkout scm
                
                // 显示当前提交信息
                bat 'git log -1 --oneline'
            }
        }
        
        stage('代码质量检查') {
            steps {
                echo '进行代码质量检查...'
                
                script {
                                         try {
                         // 检查Python语法
                         bat """
                         call ${CONDA_PATH} activate ${CONDA_ENV_NAME}
                         python -m py_compile main.py
                         python -m py_compile config.py
                         """
                         
                         // 可以添加其他检查，如flake8等
                         // bat "call ${CONDA_PATH} activate ${CONDA_ENV_NAME} && python -m flake8 app/ --max-line-length=120"
                        
                    } catch (Exception e) {
                        echo "代码质量检查发现问题: ${e.getMessage()}"
                        currentBuild.result = 'UNSTABLE'
                    }
                }
            }
        }
        
        stage('停止现有服务') {
            steps {
                echo '停止现有应用服务...'
                
                script {
                    try {
                        // 方法1: 如果使用Windows服务
                        bat """
                        sc query "${SERVICE_NAME}" >nul 2>&1
                        if %errorlevel% equ 0 (
                            echo 停止Windows服务: ${SERVICE_NAME}
                            sc stop "${SERVICE_NAME}"
                            timeout /t 5 /nobreak >nul
                        ) else (
                            echo 服务 ${SERVICE_NAME} 不存在或未运行
                        )
                        """
                        
                        // 方法2: 如果使用进程方式运行
                        bat """
                        echo 查找并终止Python进程...
                        for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo csv ^| findstr main.py') do (
                            echo 终止进程: %%i
                            taskkill /pid %%i /f 2>nul
                        )
                        """
                        
                        // 等待进程完全停止
                        sleep 10
                        
                    } catch (Exception e) {
                        echo "停止服务时出现问题: ${e.getMessage()}"
                        // 继续执行，不阻止部署
                    }
                }
            }
        }
        
        stage('备份数据') {
            steps {
                echo '备份现有数据...'
                
                script {
                    def timestamp = new Date().format('yyyyMMdd_HHmmss')
                    
                    try {
                        // 备份数据库文件
                        bat """
                        if exist "${DEPLOY_PATH}\\app.db" (
                            echo 备份数据库文件...
                            copy "${DEPLOY_PATH}\\app.db" "${DB_BACKUP_DIR}\\app_${timestamp}.db"
                        ) else (
                            echo 数据库文件不存在，跳过备份
                        )
                        """
                        
                        // 备份配置文件
                        bat """
                        if exist "${DEPLOY_PATH}\\config.py" (
                            echo 备份配置文件...
                            copy "${DEPLOY_PATH}\\config.py" "${BACKUP_PATH}\\config_${timestamp}.py"
                        )
                        """
                        
                        // 备份上传文件
                        bat """
                        if exist "${DEPLOY_PATH}\\uploads" (
                            echo 备份上传文件...
                            xcopy "${DEPLOY_PATH}\\uploads" "${BACKUP_PATH}\\uploads_${timestamp}\\" /E /I /Y
                        )
                        """
                        
                    } catch (Exception e) {
                        echo "备份过程中出现问题: ${e.getMessage()}"
                        currentBuild.result = 'UNSTABLE'
                    }
                }
            }
        }
        
        stage('部署应用') {
            steps {
                echo '部署新版本应用...'
                
                // 复制应用文件
                bat """
                echo 复制应用文件到部署目录...
                xcopy /E /I /Y . "${DEPLOY_PATH}\\temp_deploy"
                
                echo 清理临时文件...
                if exist "${DEPLOY_PATH}\\temp_deploy\\.git" rmdir /S /Q "${DEPLOY_PATH}\\temp_deploy\\.git"
                if exist "${DEPLOY_PATH}\\temp_deploy\\__pycache__" rmdir /S /Q "${DEPLOY_PATH}\\temp_deploy\\__pycache__"
                """
                
                // 移动文件到最终位置
                bat """
                echo 更新应用文件...
                for %%f in ("${DEPLOY_PATH}\\temp_deploy\\*") do (
                    if not "%%~nxf"=="app.db" (
                        move "%%f" "${DEPLOY_PATH}\\"
                    )
                )
                rmdir "${DEPLOY_PATH}\\temp_deploy"
                """
            }
        }
        
        stage('安装依赖') {
            steps {
                echo '安装Python依赖包...'
                
                bat """
                cd /d "${DEPLOY_PATH}"
                
                echo 激活Conda环境并安装依赖...
                call ${CONDA_PATH} activate ${CONDA_ENV_NAME}
                
                echo 更新pip...
                python -m pip install --upgrade pip
                
                echo 安装项目依赖...
                pip install -r requirements.txt
                
                echo 验证关键包安装...
                pip show flask
                pip show flask-sqlalchemy
                
                echo 显示当前环境信息...
                conda info
                pip list
                """
            }
        }
        
        stage('数据库迁移') {
            steps {
                echo '执行数据库迁移...'
                
                bat """
                cd /d "${DEPLOY_PATH}"
                call ${CONDA_PATH} activate ${CONDA_ENV_NAME}
                
                echo 检查数据库迁移...
                if exist migrations (
                    echo 执行数据库升级...
                    python -c "from flask_migrate import upgrade; from app import create_app; app = create_app(); app.app_context().push(); upgrade()"
                ) else (
                    echo 初始化数据库...
                    python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
                )
                """
            }
        }
        
        stage('配置环境') {
            steps {
                echo '配置运行环境...'
                
                // 设置环境变量文件
                bat """
                cd /d "${DEPLOY_PATH}"
                
                echo 创建环境配置文件...
                echo FLASK_APP=main.py > .env
                echo FLASK_ENV=production >> .env
                echo SECRET_KEY=your-secret-key-here >> .env
                echo DATABASE_URL=sqlite:///app.db >> .env
                """
                
                // 创建启动脚本
                bat """
                cd /d "${DEPLOY_PATH}"
                
                echo @echo off > start_app.bat
                echo cd /d "${DEPLOY_PATH}" >> start_app.bat
                echo call ${CONDA_PATH} activate ${CONDA_ENV_NAME} >> start_app.bat
                echo python main.py >> start_app.bat
                
                echo @echo off > stop_app.bat
                echo taskkill /f /im python.exe 2^>nul >> stop_app.bat
                echo echo 应用已停止 >> stop_app.bat
                
                echo @echo off > conda_env_info.bat
                echo call ${CONDA_PATH} activate ${CONDA_ENV_NAME} >> conda_env_info.bat
                echo conda info >> conda_env_info.bat
                echo python --version >> conda_env_info.bat
                echo pip list >> conda_env_info.bat
                """
            }
        }
        
        stage('启动服务') {
            steps {
                echo '启动应用服务...'
                
                script {
                    try {
                        // 方法1: 如果配置了Windows服务
                        bat """
                        sc query "${SERVICE_NAME}" >nul 2>&1
                        if %errorlevel% equ 0 (
                            echo 启动Windows服务: ${SERVICE_NAME}
                            sc start "${SERVICE_NAME}"
                        ) else (
                            echo 以后台进程方式启动应用...
                            cd /d "${DEPLOY_PATH}"
                            start /b call start_app.bat
                        )
                        """
                        
                        // 等待应用启动
                        sleep 15
                        
                    } catch (Exception e) {
                        echo "启动服务时出现问题: ${e.getMessage()}"
                        error "应用启动失败"
                    }
                }
            }
        }
        
        stage('健康检查') {
            steps {
                echo '执行应用健康检查...'
                
                script {
                    def maxRetries = 5
                    def retryCount = 0
                    def isHealthy = false
                    
                    while (retryCount < maxRetries && !isHealthy) {
                        try {
                            // 检查应用是否响应
                            bat """
                            curl -f http://localhost:${APP_PORT}/ || exit 1
                            """
                            
                            isHealthy = true
                            echo "✅ 应用健康检查通过"
                            
                        } catch (Exception e) {
                            retryCount++
                            echo "健康检查失败，重试 ${retryCount}/${maxRetries}"
                            
                            if (retryCount < maxRetries) {
                                sleep 10
                            } else {
                                error "❌ 应用健康检查失败，部署可能有问题"
                            }
                        }
                    }
                }
            }
        }
        
        stage('清理工作') {
            steps {
                echo '执行清理工作...'
                
                // 清理旧的备份文件（保留最近7天）
                bat """
                forfiles /p "${DB_BACKUP_DIR}" /m *.db /d -7 /c "cmd /c del @path" 2>nul || echo 没有需要清理的备份文件
                """
                
                // 清理临时文件
                bat """
                cd /d "${DEPLOY_PATH}"
                if exist temp rmdir /S /Q temp
                if exist __pycache__ rmdir /S /Q __pycache__
                """
            }
        }
    }
    
    post {
        always {
            echo '流水线执行完成'
            
            // 记录部署信息
            bat """
            echo [%date% %time%] 部署完成 - Build: ${BUILD_NUMBER} >> "${DEPLOY_PATH}\\deploy.log"
            """
        }
        
        success {
            echo '✅ 部署成功！'
            
            // 可以添加成功通知
            // emailext (
            //     subject: "部署成功 - ${APP_NAME} Build #${BUILD_NUMBER}",
            //     body: "应用部署成功，访问地址: http://localhost:${APP_PORT}",
            //     to: "admin@company.com"
            // )
        }
        
        failure {
            echo '❌ 部署失败！'
            
            // 尝试回滚到备份版本
            script {
                try {
                    def timestamp = new Date().format('yyyyMMdd')
                    
                    bat """
                    echo 尝试回滚到备份版本...
                    if exist "${DB_BACKUP_DIR}\\app_${timestamp}*.db" (
                        for /f %%i in ('dir /b /o-d "${DB_BACKUP_DIR}\\app_${timestamp}*.db"') do (
                            copy "${DB_BACKUP_DIR}\\%%i" "${DEPLOY_PATH}\\app.db"
                            goto :break
                        )
                        :break
                    )
                    """
                    
                } catch (Exception e) {
                    echo "回滚失败: ${e.getMessage()}"
                }
            }
            
            // 发送失败通知
            // emailext (
            //     subject: "部署失败 - ${APP_NAME} Build #${BUILD_NUMBER}",
            //     body: "部署过程中出现错误，请检查日志。",
            //     to: "admin@company.com"
            // )
        }
        
        unstable {
            echo '⚠️ 部署完成但存在警告'
        }
    }
} 