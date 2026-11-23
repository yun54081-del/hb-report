// 用 Playwright 讀 5168 社區實價頁（需 JS 渲染才有房數；翻頁要點頁碼），輸出 raw.json
const {chromium}=require('playwright');const fs=require('fs');
const cfg=JSON.parse(fs.readFileSync(__dirname+'/config.json'));
const minYm=process.argv[2]||'0';   // 例 11411：該頁最舊一筆比這更舊就不再翻頁
const grab=p=>p.$$eval('tr',trs=>trs.filter(t=>t.querySelector('td.addr')).map(t=>{const c=[...t.children];const T=x=>x?x.innerText.replace(/\s+/g,' ').trim():'';
  const tip=c[4]&&c[4].querySelector('[tooltip]');return {ym:T(c[0]),addr:T(t.querySelector('td.addr p')||c[1]),type:T(c[2]),price:T(c[3]),note:tip?tip.getAttribute('tooltip'):'',area:T(c[5]),land:T(c[6]),floor:T(c[7]),age:T(c[8])};}));
const ymOf=r=>{const m=r.ym.match(/(\d+)年(\d+)月/);return m?m[1]+m[2].padStart(2,'0'):'0'};
(async()=>{const b=await chromium.launch();
const ctx=await b.newContext({locale:'zh-TW',userAgent:'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'});
const p=await ctx.newPage();const out={};
const only=process.env.ONLY;for(const c of cfg.communities){if(only&&c.key!==only)continue;const o=out[c.key]={rows:[],error:null,latest:null};
 const url='https://community.houseprice.tw/building/'+c.id+'/price/';
 let ok=false;
 for(let t=0;t<3&&!ok;t++){try{await p.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
   await p.waitForSelector('td.addr',{timeout:30000});await p.waitForTimeout(1200);ok=true;}
   catch(e){o.error=String(e).slice(0,120);try{o.error+=' | '+(await p.title())+' | '+(await p.evaluate(()=>document.body.innerText.replace(/\s+/g,' ').slice(0,300)))+' | '+p.url();}catch(_){}await p.waitForTimeout(4000);}}
 if(!ok){console.log(c.name,'ERROR',o.error);continue;} o.error=null;
 for(let pg=1;pg<=6;pg++){
  if(pg>1){const first=await p.$eval('td.addr',e=>e.innerText).catch(()=> '');
    const li=p.locator('.page_wrap li',{hasText:new RegExp('^\\s*'+pg+'\\s*$')});
    if(!(await li.count()))break;
    await li.first().click();
    try{await p.waitForFunction(f=>{const e=document.querySelector('td.addr');return e&&e.innerText!==f},first,{timeout:15000});}catch(e){break;}
    await p.waitForTimeout(800);}
  const rows=await grab(p);if(!rows.length)break;
  o.rows.push(...rows);if(pg==1)o.latest=ymOf(rows[0]);
  if(ymOf(rows[rows.length-1])<minYm||rows.length<20)break;}
 console.log(c.name,o.rows.length,'latest',o.latest);}
fs.writeFileSync(__dirname+'/raw.json',JSON.stringify(out));await b.close();})();
