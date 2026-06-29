# -*- coding: utf-8 -*-
# Chạy trên GitHub Actions 20:00 VN mỗi ngày: đồng bộ Gobox->Lark, dựng board, gửi cảnh báo Lark.
import os,json,re,urllib.request,urllib.parse,urllib.error,datetime,math,time
from collections import defaultdict
LARK_HOST='https://open.larksuite.com'; GB='https://api.gobox.asia'
def gopen(req,timeout=60,tries=6):
    # gọi HTTP có retry khi 429/5xx (Gobox hay chặn tốc độ)
    for i in range(tries):
        try:
            return urllib.request.urlopen(req,timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in (429,500,502,503,504) and i<tries-1: time.sleep(2*(i+1)); continue
            raise
        except urllib.error.URLError:
            if i<tries-1: time.sleep(2*(i+1)); continue
            raise
APP_ID=os.environ['LARK_APP_ID']; APP_SECRET=os.environ['LARK_APP_SECRET']; BASE=os.environ['LARK_APP_TOKEN']
GCID=os.environ['GOBOX_CLIENT_ID']; GSEC=os.environ['GOBOX_CLIENT_SECRET']; WEBHOOK=os.environ['LARK_WEBHOOK']
T_SP='tbl7PSQh3Lq5Tlxy'; T_XK='tblIHtLsM4QTMMQJ'; T_CK='tblylArl4EL4AvrX'; T_HOAN='tblhaZvKxCktFtgW'
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
    return json.load(gopen(urllib.request.Request(GB+'/oauth/token',data=body,headers={'Accept':'application/json'}),30))['access_token']
def gb_all(tok,path,params):
    url=GB+path+'?'+urllib.parse.urlencode(params,doseq=True); H={'Authorization':'Bearer '+tok,'Accept':'application/json'}; out=[];p=0
    while url:
        d=json.load(gopen(urllib.request.Request(url,headers=H),120)); out+=d.get('data',[]);p+=1; time.sleep(0.4)
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
KALLE_KEEP=('dark beauty','first love','venus','jasmine amber','girl power','blue shirt','ladykiller','lady killer')
def kalle_alert_ok(name,hang):
    # Kalle: chỉ cảnh báo hết hàng cho 7 mùi; mùi khác bỏ qua. Hãng khác luôn cảnh báo.
    if (hang or '').strip()!='Kalle': return True
    n=_norm(name)
    return any(k in n for k in KALLE_KEEP)
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
            sku=c[0].strip(); sl=c[3].replace(',','').replace('.','').strip()
            if not sku or not re.match(r'^[+-]?\d+$',sl): continue
            out.append((sku,c[1],int(sl)))
        return out
    a=kv(seg('SECTION 1A','SECTION 1B')); b=kv(seg('SECTION 1B','SECTION 2'))
    s2=[]
    for c in rows(seg('SECTION 2',None)):
        if len(c)<7: continue
        sku=c[0].strip(); nums=[x.replace(',','').replace('.','').strip() for x in [c[3],c[4],c[5],c[6]]]
        if not sku or not all(re.match(r'^[+-]?\d+$',x) for x in nums): continue
        dau,gc,used,left=[int(x) for x in nums]; s2.append((sku,c[1],dau,gc,used,left))
    return a,b,s2
def gb_pending(gtok,ngay):
    # phiếu tạo trong ngày: pend=chưa đóng (status<200), total=đơn không hủy (status!=499)
    wp=gb_all(gtok,'/open/api/warehouse-pickings',{'warehouse_id':WID,'type':3,'source':3,'start_created_date':ngay,'end_created_date':ngay,'limit':1000})
    pend=sum(1 for r in wp if isinstance(r.get('status'),int) and r['status']<200)
    total=sum(1 for r in wp if r.get('status')!=499)
    return pend,total

def sync_gobox(ltok):
    NGAY=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date().isoformat()
    vn=datetime.timezone(datetime.timedelta(hours=7)); DATE_MS=int(datetime.datetime.strptime(NGAY,'%Y-%m-%d').replace(tzinfo=vn).timestamp()*1000)
    if any(it['fields'].get('Ngày đóng gói')==DATE_MS for it in lsearch(ltok,T_XK,['Ngày đóng gói'])):
        return NGAY,{'status':'already'}
    # --- Âu Cơ từ Gobox (giữ nguyên) ---
    gtok=gbtoken()
    pend,total=gb_pending(gtok,NGAY)
    if total==0:
        return NGAY,{'status':'notready'}
    if pend>0:
        return NGAY,{'status':'pending','pending':pend}
    lines=gb_all(gtok,'/open/api/reports/warehouse-export-by-sku',{'start_date':NGAY,'end_date':NGAY,'warehouse_id':WID,'limit':1000})
    wp=gb_all(gtok,'/open/api/warehouse-pickings',{'warehouse_id':WID,'type':3,'source':3,'start_done_date':NGAY,'end_done_date':NGAY,'limit':1000,'include[]':'processer'})
    def pn(r):
        x=r.get('processer')
        if isinstance(x,dict):
            x=x.get('data',x)
            if isinstance(x,dict): return x.get('name')
        return None
    c2p={r['code']:pn(r) for r in wp}
    c2s={r['code']:r.get('status') for r in wp}
    auco=defaultdict(float); ml2gb=defaultdict(float)
    for r in lines:
        if c2s.get(r['code'])==499: continue  # loại đơn hủy
        if c2p.get(r['code'])==MLP: ml2gb[str(r['gsku'])]+=r.get('quantity',0)
        else: auco[str(r['gsku'])]+=r.get('quantity',0)
    # --- Mê Linh 2 từ báo cáo (Bước 1-4) ---
    s1a,s1b,s2=parse_report(NGAY)
    sku2g,sku2name,name2g=_t2g_maps(ltok); tensp=_ck_tensp(ltok)
    unmapped=[]
    xk_recs=[]
    for g,q in auco.items():
        if q>0: xk_recs.append({'Ngày đóng gói':DATE_MS,'G SKU':str(g),'Số lượng':int(q),'Kho xuất':'Kho Âu Cơ','Loại':'Xuất Bán hàng'})
    # Mê Linh 2 Xuất Bán hàng = Gobox tài khoản "Mê Linh In Hàng Loạt" (đã loại đơn hủy)
    for g,q in ml2gb.items():
        if q>0: xk_recs.append({'Ngày đóng gói':DATE_MS,'G SKU':str(g),'Số lượng':int(q),'Kho xuất':'Kho Mê Linh 2','Loại':'Xuất Bán hàng'})
    # + Kho Mê Linh (Gobox kho 65) -> cộng vào Kho Mê Linh 2
    try:
        l65=gb_all(gtok,'/open/api/reports/warehouse-export-by-sku',{'start_date':NGAY,'end_date':NGAY,'warehouse_id':65,'limit':1000})
        a65=defaultdict(float)
        for r in l65: a65[str(r.get('gsku'))]+=r.get('quantity',0)
        for g,q in a65.items():
            if q>0: xk_recs.append({'Ngày đóng gói':DATE_MS,'G SKU':str(g),'Số lượng':int(q),'Kho xuất':'Kho Mê Linh 2','Loại':'Xuất Bán hàng','Ghi chú':'Kho Mê Linh (GB65)'})
        if a65: print('  + Kho Mê Linh (GB65):',len(a65),'GSKU /',int(sum(a65.values())),'đv')
    except Exception as e: print('  kho65 skip:',e)
    # Bước 1 (Xuất Bán hàng ML2) GIỜ lấy từ Gobox MLP ở trên — KHÔNG dùng Section 1A nữa.
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
    return NGAY,{'status':'done','auco':auco_n,'ml2':ml2_n,'ck':len(ck_recs),'unmapped':len(unmapped),'total':len(xk_recs)+len(ck_recs)}

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
        if not kalle_alert_ok(r.get('name'),r.get('hang')): continue
        ton=r['ac_t']+r['ml1_t']+r['ml2_t']; mn=r['min_ac']+r['min_ml2']; rate=mn/45 if mn else 0
        if rate>0 and (ton<=0 or ton<mn):
            al.append((r['name'],ton,r['buy']))
    al.sort(key=lambda x:(x[1]>0,x[1])); neg=sum(1 for a in al if a[1]<=0)
    lines=[('🔴' if t<=0 else '🟠')+f' **{n}** · tồn {t:,} · mua {b:,}' for n,t,b in al[:12]]
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime('%d/%m %H:%M')
    content=f'**⚠️ Cảnh báo hết hàng — Cheng ({now})**\nCó **{len(al)} mã** dưới tối thiểu 1,5 tháng (trong đó **{neg} mã tồn âm**).\n\n'+'\n'.join(lines)+'\n\n_Tồn tối thiểu = (bán+chuyển Shoppe)/ngày × 45._\n📊 [Board](https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/) · [Dashboard](https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/dashboard.html)'
    card={'msg_type':'interactive','card':{'config':{'wide_screen_mode':True},'header':{'title':{'tag':'plain_text','content':'⚠️ Cảnh báo hết hàng — Cheng'},'template':'red'},'elements':[{'tag':'div','text':{'tag':'lark_md','content':content}}]}}
    urllib.request.urlopen(urllib.request.Request(WEBHOOK,data=json.dumps(card).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=30)

def notify_pending(ngay,pend):
    dd='/'.join(reversed(ngay.split('-')))
    body=(f"**⏳ Chưa xuất kho — {dd}**\n"
          f"Gobox còn **{pend} đơn chưa đóng gói xong**. Cần đóng nốt đơn.\n"
          f"Hệ thống sẽ tự kiểm tra lại sau **30 phút**; đóng hết đơn sẽ tự xuất kho.")
    card={'msg_type':'interactive','card':{'config':{'wide_screen_mode':True},'header':{'title':{'tag':'plain_text','content':'⏳ Chưa xuất kho — còn đơn'},'template':'orange'},'elements':[{'tag':'div','text':{'tag':'lark_md','content':body}}]}}
    try: urllib.request.urlopen(urllib.request.Request(WEBHOOK,data=json.dumps(card).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=30)
    except Exception as e: print('notify_pending loi:',e)

DYE_PL={'Dưỡng ít','Dưỡng vừa','Dưỡng nhiều','3 gói bọt','5 gói bọt','10 gói','Màu lẻ'}
BOARD_URL='https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/daily_report.html'
def build_daily_report(data):
    tpl=r'''<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Báo cáo bán hàng __DATE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;background:#0f1729;color:#e6edf6;padding:18px;max-width:1100px;margin:0 auto}
.head{background:linear-gradient(135deg,#2563eb,#7c3aed);border-radius:16px;padding:20px 24px;margin-bottom:18px}
.head h1{font-size:22px;font-weight:800}.head .sub{opacity:.85;font-size:13px;margin-top:4px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:#16203a;border:1px solid #243352;border-radius:14px;padding:16px}
.card h2{font-size:15px;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.tag{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px}
.tag.c{background:#1e3a8a;color:#bfdbfe}.tag.k{background:#5b21b6;color:#ddd6fe}
.row{margin-bottom:10px}
.row .r1{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:13px}
.row .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .rk{display:inline-block;width:20px;color:#7d8db0;font-weight:700}
.row .qty{font-weight:800;font-size:14px}
.row .tn{color:#7d8db0;font-size:11px;white-space:nowrap}
.bar{height:6px;border-radius:6px;margin-top:4px;background:#243352;overflow:hidden}
.bar>i{display:block;height:100%;border-radius:6px}
.bc{background:linear-gradient(90deg,#3b82f6,#60a5fa)}.bk{background:linear-gradient(90deg,#8b5cf6,#a78bfa)}
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
<div class="head"><h1>📊 Báo cáo bán hàng — Kho</h1><div class="sub">Ngày __DATE__ · Top bán chạy & cảnh báo sắp hết · tốc độ bán TB 2 tuần</div></div>
<div class="grid">
 <div class="card"><h2>🏆 Top bán chạy <span class="tag c">CHENG · thuốc nhuộm</span></h2><div id="cheng"></div></div>
 <div class="card"><h2>🏆 Top bán chạy <span class="tag k">KALLE</span></h2><div id="kalle"></div></div>
</div>
<div class="card risk" style="margin-top:16px"><h2>⚠️ Sắp hết trong 1 tuần tới</h2><div class="empty" style="margin-bottom:6px">Tốc độ bán cao, tồn hiện không đủ bán 1 tuần — cần nhập thêm.</div><div id="risk"></div></div>
<div class="foot">Tự động cập nhật sau mỗi lần xuất kho · Kho Cheng/Kalle</div>
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
if(!D.risk.length){rk.innerHTML='<div class=empty>Không có mã nào dưới 1 tuần 🎉</div>'}else{
 rk.innerHTML=D.risk.map(function(x){var c=x.days<2?'cr':(x.days<4?'wn':'ye');
  return '<div class="ri '+c+'"><div class=nm>'+x.name+'</div><div class=meta>bán ~<b>'+fmt(x.rate)+'</b>/ngày · tồn <b>'+fmt(x.ton)+'</b></div><div class="dd '+c+'">'+x.days+'<div style="font-size:9px;font-weight:600;color:#9fb0d0">ngày</div></div></div>'}).join('')}
</script></body></html>'''
    html=tpl.replace('__DATE__',data['date']).replace('__DATA__',json.dumps(data,ensure_ascii=False))
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'daily_report.html'),'w',encoding='utf-8').write(html)
def send_day_reports(tok,ngay):
    DATE_MS=int(datetime.datetime.strptime(ngay,'%Y-%m-%d').replace(tzinfo=datetime.timezone(datetime.timedelta(hours=7))).timestamp()*1000)
    inv={}
    for it in lsearch(tok,T_SP,['G SKU','Tên sản phẩm','Hãng','Phân loại','Tồn kho Âu Cơ','Kho Mê Linh 1','Kho Mê Linh 2','Thông báo hết hàng']):
        f=it['fields'];g=gt(f.get('G SKU'))
        if not g: continue
        inv[str(g)]={'name':gt(f.get('Tên sản phẩm')) or g,'hang':(gt(f.get('Hãng')) or '—').strip(),'pl':(gt(f.get('Phân loại')) or '').strip(),'ton':fv(f.get('Tồn kho Âu Cơ'))+fv(f.get('Kho Mê Linh 1'))+fv(f.get('Kho Mê Linh 2')),'tb':bool(f.get('Thông báo hết hàng'))}
    from collections import defaultdict as _dd
    day=_dd(float);s14=_dd(float)
    for it in lsearch(tok,T_XK,['G SKU','Số lượng','Ngày đóng gói']):
        f=it['fields'];g=gt(f.get('G SKU'));q=f.get('Số lượng') or 0;dt=f.get('Ngày đóng gói')
        if not g or not isinstance(dt,(int,float)): continue
        g=str(g)
        if dt==DATE_MS: day[g]+=q
        dd=(DATE_MS-dt)/86400000
        if 0<=dd<14: s14[g]+=q
    rate=lambda g:s14.get(g,0)/14
    dleft=lambda g:(round(inv[g]['ton']/rate(g),1) if rate(g)>0 else None)
    chg=[{'name':inv[g]['name'],'qty':int(day[g]),'ton':int(inv[g]['ton']),'rate':round(rate(g),1),'days':dleft(g)} for g in sorted(day,key=lambda x:-day[x]) if inv.get(g,{}).get('hang')=='Cheng' and inv.get(g,{}).get('pl') in DYE_PL][:10]
    kal=[{'name':inv[g]['name'],'qty':int(day[g]),'ton':int(inv[g]['ton']),'rate':round(rate(g),1),'days':dleft(g)} for g in sorted(day,key=lambda x:-day[x]) if inv.get(g,{}).get('hang')=='Kalle'][:10]
    risk=[]
    for g,v in inv.items():
        if g in TRIO or v.get('tb') or v['hang'] not in ('Cheng','Kalle') or v['pl']=='NVL': continue
        if not kalle_alert_ok(v['name'],v['hang']): continue
        r=rate(g)
        if r>0 and 0<v['ton']<r*7: risk.append({'name':v['name'],'rate':round(r,1),'ton':int(v['ton']),'days':round(v['ton']/r,1)})
    risk=sorted(risk,key=lambda x:-x['rate'])[:10]
    dd='/'.join(reversed(ngay.split('-')))
    build_daily_report({'date':dd,'cheng':chg,'kalle':kal,'risk':risk})
    nrisk=len(risk)
    url=BOARD_URL+'?v='+str(int(datetime.datetime.now().timestamp()))
    body=f"**📊 Báo cáo bán hàng — {dd}**\nTop bán chạy Cheng (thuốc nhuộm) & Kalle, kèm **{nrisk} mã sắp hết trong 1 tuần**.\n\n👉 [Xem board chi tiết]({url})"
    card={'msg_type':'interactive','card':{'config':{'wide_screen_mode':True},'header':{'title':{'tag':'plain_text','content':'📊 Báo cáo bán hàng'},'template':'blue'},'elements':[{'tag':'div','text':{'tag':'lark_md','content':body}},{'tag':'action','actions':[{'tag':'button','text':{'tag':'plain_text','content':'📊 Mở board'},'type':'primary','url':url}]}]}}
    try: urllib.request.urlopen(urllib.request.Request(WEBHOOK,data=json.dumps(card).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=30)
    except Exception as e: print('send_day_reports loi:',e)

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

def sync_hanghoan(ltok,ngay):
    DATE_MS=int(datetime.datetime.strptime(ngay,'%Y-%m-%d').replace(tzinfo=datetime.timezone(datetime.timedelta(hours=7))).timestamp()*1000)
    gtok=gbtoken()
    from collections import defaultdict as _dd
    qty=_dd(float);pg=1
    while pg<=80:
        url=GB+'/open/api/orders?'+urllib.parse.urlencode({'warehouse_id':WID,'is_return':1,'limit':200,'page':pg,'include[]':'items'})
        d=json.load(gopen(urllib.request.Request(url,headers={'Authorization':'Bearer '+gtok,'Accept':'application/json'}),60))
        data=d.get('data',[])
        if not data: break
        recent=False
        for r in data:
            dmy=(r.get('update_time') or '')[:10]
            try: dd,mm,yy=dmy.split('-'); iso=f'{yy}-{mm}-{dd}'
            except: continue
            if iso>=ngay: recent=True
            if r.get('return_status_warehouse')==1 and iso==ngay:
                for it in (r.get('items') or {}).get('data',[]):
                    sk=(it.get('sku_code') or '').strip().lower(); q=it.get('quantity') or 0
                    if sk: qty[sk]+=q
        if not recent and pg>4: break
        if not d.get('meta',{}).get('cursor',{}).get('next'): break
        pg+=1
    sku2g,_,_=_t2g_maps(ltok); recs=[];un=0
    for sk,q in qty.items():
        g=sku2g.get(sk)
        if not g: un+=1; continue
        if q>0: recs.append({'Ngày đóng gói':DATE_MS,'G SKU':str(g),'Số lượng':int(q),'Ghi chú':'Hàng hoàn (Gobox)'})
    ex=[it['record_id'] for it in lsearch(ltok,T_HOAN,['Ngày đóng gói']) if it['fields'].get('Ngày đóng gói')==DATE_MS]
    for i in range(0,len(ex),500): lpost(ltok,f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_HOAN}/records/batch_delete',{'records':ex[i:i+500]})
    for i in range(0,len(recs),500): lpost(ltok,f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_HOAN}/records/batch_create',{'records':[{'fields':x} for x in recs[i:i+500]]})
    print('  Hàng hoàn %s: %d SKU / %d sp (xoá cũ %d, chưa map %d)'%(ngay,len(recs),int(sum(x['Số lượng'] for x in recs)),len(ex),un))
    return len(recs)

if __name__=='__main__':
    vn=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    mins=vn.hour*60+vn.minute
    if not (18*60+25 <= mins <= 23*60):
        print('Ngoài khung 18h30–23h VN (%02d:%02d) -> bỏ qua.'%(vn.hour,vn.minute))
        raise SystemExit
    ltok=ltoken()
    ngay,det=sync_gobox(ltok)
    st=det.get('status'); print('Ngày',ngay,st,det)
    if st=='already':
        print('Đã xuất kho hôm nay rồi -> bỏ qua.')
    elif st=='notready':
        print('Chưa có đơn nào trong ngày -> bỏ qua (chưa tới giờ đóng).')
    elif st=='pending':
        notify_pending(ngay,det['pending'])
    else:
        notify_done(ngay,det)
        try: send_day_reports(ltok,ngay)
        except Exception as e: print('reports loi:',e)
        try: sync_hanghoan(ltok,ngay)
        except Exception as e: print('hàng hoàn loi:',e)
        rows=compute(ltok); build_index(rows); alert(ltok,rows)
        print('Xuất kho + board + cảnh báo xong. Mã đề xuất:',len(rows))
