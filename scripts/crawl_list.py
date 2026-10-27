import re,time,json,os,urllib.request,collections
os.makedirs('.cache',exist_ok=True)
UA={'User-Agent':'Mozilla/5.0'}
def get(u): return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30).read().decode('utf-8')
items=[]
for p in range(1,53):
    s=get(f'https://www.dgpa.gov.tw/informationlist?uid=374&page={p}')
    got=re.findall(r'pid=(\d+)">\s*<dt>([\d.]+)</dt>\s*<dd>\s*<p>\s*([^<]+?)\s*</p>',s)
    if not got: print('empty',p); break
    items+=got; time.sleep(0.3)
json.dump(items,open('.cache/all_items.json','w'),ensure_ascii=False)
print(len(items))
# title patterns
pat=collections.Counter(re.sub(r'\d+','N',t) for _,_,t in items)
for k,v in pat.most_common(): print(v,k)
yr=collections.Counter(p.split('.')[0] for _,p,_ in items); print(sorted(yr.items()))
