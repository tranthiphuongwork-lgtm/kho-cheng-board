# -*- coding: utf-8 -*-
"""Lịch luân chuyển hàng về kho vệ tinh (B4) -> dashboard GitHub Pages + thẻ Lark.
ML1 (kho tổng) chuyển hết, không có tồn tối thiểu. ML2 giữ tối thiểu 1 tháng bán.
Âu Cơ điền tới ROT_AC_DAYS ngày. Hàng Kalle KHÔNG chuyển ra Âu Cơ. Tròn thùng."""
import os, math, json, html, datetime, urllib.request
from collections import defaultdict
import cloud_update as M

AC_DAYS       = float(os.getenv("ROT_AC_DAYS", "30"))       # Âu Cơ điền tới bao nhiêu ngày bán
ML2_MIN_DAYS  = float(os.getenv("ROT_ML2_MIN_DAYS", "30"))  # ML2 tồn tối thiểu = số ngày bán (mặc định 1 tháng)
KALLE_NO_AUCO = os.getenv("ROT_KALLE_NO_AUCO", "1") == "1"  # hàng Kalle KHÔNG chuyển ra Âu Cơ
PAGES_URL     = os.getenv("ROT_PAGES_URL", "https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/transfer.html")
OUT_HTML      = os.getenv("ROT_OUT_HTML", "transfer.html")
VN = datetime.timezone(datetime.timedelta(hours=7))

def build_rows(tok):
    may = M.may_cache(); shopee = M.shopee_rates(tok)
    tp = M.lsearch(tok, M.T_SP, ['G SKU','Tên sản phẩm','Phân loại','Hãng','Tồn kho Âu Cơ',
                                 'Kho Mê Linh 1','Kho Mê Linh 2','Quy cách'])
    inv = {}
    for it in tp:
        f = it['fields']; g = M.gt(f.get('G SKU'))
        if not g: continue
        inv[str(g)] = {
            'name': M.gt(f.get('Tên sản phẩm')) or str(g),
            'cat': (M.gt(f.get('Phân loại')) or '').strip() or 'Khác',
            'hang': (M.gt(f.get('Hãng')) or '—').strip(),
            'qc': M.fv(f.get('Quy cách')),
            'ac': M.fv(f.get('Tồn kho Âu Cơ')), 'ml1': M.fv(f.get('Kho Mê Linh 1')),
            'ml2': M.fv(f.get('Kho Mê Linh 2')),
        }
    xk = M.lsearch(tok, M.T_XK, ['G SKU','Số lượng','Kho xuất','Ngày đóng gói'])
    salesw = defaultdict(lambda: defaultdict(float)); days = set()
    for it in xk:
        f = it['fields']; g = M.gt(f.get('G SKU')); q = f.get('Số lượng') or 0; k = f.get('Kho xuất')
        d = f.get('Ngày đóng gói')
        if isinstance(d, (int, float)): days.add(d)
        if g and k: salesw[str(g)][k] += q
    NDW = max(1, len(days)); NDM = 31
    def rate(g, kho, shp_key):
        wk = salesw.get(g, {}).get(kho, 0)
        mo = (may.get(g, {}) or {}).get(shp_key, 0) if isinstance(may.get(g), dict) else 0
        sh = shopee.get(g, {}).get(shp_key, 0)
        return max(wk / NDW, mo / NDM) + sh
    rows = []
    for g, v in inv.items():
        if g in M.TRIO: continue
        rows.append({**v, 'g': g, 'ar': rate(g, 'Kho Âu Cơ', 'ac'), 'mr': rate(g, 'Kho Mê Linh 2', 'ml2')})
    return rows

def
