# -*- coding: utf-8 -*-
"""DO Gobox ky: tim base, dump RAW /open/api/orders, thu cac ten tham so ngay,
lay 1 don chi tiet (co tien + PTTT), dump helper enum.
    python probe_run.py 2026-07-14
"""
import sys, os, json, datetime, urllib.request, urllib.parse
import gobox as GB
TZ = datetime.timezone(datetime.timedelta(hours=7))
d = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now(TZ).date().isoformat()

def GET(path, params=None):
    url = GB.BASE + path + (("?" + urllib.parse.urlencode(params or {}, doseq=True)) if params else "")
    data, err = GB._open(urllib.request.Request(
        url, headers={"Authorization": "Bearer " + TOK, "Accept": "application/json"}), timeout=90)
    return data, err

def _n(data):
    if isinstance(data, dict):
        x = data.get("data", data)
        if isinstance(x, list): return len(x), x
        if isinstance(x, dict):
            for k in ("data","items","orders","results","list"):
                if isinstance(x.get(k), list): return len(x[k]), x[k]
    if isinstance(data, list): return len(data), data
    return 0, []

# 1) tim base
TOK = None
for b in [os.getenv("GOBOX_BASE","").strip().rstrip("/"),
          "https://api.gobox.asia","https://dev-api.gobox.asia"]:
    if not b: continue
    GB.BASE=b; GB._TOK={"val":None,"exp":0}
    t,e=GB.get_token(force=True)
    if t: TOK=t; print("BASE DUNG:",b); break
if not TOK:
    print("Khong xin duoc token"); sys.exit(0)
print("="*60)

# 2) RAW /open/api/orders limit=3 (khong loc) -> xem cau truc
print(">> RAW /open/api/orders?limit=3 (khong loc):")
data,err=GET("/open/api/orders",{"limit":3})
print("   err:",err)
print("   ", json.dumps(data, ensure_ascii=False)[:2500])
print("="*60)

# 3) thu cac ten tham so ngay + platform tren /open/api/orders
print(">> Thu tham so loc /open/api/orders (ngay =",d,"):")
variants=[
 {"start_date":d,"end_date":d},
 {"from_date":d,"to_date":d},
 {"date_from":d,"date_to":d},
 {"start_create_date":d,"end_create_date":d},
 {"created_from":d,"created_to":d},
 {"start":d,"end":d},
]
for v in variants:
    p=dict(v); p["limit"]=100
    data,err=GET("/open/api/orders",p)
    n,_=_n(data)
    print("   ", list(v.keys()), "-> n =", n, "| err:", err)
# them thu platform=6
data,err=GET("/open/api/orders",{"start_date":d,"end_date":d,"platform":6,"limit":100})
print("    + platform=6 -> n =", _n(data)[0], "| err:", err)
print("="*60)

# 4) lay transaction_no tu warehouse-export-by-order (co loc ngay) roi lay DON CHI TIET
print(">> warehouse-export-by-order (start_date/end_date =",d,"):")
data,err=GET("/open/api/reports/warehouse-export-by-order",{"start_date":d,"end_date":d,"limit":5})
n,rows=_n(data); print("   n =", n, "| err:", err)
tn=None
for r in rows:
    if isinstance(r,dict) and r.get("transaction_no"): tn=r["transaction_no"]; break
if tn:
    print("   Lay chi tiet don:", tn)
    data,err=GET("/open/api/orders/"+str(tn))
    print("   DON CHI TIET (co tien+PTTT?):")
    print("   ", json.dumps(data, ensure_ascii=False)[:2500])
print("="*60)

# 5) helper enum PTTT
print(">> /open/api/sys/helpers:")
for p in [None, {"type":"payment_method"}, {"key":"payment_method"}]:
    data,err=GET("/open/api/sys/helpers", p)
    s=json.dumps(data, ensure_ascii=False)
    print("   params",p,"->", (s[:900] if s else s), "| err:",err)
