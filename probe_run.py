# -*- coding: utf-8 -*-
"""Soi vài đơn POS cụ thể + phân bố PTTT: tìm truong nao chua 'chuyen khoan'.
    python probe_run.py            # dung danh sach ma mac dinh ben duoi
    python probe_run.py 1784001611790 1783999989816
"""
import sys, os, json, datetime, urllib.request, urllib.parse
from collections import Counter
import gobox as GB
TZ = datetime.timezone(datetime.timedelta(hours=7))

# ma don POS thu (tu anh chup cua user) - co the truyen qua args
CODES = [a for a in sys.argv[1:] if not a.startswith("-")] or [
    "1784001611790", "1783999989816", "1783995871539",
    "1783993515149", "1784035592275", "1784028209466",
]

def GET(path, params=None):
    url = GB.BASE + path + (("?" + urllib.parse.urlencode(params or {}, doseq=True)) if params else "")
    data, err = GB._open(urllib.request.Request(
        url, headers={"Authorization": "Bearer " + TOK, "Accept": "application/json"}), timeout=90)
    return data, err

TOK=None
for b in [os.getenv("GOBOX_BASE","").strip().rstrip("/"),"https://api.gobox.asia","https://dev-api.gobox.asia"]:
    if not b: continue
    GB.BASE=b; GB._TOK={"val":None,"exp":0}
    t,e=GB.get_token(force=True)
    if t: TOK=t; print("BASE:",b); break
if not TOK: print("token loi"); sys.exit(0)
print("="*60)

for code in CODES:
    data,err=GET("/open/api/orders/"+str(code))
    o=(data or {}).get("data", data) if isinstance(data,dict) else data
    if not isinstance(o,dict):
        print("Don",code,"-> khong lay duoc | err",err, "| raw:", json.dumps(data,ensure_ascii=False)[:200]); continue
    print("Đơn", code, "| platform:", o.get("platform_name"),
          "| payment_method:", o.get("payment_method"), "/", o.get("payment_method_txt"),
          "| total_amount:", o.get("total_amount"), "| cod:", o.get("cod"),
          "| payer:", o.get("payer"), "/", o.get("payer_txt"), "| status:", o.get("status_txt"))
    # in TAT CA key co chu 'pay' hoac 'transfer' hoac 'amount' hoac 'method'
    hits={k:v for k,v in o.items() if any(w in k.lower() for w in ("pay","transfer","amount","method","bank","total","discount","sub"))}
    print("   truong lien quan tien/PTTT:", json.dumps(hits, ensure_ascii=False)[:800])
    print("-"*60)

print("\n>> Phan bo PTTT & platform tren 500 don gan nhat:")
data,err=GET("/open/api/orders",{"limit":100})
rows=(data or {}).get("data",[])
allp=Counter(); allpl=Counter()
for r in rows:
    allp[r.get("payment_method_txt")]+=1; allpl[r.get("platform_name")]+=1
print("   PTTT:", dict(allp))
print("   platform:", dict(allpl))
