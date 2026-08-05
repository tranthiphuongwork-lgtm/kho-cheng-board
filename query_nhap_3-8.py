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
    # --- xuat tu 3/8 -> nay theo GSKU (tham khao) ---
    now_ms=int(datetime.datetime.now(VN).timestamp()*1000)
    xk=lsearch(t,T_XK,['G SKU','Số lượng','Kho xuất','Ngày đóng gói'])
    xuat=defaultdict(float)
    for it in xk:
        f=it['fields']; dd=f.get('Ngày đóng gói')
        if not isinstance(dd,(int,float)) or dd<LO: continue
        if 'mê linh 2' not in norm(gt(f.get('Kho xuất'))): continue
        xuat[gt(f.get('G SKU'))]+=fv(f.get('Số lượng'))

    _win=sum(len(v) for v in nhap_all.values())
    print('[debug] So ban ghi Mua hang roi vao ngay %s: %d dong, tong So nhap=%d'%(DATE,_win,int(sum(nhap.values()))))
    # --- dinh nghia field 'Kho Me Linh 2' (formula hay so tay?) ---
    fr=urllib.request.Request(H+f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_SP}/fields?page_size=200',
        headers={'Authorization':'Bearer '+t})
    fdef=json.load(urllib.request.urlopen(fr,timeout=30))['data']['items']
    TYPE={1:'Text',2:'Number',3:'SingleSelect',5:'DateTime',19:'Lookup',20:'Formula',21:'DualLink',22:'Location',23:'GroupChat'}
    print('== DINH NGHIA FIELD TON KHO ==')
    for it in fdef:
        if it['field_name'] in ('Kho Mê Linh 2','Tồn kho Âu Cơ','Kho Mê Linh 1'):
            ty=TYPE.get(it['type'],it['type'])
            fx=''
            pr=it.get('property') or {}
            if isinstance(pr,dict): fx=pr.get('formatter') or pr.get('formula_expression') or pr.get('expression') or ''
            print('  • %-16s type=%-8s %s'%(it['field_name'],ty,('formula: '+str(fx)) if fx else ('property='+str(pr)[:160])))
    # --- chuyen kho Me Linh 2 -> Au Co (T_CK) ---
    ck=lsearch(t,T_CK,['Ngày','Tên SP','Số lượng','Kho xuất','Kho nhập'])
    cve=defaultdict(float); cve_all=defaultdict(float)
    for it in ck:
        f=it['fields']
        kx=norm(gt(f.get('Kho xuất'))); kn=norm(gt(f.get('Kho nhập')))
        if 'mê linh 2' not in kx and 'ml2' not in kx: continue
        if 'âu cơ' not in kn and 'au co' not in kn: continue
        nm=norm(gt(f.get('Tên SP'))); q=fv(f.get('Số lượng')); dd=f.get('Ngày')
        cve_all[nm]+=q
        if isinstance(dd,(int,float)) and dd>=LO: cve[nm]+=q
    # --- so kiem lai thuc te (thung, cai le) theo GSKU ---
    RECOUNT={
     '1082863':(61,300),'1082893':(120,393),'1082845':(52,330),'1082884':(135,402),
     '1082896':(31,200),'1082872':(185,392),'1082878':(31,473),'1082881':(214,423),
     '1082883':(22,236),'1082871':(27,239),
     '1082870':(42,225),'1082894':(49,66),'1082867':(33,88),'1082879':(93,151),
    }
    print()
    print('== KET QUA THUC NHAN lo nhap %s -> Kho Me Linh 2 =='%DATE)
    print('| Ten SP | GSKU | QuyCach | Thung | Cai le | Ton kiem lai | Ghi so 3/8 | Ton ML2 htai | THUC NHAN | Dem sai |')
    print('-'*140)
    tot={'c':0,'kl':0,'tn':0}
    for name in DANH_SACH:
        n=norm(name); rec=by_name.get(n)
        if not rec:
            cand=[v for k,v in by_name.items() if n in k or k in n]
            rec=cand[0] if len(cand)==1 else None
        g = rec['g'] if rec else ''
        ml2 = int(rec['ml2']) if rec else 0
        qc = int(rec['qc']) if rec else 0
        c = int(nhap.get(n,0))
        if c==0:
            for k,v in nhap.items():
                if n in k or k in n: c=int(v); break
        th,cai = RECOUNT.get(g,(0,0))
        kl = th*qc + cai
        tn = c + (kl - ml2)
        ds = kl - ml2
        tot['c']+=c; tot['kl']+=kl; tot['tn']+=tn
        print('| %-38s | %-7s | %5s | %5s | %5s | %10s | %9s | %10s | %9s | %7s |'%(
              name[:38], g, qc, th, cai, kl, c, ml2, tn, ds))
    print('-'*140)
    print('| %-38s | %-7s | %5s | %5s | %5s | %10s | %9s | %10s | %9s | %7s |'%(
          'TONG','','','','',tot['kl'],tot['c'],'',tot['tn'],''))
    print()
    print('CT: Ton kiem lai (cai) = Thung x QuyCach + Cai le.')
    print('    THUC NHAN = Ghi so 3/8 + (Ton kiem lai - Ton ML2 hien tai).')
    print('    Dem sai   = Ton kiem lai - Ton ML2 (duong = dem thieu / thuc nhan nhieu hon ghi so).')

if __name__=='__main__':
    main()
