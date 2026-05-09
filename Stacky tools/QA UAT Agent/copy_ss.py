import shutil, os
base = r'N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent'
pairs = [
    ('P01','120-tests-p01_no_fecha_jud-e47ee-ece-en-grid-de-obligaciones-chromium'),
    ('P03','120-tests-p03_ocho_columna-7cb8a-n-la-grilla-de-obligaciones-chromium'),
    ('P05','120-tests-p05_nulos_sin_er-cfba9-error-grilla-carga-completa-chromium'),
    ('P06','120-tests-p06_afiliado_deb-deb97-Si-No-guion-nunca-valor-raw-chromium'),
    ('P07','120-tests-p07_solo_lectura-e9c78--grilla-son-de-solo-lectura-chromium'),
    ('P08','120-tests-p08_formato_mone-f604a-n-formato-decimal-coherente-chromium'),
    ('P11','120-tests-p11_subvista_cuo-f6c8b-a-correctamente-sin-errores-chromium'),
    ('P12','120-tests-p12_exportacion--bae3d-s-existe-y-dispara-descarga-chromium'),
]
for tid, src in pairs:
    s = os.path.join(base, 'test-results', src, 'test-failed-1.png')
    d = os.path.join(base, 'evidence', '120', tid, 'screenshot_failure.png')
    shutil.copy2(s, d)
    print(f'{tid} OK {os.path.getsize(d)}b')
