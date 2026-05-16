#!/usr/bin/env python3
"""
Parser PSPLIB — Version CORRIGÉE v4
=====================================
Génère des .dzn au format DataZinc STANDARD (compatible MiniZinc pur)
Sans extensions BTP, sans syntaxe |[...]|, sans rien de superflu.

Usage:
    python3 parser_btp_v4.py --input instancesdebtp.docx --outdir dzn_output
"""

import re
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional


# ===========================================================================
# 1. MAPPING NOMS BASEDATA -> CLÉS
# ===========================================================================

NAME_MAPPING = {
    "j30_17":   "j301_1",
    "j30_37":   "j3021_1",
    "j30_45":   "j3029_1",
    "j30_61":   "j3045_1",
    "j30_82":   "j3082_1",
    "j60_1":    "j601_1",
    "j60_2":    "j601_2",
    "j60_3":    "j601_3",
    "j60_4":    "j601_4",
    "j60_17":   "j601_1",
    "j90_1":    "j901_1",
    "j90_2":    "j901_2",
    "j90_3":    "j901_3",
    "j90_4":    "j901_4",
    "j901_":    "j901_1",
    "j1201_1":  "j1201_1",
    "j1201_2":  "j1201_2",
    "j1201_3":  "j1201_3",
    "j1201_4":  "j1201_4",
}


def get_instance_key(basedata_name: str) -> str:
    clean = basedata_name.lower().replace('.bas', '').replace('.sm', '').strip()
    if clean in NAME_MAPPING:
        return NAME_MAPPING[clean]
    return clean


def get_instance_type(stem: str) -> str:
    if stem.startswith('j120'):
        return 'J120'
    elif stem.startswith('j90'):
        return 'J90'
    elif stem.startswith('j60'):
        return 'J60'
    elif stem.startswith('j30'):
        return 'J30'
    return 'UNKNOWN'


# ===========================================================================
# 2. FONCTIONS UTILITAIRES
# ===========================================================================

def extract_text_from_docx(docx_path: str) -> str:
    try:
        import docx as _docx
    except ImportError:
        raise RuntimeError("python-docx non installé. Lancez : pip3 install python-docx")
    doc = _docx.Document(docx_path)
    lines = []
    for table in doc.tables:
        for row in table.rows:
            lines.append("\t".join(cell.text for cell in row.cells))
    for para in doc.paragraphs:
        lines.append(para.text)
    return "\n".join(lines)


def load_raw_text(path: str) -> str:
    if path.endswith(".docx"):
        text = extract_text_from_docx(path)
    else:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    return re.sub(r'\n{2,}', '\n', text)


# ===========================================================================
# 3. PARSING D'UN BLOC PSPLIB
# ===========================================================================

def parse_block(content: str) -> dict:
    bas_match = re.search(r'file with basedata\s*:\s*(\S+)', content, re.IGNORECASE)

    if bas_match:
        basedata = bas_match.group(1)
        stem_raw = re.sub(r'\.(bas|sm)$', '', basedata, flags=re.IGNORECASE)
        stem = stem_raw.lower()
        instance_key = get_instance_key(stem)
        inst_type = get_instance_type(stem)
        name = instance_key + ".sm"
    else:
        name_match = re.search(r'^(j\d+_\d+\.sm)', content)
        if name_match:
            name = name_match.group(1)
            stem = re.sub(r'\.sm$', '', name)
            instance_key = get_instance_key(stem)
            inst_type = get_instance_type(stem)
        else:
            raise ValueError("Impossible de trouver le nom de l'instance.")

    jobs_match = re.search(r'[Jj]obs.*?[:=]\s*(\d+)', content)
    n_jobs = int(jobs_match.group(1)) if jobs_match else 32

    res_match = re.search(r'[Rr]enewable\s*[:=]\s*(\d+)', content)
    n_res = int(res_match.group(1)) if res_match else 4

    # Précédences
    prec_match = re.search(
        r'PRECEDENCE\s*RELATIONS\s*[:=?]\s*(.*?)\s*REQUESTS',
        content, re.DOTALL | re.IGNORECASE
    )

    successors_raw = {}
    if prec_match:
        prec_lines = prec_match.group(1).strip().split('\n')
        for line in prec_lines:
            line = line.strip()
            if not line or line.lower().startswith('jobnr') or \
               line.lower().startswith('job') or line.lower().startswith('pronr'):
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    job = int(parts[0])
                    n_succ = int(parts[2])
                    succs = [int(x) for x in parts[3:3+n_succ]]
                    successors_raw[job] = succs
                except (ValueError, IndexError):
                    continue

    # Durées et demandes
    req_match = re.search(
        r'REQUESTS/DURATIONS\s*[:=?]\s*(.*?)\s*RESOURCE\s*AVAIL',
        content, re.DOTALL | re.IGNORECASE
    )

    durations_raw = {}
    demands_raw = {}
    if req_match:
        req_lines = req_match.group(1).strip().split('\n')
        for line in req_lines:
            line = line.strip()
            if not line or line.lower().startswith('jobnr') or \
               line.lower().startswith('job') or line.startswith('-'):
                continue
            parts = line.split()
            if len(parts) >= 3 + n_res:
                try:
                    job = int(parts[0])
                    duration = int(parts[2])
                    demands = [int(parts[3 + r]) for r in range(n_res)]
                    durations_raw[job] = duration
                    demands_raw[job] = demands
                except (ValueError, IndexError):
                    continue

    # Capacités
    cap_match = re.search(
        r'RESOURCE\s*AVAILABILITIES\s*[:=?]\s*(.*?)(?:\*{5}|\Z)',
        content, re.DOTALL | re.IGNORECASE
    )

    caps = []
    if cap_match:
        cap_lines = cap_match.group(1).strip().split('\n')
        for line in cap_lines:
            line = line.strip()
            if not line or line.startswith('R') or line.startswith('*'):
                continue
            parts = line.split()
            if len(parts) >= n_res:
                try:
                    caps = [int(parts[r]) for r in range(n_res)]
                    break
                except ValueError:
                    continue

    if not caps:
        caps = [10, 10, 10, 10][:n_res]

    n_total = n_jobs
    durations = [durations_raw.get(j, 0) for j in range(1, n_total + 1)]
    demands = [demands_raw.get(j, [0]*n_res) for j in range(1, n_total + 1)]

    # Précédences en format paires
    prec_pairs = []
    for job, succs in successors_raw.items():
        for s in succs:
            prec_pairs.append([job, s])
    n_prec = len(prec_pairs)

    H_match = re.search(r'[Hh]orizon\s*[:=]\s*(\d+)', content)
    H = int(H_match.group(1)) if H_match else (800 if inst_type == 'J120' else 400)

    return {
        'name': name,
        'stem': instance_key,
        'inst_type': inst_type,
        'n_total': n_total,
        'H': H,
        'n_res': n_res,
        'caps': caps,
        'durations': durations,
        'demands': demands,
        'prec_pairs': prec_pairs,
        'n_prec': n_prec,
    }


# ===========================================================================
# 4. GÉNÉRATION DZN — FORMAT STANDARD DATZINC
# ===========================================================================

def to_dzn(data: dict, out_path: str) -> None:
    """Génère un fichier .dzn au format DataZinc STANDARD (MiniZinc pur)"""
    n = data['n_total']
    n_res = data['n_res']
    H = data['H']

    lines = [
        f"% Instance : {data['name']}",
        f"% Type : {data['inst_type']} ({n} tâches, dont {n-2} réelles)",
        f"",
        f"n = {n};",
        f"n_resources = {n_res};",
        f"horizon = {H};",
        f"",
        f"% Durées (tâche 1 = source, tâche {n} = puits)",
        f"duration = {data['durations']};",
        f"",
        f"% Capacités des ressources renouvelables",
        f"resource_avail = {data['caps']};",
        f"",
        f"% Demandes de ressources [job, resource] — format array2d standard",
        f"req = array2d(1..n, 1..n_resources, [",
    ]

    # Flatten demands for array2d
    flat_demands = []
    for job_demands in data['demands']:
        flat_demands.extend(job_demands)
    lines.append("    " + ", ".join(str(x) for x in flat_demands))
    lines.append("]);")
    lines.append("")

    # Precedence matrix (n x n)
    lines.append("% Matrice de précédence (1 si i précède j)")
    lines.append("precedence = array2d(1..n, 1..n, [")

    prec_flat = []
    for i in range(1, n + 1):
        for j in range(1, n + 1):
            # Check if i precedes j (i -> j is in prec_pairs)
            is_preceding = any(pair[0] == i and pair[1] == j for pair in data['prec_pairs'])
            prec_flat.append(1 if is_preceding else 0)

    lines.append("    " + ", ".join(str(x) for x in prec_flat))
    lines.append("]);")
    lines.append("")

    # Also add n_prec for info
    lines.append(f"% Nombre de relations de précédence: {data['n_prec']}")
    lines.append(f"n_prec = {data['n_prec']};")
    lines.append("")

    lines.append("% === FIN DU FICHIER ===")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"  [OK] {out_path} ({data['inst_type']}, n={n}, H={H}, prec={data['n_prec']})")


# ===========================================================================
# 5. MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Parser PSPLIB -> .dzn MiniZinc standard"
    )
    parser.add_argument("--input", "-i", default="instancesdebtp.docx",
                        help="Fichier source (.docx ou .txt)")
    parser.add_argument("--outdir", "-o", default="dzn_output",
                        help="Dossier de sortie")
    args = parser.parse_args()

    print(f"Chargement de : {args.input}")
    try:
        raw = load_raw_text(args.input)
    except Exception as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        sys.exit(1)

    all_blocks = re.split(
        r'(?=(?:\*{5,}\s*file with basedata\s*:\s*\S+|file with basedata\s*:\s*\S+|j\d+_\d+\.sm))',
        raw, flags=re.IGNORECASE
    )

    valid_blocks = []
    for b in all_blocks:
        b = b.strip()
        if not b:
            continue
        has_prec = 'PRECEDENCE' in b
        has_req = 'REQUESTS' in b
        has_res = 'RESOURCE' in b
        has_jobs = re.search(r'jobs.*?[:=]\s*\d+', b) is not None
        if has_prec and has_req and has_res and has_jobs:
            valid_blocks.append(b)

    blocks = valid_blocks
    if not blocks:
        print("ERREUR : Aucun bloc valide trouvé.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(blocks)} instance(s) détectée(s)\n")
    os.makedirs(args.outdir, exist_ok=True)

    for block in blocks:
        try:
            data = parse_block(block)
            dzn_path = os.path.join(args.outdir, f"{data['stem']}.dzn")
            to_dzn(data, dzn_path)
        except Exception as e:
            print(f"ERREUR : {e}", file=sys.stderr)

    print(f"\nFichiers .dzn écrits dans : {args.outdir}/")


if __name__ == "__main__":
    main()