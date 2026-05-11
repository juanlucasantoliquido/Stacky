with open(r'N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent\qa_uat_pipeline.py', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if 'print(' in line and any(ord(c) > 127 for c in line):
            print(f'L{i}: {line.strip()[:120]}')