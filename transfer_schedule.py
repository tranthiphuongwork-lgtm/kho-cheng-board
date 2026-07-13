# -*- coding: utf-8 -*-
"""Lịch luân chuyển hàng về kho vệ tinh (B4).
Chạy trên GitHub Actions vào ngày 15,17,25,27:
 - 15 & 25: gửi DANH SÁCH CHUẨN BỊ (để Mê Linh soạn hàng trước).
 - 17 & 27: gửi LỆNH CHUYỂN chính thức.
Tái dùng dữ liệu tồn kho + tốc độ bán từ cloud_update (Lark Base).

Mục tiêu tồn:
 - Âu Cơ: đủ bán ROT_AC_DAYS ngày (mặc định 30 = ~1 tháng, trong khoảng 3 tuần–1 tháng).
 - Mê Linh 2: đủ bán ROT_ML2_DAYS ngày (mặc định 30).
 - Nguồn cấp: Mê Linh 1 (kho tổng) trước, rồi ML2-thừa cấp cho Âu Cơ.
 - Chuyển TRÒN THÙNG theo Quy cách.
"""
import os, math, json, datetime, urllib.request
from collections import defaultdict
import cloud_update as M

AC_DAYS  = float(os.getenv("ROT_AC_DAYS", "30"))
ML2_DAYS = float(os.getenv("ROT_ML2_DAYS", "30"))
ML2_KEEP_DAYS = float(os.getenv("ROT_ML2_KEEP_DAYS", "15"))  # ML2 giu toi thieu bao nhieu ngay truoc khi cho Au Co
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
        ar = rate(g, 'Kho Âu Cơ', 'ac'); mr = rate(g, 'Kho Mê Linh 2', 'ml2')
        rows.append({**v, 'g': g, 'ar': ar, 'mr': mr})
    return rows

def plan_transfers(rows):
    """Tính danh sách chuyển: điền Âu Cơ & ML2 tới target, lấy từ ML1 (rồi ML2 thừa cho Âu Cơ)."""
    out = []  # (src, dst, name, cat, hang, qty, qc)
    for v in rows:
        qc = v['qc'] or 0
        ac_t = math.ceil(v['ar'] * AC_DAYS); ml2_t = math.ceil(v['mr'] * ML2_DAYS)
        ac, ml1, ml2 = v['ac'], v['ml1'], v['ml2']
        # thừa để cho đi
        ml1_av = max(0, ml1)                    # ML1 là kho chứa -> cho hết
        ml2_keep = math.ceil(v['mr'] * ML2_KEEP_DAYS)   # ML2 giu lai theo toc do ban
        ml2_sur = max(0, ml2 - ml2_keep)        # phan ML2 co the cho Au Co (sau khi giu du keep)
        def tron(x):
            return int(math.floor(x / qc) * qc) if qc > 0 else int(x)
        # 1) Âu Cơ thiếu -> lấy ML1 trước, rồi ML2 thừa
        need = max(0, ac_t - ac)
        for src, avail_key in (('Mê Linh 1', 'ml1_av'), ('Mê Linh 2', 'ml2_sur')):
            if need <= 0: break
            avail = ml1_av if src == 'Mê Linh 1' else ml2_sur
            mv = tron(min(need, avail))
            if mv > 0:
                out.append((src, 'Âu Cơ', v['name'], v['cat'], v['hang'], mv, qc))
                need -= mv
                if src == 'Mê Linh 1': ml1_av -= mv
                else: ml2_sur -= mv
        # 2) ML2 thiếu -> lấy ML1
        need2 = max(0, ml2_t - ml2)
        if need2 > 0 and ml1_av > 0:
            mv = tron(min(need2, ml1_av))
            if mv > 0:
                out.append(('Mê Linh 1', 'Mê Linh 2', v['name'], v['cat'], v['hang'], mv, qc))
                ml1_av -= mv
    return out

def build_card(transfers, mode, ngay):
    title = ("📋 CHUẨN BỊ hàng để chuyển" if mode == 'prep' else "🔄 LỆNH CHUYỂN KHO")
    tmpl = 'orange' if mode == 'prep' else 'turquoise'
    sub = ("Danh sách để kho Mê Linh soạn trước (chuyển vào ngày 17/27)." if mode == 'prep'
           else "Thực hiện chuyển hôm nay.")
    routes = defaultdict(list); grand = 0
    for src, dst, name, cat, hang, qty, qc in transfers:
        routes[f"{src} → {dst}"].append((name, cat, qty, qc)); grand += qty
    order = ['Mê Linh 1 → Âu Cơ', 'Mê Linh 2 → Âu Cơ', 'Mê Linh 1 → Mê Linh 2']
    keys = sorted(routes, key=lambda k: order.index(k) if k in order else 99)
    elements = [{"tag": "div", "text": {"tag": "lark_md",
                 "content": f"**Ngày {ngay}** · {sub}\nTổng **{grand:,}** sp · {len(keys)} tuyến".replace(",", ".")}}]
    for k in keys:
        items = sorted(routes[k], key=lambda x: -x[2])
        cats = defaultdict(list)
        for name, cat, qty, qc in items: cats[cat].append((name, qty, qc))
        lines = [f"**🔄 {k}**"]
        for cat in sorted(cats, key=lambda c: -sum(x[1] for x in cats[c])):
            lines.append(f"__{cat}__")
            for name, qty, qc in cats[cat]:
                box = f" ({int(qty/qc)} thùng)" if qc and qty % qc == 0 else ""
                lines.append(f"• {name}: **{qty:,}**{box}".replace(",", "."))
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
    return {"config": {"wide_screen_mode": True},
            "header": {"template": tmpl, "title": {"tag": "plain_text", "content": title}},
            "elements": elements}

def send(card):
    body = {"msg_type": "interactive", "card": card}
    urllib.request.urlopen(urllib.request.Request(
        M.WEBHOOK, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=30)

def main():
    now = datetime.datetime.now(VN); day = now.day
    mode = os.getenv("ROT_MODE")  # ép chế độ khi test
    if not mode:
        if day in (15, 25): mode = 'prep'
        elif day in (17, 27): mode = 'transfer'
        else:
            print(f"Hôm nay ngày {day} không phải 15/17/25/27 -> bỏ qua."); return
    tok = M.ltoken()
    rows = build_rows(tok)
    transfers = plan_transfers(rows)
    if not transfers:
        print("Không có hàng cần chuyển."); return
    card = build_card(transfers, mode, now.strftime('%d/%m/%Y'))
    send(card)
    print(f"Đã gửi thẻ {mode}: {len(transfers)} dòng chuyển.")

if __name__ == '__main__':
    main()
