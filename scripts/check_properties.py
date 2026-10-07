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

1. 解析 `app/models.py`，为每个类收集「类体里赋值过的名字」「方法名」「`@property` 名字」
   「项目内的基类」「**backref / back_populates 声明的反向属性名**」；
2. 扫描源码目录（默认 `app/`，跳过备份文件与 `__pycache__`），**两遍**找违规：

   **A 类（类级访问，原有面）** 形如 `类名.属性名`：
   - **A-1**：该名字是**该类的 `@property`**（类级访问 property 永远是错的，在查询表达式里更错）；
   - **A-2**：该名字在**该类及其项目内基类**里都不存在（拼错/不存在的列），
     例如把只在 `RawMaterial` 上定义的 `storage_date` 用到 `FinishedProduct` 上。

   **B 类（实例访问，TL-05 新增面）** 形如 `变量.属性名`，且该变量**可静态判定为某模型类的实例**：
   - **B-1**：该属性名在该类及其项目内基类里都不存在（`e = Employee(); e.not_a_column`）。
     实例访问 `@property` **合法**（`emp.status` 正是正常用法）⇒ 实例面**不做** A-1 判定。

## 实例绑定口径（宁可漏报，不可误报）
只在**全文件唯一且可静态判定**时才认一个变量是某类的实例：

* **构造**：`x = Employee(...)`；
* **单实例查询**：链的终结方法 ∈ `INSTANCE_TERMINALS`（`first`/`one`/`get`/…）——
  `Employee.query.first()`、`Employee.query.filter_by(...).first()`、`db.session.get(Employee, id)`；
* **注解**：`x: Employee = ...`（值不可判定时按注解取类）；
* **迭代**：`for x in <以类名起头的 query 链>`（迭代产出实例），comprehension 同口径；
* **明确不绑定**（否则会误报）：
  - `x = Employee.query.filter(...)` / `.all()` / `.count()` —— 产出的是 **Query/集合**，不是实例；
  - `x = Employee`（裸类名）—— 交给类级面；
  - 任何 `json.dumps(Employee)` 式「类名只当普通实参」的调用；
  - 同一名字若还被赋值成非该类的东西，或是**函数参数 / import 名 / with-as / except-as** ⇒ 解绑。

## 用法
    python -B scripts/check_properties.py                 # 扫 app/
    python -B scripts/check_properties.py --root <dir>    # 扫指定目录（自测/注入破坏用）
    python -B scripts/check_properties.py --verbose       # 打印通过项统计
    python -B scripts/check_properties.py --selftest      # 受控合成源码的阳性/阴性对照（含 TL-05 面）

退出码：无违规 0；有违规 1；环境错误（找不到 models.py）2。

## 边界（有意为之）
- 只认「类名.属性名」（A 类）与「**可静态判定**的实例.属性名」（B 类，TL-05）；
  无法判定来源的变量（参数、返回值链、字典取值、跨函数传递…）**不检查**。
- **反向属性（backref / back_populates）算存在**：`db.relationship('X', backref='items')`
  在 `X` 上创建 `items`（运行时存在）；本闸门按该声明放行，避免误报（27 处历史误报即此类）。
- 名字解析只看 `app/models.py` 里定义的类与项目内基类；SQLAlchemy/Flask-SQLAlchemy 提供的
  内部属性（`query`/`metadata`/`__table__`/`_sa_instance_state` 等）在 `CLS_WHITELIST` /
  `INST_WHITELIST` 中放行。
- 属性**赋值**（`e.x = 1`、`del e.x`）不算读违规（本闸门只查读取）。
- 备份文件（`*.bak`、`*.new`、`*.backup`）与 `__pycache__` 一律跳过。
- `SKIP_FILENAMES` 里保留的 4 个名字（`routes_backup.py`、`routes_original.py`、
  `routes_full.py`、`routes_with_duplicates.py`）所指文件**已于 2026-09-18 从仓库删除**，
  名字留作防御：这类超大遗留副本可能带语法错误，若被误恢复，跳过它们比让本脚本崩在
  `ast.parse` 更好。
- **既有计数口径不得漂移**（E-04 / run_gates 的冻结值）：`已扫描 23 个文件，模型类 74 个`
  与 `RESULT: OK` 是判据钉住的两行；新增实例面**不得**改动它们（TL-05 验收要求）。
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

#: 实例面额外放行：ORM 运行时注入的私有状态（不是模型声明的列）
INST_WHITELIST = set(CLS_WHITELIST) | {'_sa_instance_state'}

#: 只有这些「终结方法」的调用链才产出**单个实例**（赋值的实例绑定口径）
INSTANCE_TERMINALS = {'first', 'one', 'one_or_none', 'get', 'get_or_404', 'first_or_404',
                      'scalar', 'scalars', 'last'}

#: 判定「query 链」时认的链属性名（`db.session.query(Employee).get(1)` 这类）
_CHAIN_HINTS = ('query', 'session', 'get', 'filter', 'filter_by')


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


def _str_const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _relationship_target(node):
    """`db.relationship('X', ...)` 的目标类名（取不到则 None）。"""
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Name):
        return first.id
    if isinstance(first, ast.Attribute):
        return first.attr
    name = _str_const(first)
    return name.split('.')[-1] if name else None


def _relationship_reverse_names(node):
    """`db.relationship(..., backref='items')` / `backref=db.backref('items', ...)` /
    `back_populates='items'` 在**目标类**上声明的属性名。"""
    names = []
    for kw in node.keywords:
        if kw.arg == 'backref':
            val = kw.value
            name = _str_const(val)
            if name:
                names.append(name)
            elif isinstance(val, ast.Call):
                for a in val.args:
                    name = _str_const(a)
                    if name:
                        names.append(name)
                        break
        elif kw.arg == 'back_populates':
            name = _str_const(kw.value)
            if name:
                names.append(name)
    return names


def _is_relationship_call(value):
    return (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            and value.func.attr == 'relationship')


def collect_models_from_source(source, filename='<models>'):
    """解析 models 源码文本，返回 ``(classes, extra_names)``。

    * ``classes`` = {类名: ClassInfo}（含 backref/back_populates 声明的反向属性）；
    * ``extra_names`` = 目标类无法解析时的反向属性名（全局放行集合，保守）。
    """
    tree = ast.parse(source, filename=filename)

    classes = {}
    pending = []          # (target_name, [names])
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        info = ClassInfo(node.name)
        for base in node.bases:
            if isinstance(base, ast.Name):
                info.bases.append(base.id)
            elif isinstance(base, ast.Attribute):  # db.Model
                info.bases.append(base.attr)
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        info.assigned.add(target.id)
                val = stmt.value
                # 形如 `status = property(_get_status)` 也算 property
                if (isinstance(val, ast.Call) and isinstance(val.func, ast.Name)
                        and val.func.id == 'property'):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            info.props.add(target.id)
                if _is_relationship_call(val):
                    pending.append((_relationship_target(val),
                                    _relationship_reverse_names(val)))
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                info.assigned.add(stmt.target.id)
                if _is_relationship_call(stmt.value):
                    pending.append((_relationship_target(stmt.value),
                                    _relationship_reverse_names(stmt.value)))
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_prop = any(
                    (isinstance(d, ast.Name) and d.id == 'property') for d in stmt.decorator_list
                )
                if is_prop:
                    info.props.add(stmt.name)
                else:
                    info.methods.add(stmt.name)
        classes[node.name] = info

    extra = set()
    for target, names in pending:
        if target in classes:
            classes[target].assigned |= set(names)
        else:
            extra |= set(names)
    return classes, extra


def collect_models(models_path):
    """解析 models.py 文件，返回 ``(classes, extra_names)``。"""
    with open(models_path, encoding='utf-8') as fh:
        return collect_models_from_source(fh.read(), filename=models_path)


def resolved_names(cls_name, classes, seen=None, extra=None):
    """该类 + 项目内基类上所有「存在」的名字（含 backref 反向属性与全局放行名）。"""
    seen = seen or set()
    if cls_name in seen or cls_name not in classes:
        return set()
    seen.add(cls_name)
    info = classes[cls_name]
    names = set(info.assigned) | set(info.methods) | set(info.props) | set(extra or ())
    for base in info.bases:
        if base in classes:
            names |= resolved_names(base, classes, seen, extra)
    return names


# ------------------------------------------------------------------ TL-05：实例面
def _target_names(node):
    """赋值 / for / with 目标里的简单名字（属性、下标目标不算）。"""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names = []
        for e in node.elts:
            names.extend(_target_names(e))
        return names
    return []


def _call_chain(node):
    """把 `Call/Attribute/Subscript` 链解成 (根名, [链属性名])。"""
    attrs = []
    cur = node
    for _ in range(64):                      # 防病态深链
        if isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.Attribute):
            attrs.append(cur.attr)
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        else:
            break
    root = cur.id if isinstance(cur, ast.Name) else None
    return root, attrs


def _infer_instance_class(node, classes, for_iteration=False):
    """表达式能否静态判定为某模型类的**实例**（是则返回类名，否则 None）。

    * `for_iteration=False`（赋值/注解）：只认「直接构造」与「终结方法 ∈ INSTANCE_TERMINALS」；
    * `for_iteration=True`（for/comprehension 的 iter）：以类名起头的 query 链即算（迭代产出实例）。
    """
    if not isinstance(node, ast.Call):
        return None
    root, attrs = _call_chain(node)
    terminal = attrs[0] if attrs else None

    if isinstance(node.func, ast.Name) and node.func.id in classes:
        return node.func.id                      # Employee(...)
    if for_iteration:
        if root in classes and any(h in attrs for h in _CHAIN_HINTS):
            return root                          # for x in Employee.query...
        if terminal in INSTANCE_TERMINALS and root in classes:
            return root
    elif root in classes and terminal in INSTANCE_TERMINALS:
        return root                              # Employee.query.first()
    # `db.session.query(Employee)...` / `db.session.get(Employee, id)`：链上出现类名实参
    if any(h in attrs for h in _CHAIN_HINTS):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                for arg in sub.args:
                    if isinstance(arg, ast.Name) and arg.id in classes:
                        return arg.id
    return None


def _infer_from_annotation(annotation, classes):
    """`x: Employee = ...` 的注解形态（含字符串前向引用）。"""
    if isinstance(annotation, ast.Name) and annotation.id in classes:
        return annotation.id
    if isinstance(annotation, ast.Attribute) and annotation.attr in classes:
        return annotation.attr
    name = _str_const(annotation)
    if name and name.strip().strip("'\"") in classes:
        return name.strip().strip("'\"")
    return None


def instance_bindings(tree, classes):
    """{变量名: 模型类名}：**全文件唯一且可静态判定**的实例绑定（冲突/不可判定即解绑）。"""
    seen = {}

    def note(name, cls):
        if name in seen:
            if seen[name] != cls:
                seen[name] = None            # 冲突 ⇒ 解绑（宁可漏报）
        else:
            seen[name] = cls

    def note_args(args):
        for group in (args.args, args.kwonlyargs, args.posonlyargs,
                      [args.vararg] if args.vararg else [],
                      [args.kwarg] if args.kwarg else []):
            for a in group:
                if a is not None:
                    note(a.arg, None)

    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda):
            note_args(node.args)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            note_args(node.args)
            note(node.name, None)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for al in node.names:
                note((al.asname or al.name).split('.')[0], None)
        elif isinstance(node, ast.Assign):
            cls = _infer_instance_class(node.value, classes)
            for t in node.targets:
                for nm in _target_names(t):
                    note(nm, cls)
        elif isinstance(node, ast.AnnAssign):
            cls = _infer_instance_class(node.value, classes) if node.value is not None else None
            if cls is None:
                cls = _infer_from_annotation(node.annotation, classes)
            for nm in _target_names(node.target):
                note(nm, cls)
        elif isinstance(node, ast.For):
            cls = _infer_instance_class(node.iter, classes, for_iteration=True)
            for nm in _target_names(node.target):
                note(nm, cls)
        elif isinstance(node, ast.comprehension):
            cls = _infer_instance_class(node.iter, classes, for_iteration=True)
            for nm in _target_names(node.target):
                note(nm, cls)
        elif isinstance(node, ast.With):
            for item in node.items:
                if item.optional_vars is not None:
                    for nm in _target_names(item.optional_vars):
                        note(nm, None)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            note(node.name, None)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for nm in node.names:
                note(nm, None)
    return {k: v for k, v in seen.items() if v}


# ------------------------------------------------------------------ 扫描（两遍）
def scan_tree(path, tree, classes, violations, stats=None, extra=None):
    """扫一棵 AST：A 类（类级）+ B 类（实例级，TL-05）。只查**读取**，不查赋值/删除。"""
    # ---- A 类：类级访问（原有面）
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or isinstance(node.ctx, (ast.Store, ast.Del)):
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
        elif attr not in resolved_names(value.id, classes, extra=extra):
            violations.append((
                path, node.lineno, '访问了该类不存在的属性', '%s.%s' % (value.id, attr),
                '该类及其项目内基类都没有 %s' % attr,
            ))

    # ---- B 类：实例访问（TL-05 新增面）
    binds = instance_bindings(tree, classes)
    if stats is not None:
        stats['instance_bindings'] = stats.get('instance_bindings', 0) + len(binds)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or isinstance(node.ctx, (ast.Store, ast.Del)):
            continue
        value = node.value
        if not isinstance(value, ast.Name) or value.id not in binds:
            continue
        attr = node.attr
        if attr in INST_WHITELIST or attr.startswith('__'):
            continue
        cls_name = binds[value.id]
        if cls_name in classes and attr not in resolved_names(cls_name, classes, extra=extra):
            violations.append((
                path, node.lineno, '实例访问了该类不存在的属性', '%s.%s' % (value.id, attr),
                '%s 判定为 %s 的实例，而该类及其项目内基类都没有 %s'
                % (value.id, cls_name, attr),
            ))


def scan_file(path, classes, violations, stats=None, extra=None):
    with open(path, encoding='utf-8') as fh:
        try:
            tree = ast.parse(fh.read(), filename=path)
        except SyntaxError as exc:
            violations.append((path, getattr(exc, 'lineno', 0),
                               '语法错误，未能解析：%s' % exc.msg, '?', '?'))
            return
    scan_tree(path, tree, classes, violations, stats, extra)


# ------------------------------------------------------------------ 自检（TL-05 的对抗对照）
SELFTEST_MODELS = '''
class Base(object):
    pass


class Employee(Base):
    name = db.Column(db.String(50))
    dept_id = db.Column(db.Integer)

    @property
    def status(self):
        return 'zaizhi'

    def save(self):
        pass


class Dept(Base):
    title = db.Column(db.String(50))
    employees = db.relationship('Employee', backref='dept', lazy='dynamic')


class Prod(Base):
    items = db.relationship('ProdItem', backref=db.backref('prod', lazy='dynamic'))


class ProdItem(Base):
    name = db.Column(db.String(50))
'''


def selftest():
    """受控合成源码：阳性必须命中、阴性必须放行（含 TL-05 实例面）。"""
    classes, extra = collect_models_from_source(SELFTEST_MODELS, filename='<selftest-models>')
    cases = [
        ('CP-P1 类级访问 @property ⇒ 命中（A-1）',
         'def f():\n    return Employee.query.filter(Employee.status == "active").all()\n', 1),
        ('CP-P2 类级访问不存在的属性 ⇒ 命中（A-2）',
         'def f():\n    return Employee.query.filter(Employee.not_a_column == 1).all()\n', 1),
        ('CP-P3 实例访问不存在的属性 ⇒ 命中（B-1，TL-05 核心）',
         'def f():\n    e = Employee()\n    return e.not_a_column\n', 1),
        ('CP-P4 实例注解绑定 + 不存在属性 ⇒ 命中（B-1）',
         'def f():\n    e: Employee = build()\n    return e.not_a_column\n', 1),
        ('CP-P5 实例经 query 链绑定 + 不存在属性 ⇒ 命中（B-1）',
         'def f():\n    e = Employee.query.first()\n    return e.not_a_column\n', 1),
        ('CP-P6 db.session.query(Employee) 绑定 + 不存在属性 ⇒ 命中（B-1）',
         'def f():\n    e = db.session.query(Employee).get(1)\n    return e.not_a_column\n', 1),
        ('CP-P7 for 循环绑定 + 不存在属性 ⇒ 命中（B-1）',
         'def f():\n    for e in Employee.query.all():\n        print(e.not_a_column)\n', 1),
        ('CP-P8 绑定到别类、属性属该类不存在 ⇒ 命中（B-1）',
         'def f():\n    d = Dept.query.first()\n    return d.status\n', 1),
        ('CP-N1 实例访问 @property ⇒ 放行（实例面不做 A-1）',
         'def f():\n    e = Employee()\n    return e.status\n', 0),
        ('CP-N2 实例访问真实列 ⇒ 放行',
         'def f():\n    e = Employee()\n    return e.name, e.dept_id\n', 0),
        ('CP-N3 实例调用真实方法 ⇒ 放行',
         'def f():\n    e = Employee()\n    e.save()\n', 0),
        ('CP-N4 同名被二次赋值为不可判定 ⇒ 解绑（宁可漏报）',
         'def f():\n    e = Employee()\n    e = load()\n    return e.not_a_column\n', 0),
        ('CP-N5 不可判定来源的变量 ⇒ 不判',
         'def f():\n    e = load()\n    return e.not_a_column\n', 0),
        ('CP-N6 函数参数 ⇒ 一律不判（保守）',
         'def f(e):\n    return e.not_a_column\n', 0),
        ('CP-N7 属性**写**不算读违规 ⇒ 放行',
         'def f():\n    e = Employee()\n    e.anything = 1\n    del e.anything\n', 0),
        ('CP-N8 私有 / ORM 内部名 ⇒ 放行',
         'def f():\n    e = Employee()\n    return e._sa_instance_state, e.query\n', 0),
        ('CP-N9 类名当普通实参传递（非实例）⇒ 不判',
         'def f():\n    x = json.dumps(Employee)\n    return x.not_a_column\n', 0),
        ('CP-N10 类级访问真实列 ⇒ 放行（既有面不回归）',
         'def f():\n    return Employee.name\n', 0),
        ('CP-N11 Query 链（非实例）⇒ 不判（防 27 处类误报）',
         'def f():\n    q = Employee.query.filter(Employee.name == "x")\n'
         '    return q.count(), q.all()\n', 0),
        ('CP-N12 backref 声明的反向属性 ⇒ 算存在（防误报）',
         'def f():\n    e = Employee.query.first()\n    return e.dept\n', 0),
        ('CP-N13 backref=db.backref(...) 的反向属性 ⇒ 算存在',
         'def f():\n    p = Prod.query.first()\n    return p.items\n'
         '    # 反向：ProdItem.prod 由 backref 声明\n', 0),
        ('CP-N14 反向属性（ProdItem.prod）读 ⇒ 放行',
         'def f():\n    it = ProdItem.query.first()\n    return it.prod\n', 0),
    ]
    ok_all = True
    n_ok = 0
    for name, src, expect in cases:
        violations = []
        tree = ast.parse(src, filename='<selftest>')
        scan_tree('<selftest>', tree, classes, violations, extra=extra)
        got = len(violations)
        ok = got == expect
        ok_all = ok_all and ok
        n_ok += 1 if ok else 0
        print('  [%s] %s（期望 %d，实测 %d）%s'
              % ('PASS' if ok else 'FAIL', name, expect, got,
                 '' if ok else '  <- 判据不敏感/误报：%s' % (violations[:1],)))
    print('[check_properties] 自检 %d/%d 通过' % (n_ok, len(cases)))
    return 0 if ok_all else 1


def main():
    parser = argparse.ArgumentParser(description='检查「把 @property / 不存在的列当数据库列用」')
    parser.add_argument('--root', default='app', help='要扫描的源码目录（默认 app）')
    parser.add_argument('--verbose', action='store_true', help='打印通过项统计')
    parser.add_argument('--selftest', action='store_true',
                        help='受控合成源码的阳性/阴性对照（含 TL-05 实例面）')
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass

    if args.selftest:
        return selftest()

    root = os.path.abspath(args.root)
    models_path = os.path.join(root, 'models.py') if os.path.isdir(root) else MODELS_REL
    if not os.path.exists(models_path):
        models_path = MODELS_REL
    if not os.path.exists(models_path):
        print('找不到 app/models.py，无法解析模型：%s' % models_path)
        return 2

    classes, extra = collect_models(models_path)
    if args.verbose:
        print('已解析模型类 %d 个，其中带 @property 的 %d 个'
              % (len(classes), sum(1 for c in classes.values() if c.props)))

    violations = []
    stats = {}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in filenames:
            if not name.endswith('.py') or _is_skip_file(name):
                continue
            scanned += 1
            scan_file(os.path.join(dirpath, name), classes, violations, stats, extra)

    if args.verbose:
        print('实例绑定（可静态判定）%d 个；violations=%d 处'
              % (stats.get('instance_bindings', 0), len(violations)))

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
