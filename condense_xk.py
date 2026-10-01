# -*- coding: utf-8 -*-
"""
DỒN NÉN bảng Xuất kho theo THÁNG — chạy ngày 5 hàng tháng, nén dữ liệu THÁNG TRƯỚC.
Gộp toàn bộ bản ghi chi tiết của tháng đích thành 1 dòng tổng /(kho × loại × G SKU)
(cộng dồn nếu dòng tổng đã có) rồi xoá chi tiết → bảng không chạm giới hạn 20.000.

- Chỉ thao tác Lark Base, KHÔNG cần Gobox.
- Idempotent: chạy lại cùng tháng không gây trùng (tháng đã nén thì không còn chi tiết).
- Mặc định nén THÁNG LIỀN TRƯỚC ngày chạy. Đặt MONTH=YYYY-MM để nén tháng cụ thể (bù).

Chạy trên GitHub Actions. Secret: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN.
ENV tuỳ chọn: MONTH=YYYY-MM, DRY_RUN=1 (chỉ xem).
"""
import os, json, datetime, time, calendar, urllib.request, urllib.error
from collections import defaultdict

H='https://open.larksuite.com'
APP=os.environ['LARK_APP_ID']; SEC=os.environ['LARK_APP_SECRET']; BASE=os.environ['LARK_APP_TOKEN']
T_XK='tblIHtLsM4QTMMQJ'
TAG='Tổng tháng (đã gộp)'
BK_PREFIX='XK_backup_'   # moi thang mot bang: XK_backup_YYYY-MM
VN=datetime.timezone(datetime.timedelta(hours=7))
DRY_RUN=(os.getenv('DRY_RUN') or '').strip() in ('1','true','yes')


def tok():
    r=urllib.request.Request(H+'/open-apis/auth/v3/tenant_access_token/internal',
        data=json.dumps({'app_id':APP,'app_secret':SEC}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=30))['tenant_access_token']

def api(t, method, path, body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(H+path, data=data,
        headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'}, method=method)
    try: return json.load(urllib.request.urlopen(r,timeout=60))
    except urllib.error.HTTPError as e: return {'_http':e.code,'body':e.read().decode()[:300]}

def gt(v):
    while isinstance(v,dict): v=v.get('value') if 'value' in v else (v.get('text') or '')
    if isinstance(v,list): v=''.join(str(x.get('text') or x.get('name') or '') if isinstance(x,dict) else str(x) for x in v)
    return str(v or '').strip()

def num(v):
    if isinstance(v,dict) and 'value' in v:
        x=v['value']; v=x[0] if isinstance(x,list) and x else 0
    if isinstance(v,list): v=v[0] if v else 0
    try: return float(str(v).replace(',',''))
    except: return 0.0

def list_tables(t):
    out=[]; pt=None
    while True:
        url=f'/open-apis/bitable/v1/apps/{BASE}/tables?page_size=100'+(('&page_token='+pt) if pt else '')
        d=api(t,'GET',url)
        if d.get('_http') or d.get('code') not in (0,None): raise SystemExit('Liệt kê bảng lỗi: %s'%d)
        out+=d['data'].get('items',[])
        if d['data'].get('has_more'): pt=d['data']['page_token']
        else: break
    return out

def ensure_backup_table(t, name):
    """Tra ve (table_id, vua_tao_moi). Neu bang da co thi dung lai bang do."""
    for it in list_tables(t):
        if it['name']==name: return it['table_id'], False
    # Cot dau tien la cot chinh -> phai la kieu van ban.
    body={'table':{'name':name,'fields':[
        {'field_name':'G SKU','type':1},
        {'field_name':'Ngày đóng gói','type':5},
        {'field_name':'Số lượng','type':2},
        {'field_name':'Kho xuất','type':1},
        {'field_name':'Loại','type':1},
        {'field_name':'Ghi chú','type':1},
    ]}}
    d=api(t,'POST',f'/open-apis/bitable/v1/apps/{BASE}/tables',body)
    if d.get('_http') or d.get('code')!=0: raise SystemExit('Tạo bảng backup lỗi: %s'%d)
    return d['data']['table_id'], True

def write_backup(t, tid, rows):
    """Ghi cac dong chi tiet vao bang backup. Tra ve so dong da ghi thuc te."""
    n=0
    for i in range(0,len(rows),500):
        d=api(t,'POST',f'/open-apis/bitable/v1/apps/{BASE}/tables/{tid}/records/batch_create',
              {'records':[{'fields':r} for r in rows[i:i+500]]})
        if d.get('_http') or d.get('code')!=0: raise SystemExit('Ghi backup lỗi: %s'%d)
        n+=len(d['data']['records']); time.sleep(0.3)
    return n

def search_all(t):
    out=[]; pt=None
    fields=['Ngày đóng gói','G SKU','Số lượng','Kho xuất','Loại','Ghi chú']
    while True:
        url=f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_XK}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        d=api(t,'POST',url,{'field_names':fields})
        if d.get('_http'): raise SystemExit('Đọc Base lỗi: %s'%d)
        d=d['data']; out+=d.get('items',[])
        if d.get('has_more'): pt=d['page_token']
        else: break
    return out

def target_month():
    m=os.getenv('MONTH','').strip()
    if m:
        y,mo=map(int,m.split('-')); return y,mo
    now=datetime.datetime.now(VN)
    first=now.replace(day=1)
    prev=first - datetime.timedelta(days=1)   # ngày cuối tháng trước
    return prev.year, prev.month

def main():
    t=tok()
    y,mo=target_month()
    lo=int(datetime.datetime(y,mo,1,tzinfo=VN).timestamp()*1000)
    last=calendar.monthrange(y,mo)[1]
    hi=int(datetime.datetime(y,mo,last,23,59,59,tzinfo=VN).timestamp()*1000)
    eom=int(datetime.datetime(y,mo,last,tzinfo=VN).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)
    print('== DỒN NÉN tháng %02d/%d =='%(mo,y))
    items=search_all(t)
    existing={}   # (kho,loai,g) -> (record_id, sl) của dòng tổng tháng này
    aging=defaultdict(float); del_ids=[]; bk_rows=[]
    for it in items:
        f=it['fields']; d=f.get('Ngày đóng gói')
        if not isinstance(d,(int,float)) or not (lo<=d<=hi): continue
        gc=gt(f.get('Ghi chú')); g=gt(f.get('G SKU')); kho=gt(f.get('Kho xuất')); loai=gt(f.get('Loại'))
        if TAG in gc:
            existing[(kho,loai,g)]=(it['record_id'], num(f.get('Số lượng')))
        else:
            sl=num(f.get('Số lượng'))
            aging[(kho,loai,g)]+=sl; del_ids.append(it['record_id'])
            bk_rows.append({'G SKU':str(g),'Ngày đóng gói':int(d),'Số lượng':int(sl),
                            'Kho xuất':kho,'Loại':loai,'Ghi chú':gc})
    print('  Chi tiết cần gộp: %d dòng -> %d nhóm (dòng tổng đã có: %d)'%(len(del_ids),len(aging),len(existing)))
    if not del_ids:
        print('  Không có chi tiết để nén cho tháng này. Xong.'); return
    if DRY_RUN:
        print('  DRY_RUN: không sửa Base (và không tạo backup).'); return

    # ---- BACKUP TRUOC KHI DONG/XOA ----
    bk_name='%s%04d-%02d'%(BK_PREFIX,y,mo)
    bk_tid,is_new=ensure_backup_table(t,bk_name)
    n_bk=write_backup(t,bk_tid,bk_rows)
    print('  Backup -> bảng "%s" (%s): đã ghi %d dòng'
          %(bk_name,'vừa tạo mới' if is_new else 'đã có sẵn, ghi thêm',n_bk))
    if n_bk!=len(del_ids):
        raise SystemExit('DỪNG LẠI: backup %d dòng nhưng cần xoá %d dòng — không khớp. '
                         'Không sửa và không xoá gì cả.'%(n_bk,len(del_ids)))

    upd=[]; new=[]
    for (kho,loai,g),sl in aging.items():
        if (kho,loai,g) in existing:
            rid,cur=existing[(kho,loai,g)]
            upd.append({'record_id':rid,'fields':{'Số lượng':int(cur+sl)}})
        else:
            f={'Ngày đóng gói':eom,'G SKU':str(g),'Số lượng':int(sl),'Ghi chú':TAG}
            if kho and kho!='(trống)': f['Kho xuất']=kho
            if loai: f['Loại']=loai
            new.append({'fields':f})
    for i in range(0,len(upd),500):
        d=api(t,'POST',f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_XK}/records/batch_update',{'records':upd[i:i+500]})
        if d.get('code')!=0: print('  update lỗi:',d); return
        time.sleep(0.3)
    for i in range(0,len(new),500):
        d=api(t,'POST',f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_XK}/records/batch_create',{'records':new[i:i+500]})
        if d.get('code')!=0: print('  create lỗi:',d); return
        time.sleep(0.3)
    dele=0
    for i in range(0,len(del_ids),500):
        d=api(t,'POST',f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_XK}/records/batch_delete',{'records':del_ids[i:i+500]})
        if d.get('code')==0: dele+=len(del_ids[i:i+500])
        else: print('  delete lỗi:',d)
        time.sleep(0.3)
    print('>> XONG tháng %02d/%d: backup %d dòng vào "%s", cập nhật %d + tạo %d dòng tổng, xoá %d chi tiết.'
          %(mo,y,n_bk,bk_name,len(upd),len(new),dele))


if __name__=='__main__':
    main()
