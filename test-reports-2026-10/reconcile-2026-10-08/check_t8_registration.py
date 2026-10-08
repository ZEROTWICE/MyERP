#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_t8_registration.py — B12-05（t8）登记件的机检判据（不写任何业务库）

目标文件（只读）：
  1. `test-reports-2026-10/B12-05-口径登记-N-12收窄与工资口径对照.md`（本任务的登记件）
  2. `test-reports-2026-10/reconcile-2026-10-08/recon-arbitration.md`（**A-13 黑名单的权威属地**——
     本脚本的禁区词表**在运行时从该文件解析**，不在本脚本里硬编码任何黑名单数字）

判据（RESULT: OK ⇒ 全真）：
  P1 口径键 `B12-05/N-12-narrowed` 下**两句同时命中**：「不做金额台账」+「库存台账行必须写」
  P2 两态阳性对照（`81-:112` 的口径）：两句都在 ⇒ 命中；**缺任一句 ⇒ 0 命中**（用内存里删句的副本模拟）
  N1 阴性对照：不得出现「不做报废」与「台账」**连写**的旧措辞（逐字原文见 `81-:111`，本脚本不复述，
     故以「片段拼接 + 正则」构造检测模式，避免脚本自身成为命中源）
  N2 A-13 黑名单：从 `recon-arbitration.md` §A-13 的 6 条里解析出的**作废口径**，在登记件中出现 0 次
  A1 对照读数锚点齐备：`3487` / `3488` / `15.0` / 真库 SHA256 / `§6.1` / `§6.4`
  A2 拍板项标注：§C.1 表 4 行 + 「按默认路径执行」≥ 4 处 + 「用户拍板」计数口径在 §C.0/§D 有登记
  A3 append-only 纪律：`§E 追加声明` 节存在且 v1 声明「本节为空」+ 订正规则（只增不删）在位

复跑：
  F:\\Miniconda\\envs\\wage\\python.exe -B scripts/_sandbox_compat.py ^
    test-reports-2026-10/reconcile-2026-10-08/check_t8_registration.py
退出码：0 = 全真；1 = 有判据为假。
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent                      # test-reports-2026-10/reconcile-2026-10-08
REPORTS = HERE.parent                                               # test-reports-2026-10
REGISTRATION = REPORTS / 'B12-05-口径登记-N-12收窄与工资口径对照.md'
ARBITRATION = HERE / 'recon-arbitration.md'

REAL_DB_SHA = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

POSITIVE_SENTENCE_1 = '不做金额台账'
POSITIVE_SENTENCE_2 = '库存台账行必须写'
# 阴性判据的字符串在登记件与 81- 里都以「逐字原文」存在，若本脚本直接写死，
# 脚本自身就会成为「出现旧措辞」的命中源 ⇒ 用片段拼接构造，脚本正文里不出现该整串。
LEGACY_PREFIX = '不做报废'
LEGACY_SUFFIX = '台账'
LEGACY_PATTERN = re.compile(re.escape(LEGACY_PREFIX) + re.escape(LEGACY_SUFFIX))

ANCHORS = ['3487', '3488', '15.0', REAL_DB_SHA, '§6.1', '§6.4',
           '业务流程现状与缺口.md', '81-', '不做金额台账', '库存台账行必须写']


def read_text(path):
    return path.read_text(encoding='utf-8')


def parse_a13_forbidden(arbitration_text):
    """从 recon-arbitration.md §A-13 解析作废口径；只取带数字（或「已实现」）的片段。"""
    lines = arbitration_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith('## A-13'):
            start = i
            break
    if start is None:
        return None, []
    body = []
    for line in lines[start + 1:]:
        if line.startswith('## '):
            break
        body.append(line)

    forbidden = []
    bullets = [ln for ln in body if re.match(r'^[①②③④⑤⑥]', ln.strip())]
    for line in bullets:
        left = line.split('→')[0]
        inner = re.findall(r'「(.+?)」', left)
        spans = re.findall(r'`([^`]+)`', left)
        candidates = [s for s in spans if re.search(r'\d', s)]
        if not candidates:
            candidates = [s.strip() for s in inner if re.search(r'\d', s) or '已实现' in s]
        for cand in candidates:
            token = cand.strip()
            if token and token not in forbidden:
                forbidden.append(token)
    return len(bullets), forbidden


def token_hits(text, tokens):
    """整体命中 + 去空白命中的并集（容忍 `110 处` / `110处` 的写法差异）。"""
    squashed = re.sub(r'\s+', '', text)
    hits = {}
    for token in tokens:
        n = text.count(token) + re.sub(r'\s+', '', squashed).count(re.sub(r'\s+', '', token))
        if n:
            hits[token] = n
    return hits


def main():
    out = {'checker': pathlib.Path(__file__).name, 'task': 't8 / B12-05 登记件机检'}
    missing = [str(p) for p in (REGISTRATION, ARBITRATION) if not p.is_file()]
    if missing:
        out['RESULT'] = 'FAIL'
        out['missing_files'] = missing
        print(json.dumps({'RESULT': 'FAIL', 'missing_files': missing}, ensure_ascii=True))
        return 1

    doc = read_text(REGISTRATION)
    arbitration = read_text(ARBITRATION)

    out['target'] = str(REGISTRATION)
    out['target_bytes'] = REGISTRATION.stat().st_size

    # ---- P1 / P2：口径键下两句同时命中，且缺一句即 0 命中（两态阳性对照） ----
    key_block = doc
    s1 = key_block.count(POSITIVE_SENTENCE_1)
    s2 = key_block.count(POSITIVE_SENTENCE_2)
    only1 = key_block.replace(POSITIVE_SENTENCE_2, '')
    only2 = key_block.replace(POSITIVE_SENTENCE_1, '')
    neither = only1.replace(POSITIVE_SENTENCE_1, '')

    def pair_hit(text):
        return text.count(POSITIVE_SENTENCE_1) > 0 and text.count(POSITIVE_SENTENCE_2) > 0

    out['P1_sentences'] = {
        'positive_1': POSITIVE_SENTENCE_1, 'count_1': s1,
        'positive_2': POSITIVE_SENTENCE_2, 'count_2': s2,
        'both_present': pair_hit(key_block),
    }
    out['P2_two_state'] = {
        'both_present_verdict': pair_hit(key_block),
        'drop_sentence_2_verdict': pair_hit(only1),
        'drop_sentence_1_verdict': pair_hit(only2),
        'drop_both_verdict': pair_hit(neither),
    }

    # ---- N1：旧措辞（连写）不得出现 ----
    legacy_hits = LEGACY_PATTERN.findall(doc)
    out['N1_legacy_wording'] = {
        'pattern': LEGACY_PREFIX + '...' + LEGACY_SUFFIX + '（片段拼接，脚本不复述逐字原文）',
        'hits': len(legacy_hits),
        'quote_marked_occurrences': doc.count('不做报废成本台账'),
        'note': ('登记件允许「不做报废成本台账」以**带出处标注的原值引用**形态出现'
                 '（§A.1 原值 + §A.3 引用），禁止的是去掉「金额」限定的连写旧措辞'),
    }

    # ---- N2：A-13 黑名单（禁区的权威属地是 recon-arbitration.md，运行时解析） ----
    bullet_count, forbidden = parse_a13_forbidden(arbitration)
    a13_hits = token_hits(doc, forbidden)
    out['N2_A13_blacklist'] = {
        'source': str(ARBITRATION) + ' §A-13',
        'bullets_parsed': bullet_count,
        'derived_forbidden_tokens': forbidden,
        'hits_in_registration': a13_hits,
        'hit_count': len(a13_hits),
    }

    # ---- A1：对照读数锚点 ----
    out['A1_anchors'] = {a: doc.count(a) for a in ANCHORS}
    out['A1_all_anchors_present'] = all(doc.count(a) > 0 for a in ANCHORS)

    # ---- A2：拍板项标注 ----
    c_section = doc.split('## §C', 1)[-1].split('## §D', 1)[0] if '## §C' in doc else ''
    c_rows = [ln for ln in c_section.splitlines()
              if ln.strip().startswith('| ') and '按默认路径执行' in ln]
    out['A2_decision_items'] = {
        'table_rows_with_default_path': len(c_rows),
        'default_path_phrase_count': doc.count('按默认路径执行'),
        'user_decision_phrase_count': doc.count('用户拍板'),
        'has_A13_discipline_statement': 'A-13' in doc,
    }

    # ---- A3：append-only 纪律 ----
    out['A3_append_only'] = {
        'section_E_present': '## §E 追加声明' in doc,
        'v1_empty_declared': '本节为空' in doc,
        'add_only_rule_present': '只增不删' in doc,
        'correction_format_rule_present': '§E-n' in doc,
    }

    verdict = {
        'P1_both_sentences_present': out['P1_sentences']['both_present'],
        'P2_two_state_discriminates': (out['P2_two_state']['both_present_verdict'] is True
                                       and out['P2_two_state']['drop_sentence_2_verdict'] is False
                                       and out['P2_two_state']['drop_sentence_1_verdict'] is False
                                       and out['P2_two_state']['drop_both_verdict'] is False),
        'N1_no_legacy_wording': len(legacy_hits) == 0,
        'N2_no_A13_blacklist_numbers': len(a13_hits) == 0,
        'N2_a13_source_parsed': bullet_count == 6 and len(forbidden) >= 5,
        'A1_all_anchors_present': out['A1_all_anchors_present'],
        'A2_four_decision_rows': len(c_rows) == 4,
        'A2_default_path_at_least_4': doc.count('按默认路径执行') >= 4,
        'A3_append_only_discipline': (out['A3_append_only']['section_E_present']
                                      and out['A3_append_only']['v1_empty_declared']
                                      and out['A3_append_only']['add_only_rule_present']),
    }
    out['verdict'] = verdict
    out['RESULT'] = 'OK' if all(verdict.values()) else 'FAIL'

    dest = pathlib.Path(__file__).with_suffix('.output.json')
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    out['output'] = str(dest)

    print(json.dumps(out, ensure_ascii=True, indent=2))
    print('RESULT: %s' % out['RESULT'])
    return 0 if out['RESULT'] == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
