#!/usr/bin/env python3
"""
Parser PSPLIB — Projet P2 RCPSP etendu (CP-INSEA-SDRO-2A)
=============================================================
Lit le fichier instancesdebtp.docx (J30 et J120 melanges),
parse toutes les instances, et genere les fichiers .dzn 
avec les 3 extensions BTP marocain + ANALYSE DE SCALABILITE.

Usage:
    python3 parser_btp.py --input instancesdebtp.docx --outdir dzn_output
    python3 parser_btp.py --input instancesdebtp.docx --scalabilite
"""

import re
import os
import argparse
import sys
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional


# ===========================================================================
# 1. PARAMETRES D'EXTENSION J30 (ORIGINAUX)
# ===========================================================================

DEBUT_ETE_J30 = 80
FIN_ETE_J30   = 140

STOCK_CIMENT_J30 = {
    "j301_1":   200,
    "j3021_1":  250,
    "j3029_1":  300,
    "j3045_1":  280,
    "j3082_1":  160,
}

CIMENT_PAR_TACHE_J30 = {
    "j301_1":   {1: 40, 2: 35, 5: 50, 8: 30, 11: 45},
    "j3021_1":  {0: 30, 3: 40, 6: 55, 10: 35, 14: 40},
    "j3029_1":  {1: 50, 4: 40, 7: 30, 12: 45, 18: 35},
    "j3045_1":  {0: 40, 3: 50, 6: 35, 9: 40, 15: 30},
    "j3082_1":  {2: 35, 3: 18, 4: 22, 5: 25, 6: 22, 7: 25, 8: 28},
}

TACHES_BETON_J30 = {
    "j301_1":   [2, 3, 6, 9, 12],
    "j3021_1":  [1, 4, 7, 11, 15],
    "j3029_1":  [2, 5, 8, 13, 19],
    "j3045_1":  [1, 4, 7, 10, 16],
    "j3082_1":  [4, 5, 6, 7, 8, 9, 10],
}

N_EQUIPEMENTS_J30 = {
    "j301_1":   2, "j3021_1":  2, "j3029_1":  2,
    "j3045_1":  2, "j3082_1":  2,
}

CAPACITE_EQUIPEMENT_J30 = {
    "j301_1":   [2, 1], "j3021_1":  [2, 1], "j3029_1":  [2, 1],
    "j3045_1":  [2, 1], "j3082_1":  [1, 1],
}

BESOIN_EQUIPEMENT_J30 = {
    "j301_1": {
        1:  [1, 1], 2:  [1, 1], 5:  [1, 1], 8:  [1, 1], 11: [1, 1],
        3:  [1, 0], 6:  [1, 0], 9:  [1, 0], 12: [1, 0],
    },
    "j3021_1": {
        0:  [1, 1], 3:  [1, 1], 6:  [1, 1], 10: [1, 1], 14: [1, 1],
        1:  [1, 0], 4:  [1, 0], 7:  [1, 0], 11: [1, 0],
    },
    "j3029_1": {
        1:  [1, 1], 4:  [1, 1], 7:  [1, 1], 12: [1, 1], 18: [1, 1],
        2:  [1, 0], 5:  [1, 0], 8:  [1, 0], 13: [1, 0],
    },
    "j3045_1": {
        0:  [1, 1], 3:  [1, 1], 6:  [1, 1], 9:  [1, 1], 15: [1, 1],
        1:  [1, 0], 4:  [1, 0], 7:  [1, 0], 10: [1, 0],
    },
    "j3082_1": {
        2:  [1, 1], 3:  [1, 1], 4:  [1, 1], 5:  [1, 1], 6:  [1, 1],
        7:  [1, 1], 8:  [1, 1], 9:  [1, 0], 10: [1, 0],
    },
}


# ===========================================================================
# 2. PARAMETRES D'EXTENSION J120 (NOUVEAUX)
# ===========================================================================

DEBUT_ETE_J120 = 150
FIN_ETE_J120   = 240

STOCK_CIMENT_J120 = {
    "j1201_1":   600,
    "j1201_2":   650,
    "j1201_3":   620,
    "j1201_4":   580,
}

CIMENT_PAR_TACHE_J120 = {
    "j1201_1": {
        2: 40, 5: 35, 8: 50, 12: 30, 15: 45,
        18: 35, 22: 40, 25: 50, 30: 30, 35: 45,
        40: 35, 45: 40, 50: 30, 55: 45, 60: 35,
        65: 40, 70: 30, 75: 45, 80: 35, 85: 40,
    },
    "j1201_2": {
        1: 35, 4: 45, 7: 30, 10: 50, 14: 35,
        18: 40, 22: 30, 26: 45, 30: 35, 34: 50,
        38: 30, 42: 45, 46: 35, 50: 40, 54: 30,
        58: 45, 62: 35, 66: 40, 70: 30, 74: 45,
    },
    "j1201_3": {
        3: 40, 6: 35, 9: 50, 13: 30, 17: 45,
        21: 35, 25: 40, 29: 30, 33: 45, 37: 35,
        41: 40, 45: 30, 49: 45, 53: 35, 57: 40,
        61: 30, 65: 45, 69: 35, 73: 40, 77: 30,
    },
    "j1201_4": {
        0: 45, 4: 30, 8: 50, 12: 35, 16: 40,
        20: 30, 24: 45, 28: 35, 32: 40, 36: 30,
        40: 45, 44: 35, 48: 40, 52: 30, 56: 45,
        60: 35, 64: 40, 68: 30, 72: 45, 76: 35,
    },
}

TACHES_BETON_J120 = {
    "j1201_1":  [3, 6, 9, 13, 16, 19, 23, 26, 31, 36, 41, 46, 51, 56, 61, 66, 71, 76, 81, 86],
    "j1201_2":  [2, 5, 8, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71, 75],
    "j1201_3":  [4, 7, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50, 54, 58, 62, 66, 70, 74, 78],
    "j1201_4":  [1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 65, 69, 73, 77],
}

N_EQUIPEMENTS_J120 = {
    "j1201_1":  3, "j1201_2":  3, "j1201_3":  3, "j1201_4":  3,
}

CAPACITE_EQUIPEMENT_J120 = {
    "j1201_1":  [2, 1, 2], "j1201_2":  [2, 1, 2],
    "j1201_3":  [2, 1, 2], "j1201_4":  [2, 1, 2],
}

BESOIN_EQUIPEMENT_J120 = {
    "j1201_1": {
        2:  [1, 1, 0], 5:  [1, 1, 0], 8:  [1, 1, 0], 12: [1, 1, 0], 15: [1, 1, 0],
        18: [1, 1, 0], 22: [1, 1, 0], 25: [1, 1, 0], 30: [1, 1, 0], 35: [1, 1, 0],
        0:  [0, 0, 1], 10: [0, 0, 1], 20: [0, 0, 1], 40: [0, 0, 1], 50: [0, 0, 1],
        60: [0, 0, 1], 70: [0, 0, 1], 80: [0, 0, 1],
        4:  [1, 0, 0], 9:  [1, 0, 0], 14: [1, 0, 0], 19: [1, 0, 0], 24: [1, 0, 0],
        29: [1, 0, 0], 34: [1, 0, 0], 39: [1, 0, 0], 44: [1, 0, 0], 49: [1, 0, 0],
        54: [1, 0, 0], 59: [1, 0, 0], 64: [1, 0, 0], 69: [1, 0, 0], 74: [1, 0, 0],
        79: [1, 0, 0], 84: [1, 0, 0],
    },
    "j1201_2": {
        1:  [1, 1, 0], 4:  [1, 1, 0], 7:  [1, 1, 0], 10: [1, 1, 0], 15: [1, 1, 0],
        19: [1, 1, 0], 23: [1, 1, 0], 27: [1, 1, 0], 31: [1, 1, 0], 35: [1, 1, 0],
        0:  [0, 0, 1], 11: [0, 0, 1], 21: [0, 0, 1], 41: [0, 0, 1], 51: [0, 0, 1],
        61: [0, 0, 1], 71: [0, 0, 1],
        3:  [1, 0, 0], 8:  [1, 0, 0], 13: [1, 0, 0], 18: [1, 0, 0], 22: [1, 0, 0],
        26: [1, 0, 0], 30: [1, 0, 0], 34: [1, 0, 0], 38: [1, 0, 0], 42: [1, 0, 0],
        46: [1, 0, 0], 50: [1, 0, 0], 54: [1, 0, 0], 58: [1, 0, 0], 62: [1, 0, 0],
        66: [1, 0, 0], 70: [1, 0, 0], 74: [1, 0, 0],
    },
    "j1201_3": {
        3:  [1, 1, 0], 6:  [1, 1, 0], 9:  [1, 1, 0], 13: [1, 1, 0], 17: [1, 1, 0],
        21: [1, 1, 0], 25: [1, 1, 0], 29: [1, 1, 0], 33: [1, 1, 0], 37: [1, 1, 0],
        1:  [0, 0, 1], 12: [0, 0, 1], 22: [0, 0, 1], 32: [0, 0, 1], 42: [0, 0, 1],
        52: [0, 0, 1], 62: [0, 0, 1], 72: [0, 0, 1],
        0:  [1, 0, 0], 5:  [1, 0, 0], 10: [1, 0, 0], 15: [1, 0, 0], 20: [1, 0, 0],
        24: [1, 0, 0], 28: [1, 0, 0], 31: [1, 0, 0], 35: [1, 0, 0], 39: [1, 0, 0],
        44: [1, 0, 0], 48: [1, 0, 0], 53: [1, 0, 0], 57: [1, 0, 0], 61: [1, 0, 0],
        65: [1, 0, 0], 69: [1, 0, 0], 73: [1, 0, 0], 77: [1, 0, 0],
    },
    "j1201_4": {
        0:  [1, 1, 0], 4:  [1, 1, 0], 8:  [1, 1, 0], 12: [1, 1, 0], 16: [1, 1, 0],
        20: [1, 1, 0], 24: [1, 1, 0], 28: [1, 1, 0], 32: [1, 1, 0], 36: [1, 1, 0],
        2:  [0, 0, 1], 13: [0, 0, 1], 23: [0, 0, 1], 33: [0, 0, 1], 43: [0, 0, 1],
        53: [0, 0, 1], 63: [0, 0, 1], 73: [0, 0, 1],
        3:  [1, 0, 0], 7:  [1, 0, 0], 11: [1, 0, 0], 15: [1, 0, 0], 19: [1, 0, 0],
        22: [1, 0, 0], 26: [1, 0, 0], 30: [1, 0, 0], 34: [1, 0, 0], 38: [1, 0, 0],
        42: [1, 0, 0], 46: [1, 0, 0], 50: [1, 0, 0], 54: [1, 0, 0], 58: [1, 0, 0],
        62: [1, 0, 0], 66: [1, 0, 0], 70: [1, 0, 0], 74: [1, 0, 0],
    },
}


# ===========================================================================
# 3. MAPPING NOMS BASEDATA -> CLES DICO (CORRECTION)
# ===========================================================================

# Mapping: j30_17.bas -> j301_1, j30_37.bas -> j3021_1, etc.
NAME_MAPPING = {
    # J30
    "j30_17":   "j301_1",
    "j30_37":   "j3021_1",
    "j30_45":   "j3029_1",
    "j30_61":   "j3045_1",
    "j30_82":   "j3082_1",
    # J120
    "j1201_1":  "j1201_1",
    "j1201_2":  "j1201_2",
    "j1201_3":  "j1201_3",
    "j1201_4":  "j1201_4",
}


def get_instance_key(basedata_name: str) -> str:
    """Convertit le nom basedata en cle de dictionnaire"""
    # Nettoyer: j30_17.bas -> j30_17
    clean = basedata_name.lower().replace('.bas', '').replace('.sm', '').strip()
    # Chercher dans le mapping
    if clean in NAME_MAPPING:
        return NAME_MAPPING[clean]
    # Fallback: essayer de deviner
    return clean


# ===========================================================================
# 4. FONCTIONS COMMUNES
# ===========================================================================

def extract_text_from_docx(docx_path: str) -> str:
    try:
        import docx as _docx
    except ImportError:
        raise RuntimeError("python-docx non installe. Lancez : pip3 install python-docx")
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


def format_list(lst: list) -> str:
    return "[" + ", ".join(str(x) for x in lst) + "]"


def format_2d(matrix: list) -> str:
    rows = " | ".join(", ".join(str(x) for x in row) for row in matrix)
    return "[| " + rows + " |]"


# ===========================================================================
# 5. PARSING D'UN BLOC (J30 ou J120) — VERSION CORRIGEE
# ===========================================================================

def parse_block(content: str) -> dict:
    """Parse un bloc d'instance PSPLIB (J30 ou J120)"""

    # === DETECTION DU NOM D'INSTANCE (CORRIGE) ===
    # Priorite 1: basedata dans le bloc
    bas_match = re.search(r'file with basedata\s*:\s*(\S+)', content, re.IGNORECASE)

    if bas_match:
        basedata = bas_match.group(1)
        stem_raw = re.sub(r'\.(bas|sm)$', '', basedata, flags=re.IGNORECASE)
        stem = stem_raw.lower()
        instance_key = get_instance_key(stem)
        is_j120 = stem.startswith('j120')
        # Nom de fichier pour le .dzn
        name = instance_key + ".sm"
    else:
        # Fallback: ancienne methode
        name_match = re.search(r'^(j\d+_\d+\.sm)', content)
        if name_match:
            name = name_match.group(1)
            stem = re.sub(r'\.sm$', '', name)
            instance_key = get_instance_key(stem)
            is_j120 = stem.startswith('j120')
        else:
            raise ValueError("Impossible de trouver le nom de l'instance dans le bloc.")

    # === EXTRACTION METADONNEES ===
    H_match = re.search(r'[Hh]orizon\s*[:=]\s*(\d+)', content)
    H = int(H_match.group(1)) if H_match else (800 if is_j120 else 200)

    jobs_match = re.search(r'[Jj]obs.*?[:]\s*(\d+)', content)
    n_jobs = int(jobs_match.group(1)) if jobs_match else (122 if is_j120 else 32)
    n_real = n_jobs - 2

    res_match = re.search(r'[Rr]enewable\s*[:=]\s*(\d+)', content)
    n_res = int(res_match.group(1)) if res_match else 4

    # === PRECEDENCES ===
    prec_match = re.search(
        r'PRECEDENCE\s*RELATIONS\s*[:=]?\s*(.*?)\s*REQUESTS',
        content, re.DOTALL | re.IGNORECASE
    )

    successors_raw = {}
    if prec_match:
        prec_lines = prec_match.group(1).strip().split('\n')
        for line in prec_lines:
            line = line.strip()
            if not line or line.lower().startswith('jobnr') or line.lower().startswith('job') or line.lower().startswith('pronr'):
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

    # === DUREES ET DEMANDES ===
    req_match = re.search(
        r'REQUESTS/DURATIONS\s*[:=]?\s*(.*?)\s*RESOURCE\s*AVAIL',
        content, re.DOTALL | re.IGNORECASE
    )

    durations_raw = {}
    demands_raw = {}
    if req_match:
        req_lines = req_match.group(1).strip().split('\n')
        for line in req_lines:
            line = line.strip()
            if not line or line.lower().startswith('jobnr') or line.lower().startswith('job') or line.startswith('-'):
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

    # === CAPACITES ===
    cap_match = re.search(
        r'RESOURCE\s*AVAILABILITIES\s*[:=]?\s*(.*?)(?:\*{5}|\Z)',
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

    # === REORGANISATION 0-BASED ===
    real_jobs = list(range(2, n_jobs))
    n = len(real_jobs)

    durations = [durations_raw.get(j, 0) for j in real_jobs]
    demands = [demands_raw.get(j, [0]*n_res) for j in real_jobs]

    prec_matrix = [[0] * n for _ in range(n)]
    job_map = {j: i for i, j in enumerate(real_jobs)}

    for job, succs in successors_raw.items():
        if job in job_map:
            for s in succs:
                if s in job_map:
                    prec_matrix[job_map[job]][job_map[s]] = 1

    return {
        'name': name,
        'stem': instance_key,
        'stem_raw': stem,
        'is_j120': is_j120,
        'n': n,
        'H': H,
        'n_res': n_res,
        'caps': caps,
        'durations': durations,
        'demands': demands,
        'prec_matrix': prec_matrix,
    }


# ===========================================================================
# 6. METRIQUES DE SCALABILITE
# ===========================================================================

def compute_metrics(data: dict) -> dict:
    """Calcule les metriques RF, RS, NC, etc."""
    n = data['n']
    n_res = data['n_res']
    caps = data['caps']
    demands = data['demands']
    durations = data['durations']
    prec_matrix = data['prec_matrix']

    # RF: Resource Factor (couverture)
    uses_res = sum(1 for d in demands if any(x > 0 for x in d))
    rf = round(uses_res / n, 3) if n > 0 else 0

    # RS: Resource Strength (pression)
    rs_vals = []
    for r in range(n_res):
        col = [demands[i][r] for i in range(n)]
        mx = max(col) if col else 1
        if mx > 0:
            rs_vals.append(round(caps[r] / mx, 3))
    rs = round(sum(rs_vals) / len(rs_vals), 3) if rs_vals else 0

    # NC: Network Complexity (OS - Order Strength)
    total_prec = sum(prec_matrix[i][j] for i in range(n) for j in range(n))
    max_prec = n * (n - 1) / 2
    nc = round(total_prec / max_prec, 3) if max_prec > 0 else 0

    # Work content
    total_work = sum(durations)
    avg_duration = round(total_work / n, 1) if n > 0 else 0

    # Utilisation ressources
    util = {}
    for r in range(n_res):
        total_demand = sum(demands[i][r] * durations[i] for i in range(n))
        capacity = caps[r] * data['H']
        util[f"R{r+1}"] = round(total_demand / capacity, 3) if capacity > 0 else 0

    return {
        'rf': rf,
        'rs': rs,
        'nc': nc,
        'total_work': total_work,
        'avg_duration': avg_duration,
        'utilization': util,
    }


def analyze_scalability(all_data: list) -> dict:
    """Analyse de scalabilite entre toutes les instances"""
    results = []

    for data in all_data:
        metrics = compute_metrics(data)
        info = {
            'name': data['name'],
            'stem': data['stem'],
            'type': 'J120' if data['is_j120'] else 'J30',
            'n_jobs': data['n'],
            'horizon': data['H'],
            'n_resources': data['n_res'],
            'caps': data['caps'],
            'rf': metrics['rf'],
            'rs': metrics['rs'],
            'nc': metrics['nc'],
            'total_work': metrics['total_work'],
            'avg_duration': metrics['avg_duration'],
            'utilization': metrics['utilization'],
        }
        results.append(info)

    # Ratios J30 vs J120
    j30_instances = [r for r in results if r['type'] == 'J30']
    j120_instances = [r for r in results if r['type'] == 'J120']

    summary = {}
    if j30_instances and j120_instances:
        avg_j30_jobs = sum(r['n_jobs'] for r in j30_instances) / len(j30_instances)
        avg_j120_jobs = sum(r['n_jobs'] for r in j120_instances) / len(j120_instances)
        avg_j30_horizon = sum(r['horizon'] for r in j30_instances) / len(j30_instances)
        avg_j120_horizon = sum(r['horizon'] for r in j120_instances) / len(j120_instances)
        avg_j30_work = sum(r['total_work'] for r in j30_instances) / len(j30_instances)
        avg_j120_work = sum(r['total_work'] for r in j120_instances) / len(j120_instances)

        summary = {
            'ratio_jobs_j120_j30': round(avg_j120_jobs / avg_j30_jobs, 2) if avg_j30_jobs > 0 else 0,
            'ratio_horizon_j120_j30': round(avg_j120_horizon / avg_j30_horizon, 2) if avg_j30_horizon > 0 else 0,
            'ratio_work_j120_j30': round(avg_j120_work / avg_j30_work, 2) if avg_j30_work > 0 else 0,
            'avg_rf_j30': round(sum(r['rf'] for r in j30_instances) / len(j30_instances), 3),
            'avg_rf_j120': round(sum(r['rf'] for r in j120_instances) / len(j120_instances), 3),
            'avg_rs_j30': round(sum(r['rs'] for r in j30_instances) / len(j30_instances), 3),
            'avg_rs_j120': round(sum(r['rs'] for r in j120_instances) / len(j120_instances), 3),
            'avg_nc_j30': round(sum(r['nc'] for r in j30_instances) / len(j30_instances), 3),
            'avg_nc_j120': round(sum(r['nc'] for r in j120_instances) / len(j120_instances), 3),
        }

    return {'instances': results, 'summary': summary}


# ===========================================================================
# 7. GENERATION DZN
# ===========================================================================

def to_dzn(data: dict, out_path: str) -> None:
    stem = data['stem']
    is_j120 = data['is_j120']
    n = data['n']

    if is_j120:
        debut_ete = DEBUT_ETE_J120
        fin_ete = FIN_ETE_J120
        stock_ciment = STOCK_CIMENT_J120.get(stem, 600)
        ciment_par_tache = CIMENT_PAR_TACHE_J120.get(stem, {})
        taches_beton = TACHES_BETON_J120.get(stem, [])
        n_equipements = N_EQUIPEMENTS_J120.get(stem, 3)
        capacite_equipement = CAPACITE_EQUIPEMENT_J120.get(stem, [2, 1, 2])
        besoin_equipement = BESOIN_EQUIPEMENT_J120.get(stem, {})
    else:
        debut_ete = DEBUT_ETE_J30
        fin_ete = FIN_ETE_J30
        stock_ciment = STOCK_CIMENT_J30.get(stem, 300)
        ciment_par_tache = CIMENT_PAR_TACHE_J30.get(stem, {})
        taches_beton = TACHES_BETON_J30.get(stem, [])
        n_equipements = N_EQUIPEMENTS_J30.get(stem, 2)
        capacite_equipement = CAPACITE_EQUIPEMENT_J30.get(stem, [2, 1])
        besoin_equipement = BESOIN_EQUIPEMENT_J30.get(stem, {})

    ciment = [0] * n
    for idx, qty in ciment_par_tache.items():
        if 0 <= idx < n:
            ciment[idx] = qty

    besoin_eq = [[0] * n_equipements for _ in range(n)]
    for idx, needs in besoin_equipement.items():
        if 0 <= idx < n:
            for e in range(min(len(needs), n_equipements)):
                besoin_eq[idx][e] = needs[e]

    lines = [
        f"% Instance : {data['name']}",
        f"% Generee par parser_btp.py — Projet P2 RCPSP etendu INSEA",
        f"% Type : {'J120' if is_j120 else 'J30'} (n={n} taches)",
        f"% Extensions : Climatique + NR + Equipements lourds + Scalabilite",
        f"",
        f"% --- Parametres de base ---",
        f"n     = {n};",
        f"H     = {data['H']};",
        f"n_res = {data['n_res']};",
        f"",
        f"% --- Durees des taches (jours) ---",
        f"duree = {format_list(data['durations'])};",
        f"",
        f"% --- Capacites ressources renouvelables standard ---",
        f"capacite = {format_list(data['caps'])};",
        f"",
        f"% --- Demandes en ressources renouvelables [tache, ressource] ---",
        f"besoin = {format_2d(data['demands'])};",
        f"",
        f"% --- Matrice de precedence [i,j]=1 si i doit finir avant j ---",
        f"prec = {format_2d(data['prec_matrix'])};",
        f"",
        f"% --- Extension A : Fenetre climatique ---",
        f"debut_ete = {debut_ete};",
        f"fin_ete   = {fin_ete};",
        f"",
        f"% --- Extension B : Taches beton ---",
        f"TACHES_BETON = {{{', '.join(str(t) for t in taches_beton)}}};",
        f"",
        f"% --- Extension C : Ressource non-renouvelable (ciment) ---",
        f"stock_NR = {stock_ciment};",
        f"ciment   = {format_list(ciment)};",
        f"",
        f"% --- Extension D : Equipements lourds partages ---",
        f"n_equipements = {n_equipements};",
        f"capacite_equipement = {format_list(capacite_equipement)};",
        f"besoin_equipement = {format_2d(besoin_eq)};",
    ]

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"  [OK] {out_path} ({'J120' if is_j120 else 'J30'}, {n} taches, "
          f"beton={len(taches_beton)}, equip={n_equipements})")


# ===========================================================================
# 8. AFFICHAGE RESUME + TABLEAU SCALABILITE
# ===========================================================================

def print_summary(data: dict) -> None:
    stem = data['stem']
    n = data['n']
    is_j120 = data['is_j120']
    metrics = compute_metrics(data)

    print(f"\n{'='*60}")
    print(f"Instance : {data['name']} ({'J120' if is_j120 else 'J30'})")
    print(f"  Cle dictionnaire   : {stem}")
    print(f"  Taches reelles     : {n}")
    print(f"  Horizon H          : {data['H']}")
    print(f"  Ressources         : {data['n_res']}")
    print(f"  Capacites          : {data['caps']}")
    print(f"  RF (couverture)    : {metrics['rf']}")
    print(f"  RS (pression)      : {metrics['rs']}")
    print(f"  NC (precedences)   : {metrics['nc']}")
    print(f"  Travail total      : {metrics['total_work']} jours")
    print(f"  Duree moyenne      : {metrics['avg_duration']} jours")

    if is_j120:
        stock = STOCK_CIMENT_J120.get(stem, 'N/A')
        n_beton = len(TACHES_BETON_J120.get(stem, []))
        n_equip = N_EQUIPEMENTS_J120.get(stem, 0)
        cap_equip = CAPACITE_EQUIPEMENT_J120.get(stem, [])
    else:
        stock = STOCK_CIMENT_J30.get(stem, 'N/A')
        n_beton = len(TACHES_BETON_J30.get(stem, []))
        n_equip = N_EQUIPEMENTS_J30.get(stem, 0)
        cap_equip = CAPACITE_EQUIPEMENT_J30.get(stem, [])

    print(f"  Stock ciment       : {stock} t")
    print(f"  Taches beton       : {n_beton}")
    print(f"  Equipements lourds : {n_equip} types")
    print(f"  Capacite equip.    : {cap_equip}")


def print_scalability_table(all_data: list):
    """Affiche le tableau comparatif de scalabilite"""
    analysis = analyze_scalability(all_data)

    print(f"\n{'='*70}")
    print("ANALYSE DE SCALABILITE")
    print(f"{'='*70}")

    print(f"\n{'Instance':<15} {'Type':>6} {'Jobs':>6} {'Horizon':>8} {'Work':>8} {'RF':>6} {'RS':>6} {'NC':>6}")
    print("-" * 70)
    for info in analysis['instances']:
        print(f"{info['name']:<15} {info['type']:>6} {info['n_jobs']:>6} "
              f"{info['horizon']:>8} {info['total_work']:>8} {info['rf']:>6.3f} "
              f"{info['rs']:>6.3f} {info['nc']:>6.3f}")

    if analysis['summary']:
        print(f"\n{'='*70}")
        print("RATIOS J120 / J30")
        print(f"{'='*70}")
        s = analysis['summary']
        print(f"  Ratio jobs    : {s['ratio_jobs_j120_j30']:.2f}x")
        print(f"  Ratio horizon : {s['ratio_horizon_j120_j30']:.2f}x")
        print(f"  Ratio travail : {s['ratio_work_j120_j30']:.2f}x")
        print(f"\n  RF moyen J30  : {s['avg_rf_j30']:.3f} | J120 : {s['avg_rf_j120']:.3f}")
        print(f"  RS moyen J30  : {s['avg_rs_j30']:.3f} | J120 : {s['avg_rs_j120']:.3f}")
        print(f"  NC moyen J30  : {s['avg_nc_j30']:.3f} | J120 : {s['avg_nc_j120']:.3f}")

    return analysis


# ===========================================================================
# 9. MAIN — VERSION CORRIGEE AVEC SCALABILITE
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Parser PSPLIB J30+J120 depuis .docx -> .dzn MiniZinc + Scalabilite"
    )
    parser.add_argument("--input", "-i", default="instancesdebtp.docx",
                        help="Chemin vers le fichier source (.docx ou .txt)")
    parser.add_argument("--outdir", "-o", default="dzn_output",
                        help="Dossier de sortie pour les fichiers .dzn")
    parser.add_argument("--verify", "-v", action="store_true",
                        help="Afficher le resume uniquement (pas de .dzn)")
    parser.add_argument("--scalabilite", "-s", action="store_true",
                        help="Generer le rapport de scalabilite JSON")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Mode debug: afficher les noms trouves")
    args = parser.parse_args()

    print(f"Chargement de : {args.input}")
    try:
        raw = load_raw_text(args.input)
    except Exception as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        sys.exit(1)

    # Mode debug
    if args.debug:
        bas_names = re.findall(r'file with basedata\s*:\s*(\S+)', raw, re.IGNORECASE)
        print(f"\n[DEBUG] Basedata trouves ({len(bas_names)}): {bas_names}")
        print()

    # Split sur les patterns de debut d'instance
    all_blocks = re.split(
        r'(?=(?:\*{5,}\s*file with basedata\s*:\s*\S+|file with basedata\s*:\s*\S+|j30\d+_\d+\.sm))',
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
        has_jobs = re.search(r'jobs.*?:\s*\d+', b) is not None

        if has_prec and has_req and has_res and has_jobs:
            valid_blocks.append(b)
        elif args.debug and (has_prec or has_req):
            preview = b[:100].replace('\n', ' ')
            print(f"[DEBUG] Bloc rejete: {preview}...")

    blocks = valid_blocks

    if not blocks:
        print("ERREUR : Aucun bloc valide trouve.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(blocks)} instance(s) detectee(s)\n")

    if not args.verify:
        os.makedirs(args.outdir, exist_ok=True)

    all_data = []
    j30_count = 0
    j120_count = 0

    for block in blocks:
        try:
            data = parse_block(block)
            all_data.append(data)

            print_summary(data)

            if not args.verify:
                dzn_path = os.path.join(args.outdir, f"{data['stem']}.dzn")
                to_dzn(data, dzn_path)

                if data['is_j120']:
                    j120_count += 1
                else:
                    j30_count += 1

        except Exception as e:
            print(f"ERREUR lors du parsing : {e}", file=sys.stderr)
            if args.debug:
                preview = block[:200].replace('\n', ' ')
                print(f"  [DEBUG] Debut du bloc: {preview}...", file=sys.stderr)

    # Analyse de scalabilite
    if len(all_data) > 1:
        analysis = print_scalability_table(all_data)

        if args.scalabilite:
            scal_file = os.path.join(args.outdir, 'scalabilite_analysis.json')
            with open(scal_file, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
            print(f"\n[OK] Rapport de scalabilite: {scal_file}")

    if not args.verify:
        print(f"\n{'='*60}")
        print(f"Fichiers .dzn ecrits dans : {args.outdir}/")
        print(f"  J30 : {j30_count} instances")
        print(f"  J120: {j120_count} instances")
        print(f"  Total: {j30_count + j120_count} instances")


if __name__ == "__main__":
    main()