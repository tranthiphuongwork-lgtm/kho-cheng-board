# -*- coding: utf-8 -*-
# Chạy trên GitHub Actions 20:00 VN mỗi ngày: đồng bộ Gobox->Lark, dựng board, gửi cảnh báo Lark.
import os,json,re,urllib.request,urllib.parse,datetime,math
from collections import defaultdict
LARK_HOST='https://open.larksuite.com'; GB='https://api.gobox.asia'
APP_ID=os.environ['LARK_APP_ID']; APP_SECRET=os.environ['LARK_APP_SECRET']; BASE=os.environ['LARK_APP_TOKEN']
GCID=os.environ['GOBOX_CLIENT_ID']; GSEC=os.environ['GOBOX_CLIENT_SECRET']; WEBHOOK=os.environ['LARK_WEBHOOK']
T_SP='tbl7PSQh3Lq5Tlxy'; T_XK='tblIHtLsM4QTMMQJ'; T_CK='tblylArl4EL4AvrX'
WID='32'; COVER=45; MELINH_RPT='https://melinh-lark-relay.hungnv21295.workers.dev'; MELINH_TOKEN='melinh-share-2026'; TRIO=['1082704','1082694','1082699']; MLP='Mê Linh In Hàng Loạt'

def ltoken():
    r=urllib.request.Request(LARK_HOST+'/open-apis/auth/v3/tenant_access_token/internal',data=json.dumps({'app_id':APP_ID,'app_secret':APP_SECRET}).encode(),headers={'Content-Type':'application/json'},method='POST')
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
    r=urllib.request.Request(LARK_HOST+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+tok,'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=60))
def lsearch(tok,tid,fields):
    out=[];pt=None
    while True:
        url=LARK_HOST+f'/open-apis/bitable/v1/apps/{BASE}/tables/{tid}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        d=lpost(tok,url.replace(LARK_HOST,''),{'page_size':500,'field_names':fields})
        out+=d['data'].get('items',[])
        if d['data'].get('has_more'): pt=d['data']['page_token']
        else: break
    return out
def gbtoken():
    body=urllib.parse.urlencode({'grant_type':'client_credentials','client_id':GCID,'client_secret':GSEC}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(GB+'/oauth/token',data=body,headers={'Accept':'application/json'}),timeout=30))['access_token']
def gb_all(tok,path,params):
    url=GB+path+'?'+urllib.parse.urlencode(params,doseq=True); H={'Authorization':'Bearer '+tok,'Accept':'application/json'}; out=[];p=0
    while url:
        d=json.load(urllib.request.urlopen(urllib.request.Request(url,headers=H),timeout=120)); out+=d.get('data',[]);p+=1
        url=d.get('meta',{}).get('cursor',{}).get('next')
        if p>80:break
    return out

def _t2g_maps(tok):
    sku2g={};sku2name={};name2g={}
    for it in lsearch(tok,T_SP,['SKU','G SKU','Tên sản phẩm']):
        f=it['fields'];sk=gt(f.get('SKU'));g=gt(f.get('G SKU'));nm=gt(f.get('Tên sản phẩm'))
        if g:
            g=str(g)
            if nm: name2g[_norm(nm)]=g
            if sk: sku2g[str(sk).strip().lower()]=g; 
            if sk and nm: sku2name[str(sk).strip().lower()]=nm
    return sku2g,sku2name,name2g
def _norm(s): return re.sub(r'\s+',' ',(s or '').strip()).lower()
def _ck_tensp(tok):
    r=urllib.request.Request(LARK_HOST+f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_CK}/fields?page_size=200',headers={'Authorization':'Bearer '+tok})
    for f in json.load(urllib.request.urlopen(r,timeout=40))['data']['items']:
        if f['field_name']=='Tên SP': return {_norm(o['name']):o['name'] for o in (f.get('property') or {}).get('options',[])}
    return {}
def _cells(tr): return [re.sub('<[^>]+>','',c).replace('&amp;','&').strip() for c in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
def parse_report(ngay):
    # trả (s1a, s1b, s2): s1a/s1b=[(sku,name,sl)], s2=[(sku,name,dau,gc,used,left)]
    url=f'{MELINH_RPT}/nvl-report/{ngay}?token={MELINH_TOKEN}'
    try: h=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=40).read().decode('utf-8','ignore')
    except Exception: return [],[],[]
    def seg(a,b):
        i=h.find(a); j=h.find(b) if b else len(h); return h[i:j] if i>=0 else ''
    def rows(s): return [_cells(tr) for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',s,re.S)]
    def kv(s):
        out=[]
        for c in rows(s):
            if len(c)<4: continue
            sku=c[0].strip(); sl=c[3].replace(',','').strip()
            if not sku or not re.match(r'^[+-]?\d+$',sl): continue
            out.append((sku,c[1],int(sl)))
        return out
    a=kv(seg('SECTION 1A','SECTION 1B')); b=kv(seg('SECTION 1B','SECTION 2'))
    s2=[]
    for c in rows(seg('SECTION 2',None)):
        if len(c)<7: continue
        sku=c[0].strip(); nums=[c[3],c[4],c[5],c[6]]
        if not sku or not all(re.match(r'^[+-]?\d+$',x.replace(',','').strip()) for x in nums): continue
        dau,gc,used,left=[int(x.replace(',','')) for x in nums]; s2.append((sku,c[1],dau,gc,used,left))
    return a,b,s2
def sync_gobox(ltok):
    NGAY=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date().isoformat()
    vn=datetime.timezone(datetime.timedelta(hours=7)); DATE_MS=int(datetime.datetime.strptime(NGAY,'%Y-%m-%d').replace(tzinfo=vn).timestamp()*1000)
    # --- Âu Cơ từ Gobox (giữ nguyên) ---
    gtok=gbtoken()
    lines=gb_all(gtok,'/open/api/reports/warehouse-export-by-sku',{'start_date':NGAY,'end_date':NGAY,'warehouse_id':WID,'limit':1000})
    wp=gb_all(gtok,'/open/api/warehouse-pickings',{'warehouse_id':WID,'type':3,'source':3,'start_done_date':NGAY,'end_done_date':NGAY,'limit':1000,'include[]':'processer'})
    def pn(r):
        x=r.get('processer')
        if isinstance(x,dict):
            x=x.get('data',x)
            if isinstance(x,dict): return x.get('name')
        return None
    c2p={r['code']:pn(r) for r in wp}
    auco=defaultdict(float)
    for r in lines:
        if c2p.get(r['code'])!=MLP: auco[str(r['gsku'])]+=r.get('quantity',0)
    # --- Mê Linh 2 từ báo cáo (Bước 1-4) ---
    s1a,s1b,s2=parse_report(NGAY)
    sku2g,sku2name,name2g=_t2g_maps(ltok); tensp=_ck_tensp(ltok)
    unmapped=[]
    xk_recs=[]
    for g,q in auco.items():
        if q>0: xk_recs.append({'Ngày đóng gói':DATE_MS,'G SKU':str(g),'Số lượng':int(q),'Kho xuất':'Kho Âu Cơ'})
    # Bước 1: Section 1A -> ML2 Xuất Bán hàng
    for sku,name,qty in s1a:
        g=sku2g.get(sku.lower()) or name2g.get(_norm(name))
        if not g: unmapped.append(('1A',sku,name,qty)); continue
        if qty>0: xk_recs.append({'Ngày đóng gói':DATE_MS,'G SKU':str(g),'Số lượng':int(qty),'Kho xuất':'Kho Mê Linh 2','Loại':'Xuất Bán hàng'})
    # Bước 2: Section 1B -> ML2 Xuất Gia công
    for sku,name,qty in s1b:
        g=sku2g.get(sku.lower()) or name2g.get(_norm(name))
        if not g: unmapped.append(('1B',sku,name,qty)); continue
        if qty>0: xk_recs.append({'Ngày đóng gói':DATE_MS,'G SKU':str(g),'Số lượng':int(qty),'Kho xuất':'Kho Mê Linh 2','Loại':'Xuất Gia công'})
    # Bước 4: Section 2 -Đã dùng -> ML2 Xuất Bán hàng, G SKU=SKU combo
    for sku,name,dau,gc,used,left in s2:
        if used<0: xk_recs.append({'Ngày đóng gói':DATE_MS,'G SKU':sku,'Số lượng':int(abs(used)),'Kho xuất':'Kho Mê Linh 2','Loại':'Xuất Bán hàng'})
    # Bước 3: Section 2 +Gia công -> Chuyển kho Nhập combo
    ck_recs=[]
    for sku,name,dau,gc,used,left in s2:
        if gc<=0: continue
        opt=tensp.get(_norm(name)) or tensp.get(_norm(sku2name.get(sku.lower())))
        if not opt: unmapped.append(('S2+GC',sku,name,gc)); continue
        ck_recs.append({'Ngày':DATE_MS,'Loại nhập kho':'Nhập combo','Tên SP':opt,'Số lượng':int(gc),'Kho nhập':'Mê Linh 2'})
    # --- Dedup + ghi Xuất kho (xoá hết record ngày này) ---
    ex=[it['record_id'] for it in lsearch(ltok,T_XK,['Ngày đóng gói']) if it['fields'].get('Ngày đóng gói')==DATE_MS]
    for i in range(0,len(ex),500): lpost(ltok,f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_XK}/records/batch_delete',{'records':ex[i:i+500]})
    for i in range(0,len(xk_recs),500): lpost(ltok,f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_XK}/records/batch_create',{'records':[{'fields':r} for r in xk_recs[i:i+500]]})
    # --- Dedup + ghi Chuyển kho (chỉ Nhập combo ngày này) ---
    exc=[it['record_id'] for it in lsearch(ltok,T_CK,['Ngày','Loại nhập kho']) if it['fields'].get('Ngày')==DATE_MS and it['fields'].get('Loại nhập kho')=='Nhập combo']
    for i in range(0,len(exc),500): lpost(ltok,f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_CK}/records/batch_delete',{'records':exc[i:i+500]})
    for i in range(0,len(ck_recs),500): lpost(ltok,f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_CK}/records/batch_create',{'records':[{'fields':r} for r in ck_recs[i:i+500]]})
    auco_n=sum(1 for q in auco.values() if q>0); ml2_n=len(xk_recs)-auco_n
    print(f'  ÂuCơ={auco_n} | ML2={ml2_n} rec | ChuyểnKho(NhậpCombo)={len(ck_recs)} rec | chưa map={len(unmapped)}')
    if unmapped: print('  chưa map:',unmapped[:10])
    return NGAY,{'auco':auco_n,'ml2':ml2_n,'ck':len(ck_recs),'unmapped':len(unmapped),'total':len(xk_recs)+len(ck_recs)}

def shopee_rates(tok):
    out=lsearch(tok,T_CK,['Kho nhập','Kho xuất','G SKU','Số lượng','Ngày'])
    now=datetime.datetime.now().timestamp()*1000; res={}
    for it in out:
        f=it['fields']
        if f.get('Kho nhập')!='Shoppe': continue
        d=f.get('Ngày')
        if isinstance(d,(int,float)) and (now-d)>30*86400*1000: continue
        gv=f.get('G SKU')
        if isinstance(gv,dict): gv=gv.get('value')
        g=(''.join(x.get('text','') for x in gv if isinstance(x,dict)) if isinstance(gv,list) else (str(gv) if gv else ''))
        if not g: continue
        r=res.setdefault(g,{'ac':0.0,'ml2':0.0})
        if f.get('Kho xuất')=='Mê Linh 2': r['ml2']+=f.get('Số lượng') or 0
        else: r['ac']+=f.get('Số lượng') or 0
    for g in res: res[g]['ac']/=30; res[g]['ml2']/=30
    return res

def may_cache():
    p=os.path.join(os.path.dirname(os.path.abspath(__file__)),'may_wh_cache.json')
    try: return json.load(open(p,encoding='utf-8'))
    except: return {}

def compute(tok):
    may=may_cache(); shopee=shopee_rates(tok)
    tp=lsearch(tok,T_SP,['G SKU','Tên sản phẩm','Phân loại','Tồn kho Âu Cơ','Kho Mê Linh 1','Kho Mê Linh 2','Hàng dự kiến về','Quy cách','Hãng'])
    inv={}
    for it in tp:
        f=it['fields'];g=gt(f.get('G SKU'))
        if not g: continue
        inv[str(g)]={'name':gt(f.get('Tên sản phẩm')),'cat':gt(f.get('Phân loại')) or '','hang':(gt(f.get('Hãng')) or '—').strip() or '—','qc':fv(f.get('Quy cách')),'ve':fv(f.get('Hàng dự kiến về')),'ac':fv(f.get('Tồn kho Âu Cơ')),'ml1':fv(f.get('Kho Mê Linh 1')),'ml2':fv(f.get('Kho Mê Linh 2'))}
    xk=lsearch(tok,T_XK,['G SKU','Số lượng','Kho xuất','Ngày đóng gói'])
    salesw=defaultdict(lambda:defaultdict(float));days=set();now=datetime.datetime.now().timestamp()*1000;q7=defaultdict(float)
    for it in xk:
        f=it['fields'];g=gt(f.get('G SKU'));q=f.get('Số lượng') or 0;k=f.get('Kho xuất');d=f.get('Ngày đóng gói')
        if isinstance(d,(int,float)): days.add(d)
        if g and k: salesw[g][k]+=q
        if g and isinstance(d,(int,float)) and (now-d)<=7*86400*1000: q7[g]+=q
    NDW=max(1,len(days));NDM=31
    def wk(g,k): return salesw.get(g,{}).get(k,0)
    def mo(g,k):
        m=may.get(g,{}); return m.get(k,0) if isinstance(m,dict) else 0
    def shp(g,k): return shopee.get(g,{}).get(k,0)
    items={}
    for g in set(inv)|set(salesw)|set(may):
        if g in TRIO: continue
        v=inv.get(g,{})
        items[g]={'name':v.get('name') or g,'cat':v.get('cat') or '','hang':v.get('hang') or '—','qc':v.get('qc',0),'ve':v.get('ve',0),'ac_t':v.get('ac',0),'ml1_t':v.get('ml1',0),'ml2_t':v.get('ml2',0),'ac_wk':wk(g,'Kho Âu Cơ'),'ml2_wk':wk(g,'Kho Mê Linh 2'),'ac_mo':mo(g,'ac'),'ml2_mo':mo(g,'ml2'),'sh_ac':shp(g,'ac'),'sh_ml2':shp(g,'ml2')}
    def ts(fn): return sum(fn(g) for g in TRIO)
    items['POOL_U']={'name':'Ủ ngẫu nhiên + hồng + tím (gộp)','cat':'Ziemlich','hang':'Cheng','qc':50,'ve':ts(lambda g:inv.get(g,{}).get('ve',0)),'ac_t':ts(lambda g:inv.get(g,{}).get('ac',0)),'ml1_t':ts(lambda g:inv.get(g,{}).get('ml1',0)),'ml2_t':ts(lambda g:inv.get(g,{}).get('ml2',0)),'ac_wk':ts(lambda g:wk(g,'Kho Âu Cơ')),'ml2_wk':ts(lambda g:wk(g,'Kho Mê Linh 2')),'ac_mo':ts(lambda g:mo(g,'ac')),'ml2_mo':ts(lambda g:mo(g,'ml2')),'sh_ac':ts(lambda g:shp(g,'ac')),'sh_ml2':ts(lambda g:shp(g,'ml2'))}
    rows=[]
    for g,v in items.items():
        C=45 if v['hang']=='Kalle' else COVER
        ar=max(v['ac_wk']/NDW,v['ac_mo']/NDM)+v['sh_ac']; mr=max(v['ml2_wk']/NDW,v['ml2_mo']/NDM)+v['sh_ml2']
        mac=math.ceil(ar*C);mml=math.ceil(mr*C);q=v['qc']
        whs={'Âu Cơ':(v['ac_t'],mac),'Mê Linh 1':(v['ml1_t'],0),'Mê Linh 2':(v['ml2_t'],mml)}
        dfc={k:max(0,m-t) for k,(t,m) in whs.items()};sur={k:max(0,t-m) for k,(t,m) in whs.items()};tf=[]
        for dst in ['Âu Cơ','Mê Linh 2']:
            need=dfc[dst]
            if need<=0: continue
            for src in ['Mê Linh 1','Mê Linh 2','Âu Cơ']:
                if src==dst: continue
                av=sur[src]
                if av<=0: continue
                mv=min(need,av)
                if q>0: mv=math.floor(mv/q)*q
                if mv>0: tf.append((src,dst,int(mv)));sur[src]-=mv;need-=mv
                if need<=0: break
            dfc[dst]=need
        rem=dfc['Âu Cơ']+dfc['Mê Linh 2'];braw=max(0,rem-v['ve'])
        if braw<=0: buy=0;bx=0
        elif q>0: bx=math.ceil(braw/q);buy=int(bx*q)
        else: bx=None;buy=int(math.ceil(braw))
        if not tf and buy<=0: continue
        rows.append({'name':v['name'],'cat':v['cat'],'hang':v['hang'],'qc':int(q),'ve':int(v['ve']),'cover':C,'ac_t':int(v['ac_t']),'ml1_t':int(v['ml1_t']),'ml2_t':int(v['ml2_t']),'min_ac':mac,'min_ml2':mml,'transfers':[[s,d,m] for s,d,m in tf],'buy':buy,'boxes':bx,'tfqty':sum(m for _,_,m in tf)})
    rows.sort(key=lambda r:-(r['buy']+r['tfqty']))
    return rows

def build_index(rows):
    base=os.path.dirname(os.path.abspath(__file__))
    tpl=open(os.path.join(base,'board_template.html'),encoding='utf-8').read()
    today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime('%d/%m/%Y')
    html=tpl.replace('__CC__','45').replace('__CK__','45').replace('__DATE__',today).replace('__DATA__',json.dumps(rows,ensure_ascii=False))
    open(os.path.join(base,'index.html'),'w',encoding='utf-8').write(html)

def alert(tok,rows):
    al=[]
    for r in rows:
        ton=r['ac_t']+r['ml1_t']+r['ml2_t']; mn=r['min_ac']+r['min_ml2']; rate=mn/45 if mn else 0
        if rate>0 and (ton<=0 or ton<mn):
            al.append((r['name'],ton,r['buy']))
    al.sort(key=lambda x:(x[1]>0,x[1])); neg=sum(1 for a in al if a[1]<=0)
    lines=[('🔴' if t<=0 else '🟠')+f' **{n}** · tồn {t:,} · mua {b:,}' for n,t,b in al[:12]]
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime('%d/%m %H:%M')
    content=f'**⚠️ Cảnh báo hết hàng — Cheng ({now})**\nCó **{len(al)} mã** dưới tối thiểu 1,5 tháng (trong đó **{neg} mã tồn âm**).\n\n'+'\n'.join(lines)+'\n\n_Tồn tối thiểu = (bán+chuyển Shoppe)/ngày × 45._\n📊 [Board](https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/) · [Dashboard](https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/dashboard.html)'
    card={'msg_type':'interactive','card':{'config':{'wide_screen_mode':True},'header':{'title':{'tag':'plain_text','content':'⚠️ Cảnh báo hết hàng — Cheng'},'template':'red'},'elements':[{'tag':'div','text':{'tag':'lark_md','content':content}}]}}
    urllib.request.urlopen(urllib.request.Request(WEBHOOK,data=json.dumps(card).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=30)

def notify_done(ngay,d):
    dd='/'.join(reversed(ngay.split('-')))
    body=(f"**✅ Đã hoàn tất nhập/xuất kho — {dd}**\n"
          f"• Xuất kho Âu Cơ: **{d['auco']}** mã\n"
          f"• Xuất kho Mê Linh 2 (báo cáo): **{d['ml2']}** dòng\n"
          f"• Nhập combo (Chuyển kho): **{d['ck']}** dòng")
    if d['unmapped']: body+=f"\n• ⚠️ Chưa map được: **{d['unmapped']}** mã (cần kiểm tra)"
    body+="\n\n📊 [Board](https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/)"
    card={'msg_type':'interactive','card':{'config':{'wide_screen_mode':True},'header':{'title':{'tag':'plain_text','content':'✅ Nhập/Xuất kho xong'},'template':'green'},'elements':[{'tag':'div','text':{'tag':'lark_md','content':body}}]}}
    try: urllib.request.urlopen(urllib.request.Request(WEBHOOK,data=json.dumps(card).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=30)
    except Exception as e: print('notify_done lỗi:',e)

if __name__=='__main__':
    ltok=ltoken()
    ngay,det=sync_gobox(ltok)
    print('Đồng bộ ngày',ngay,':',det)
    notify_done(ngay,det)
    rows=compute(ltok)
    build_index(rows)
    alert(ltok,rows)
    print('Board cập nhật + cảnh báo đã gửi. Số mã đề xuất:',len(rows))
