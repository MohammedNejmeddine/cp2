#!/usr/bin/env python3
"""
Parser PSPLIB — Projet P2 RCPSP Étendu (CP-INSEA-SDRO-2A)
=============================================================
Version CORRIGÉE v3 :
  - Génère des .dzn compatibles avec le modèle du prof (n_total, n_RR, etc.)
  - Conserve les dummies (source/puits) comme dans le format PSPLIB original
  - Format précédences en paires n_prec×2 (compatible modèle prof)
  - 3 ressources non-renouvelables : Ciment, Acier, Gravier
  - Analyse de scalabilité sur J30, J60, J90, J120
  - Génère aussi un fichier de métriques pour comparaison CP vs MILP

Usage:
    python3 parser_btp_v3.py --input instancesdebtp.docx --outdir dzn_output
    python3 parser_btp_v3.py --input instancesdebtp.docx --scalabilite
"""

import re
import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional


# ===========================================================================
# 1. PARAMÈTRES D'EXTENSION BTP MAROCAIN — J30
# ===========================================================================

DEBUT_ETE_J30 = 80
FIN_ETE_J30   = 140

def _compute_stocks(ciment_dict: dict, marge: float = 1.05) -> dict:
    """Calcule stock_NR = sum(ciment) * marge."""
    return {inst: round(sum(vals.values()) * marge) for inst, vals in ciment_dict.items()}

# Indices 1-based (format PSPLIB avec dummies : tâche 1=source, tâche N=puits)
# Les indices ci-dessous sont les numéros de tâches PSPLIB (1-based avec dummies)
CIMENT_PAR_TACHE_J30 = {
    "j301_1":   {4: 40, 5: 35, 8: 50, 11: 30, 14: 45},    # j30_17
    "j3021_1":  {3: 30, 6: 40, 9: 55, 13: 35, 17: 40},    # j30_37
    "j3029_1":  {4: 50, 7: 40, 10: 30, 15: 45, 21: 35},   # j30_45
    "j3045_1":  {3: 40, 6: 50, 9: 35, 12: 40, 18: 30},    # j30_61
    "j3082_1":  {5: 35, 6: 18, 7: 22, 8: 25, 9: 22, 10: 25, 11: 28},  # j30_82
}

STOCK_CIMENT_J30 = _compute_stocks(CIMENT_PAR_TACHE_J30)

# Tâches béton identifiées par leurs numéros PSPLIB (1-based avec dummies)
TACHES_BETON_J30 = {
    "j301_1":   [4, 5, 8, 11, 14],       # j30_17
    "j3021_1":  [3, 6, 9, 13, 17],       # j30_37
    "j3029_1":  [4, 7, 10, 15, 21],      # j30_45
    "j3045_1":  [3, 6, 9, 12, 18],       # j30_61
    "j3082_1":  [5, 6, 7, 8, 9, 10, 11], # j30_82
}

# Acier et Gravier (mêmes tâches que ciment, proportions différentes)
ACIER_PAR_TACHE_J30 = {
    "j301_1":   {4: 8, 5: 6, 8: 12, 11: 5, 14: 10},
    "j3021_1":  {3: 6, 6: 9, 9: 14, 13: 7, 17: 9},
    "j3029_1":  {4: 10, 7: 8, 10: 5, 15: 9, 21: 7},
    "j3045_1":  {3: 8, 6: 12, 9: 7, 12: 8, 18: 5},
    "j3082_1":  {5: 7, 6: 3, 7: 4, 8: 5, 9: 4, 10: 5, 11: 6},
}

STOCK_ACIER_J30 = _compute_stocks(ACIER_PAR_TACHE_J30, marge=1.05)

GRAVIER_PAR_TACHE_J30 = {
    "j301_1":   {4: 70, 5: 45, 8: 90, 11: 40, 14: 75},
    "j3021_1":  {3: 55, 6: 75, 9: 95, 13: 55, 17: 70},
    "j3029_1":  {4: 90, 7: 70, 10: 50, 15: 80, 21: 65},
    "j3045_1":  {3: 70, 6: 85, 9: 60, 12: 70, 18: 50},
    "j3082_1":  {5: 60, 6: 35, 7: 45, 8: 50, 9: 45, 10: 50, 11: 55},
}

STOCK_GRAVIER_J30 = _compute_stocks(GRAVIER_PAR_TACHE_J30, marge=1.05)


# ===========================================================================
# 2. PARAMÈTRES D'EXTENSION — J60
# ===========================================================================

DEBUT_ETE_J60 = 120
FIN_ETE_J60   = 200

CIMENT_PAR_TACHE_J60 = {
    "j601_1":   {3: 35, 7: 45, 12: 30, 18: 50, 25: 40, 32: 35, 40: 45, 48: 30, 55: 40},
    "j601_2":   {4: 40, 9: 35, 15: 50, 22: 30, 28: 45, 35: 35, 42: 50, 50: 30, 58: 40},
    "j601_3":   {5: 45, 10: 40, 16: 35, 20: 50, 27: 30, 33: 45, 38: 35, 45: 50, 52: 30},
    "j601_4":   {2: 30, 6: 50, 14: 40, 19: 35, 24: 45, 30: 30, 36: 50, 44: 40, 51: 35},
}

STOCK_CIMENT_J60 = _compute_stocks(CIMENT_PAR_TACHE_J60)

TACHES_BETON_J60 = {
    "j601_1":   [3, 7, 12, 18, 25, 32, 40, 48, 55],
    "j601_2":   [4, 9, 15, 22, 28, 35, 42, 50, 58],
    "j601_3":   [5, 10, 16, 20, 27, 33, 38, 45, 52],
    "j601_4":   [2, 6, 14, 19, 24, 30, 36, 44, 51],
}

ACIER_PAR_TACHE_J60 = {
    "j601_1":   {3: 7, 7: 9, 12: 6, 18: 10, 25: 8, 32: 7, 40: 9, 48: 6, 55: 8},
    "j601_2":   {4: 8, 9: 7, 15: 10, 22: 6, 28: 9, 35: 7, 42: 10, 50: 6, 58: 8},
    "j601_3":   {5: 9, 10: 8, 16: 7, 20: 10, 27: 6, 33: 9, 38: 7, 45: 10, 52: 6},
    "j601_4":   {2: 6, 6: 10, 14: 8, 19: 7, 24: 9, 30: 6, 36: 10, 44: 8, 51: 7},
}

STOCK_ACIER_J60 = _compute_stocks(ACIER_PAR_TACHE_J60, marge=1.05)

GRAVIER_PAR_TACHE_J60 = {
    "j601_1":   {3: 60, 7: 80, 12: 55, 18: 90, 25: 75, 32: 65, 40: 80, 48: 55, 55: 75},
    "j601_2":   {4: 70, 9: 60, 15: 85, 22: 55, 28: 80, 35: 65, 42: 85, 50: 55, 58: 70},
    "j601_3":   {5: 80, 10: 70, 16: 60, 20: 85, 27: 55, 33: 80, 38: 65, 45: 85, 52: 55},
    "j601_4":   {2: 55, 6: 85, 14: 70, 19: 60, 24: 80, 30: 55, 36: 85, 44: 70, 51: 60},
}

STOCK_GRAVIER_J60 = _compute_stocks(GRAVIER_PAR_TACHE_J60, marge=1.05)


# ===========================================================================
# 3. PARAMÈTRES D'EXTENSION — J90
# ===========================================================================

DEBUT_ETE_J90 = 150
FIN_ETE_J90   = 240

CIMENT_PAR_TACHE_J90 = {
    "j901_1":   {4: 40, 10: 35, 18: 50, 25: 30, 32: 45, 40: 35, 48: 50, 55: 30, 62: 40, 70: 35, 78: 45},
    "j901_2":   {5: 45, 12: 40, 20: 35, 28: 50, 35: 30, 42: 45, 50: 35, 58: 50, 65: 30, 72: 40, 80: 35},
    "j901_3":   {3: 35, 8: 50, 15: 40, 22: 35, 30: 50, 38: 30, 45: 45, 52: 35, 60: 50, 68: 30, 75: 40},
    "j901_4":   {6: 50, 14: 35, 21: 45, 29: 30, 36: 50, 44: 35, 51: 45, 59: 30, 66: 50, 74: 35, 82: 45},
}

STOCK_CIMENT_J90 = _compute_stocks(CIMENT_PAR_TACHE_J90)

TACHES_BETON_J90 = {
    "j901_1":   [4, 10, 18, 25, 32, 40, 48, 55, 62, 70, 78],
    "j901_2":   [5, 12, 20, 28, 35, 42, 50, 58, 65, 72, 80],
    "j901_3":   [3, 8, 15, 22, 30, 38, 45, 52, 60, 68, 75],
    "j901_4":   [6, 14, 21, 29, 36, 44, 51, 59, 66, 74, 82],
}

ACIER_PAR_TACHE_J90 = {
    "j901_1":   {4: 8, 10: 7, 18: 10, 25: 6, 32: 9, 40: 7, 48: 10, 55: 6, 62: 8, 70: 7, 78: 9},
    "j901_2":   {5: 9, 12: 8, 20: 7, 28: 10, 35: 6, 42: 9, 50: 7, 58: 10, 65: 6, 72: 8, 80: 7},
    "j901_3":   {3: 7, 8: 10, 15: 8, 22: 7, 30: 10, 38: 6, 45: 9, 52: 7, 60: 10, 68: 6, 75: 8},
    "j901_4":   {6: 10, 14: 7, 21: 9, 29: 6, 36: 10, 44: 7, 51: 9, 59: 6, 66: 10, 74: 7, 82: 9},
}

STOCK_ACIER_J90 = _compute_stocks(ACIER_PAR_TACHE_J90, marge=1.05)

GRAVIER_PAR_TACHE_J90 = {
    "j901_1":   {4: 70, 10: 60, 18: 90, 25: 55, 32: 80, 40: 65, 48: 90, 55: 55, 62: 75, 70: 65, 78: 80},
    "j901_2":   {5: 80, 12: 70, 20: 60, 28: 85, 35: 55, 42: 80, 50: 65, 58: 85, 65: 55, 72: 75, 80: 65},
    "j901_3":   {3: 60, 8: 85, 15: 70, 22: 60, 30: 85, 38: 55, 45: 80, 52: 65, 60: 85, 68: 55, 75: 75},
    "j901_4":   {6: 85, 14: 60, 21: 80, 29: 55, 36: 85, 44: 60, 51: 80, 59: 55, 66: 85, 74: 60, 82: 80},
}

STOCK_GRAVIER_J90 = _compute_stocks(GRAVIER_PAR_TACHE_J90, marge=1.05)


# ===========================================================================
# 4. PARAMÈTRES D'EXTENSION — J120
# ===========================================================================

DEBUT_ETE_J120 = 200
FIN_ETE_J120   = 300

CIMENT_PAR_TACHE_J120 = {
    "j1201_1": {
        3: 40, 8: 35, 15: 50, 22: 30, 30: 45, 38: 35, 45: 50, 52: 30, 60: 40,
        68: 35, 75: 45, 82: 30, 90: 50, 98: 35, 105: 40,
    },
    "j1201_2": {
        4: 45, 10: 40, 18: 35, 25: 50, 32: 30, 40: 45, 48: 35, 55: 50, 62: 30,
        70: 40, 78: 35, 85: 45, 92: 30, 100: 50, 108: 35,
    },
    "j1201_3": {
        5: 50, 12: 35, 20: 45, 28: 30, 35: 50, 42: 35, 50: 45, 58: 30, 65: 50,
        72: 35, 80: 45, 88: 30, 95: 50, 102: 35, 110: 45,
    },
    "j1201_4": {
        2: 35, 9: 50, 16: 30, 24: 45, 31: 35, 39: 50, 46: 30, 54: 45, 61: 35,
        69: 50, 76: 30, 84: 45, 91: 35, 99: 50, 107: 30,
    },
}

STOCK_CIMENT_J120 = _compute_stocks(CIMENT_PAR_TACHE_J120)

TACHES_BETON_J120 = {
    "j1201_1":  [3, 8, 15, 22, 30, 38, 45, 52, 60, 68, 75, 82, 90, 98, 105],
    "j1201_2":  [4, 10, 18, 25, 32, 40, 48, 55, 62, 70, 78, 85, 92, 100, 108],
    "j1201_3":  [5, 12, 20, 28, 35, 42, 50, 58, 65, 72, 80, 88, 95, 102, 110],
    "j1201_4":  [2, 9, 16, 24, 31, 39, 46, 54, 61, 69, 76, 84, 91, 99, 107],
}

ACIER_PAR_TACHE_J120 = {
    "j1201_1": {3: 8, 8: 7, 15: 10, 22: 6, 30: 9, 38: 7, 45: 10, 52: 6, 60: 8, 68: 7, 75: 9, 82: 6, 90: 10, 98: 7, 105: 8},
    "j1201_2": {4: 9, 10: 8, 18: 7, 25: 10, 32: 6, 40: 9, 48: 7, 55: 10, 62: 6, 70: 8, 78: 7, 85: 9, 92: 6, 100: 10, 108: 7},
    "j1201_3": {5: 10, 12: 7, 20: 9, 28: 6, 35: 10, 42: 7, 50: 9, 58: 6, 65: 10, 72: 7, 80: 9, 88: 6, 95: 10, 102: 7, 110: 9},
    "j1201_4": {2: 7, 9: 10, 16: 6, 24: 9, 31: 7, 39: 10, 46: 6, 54: 9, 61: 7, 69: 10, 76: 6, 84: 9, 91: 7, 99: 10, 107: 6},
}

STOCK_ACIER_J120 = _compute_stocks(ACIER_PAR_TACHE_J120, marge=1.05)

GRAVIER_PAR_TACHE_J120 = {
    "j1201_1": {3: 70, 8: 60, 15: 90, 22: 55, 30: 80, 38: 65, 45: 90, 52: 55, 60: 75, 68: 65, 75: 80, 82: 55, 90: 90, 98: 65, 105: 70},
    "j1201_2": {4: 80, 10: 70, 18: 60, 25: 85, 32: 55, 40: 80, 48: 65, 55: 85, 62: 55, 70: 75, 78: 65, 85: 80, 92: 55, 100: 85, 108: 65},
    "j1201_3": {5: 85, 12: 60, 20: 80, 28: 55, 35: 85, 42: 60, 50: 80, 58: 55, 65: 85, 72: 60, 80: 80, 88: 55, 95: 85, 102: 60, 110: 80},
    "j1201_4": {2: 60, 9: 85, 16: 55, 24: 80, 31: 60, 39: 85, 46: 55, 54: 80, 61: 60, 69: 85, 76: 55, 84: 80, 91: 60, 99: 85, 107: 55},
}

STOCK_GRAVIER_J120 = _compute_stocks(GRAVIER_PAR_TACHE_J120, marge=1.05)


# ===========================================================================
# 5. MAPPING NOMS BASEDATA -> CLÉS DICO
# ===========================================================================

NAME_MAPPING = {
    # J30
    "j30_17":   "j301_1",
    "j30_37":   "j3021_1",
    "j30_45":   "j3029_1",
    "j30_61":   "j3045_1",
    "j30_82":   "j3082_1",
    # J60
    "j60_1":    "j601_1",
    "j60_2":    "j601_2",
    "j60_3":    "j601_3",
    "j60_4":    "j601_4",
    # J90
    "j90_1":    "j901_1",
    "j90_2":    "j901_2",
    "j90_3":    "j901_3",
    "j90_4":    "j901_4",
    # J120
    "j1201_1":  "j1201_1",
    "j1201_2":  "j1201_2",
    "j1201_3":  "j1201_3",
    "j1201_4":  "j1201_4",
}


def get_instance_key(basedata_name: str) -> str:
    """Convertit le nom basedata en clé de dictionnaire"""
    clean = basedata_name.lower().replace('.bas', '').replace('.sm', '').strip()
    if clean in NAME_MAPPING:
        return NAME_MAPPING[clean]
    return clean


def get_instance_type(stem: str) -> str:
    """Détermine le type d'instance (J30, J60, J90, J120)"""
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
# 6. FONCTIONS UTILITAIRES
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


def format_list(lst: list) -> str:
    return "[" + ", ".join(str(x) for x in lst) + "]"


def format_2d(matrix: list) -> str:
    rows = " | ".join(", ".join(str(x) for x in row) for row in matrix)
    return "[| " + rows + " |]"


# ===========================================================================
# 7. PARSING D'UN BLOC PSPLIB
# ===========================================================================

def parse_block(content: str) -> dict:
    """Parse un bloc d'instance PSPLIB (format standard)"""

    # Détection du nom d'instance
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
            raise ValueError("Impossible de trouver le nom de l'instance dans le bloc.")

    # Extraction métadonnées
    jobs_match = re.search(r'[Jj]obs.*?[:]\s*(\d+)', content)
    n_jobs = int(jobs_match.group(1)) if jobs_match else 32

    res_match = re.search(r'[Rr]enewable\s*[:=]\s*(\d+)', content)
    n_res = int(res_match.group(1)) if res_match else 4

    # Précédences (format successeurs PSPLIB)
    prec_match = re.search(
        r'PRECEDENCE\s*RELATIONS\s*[:=]?\s*(.*?)\s*REQUESTS',
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
        r'REQUESTS/DURATIONS\s*[:=]?\s*(.*?)\s*RESOURCE\s*AVAIL',
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

    # Reconstruction avec dummies (toutes les tâches 1..n_jobs)
    n_total = n_jobs

    # Durées pour toutes les tâches (1..n_total)
    durations = [durations_raw.get(j, 0) for j in range(1, n_total + 1)]

    # Demandes pour toutes les tâches
    demands = [demands_raw.get(j, [0]*n_res) for j in range(1, n_total + 1)]

    # Précédences en format paires (compatible modèle prof)
    prec_pairs = []
    for job, succs in successors_raw.items():
        for s in succs:
            prec_pairs.append([job, s])
    n_prec = len(prec_pairs)

    # Horizon
    H_match = re.search(r'[Hh]orizon\s*[:=]\s*(\d+)', content)
    H = int(H_match.group(1)) if H_match else (800 if inst_type == 'J120' else 400)

    return {
        'name': name,
        'stem': instance_key,
        'stem_raw': stem,
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
# 8. MÉTRIQUES DE SCALABILITÉ
# ===========================================================================

def compute_metrics(data: dict) -> dict:
    """Calcule les métriques RF, RS, NC, etc."""
    n_total = data['n_total']
    n_res = data['n_res']
    caps = data['caps']
    demands = data['demands']
    durations = data['durations']

    # Tâches réelles (sans dummies)
    real_demands = demands[1:-1] if n_total > 2 else demands
    real_durations = durations[1:-1] if n_total > 2 else durations
    n_real = len(real_demands)

    # RF: Resource Factor
    uses_res = sum(1 for d in real_demands if any(x > 0 for x in d))
    rf = round(uses_res / n_real, 3) if n_real > 0 else 0

    # RS: Resource Strength
    rs_vals = []
    for r in range(n_res):
        col = [demands[i][r] for i in range(n_total)]
        mx = max(col) if col else 1
        if mx > 0:
            rs_vals.append(round(caps[r] / mx, 3))
    rs = round(sum(rs_vals) / len(rs_vals), 3) if rs_vals else 0

    # NC: Network Complexity
    n_prec = data['n_prec']
    max_prec = n_total * (n_total - 1) / 2
    nc = round(n_prec / max_prec, 3) if max_prec > 0 else 0

    total_work = sum(real_durations)
    avg_duration = round(total_work / n_real, 1) if n_real > 0 else 0

    # Utilisation des ressources
    util = {}
    for r in range(n_res):
        total_demand = sum(demands[i][r] * durations[i] for i in range(n_total))
        capacity = caps[r] * data['H']
        util[f"R{r+1}"] = round(total_demand / capacity, 3) if capacity > 0 else 0

    return {
        'rf': rf,
        'rs': rs,
        'nc': nc,
        'total_work': total_work,
        'avg_duration': avg_duration,
        'utilization': util,
        'n_real': n_real,
    }


def analyze_scalability(all_data: list) -> dict:
    """Analyse de scalabilité entre toutes les instances"""
    results = []

    for data in all_data:
        metrics = compute_metrics(data)
        info = {
            'name': data['name'],
            'stem': data['stem'],
            'type': data['inst_type'],
            'n_total': data['n_total'],
            'n_real': metrics['n_real'],
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

    # Regroupement par type
    by_type = {}
    for r in results:
        t = r['type']
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(r)

    # Ratios de scalabilité
    summary = {}
    types = ['J30', 'J60', 'J90', 'J120']
    for t in types:
        if t in by_type:
            insts = by_type[t]
            summary[t] = {
                'count': len(insts),
                'avg_jobs': round(sum(r['n_real'] for r in insts) / len(insts), 1),
                'avg_horizon': round(sum(r['horizon'] for r in insts) / len(insts), 1),
                'avg_work': round(sum(r['total_work'] for r in insts) / len(insts), 1),
                'avg_rf': round(sum(r['rf'] for r in insts) / len(insts), 3),
                'avg_rs': round(sum(r['rs'] for r in insts) / len(insts), 3),
                'avg_nc': round(sum(r['nc'] for r in insts) / len(insts), 3),
            }

    return {'instances': results, 'summary': summary, 'by_type': by_type}


# ===========================================================================
# 9. GÉNÉRATION DZN — Compatible modèle du prof
# ===========================================================================

def to_dzn(data: dict, out_path: str) -> None:
    """Génère un fichier .dzn compatible avec le modèle du prof"""
    stem = data['stem']
    inst_type = data['inst_type']
    n_total = data['n_total']

    # Sélection des paramètres d'extension selon le type
    if inst_type == 'J120':
        debut_ete = DEBUT_ETE_J120
        fin_ete = FIN_ETE_J120
        ciment_dict = CIMENT_PAR_TACHE_J120.get(stem, {})
        acier_dict = ACIER_PAR_TACHE_J120.get(stem, {})
        gravier_dict = GRAVIER_PAR_TACHE_J120.get(stem, {})
        taches_beton = TACHES_BETON_J120.get(stem, [])
        stock_ciment = STOCK_CIMENT_J120.get(stem, 600)
        stock_acier = STOCK_ACIER_J120.get(stem, 120)
        stock_gravier = STOCK_GRAVIER_J120.get(stem, 1200)
    elif inst_type == 'J90':
        debut_ete = DEBUT_ETE_J90
        fin_ete = FIN_ETE_J90
        ciment_dict = CIMENT_PAR_TACHE_J90.get(stem, {})
        acier_dict = ACIER_PAR_TACHE_J90.get(stem, {})
        gravier_dict = GRAVIER_PAR_TACHE_J90.get(stem, {})
        taches_beton = TACHES_BETON_J90.get(stem, [])
        stock_ciment = STOCK_CIMENT_J90.get(stem, 450)
        stock_acier = STOCK_ACIER_J90.get(stem, 90)
        stock_gravier = STOCK_GRAVIER_J90.get(stem, 900)
    elif inst_type == 'J60':
        debut_ete = DEBUT_ETE_J60
        fin_ete = FIN_ETE_J60
        ciment_dict = CIMENT_PAR_TACHE_J60.get(stem, {})
        acier_dict = ACIER_PAR_TACHE_J60.get(stem, {})
        gravier_dict = GRAVIER_PAR_TACHE_J60.get(stem, {})
        taches_beton = TACHES_BETON_J60.get(stem, [])
        stock_ciment = STOCK_CIMENT_J60.get(stem, 300)
        stock_acier = STOCK_ACIER_J60.get(stem, 60)
        stock_gravier = STOCK_GRAVIER_J60.get(stem, 600)
    else:  # J30
        debut_ete = DEBUT_ETE_J30
        fin_ete = FIN_ETE_J30
        ciment_dict = CIMENT_PAR_TACHE_J30.get(stem, {})
        acier_dict = ACIER_PAR_TACHE_J30.get(stem, {})
        gravier_dict = GRAVIER_PAR_TACHE_J30.get(stem, {})
        taches_beton = TACHES_BETON_J30.get(stem, [])
        stock_ciment = STOCK_CIMENT_J30.get(stem, 200)
        stock_acier = STOCK_ACIER_J30.get(stem, 40)
        stock_gravier = STOCK_GRAVIER_J30.get(stem, 400)

    # Vecteurs RNR (1-based, toutes les tâches)
    ciment = [ciment_dict.get(i, 0) for i in range(1, n_total + 1)]
    acier = [acier_dict.get(i, 0) for i in range(1, n_total + 1)]
    gravier = [gravier_dict.get(i, 0) for i in range(1, n_total + 1)]

    # Vérification cohérence
    total_ciment = sum(ciment)
    total_acier = sum(acier)
    total_gravier = sum(gravier)

    if stock_ciment < total_ciment:
        stock_ciment = round(total_ciment * 1.05)
    if stock_acier < total_acier:
        stock_acier = round(total_acier * 1.05)
    if stock_gravier < total_gravier:
        stock_gravier = round(total_gravier * 1.05)

    n_taches_beton = len(taches_beton)

    # Construction du fichier
    lines = [
        f"% =====================================================================",
        f"% Instance : {data['name']}",
        f"% Type : {inst_type} (n_total={n_total} tâches, dont {n_total-2} réelles)",
        f"% Généré par parser_btp_v3.py — Projet P2 RCPSP étendu INSEA",
        f"% Extensions : Climatique + NR (Ciment/Acier/Gravier) + Scalabilité",
        f"% =====================================================================",
        f"",
        f"% --- Paramètres de base ---",
        f"n_total = {n_total};",
        f"H       = {data['H']};",
        f"",
        f"% --- Durées des tâches (jours ouvrés) ---",
        f"% Tâche 1 = SOURCE (dummy), Tâche {n_total} = PUITS (dummy)",
        f"duree = {format_list(data['durations'])};",
        f"",
        f"% --- Précédences (format paires PSPLIB) ---",
        f"n_prec = {data['n_prec']};",
        f"prec = {format_2d(data['prec_pairs'])};",
        f"",
        f"% --- Ressources renouvelables ---",
        f"n_RR = {data['n_res']};",
        f"capacite_RR = {format_list(data['caps'])};",
        f"besoin_RR = {format_2d(data['demands'])};",
        f"",
        f"% --- Ressources non-renouvelables ---",
        f"% RNR1 = Ciment (tonnes), RNR2 = Acier (tonnes), RNR3 = Gravier (m³)",
        f"n_RNR = 3;",
        f"budget_RNR = [{stock_ciment}, {stock_acier}, {stock_gravier}];",
        f"besoin_RNR = [| {', '.join(str(ciment[i]) for i in range(n_total))} |",
        f"             | {', '.join(str(acier[i]) for i in range(n_total))} |",
        f"             | {', '.join(str(gravier[i]) for i in range(n_total))} |];",
        f"",
        f"% --- Contraintes climatiques ---",
        f"debut_ete = {debut_ete};",
        f"fin_ete   = {fin_ete};",
        f"n_TACHES_BETON = {n_taches_beton};",
        f"TACHES_BETON = {{{', '.join(str(t) for t in taches_beton)}}};",
        f"",
        f"% =====================================================================",
        f"% Vérification RNR : Ciment={total_ciment}/{stock_ciment}, Acier={total_acier}/{stock_acier}, Gravier={total_gravier}/{stock_gravier}",
        f"% Tâches béton : {n_taches_beton} tâches identifiées",
        f"% =====================================================================",
    ]

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"  [OK] {out_path} ({inst_type}, n_total={n_total}, H={data['H']}, "
          f"béton={n_taches_beton}, RNR=3)")


# ===========================================================================
# 10. AFFICHAGE RÉSUMÉ + TABLEAU SCALABILITÉ
# ===========================================================================

def print_summary(data: dict) -> None:
    metrics = compute_metrics(data)
    print(f"\n{'='*70}")
    print(f"Instance : {data['name']} ({data['inst_type']})")
    print(f"  Tâches totales     : {data['n_total']} (dont {metrics['n_real']} réelles)")
    print(f"  Horizon H          : {data['H']}")
    print(f"  Ressources RR      : {data['n_res']}")
    print(f"  Capacités RR       : {data['caps']}")
    print(f"  RF (couverture)    : {metrics['rf']}")
    print(f"  RS (pression)      : {metrics['rs']}")
    print(f"  NC (précédences)   : {metrics['nc']}")
    print(f"  Travail total      : {metrics['total_work']} jours")
    print(f"  Durée moyenne      : {metrics['avg_duration']} jours")


def print_scalability_table(all_data: list):
    analysis = analyze_scalability(all_data)

    print(f"\n{'='*80}")
    print("ANALYSE DE SCALABILITÉ")
    print(f"{'='*80}")

    print(f"\n{'Instance':<15} {'Type':>6} {'Total':>6} {'Réelles':>7} {'Horizon':>8} "
          f"{'Work':>8} {'RF':>6} {'RS':>6} {'NC':>6}")
    print("-" * 80)
    for info in analysis['instances']:
        print(f"{info['name']:<15} {info['type']:>6} {info['n_total']:>6} {info['n_real']:>7} "
              f"{info['horizon']:>8} {info['total_work']:>8} {info['rf']:>6.3f} "
              f"{info['rs']:>6.3f} {info['nc']:>6.3f}")

    if analysis['summary']:
        print(f"\n{'='*80}")
        print("RÉSUMÉ PAR TYPE D'INSTANCE")
        print(f"{'='*80}")
        for t in ['J30', 'J60', 'J90', 'J120']:
            if t in analysis['summary']:
                s = analysis['summary'][t]
                print(f"\n  {t} ({s['count']} instances):")
                print(f"    Tâches réelles moy. : {s['avg_jobs']:.1f}")
                print(f"    Horizon moyen       : {s['avg_horizon']:.1f}")
                print(f"    Travail total moy.  : {s['avg_work']:.1f}")
                print(f"    RF moyen            : {s['avg_rf']:.3f}")
                print(f"    RS moyen            : {s['avg_rs']:.3f}")
                print(f"    NC moyen            : {s['avg_nc']:.3f}")

    return analysis


# ===========================================================================
# 11. MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Parser PSPLIB J30/J60/J90/J120 -> .dzn MiniZinc + Scalabilité"
    )
    parser.add_argument("--input", "-i", default="instancesdebtp.docx",
                        help="Chemin vers le fichier source (.docx ou .txt)")
    parser.add_argument("--outdir", "-o", default="dzn_output",
                        help="Dossier de sortie pour les fichiers .dzn")
    parser.add_argument("--verify", "-v", action="store_true",
                        help="Afficher le résumé uniquement (pas de .dzn)")
    parser.add_argument("--scalabilite", "-s", action="store_true",
                        help="Générer le rapport de scalabilité JSON")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Mode debug")
    args = parser.parse_args()

    print(f"Chargement de : {args.input}")
    try:
        raw = load_raw_text(args.input)
    except Exception as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        bas_names = re.findall(r'file with basedata\s*:\s*(\S+)', raw, re.IGNORECASE)
        print(f"\n[DEBUG] Basedata trouvés ({len(bas_names)}): {bas_names}\n")

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
        has_jobs = re.search(r'jobs.*?:\s*\d+', b) is not None

        if has_prec and has_req and has_res and has_jobs:
            valid_blocks.append(b)

    blocks = valid_blocks

    if not blocks:
        print("ERREUR : Aucun bloc valide trouvé.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(blocks)} instance(s) détectée(s)\n")

    if not args.verify:
        os.makedirs(args.outdir, exist_ok=True)

    all_data = []
    counts = {'J30': 0, 'J60': 0, 'J90': 0, 'J120': 0}

    for block in blocks:
        try:
            data = parse_block(block)
            all_data.append(data)

            print_summary(data)

            if not args.verify:
                dzn_path = os.path.join(args.outdir, f"{data['stem']}.dzn")
                to_dzn(data, dzn_path)
                counts[data['inst_type']] = counts.get(data['inst_type'], 0) + 1

        except Exception as e:
            print(f"ERREUR lors du parsing : {e}", file=sys.stderr)

    # Analyse de scalabilité
    if len(all_data) > 1:
        analysis = print_scalability_table(all_data)

        if args.scalabilite:
            scal_file = os.path.join(args.outdir, 'scalabilite_analysis.json')
            with open(scal_file, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
            print(f"\n[OK] Rapport de scalabilité : {scal_file}")

    if not args.verify:
        print(f"\n{'='*60}")
        print(f"Fichiers .dzn écrits dans : {args.outdir}/")
        for t in ['J30', 'J60', 'J90', 'J120']:
            if counts.get(t, 0) > 0:
                print(f"  {t} : {counts[t]} instances")
        print(f"  Total : {sum(counts.values())} instances")


if __name__ == "__main__":
    main()