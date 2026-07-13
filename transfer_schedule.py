# -*- coding: utf-8 -*-
"""Lịch luân chuyển hàng về kho vệ tinh (B4) -> thẻ Lark + trang xác nhận Render."""
import os, math, json, html, datetime, urllib.request
from collections import defaultdict
import cloud_update as M

AC_DAYS       = float(os.getenv("ROT_AC_DAYS", "30"))
ML2_MIN_DAYS  = float(os.getenv("ROT_ML2_MIN_DAYS", "30"))
KALLE_NO_AUCO = os.getenv("ROT_KALLE_NO_AUCO", "1") == "1"
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
        ml2_min = math.ceil(mr * ML2_MIN_DAYS)
        ml1_left, ml2_left, ac = v['ml1'], v['ml2'], v['ac']
        if not (KALLE_NO_AUCO and kalle):
            need = max(0, ac_t - ac)
            if need > 0 and ml1_left > 0:
                give = tron(min(need, ml1_left))
                if give > 0:
                    ml1_left -= give; need -= give
                    out.append({'src': 'Mê Linh 1', 'dst': 'Âu Cơ', **v, 'qty': give, 'src_min': None, 'src_left': int(ml1_left)})
            if need > 0:
                give = tron(min(need, max(0, ml2_left - ml2_min)))
                if give > 0 and ml2_left - give > 0:
                    ml2_left -= give; need -= give
                    out.append({'src': 'Mê Linh 2', 'dst': 'Âu Cơ', **v, 'qty': give, 'src_min': int(ml2_min), 'src_left': int(ml2_left)})
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
    body = f"**Ngày {ngay}** · Tổng **{_vn(grand)}** sp\n" + "\n".join(lines)
    return {"config": {"wide_screen_mode": True},
            "header": {"template": tmpl, "title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "✅ Xác nhận & chỉnh số"},
                     "type": "primary", "url": url}]}]}

def send(card):
    body = {"msg_type": "interactive", "card": card}
    urllib.request.urlopen(urllib.request.Request(
        M.WEBHOOK, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=30)

def _bot_state_set(tok, key, value):
    r = urllib.request.Request(M.LARK_HOST + f"/open-apis/bitable/v1/apps/{M.BASE}/tables?page_size=100",
                               headers={"Authorization": "Bearer " + tok})
    tid = None
    for it in json.load(urllib.request.urlopen(r, timeout=30))["data"]["items"]:
        if it["name"] == "Bot_State": tid = it["table_id"]; break
    if not tid:
        print("Khong thay bang Bot_State"); return
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

def _make_draft(transfers, ngay):
    rows = []
    for t in transfers:
        rows.append({"src": t["src"], "dst": t["dst"], "gsku": t.get("g"), "sku": t.get("sku") or "",
                     "name": t["name"], "cat": t.get("cat") or "", "qc": int(t.get("qc") or 0),
                     "dvt": t.get("dvt") or "", "qty": int(t["qty"]),
                     "src_stock": int(t["ml1"] if t["src"] == "Mê Linh 1" else t["ml2"])})
    return {"ngay": ngay, "rows": rows}

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
    _bot_state_set(tok, "transfer_draft", json.dumps(_make_draft(transfers, ngay), ensure_ascii=False))
    send(build_card(transfers, mode, ngay, CONFIRM_URL))
    print(f"Đã lưu draft + gửi thẻ {mode}: {len(transfers)} dòng.")

if __name__ == '__main__':
    main()
