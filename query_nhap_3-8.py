# -*- coding: utf-8 -*-
"""Lay so cho bai toan THUC NHAN lo nhap 3/8 -> Kho Me Linh 2.
Voi tung ten SP trong DANH SACH: in ra
  - Ghi so nhap 3/8  (tong So luong o bang Chuyen/Nhap kho, Ngay=3/8, Kho nhap = Me Linh 2)
  - Ton he thong Me Linh 2 hien tai (field 'Kho Me Linh 2' o bang San pham)
  - Xuat tu 3/8 -> nay (tham khao)
Chay tren GitHub Actions. Secret: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN.
ENV tuy chon: QUERY_DATE=YYYY-MM-DD (mac dinh 2026-08-03)
"""
import os, json, datetime, urllib.request, unicodedata, re
from collections import defaultdict

H='https://open.larksuite.com'
APP=os.environ['LARK_APP_ID']; SEC=os.environ['LARK_APP_SECRET']; BASE=os.environ['LARK_APP_TOKEN']
T_SP='tbl7PSQh3Lq5Tlxy'; T_XK='tblIHtLsM4QTMMQJ'; T_CK='tblylArl4EL4AvrX'; T_MH='tblsSoY9HERffH6A'
VN=datetime.timezone(datetime.timedelta(hours=7))
DATE=os.getenv('QUERY_DATE','2026-08-03').strip()
d0=datetime.datetime.strptime(DATE,'%Y-%m-%d').replace(tzinfo=VN)
LO=int(d0.timestamp()*1000); HI=int((d0+datetime.timedelta(days=1)).timestamp()*1000)-1

DANH_SACH=[
 "3 gói nhuộm bọt - nâu lạnh trầm (túi)",
 "3 gói nhuộm bọt - mocha (túi)",
 "3 gói nhuộm bọt - hạt dẻ (túi)",
 "3 gói nhuộm bọt - nâu tây (túi)",
 "3 gói nhuộm bọt - nâu cam (túi)",
 "3 gói nhuộm bọt - nâu lạnh (túi)",
 "3 gói nhuộm bọt - đỏ rượu vang (túi)",
 "3 gói nhuộm bọt - trà lạnh (túi)",
 "5 gói nhuộm bọt - nâu tây (hộp)",
 "5 gói nhuộm bọt - nâu lạnh (hộp)",
 "10 gói nhuộm bọt - nâu lạnh (hộp)",
 "10 gói nhuộm bọt - nâu cam (hộp)",
 "10 gói nhuộm bọt - chocolate (hộp)",
 "10 gói nhuộm bọt - trà lạnh (hộp)",
]

def tok():
    r=urllib.request.Request(H+'/open-apis/auth/v3/tenant_access_token/internal',
        data=json.dumps({'app_id':APP,'app_secret':SEC}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=30))['tenant_access_token']

def lsearch(t,table,fields):
    out=[]; pt=None
    while True:
        url=f'/open-apis/bitable/v1/apps/{BASE}/tables/{table}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        r=urllib.request.Request(H+url,data=json.dumps({'field_names':fields}).encode(),
            headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'},method='POST')
        d=json.load(urllib.request.urlopen(r,timeout=60))['data']
        out+=d.get('items',[])
        if d.get('has_more'): pt=d['page_token']
        else: break
    return out

def gt(v):
    while isinstance(v,dict): v=v.get('value') if 'value' in v else (v.get('text') or '')
    if isinstance(v,list): v=''.join(str(x.get('text') or x.get('name') or '') if isinstance(x,dict) else str(x) for x in v)
    return str(v or '').strip()

def fv(v):
    if isinstance(v,dict) and 'value' in v:
        x=v['value']; v=x[0] if isinstance(x,list) and x else 0
    if isinstance(v,list): v=v[0] if v else 0
    try: return float(str(v).replace(',',''))
    except: return 0.0

def norm(s):
    s=unicodedata.normalize('NFC',str(s or '')).lower().strip()
    s=s.replace('–','-').replace('—','-')
    s=re.sub(r'\s+',' ',s)
    s=re.sub(r'\s*-\s*','-',s)
    return s

def main():
    t=tok()
    # --- ton he thong + quy cach tu T_SP ---
    sp=lsearch(t,T_SP,['G SKU','Tên sản phẩm','Kho Mê Linh 2','Quy cách'])
    by_name={}; by_g={}
    for it in sp:
        f=it['fields']; nm=gt(f.get('Tên sản phẩm'))
        rec={'name':nm,'g':gt(f.get('G SKU')),'ml2':fv(f.get('Kho Mê Linh 2')),'qc':fv(f.get('Quy cách'))}
        if nm: by_name[norm(nm)]=rec
        if rec['g']: by_g[rec['g']]=rec
    # --- nhap 3/8 tu T_MH (bang Mua hang, field 'So nhap') ---
    mh=lsearch(t,T_MH,['Số ĐH','Ngày','Tên SP','Số nhập','Ghi chú'])
    nhap=defaultdict(float); nhap_all=defaultdict(list)
    for it in mh:
        f=it['fields']; dd=f.get('Ngày')
        if not isinstance(dd,(int,float)) or not (LO<=dd<=HI): continue
        nm=gt(f.get('Tên SP')); q=fv(f.get('Số nhập'))
        nhap[norm(nm)]+=q; nhap_all[norm(nm)].append((nm,q,gt(f.get('Số ĐH'))))
    _win=sum(len(v) for v in nhap_all.values())
    print('[debug] So ban ghi Mua hang roi vao ngay %s: %d dong, tong So nhap=%d'%(DATE,_win,int(sum(nhap.values()))))

    def bucket(dd):
        if not isinstance(dd,(int,float)): return None
        if dd<LO: return 'b'      # truoc 3/8
        if dd<=HI: return 'in'    # trong ngay 3/8 (chinh la lo)
        return 'af'               # sau 3/8
    def dfmt(ms):
        return datetime.datetime.fromtimestamp(ms/1000,VN).strftime('%Y-%m-%d') if ms else '?'

    # --- Mua hang (nhap) theo Ten SP, chia truoc / lo 3/8 / sau ---
    mh_b=defaultdict(float); mh_in=defaultdict(float); mh_af=defaultdict(float); mh_min=None
    for it in mh:
        f=it['fields']; dd=f.get('Ngày'); bk=bucket(dd)
        if bk is None: continue
        if mh_min is None or dd<mh_min: mh_min=dd
        n=norm(gt(f.get('Tên SP'))); q=fv(f.get('Số nhập'))
        (mh_b if bk=='b' else mh_in if bk=='in' else mh_af)[n]+=q
    # --- Xuat khoi ML2 (ban+gia cong) theo GSKU ---
    xk=lsearch(t,T_XK,['G SKU','Số lượng','Kho xuất','Ngày đóng gói'])
    xk_b=defaultdict(float); xk_af=defaultdict(float); xk_min=None
    for it in xk:
        f=it['fields']; dd=f.get('Ngày đóng gói')
        if 'mê linh 2' not in norm(gt(f.get('Kho xuất'))): continue
        bk=bucket(dd)
        if bk is None: continue
        if xk_min is None or dd<xk_min: xk_min=dd
        g=gt(f.get('G SKU')); q=fv(f.get('Số lượng'))
        (xk_b if bk=='b' else xk_af)[g]+=q   # 'in'+'af' deu tinh la sau khi nhan
    # --- Chuyen kho lien quan ML2 theo Ten SP ---
    ck=lsearch(t,T_CK,['Ngày','Tên SP','Số lượng','Kho xuất','Kho nhập'])
    cv_b=defaultdict(float); cv_af=defaultdict(float)   # chuyen VE ML2
    cd_b=defaultdict(float); cd_af=defaultdict(float)   # chuyen DI khoi ML2
    for it in ck:
        f=it['fields']; dd=f.get('Ngày'); bk=bucket(dd)
        if bk is None: continue
        kx=norm(gt(f.get('Kho xuất'))); kn=norm(gt(f.get('Kho nhập')))
        n=norm(gt(f.get('Tên SP'))); q=fv(f.get('Số lượng'))
        if 'mê linh 2' in kn or 'ml2' in kn: (cv_b if bk=='b' else cv_af)[n]+=q
        if 'mê linh 2' in kx or 'ml2' in kx: (cd_b if bk=='b' else cd_af)[n]+=q

    def gv(d,n):
        if n in d: return d[n]
        for k,v in d.items():
            if n and (n in k or k in n): return v
        return 0.0

    RECOUNT={
     '1082863':(61,300),'1082893':(120,393),'1082845':(52,330),'1082884':(135,402),
     '1082896':(31,200),'1082872':(185,392),'1082878':(31,473),'1082881':(214,423),
     '1082883':(22,236),'1082871':(27,239),
     '1082870':(42,225),'1082894':(49,66),'1082867':(33,88),'1082879':(93,151),
    }
    QC=48
    print()
    print('== DUNG LAI TON TRUOC 3/8 + THUC NHAN (theo luong nhap-xuat, KHONG dung ton Lookup) ==')
    print('  Du lieu Mua hang som nhat: %s | Xuat ML2 som nhat: %s'%(dfmt(mh_min),dfmt(xk_min)))
    print('  (Ton truoc 3/8 chi dung neu truoc moc nay ML2 = 0)')
    print('-'*146)
    print('| Ten SP | GSKU | Ton kiem lai | Ton truoc 3/8 | Xuat sau 3/8 | Nhap khac sau | Ghi so lo 3/8 | THUC NHAN | Chenh vs ghi so |')
    print('-'*146)
    T={'kl':0,'tt':0,'xa':0,'na':0,'gs':0,'tn':0}
    for name in DANH_SACH:
        n=norm(name); rec=by_name.get(n)
        if not rec:
            cand=[v for k,v in by_name.items() if n in k or k in n]; rec=cand[0] if len(cand)==1 else None
        g=rec['g'] if rec else ''
        th,cai=RECOUNT.get(g,(0,0)); kl=th*QC+cai
        nb=gv(mh_b,n); nin=gv(mh_in,n); naf=gv(mh_af,n)
        cvb=gv(cv_b,n); cvaf=gv(cv_af,n); cdb=gv(cd_b,n); cdaf=gv(cd_af,n)
        xb=xk_b.get(g,0); xaf=xk_af.get(g,0)
        ton_truoc = nb + cvb - xb - cdb
        xuat_after = xaf + cdaf
        nhap_khac_after = naf + cvaf
        tn = kl - ton_truoc + xuat_after - nhap_khac_after
        ch = tn - nin
        for k,vv in (('kl',kl),('tt',ton_truoc),('xa',xuat_after),('na',nhap_khac_after),('gs',nin),('tn',tn)): T[k]+=vv
        print('| %-36s | %-7s | %10d | %11d | %10d | %11d | %11d | %9d | %11d |'%(
              name[:36], g, kl, ton_truoc, xuat_after, nhap_khac_after, nin, tn, ch))
    print('-'*146)
    print('| %-36s | %-7s | %10d | %11d | %10d | %11d | %11d | %9d | %11d |'%(
          'TONG','',T['kl'],T['tt'],T['xa'],T['na'],T['gs'],T['tn'],T['tn']-T['gs']))
    print()
    print('CT: THUC NHAN = Ton kiem lai - Ton truoc 3/8 + Xuat sau 3/8 - Nhap khac sau 3/8')
    print('    Ton truoc 3/8 = Mua hang truoc + Chuyen ve ML2 truoc - Xuat ML2 truoc - Chuyen di truoc (goc 0).')
    print('    "Ghi so lo 3/8" = So nhap da ghi ngay 3/8 (de doi chieu). Chenh = THUC NHAN - Ghi so.')

if __name__=='__main__':
    main()
