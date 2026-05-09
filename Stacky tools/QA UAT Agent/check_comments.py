import json
data = open(r'N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent\evidence\120\comments_check.json', encoding='utf-8').read()
obj = json.loads(data)
comments = obj.get('result', [])
print(f'Total comments: {len(comments)}')
qa_uat = [c for c in comments if 'qa-uat' in str(c.get('text','')).lower() or 'QA UAT' in str(c.get('text',''))]
print(f'Existing QA UAT comments: {len(qa_uat)}')
for c in comments:
    cid = c.get('id','?')
    txt = str(c.get('text',''))[:80]
    print(f'  #{cid}: {txt}')
