#!/usr/bin/env python3
"""每日更新：raw.json（scrape.js 產生）→ data.json → build.py → 網站根目錄 index.html 與 pdf/。
用法：python3 update.py period   -> 印出 近一年起月（給 scrape.js 判斷翻頁）
      python3 update.py build    -> 產生資料與網頁，並寫出 report.md
"""
import json, os, re, sys, glob, shutil, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(HERE, 'config.json')))
now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)


def ym_add(y, m, k):
    t = y * 12 + (m - 1) + k
    return t // 12, t % 12 + 1


def periods():
    y, m = ym_add(now.year, now.month, -1)          # 上一個完整月
    def p(n):
        sy, sm = ym_add(y, m, -(n - 1))
        a = '%d%02d' % (sy - 1911, sm); b = '%d%02d' % (y - 1911, m)
        lab = '%d年%02d月～%d年%02d月' % (sy - 1911, sm, y - 1911, m)
        return a, b, lab
    return p(6), p(12)


FW = lambda s: ''.join(chr(ord(ch) + 0xFEE0) if ch.isdigit() else ch for ch in str(s))
DG = '〇一二三四五六七八九'


def cn(n):
    n = int(n)
    if n < 10: return DG[n]
    if n < 20: return '十' + (DG[n % 10] if n % 10 else '')
    return DG[n // 10] + '十' + (DG[n % 10] if n % 10 else '')


def num(s, default=None):
    m = re.search(r'-?[\d,]+(?:\.\d+)?', s or '')
    return float(m.group(0).replace(',', '')) if m else default


ADDR = re.compile(r'^(.+?[路街道段])(\d+)號(?:(\d+)樓)?(?:之(\d+))?')


def parse(c, r):
    m = re.search(r'(\d+)年(\d+)月', r['ym'])
    if not m: return None
    ym = '%s%02d' % (m.group(1), int(m.group(2)))
    raw = r['addr'].replace(' ', '')
    a = ADDR.match(raw)
    fl_page = num(r['floor'].split('/')[0]) if '/' in r['floor'] else None
    if a:
        road, no, fl, z = a.group(1), int(a.group(2)), a.group(3), a.group(4)
        ok = False
        for mt in c['match']:
            if mt['road'] != road: continue
            if 'nums' in mt and no in mt['nums']: ok = True
            if 'from' in mt and mt['from'] <= no <= mt['to'] and (mt.get('parity') is None or no % 2 == mt['parity']): ok = True
        if not ok: return ('skip', raw)
        fl = int(fl) if fl else (int(fl_page) if fl_page else None)
        addr = '台南市%s%s%s號' % (c['district'], road, FW(no))
        if a.group(3): addr += '%s樓' % cn(fl)
        if z: addr += '之' + FW(z)
        presale = False
    elif any(k in raw for k in c.get('presale', [])):
        addr = '台南市%s%s' % (c['district'], FW(raw)); fl = int(fl_page) if fl_page else None; presale = True
    else:
        return ('skip', raw)
    t = r['type'].split(' ')
    typ = t[0] if t else ''
    rooms = re.search(r'(\d+)房', r['type'])
    total = num(r['price'])
    carp = num(r['price'].split('含車位')[1]) if '含車位' in r['price'] else 0
    parts = r['area'].split('坪', 1)
    area = num(parts[0])
    cara = num(parts[1]) if len(parts) > 1 else 0
    land = num(r['land'])
    age = num(r['age']) if re.search(r'\d', r['age'] or '') else None
    car = '有' if (carp or 0) > 0 or (cara or 0) > 0 else '無'
    if total is None or area is None: return None
    total = int(total) if total == int(total) else total
    return dict(ym=ym, typ=typ, addr=addr, total=total, area=area, land=land,
                floor='%d / %d' % (fl, c['tf']) if fl else '', rooms=(rooms.group(1) + '房') if rooms else '',
                age=age, car=car, note=(r.get('note') or '').strip(), presale=presale, raw=raw)


KEYW = ('親友', '特殊', '關係人', '瑕疵', '債', '急買', '急賣', '員工', '受贈', '共有')


def main_build():
    (a6, b6, l6), (a12, b12, l12) = periods()
    raw = json.load(open(os.path.join(HERE, 'raw.json')))
    old = json.load(open(os.path.join(HERE, 'data.json'))) if os.path.exists(os.path.join(HERE, 'data.json')) else {'communities': []}
    oldc = {c['key']: c for c in old['communities']}
    lay = json.load(open(os.path.join(HERE, 'layouts.json')))
    comms, report, problems = [], [], []
    for c in cfg['communities']:
        rc = raw.get(c['key'], {})
        recs = [x for x in (parse(c, r) for r in rc.get('rows', [])) if x]
        skipped = sorted(set(x[1] for x in recs if isinstance(x, tuple)))
        recs = [x for x in recs if isinstance(x, dict)]
        if not recs:
            problems.append('%s：抓不到資料（%s），沿用上次資料' % (c['name'], rc.get('error') or '0 筆'))
            if c['key'] in oldc: comms.append(oldc[c['key']])
            continue
        # 去重：同址同月同價只留一筆；預售版若已有門牌版（同月同價）則略過
        seen, uniq = set(), []
        for x in recs:
            k = (x['addr'], x['ym'], x['total'])
            if k in seen: continue
            seen.add(k); uniq.append(x)
        door = {(x['ym'], x['total']) for x in uniq if not x['presale']}
        uniq = [x for x in uniq if not (x['presale'] and (x['ym'], x['total']) in door)]
        n6 = [x for x in uniq if a6 <= x['ym'] <= b6]
        if len(n6) >= 3:
            sel, per, lab, note = n6, '%s-%s' % (a6, b6), l6, '近半年共%d筆' % len(n6)
        else:
            sel = [x for x in uniq if a12 <= x['ym'] <= b12]
            per, lab = '%s-%s' % (a12, b12), l12
            note = '近半年僅%d筆，改列近一年（近一年共%d筆）' % (len(n6), len(sel))
        sel.sort(key=lambda x: x['ym'], reverse=True)
        extra = []
        for x in sel:
            if x['note'] and any(k in x['note'] for k in KEYW):
                extra.append('%s為特殊交易（%s）' % (x['addr'].replace('台南市' + c['district'], ''), x['note'][:30]))
        byaddr = {}
        for x in sel: byaddr.setdefault((x['addr'], x['total']), []).append(x['ym'])
        for (ad, tot), yms in byaddr.items():
            if len(yms) > 1:
                extra.append('%s於%s各有一筆同價登錄，疑為重複揭露，請以原始登錄為準' % (ad.replace('台南市' + c['district'], ''), '、'.join(sorted(set(yms)))))
        rows, onlyroom = [], False
        for x in sel:
            g = lay.get(x['addr']) or x['rooms']
            if g and '/' not in g: onlyroom = True
            rows.append([x['ym'], x['typ'], x['addr'], x['total'], x['area'], x['land'], x['floor'], g, x['age'], x['car']])
        if skipped: extra.append('已排除不在本社區門牌範圍的交易%d筆' % len(skipped))
        tail = '格局僅列房數者為登錄資料未提供廳衛，請以原始登錄為準。' if onlyroom else ''
        full_note = '；'.join([note] + extra) + '；' + tail if tail else '；'.join([note] + extra) + '。'
        comm = dict(key=c['key'], name=c['name'], district=c['district'], period=per, period_label=lab, note=full_note, rows=rows)
        comms.append(comm)
        # 與上次比較，找出新增成交
        prev = {(r[2], r[0], r[3]) for r in oldc.get(c['key'], {}).get('rows', [])}
        new = [r for r in rows if (r[2], r[0], r[3]) not in prev]
        if oldc and new:
            for r in new:
                report.append('- %s：%s %s，%s萬，%s坪，單價 %.2f 萬' % (c['name'], r[0], r[2].replace('台南市', ''), r[3], r[4], r[3] / r[4]))
        if rc.get('latest') and rc['latest'] < '%d%02d' % ym_add(now.year - 1911, now.month, -4):
            problems.append('%s：5168 最新資料只到 %s，可能尚未更新' % (c['name'], rc['latest']))
    upd = '%d/%02d/%02d' % (now.year - 1911, now.month, now.day)
    data = dict(updated=upd, period='%s-%s' % (a6, b6), period_label=l6, communities=comms)
    json.dump(data, open(os.path.join(HERE, 'data.json'), 'w'), ensure_ascii=False, indent=1)
    out = os.path.join(HERE, 'out')
    shutil.rmtree(out, ignore_errors=True)
    assets = {c['key']: c['key'] for c in comms}
    json.dump(assets, open(os.path.join(HERE, 'assets.json'), 'w'))
    subprocess.run(['python3', os.path.join(HERE, 'build.py'), os.path.join(HERE, 'data.json'), os.path.join(HERE, 'mark.png'), out, os.path.join(HERE, 'assets.json')], check=True)
    h = open(os.path.join(out, 'site', 'index.html')).read()
    h = re.sub(r'/_blob/(\w+)"', r'pdf/\1.pdf"', h)
    assert '/_blob/' not in h
    open(os.path.join(ROOT, 'index.html'), 'w').write(h)
    os.makedirs(os.path.join(ROOT, 'pdf'), exist_ok=True)
    from pypdf import PdfWriter
    w = PdfWriter()
    for c in comms:
        f = glob.glob(os.path.join(out, '%s實價登錄_*.pdf' % c['name']))[0]
        shutil.copy(f, os.path.join(ROOT, 'pdf', c['key'] + '.pdf')); w.append(f)
    w.write(os.path.join(ROOT, 'pdf', 'all.pdf'))
    lines = ['# 實價登錄更新 %s' % upd, '']
    lines += (['## 新增成交'] + report) if report else ['今日無新增成交。']
    if problems: lines += ['', '## 需要注意'] + ['- ' + p for p in problems]
    lines += ['', '## 各社區筆數'] + ['- %s：%s，%d 筆' % (c['name'], c['period_label'], len(c['rows'])) for c in comms]
    open(os.path.join(HERE, 'report.md'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    if sys.argv[1] == 'period':
        print(periods()[1][0])
    else:
        main_build()
