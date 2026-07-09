# -*- coding: utf-8 -*-
"""Goi API Gobox: token, danh sach kho, xuat kho theo SKU.
Khop cach lam da chay that (repo kho-cheng-board):
 - BASE production: https://api.gobox.asia
 - token: POST /oauth/token grant_type=client_credentials (form-encoded)
 - phan trang theo meta.cursor.next, retry khi 429/5xx (Gobox chan toc do)
"""
import os, json, time, base64, urllib.request, urllib.parse, urllib.error

BASE   = os.getenv("GOBOX_BASE", "https://api.gobox.asia").rstrip("/")
CID    = os.getenv("GOBOX_CLIENT_ID", "25")
CSEC   = os.getenv("GOBOX_CLIENT_SECRET", "bdEOeIp9yu6V8okBoP2UQcPAudHLuegDk4rIevOG")
GRANT  = os.getenv("GOBOX_GRANT_TYPE", "client_credentials")
# Uu tien chi dinh thang ID kho (vd "32,65"); neu de trong thi khop theo ten.
WH_IDS   = [s.strip() for s in os.getenv("GOBOX_WH_IDS", "").split(",") if s.strip()]
WH_NAMES = [s.strip() for s in os.getenv("GOBOX_WH_NAMES", "Online Cheng,Kho Me Linh").split(",") if s.strip()]

_TOK = {"val": None, "exp": 0}

import unicodedata as _ud
def _strip_accents(s):
    s = (s or "").replace("đ", "d").replace("Đ", "d")
    s = _ud.normalize("NFD", s)
    return "".join(c for c in s if _ud.category(c) != "Mn").strip().lower()

def _open(req, timeout=90, tries=6):
    """urlopen co retry khi 429/5xx hoac loi mang tam thoi."""
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 * (i + 1)); continue
            return None, f"{e.code} {body}"
        except urllib.error.URLError as e:
            last = str(e)
            if i < tries - 1:
                time.sleep(2 * (i + 1)); continue
            return None, last
        except Exception as e:
            return None, str(e)
    return None, last or "unknown"

# ---------- Token (thu 3 cach, uu tien form-encoded nhu ban chay that) ----------
def _token_form():
    data = urllib.parse.urlencode({"grant_type": GRANT, "client_id": CID, "client_secret": CSEC}).encode()
    req = urllib.request.Request(BASE + "/oauth/token", data=data, method="POST",
                                 headers={"Accept": "application/json",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    return _open(req, timeout=40, tries=3)

def _token_basic():
    data = urllib.parse.urlencode({"grant_type": GRANT}).encode()
    cred = base64.b64encode(f"{CID}:{CSEC}".encode()).decode()
    req = urllib.request.Request(BASE + "/oauth/token", data=data, method="POST",
                                 headers={"Accept": "application/json",
                                          "Content-Type": "application/x-www-form-urlencoded",
                                          "Authorization": "Basic " + cred})
    return _open(req, timeout=40, tries=3)

def _token_json():
    data = json.dumps({"grant_type": GRANT, "client_id": CID, "client_secret": CSEC}).encode()
    req = urllib.request.Request(BASE + "/oauth/token", data=data, method="POST",
                                 headers={"Accept": "application/json", "Content-Type": "application/json"})
    return _open(req, timeout=40, tries=3)

def get_token(force=False):
    if not force and _TOK["val"] and time.time() < _TOK["exp"] - 60:
        return _TOK["val"], None
    errors = []
    for name, fn in (("form", _token_form), ("basic", _token_basic), ("json", _token_json)):
        d, err = fn()
        if err:
            errors.append(f"{name}:{err}"); continue
        at = (d or {}).get("access_token")
        if at:
            _TOK["val"] = at
            _TOK["exp"] = time.time() + int(d.get("expires_in", 3600))
            return at, None
        errors.append(f"{name}:no_access_token:{json.dumps(d)[:120]}")
    return None, "token that bai (da thu form/basic/json) -> " + " | ".join(errors)

# ---------- Goi chung: phan trang theo meta.cursor.next ----------
def _get_all(token, path, params, sleep=0.4, cap=120):
    url = BASE + path + "?" + urllib.parse.urlencode(params, doseq=True)
    H = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    out, p = [], 0
    while url:
        d, err = _open(urllib.request.Request(url, headers=H), timeout=120)
        if err:
            return out, err
        out += (d or {}).get("data", []) or []
        p += 1
        if sleep:
            time.sleep(sleep)
        url = ((d or {}).get("meta", {}) or {}).get("cursor", {}).get("next")
        if p > cap:
            break
    return out, None

def list_warehouses(token):
    return _get_all(token, "/open/api/warehouses", {"limit": 100}, sleep=0)

def resolve_warehouse_ids(token, names=None):
    """Tra ve ({label: id}, danh_sach_kho, err).
    Neu GOBOX_WH_IDS duoc dat -> dung thang; nguoc lai khop theo ten (bo dau)."""
    if WH_IDS:
        return ({("Kho #" + i): int(i) for i in WH_IDS}, [], None)
    names = names or WH_NAMES
    whs, err = list_warehouses(token)
    if err:
        return {}, whs, err
    found = {}
    for want in names:
        w = _strip_accents(want)
        for wh in whs:
            nm = _strip_accents(wh.get("name"))
            if w and (w in nm or nm in w):
                found[wh.get("name")] = wh.get("id"); break
    return found, whs, None

def export_by_sku(token, warehouse_id, start_date, end_date, limit=1000):
    """Tat ca dong xuat kho theo SKU trong khoang ngay (Y-m-d) cua 1 kho."""
    return _get_all(token, "/open/api/reports/warehouse-export-by-sku",
                    {"warehouse_id": warehouse_id, "start_date": start_date,
                     "end_date": end_date, "limit": limit})

def row_label(r):
    for k in ("sku", "sku_sku", "product_name", "name"):
        if r.get(k):
            return str(r[k])
    ps = r.get("product_sku") or r.get("productSku")
    if isinstance(ps, dict):
        for k in ("sku", "name", "title"):
            if ps.get(k):
                return str(ps[k])
    return "GSKU " + str(r.get("gsku"))
