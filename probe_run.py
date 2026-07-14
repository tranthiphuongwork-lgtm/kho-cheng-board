# -*- coding: utf-8 -*-
"""DO Gobox (cuoi): phan bo platform/PTTT don hom nay, kiem tra loc ngay, enum PTTT.
    python probe_run.py 2026-07-14
"""
import sys, os, json, datetime, urllib.request, urllib.parse
from collections import Counter
import gobox as GB
TZ = datetime.timezone(datetime.timedelta(hours=7))
d = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now(TZ).date().isoformat()

def GET(path, params=None):
    url = GB.BASE + path + (("?" + urllib.parse.urlencode(params or {}, doseq=True)) if params else "")
    data, err = GB._open(urllib.request.Request(
        url, headers={"Authorization": "Bearer " + TOK, "Accept": "application/json"}), timeout=90)
    return data, err

def rows_of(data):
    if isinstance(data, dict):
        x = data.get("data", data)
        if isinstance(x, list): return x
    return data if isinstance(data, list) else []

# base + token
TOK=None
for b in [os.getenv("GOBOX_BASE","").strip().rstrip("/"),"https://api.gobox.asia","https://dev-api.gobox.asia"]:
    if not b: continue
    GB.BASE=b; GB._TOK={"val":None,"exp":0}
    t,e=GB.get_token(force=True)
    if t: TOK=t; print("BASE:",b); break
if not TOK: print("token loi"); sys.exit(0)
print("="*60)

# 1) keo don hom nay (phan trang), kiem tra loc ngay
allrows=[]
for page in range(1,8):
    data,err=GET("/open/api/orders",{"start_date":d,"end_date":d,"limit":100,"page":page})
    r=rows_of(data)
    allrows+=r
    if len(r)<100: break
print("Tong don keo ve (start_date=end_date=%s):"%d, len(allrows))
def cdate(o):
    s=str(o.get("create_time","")); h=s.split(" ")[0]
    if len(h)==10 and h[2]=="-": return h[6:10]+"-"+h[3:5]+"-"+h[0:2]
    return h
dates=[cdate(o) for o in allrows if o.get("create_time")]
print("  create_time min..max:", (min(dates) if dates else "-"), "..", (max(dates) if dates else "-"))
print("  So don dung ngay %s:"%d, sum(1 for x in dates if x==d), "/", len(dates))
print("  Phan bo platform:", dict(Counter(o.get("platform_name") for o in allrows)))
print("  Phan bo PTTT:", dict(Counter(o.get("payment_method_txt") for o in allrows)))
print("  Phan bo status:", dict(Counter(o.get("status_txt") for o in allrows)))
print("="*60)

# 2) cac don CHUYEN KHOAN hom nay
ck=[o for o in allrows if "chuyen khoan" in (o.get("payment_method_txt","") or "").lower()
    .replace("ể","e").replace("ả","a").replace("ề","e") or "khoản" in (o.get("payment_method_txt","") or "").lower()]
# loc lai chac chan bang tu "khoản"
ck=[o for o in allrows if "khoản" in (o.get("payment_method_txt") or "")]
print("Don CHUYEN KHOAN hom nay:", len(ck), "| tong total_amount:", sum(o.get("total_amount",0) for o in ck))
for o in ck[:15]:
    print("  ", o.get("transaction_no"), "|", o.get("platform_name"), "|",
          o.get("total_amount"), "|", o.get("payment_method_txt"), "|", o.get("create_time"), "|", o.get("status_txt"))
print("="*60)

# 3) enum PTTT tu helper (tim chu 'khoan')
data,err=GET("/open/api/sys/helpers")
raw=json.dumps((data or {}).get("data",{}), ensure_ascii=False)
i=raw.lower().find("payment")
print("Helper - quanh 'payment':", raw[i-20:i+400] if i>=0 else "(khong thay 'payment' - PTTT co the chi co trong don)")
