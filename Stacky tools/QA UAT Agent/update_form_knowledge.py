"""
update_form_knowledge.py
------------------------
Ejecutar después de un run exitoso para actualizar form_knowledge.json
con el conocimiento validado del run.

Uso:
    python update_form_knowledge.py --run-id freeform-20260505-001641 [--selector-overrides sel.json]

Lee el log de Playwright (stdout) del run y extrae:
- Opciones de DDL validadas
- Selectores usados
- Flujos exitosos
"""
import argparse
import json
import pathlib
import re
import sys
from datetime import date

KNOWLEDGE_FILE = pathlib.Path(__file__).parent / 'form_knowledge.json'


def load_knowledge() -> dict:
    if KNOWLEDGE_FILE.exists():
        return json.loads(KNOWLEDGE_FILE.read_text(encoding='utf-8'))
    return {}


def save_knowledge(data: dict):
    KNOWLEDGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] form_knowledge.json actualizado: {KNOWLEDGE_FILE}')


def update_from_run(run_id: str, log_text: str, knowledge: dict) -> dict:
    """Extrae conocimiento del log de Playwright y lo merge en knowledge."""
    today = str(date.today())

    # --- Extraer opciones DDL del log ---
    # Lineas como: [INFO] Opciones Figura: [{"v":"A01","t":"..."},...]
    figura_match = re.search(r'\[INFO\] Figuras?: (\[.*?\])', log_text)
    accion_match = re.search(r'\[INFO\] Opciones Accion \(.*?\): (\[.*?\])', log_text)

    if figura_match:
        try:
            opts = json.loads(figura_match.group(1))
            figura_dict = {o['v']: o['t'] for o in opts if o.get('v') and o['v'] != '0'}
            if figura_dict:
                knowledge.setdefault('PopUpCompromisos', {})['ddl_figura_opciones'] = figura_dict
                print(f'  [LEARN] Figura options actualizadas: {list(figura_dict.keys())}')
        except Exception:
            pass

    if accion_match:
        try:
            opts = json.loads(accion_match.group(1))
            # Solo guardar los más comunes (los primeros 10 que no sean "Seleccione")
            accion_dict = {o['v']: o['t'] for o in opts if o.get('v') and o['v'] not in ('0', 'Seleccione')}
            if accion_dict:
                knowledge.setdefault('PopUpCompromisos', {})['ddl_accion_opciones_comunes'] = dict(
                    list(accion_dict.items())[:10]
                )
                print(f'  [LEARN] Accion options actualizadas: {list(accion_dict.keys())[:5]}...')
        except Exception:
            pass

    # --- Detectar cliente utilizado ---
    cliente_match = re.search(r'\[INFO\] Abriendo cliente: (.+)', log_text)
    if cliente_match:
        cliente = cliente_match.group(1).strip()
        if cliente and cliente != 'N/A':
            knowledge.setdefault('PopUpCompromisos', {})['cliente_prueba'] = cliente
            print(f'  [LEARN] Cliente de prueba: {cliente}')

    # --- Detectar si se usó búsqueda avanzada (fallback) ---
    if 'Agenda vacia' in log_text or 'Busqueda Avanzada' in log_text:
        knowledge.setdefault('FrmAgenda.aspx', {})['nota_fallback'] = (
            'La agenda puede estar vacía si clientes fueron procesados — '
            'usar Búsqueda Avanzada con nombre vacío para traer todos los clientes del agente.'
        )
        print('  [LEARN] Fallback búsqueda avanzada detectado y documentado')

    # --- Actualizar metadata ---
    knowledge.setdefault('_meta', {})['last_updated'] = today
    knowledge.setdefault('_meta', {})['last_run_id'] = run_id

    return knowledge


def main():
    parser = argparse.ArgumentParser(description='Actualizar form_knowledge.json post-run')
    parser.add_argument('--run-id', required=True, help='ID del run (ej: freeform-20260505-001641)')
    parser.add_argument('--log-file', help='Archivo de log del run Playwright (stdout capturado)')
    args = parser.parse_args()

    knowledge = load_knowledge()

    log_text = ''
    if args.log_file:
        log_path = pathlib.Path(args.log_file)
        if log_path.exists():
            log_text = log_path.read_text(encoding='utf-8', errors='replace')
            print(f'[INFO] Leyendo log: {log_path} ({len(log_text)} chars)')
        else:
            print(f'[WARN] Log no encontrado: {log_path}')
    else:
        # Intentar encontrar log por run-id
        auto_log = pathlib.Path(__file__).parent / 'evidence' / args.run_id / 'playwright_output.txt'
        if auto_log.exists():
            log_text = auto_log.read_text(encoding='utf-8', errors='replace')
            print(f'[INFO] Log auto-detectado: {auto_log}')
        else:
            print(f'[WARN] No se encontró log. Pasando stdin... (Ctrl+Z/Enter para terminar)')
            log_text = sys.stdin.read()

    print(f'[INFO] Procesando run: {args.run_id}')
    knowledge = update_from_run(args.run_id, log_text, knowledge)
    save_knowledge(knowledge)


if __name__ == '__main__':
    main()
