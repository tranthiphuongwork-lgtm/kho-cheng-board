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
T_SP='tbl7PSQh3Lq5Tlxy'; T_XK='tblIHtLsM4QTMMQJ'; T_CK='tblylArl4EL4AvrX'
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
    # --- ton he thong tu T_SP ---
    sp=lsearch(t,T_SP,['G SKU','Tên sản phẩm','Kho Mê Linh 2'])
    by_name={}
    for it in sp:
        f=it['fields']; nm=gt(f.get('Tên sản phẩm'))
        if nm: by_name[norm(nm)]={'name':nm,'g':gt(f.get('G SKU')),'ml2':fv(f.get('Kho Mê Linh 2'))}
    # --- nhap 3/8 tu T_CK (theo ten SP, kho nhap ML2) ---
    ck=lsearch(t,T_CK,['Ngày','Loại nhập kho','Tên SP','Số lượng','Kho nhập'])
    nhap=defaultdict(float); nhap_all=defaultdict(list)
    for it in ck:
        f=it['fields']; dd=f.get('Ngày')
        if not isinstance(dd,(int,float)) or not (LO<=dd<=HI): continue
        kn=gt(f.get('Kho nhập'))
        if 'mê linh 2' not in norm(kn) and 'ml2' not in norm(kn): continue
        nm=gt(f.get('Tên SP')); q=fv(f.get('Số lượng'))
        nhap[norm(nm)]+=q; nhap_all[norm(nm)].append((nm,q,gt(f.get('Loại nhập kho'))))
    # --- xuat tu 3/8 -> nay theo GSKU (tham khao) ---
    now_ms=int(datetime.datetime.now(VN).timestamp()*1000)
    xk=lsearch(t,T_XK,['G SKU','Số lượng','Kho xuất','Ngày đóng gói'])
    xuat=defaultdict(float)
    for it in xk:
        f=it['fields']; dd=f.get('Ngày đóng gói')
        if not isinstance(dd,(int,float)) or dd<LO: continue
        if 'mê linh 2' not in norm(gt(f.get('Kho xuất'))): continue
        xuat[gt(f.get('G SKU'))]+=fv(f.get('Số lượng'))

    print('== SO LIEU cho bai toan THUC NHAN lo nhap %s -> Kho Me Linh 2 =='%DATE)
    print('Cot: | Ten SP (danh sach) | Match Base | GSKU | Ghi so nhap 3/8 (C) | Ton ML2 hien tai (G) | Xuat tu 3/8->nay |')
    print('-'*120)
    for name in DANH_SACH:
        n=norm(name)
        rec=by_name.get(n)
        # fuzzy neu khong khop chinh xac
        if not rec:
            cand=[v for k,v in by_name.items() if n in k or k in n]
            rec=cand[0] if len(cand)==1 else None
        g = rec['g'] if rec else ''
        ml2 = int(rec['ml2']) if rec else ''
        mname = rec['name'] if rec else '❌ KHONG KHOP'
        c = int(nhap.get(n,0))
        # neu ten trong T_CK khac, thu match qua nhap_all keys
        if c==0:
            for k,v in nhap.items():
                if n in k or k in n: c=int(v); break
        x = int(xuat.get(g,0)) if g else ''
        print('| %-42s | %-38s | %-6s | %8s | %8s | %8s |'%(name, mname[:38], g, c, ml2, x))
    print('-'*120)
    print('GHI CHU: "Ghi so nhap 3/8" = tong So luong ghi vao bang Nhap/Chuyen kho ngay 3/8, kho nhap Me Linh 2.')
    print('         "Ton ML2 hien tai" = field "Kho Me Linh 2" bang San pham (tai thoi diem chay).')
    print('         Thuc nhan = Ghi so 3/8 + (Ton kiem lai - Ton ML2 hien tai).')

if __name__=='__main__':
    main()
