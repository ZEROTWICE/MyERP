# 工资管理系统

这是一个基于Flask的工资管理系统，用于管理企业员工的工资计算、工序管理、任务分配等功能。

## 功能特性

### 1. 用户管理
- 多角色支持（管理员、经理、普通用户）
- 用户登录和权限控制
- 用户信息管理

### 2. 工序管理
- 工序信息维护
- 工序价格设置
- 工序历史记录查询

### 3. 任务管理
- 任务分配
- 任务进度跟踪
- 任务完成状态更新
- 批量导入导出任务

### 4. 奖惩管理
- 奖金和处罚记录
- 奖惩原因记录
- 奖惩历史查询
- 批量导入导出奖惩记录

### 5. 工资计算
- 基于工序和任务的工资自动计算
- 奖惩金额自动计入
- 工资报表生成
- 工资历史记录查询

### 6. 数据导入导出
- 支持Excel格式的数据导入导出
- 工序价格导入导出
- 任务数据导入导出
- 奖惩记录导入导出

### 7. 审计日志
- 操作记录追踪
- 数据变更历史
- 支持数据回滚

## 技术栈

- 后端：Python Flask
- 数据库：SQLite/MySQL
- 前端：Bootstrap 5 + jQuery
- UI组件：Select2, DataTables
- 文件处理：openpyxl

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
flask run
```

## 配置说明

1. 数据库配置
- 在 `config.py` 中配置数据库连接信息
- 默认使用SQLite，可切换至MySQL

2. 系统配置
- 在 `config.py` 中配置系统参数
- 可设置分页大小、上传文件限制等

## 使用说明

1. 初始管理员账号
- 用户名：admin
- 密码：请查看初始化脚本或联系系统管理员

2. 基本操作流程
- 首先配置工序信息和价格
- 创建员工账号
- 分配任务给员工
- 记录奖惩信息
- 生成工资报表

## 注意事项

1. 数据安全
- 定期备份数据库
- 妥善保管管理员密码
- 及时更新系统安全补丁

2. 操作建议
- 建议使用批量导入功能处理大量数据
- 定期检查系统日志
- 及时处理异常情况

## 更新日志

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