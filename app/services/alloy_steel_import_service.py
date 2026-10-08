"""合金钢辙叉数据导入服务。

把两个转换器的产出落库：

* ``import_price_result`` —— 「工具/合金钢辙叉计件工价标准.xlsx」→ ``ProcessPrice`` / ``ProcessPriceGroup``
* ``import_bom_result``   —— 「工具/48页表格/（N）XXX.xlsx」→ ``Product`` / ``ProductBOM``

与既有导入端点（``import_process_prices`` / ``import_products``）刻意不同的几点，都是有原因的：

1. **行级容错**（AGENTS.md 硬约束）：坏行只记「第N页 行M：原因」并跳过，绝不因为一行失败整批
   500。每行写在一个 SAVEPOINT（``db.session.begin_nested()``）里，异常只回滚该行，
   外层的其它行不受影响。
2. **自然键幂等**：工价以 ``(process_code, price_type)`` 为键。已存在同键、同值的当前版本 →
   跳过（不升版），只有值真的变了才 ``is_current=False`` + ``version+1``。同一份文件重复导入
   不会把版本号刷爆。小计的「同值」包含它的成员工序集合。
3. **BOM 子件复用**：子件键取 图号 → 代码 → 名称（源表很多行只有代码、没有图号）。同键复用
   同一个 ``Product``，父子层级用 ``ProductBOM(material_type='product', product_id=父件,
   material_id=子件)`` 表达，与手工录入 BOM 的写法一致。
4. **不发明数据**：源表里的错别字、Excel 自动填充事故（``Q236(底板)``/``ZG230-451``）、
   罗马数字全半角混用等一律按原值导入并进报告，不做启发式「修正」。
5. **dry_run**：只解析、校验、统计并 flush，最后 ``db.session.rollback()``，用于「先出报告，
   人工确认后再落库」。报告结构与真实导入完全一致，可以直接对比。**注意**：dry_run 能回滚
   依赖 :func:`_begin_real_transaction`——CPython 的 ``sqlite3`` 只在 INSERT/UPDATE/DELETE
   之前隐式 BEGIN，如果事务的第一条 SQL 是 ``SAVEPOINT``（本服务每行都用
   ``db.session.begin_nested()``，``SerialNumber.get_next_number()`` 内部也是），SQLite 会把
   它当成最外层保存点，``RELEASE`` 等价于 ``COMMIT``，之后 ``rollback()`` 回滚不掉任何行。
"""

import hashlib
import re
from datetime import date, datetime, time

from flask import current_app
from sqlalchemy import text as sa_text

from app import db
from app.models import AuditLog, ProcessPrice, ProcessPriceGroup, Product, ProductBOM

PRICE_TYPE_NORMAL = 'normal'
PRICE_TYPE_SUBTOTAL = 'subtotal'

CODE_LIMIT = 50
NAME_LIMIT = 100
TEXT_LIMIT = 100

CHILD_CATEGORY = 'BOM子件'
PARENT_CATEGORY = '辙叉总成'

DEFAULT_ERROR_LIMIT = 200
DEFAULT_WARNING_LIMIT = 200


# ---------------------------------------------------------------- 小工具

def _text(value):
    """去掉首尾空白（含全角空格），None → ''。"""
    if value is None:
        return ''
    return str(value).replace('\u3000', ' ').strip()


def _clip(value, limit):
    """按列宽截断。返回 (值, 是否截断)。"""
    text = _text(value)
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _make_code(key, limit=CODE_LIMIT):
    """把子件键折成产品编号：空白折叠、超长时截断 + 6 位摘要（保证确定性且可读）。"""
    text = re.sub(r'\s+', ' ', _text(key))
    if len(text) <= limit:
        return text
    digest = hashlib.md5(text.encode('utf-8')).hexdigest()[:6].upper()
    return text[:limit - 7] + '-' + digest


def _to_datetime(value):
    """把 date/str/datetime 统一成 datetime（DateTime 列不接受纯 date 之外的类型）。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = _text(value)
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y年%m月%d日'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _push(bucket, message):
    """往报告的错误/告警桶里追加，超过上限只计数不追加（避免报告刷屏）。"""
    bucket['count'] += 1
    if len(bucket['items']) < bucket['limit']:
        bucket['items'].append(message)


def _new_bucket(limit):
    return {'count': 0, 'items': [], 'limit': limit}


def _log_import(action, details, user_id, target_model):
    """记一条汇总审计。批量导入不逐行建审计行（回滚粒度是整批，不是单行）。"""
    try:
        db.session.add(AuditLog(
            user_id=user_id,
            action=action,
            details=details,
            can_rollback=False,
            target_model=target_model,
        ))
    except Exception as exc:  # 审计失败不能拖垮已经成功的导入
        current_app.logger.error('导入审计写入失败：%s', exc)


# ---------------------------------------------------------------- 工价导入

def _price_same(current, fields):
    """当前生效版本与待写入值是否等价（价格用 1e-9 容差，SQLite Float 是双精度）。"""
    for key in ('process_name', 'component', 'drawing_no', 'model_no'):
        if _text(getattr(current, key)) != _text(fields.get(key)):
            return False
    try:
        if abs(float(current.price or 0) - float(fields.get('price') or 0)) > 1e-9:
            return False
    except (TypeError, ValueError):
        return False
    return True


def _current_price(code, price_type):
    return ProcessPrice.query.filter_by(
        process_code=code, price_type=price_type, is_current=True).first()


def _upsert_price(code, price_type, fields, report, kind):
    """按自然键写入工序价格。返回 (记录, 动作)，动作 ∈ created/versioned/unchanged。

    ``kind`` 为报告计数前缀（'normal' / 'subtotal'）。
    """
    current = _current_price(code, price_type)
    if current is not None and _price_same(current, fields):
        report[kind + '_unchanged'] += 1
        return current, 'unchanged'
    if current is not None:
        current.is_current = False
        version = (current.version or 0) + 1
        action = 'versioned'
    else:
        version = 1
        action = 'created'
    record = ProcessPrice(
        process_code=code,
        price_type=price_type,
        version=version,
        is_current=True,
        **fields
    )
    db.session.add(record)
    db.session.flush()
    report[kind + '_' + action] += 1
    return record, action


def _subtotal_members(record):
    """当前小计行已包含的工序编号集合（用于判断「成员没变就不升版」）。"""
    codes = []
    try:
        for link in record.included_processes:
            process = link.process
            if process is not None:
                codes.append(_text(process.process_code))
    except Exception as exc:
        current_app.logger.warning('读取小计成员失败（按「已变化」处理）：%s', exc)
        return None
    return sorted(c for c in codes if c)


def _chunked(values, size=400):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _begin_real_transaction():
    """迫使 SQLite 层真正开启事务（dry_run 能回滚、批量写入是一个事务的前提）。

    CPython 的 ``sqlite3`` 只在 INSERT/UPDATE/DELETE/REPLACE **之前**隐式 ``BEGIN``，
    ``SAVEPOINT`` 不触发它。因此若一条会话事务的第一条 SQL 是 ``SAVEPOINT``（本服务
    每行用 ``db.session.begin_nested()``、``SerialNumber.get_next_number()`` 内部也是），
    SQLite 会把该保存点当成最外层保存点，``RELEASE`` 等价于 ``COMMIT``——
    之后 ``db.session.rollback()`` 再也回滚不掉已写入的行（实测：dry_run 的报告会真落库）。

    这里先执行一条不改变任何数据的 UPDATE（sqlite3 按语句类型判定 DML，`WHERE 1 = 0`
    照样触发隐式 BEGIN），把真事务打开，后续保存点才是嵌套的。
    """
    db.session.execute(sa_text('UPDATE serial_numbers SET current_number = current_number WHERE 1 = 0'))


def import_price_result(result, source_name='', dry_run=False, user_id=None,
                        error_limit=DEFAULT_ERROR_LIMIT, warning_limit=DEFAULT_WARNING_LIMIT):
    """把工价转换器的结果落库（或 dry_run 只统计）。

    :param result: ``AlloySteelPriceConverter.convert_alloy_steel_file`` 的返回值
    :param dry_run: True 时全部写入最后回滚，只返回报告
    :return: 报告 dict（见模块 docstring；``success`` 表示有没有可用行）
    """
    rows = [row for row in (result.get('data') or []) if isinstance(row, dict)]
    default_date = _to_datetime(result.get('effective_date'))
    report = {
        'kind': 'process_price',
        'dry_run': bool(dry_run),
        'source': _text(source_name),
        'total_rows': len(rows),
        'normal_created': 0, 'normal_versioned': 0, 'normal_unchanged': 0,
        'subtotal_created': 0, 'subtotal_versioned': 0, 'subtotal_unchanged': 0,
        'groups_created': 0,
        'error_sheets': list(result.get('error_sheets') or []),
        'source_warnings': list(result.get('warnings') or []),
        'errors': _new_bucket(error_limit),
        'warnings': _new_bucket(warning_limit),
    }

    def row_label(row):
        return '第{0}页 行{1}'.format(_text(row.get('sheet_name')) or '?', row.get('source_row') or '?')

    def warn(message):
        _push(report['warnings'], message)

    def fail(message):
        _push(report['errors'], message)

    def fields_of(row):
        process_name, cut = _clip(row.get('process_name'), NAME_LIMIT)
        if cut:
            warn('{0}：工序名称超过 {1} 字，已截断'.format(row_label(row), NAME_LIMIT))
        component, cut_c = _clip(row.get('component'), TEXT_LIMIT)
        drawing_no, cut_d = _clip(row.get('drawing_no'), TEXT_LIMIT)
        model_no, cut_m = _clip(row.get('model_no'), TEXT_LIMIT)
        if cut_c or cut_d or cut_m:
            warn('{0}：部件/图号/型号超过 {1} 字，已截断'.format(row_label(row), TEXT_LIMIT))
        return {
            'process_name': process_name,
            'component': component,
            'drawing_no': drawing_no,
            'model_no': model_no,
            'notes': _text(row.get('notes')) or None,
            'effective_date': default_date,
        }

    # ---- 第一遍：普通工序
    # 先让 SQLite 真开事务，否则每行的 SAVEPOINT 会退化成 COMMIT，dry_run 也回滚不掉
    try:
        _begin_real_transaction()
    except Exception as exc:
        current_app.logger.warning('无法开启外层事务，将退回逐行提交语义：%s', exc)

    normal_rows = [r for r in rows if _text(r.get('price_type')) != PRICE_TYPE_SUBTOTAL]
    subtotal_rows = [r for r in rows if _text(r.get('price_type')) == PRICE_TYPE_SUBTOTAL]

    for row in normal_rows:
        label = row_label(row)
        code = _text(row.get('process_code'))
        if not code:
            fail('{0}：缺少工序编号，已跳过'.format(label))
            continue
        code, cut = _clip(code, CODE_LIMIT)
        if cut:
            fail('{0}：工序编号超过 {1} 字，已跳过'.format(label, CODE_LIMIT))
            continue
        if not _text(row.get('process_name')):
            fail('{0}：缺少工序名称，已跳过'.format(label))
            continue
        price = row.get('price')
        if price is None or _text(price) == '':
            fail('{0}：缺少单价，已跳过'.format(label))
            continue
        try:
            price = float(price)
        except (TypeError, ValueError):
            fail('{0}：单价「{1}」不是数字，已跳过'.format(label, price))
            continue
        if price < 0:
            fail('{0}：单价 {1} 为负数，已跳过'.format(label, price))
            continue
        try:
            with db.session.begin_nested():
                fields = fields_of(row)
                fields['price'] = price
                _upsert_price(code, PRICE_TYPE_NORMAL, fields, report, 'normal')
        except Exception as exc:
            fail('{0}：写入失败（{1}），已跳过'.format(label, exc))
            current_app.logger.error('导入工序价格失败 %s：%s', label, exc)
    try:
        # 试运行时只 flush：让第二遍的查询能看到第一遍的行，但绝不落盘
        db.session.flush() if dry_run else db.session.commit()
    except Exception as exc:
        db.session.rollback()
        fail('普通工序提交失败（{0}）'.format(exc))
        current_app.logger.error('普通工序提交失败：%s', exc)

    # ---- 第二遍：小计（成员单价只认数据库里的当前版本，与既有端点一致）
    #
    # 源表里「合计」行汇总的是本页各个「小计」编号，所以成员既可能是普通工序、也可能是
    # 更小一级的小计。因此先把所有被引用编号的当前单价解析出来，再按依赖顺序写入：
    # 每写完一条小计，就把它的单价登记进 price_by_code，供上层小计使用。
    needed = set()
    for row in subtotal_rows:
        for code in (row.get('included_processes') or []):
            code = _text(code)
            if code:
                needed.add(code)
    price_by_code = {}
    for chunk in _chunked(sorted(needed)):
        found = ProcessPrice.query.filter(
            ProcessPrice.process_code.in_(chunk),
            ProcessPrice.is_current.is_(True),
        ).all()
        for record in found:
            key = _text(record.process_code)
            # 同一编号若同时存在普通与小计两个当前版本，普通工序优先
            if record.price_type == PRICE_TYPE_NORMAL or key not in price_by_code:
                price_by_code[key] = float(record.price or 0)

    def member_codes(row):
        return [_text(c) for c in (row.get('included_processes') or []) if _text(c)]

    def write_subtotal(row, label, code, fields, members, current):
        total = round(sum(price_by_code[c] for c in members), 4)
        if current is not None and _price_same(current, dict(fields, price=total)) \
                and _subtotal_members(current) == sorted(set(members)):
            report['subtotal_unchanged'] += 1
            price_by_code[code] = float(current.price or total)
            _member_ids.setdefault(code, current.id)
            return
        try:
            with db.session.begin_nested():
                record = ProcessPrice(
                    process_code=code, price_type=PRICE_TYPE_SUBTOTAL,
                    version=((current.version or 0) + 1) if current is not None else 1,
                    is_current=True, **dict(fields, price=total)
                )
                if current is not None:
                    current.is_current = False
                db.session.add(record)
                db.session.flush()
                seen = set()
                for member_code in members:
                    process_id = _member_ids.get(member_code)
                    if process_id is None:
                        raise ValueError('成员「{0}」没有可用记录'.format(member_code))
                    if process_id in seen:
                        continue
                    seen.add(process_id)
                    db.session.add(ProcessPriceGroup(subtotal_id=record.id, process_id=process_id))
                    report['groups_created'] += 1
        except Exception as exc:
            fail('{0}：小计写入失败（{1}），已跳过'.format(label, exc))
            current_app.logger.error('导入小计失败 %s：%s', label, exc)
            return
        report['subtotal_versioned' if current is not None else 'subtotal_created'] += 1
        price_by_code[code] = total
        _member_ids[code] = record.id

    # 成员的主键 id：普通工序来自库里，小计在写入时就地登记
    _member_ids = {}
    for chunk in _chunked(sorted(needed)):
        for record in ProcessPrice.query.filter(
                ProcessPrice.process_code.in_(chunk),
                ProcessPrice.is_current.is_(True)).all():
            _member_ids.setdefault(_text(record.process_code), record.id)

    # 预校验：编号/名称/成员齐全才进依赖排序队列
    candidates = []
    for row in subtotal_rows:
        label = row_label(row)
        code = _text(row.get('process_code'))
        if not code:
            fail('{0}：小计缺少工序编号，已跳过'.format(label))
            continue
        code, cut = _clip(code, CODE_LIMIT)
        if cut:
            fail('{0}：小计工序编号超过 {1} 字，已跳过'.format(label, CODE_LIMIT))
            continue
        if not _text(row.get('process_name')):
            fail('{0}：小计缺少工序名称，已跳过'.format(label))
            continue
        members = member_codes(row)
        if not members:
            fail('{0}：小计没有「包含工序」，已跳过'.format(label))
            continue
        candidates.append((row, label, code, members))

    pending = candidates
    while pending:
        deferred = []
        for row, label, code, members in pending:
            if any(c not in price_by_code for c in members):
                deferred.append((row, label, code, members))
                continue
            write_subtotal(row, label, code, fields_of(row), members,
                           _current_price(code, PRICE_TYPE_SUBTOTAL))
        if not deferred:
            break
        if len(deferred) == len(pending):
            # 再排也排不出来：成员确实在系统里找不到（含环状引用）
            for row, label, code, members in deferred:
                missing = [c for c in members if c not in price_by_code]
                fail('{0}：小计引用的工序编号在系统中不存在（{1}），已跳过'.format(
                    label, '、'.join(missing[:5]) + ('…' if len(missing) > 5 else '')))
            break
        pending = deferred

    # ---- 收尾
    usable = (report['normal_created'] + report['normal_versioned'] + report['normal_unchanged']
              + report['subtotal_created'] + report['subtotal_versioned'] + report['subtotal_unchanged'])
    report['success'] = bool(usable)
    if dry_run:
        db.session.rollback()
        report['message'] = '试运行完成（未写入数据库）：可导入 {0} 条，错误 {1} 条'.format(
            usable, report['errors']['count'])
        return report

    try:
        if usable:
            _log_import(
                '导入合金钢辙叉计件工价标准',
                '来源 {0}；总行数 {1}；新增普通 {2}、升版 {3}、未变 {4}；'
                '新增小计 {5}、升版 {6}、未变 {7}；小计成员 {8} 条；跳过/错误 {9} 条'.format(
                    report['source'] or '(上传文件)', report['total_rows'],
                    report['normal_created'], report['normal_versioned'], report['normal_unchanged'],
                    report['subtotal_created'], report['subtotal_versioned'], report['subtotal_unchanged'],
                    report['groups_created'], report['errors']['count']),
                user_id, 'ProcessPrice')
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        report['success'] = False
        report['message'] = '提交失败，已回滚：{0}'.format(exc)
        current_app.logger.error('工序价格导入提交失败：%s', exc)
        return report

    report['message'] = '导入完成：可导入 {0} 条，错误 {1} 条'.format(usable, report['errors']['count'])
    return report


# ---------------------------------------------------------------- BOM 导入

def _allocate_product_code(base, taken):
    """在 ``taken``（已占用编号集合）之外分配一个唯一产品编号。"""
    code = _make_code(base) or 'BOM-PART'
    candidate = code
    seq = 1
    while candidate in taken:
        seq += 1
        suffix = '-{0}'.format(seq)
        candidate = code[:CODE_LIMIT - len(suffix)] + suffix
        if seq > 500:
            raise ValueError('无法为「{0}」分配唯一产品编号'.format(base))
    return candidate


def _child_key(row):
    """子件键优先级：图号 → 代码 → 名称。返回 (键, 是否只靠名称)。"""
    for field in ('drawing_no', 'code'):
        value = _text(row.get(field))
        if value:
            return value, False
    return _text(row.get('name')), True


def _child_specification(entry):
    """把源表里的 材料/单重/总重 拼进子件「规格说明」（Product.specification 是 Text）。"""
    parts = []
    if entry.get('material'):
        parts.append('材料：{0}'.format(entry['material']))
    if entry.get('unit_weight') is not None:
        parts.append('单重：{0}kg'.format(entry['unit_weight']))
    if entry.get('total_weight') is not None:
        parts.append('总重：{0}kg'.format(entry['total_weight']))
    return '；'.join(parts) or None


def import_bom_result(result, source_name='', dry_run=False, replace_existing=True, user_id=None,
                      error_limit=DEFAULT_ERROR_LIMIT, warning_limit=DEFAULT_WARNING_LIMIT,
                      max_examples=20):
    """把 BOM 转换器的结果落库（或 dry_run 只统计）。

    :param result: ``AlloySteelBomConverter.convert_bom_folder``/``convert_bom_files`` 的返回值
    :param replace_existing: True 时先删掉这些父件已有的 ``material_type='product'`` 明细再写入
        （保证重复导入幂等）；False 时只追加。**只删 product 类型**，操作员手工加的
        raw/finished 明细不受影响。
    :param dry_run: True 时全部写入最后回滚，只返回报告
    """
    rows = [row for row in (result.get('data') or []) if isinstance(row, dict)]
    parents_in = list(result.get('parents') or [])
    report = {
        'kind': 'product_bom',
        'dry_run': bool(dry_run),
        'source': _text(source_name),
        'replace_existing': bool(replace_existing),
        'total_rows': len(rows),
        'file_count': result.get('file_count') or 0,
        'sheet_count': result.get('sheet_count') or 0,
        'parents_total': 0, 'parents_created': 0, 'parents_reused': 0,
        'children_total': 0, 'children_created': 0, 'children_reused': 0,
        'bom_rows_created': 0, 'bom_rows_removed': 0, 'bom_rows_merged': 0,
        'rows_without_key': 0,
        'key_conflicts': [],
        'error_sheets': list(result.get('error_sheets') or []),
        'source_warnings': list(result.get('warnings') or []),
        'errors': _new_bucket(error_limit),
        'warnings': _new_bucket(warning_limit),
    }

    if not rows:
        report['success'] = False
        report['message'] = '没有可导入的 BOM 明细行'
        if dry_run:
            db.session.rollback()
        return report

    # 先让 SQLite 真开事务，否则每行的 SAVEPOINT 会退化成 COMMIT，dry_run 也回滚不掉
    try:
        _begin_real_transaction()
    except Exception as exc:
        current_app.logger.warning('无法开启外层事务，将退回逐行提交语义：%s', exc)

    # 现有产品索引（按图号、按编号各一份），新增产品即时回填，避免逐行查库
    by_drawing = {}
    by_code = {}
    for product in Product.query.all():
        drawing = _text(product.drawing_number)
        if drawing:
            by_drawing.setdefault(drawing, product)
        code = _text(product.product_code)
        if code:
            by_code.setdefault(code, product)
    taken_codes = set(by_code)

    def resolve(key, is_parent, defaults, provenance):
        key = _text(key)
        if not key:
            return None
        product = by_drawing.get(key) or by_code.get(key)
        if product is not None:
            if is_parent:
                report['parents_reused'] += 1
            else:
                report['children_reused'] += 1
            return product
        code = _allocate_product_code(key, taken_codes)
        taken_codes.add(code)
        product = Product(
            product_code=code,
            product_name=defaults['product_name'] or key,
            drawing_number=defaults.get('drawing_number') or None,
            specification=defaults.get('specification'),
            unit=defaults.get('unit') or '件',
            category=PARENT_CATEGORY if is_parent else CHILD_CATEGORY,
            notes=provenance,
            status='active',
        )
        db.session.add(product)
        db.session.flush()
        by_drawing.setdefault(key, product)
        by_code.setdefault(code, product)
        if is_parent:
            report['parents_created'] += 1
        else:
            report['children_created'] += 1
        return product

    # ---- 父件（按转换器给的 parents 顺序；编号与明细行 parent_drawing 一致）
    parent_by_drawing = {}
    for parent in parents_in:
        drawing = _text(parent.get('parent_drawing'))
        if not drawing:
            continue
        provenance = '由「48页表格」BOM 导入：{0}'.format(_text(parent.get('file_name')))
        product = resolve(
            drawing, True,
            {'product_name': _text(parent.get('parent_model')) or drawing,
             'drawing_number': drawing,
             'unit': '组'},
            provenance)
        if product is not None:
            parent_by_drawing[drawing] = product

    # ---- 明细行分组 + 子件
    # group[parent_drawing][child_key] = entry
    groups = {}
    parent_order = []
    child_keys = set()
    for row in rows:
        parent_drawing = _text(row.get('parent_drawing'))
        if not parent_drawing:
            _push(report['errors'], '第{0}页 行{1}：明细行没有父件图号，已跳过'.format(
                _text(row.get('file_name')), row.get('source_row')))
            continue
        key, by_name_only = _child_key(row)
        if not key:
            _push(report['errors'], '{0} 第{1}行（{2}）：图号/代码/名称全为空，已跳过'.format(
                _text(row.get('file_name')), row.get('source_row'), _text(row.get('name'))))
            continue
        if by_name_only:
            report['rows_without_key'] += 1
        child_keys.add(key)
        child = resolve(
            key, False,
            {'product_name': _text(row.get('name')) or key,
             'drawing_number': _text(row.get('drawing_no')) or None,
             'unit': _text(row.get('unit')) or '件',
             'specification': _child_specification({
                 'material': _text(row.get('material')),
                 'unit_weight': row.get('unit_weight'),
                 'total_weight': row.get('total_weight'),
             })},
            '由「48页表格」BOM 导入：{0} 工作表 {1} 第{2}行'.format(
                _text(row.get('file_name')), _text(row.get('sheet_name')), row.get('source_row')))
        if child is None:
            continue
        if parent_drawing not in groups:
            groups[parent_drawing] = {}
            parent_order.append(parent_drawing)
        bucket = groups[parent_drawing]
        entry = bucket.get(key)
        if entry is None:
            bucket[key] = {
                'child': child,
                'key': key,
                'name': _text(row.get('name')),
                'quantity': 0.0,
                'quantity_missing': False,
                'unit': _text(row.get('unit')),
                'units': set(),
                'notes': [],
                'sequence': _extract_sequence(row),
                'occurrences': 0,
                'material': _text(row.get('material')),
            }
            entry = bucket[key]
        entry['occurrences'] += 1
        quantity = row.get('quantity')
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            entry['quantity_missing'] = True
            quantity = 0.0
        entry['quantity'] += quantity
        unit = _text(row.get('unit'))
        if unit:
            entry['units'].add(unit)
            if not entry['unit']:
                entry['unit'] = unit
        note = _text(row.get('notes'))
        if note and note not in entry['notes']:
            entry['notes'].append(note)

    # ---- 写 ProductBOM
    for parent_drawing in parent_order:
        parent = parent_by_drawing.get(parent_drawing)
        if parent is None:
            _push(report['errors'], '父件「{0}」没有对应的产品记录，其 {1} 个子件已跳过'.format(
                parent_drawing, len(groups[parent_drawing])))
            continue
        bucket = groups[parent_drawing]
        try:
            with db.session.begin_nested():
                if replace_existing:
                    removed = ProductBOM.query.filter_by(
                        product_id=parent.id, material_type='product').delete(synchronize_session=False)
                    report['bom_rows_removed'] += int(removed or 0)
                for entry in bucket.values():
                    if entry['occurrences'] > 1:
                        report['bom_rows_merged'] += 1
                    if len(entry['units']) > 1:
                        _push(report['warnings'], '父件「{0}」子件「{1}」的单位有多个取值（{2}），取「{3}」'.format(
                            parent_drawing, entry['key'], '、'.join(sorted(entry['units'])), entry['unit'] or '件'))
                    bom = ProductBOM(
                        product_id=parent.id,
                        material_type='product',
                        material_id=entry['child'].id,
                        quantity=entry['quantity'],
                        unit=entry['unit'] or '件',
                        unit_cost=0,
                        waste_rate=0,
                        notes='；'.join(entry['notes']) or None,
                        sequence=entry['sequence'],
                    )
                    db.session.add(bom)
                    report['bom_rows_created'] += 1
        except Exception as exc:
            # 该父件的 SAVEPOINT 已随异常自动回滚，session 仍可用；不整体 rollback
            _push(report['errors'], '父件「{0}」写入 BOM 失败（{1}），已跳过该父件'.format(parent_drawing, exc))
            current_app.logger.error('导入 BOM 失败 %s：%s', parent_drawing, exc)

    report['parents_total'] = len(parent_by_drawing)
    report['children_total'] = len(child_keys)
    report['key_conflicts'] = _collect_key_conflicts(rows, max_examples)
    report['success'] = bool(report['bom_rows_created'])

    if dry_run:
        db.session.rollback()
        report['message'] = '试运行完成（未写入数据库）：父件 {0} 个、子件 {1} 个、BOM 明细 {2} 条'.format(
            report['parents_total'], report['children_total'], report['bom_rows_created'])
        return report

    try:
        if report['success']:
            _log_import(
                '导入合金钢辙叉 48页表格 BOM',
                '来源 {0}；文件 {1} 个工作表 {2} 个；明细行 {3}；父件 {4}（新增 {5}）；'
                '子件 {6}（新增 {7}）；写入 BOM {8} 条（覆盖删除 {9} 条，合并重复 {10} 条）；错误 {11} 条'.format(
                    report['source'] or '(上传文件)', report['file_count'], report['sheet_count'],
                    report['total_rows'], report['parents_total'], report['parents_created'],
                    report['children_total'], report['children_created'], report['bom_rows_created'],
                    report['bom_rows_removed'], report['bom_rows_merged'], report['errors']['count']),
                user_id, 'ProductBOM')
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        report['success'] = False
        report['message'] = '提交失败，已回滚：{0}'.format(exc)
        current_app.logger.error('BOM 导入提交失败：%s', exc)
        return report

    report['message'] = '导入完成：父件 {0} 个、子件 {1} 个、BOM 明细 {2} 条'.format(
        report['parents_total'], report['children_total'], report['bom_rows_created'])
    return report


def _extract_sequence(row):
    """把源表「序号」折成 int 排序号（不是数字时退回 0）。"""
    text = _text(row.get('seq_text')) or _text(row.get('seq'))
    match = re.search(r'\d+', text or '')
    if not match:
        return 0
    try:
        return int(match.group(0))
    except ValueError:
        return 0


def _collect_key_conflicts(rows, max_examples):
    """同一子件键在不同行带着不同名称/材料 → 进报告供人工复核（不自动合并、不改正）。"""
    names = {}
    materials = {}
    for row in rows:
        key, _ = _child_key(row)
        if not key:
            continue
        name = _text(row.get('name'))
        material = _text(row.get('material'))
        if name:
            names.setdefault(key, set()).add(name)
        if material:
            materials.setdefault(key, set()).add(material)
    conflicts = []
    for key in sorted(names):
        if len(names[key]) > 1:
            conflicts.append({'key': key, 'field': '名称', 'values': sorted(names[key])})
    for key in sorted(materials):
        if len(materials[key]) > 1:
            conflicts.append({'key': key, 'field': '材料', 'values': sorted(materials[key])})
    conflicts.sort(key=lambda item: (-len(item['values']), item['key']))
    return conflicts[:max_examples]
