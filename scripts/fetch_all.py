import re,html,time,json,os,urllib.request
os.makedirs('.cache',exist_ok=True)
UA={'User-Agent':'Mozilla/5.0'}
def raw(u):
    for i in range(3):
        try: return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30).read()
        except Exception as e: err=e; time.sleep(1)
    raise err
items=json.load(open('.cache/all_items.json'))
meta={}
for n,(pid,pub,t) in enumerate(items):
    p=f'.cache/{pid}.detail'
    if not os.path.exists(p): open(p,'wb').write(raw(f'https://www.dgpa.gov.tw/information?uid=374&pid={pid}')); time.sleep(0.2)
    d=open(p,'rb').read().decode('utf-8','replace')
    links=re.findall(r'<a href="(/FileConversion\?[^"]*)"[^>]*title="([^"]*)"',d)
    meta[pid]=[(html.unescape(h),t_) for h,t_ in links]
    for i,(h,t_) in enumerate(meta[pid]):
        q=f'.cache/{pid}.att{i}'
        if not os.path.exists(q):
            try: open(q,'wb').write(raw('https://www.dgpa.gov.tw'+h)); time.sleep(0.2)
            except Exception as e: print('ERR',pid,i,e)
    if n%50==0: print(n,flush=True)
json.dump(meta,open('.cache/meta.json','w'),ensure_ascii=False)
print('done')
