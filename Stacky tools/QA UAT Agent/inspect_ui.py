import json
ui = json.load(open(r'n:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent\cache\ui_maps\FrmAgenda.aspx.json', encoding='utf-8'))
for e in ui['elements']:
    n = e.get('name','')
    s = e.get('selector','')
    vis = e.get('visible', True)
    keys = ['avanz','corredor','busqueda','abf','ddldebito']
    if any(k in n.lower() or k in s.lower() for k in keys):
        print(n, '|', e.get('type',''), '|', s, '| visible=' + str(vis))
