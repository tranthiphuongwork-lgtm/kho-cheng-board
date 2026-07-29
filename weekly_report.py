# -*- coding: utf-8 -*-
"""Báo cáo bán hàng theo KỲ — chạy sáng Thứ 2 (tuần) và ngày 1 hàng tháng (tháng).
REPORT_PERIOD = 'week' (mặc định) hoặc 'month'.
  week  -> cộng tổng Thứ 2..Chủ nhật tuần trước -> weekly_report.html
  month -> cộng tổng cả tháng trước           -> monthly_report.html
Top Kalle KHÔNG tính các mã: gói sữa tắm ngẫu nhiên, vial ngẫu nhiên, bst ngẫu nhiên, bst.
Tự chứa, chỉ cần secret: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN, LARK_WEBHOOK
"""
import os, json, re, urllib.request, datetime

LARK_HOST='https://open.larksuite.com'
APP_ID=os.environ['LARK_APP_ID']; APP_SECRET=os.environ['LARK_APP_SECRET']
BASE=os.environ['LARK_APP_TOKEN']; WEBHOOK=os.environ['LARK_WEBHOOK']
T_SP='tbl7PSQh3Lq5Tlxy'; T_XK='tblIHtLsM4QTMMQJ'
TRIO=['1082704','1082694','1082699']
DYE_PL={'Dưỡng ít','Dưỡng vừa','Dưỡng nhiều','3 gói bọt','5 gói bọt','10 gói','Màu lẻ'}
KALLE_KEEP=('dark beauty','first love','venus','jasmine amber','girl power','blue shirt','ladykiller','lady killer')
KALLE_TOP_SKIP=('ngẫu nhiên','bst')   # không đưa vào TOP Kalle
PERIOD=(os.getenv('REPORT_PERIOD') or 'week').strip().lower()

def _norm(s): return re.sub(r'\s+',' ',(s or '').strip()).lower()
def kalle_alert_ok(name,hang):
    if (hang or '').strip()!='Kalle': return True
    n=_norm(name); return any(k in n for k in KALLE_KEEP)
def kalle_top_ok(name):
    n=_norm(name); return not any(k in n for k in KALLE_TOP_SKIP)
def ltoken():
    r=urllib.request.Request(LARK_HOST+'/open-apis/auth/v3/tenant_access_token/internal',
        data=json.dumps({'app_id':APP_ID,'app_secret':APP_SECRET}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=30))['tenant_access_token']
def gt(v):
    if isinstance(v,list): return ''.join(x.get('text','') for x in v if isinstance(x,dict)) or (str(v[0]) if v else '')
    if isinstance(v,dict): return v.get('value') or v.get('text')
    return v
def fv(v):
    if isinstance(v,dict) and 'value' in v:
        vv=v['value']; return vv[0] if isinstance(vv,list) and vv else 0
    try: return float(v)
    except: return 0
def lpost(tok,path,body):
    r=urllib.request.Request(LARK_HOST+path,data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+tok,'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=60))
def lsearch(tok,tid,fields):
    out=[];pt=None
    while True:
        url=f'/open-apis/bitable/v1/apps/{BASE}/tables/{tid}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        d=lpost(tok,url,{'page_size':500,'field_names':fields})['data']
        out+=d.get('items',[])
        if d.get('has_more'): pt=d['page_token']
        else: break
    return out

TPL=r'''<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Báo cáo bán hàng __KIND__ __RANGE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;background:#0f1729;color:#e6edf6;padding:18px;max-width:1100px;margin:0 auto}
.head{background:__GRAD__;border-radius:16px;padding:20px 24px;margin-bottom:18px}
.head h1{font-size:22px;font-weight:800}.head .sub{opacity:.85;font-size:13px;margin-top:4px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:#16203a;border:1px solid #243352;border-radius:14px;padding:16px}
.card h2{font-size:15px;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.tag{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px}
.tag.c{background:#155e75;color:#a5f3fc}.tag.k{background:#5b21b6;color:#ddd6fe}
.row{margin-bottom:10px}
.row .r1{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:13px}
.row .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .rk{display:inline-block;width:20px;color:#7d8db0;font-weight:700}
.row .qty{font-weight:800;font-size:14px}
.row .tn{color:#7d8db0;font-size:11px;white-space:nowrap}
.bar{height:6px;border-radius:6px;margin-top:4px;background:#243352;overflow:hidden}
.bar>i{display:block;height:100%;border-radius:6px}
.bc{background:linear-gradient(90deg,#06b6d4,#22d3ee)}.bk{background:linear-gradient(90deg,#8b5cf6,#a78bfa)}
.risk h2{color:#fbbf24}
.ri{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;background:#1b1430;border-left:4px solid #f59e0b;margin-bottom:8px}
.ri.cr{border-color:#ef4444;background:#2a1320}.ri.wn{border-color:#f59e0b}.ri.ye{border-color:#eab308}
.ri .nm{flex:1;font-size:13px;font-weight:600}
.ri .meta{font-size:11px;color:#9fb0d0;text-align:right;white-space:nowrap}
.ri .dd{font-weight:800;font-size:15px;text-align:center}
.dd.cr{color:#f87171}.dd.wn{color:#fbbf24}.dd.ye{color:#fde047}
.empty{color:#7d8db0;font-size:13px;padding:8px}
.foot{text-align:center;color:#5b6b8c;font-size:11px;margin-top:16px}
</style></head><body>
<div class="head"><h1>__ICON__ Báo cáo bán hàng __KINDUP__ — Kho</h1><div class="sub">__KIND2__ __RANGE__ · Tổng bán cả __KIND3__ · Top bán chạy & cảnh báo sắp hết · tốc độ bán TB 2 tuần</div></div>
<div class="grid">
 <div class="card"><h2>🏆 Top bán chạy __KIND4__ <span class="tag c">CHENG · thuốc nhuộm</span></h2><div id="cheng"></div></div>
 <div class="card"><h2>🏆 Top bán chạy __KIND4__ <span class="tag k">KALLE</span></h2><div id="kalle"></div></div>
</div>
<div class="card risk" style="margin-top:16px"><h2>⚠️ Sắp hết trong 1 tháng tới</h2><div class="empty" style="margin-bottom:6px">Tốc độ bán cao, tồn hiện không đủ bán 1 tháng — cần nhập thêm.</div><div id="risk"></div></div>
<div class="foot">__FOOT__ · Kho Cheng/Kalle</div>
<script>
var D=__DATA__;
function fmt(n){return n.toLocaleString('vi-VN')}
function sellers(id,arr,cls){var el=document.getElementById(id);if(!arr.length){el.innerHTML='<div class=empty>Không có dữ liệu</div>';return}
 var mx=Math.max.apply(null,arr.map(function(x){return x.qty}))||1;
 el.innerHTML=arr.map(function(x,i){var w=Math.max(4,Math.round(x.qty/mx*100));
  return '<div class=row><div class=r1><div class=nm><span class=rk>'+(i+1)+'</span>'+x.name+'</div><div class=qty>'+fmt(x.qty)+'</div></div>'+
  '<div class=bar><i class="'+cls+'" style="width:'+w+'%"></i></div><div class=tn>tồn '+fmt(x.ton)+(x.days==null?' · đủ bán lâu':(x.days<0?' · <b style="color:#f87171">tồn âm</b>':' · đủ bán ~<b style="color:'+(x.days<7?'#f87171':(x.days<14?'#fbbf24':'#9fb0d0'))+'">'+x.days+' ngày</b>'))+'</div></div>'}).join('')}
sellers('cheng',D.cheng,'bc');sellers('kalle',D.kalle,'bk');
var rk=document.getElementById('risk');
if(!D.risk.length){rk.innerHTML='<div class=empty>Không có mã nào dưới 1 tháng 🎉</div>'}else{
 rk.innerHTML=D.risk.map(function(x){var c=x.days<7?'cr':(x.days<14?'wn':'ye');
  return '<div class="ri '+c+'"><div class=nm>'+x.name+'</div><div class=meta>bán ~<b>'+fmt(x.rate)+'</b>/ngày · tồn <b>'+fmt(x.ton)+'</b></div><div class="dd '+c+'">'+x.days+'<div style="font-size:9px;font-weight:600;color:#9fb0d0">ngày</div></div></div>'}).join('')}
</script></body></html>'''

def build_report(data,is_month):
    kind='tháng' if is_month else 'tuần'
    subs={'__KIND__':kind,'__KINDUP__':kind.upper(),'__KIND2__':('Tháng' if is_month else 'Tuần'),
          '__KIND3__':kind,'__KIND4__':kind,'__ICON__':('🗓️' if is_month else '📅'),
          '__GRAD__':('linear-gradient(135deg,#7c3aed,#c026d3)' if is_month else 'linear-gradient(135deg,#0891b2,#7c3aed)'),
          '__FOOT__':('Báo cáo tháng tự động ngày 1 hàng tháng' if is_month else 'Báo cáo tuần tự động sáng Thứ 2'),
          '__RANGE__':data['range'],'__DATA__':json.dumps(data,ensure_ascii=False)}
    html=TPL
    for k,v in subs.items(): html=html.replace(k,v)
    fn='monthly_report.html' if is_month else 'weekly_report.html'
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)),fn),'w',encoding='utf-8').write(html)

def main():
    is_month=(PERIOD=='month')
    tok=ltoken()
    vn=datetime.timezone(datetime.timedelta(hours=7))
    now=datetime.datetime.now(vn)
    if is_month:   # THÁNG TRƯỚC
        first_this=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        end=first_this - datetime.timedelta(days=1)             # ngày cuối tháng trước
        start=end.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        rng=start.strftime('%m/%Y')
    else:          # TUẦN TRƯỚC (Thứ 2 -> Chủ nhật)
        this_mon=(now - datetime.timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        start=this_mon - datetime.timedelta(days=7)
        end=this_mon - datetime.timedelta(days=1)
        rng=start.strftime('%d/%m')+'–'+end.strftime('%d/%m/%Y')
    def ms(d): return int(d.timestamp()*1000)
    LO=ms(start); HI=ms(end)+86400000-1; NOW_MS=ms(now)
    inv={}
    for it in lsearch(tok,T_SP,['G SKU','Tên sản phẩm','Hãng','Phân loại','Tồn kho Âu Cơ','Kho Mê Linh 1','Kho Mê Linh 2','Thông báo hết hàng']):
        f=it['fields'];g=gt(f.get('G SKU'))
        if not g: continue
        inv[str(g)]={'name':gt(f.get('Tên sản phẩm')) or g,'hang':(gt(f.get('Hãng')) or '—').strip(),
                     'pl':(gt(f.get('Phân loại')) or '').strip(),
                     'ton':fv(f.get('Tồn kho Âu Cơ'))+fv(f.get('Kho Mê Linh 1'))+fv(f.get('Kho Mê Linh 2')),
                     'tb':bool(f.get('Thông báo hết hàng'))}
    from collections import defaultdict as _dd
    per=_dd(float); s14=_dd(float)
    for it in lsearch(tok,T_XK,['G SKU','Số lượng','Ngày đóng gói']):
        f=it['fields'];g=gt(f.get('G SKU'));q=f.get('Số lượng') or 0;dt=f.get('Ngày đóng gói')
        if not g or not isinstance(dt,(int,float)): continue
        g=str(g)
        if LO<=dt<=HI: per[g]+=q
        dd=(NOW_MS-dt)/86400000
        if 0<=dd<14: s14[g]+=q
    rate=lambda g:s14.get(g,0)/14
    dleft=lambda g:(round(inv[g]['ton']/rate(g),1) if rate(g)>0 else None)
    chg=[{'name':inv[g]['name'],'qty':int(per[g]),'ton':int(inv[g]['ton']),'rate':round(rate(g),1),'days':dleft(g)}
         for g in sorted(per,key=lambda x:-per[x]) if inv.get(g,{}).get('hang')=='Cheng' and inv.get(g,{}).get('pl') in DYE_PL][:10]
    kal=[{'name':inv[g]['name'],'qty':int(per[g]),'ton':int(inv[g]['ton']),'rate':round(rate(g),1),'days':dleft(g)}
         for g in sorted(per,key=lambda x:-per[x])
         if inv.get(g,{}).get('hang')=='Kalle' and kalle_top_ok(inv.get(g,{}).get('name'))][:10]
    risk=[]
    for g,v in inv.items():
        if g in TRIO or v.get('tb') or v['hang'] not in ('Cheng','Kalle') or v['pl']=='NVL': continue
        if not kalle_alert_ok(v['name'],v['hang']): continue
        r=rate(g)
        if r>0 and 0<v['ton']<r*30: risk.append({'name':v['name'],'rate':round(r,1),'ton':int(v['ton']),'days':round(v['ton']/r,1)})
    risk=sorted(risk,key=lambda x:x['days'])[:12]
    build_report({'range':rng,'cheng':chg,'kalle':kal,'risk':risk},is_month)
    tot_ch=sum(int(per[g]) for g in per if inv.get(g,{}).get('hang')=='Cheng')
    tot_ka=sum(int(per[g]) for g in per if inv.get(g,{}).get('hang')=='Kalle' and kalle_top_ok(inv.get(g,{}).get('name')))
    kind='THÁNG' if is_month else 'TUẦN'
    fn='monthly_report.html' if is_month else 'weekly_report.html'
    url='https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/'+fn+'?v='+str(int(now.timestamp()))
    print(kind,rng,'| Cheng',tot_ch,'| Kalle',tot_ka,'| risk',len(risk))
    body=(f"**{('🗓️' if is_month else '📅')} Báo cáo bán hàng {kind} — {rng}**\n"
          f"Tổng bán {kind.lower()}: Cheng **{tot_ch:,}** · Kalle **{tot_ka:,}**.\n"
          f"Kèm **{len(risk)} mã sắp hết trong 1 tháng**.\n\n👉 [Xem báo cáo {kind.lower()}]({url})")
    card={'msg_type':'interactive','card':{'config':{'wide_screen_mode':True},
          'header':{'title':{'tag':'plain_text','content':('🗓️' if is_month else '📅')+' Báo cáo bán hàng '+kind.lower()},'template':('purple' if is_month else 'turquoise')},
          'elements':[{'tag':'div','text':{'tag':'lark_md','content':body}},
                      {'tag':'action','actions':[{'tag':'button','text':{'tag':'plain_text','content':'Mở báo cáo '+kind.lower()},'type':'primary','url':url}]}]}}
    try: urllib.request.urlopen(urllib.request.Request(WEBHOOK,data=json.dumps(card).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=30)
    except Exception as e: print('gửi thẻ lỗi:',e)

if __name__=='__main__':
    main()
