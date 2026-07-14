# -*- coding: utf-8 -*-
"""Lịch luân chuyển hàng về kho vệ tinh (B4) -> thẻ Lark 2 tầng duyệt.
Chạy ngày 15,17,25,27:
 - 15 & 25: DANH SÁCH CHUẨN BỊ (Mê Linh soạn hàng trước, không có nút duyệt).
 - 17 & 27: gửi thẻ ĐỀ XUẤT + lưu state 2 tầng (kho nhận -> kho xuất -> tem + Lark).
Ưu tiên lấy Mê Linh 1 (kho tổng, cho hết); ML1 hết mới lấy Mê Linh 2
(ML2 giữ tối thiểu ROT_ML2_MIN_DAYS ngày bán của chính nó).
Âu Cơ điền tới ROT_AC_DAYS ngày. Chuyển TRÒN THÙNG theo Quy cách.
"""
import os, math, json, html, datetime, urllib.request
from collections import defaultdict
import cloud_update as M

AC_DAYS       = float(os.getenv("ROT_AC_DAYS", "30"))       # Âu Cơ điền tới bao nhiêu ngày bán
ML2_MIN_DAYS  = float(os.getenv("ROT_ML2_MIN_DAYS", "30"))  # ML2 tồn tối thiểu = số ngày bán (mặc định 1 tháng)
KALLE_NO_AUCO = os.getenv("ROT_KALLE_NO_AUCO", "1") == "1"  # hàng Kalle KHÔNG chuyển ra Âu Cơ
CONFIRM_URL   = os.getenv("ROT_CONFIRM_URL", "https://larkbot-laj5.onrender.com/transfer-confirm?token=Yl87CkKIQskunk09DIAbDcNCK6bJ5xcK")
VN = datetime.timezone(datetime.timedelta(hours=7))

def build_rows(tok):
    may = M.may_cache(); shopee = M.shopee_rates(tok)
    tp = M.lsearch(tok, M.T_SP, ['G SKU','SKU','Tên sản phẩm','Phân loại','Hãng','Đơn vị tính','Tồn kho Âu Cơ',
                                 'Kho Mê Linh 1','Kho Mê Linh 2','Quy cách'])
    inv = {}
    for it in tp:
        f = it['fields']; g = M.gt(f.get('G SKU'))
        if not g: continue
        inv[str(g)] = {
            'name': M.gt(f.get('Tên sản phẩm')) or str(g),
            'cat': (M.gt(f.get('Phân loại')) or '').strip() or 'Khác',
            'hang': (M.gt(f.get('Hãng')) or '—').strip(),
            'qc': M.fv(f.get('Quy cách')), 'sku': M.gt(f.get('SKU')) or '', 'dvt': (M.gt(f.get('Đơn vị tính')) or '').strip(),
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
        v = {**v, 'g': g, 'ar': rate(g, 'Kho Âu Cơ', 'ac'), 'mr': rate(g, 'Kho Mê Linh 2', 'ml2')}
        rows.append(v)
    return rows

def plan_transfers(rows):
    out = []
    for v in rows:
        qc = v['qc'] or 0
        def tron(x): return int(math.floor(x / qc) * qc) if qc > 0 else int(x)
        ar, mr = v['ar'], v['mr']
        kalle = (v['hang'] == 'Kalle')
        ac_t = math.ceil(ar * AC_DAYS)
        ml2_min = math.ceil(mr * ML2_MIN_DAYS)       # ML2 tồn tối thiểu (1 tháng bán)
        ml1_left, ml2_left, ac = v['ml1'], v['ml2'], v['ac']
        # 1) Âu Cơ thiếu -> ML1 trước, rồi ML2 (BỎ hàng Kalle). Chỉ chuyển nếu kho xuất còn lại > 0.
        if not (KALLE_NO_AUCO and kalle):
            need = max(0, ac_t - ac)
            if need > 0 and ml1_left > 0:            # ML1: kho tổng, không có tồn tối thiểu, chuyển hết (được về 0)
                give = tron(min(need, ml1_left))
                if give > 0:
                    ml1_left -= give; need -= give
                    out.append({'src': 'Mê Linh 1', 'dst': 'Âu Cơ', **v, 'qty': give, 'src_min': None, 'src_left': int(ml1_left)})
            if need > 0:                             # ML2: cho phần dư trên tồn tối thiểu
                give = tron(min(need, max(0, ml2_left - ml2_min)))
                if give > 0 and ml2_left - give > 0:
                    ml2_left -= give; need -= give
                    out.append({'src': 'Mê Linh 2', 'dst': 'Âu Cơ', **v, 'qty': give, 'src_min': int(ml2_min), 'src_left': int(ml2_left)})
        # 2) ML2 dưới tồn tối thiểu -> lấy ML1 bù (ML1 còn lại > 0)
        need2 = max(0, ml2_min - ml2_left)
        if need2 > 0 and ml1_left > 0:
            give = tron(min(need2, ml1_left))
            if give > 0:
                ml1_left -= give
                out.append({'src': 'Mê Linh 1', 'dst': 'Mê Linh 2', **v, 'qty': give, 'src_min': None, 'src_left': int(ml1_left)})
    return out

def _vn(n):
    try: return f"{int(n):,}".replace(",", ".")
    except: return str(n)
def _esc(s): return html.escape(str(s))

ROUTE_ORDER = ['Mê Linh 1 → Âu Cơ', 'Mê Linh 2 → Âu Cơ', 'Mê Linh 1 → Mê Linh 2']

def build_card(transfers, mode, ngay, url):
    grand = sum(t['qty'] for t in transfers)
    routes = defaultdict(lambda: [0, 0])
    for t in transfers:
        r = routes[f"{t['src']} → {t['dst']}"]; r[0] += 1; r[1] += t['qty']
    lines = [f"• {k}: **{_vn(q)}** sp ({n} mã)" for k, (n, q) in
             sorted(routes.items(), key=lambda x: ROUTE_ORDER.index(x[0]) if x[0] in ROUTE_ORDER else 99)]
    title = "📋 CHUẨN BỊ hàng để chuyển" if mode == 'prep' else "🔄 LỆNH CHUYỂN KHO"
    tmpl = 'orange' if mode == 'prep' else 'turquoise'
    note = "\n\n_Danh sách để Mê Linh soạn hàng trước. Lệnh chuyển & duyệt số sẽ gửi ngày 17/27._"
    body = (f"**Ngày {ngay}** · Tổng **{_vn(grand)}** sp\n" + "\n".join(lines) + note)
    return {"config": {"wide_screen_mode": True},
            "header": {"template": tmpl, "title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body}},
            ]}

def send(card):
    body = {"msg_type": "interactive", "card": card}
    urllib.request.urlopen(urllib.request.Request(
        M.WEBHOOK, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=30)

def _bot_state_set(tok, key, value):
    """Ghi 1 dong key/value vao bang Bot_State (Base) de app Render doc lai."""
    import urllib.request
    r = urllib.request.Request(M.LARK_HOST + f"/open-apis/bitable/v1/apps/{M.BASE}/tables?page_size=100",
                               headers={"Authorization": "Bearer " + tok})
    tid = None
    for it in json.load(urllib.request.urlopen(r, timeout=30))["data"]["items"]:
        if it["name"] == "Bot_State": tid = it["table_id"]; break
    if not tid:
        print("Khong thay bang Bot_State -> bo qua luu state"); return
    rid = None
    for it in M.lsearch(tok, tid, ["Key", "Value"]):
        if M.gt(it["fields"].get("Key")) == key: rid = it["record_id"]; break
    if rid:
        req = urllib.request.Request(M.LARK_HOST + f"/open-apis/bitable/v1/apps/{M.BASE}/tables/{tid}/records/{rid}",
              data=json.dumps({"fields": {"Value": str(value)}}).encode(), method="PUT",
              headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30)
    else:
        M.lpost(tok, f"/open-apis/bitable/v1/apps/{M.BASE}/tables/{tid}/records/batch_create",
                {"records": [{"fields": {"Key": key, "Value": str(value)}}]})

def _make_state(transfers, ngay):
    """State 2 tầng: mỗi dòng có p_thung (đề xuất) + status='draft'."""
    rows = []
    for t in transfers:
        qc = int(t.get("qc") or 0); qty = int(t["qty"])
        p_thung = int(round(qty / qc)) if qc > 0 else qty
        rows.append({"src": t["src"], "dst": t["dst"], "gsku": t.get("g"), "sku": t.get("sku") or "",
                     "name": t["name"], "cat": t.get("cat") or "", "qc": qc,
                     "dvt": t.get("dvt") or "", "qty": qty, "p_thung": max(0, p_thung),
                     "status": "draft"})
    return {"ngay": ngay, "rows": rows}

def _up(s):
    import urllib.parse
    return urllib.parse.quote(s)

def card_stage1(state, ngay, confirm_url):
    """Thẻ tầng 1: mỗi KHO NHẬN 1 nút xác nhận."""
    dsts = []
    for r in state["rows"]:
        if r["dst"] not in dsts: dsts.append(r["dst"])
    grand = sum(r["qty"] for r in state["rows"])
    routes = defaultdict(lambda: [0, 0])
    for r in state["rows"]:
        x = routes[f"{r['src']} → {r['dst']}"]; x[0] += 1; x[1] += r["qty"]
    lines = [f"• {k}: **{_vn(q)}** sp ({n} mã)" for k, (n, q) in
             sorted(routes.items(), key=lambda x: ROUTE_ORDER.index(x[0]) if x[0] in ROUTE_ORDER else 99)]
    body = f"**📦 ĐỀ XUẤT chuyển kho — {ngay}** · Tổng **{_vn(grand)}** sp\n" + "\n".join(lines) + \
           "\n\n_Trưởng kho NHẬN kiểm tra & chỉnh số → gửi kho xuất duyệt._"
    acts = [{"tag": "button", "text": {"tag": "plain_text", "content": f"📥 Kho nhận {d} xác nhận"},
             "type": "primary", "url": f"{confirm_url}&role=nhan&kho={_up(d)}"} for d in dsts]
    return {"config": {"wide_screen_mode": True},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": "📦 Đề xuất chuyển kho"}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}},
                         {"tag": "action", "actions": acts}]}

def main():
    now = datetime.datetime.now(VN); day = now.day
    mode = os.getenv("ROT_MODE") or ({15: 'prep', 25: 'prep', 17: 'transfer', 27: 'transfer'}.get(day))
    if not mode:
        print(f"Hôm nay ngày {day} không phải 15/17/25/27 -> bỏ qua."); return
    tok = M.ltoken()
    transfers = plan_transfers(build_rows(tok))
    if not transfers:
        print("Không có hàng cần chuyển."); return
    ngay = now.strftime('%d/%m/%Y')
    if mode == 'transfer':
        state = _make_state(transfers, ngay)
        _bot_state_set(tok, "transfer_state", json.dumps(state, ensure_ascii=False))
        send(card_stage1(state, ngay, CONFIRM_URL))
        print(f"Đã lưu state 2 tầng + gửi thẻ kho nhận: {len(transfers)} dòng.")
    else:  # prep: chỉ báo trước để Mê Linh soạn hàng (không có nút duyệt)
        send(build_card(transfers, mode, ngay, CONFIRM_URL))
        print(f"Đã gửi thẻ chuẩn bị: {len(transfers)} dòng.")

if __name__ == '__main__':
    main()
