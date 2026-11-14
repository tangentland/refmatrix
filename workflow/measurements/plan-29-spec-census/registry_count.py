import re, sys, collections
p = sys.argv[1]
def split_cells(line):
    # code-span aware; also honour \| escapes
    cells=[]; cur=[]; i=0; tick=0; n=len(line)
    while i<n:
        c=line[i]
        if c=='\\' and i+1<n and line[i+1]=='|':
            cur.append('\\|'); i+=2; continue
        if c=='`':
            j=i
            while j<n and line[j]=='`': j+=1
            run=j-i
            if tick==0: tick=run
            elif tick==run: tick=0
            cur.append(line[i:j]); i=j; continue
        if c=='|' and tick==0:
            cells.append(''.join(cur)); cur=[]; i+=1; continue
        cur.append(c); i+=1
    cells.append(''.join(cur))
    return [x.strip() for x in cells[1:-1]]
rows=[]
for ln,line in enumerate(open(p),1):
    m=re.match(r'\| (bug-\d+[a-z]?) \|',line)
    if not m: continue
    cells=split_cells(line.rstrip('\n'))
    rows.append((m.group(1),ln,cells))
print('rows',len(rows))
ids=[int(re.sub(r'\D','',r[0])) for r in rows]
print('min/max',min(ids),max(ids),'missing',[i for i in range(1,max(ids)+1) if i not in ids], 'dups',[k for k,v in collections.Counter(ids).items() if v>1])
bad=[(r[0],len(r[2])) for r in rows if len(r[2])!=8]
print('malformed',bad)
CLOSED=('fixed','closed','wontfix','not a bug','superseded','remedied')
nf=[]
cnt=collections.Counter()
for id_,ln,cells in rows:
    # status = 7th cell if 8 cells; else guess: second to last if >=8 else last?
    if len(cells)==8: st=cells[6]
    elif len(cells)==7: st=cells[6]  # no Seen
    else: st=cells[-2]
    s=st.lower().lstrip('*_ ')
    if s.startswith(CLOSED):
        cnt[s.split()[0]]+=1
    else:
        nf.append((id_,ln,st, cells[5] if len(cells)>5 else ''))
print('closed kinds',dict(cnt), sum(cnt.values()))
print('not fixed',len(nf))
k=collections.Counter()
for id_,ln,st,tags in nf:
    k[re.split(r'[ (;,:]',st.lower())[0]]+=1
print(dict(k))
for id_,ln,st,tags in nf:
    print(f'{id_}\tL{ln}\t{st[:150]!r}\t[{tags[:60]}]')
