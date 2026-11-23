#!/usr/bin/env python3
"""每日更新：下載內政部實價登錄開放資料 → data.json → build.py → 網站根目錄 index.html 與 pdf/。
用法：python3 update.py period   -> 印出 近一年起月（給 scrape.js 判斷翻頁）
      python3 update.py build    -> 產生資料與網頁，並寫出 report.md
"""
import json, os, re, sys, glob, shutil, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(HERE, 'config.json')))
now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=8)


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


FW2H = str.maketrans('０１２３４５６７８９', '0123456789')
CNUM = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}


def cnint(t):
    t = (t or '').replace('層', '').strip()
    if not t: return None
    if t.isdigit(): return int(t)
    if t.startswith('地下') or '全' in t or '，' in t or ',' in t: return None
    v = 0
    if '十' in t:
        a, b = t.split('十', 1)
        v = (CNUM.get(a, 1) if a else 1) * 10 + (CNUM.get(b[:1], 0) if b else 0)
    else:
        v = CNUM.get(t[:1])
    return v


ADDR = re.compile(r'^(.+?區)(.+?[路街道段])(\d+)號')
TYPEMAP = [('大樓', '大樓'), ('華廈', '華廈'), ('公寓', '公寓'), ('透天', '透天'), ('店面', '店面'), ('套房', '套房')]


def moi_rows():
    """下載內政部實價登錄開放資料（台南市 d_lvr_land_a.csv），近 6 季＋本期，以編號去重"""
    import urllib.request, zipfile, io, csv
    urls = ['https://plvr.land.moi.gov.tw/Download?type=zip&fileName=lvr_landcsv.zip']
    y, q = now.year - 1911, (now.month - 1) // 3 + 1
    for _ in range(6):
        urls.append('https://plvr.land.moi.gov.tw/DownloadSeason?season=%dS%d&type=zip&fileName=lvr_landcsv.zip' % (y, q))
        q -= 1
        if q == 0: y, q = y - 1, 4
    rows, ok, errs = {}, 0, []
    for u in urls:
        try:
            raw = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=180).read()
            z = zipfile.ZipFile(io.BytesIO(raw))
            txt = z.read('d_lvr_land_a.csv').decode('utf-8-sig')
            lines = txt.splitlines()
            rd = csv.DictReader([lines[0]] + lines[2:])
            for r in rd:
                rows[r['編號']] = r
            ok += 1
        except Exception as e:
            errs.append('%s：%s' % (u.split('?')[1][:40], str(e)[:80]))
    return list(rows.values()), ok, errs


def parse(c, r):
    if r.get('交易標的', '') == '土地': return None
    raw = r['土地位置建物門牌'].replace('臺', '台')
    norm = raw.translate(FW2H)
    a = ADDR.match(norm)
    if not a or a.group(1) != '台南市' + c['district']: return None
    road, no = a.group(2), int(a.group(3))
    hit = False
    for mt in c['match']:
        if mt['road'] != road: continue
        if 'nums' in mt and no in mt['nums']: hit = True
        if 'from' in mt and mt['from'] <= no <= mt['to'] and (mt.get('parity') is None or no % 2 == mt['parity']): hit = True
    if not hit: return None
    d = r['交易年月日']
    if len(d) < 6: return None
    ym = d[:-2]
    total = round(int(r['總價元'] or 0) / 10000)
    area = round(float(r['建物移轉總面積平方公尺'] or 0) * 0.3025, 2)
    land = round(float(r['土地移轉總面積平方公尺'] or 0) * 0.3025, 2) or None
    carp = int(r['車位總價元'] or 0)
    cara = float(r['車位移轉總面積平方公尺'] or 0)
    car = '有' if (r['車位類別'] or carp > 0 or cara > 0 or '車位1' in r['交易筆棟數'] or '車位2' in r['交易筆棟數']) else '無'
    fl = cnint(r['移轉層次']); tf = cnint(r['總樓層數']) or c['tf']
    bt = r['建物型態']
    typ = next((v for k, v in TYPEMAP if k in bt), '其他')
    onlycar = r.get('交易標的', '') == '車位' or (area and '建物0' in r['交易筆棟數'])
    if onlycar:
        typ, lay, flo = '其他', '車位', ''
    else:
        lay = '%s/%s/%s' % (r['建物現況格局-房'], r['建物現況格局-廳'], r['建物現況格局-衛'])
        flo = '%d / %d' % (fl, tf) if fl else ''
    age = None
    b = r['建築完成年月']
    if len(b) >= 5 and b[:-4].isdigit():
        by, bm = int(b[:-4]), int(b[-4:-2] or 1)
        ty, tm = int(d[:-4]), int(d[-4:-2])
        age = round(((ty * 12 + tm) - (by * 12 + bm)) / 12, 1)
        if age < 0: age = 0.0
    if not area or not total: return None
    addr = raw.replace('台南市', '台南市', 1)
    return dict(ym=ym, typ=typ, addr=addr, total=total, area=area, land=land, floor=flo, rooms=lay,
                age=age, car=car, note=(r['備註'] or '').strip(), presale=False, raw=raw, id=r['編號'])


KEYW = ('親友', '特殊', '關係人', '瑕疵', '債', '急買', '急賣', '員工', '受贈', '共有')


def main_build():
    (a6, b6, l6), (a12, b12, l12) = periods()
    allrows, okn, derrs = moi_rows()
    if okn == 0:
        print('內政部資料下載全部失敗：', derrs); sys.exit(1)
    old = json.load(open(os.path.join(HERE, 'data.json'))) if os.path.exists(os.path.join(HERE, 'data.json')) else {'communities': []}
    oldc = {c['key']: c for c in old['communities']}
    comms, report, problems = [], [], []
    for c in cfg['communities']:
        recs = [x for x in (parse(c, r) for r in allrows) if x]
        if not recs and c['key'] in oldc:
            comms.append(oldc[c['key']]); continue
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
            g = x['rooms']
            if g and '/' not in g and g != '車位': onlyroom = True
            rows.append([x['ym'], x['typ'], x['addr'], x['total'], x['area'], x['land'], x['floor'], g, x['age'], x['car']])
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
    if derrs: problems += ['部分資料檔下載失敗：' + e for e in derrs]
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
