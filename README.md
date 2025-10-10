# 工资管理系统

这是一个基于Flask的工资管理系统，用于管理企业员工的工资计算、工序管理、任务分配等功能。

## 功能特性

### 1. 用户管理
- 多角色支持（管理员、经理、普通用户）
- 用户登录和权限控制
- 用户信息管理
- 个人工资查询界面

### 2. 工序管理
- 工序信息维护
- 工序价格设置
- 工序历史记录查询
- 工序编码规则管理

### 3. 任务管理
- 任务分配
- 任务进度跟踪
- 任务完成状态更新
- 批量导入导出任务
- 任务完成自动生成生产记录

### 4. 奖惩管理
- 奖金和处罚记录
- 奖惩原因记录
- 奖惩历史查询
- 批量导入导出奖惩记录
- 关联员工和工序的奖惩管理

### 5. 工资计算
- 基于工序和任务的工资自动计算
- 奖惩金额自动计入
- 工资报表生成
- 工资历史记录查询

### 6. 工资变更管理
- 查看员工工资变更历史
- 添加新的工资或系数变更
- 设置变更生效日期
- 删除未生效的变更记录
- 完整的变更审计日志

### 7. 库存管理
- 原材料库存管理
- 成品库存管理
- 库存编码规则设置
- 库存变更记录
- 批量导入导出库存数据
- 库存状态追踪

### 8. 数据导入导出
- 支持Excel格式的数据导入导出
- 工序价格导入导出
- 任务数据导入导出
- 奖惩记录导入导出
- 库存数据导入导出

### 9. 系统功能
- 全局流水号管理
- 编码规则管理
- 完整的审计日志
- 数据变更历史
- 支持数据回滚

### 10. 生产中心（以产品为中心）
- 从销售订单选择性创建生产订单（支持勾选行，已关联的行默认勾选且不可修改）
- 生产订单可分批，严格依据“剩余可下达数量”防止超发
- 按产品工序路由自动创建生产任务，支持“工序分配规则”（轮询、加权、固定）
- 技术拆解：在分解/创建任务时允许编辑规格参数并保留到记录
- 生产可视化：批次/任务状态联动更新
- 任务执行可记录操作者与实际使用原材料

### 11. 通知系统（含原材料替用）
- 支持触发类型规则、模板渲染、系统内通知投递
- 新增触发类型：原材料替用（raw_substitution）
- 任务更新提交材料时，自动识别非 BOM 材料并触发“原材料替用”通知
- 通知规则可按用户/角色/部门投递，支持优先级与条件筛选

## 技术栈

- 后端：Python Flask
- 数据库：SQLite/MySQL
- 前端：Bootstrap 5 + jQuery
- UI组件：Select2, DataTables, SweetAlert2, Toastr
- 文件处理：openpyxl
- 移动端支持：响应式设计
- 扫码兼容：BarcodeDetector（优先）+ jsQR（回退）+ getUserMedia

## 安装说明

1. 克隆项目
```bash
git clone [项目地址]
cd wage_management_system
```

2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 初始化数据库
```bash
flask db upgrade
```

5. 运行项目
```bash
# 方式一（Flask CLI）
flask run

# 方式二（直接运行）
python main.py
```

6. Docker部署（可选）
```bash
docker build -t wage-system .
docker run -d -p 5000:5000 wage-system
```

## 配置说明

1. 数据库配置
- 在 `config.py` 中配置数据库连接信息
- 默认使用SQLite，可切换至MySQL

2. 系统配置
- 在 `config.py` 中配置系统参数
- 可设置分页大小、上传文件限制等
- 配置编码规则和流水号格式

## 使用说明

1. 初始管理员账号
- 用户名：admin
- 密码：请查看初始化脚本或联系系统管理员

2. 基本操作流程
- 首先配置工序信息和价格
- 创建员工账号
- 设置编码规则
- 管理库存信息
- 分配任务给员工
- 记录奖惩信息
- 管理工资变更
- 生成工资报表

### 生产中心使用指南
- 销售订单详情：点击“创建生产订单”，按需勾选销售行创建对应生产订单（已关联的行默认勾选且不可修改）
- 生产订单详情：使用“新增批次”，上限为“剩余可下达数量”（自动计算）
- 工序分配：在“工序分配”管理页为各工序配置分配策略与成员（轮询/加权/固定）
- 开始生产：创建批次或任务后，系统按工序规则自动分配员工并创建任务
- 我的任务：在“更新完成数量”弹窗中选择原材料，支持摄像头扫码与相册识别；提交前进行 BOM 校验
- BOM 校验：若选择了非 BOM 原材料，前端弹出 SweetAlert2 警告，确认后按“替用”提交
- 审计与联动：提交后记录审计日志（含 materials 与 substitutions），并联动更新批次/任务状态

### 通知：原材料替用
- 触发时机：在“我的任务/更新完成数量”提交时，系统自动识别非 BOM 原材料并触发通知
- 规则配置：在“通知规则”中新增规则，触发类型选择“原材料替用（raw_substitution）”，设置接收者（用户/角色/部门）与优先级
- 模板配置：在“通知模板”中新增模板，触发类型选择“原材料替用（raw_substitution）”，可使用变量：task_id, order_number, operator_name, items
- 查看通知：顶部通知入口或“通知中心”页面可查看最新通知与未读统计

### 移动端扫码与性能
- 本地化静态资源（Font Awesome/Select2/SweetAlert2/Toastr/jQuery 等），避免外网依赖
- <head> 预加载 Font Awesome woff2，移除重复 Select2 引用，保证加载顺序
- 摄像头优先使用 getUserMedia，不可用时回退相册+jsQR；图片识别使用 createImageBitmap 与压缩处理避免卡顿

## 注意事项

1. 数据安全
- 定期备份数据库
- 妥善保管管理员密码
- 及时更新系统安全补丁

2. 操作建议
- 建议使用批量导入功能处理大量数据
- 定期检查系统日志
- 及时处理异常情况
- 工资变更设置要提前规划生效日期
- 定期核对库存信息

### 数据迁移与故障排查
- 初始化/升级迁移：
```bash
flask db upgrade
```
- 若出现“Multiple head revisions are present”：
```bash
flask db stamp heads
flask db merge -m "merge heads"
flask db upgrade
```
- 若出现“table ... already exists”且为历史表重复创建：
```bash
flask db stamp heads
flask db upgrade
```
- 如需手动创建特定表（示例）：
```python
# 正确写法是 __table__
ProcessAssignmentRule.__table__.create(db.engine, checkfirst=True)
```

## 更新日志

### v1.3.0
- 新增“生产中心（以产品为中心）”模块：从销售创建生产订单、批次管控（剩余可下达），按工序规则自动建任务，技术拆解支持参数修改
- 新增“工序分配”管理页：支持轮询、加权、固定策略与成员启用序列
- 我的任务：新增扫码入料（摄像头/相册），BOM 校验并允许替用，前端弹窗确认
- 审计增强：任务更新记录 materials 与 substitutions（替用明细）
- 通知系统：新增触发类型“原材料替用（raw_substitution）”，提交替用时自动通知
- 静态资源本地化与移动端优化：预加载字体、移除重复依赖、修复移动端 Chrome 加载缓慢与样式缺失
- 迁移与容错：API/页面对“规则表未初始化”等场景友好提示；提供迁移冲突与已存在表的处理指引

### v1.2.0
- 新增库存管理功能
- 添加全局流水号管理
- 实现编码规则管理
- 优化奖惩管理功能
- 添加移动端支持
- 支持Docker部署

### v1.1.0
- 新增工资变更管理功能
- 支持工资和系数变更
- 添加变更历史查看
- 实现变更生效日期设置
- 完善审计日志功能

### v1.0.0
- 基础功能实现
- 工序管理
- 任务管理
- 奖惩管理
- 工资计算
- 数据导入导出

## 联系方式

如有问题或建议，请联系系统管理员。

## 许可证

本项目采用 MIT 许可证。

# wage_management_system



## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

Already a pro? Just edit this README.md and make it your own. Want to make it easy? [Use the template at the bottom](#editing-this-readme)!

## Add your files

- [ ] [Create](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#create-a-file) or [upload](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#upload-a-file) files
- [ ] [Add files using the command line](https://docs.gitlab.com/topics/git/add_files/#add-files-to-a-git-repository) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin http://192.168.50.115:8880/root/wage_management_system.git
git branch -M main
git push -uf origin main
```

## Integrate with your tools

- [ ] [Set up project integrations](http://192.168.50.115:8880/root/wage_management_system/-/settings/integrations)

## Collaborate with your team

- [ ] [Invite team members and collaborators](https://docs.gitlab.com/ee/user/project/members/)
- [ ] [Create a new merge request](https://docs.gitlab.com/ee/user/project/merge_requests/creating_merge_requests.html)
- [ ] [Automatically close issues from merge requests](https://docs.gitlab.com/ee/user/project/issues/managing_issues.html#closing-issues-automatically)
- [ ] [Enable merge request approvals](https://docs.gitlab.com/ee/user/project/merge_requests/approvals/)
- [ ] [Set auto-merge](https://docs.gitlab.com/user/project/merge_requests/auto_merge/)

## Test and Deploy

Use the built-in continuous integration in GitLab.

- [ ] [Get started with GitLab CI/CD](https://docs.gitlab.com/ee/ci/quick_start/)
- [ ] [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/ee/user/application_security/sast/)
- [ ] [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/ee/topics/autodevops/requirements.html)
- [ ] [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/ee/user/clusters/agent/)
- [ ] [Set up protected environments](https://docs.gitlab.com/ee/ci/environments/protected_environments.html)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.


already 流水号 ✔
already 修复奖惩管理找不到员工和工序 ✔
already 工资变更生效日

next 库存管理
next 任务完成自动创建生产记录
next user界面我的薪资。

last-1 创建手机版
last 创建docker file

非常好，现在请帮我添加一个通知模块。
对于这个模块，我有如下构想。
首先，这个模块由触发端，服务端，和接收端三端构成。其中触发端可以插入目前已有的代码中，将某些信息，如工艺，规格信息变更

wiki
https://deepwiki.com/ZEROTWICE/MyERP