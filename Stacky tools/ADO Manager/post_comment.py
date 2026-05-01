#!/usr/bin/env python3
"""Helper: post comment from HTML file to ADO ticket."""
import sys
import os

# Agregar el directorio del script al path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from ado import AdoClient, _load_config, _resolve, _encode_pat
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work_item_id", type=int)
    parser.add_argument("html_file")
    args = parser.parse_args()

    html_content = open(args.html_file, encoding="utf-8").read()

    cfg = _load_config()
    org = cfg.get("org", "UbimiaPacifico")
    project = cfg.get("project", "Strategist_Pacifico")
    pat_raw = cfg.get("pat", "")
    pat_fmt = cfg.get("pat_format", "")
    pat_enc = _encode_pat(pat_raw, pat_fmt)

    client = AdoClient(org, project, pat_enc)
    result = client.add_comment(args.work_item_id, html_content, is_html=True)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
