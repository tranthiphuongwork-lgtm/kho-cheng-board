# -*- coding: utf-8 -*-
"""Lay DON HANG POS tu Gobox (kem phuong thuc thanh toan + doanh thu) va DO endpoint.

Nguon: tai lieu Open API Gobox (https://dev-api.gobox.asia/open-docs/).
Doi tuong `order` (xac nhan tu tai lieu) co cac truong:
    transaction_no      -> MA DON        (string)
    total_amount        -> DOANH THU     (int VND)   + total_amount_format
    payment_method      -> PTTT (int)                + payment_method_txt (vd "Tien mat")
    cod                 -> tien COD (int)            + cod_format
    create_time         -> ngay tao "DD-MM-YYYY HH:mm:ss"
    platform            -> 1 shopee,2 lazada,3 tiktokshop,4 tiki,5 pancake,6 POS
    warehouse_id, status, status_txt, ...

Vi tai lieu KHONG liet ke enum payment_method day du (chi thay 1 = "Tien mat"),
ta xac dinh "chuyen khoan" theo 2 cach (uu tien txt vi chac chan):
  - payment_method_txt chua "chuyen khoan"  (khong dau, thuong)  -> HAM is_transfer()
  - HOAC payment_method == GOBOX_TRANSFER_CODE (int) neu ban da biet ma so.
Chay /open/api/sys/helpers de lay enum that -> dien GOBOX_TRANSFER_CODE cho chac.

Moi cau hinh deu override bang env, KHONG can sua code.
"""
import os, time, unicodedata, urllib.request, urllib.parse
import gobox as GB   # tai su dung get_token() + BASE + _open() da chay that

# ---- Endpoint & tham so ----
ORDERS_PATH = os.getenv("GOBOX_ORDERS_PATH", "/open/api/orders")
P_LIMIT     = os.getenv("GOBOX_ORDER_LIMIT_PARAM", "limit")
P_PAGE      = os.getenv("GOBOX_ORDER_PAGE_PARAM", "page")
LIMIT       = int(os.getenv("GOBOX_ORDER_LIMIT", "100"))
# Tham so ngay: mac dinh thu theo kieu warehouse-pickings; override neu /orders dung ten khac.
P_START     = os.getenv("GOBOX_ORDER_START_PARAM", "start_create_date")
P_END       = os.getenv("GOBOX_ORDER_END_PARAM",   "end_create_date")
# Loc platform POS (theo user: don chi len o POS). De trong = khong loc.
PLATFORM    = os.getenv("GOBOX_ORDER_PLATFORM", "6")
P_PLATFORM  = os.getenv("GOBOX_ORDER_PLATFORM_PARAM", "platform")
# Loc kho (tuy chon)
WH_IDS      = [s.strip() for s in os.getenv("GOBOX_WH_IDS", "").split(",") if s.strip()]
P_WAREHOUSE = os.getenv("GOBOX_ORDER_WH_PARAM", "warehouse_id")
# Bao gom order object (mot so list can include)
INCLUDE     = os.getenv("GOBOX_ORDER_INCLUDE", "")   # vd "order" khi doc tu pickings

# Ten truong (mac dinh dung dung ten tai lieu; van cho override)
F_CODE    = [s for s in os.getenv("GOBOX_ORDER_CODE_FIELD",    "transaction_no,code,tracking_number").split(",") if s]
F_AMOUNT  = [s for s in os.getenv("GOBOX_ORDER_AMOUNT_FIELD",  "total_amount,grand_total,amount,total").split(",") if s]
F_PAYCODE = [s for s in os.getenv("GOBOX_ORDER_PAYCODE_FIELD", "payment_method").split(",") if s]
F_PAYTXT  = [s for s in os.getenv("GOBOX_ORDER_PAYTXT_FIELD",  "payment_method_txt,payment_txt").split(",") if s]
F_COD     = [s for s in os.getenv("GOBOX_ORDER_COD_FIELD",     "cod").split(",") if s]
F_DATE    = [s for s in os.getenv("GOBOX_ORDER_DATE_FIELD",    "create_time,created_at,order_date,done_at").split(",") if s]
F_PLATF   = [s for s in os.getenv("GOBOX_ORDER_PLATFORM_FIELD","platform").split(",") if s]
# So tien THUC TRA (uu tien khop) va cac thanh phan de suy ra net = subtotal - discount
F_PAID     = [s for s in os.getenv("GOBOX_ORDER_PAID_FIELD",     "total_amount,total_paid,paid_amount,final_amount,grand_total,payment_amount,transfer_amount").split(",") if s]
F_SUBTOTAL = [s for s in os.getenv("GOBOX_ORDER_SUBTOTAL_FIELD", "subtotal,sub_total,items_total,total_price,goods_amount,order_amount").split(",") if s]
F_DISCOUNT = [s for s in os.getenv("GOBOX_ORDER_DISCOUNT_FIELD", "discount,discount_amount,total_discount,voucher_amount").split(",") if s]

# "chuyen khoan": khop txt chua 1 trong cac chuoi nay (khong dau, thuong)
TRANSFER_TXT = [s.strip() for s in os.getenv(
    "GOBOX_TRANSFER_TXT",
    "chuyen khoan,chuyenkhoan,transfer,bank,vietqr,qr,ck").split(",") if s.strip()]
# Neu biet ma so PTTT chuyen khoan (int) -> dien vao day (vd "2"); de trong = chi dung txt.
TRANSFER_CODE = os.getenv("GOBOX_TRANSFER_CODE", "").strip()

PROBE_PATHS = [s.strip() for s in os.getenv("GOBOX_PROBE_PATHS", ",".join([
    "/open/api/orders",
    "/open/api/reports/warehouse-export-by-order",
    "/open/api/warehouse-pickings",
])).split(",") if s.strip()]


def _no_accent(s):
    s = (s or "").replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip().lower()


def _first(d, keys):
    for k in keys:
        cur, ok = d, True
        for part in k.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False; break
        if ok and cur not in (None, ""):
            return cur, k
    return None, None


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(".", "").replace(",", "").replace(" ", "").replace("đ", "")
    try:
        return float(s)
    except ValueError:
        return None


def _order_obj(row):
    """Mot so list tra order long trong {'order':{'data':{...}}}. Boc ra neu co."""
    if isinstance(row, dict) and isinstance(row.get("order"), dict):
        o = row["order"]
        return o.get("data", o) if isinstance(o.get("data"), dict) else o
    return row


def _unwrap_list(d):
    data = (d or {}).get("data", d)
    if isinstance(data, dict):
        for k in ("data", "items", "orders", "results", "list"):
            if isinstance(data.get(k), list):
                return data[k]
        return []
    return data if isinstance(data, list) else []


def _params(start_date, end_date, limit, page=None):
    p = {P_START: start_date, P_END: end_date, P_LIMIT: limit}
    if page is not None:
        p[P_PAGE] = page
    if PLATFORM:
        p[P_PLATFORM] = PLATFORM
    if INCLUDE:
        p["include"] = INCLUDE
    return p


def _get(token, path, params):
    url = GB.BASE + path + "?" + urllib.parse.urlencode(params, doseq=True)
    H = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    d, err = GB._open(urllib.request.Request(url, headers=H), timeout=120)
    if err:
        return None, [], err
    return d, _unwrap_list(d), None


def _get_all(token, path, base_params, sleep=0.4, cap=300):
    """Phan trang: uu tien meta.cursor.next; neu khong co thi tang ?page."""
    out, page = [], 1
    d, chunk, err = _get(token, path, dict(base_params, **{P_PAGE: page}))
    if err:
        return out, err
    out += chunk
    nxt = ((d or {}).get("meta", {}) or {}).get("cursor", {}).get("next")
    while nxt:
        dd, err = GB._open(urllib.request.Request(
            nxt, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}), timeout=120)
        if err:
            return out, err
        out += _unwrap_list(dd)
        nxt = ((dd or {}).get("meta", {}) or {}).get("cursor", {}).get("next")
        if len(out) > cap * LIMIT:
            break
        if sleep:
            time.sleep(sleep)
    # Neu API khong dung cursor -> lat page cho den khi rong
    if not ((d or {}).get("meta", {}) or {}).get("cursor"):
        while len(chunk) >= LIMIT and page < cap:
            page += 1
            _, chunk, err = _get(token, path, dict(base_params, **{P_PAGE: page}))
            if err:
                return out, err
            out += chunk
            if sleep:
                time.sleep(sleep)
    return out, None


# ---------------- DO ENDPOINT (chay tren moi truong goi duoc Gobox) ----------------
def probe(start_date, end_date):
    token, err = GB.get_token()
    if err:
        return {"ok": False, "err": "token: " + err}
    rep = {"ok": True, "base": GB.BASE, "tried": []}
    # enum PTTT tu helper (neu goi duoc)
    try:
        _, helpers, herr = _get(token, "/open/api/sys/helpers", {})
        rep["helpers_err"] = herr
        rep["helpers_sample"] = helpers[:1] if isinstance(helpers, list) else helpers
    except Exception as e:
        rep["helpers_err"] = str(e)
    for path in PROBE_PATHS:
        params = _params(start_date, end_date, 5, page=1)
        if WH_IDS:
            params[P_WAREHOUSE] = WH_IDS[0]
        if "pickings" in path and not INCLUDE:
            params["include"] = "order"
        d, data, e = _get(token, path, params)
        entry = {"path": path, "err": e, "n": len(data)}
        if data:
            o = _order_obj(data[0])
            entry["sample_keys"] = sorted(o.keys()) if isinstance(o, dict) else str(type(o))
            _, ck = _first(o, F_CODE);    entry["guess_code"] = ck
            _, ak = _first(o, F_AMOUNT);  entry["guess_amount"] = ak
            entry["guess_paytxt"] = _first(o, F_PAYTXT)[1]
            entry["guess_date"] = _first(o, F_DATE)[1]
            entry["sample"] = {k: o.get(k) for k in list(o.keys())[:30]} if isinstance(o, dict) else None
        rep["tried"].append(entry)
    return rep


# ---------------- FETCH THAT ----------------
def fetch_orders(start_date, end_date):
    token, err = GB.get_token()
    if err:
        return [], "token: " + err
    base = _params(start_date, end_date, LIMIT)
    if "pickings" in ORDERS_PATH and not INCLUDE:
        base["include"] = "order"
    rows_all, wh_list = [], (WH_IDS or [None])
    for wh in wh_list:
        p = dict(base)
        if wh:
            p[P_WAREHOUSE] = wh
        rows, e = _get_all(token, ORDERS_PATH, p)
        if e:
            return rows_all, e
        rows_all += rows
    return rows_all, None



def _all_nums(o, keys):
    """Tra list gia tri so (float>0) cho tat ca key co mat trong o."""
    out = []
    for k in keys:
        v, _ = _first(o, [k])
        n = _num(v)
        if n and n > 0:
            out.append(n)
    return out

def normalize(row):
    o = _order_obj(row)
    code, _ = _first(o, F_CODE)
    pc, _   = _first(o, F_PAYCODE)
    ptxt, _ = _first(o, F_PAYTXT)
    cod, _  = _first(o, F_COD)
    dt, _   = _first(o, F_DATE)
    plat, _ = _first(o, F_PLATF)
    # amount THUC TRA = uu tien F_PAID; con lai F_AMOUNT
    paid, _ = _first(o, F_PAID) if F_PAID else (None, None)
    amt, _  = _first(o, F_AMOUNT)
    primary = _num(paid) if paid is not None else _num(amt)
    # candidate: cac gia tri thanh toan co mat + (subtotal - discount)
    cands = set(_all_nums(o, F_PAID) + _all_nums(o, F_AMOUNT))
    subs = _all_nums(o, F_SUBTOTAL); disc = _all_nums(o, F_DISCOUNT)
    if subs:
        base = max(subs)
        for d in (disc or [0]):
            net = base - d
            if net > 0:
                cands.add(net)
    if primary:
        cands.add(primary)
    return {
        "code": str(code) if code is not None else "",
        "amount": primary,
        "amounts": sorted(cands),
        "cod": _num(cod) or 0,
        "pay_code": pc,
        "pay_txt": str(ptxt) if ptxt is not None else "",
        "date": _date10(dt),
        "platform": plat,
        "raw": o,
    }


def _date10(v):
    """Chuan hoa ve 'YYYY-MM-DD' tu 'DD-MM-YYYY HH:MM:SS' hoac 'YYYY-MM-DD...'."""
    s = str(v or "").strip()
    if not s:
        return ""
    head = s.split(" ")[0].split("T")[0]
    if len(head) == 10 and head[2] == "-" and head[4] != "-":   # DD-MM-YYYY
        d, m, y = head.split("-")
        return f"{y}-{m}-{d}"
    return head


def is_transfer(n):
    """True neu don la CHUYEN KHOAN."""
    if TRANSFER_CODE and str(n.get("pay_code")) == TRANSFER_CODE:
        return True
    t = _no_accent(n.get("pay_txt"))
    return any(v in t for v in TRANSFER_TXT)


def transfer_orders(start_date, end_date):
    """Lay + loc don POS chuyen khoan da chuan hoa. Tra (list, err)."""
    rows, err = fetch_orders(start_date, end_date)
    if err:
        return [], err
    out = []
    for r in rows:
        n = normalize(r)
        if n["amount"] and is_transfer(n):
            out.append(n)
    return out, None


# ---------------- PHAN LOAI THEO PTTT (them TIEN MAT) ----------------
CASH_TXT  = [s.strip() for s in os.getenv("GOBOX_CASH_TXT", "tien mat,tienmat,cash").split(",") if s.strip()]
CASH_CODE = os.getenv("GOBOX_CASH_CODE", "1").strip()   # tai lieu: 1 = "Tien mat"


def is_cash(n):
    """True neu don la TIEN MAT."""
    if CASH_CODE and str(n.get("pay_code")) == CASH_CODE:
        return True
    t = _no_accent(n.get("pay_txt"))
    return any(v in t for v in CASH_TXT)


def classify(start_date, end_date):
    """Lay TAT CA don POS 1 lan, chia nhom theo PTTT.
    Tra ({'transfer':[...],'cash':[...],'other':[...],'all':[...]}, err)."""
    rows, err = fetch_orders(start_date, end_date)
    if err:
        return {"transfer": [], "cash": [], "other": [], "all": []}, err
    g = {"transfer": [], "cash": [], "other": [], "all": []}
    for r in rows:
        n = normalize(r)
        if not n["amount"]:
            continue
        g["all"].append(n)
        if is_transfer(n):
            g["transfer"].append(n)
        elif is_cash(n):
            g["cash"].append(n)
        else:
            g["other"].append(n)
    return g, None
