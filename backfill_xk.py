# -*- coding: utf-8 -*-
"""Chạy BÙ xuất kho cho 1 ngày cụ thể (khi job daily lỗi / không chạy được).
Dùng:  SYNC_DATE=2026-07-18 python backfill_xk.py
Chỉ đồng bộ Xuất kho + Nhập combo + Hàng hoàn cho ĐÚNG ngày đó.
KHÔNG dựng lại board, KHÔNG gửi cảnh báo (tránh ghi đè báo cáo hôm nay).
"""
import os, datetime
from collections import defaultdict
import cloud_update as M

NGAY = os.environ['SYNC_DATE'].strip()
vn = datetime.timezone(datetime.timedelta(hours=7))
DATE_MS = int(datetime.datetime.strptime(NGAY, '%Y-%m-%d').replace(tzinfo=vn).timestamp() * 1000)
print('=== BACKFILL xuất kho ngày', NGAY, '===')

ltok = M.ltoken()
gtok = M.gbtoken()

# --- Âu Cơ + Mê Linh (qua tài khoản MLP) từ Gobox ---
lines = M.gb_all(gtok, '/open/api/reports/warehouse-export-by-sku',
                 {'start_date': NGAY, 'end_date': NGAY, 'warehouse_id': M.WID, 'limit': 1000})
wp = M.gb_all(gtok, '/open/api/warehouse-pickings',
              {'warehouse_id': M.WID, 'type': 3, 'source': 3, 'start_done_date': NGAY,
               'end_done_date': NGAY, 'limit': 1000, 'include[]': 'processer'})
def pn(r):
    x = r.get('processer')
    if isinstance(x, dict):
        x = x.get('data', x)
        if isinstance(x, dict): return x.get('name')
    return None
c2p = {r['code']: pn(r) for r in wp}
c2s = {r['code']: r.get('status') for r in wp}
auco = defaultdict(float); ml2gb = defaultdict(float)
for r in lines:
    if c2s.get(r['code']) == 499: continue          # bỏ đơn huỷ
    if c2p.get(r['code']) == M.MLP: ml2gb[str(r['gsku'])] += r.get('quantity', 0)
    else: auco[str(r['gsku'])] += r.get('quantity', 0)

# --- Mê Linh 2 từ báo cáo NVL ---
s1a, s1b, s2 = M.parse_report(NGAY)
sku2g, sku2name, name2g = M._t2g_maps(ltok)
tensp = M._ck_tensp(ltok)
unmapped = []; xk_recs = []

for g, q in auco.items():
    if q > 0: xk_recs.append({'Ngày đóng gói': DATE_MS, 'G SKU': str(g), 'Số lượng': int(q),
                              'Kho xuất': 'Kho Âu Cơ', 'Loại': 'Xuất Bán hàng'})
for g, q in ml2gb.items():
    if q > 0: xk_recs.append({'Ngày đóng gói': DATE_MS, 'G SKU': str(g), 'Số lượng': int(q),
                              'Kho xuất': 'Kho Mê Linh 2', 'Loại': 'Xuất Bán hàng'})
# kho Gobox 65 -> cộng vào Mê Linh 2
try:
    l65 = M.gb_all(gtok, '/open/api/reports/warehouse-export-by-sku',
                   {'start_date': NGAY, 'end_date': NGAY, 'warehouse_id': 65, 'limit': 1000})
    a65 = defaultdict(float)
    for r in l65: a65[str(r.get('gsku'))] += r.get('quantity', 0)
    for g, q in a65.items():
        if q > 0: xk_recs.append({'Ngày đóng gói': DATE_MS, 'G SKU': str(g), 'Số lượng': int(q),
                                  'Kho xuất': 'Kho Mê Linh 2', 'Loại': 'Xuất Bán hàng',
                                  'Ghi chú': 'Kho Mê Linh (GB65)'})
    print('  + Kho Mê Linh (GB65):', len(a65), 'GSKU')
except Exception as e:
    print('  kho65 skip:', e)

# Section 1B -> Xuất Gia công
for sku, name, qty in s1b:
    g = sku2g.get(sku.lower()) or name2g.get(M._norm(name))
    if not g: unmapped.append(('1B', sku, name, qty)); continue
    if qty > 0: xk_recs.append({'Ngày đóng gói': DATE_MS, 'G SKU': str(g), 'Số lượng': int(qty),
                                'Kho xuất': 'Kho Mê Linh 2', 'Loại': 'Xuất Gia công'})
# Section 2 (-Đã dùng) -> Xuất Bán hàng
for sku, name, dau, gc, used, left in s2:
    if used < 0: xk_recs.append({'Ngày đóng gói': DATE_MS, 'G SKU': sku, 'Số lượng': int(abs(used)),
                                 'Kho xuất': 'Kho Mê Linh 2', 'Loại': 'Xuất Bán hàng'})
# Section 2 (+Gia công) -> Chuyển kho Nhập combo
ck_recs = []
for sku, name, dau, gc, used, left in s2:
    if gc <= 0: continue
    opt = tensp.get(M._norm(name)) or tensp.get(M._norm(sku2name.get(sku.lower())))
    if not opt: unmapped.append(('S2+GC', sku, name, gc)); continue
    ck_recs.append({'Ngày': DATE_MS, 'Loại nhập kho': 'Nhập combo', 'Tên SP': opt,
                    'Số lượng': int(gc), 'Kho nhập': 'Mê Linh 2'})

# --- Xoá bản ghi cũ của ĐÚNG ngày đó rồi ghi lại ---
_SYNC_LOAI = {'Xuất Bán hàng', 'Xuất Gia công'}
ex = [it['record_id'] for it in M.lsearch(ltok, M.T_XK, ['Ngày đóng gói', 'Loại'])
      if it['fields'].get('Ngày đóng gói') == DATE_MS and M.gt(it['fields'].get('Loại')) in _SYNC_LOAI]
for i in range(0, len(ex), 500):
    M.lpost(ltok, f'/open-apis/bitable/v1/apps/{M.BASE}/tables/{M.T_XK}/records/batch_delete',
            {'records': ex[i:i+500]})
for i in range(0, len(xk_recs), 500):
    M.lpost(ltok, f'/open-apis/bitable/v1/apps/{M.BASE}/tables/{M.T_XK}/records/batch_create',
            {'records': [{'fields': r} for r in xk_recs[i:i+500]]})

exc = [it['record_id'] for it in M.lsearch(ltok, M.T_CK, ['Ngày', 'Loại nhập kho'])
       if it['fields'].get('Ngày') == DATE_MS and it['fields'].get('Loại nhập kho') == 'Nhập combo']
for i in range(0, len(exc), 500):
    M.lpost(ltok, f'/open-apis/bitable/v1/apps/{M.BASE}/tables/{M.T_CK}/records/batch_delete',
            {'records': exc[i:i+500]})
for i in range(0, len(ck_recs), 500):
    M.lpost(ltok, f'/open-apis/bitable/v1/apps/{M.BASE}/tables/{M.T_CK}/records/batch_create',
            {'records': [{'fields': r} for r in ck_recs[i:i+500]]})

tong = sum(r['Số lượng'] for r in xk_recs)
print(f'>> XONG {NGAY}: Xuất kho {len(xk_recs)} dòng / {tong} sp (đã xoá {len(ex)} dòng cũ) '
      f'| Nhập combo {len(ck_recs)} dòng | chưa map {len(unmapped)}')
if unmapped: print('  chưa map:', unmapped[:10])

try:
    n = M.sync_hanghoan(ltok, NGAY)
    print('  Hàng hoàn:', n, 'dòng')
except Exception as e:
    print('  hàng hoàn lỗi:', e)
