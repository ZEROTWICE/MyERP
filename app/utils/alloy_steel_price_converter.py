# -*- coding: utf-8 -*-
"""合金钢辙叉计件工价标准转换器。

把《合金钢辙叉计件工价标准.xlsx》转换成可批量写入 `process_price` 表的工序价格行。

数据源版式（每页一个型号/图号）::

    行1  易亨公司 合金钢组合辙叉 计件工价 明细表-NN
    行2  型号：50kg/m钢轨9号   图号：CZ2209-I    金额：854元/组
    行3  序号 | 型号 | 图号 | 部件名称 | 工序名称 | 单价 | 备注
    行4+ 明细行；部件名称 为「小计」/「合计」的行是汇总行

已知例外（数据源本身有问题，一律容错 + 记入 warnings，不猜测修正）：
* ``16-精加工心轨``：两个单价列（``60-12 单价`` / ``60-9 单价``），
  数据行的 型号/图号 为空，需回填行2 的 ``型号：A / B`` 与 ``图号：X / Y``（按位置配对）。
* ``46-其它项目``：表头是 ``序号|工序名称|图号|规格 型号|单位|单价|备注``，没有「部件名称」列。
* ``72-补漏项``：行2 没有型号/图号/金额，每一行自带 图号；含没有单价的说明行。
* 部分页 行2 的图号 与 数据行图号 不一致（如 ``59`` 行2 写 专线4228-IV、数据行写 专线4249-IV；
  ``67`` 行2 写 研线1612HC-I、数据行写 16121HC-I）。本转换器**以数据行图号为业务值**，
  并把不一致写入 warnings 与行备注，不做猜测性修正。

与旧的 `工具/工价转换.py` 的关键差异：
* 工序编号由「型号+图号+部件+工序名称」的确定性摘要生成，
  同一逻辑工序在不同页出现时得到**同一个**编号（导入时自动升版本），
  不同逻辑工序不会撞码（旧脚本 01/65、04/64、50/63 会撞码导致整批拒绝）；
* 只产出内存数据结构，不写任何文件；
* 逐页/逐行容错，异常进 ``error_sheets`` / ``warnings``，不会整体失败。
"""

import hashlib
import re
from datetime import date, datetime

from openpyxl import load_workbook

ROMAN_MAP = {
    'Ⅰ': 'I', 'Ⅱ': 'II', 'Ⅲ': 'III', 'Ⅳ': 'IV', 'Ⅴ': 'V', 'Ⅵ': 'VI',
    'Ⅶ': 'VII', 'Ⅷ': 'VIII', 'Ⅸ': 'IX', 'Ⅹ': 'X',
    'ⅰ': 'i', 'ⅱ': 'ii', 'ⅲ': 'iii', 'ⅳ': 'iv', 'ⅴ': 'v',
    'Ｉ': 'I', 'ＩＩ': 'II', 'Ｖ': 'V', 'Ｘ': 'X',
}

_FOOTER_RE = re.compile(r'^\s*(编制|审核|批准|制表|校核|整理|日期)\s*[：:]')
_LABEL_RE = re.compile(r'(型号|图号|金额)\s*[：:]')
_AMOUNT_RE = re.compile(r'([0-9]+(?:\.[0-9]+)?)')
_CN_DATE_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')

PROCESS_CODE_PREFIX = 'YHGH'
PROCESS_CODE_DRAWING_MAX = 14
PROCESS_CODE_DIGEST_LEN = 6


def _text(value):
    """单元格值 → 去首尾空白的字符串（None → ''）。"""
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def normalize_key_part(value):
    """归一化业务键片段：折叠罗马数字、去掉空白与标点、统一大小写。"""
    text = _text(value)
    if not text:
        return ''
    for src, dst in ROMAN_MAP.items():
        text = text.replace(src, dst)
    text = re.sub(r'[\s\u3000]+', '', text)
    text = re.sub(r'[·・、,，。．\.]+', '', text)
    return text.upper()


def clean_code_segment(value, max_len=PROCESS_CODE_DRAWING_MAX):
    """生成可用于工序编号的片段：保留字母数字、连字符与中文。

    ``/`` 与 ``_`` 归一成 ``-``（如 46 页图号「50、60kg/m各型」），并折叠连续
    连字符，避免出现 ``YHGH5060KG/M各型-FACDA6`` 这类带分隔符的编号。
    """
    text = normalize_key_part(value)
    text = re.sub(r'[^0-9A-Z\u4e00-\u9fff\-_/]', '', text)
    text = text.replace('/', '-').replace('_', '-')
    text = re.sub(r'-{2,}', '-', text).strip('-')
    return text[:max_len]


def _unique(values):
    """保序去重。"""
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def generate_process_code(model_no, drawing_no, component, process_name, extra=''):
    """由业务自然键生成确定性工序编号。

    同一 (型号, 图号, 部件, 工序名称) 永远得到同一个编号，因此：
    * 不同页出现同一道工序 → 同编号 → 导入时自动升版本（旧版 is_current=False）；
    * 不同工序（哪怕同图号同部件）→ 摘要不同 → 不会撞码。

    ``extra`` 供「小计/合计」行使用：同一页可能有两个同名汇总行（如 41 页两个
    「间隔铁加工费用小计」，一个汇总 3 道工序、一个汇总 1 道），把所包含的工序
    编号集合并入摘要，二者才会得到不同编号，否则会互相覆盖。
    """
    key = '|'.join(normalize_key_part(x) for x in (model_no, drawing_no, component, process_name))
    if extra:
        key = key + '#' + extra
    digest = hashlib.md5(key.encode('utf-8')).hexdigest()[:PROCESS_CODE_DIGEST_LEN].upper()
    segment = clean_code_segment(drawing_no) or 'X'
    return '{0}{1}-{2}'.format(PROCESS_CODE_PREFIX, segment, digest)


def _to_float(value):
    """宽松解析数值；无法解析返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = _text(value)
    if not text:
        return None
    match = re.search(r'-?\d+(?:\.\d+)?', text.replace(',', ''))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _split_slash(value):
    """按 `/` 分割并去空白，保留原始顺序（用于 行2 的多型号/多图号）。"""
    text = _text(value)
    if not text:
        return []
    return [part.strip() for part in text.split('/') if part.strip()]


def _parse_meta_row(cells):
    """解析行2 ``型号：.. 图号：.. 金额：..``，返回 (models, drawings, amount, raw)。"""
    raw = _text(cells[0]) if cells else ''
    if not raw:
        raw = ' '.join(_text(c) for c in cells if _text(c))
    labels = list(_LABEL_RE.finditer(raw))
    values = {}
    for idx, match in enumerate(labels):
        start = match.end()
        end = labels[idx + 1].start() if idx + 1 < len(labels) else len(raw)
        values[match.group(1)] = raw[start:end].strip()
    models = _split_slash(values.get('型号', ''))
    drawings = _split_slash(values.get('图号', ''))
    amount_text = values.get('金额', '')
    amount_match = _AMOUNT_RE.search(amount_text.replace(',', ''))
    amount = float(amount_match.group(1)) if amount_match else None
    return models, drawings, amount, raw


class AlloySteelPriceConverter(object):
    """《合金钢辙叉计件工价标准.xlsx》转换器（全部静态方法）。"""

    @staticmethod
    def chinese_to_pinyin_initial(text):
        """中文取拼音首字母；未安装 pypinyin 时原样返回。"""
        if not text:
            return ''
        try:
            from pypinyin import Style, lazy_pinyin
        except Exception:
            return text
        try:
            return ''.join(lazy_pinyin(str(text), style=Style.FIRST_LETTER))
        except Exception:
            return text

    @staticmethod
    def clean_code_string(text):
        """兼容旧脚本的清洗函数：去除非词字符，中文取拼音首字母。"""
        if not text:
            return ''
        cleaned = re.sub(r'[^\w\u4e00-\u9fff]', '', str(text))
        return ''.join(
            AlloySteelPriceConverter.chinese_to_pinyin_initial(ch)
            if re.match(r'[\u4e00-\u9fff]', ch) else ch
            for ch in cleaned
        )

    @staticmethod
    def split_by_slash(text):
        return _split_slash(text)

    @staticmethod
    def get_cell_value(cell, formula_cell=None):
        """读取单元格值；公式单元格优先取缓存结果。"""
        if cell is None:
            return None
        value = getattr(cell, 'value', cell)
        if getattr(cell, 'data_type', None) == 'f' and formula_cell is not None:
            cached = getattr(formula_cell, 'value', None)
            if cached is not None:
                return cached
        return value

    @staticmethod
    def generate_process_code(model_no, drawing_no, component, process_name, extra=''):
        return generate_process_code(model_no, drawing_no, component, process_name, extra)

    # ------------------------------------------------------------------ #
    # 内部解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_values(ws, row_idx, max_col):
        return [ws.cell(row=row_idx, column=c).value for c in range(1, max_col + 1)]

    @staticmethod
    def _find_header_row(ws, max_col):
        """定位表头行：同时含 序号、工序名称(或工序)、单价；取最后一个匹配行。"""
        found = None
        for row_idx in range(1, min(ws.max_row, 12) + 1):
            texts = [_text(v) for v in AlloySteelPriceConverter._row_values(ws, row_idx, max_col)]
            joined = ' '.join(texts)
            has_seq = any(re.fullmatch(r'序号', t) for t in texts)
            has_step = '工序' in joined
            has_price = '单价' in joined or '价格' in joined
            if has_seq and has_step and has_price:
                found = row_idx
        return found

    @staticmethod
    def _map_columns(header_cells):
        """表头 → 列号映射；单价列可能有多个（如 60-12 单价 / 60-9 单价）。"""
        cols = {'序号': None, '型号': None, '图号': None, '部件': None, '工序': None, '备注': None}
        price_cols = []
        for col_idx, raw in enumerate(header_cells, 1):
            text = _text(raw)
            flat = re.sub(r'[\s\u3000]+', '', text)
            if not flat:
                continue
            if flat in ('序号', '序'):
                cols['序号'] = cols['序号'] or col_idx
            elif '备注' in flat:
                cols['备注'] = cols['备注'] or col_idx
            elif '部件' in flat:
                cols['部件'] = cols['部件'] or col_idx
            elif '工序' in flat:
                cols['工序'] = cols['工序'] or col_idx
            elif '图号' in flat:
                cols['图号'] = cols['图号'] or col_idx
            elif '型号' in flat or '规格' in flat:
                cols['型号'] = cols['型号'] or col_idx
            elif '单价' in flat or flat == '价格':
                hint = re.sub(r'(单价|价格)', '', flat).strip() or None
                price_cols.append((col_idx, hint))
        return cols, price_cols

    @staticmethod
    def _detect_effective_date(wb):
        """从 00-工价目录 的页脚解析整理日期，取不到用今天。"""
        for sheet_name in wb.sheetnames:
            if not sheet_name.startswith('00'):
                continue
            ws = wb[sheet_name]
            for row_idx in range(1, ws.max_row + 1):
                for col_idx in range(1, min(ws.max_column, 12) + 1):
                    text = _text(ws.cell(row=row_idx, column=col_idx).value)
                    if not text or '日期' not in text:
                        continue
                    match = _CN_DATE_RE.search(text)
                    if match:
                        try:
                            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                        except ValueError:
                            continue
        return datetime.utcnow().date()

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #
    @staticmethod
    def convert_alloy_steel_file(file_path):
        """解析工价标准工作簿，返回导入用数据结构。"""
        result = {
            'success': False,
            'message': '',
            'data': [],
            'error_sheets': [],
            'warnings': [],
            'total_count': 0,
            'error_count': 0,
            'sheet_count': 0,
            'effective_date': None,
            'declared_total': None,
            'computed_total': None,
        }
        try:
            wb = load_workbook(file_path, data_only=True)
        except Exception as first_error:
            try:
                wb = load_workbook(file_path)
            except Exception as second_error:
                result['message'] = '文件格式不受支持或文件已损坏：{0}（{1}）'.format(
                    first_error, second_error)
                return result

        effective_date = AlloySteelPriceConverter._detect_effective_date(wb)
        result['effective_date'] = effective_date

        data_rows = []
        warnings = result['warnings']
        declared_total = 0.0
        has_declared = False
        computed_total = 0.0

        for sheet_name in wb.sheetnames:
            if sheet_name.startswith('00'):
                continue
            ws = wb[sheet_name]
            max_col = min(ws.max_column or 1, 30)
            header_row = AlloySteelPriceConverter._find_header_row(ws, max_col)
            if not header_row:
                result['error_sheets'].append({
                    'sheet_name': sheet_name,
                    'error_type': '未找到表头行',
                    'detail': '未找到同时包含 序号/工序名称/单价 的表头行',
                })
                continue

            header_cells = AlloySteelPriceConverter._row_values(ws, header_row, max_col)
            cols, price_cols = AlloySteelPriceConverter._map_columns(header_cells)
            if cols['工序'] is None:
                result['error_sheets'].append({
                    'sheet_name': sheet_name,
                    'error_type': '未找到必要的列',
                    'detail': '缺少「工序名称」列',
                })
                continue
            if not price_cols:
                result['error_sheets'].append({
                    'sheet_name': sheet_name,
                    'error_type': '未找到必要的列',
                    'detail': '缺少「单价」列',
                })
                continue

            meta_models, meta_drawings, meta_amount, meta_raw = _parse_meta_row(
                AlloySteelPriceConverter._row_values(ws, 2, max_col) if ws.max_row >= 2 else []
            )
            if meta_amount is not None:
                declared_total += meta_amount
                has_declared = True

            result['sheet_count'] += 1
            sheet_rows = AlloySteelPriceConverter._parse_sheet(
                ws, sheet_name, header_row, cols, price_cols,
                meta_models, meta_drawings, effective_date, warnings,
            )
            if not sheet_rows:
                result['error_sheets'].append({
                    'sheet_name': sheet_name,
                    'error_type': '没有可导入的明细行',
                    'detail': meta_raw or '',
                })
                continue
            data_rows.extend(sheet_rows)
            computed_total += sum(
                r['price'] for r in sheet_rows if r['price_type'] == 'normal' and r['price']
            )

        # 批次内去重：同编号保留最后一条（后出现的页覆盖先出现的页）
        if data_rows:
            data_rows, dedup_warnings = AlloySteelPriceConverter._dedup_rows(data_rows)
            warnings.extend(dedup_warnings)
            warnings.extend(AlloySteelPriceConverter._suspect_model_typos(data_rows))

        result['data'] = data_rows
        result['total_count'] = len(data_rows)
        result['error_count'] = len(result['error_sheets'])
        result['declared_total'] = round(declared_total, 2) if has_declared else None
        result['computed_total'] = round(computed_total, 2) if computed_total else None
        result['success'] = bool(data_rows)

        if not data_rows:
            message_parts = ['未解析到任何可导入的工序价格行']
            if result['error_sheets']:
                message_parts.append('；'.join(
                    '{0}（{1}）'.format(e['sheet_name'], e['error_type'])
                    for e in result['error_sheets'][:10]
                ))
            result['message'] = '：'.join(message_parts)

        return result

    @staticmethod
    def _parse_sheet(ws, sheet_name, header_row, cols, price_cols,
                     meta_models, meta_drawings, effective_date, warnings):
        """解析单个数据页，返回工序价格行列表。"""
        max_col = min(ws.max_column or 1, 30)
        multi_price = len(price_cols) > 1

        # 价格列 → (型号, 图号) 变体
        variants = []
        for col_idx, hint in price_cols:
            model_hint = hint
            drawing_hint = None
            if model_hint and meta_models:
                key_model = normalize_key_part(model_hint)
                for idx, meta_model in enumerate(meta_models):
                    if normalize_key_part(meta_model) == key_model:
                        if idx < len(meta_drawings):
                            drawing_hint = meta_drawings[idx]
                        break
            variants.append({
                'price_col': col_idx,
                'model': model_hint,
                'drawing': drawing_hint,
            })
        if not multi_price and variants:
            # 单一单价列：型号/图号 回填行2 的首个取值
            if not variants[0]['model'] and meta_models:
                variants[0]['model'] = meta_models[0]
            if not variants[0]['drawing']:
                variants[0]['drawing'] = meta_drawings[0] if meta_drawings else None

        rows = []
        for variant in variants:
            rows.extend(AlloySteelPriceConverter._parse_variant(
                ws, sheet_name, header_row, cols, variant, meta_models, meta_drawings,
                max_col, effective_date, warnings,
            ))
        return rows

    @staticmethod
    def _parse_variant(ws, sheet_name, header_row, cols, variant, meta_models,
                       meta_drawings, max_col, effective_date, warnings):
        """按一个单价列变体扫描明细行，生成工序价格行（含小计/合计汇总）。"""
        price_col = variant['price_col']

        def cell(row_values, key):
            col_idx = cols.get(key)
            if not col_idx or col_idx > len(row_values):
                return None
            return row_values[col_idx - 1]

        raw_rows = []
        for row_idx in range(header_row + 1, ws.max_row + 1):
            values = AlloySteelPriceConverter._row_values(ws, row_idx, max_col)
            texts = [_text(v) for v in values]
            # 页内重复出现的表头行（如 43/45 页在第 16 行重排一次表头）不是明细行
            if any(t == '序号' for t in texts) and any('单价' in t for t in texts):
                continue
            process_name = _text(cell(values, '工序'))
            component = _text(cell(values, '部件'))
            if not process_name:
                if component and ('小计' in component or '合计' in component):
                    process_name = component
                else:
                    # 46 页行12/行15 这类「上一行的补充说明行」：名称与图号为空，
                    # 只带一个单价与说明备注（如「自制扣板：铣削25，钻孔5」）。
                    # 归属哪个工序属于人为判断，这里只跳过并把单价与备注留在告警里。
                    skip_price = _to_float(values[price_col - 1]) if price_col <= len(values) else None
                    skip_notes = _text(cell(values, '备注'))
                    if skip_price is None and not skip_notes:
                        # 空白行与页脚行（「编制：」「日期：」等）不产生告警
                        continue
                    warnings.append(
                        '第{0}页 行{1} 没有工序名称（单价 {2}，备注：{3}），已跳过'.format(
                            sheet_name, row_idx,
                            '空' if skip_price is None else skip_price,
                            skip_notes or '无')
                    )
                    continue
            variant_model = variant.get('model')
            row_model = _text(cell(values, '型号'))
            row_drawing = _text(cell(values, '图号'))
            model_no = row_model or variant_model or (meta_models[0] if meta_models else '')
            drawing_no = row_drawing or variant.get('drawing') or ''
            if not drawing_no and meta_drawings:
                drawing_no = meta_drawings[0]
            notes = _text(cell(values, '备注'))
            price = _to_float(values[price_col - 1]) if price_col <= len(values) else None
            raw_rows.append({
                'row_idx': row_idx,
                'model_no': model_no,
                'drawing_no': drawing_no,
                'component': component,
                'process_name': process_name,
                'price': price,
                'notes': notes,
                'is_subtotal': ('小计' in component) or ('合计' in component),
                'is_total': '合计' in component,
            })

        rows = []
        rows_by_code = {}
        block_codes = []              # 当前汇总块（自上一汇总行以来的明细编号）
        block_components = []
        subtotal_codes_by_model = {}  # model -> [code]
        all_normal_codes = {}         # model -> [code]
        code_index = {}

        for item in raw_rows:
            model_no = item['model_no']
            component = item['component'] or '未分类'
            code = generate_process_code(model_no, item['drawing_no'], component, item['process_name'])
            if len(code) > 50:
                code = code[:50]

            if not item['is_subtotal']:
                if item['price'] is None:
                    warnings.append(
                        '第{0}页 行{1}（{2}/{3}）没有单价，已跳过'.format(
                            sheet_name, item['row_idx'], component, item['process_name'])
                    )
                    continue
                if code in code_index:
                    warnings.append(
                        '第{0}页 行{1} 与行{2} 的工序编号相同（{3}），保留后者'.format(
                            sheet_name, code_index[code], item['row_idx'], code)
                    )
                code_index[code] = item['row_idx']
                block_codes.append(code)
                block_components.append(component)
                all_normal_codes.setdefault(model_no, []).append(code)
                rows_by_code[code] = {
                    'process_code': code,
                    'process_name': item['process_name'][:100],
                    'component': component[:100],
                    'drawing_no': item['drawing_no'][:100],
                    'model_no': model_no[:100],
                    'price': item['price'],
                    'notes': item['notes'] or None,
                    'price_type': 'normal',
                    'included_processes': None,
                    'sheet_name': sheet_name,
                    'source_row': item['row_idx'],
                }
                rows.append(rows_by_code[code])
                continue

            # 汇总行：小计汇总「自上一汇总行以来的连续明细块」——数据源就是这样排版的，
            # 不能按部件名匹配（同一部件名会在页内出现多个互不相属的块，如 39 页
            # 「辙叉垫板」既有辙叉组装块也有垫板加工块）。
            if item['is_total']:
                recorded_subtotals = _unique(subtotal_codes_by_model.get(model_no) or [])
                open_block = _unique(block_codes)
                if recorded_subtotals and open_block:
                    # 页末合计：已收口的块用其小计，尚未收口的块直接取明细
                    included = recorded_subtotals + open_block
                elif recorded_subtotals:
                    included = recorded_subtotals
                elif open_block:
                    # 43/45 这类「每块各自合计、块间重排表头」的页
                    included = open_block
                else:
                    included = _unique(all_normal_codes.get(model_no) or [])
                sub_component = component
            else:
                included = _unique(block_codes)
                sub_component = block_components[-1] if block_components else '小计'

            # 同名汇总行在不同块上出现时，把内容并入摘要，保证各自独立成行
            if included:
                code = generate_process_code(
                    model_no, item['drawing_no'], sub_component, item['process_name'],
                    extra=','.join(sorted(included)),
                )
                if len(code) > 50:
                    code = code[:50]

            block_codes = []
            block_components = []

            if not included:
                warnings.append(
                    '第{0}页 行{1}（{2}）没有可关联的明细工序，已跳过'.format(
                        sheet_name, item['row_idx'], item['process_name'])
                )
                continue

            computed = round(sum(
                (rows_by_code[c]['price'] or 0.0) for c in included if c in rows_by_code
            ), 2)
            declared = item['price']
            if declared is not None and abs(declared - computed) > 1.0:
                warnings.append(
                    '第{0}页 行{1}（{2}）表内单价 {3} 与明细合计 {4} 相差超过 1 元'.format(
                        sheet_name, item['row_idx'], item['process_name'], declared, computed)
                )
            if code in code_index:
                warnings.append(
                    '第{0}页 行{1} 汇总行与行{2} 编号相同（{3}），保留后者'.format(
                        sheet_name, code_index[code], item['row_idx'], code)
                )
            code_index[code] = item['row_idx']
            if not item['is_total']:
                subtotal_codes_by_model.setdefault(model_no, []).append(code)

            rows_by_code[code] = {
                'process_code': code,
                'process_name': item['process_name'][:100],
                'component': sub_component[:100],
                'drawing_no': item['drawing_no'][:100],
                'model_no': model_no[:100],
                'price': declared if declared is not None else computed,
                'notes': item['notes'] or None,
                'price_type': 'subtotal',
                'included_processes': included,
                'sheet_name': sheet_name,
                'source_row': item['row_idx'],
            }
            rows.append(rows_by_code[code])

        # 图号可信度提示：行2 与数据行不一致
        meta_drawing = (variant.get('drawing') or (meta_drawings[0] if meta_drawings else ''))
        data_drawings = {r['drawing_no'] for r in rows if r['drawing_no']}
        if meta_drawing and data_drawings:
            norm_meta = normalize_key_part(meta_drawing)
            if all(normalize_key_part(d) != norm_meta for d in data_drawings):
                for row in rows:
                    note = '[图号存疑：行2/页名写 {0}，数据行写 {1}]'.format(
                        meta_drawing, row['drawing_no'])
                    row['notes'] = (note + ' ' + row['notes']) if row['notes'] else note
                warnings.append(
                    '第{0}页 行2 图号「{1}」与数据行图号「{2}」不一致，已按数据行取值并在备注标注'.format(
                        sheet_name, meta_drawing, '、'.join(sorted(data_drawings)))
                )
        return rows

    @staticmethod
    def _suspect_model_typos(rows):
        """提示疑似笔误的型号（如 48 页的「6012」，本系统其余位置写「60-12」）。

        只提示、不改正：源数据是业务事实，改正要由人工确认。
        """
        warnings = []
        models = {row['model_no'] for row in rows if row['model_no']}
        for row in rows:
            model = row['model_no']
            if not model or not model.isdigit() or len(model) < 3:
                continue
            for idx in range(1, len(model)):
                candidate = model[:idx] + '-' + model[idx:]
                if candidate in models:
                    warnings.append(
                        '第{0}页 行{1} 型号「{2}」疑似「{3}」的笔误，已按原值导入'.format(
                            row['sheet_name'], row['source_row'], model, candidate)
                    )
                    break
        return warnings

    @staticmethod
    def _dedup_rows(rows):
        """批次内去重：同一 process_code 保留最后出现的一条（后者覆盖前者）。"""
        warnings = []
        ordered = []
        position_by_code = {}
        for row in rows:
            code = row['process_code']
            previous = position_by_code.get(code)
            if previous is not None:
                warnings.append(
                    '工序编号 {0}（{1} 行{2} 与 {3} 行{4}）重复，保留后者'.format(
                        code, ordered[previous]['sheet_name'], ordered[previous]['source_row'],
                        row['sheet_name'], row['source_row'])
                )
                ordered[previous] = row
                continue
            position_by_code[code] = len(ordered)
            ordered.append(row)
        return ordered, warnings
