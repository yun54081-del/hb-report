#!/usr/bin/env python3
"""住商社區實價登錄月報產生器
用法：
  python3 build.py data.json logo.png outdir            -> 產生各社區 PDF/PNG 與 outdir/site/index.html（無下載鍵）
  python3 build.py data.json logo.png outdir assets.json -> 同上，並把 PDF 資產 id 寫入網頁下載鍵
data.json: {"updated":"2026/12/02","period":"11507-11511","period_label":"115年07月～115年11月",
  "communities":[{"key":"sdc","name":"上東城","district":"仁德區","note":"表下註記文字",
    "rows":[["11509","大樓","台南市仁德區文心路６８號二樓之６",780,29.42,2.91,"2 / 24","2/2/1",5.5,"有"], ...]}]}
社區可另設 "period" 與 "period_label"（覆蓋全域值，例如資料不足改抓近一年時）。
row 欄位：成交年月, 房屋型式, 地址, 總價(萬), 建坪(含車位), 地坪(可為null), 樓層/總樓層, 格局, 屋齡, 車位
單價 = 總價 / 建坪（自動計算；格局為「車位」的單獨車位交易不顯示單價）
assets.json: {"sdc":"<asset opaque_id>", ...}
"""
import json, sys, base64, os, subprocess, html as H

data = json.load(open(sys.argv[1]))
logo = 'data:image/png;base64,' + base64.b64encode(open(sys.argv[2], 'rb').read()).decode()
out = sys.argv[3]
assets = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else {}
os.makedirs(out + '/site', exist_ok=True)

HOUSE = '<svg class="house" viewBox="0 0 155 118"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8cc63f"/><stop offset="1" stop-color="#a8d86a"/></linearGradient></defs><rect width="155" height="118" fill="url(#g)"/><path d="M18 62 L77 18 L137 62 M30 54 V118 M125 54 V118 M112 32 V20 H122 V40" fill="none" stroke="#6faa2e" stroke-width="5" opacity=".7"/><g fill="#4d8f22"><circle cx="64" cy="70" r="6"/><rect x="56" y="78" width="16" height="22" rx="4"/><rect x="58" y="98" width="5" height="18"/><rect x="65" y="98" width="5" height="18"/><circle cx="92" cy="70" r="6"/><rect x="84" y="78" width="16" height="22" rx="4"/><rect x="86" y="98" width="5" height="18"/><rect x="93" y="98" width="5" height="18"/><rect x="70" y="86" width="16" height="4"/></g></svg>'

SHEET_CSS = '''*{box-sizing:border-box}
body{margin:0;font-family:"Noto Sans CJK TC","Microsoft JhengHei",sans-serif;color:#222}
.page{width:1120px;margin:0 auto;border:1px solid #bbb;position:relative;padding-bottom:130px;background:#fff}
.head{padding:20px 26px 12px;display:flex;align-items:center;gap:16px}.head img{height:76px;display:block}
.wm1{font-family:"Noto Sans CJK TC Black","Noto Sans TC","Microsoft JhengHei",sans-serif;font-size:46px;font-weight:900;color:#40ae36;-webkit-text-stroke:0.8px #40ae36;letter-spacing:6px;line-height:1.05}.wm2{font-size:19px;font-weight:bold;color:#40ae36;margin-top:6px;letter-spacing:.5px}
.gbar{height:4px;background:#5cb531;margin:0 0 12px}
.notes{padding:0 18px;font-size:15px;line-height:1.55}.notes p{margin:0 0 8px}
.title{text-align:center;font-size:18px;font-weight:bold;margin:14px 0 4px}
table.rt{width:calc(100% - 24px);margin:8px 12px 0;border-collapse:collapse;font-size:15px}
.rt th{font-weight:bold;padding:6px 4px;vertical-align:bottom;line-height:1.25}
.rt td{padding:5px 4px;text-align:center;white-space:nowrap}.rt td.addr{text-align:left;padding-left:10px}.rt td.price{color:#d0312d}
.rt td.empty{color:#888;padding:20px}
.sign{display:flex;justify-content:center;gap:210px;font-family:"Noto Serif CJK TC",serif;font-weight:bold;font-size:22px;letter-spacing:6px;margin-top:26px}
.foot{font-size:12.5px;color:#555;padding:14px 18px 0}
.house{position:absolute;right:2px;bottom:2px;width:155px;height:118px}'''

NOTES = '''<p>＊本表提供住商不動產及內政部公告之實價登錄部分成交行情資料，建議您若需要進一步的專業評估時，可聯絡各地住商不動產加盟店，或線上填寫買屋服務留言、賣屋服務留言。</p>
<p>＊本系統僅提供成交行情供您參考，為各物件成交價因不同之物件特性，如裝潢、屋齡 、格局、景觀、交通、景氣 波動及客戶意願......等因素而影響成交價格。</p>
<p>＊本系統成交行情資料所提供之每坪單價係以【成交總價/建物坪數】計算，個案單價易受到物件本身特性(例如車位的有無、土地持分)而有所差異，進行比較時應考量實際狀況！</p>
<p>＊單價計算土地依地坪,另農舍/車位/廠房/透天/別墅不顯示單價。</p>'''

def g(x):
    return ('%.2f' % x).rstrip('0').rstrip('.')

def sheet(c):
    trs = []
    for r in c['rows']:
        ym, typ, addr, tot, b, l, fl, lay, age, pk = r
        unit = g(tot / b) + '萬' if (b and lay != '車位') else ''
        trs.append('<tr><td>%s</td><td>%s</td><td class="addr">%s</td><td class="price">%s萬</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            ym, H.escape(typ), H.escape(addr), g(tot), (g(b) + '坪') if b else '', (g(l) + '坪') if l else '', unit,
            H.escape(fl or ''), H.escape(lay or ''), age if age is not None else '', pk))
    if not trs:
        trs.append('<tr><td class="empty" colspan="11">本期間內查無成交資料</td></tr>')
    return '''<div class="page"><div class="head"><img src="%s" alt="住商不動產"><div><div class="wm1">住商不動產</div><div class="wm2">www.hbhousing.com.tw</div></div></div><div class="gbar"></div>
<div class="notes">%s</div>
<div class="title">台南市%s　%s社區　實價登錄（%s）</div>
<table class="rt"><tr><th>成交年月</th><th>房屋型式</th><th>地址</th><th>成交總價</th><th>建坪</th><th>地坪</th><th>單價</th><th>出售樓層<br>/ 總樓層</th><th>格局<br>(房/廳/衛)</th><th>屋齡(年)</th><th>車位</th></tr>
%s
</table>
<div class="sign"><span>確認人：</span><span>時間：</span></div>
<div class="foot">資料來源：內政部實價登錄（資料更新至%s）。%s</div>
%s</div>''' % (logo, NOTES, c['district'], c['name'], c.get('period_label', data['period_label']), '\n'.join(trs), data['updated'], H.escape(c.get('note', '')), HOUSE)

JS_RENDER = r'''
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [src,png,pdf]=process.argv.slice(2);const b=await chromium.launch();
const p=await b.newPage({viewport:{width:1140,height:900},deviceScaleFactor:2});
await p.goto('file://'+src);await p.waitForTimeout(300);
await p.locator('.page').screenshot({path:png});
for(const s of [0.65,0.62,0.6,0.57,0.55,0.52,0.5,0.47,0.45,0.42,0.4]){await p.pdf({path:pdf,format:'A4',landscape:false,printBackground:true,scale:s});
 const n=(fs.readFileSync(pdf,'latin1').match(/\/Type\s*\/Page[^s]/g)||[]).length;if(n<=1)break;}
await b.close();})();'''
open(out + '/render.js', 'w').write(JS_RENDER)

sections, tabs = [], []
for c in data['communities']:
    doc = '<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"><style>@page{size:A4 portrait;margin:8mm}%s</style></head><body>%s</body></html>' % (SHEET_CSS, sheet(c))
    per = c.get('period', data['period'])
    base = '%s/%s實價登錄_%s' % (out, c['name'], per)
    open(base + '.html', 'w').write(doc)
    subprocess.run(['node', out + '/render.js', os.path.abspath(base + '.html'), os.path.abspath(base + '.png'), os.path.abspath(base + '.pdf')], check=True)
    k = c['key']
    tabs.append('<a class="tab" href="#%s" data-k="%s">%s（%s）</a>' % (k, k, c['name'], c['district']))
    sections.append('''<section id="sec-%s" class="rep" data-asset="%s" data-file="%s實價登錄_%s.pdf">
<div class="bar2"><span class="nm">%s</span><span class="pd">%s・%d 筆</span><a class="op" href="/_blob/%s" target="_blank" rel="noopener">開啟 PDF（列印／下載）</a><span class="msg"></span></div>
<div class="sheet">%s</div></section>''' % (k, assets.get(k, ''), c['name'], per, c['name'], c.get('period_label', data['period_label']), len(c['rows']), assets.get(k, ''), sheet(c)))

first = data['communities'][0]['key']
keys = json.dumps([c['key'] for c in data['communities']])
site = '''<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>住商不動產｜興城團隊｜社區實價登錄月報</title><meta property="og:title" content="住商不動產｜興城團隊｜社區實價登錄月報"><meta property="og:description" content="台南各社區近半年實價登錄，每天中午 12 點更新"><meta name="description" content="台南各社區近半年實價登錄，每天中午 12 點更新"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@900&display=swap"><style>%s
html{-webkit-text-size-adjust:100%%;text-size-adjust:100%%}html,body{background:#f3f5f2}
.top{position:sticky;top:0;z-index:5;background:#fff;border-bottom:3px solid #5cb531;padding:12px 18px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.top h1{font-size:18px;margin:0 12px 0 0;color:#2f6b14}.top .upd{font-size:13px;color:#666;margin-left:auto}
.tab{border:1px solid #5cb531;background:#fff;color:#2f6b14;padding:6px 14px;border-radius:16px;font-size:15px;cursor:pointer;text-decoration:none}
.tab.on{background:#5cb531;color:#fff}
.rep{display:none;padding:16px 0 40px}.rep.on{display:block}
.bar2{max-width:1120px;margin:0 auto 10px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:0 8px}
.bar2 .nm{font-weight:bold;font-size:17px}.bar2 .pd{color:#555}
.op{margin-left:auto;background:#d0312d;color:#fff;padding:8px 16px;border-radius:6px;font-size:15px;text-decoration:none}
.dl:disabled{background:#bbb;cursor:default}.msg{font-size:13px;color:#666}
.sheet{overflow-x:auto;padding:0 8px}
@media (max-width:760px){.top{position:static;padding:8px 10px;gap:6px}.top h1{font-size:15px;width:100%%;margin:0}.tab{font-size:13px;padding:4px 10px}.top .upd{margin-left:0;font-size:12px}.bar2 .nm{font-size:15px}.op{padding:7px 12px;font-size:14px}.sheet{overflow:hidden;padding:0 4px}.sheet .page{margin:0}}
@media print{.page{transform:none!important}.sheet{height:auto!important}.top,.bar2{display:none}.rep{display:block!important;padding:0;page-break-after:always}html,body{background:#fff}@page{size:A4 portrait;margin:8mm}}
</style></head><body>
<div class="top"><h1>住商不動產｜興城團隊｜社區實價登錄月報</h1>%s<span class="upd">最近更新：%s　每天中午 12 點自動更新</span></div>
%s
<script>
var KEYS=%s;
function show(){var k=(location.hash||'').slice(1);if(KEYS.indexOf(k)<0)k='%s';
document.querySelectorAll('.rep').forEach(function(s){s.classList.toggle('on',s.id==='sec-'+k)});
document.querySelectorAll('.tab').forEach(function(t){t.classList.toggle('on',t.dataset.k===k)});window.scrollTo(0,0);}
function fit(){document.querySelectorAll('.rep.on .sheet').forEach(function(sh){var pg=sh.querySelector('.page');if(!pg)return;pg.style.transform='';sh.style.height='';var w=sh.clientWidth-8,pw=pg.offsetWidth+2;if(w<pw){var k=w/pw;pg.style.transformOrigin='0 0';pg.style.transform='scale('+k+')';sh.style.height=Math.ceil(pg.offsetHeight*k+4)+'px';}});}
window.addEventListener('hashchange',function(){show();fit();});window.addEventListener('resize',fit);window.addEventListener('orientationchange',function(){setTimeout(fit,300)});show();fit();
document.querySelectorAll('.rep').forEach(function(s){if(!s.dataset.asset){s.querySelector('.op').style.display='none';s.querySelector('.msg').textContent='PDF 準備中';}});
</script></body></html>''' % (SHEET_CSS, ''.join(tabs), data['updated'], '\n'.join(sections), keys, first)
open(out + '/site/index.html', 'w').write(site)
print('ok', len(site))
