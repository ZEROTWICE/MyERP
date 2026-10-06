"""「把 @property / 不存在的列当数据库列用」的长期闸门（只读检查，不需要数据库）。

## 为什么存在
本项目已 **5 次**踩同一个坑：在查询表达式或类级访问里用了模型上的 `@property`，
或用了模型上根本不存在的列名。这类错误**不会抛异常**，而是静默失效：

- `Employee.status`（是 `@property`，返回 '在职'/'离职'）→ `Employee.status == 'active'`
  在 Python 里求值为假，SQLAlchemy 当恒假条件，**过滤恒空、不报错**；
- `RawMaterial.material_name`（是 `@property`，读 `category.name`）→ `material_name.like(...)`
  抛 `AttributeError: 'property' object has no attribute 'like'`，被外层 `except` 吞掉；
- `RawMaterial(material_name=...)`（构造参数）→ 构造器不接受该名，**逐行失败**；
- `FinishedProduct.current_stock` / `FinishedProduct.storage_date`（**根本不存在**）→
  属性访问报错后被 `except` 吞掉，或构造时 `TypeError` 被逐行吞掉。

## 检查什么
用 `ast` 静态分析，**不导入应用、不连数据库**：

1. 解析 `app/models.py`，为每个类收集「类体里赋值过的名字」「方法名」「`@property` 名字」「项目内的基类」；
2. 扫描源码目录（默认 `app/`，跳过备份文件与 `__pycache__`），找出形如 `类名.属性名` 的访问，
   命中以下任一即报违规：
   - **A 类**：该名字是**该类的 `@property`**（类级访问 property 永远是错的，在查询表达式里更错）；
   - **B 类**：该名字在**该类及其项目内基类**里都不存在（拼错/不存在的列），
     例如把只在 `RawMaterial` 上定义的 `storage_date` 用到 `FinishedProduct` 上。

## 用法
    python -B scripts/check_properties.py                 # 扫 app/
    python -B scripts/check_properties.py --root <dir>    # 扫指定目录（自测用）
    python -B scripts/check_properties.py --verbose       # 打印通过项统计

退出码：无违规 0；有违规 1。

## 边界（有意为之）
- 只认 `类名.属性名` 这种类级访问。`instance.property` 无法静态判定，不做检查。
- 名字解析只看 `app/models.py` 里定义的类与项目内基类；SQLAlchemy/Flask-SQLAlchemy 提供的
  内部属性（`query`/`metadata`/`__table__` 等）在 `CLS_WHITELIST` 中放行。
- 备份文件（`*.bak`、`*.new`、`*.backup`）与 `__pycache__` 一律跳过。
- `SKIP_FILENAMES` 里保留的 4 个名字（`routes_backup.py`、`routes_original.py`、
  `routes_full.py`、`routes_with_duplicates.py`）所指文件**已于 2026-09-18 从仓库删除**，
  名字留作防御：这类超大遗留副本可能带语法错误，若被误恢复，跳过它们比让本脚本崩在
  `ast.parse` 更好。
"""
import argparse
import ast
import os
import sys

MODELS_REL = os.path.join('app', 'models.py')

# 备份文件 / 生成物：不参与检查
SKIP_FILENAMES = {
    'routes_backup.py', 'routes_original.py', 'routes_full.py', 'routes_with_duplicates.py',
}
SKIP_SUFFIXES = ('.bak', '.new', '.backup', '.pyc')

# SQLAlchemy / Flask-SQLAlchemy 与 Python 协议提供的名字，不是模型自己声明的列
CLS_WHITELIST = {
    'query', 'metadata', 'registry', 'mapper', '__table__', '__tablename__', '__mapper__',
    '__table_args__', '__init__', '__repr__', '__str__', '__eq__', '__ne__', '__hash__',
    '__bool__', '__len__', '__iter__', '__getitem__', '__setattr__', '__delattr__',
}


def _is_skip_file(name):
    if name in SKIP_FILENAMES:
        return True
    if name.endswith(SKIP_SUFFIXES):
        return True
    return False


class ClassInfo(object):
    __slots__ = ('name', 'assigned', 'methods', 'props', 'bases')

    def __init__(self, name):
        self.name = name
        self.assigned = set()   # 类体里赋值过的名字（含 db.Column / db.relationship）
        self.methods = set()    # 普通方法名
        self.props = set()      # @property 名字
        self.bases = []         # 基类名（只保留字符串形式的简单名字）


def collect_models(models_path):
    """解析 models.py，返回 {类名: ClassInfo}。"""
    with open(models_path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), filename=models_path)

    classes = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        info = ClassInfo(node.name)
        for base in node.bases:
            if isinstance(base, ast.Name):
                info.bases.append(base.id)
            elif isinstance(base, ast.Attribute):  # db.Model
                info.bases.append(base.attr)
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        info.assigned.add(target.id)
                # 形如 `status = property(_get_status)` 也算 property
                val = stmt.value
                if (isinstance(val, ast.Call) and isinstance(val.func, ast.Name)
                        and val.func.id == 'property'):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            info.props.add(target.id)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                info.assigned.add(stmt.target.id)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_prop = any(
                    (isinstance(d, ast.Name) and d.id == 'property') for d in stmt.decorator_list
                )
                if is_prop:
                    info.props.add(stmt.name)
                else:
                    info.methods.add(stmt.name)
        classes[node.name] = info
    return classes


def resolved_names(cls_name, classes, seen=None):
    """该类 + 项目内基类上所有「存在」的名字。"""
    seen = seen or set()
    if cls_name in seen or cls_name not in classes:
        return set()
    seen.add(cls_name)
    info = classes[cls_name]
    names = set(info.assigned) | set(info.methods) | set(info.props)
    for base in info.bases:
        if base in classes:
            names |= resolved_names(base, classes, seen)
    return names


def scan_file(path, classes, violations):
    with open(path, encoding='utf-8') as fh:
        try:
            tree = ast.parse(fh.read(), filename=path)
        except SyntaxError as exc:
            violations.append((path, getattr(exc, 'lineno', 0), '语法错误，未能解析：%s' % exc.msg, '?', '?'))
            return

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        value = node.value
        if not isinstance(value, ast.Name) or value.id not in classes:
            continue
        attr = node.attr
        if attr in CLS_WHITELIST or attr.startswith('__'):
            continue
        info = classes[value.id]
        if attr in info.props:
            violations.append((
                path, node.lineno, '把 @property 当列用', '%s.%s' % (value.id, attr),
                '该类上 %s 是 @property，不是数据库列' % attr,
            ))
        elif attr not in resolved_names(value.id, classes):
            violations.append((
                path, node.lineno, '访问了该类不存在的属性', '%s.%s' % (value.id, attr),
                '该类及其项目内基类都没有 %s' % attr,
            ))


def main():
    parser = argparse.ArgumentParser(description='检查「把 @property / 不存在的列当数据库列用」')
    parser.add_argument('--root', default='app', help='要扫描的源码目录（默认 app）')
    parser.add_argument('--verbose', action='store_true', help='打印通过项统计')
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    models_path = os.path.join(root, 'models.py') if os.path.isdir(root) else MODELS_REL
    if not os.path.exists(models_path):
        models_path = MODELS_REL
    if not os.path.exists(models_path):
        print('找不到 app/models.py，无法解析模型：%s' % models_path)
        return 2

    classes = collect_models(models_path)
    if args.verbose:
        print('已解析模型类 %d 个，其中带 @property 的 %d 个'
              % (len(classes), sum(1 for c in classes.values() if c.props)))

    violations = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in filenames:
            if not name.endswith('.py') or _is_skip_file(name):
                continue
            scanned += 1
            scan_file(os.path.join(dirpath, name), classes, violations)

    if violations:
        violations.sort(key=lambda v: (v[0], v[1]))
        print('发现 %d 处违规：' % len(violations))
        for path, lineno, kind, expr, why in violations:
            rel = os.path.relpath(path)
            print('  %s:%s  [%s]  %s —— %s' % (rel, lineno, kind, expr, why))
        print('RESULT: FAIL')
        return 1

    print('已扫描 %d 个文件，模型类 %d 个' % (scanned, len(classes)))
    print('RESULT: OK（未发现把 @property / 不存在的列当数据库列用）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
