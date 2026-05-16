#!/usr/bin/env python3
"""
Parser PSPLIB Unifié — J30 + CASA-LYC-14
==========================================
Génère deux types de fichiers .dzn :
  - Type STANDARD  : pour les instances J30 (PSPLIB classique)
  - Type BTP-ENRICH: pour l'instance CASA-LYC-14 (ressources non-renouvelables,
                     contraintes climatiques, tâches béton)

Usage:
    python3 parser_unified.py --input instancesdebtp.docx --outdir dzn_output
"""

import re
import os
import sys
import argparse

# ===========================================================================
# 1. MAPPING NOMS
# ===========================================================================

NAME_MAPPING = {
    "j30_17":  "j301_1",  "j30_37":  "j3021_1", "j30_45":  "j3029_1",
    "j30_61":  "j3045_1", "j30_82":  "j3082_1",
    "j60_1":   "j601_1",  "j60_2":   "j601_2",  "j60_3":   "j601_3",
    "j60_4":   "j601_4",  "j60_17":  "j601_1",
    "j90_1":   "j901_1",  "j90_2":   "j901_2",  "j90_3":   "j901_3",
    "j90_4":   "j901_4",  "j901_":   "j901_1",
    "j1201_1": "j1201_1", "j1201_2": "j1201_2",
    "j1201_3": "j1201_3", "j1201_4": "j1201_4",
}

def get_instance_key(basedata_name: str) -> str:
    clean = basedata_name.lower().replace('.bas', '').replace('.sm', '').strip()
    return NAME_MAPPING.get(clean, clean)

def get_instance_type(stem: str) -> str:
    s = stem.lower()
    if 'casa' in s or 'lyc' in s:  return 'BTP-ENRICH'
    if s.startswith('j120'):        return 'J120'
    if s.startswith('j90'):         return 'J90'
    if s.startswith('j60'):         return 'J60'
    if s.startswith('j30'):         return 'J30'
    return 'UNKNOWN'


# ===========================================================================
# 2. EXTRACTION TEXTE
# ===========================================================================

def load_raw_text(path: str) -> str:
    if path.endswith(".docx"):
        try:
            import docx as _docx
        except ImportError:
            raise RuntimeError("Installez python-docx : pip3 install python-docx")
        doc = _docx.Document(path)
        lines = []
        for table in doc.tables:
            for row in table.rows:
                lines.append("\t".join(cell.text for cell in row.cells))
        for para in doc.paragraphs:
            lines.append(para.text)
        text = "\n".join(lines)
    else:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    return re.sub(r'\n{3,}', '\n\n', text)


# ===========================================================================
# 3. PARSING COMMUN (précédences + durées/demandes renouvelables + caps)
# ===========================================================================

def parse_precedences(content: str) -> dict:
    """Retourne {job: [successeurs]} depuis la section PRECEDENCE RELATIONS."""
    prec_match = re.search(
        r'PRECEDENCE\s*RELATIONS\s*[:=?]?\s*(.*?)\s*REQUESTS',
        content, re.DOTALL | re.IGNORECASE
    )
    successors = {}
    if not prec_match:
        return successors
    for line in prec_match.group(1).splitlines():
        line = line.strip()
        if not line or re.match(r'(jobnr|job|pronr)', line, re.IGNORECASE):
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                job    = int(parts[0])
                n_succ = int(parts[2])
                succs  = [int(x) for x in parts[3:3 + n_succ]]
                successors[job] = succs
            except (ValueError, IndexError):
                continue
    return successors


def parse_renewable_requests(content: str, n_res: int) -> tuple:
    """
    Retourne (durations_raw, demands_raw) depuis REQUESTS/DURATIONS (RENEWABLE).
    Gère indifféremment :
      - "REQUESTS/DURATIONS :"
      - "REQUESTS/DURATIONS (RENEWABLE RESOURCES) :"
    """
    # Cherche la section RENEWABLE uniquement (s'arrête avant NONRENEWABLE)
    req_match = re.search(
        r'REQUESTS/DURATIONS(?:\s*\([^)]*RENEWABLE\s*RESOURCES[^)]*\))?\s*[:=?]?\s*\n'
        r'(.*?)'
        r'\s*(?:REQUESTS/DURATIONS\s*\(NONRENEWABLE|RESOURCEAVAIL|RESOURCE\s*AVAIL)',
        content, re.DOTALL | re.IGNORECASE
    )
    if not req_match:
        # Fallback sans parenthèse
        req_match = re.search(
            r'REQUESTS/DURATIONS[^\n]*\n(.*?)'
            r'\s*(?:RESOURCE\s*AVAIL|RESOURCEAVAIL)',
            content, re.DOTALL | re.IGNORECASE
        )

    durations_raw, demands_raw = {}, {}
    if not req_match:
        return durations_raw, demands_raw

    for line in req_match.group(1).splitlines():
        line = line.strip()
        if not line or re.match(r'(jobnr|job|-)', line, re.IGNORECASE):
            continue
        parts = line.split()
        if len(parts) >= 3 + n_res:
            try:
                job      = int(parts[0])
                duration = int(parts[2])
                demands  = [int(parts[3 + r]) for r in range(n_res)]
                durations_raw[job] = duration
                demands_raw[job]   = demands
            except (ValueError, IndexError):
                continue
    return durations_raw, demands_raw


def parse_renewable_caps(content: str, n_res: int) -> list:
    """
    Retourne les capacités renouvelables.
    Gère "RESOURCE AVAILABILITIES" et "RESOURCEAVAILABILITIES (RENEWABLE)".
    """
    cap_match = re.search(
        r'RESOURCE\s*AVAILABILITIES(?:\s*\([^)]*RENEWABLE[^)]*\))?\s*[:=?]?\s*\n'
        r'(.*?)'
        r'(?:RESOURCE\s*AVAIL.*?NONRENEWABLE|CLIMATIC|\*{5}|\Z)',
        content, re.DOTALL | re.IGNORECASE
    )
    if not cap_match:
        return [10] * n_res

    for line in cap_match.group(1).splitlines():
        line = line.strip()
        if not line or re.match(r'^[RN*]', line):
            continue
        parts = line.split()
        if len(parts) >= n_res:
            try:
                return [int(parts[r]) for r in range(n_res)]
            except ValueError:
                continue
    return [10] * n_res


# ===========================================================================
# 4. PARSING SPÉCIFIQUE CASA-LYC-14 (ressources non-renouvelables + extras)
# ===========================================================================

def parse_nonrenewable_requests(content: str, n_nr: int) -> dict:
    """Retourne {job: [demandes_NR]} depuis REQUESTS/DURATIONS (NONRENEWABLE RESOURCES)."""
    nr_match = re.search(
        r'REQUESTS/DURATIONS\s*\([^)]*NONRENEWABLE[^)]*\)[^\n]*\n(.*?)'
        r'\s*(?:RESOURCEAVAIL|RESOURCE\s*AVAIL)',
        content, re.DOTALL | re.IGNORECASE
    )
    nr_demands = {}
    if not nr_match:
        return nr_demands
    for line in nr_match.group(1).splitlines():
        line = line.strip()
        if not line or re.match(r'(jobnr|job|-)', line, re.IGNORECASE):
            continue
        parts = line.split()
        if len(parts) >= 3 + n_nr:
            try:
                job = int(parts[0])
                nr_demands[job] = [int(parts[3 + r]) for r in range(n_nr)]
            except (ValueError, IndexError):
                continue
    return nr_demands


def parse_nonrenewable_caps(content: str, n_nr: int) -> list:
    """Retourne les capacités non-renouvelables."""
    cap_match = re.search(
        r'RESOURCE\s*AVAILABILITIES\s*\([^)]*NONRENEWABLE[^)]*\)\s*[:=?]?\s*\n(.*?)'
        r'(?:CLIMATIC|\*{5}|\Z)',
        content, re.DOTALL | re.IGNORECASE
    )
    if not cap_match:
        return [9999] * n_nr
    for line in cap_match.group(1).splitlines():
        line = line.strip()
        if not line or re.match(r'^[RN*]', line):
            continue
        parts = line.split()
        if len(parts) >= n_nr:
            try:
                return [int(parts[r]) for r in range(n_nr)]
            except ValueError:
                continue
    return [9999] * n_nr


def parse_climatic(content: str) -> dict:
    """Extrait les contraintes climatiques CASA-LYC-14."""
    result = {}
    m = re.search(r'Big-M\s*[^:]*:\s*(\d+)', content, re.IGNORECASE)
    result['big_m'] = int(m.group(1)) if m else 280

    m = re.search(r'Summer window start[^:]*:\s*(\d+)', content, re.IGNORECASE)
    result['summer_start'] = int(m.group(1)) if m else 108

    m = re.search(r'Summer window end[^:]*:\s*(\d+)', content, re.IGNORECASE)
    result['summer_end'] = int(m.group(1)) if m else 192

    m = re.search(r'Working days only\s*:\s*(YES|NO)', content, re.IGNORECASE)
    result['working_days_only'] = (m.group(1).upper() == 'YES') if m else True

    return result


def parse_concrete_tasks(content: str) -> list:
    """Extrait le sous-ensemble de tâches béton."""
    m = re.search(r'Task subset\s*:\s*\{([^}]+)\}', content, re.IGNORECASE)
    if m:
        try:
            return [int(x.strip()) for x in m.group(1).split(',')]
        except ValueError:
            pass
    return []


# ===========================================================================
# 5. PARSEUR PRINCIPAL DE BLOC
# ===========================================================================

def parse_block(content: str) -> dict:
    # --- Nom & type ---
    bas_match = re.search(r'file with basedata\s*:\s*([^\n]+)', content, re.IGNORECASE)
    if bas_match:
        raw_name = bas_match.group(1).strip()
        stem_raw = re.sub(r'\.(bas|sm)$', '', raw_name.split()[0], flags=re.IGNORECASE)
        stem     = stem_raw.lower()
        key      = get_instance_key(stem) if get_instance_key(stem) != stem else stem_raw
        inst_type = get_instance_type(stem_raw)
        name = key + ".sm"
    else:
        raise ValueError("Impossible de trouver le nom de l'instance.")

    # --- Paramètres de base ---
    n_jobs = int(re.search(r'[Jj]obs.*?[:=]\s*(\d+)', content).group(1)) if \
             re.search(r'[Jj]obs.*?[:=]\s*(\d+)', content) else 32

    n_r_match = re.search(r'[Rr]enewable\s*[:=]\s*(\d+)', content)
    n_res = int(n_r_match.group(1)) if n_r_match else 4

    n_nr_match = re.search(r'[Nn]onrenewable\s*[:=]\s*(\d+)', content)
    n_nr = int(n_nr_match.group(1)) if n_nr_match else 0

    H_match = re.search(r'[Hh]orizon\s*[:=]\s*(\d+)', content)
    H = int(H_match.group(1)) if H_match else (800 if inst_type == 'J120' else 400)

    # --- Précédences ---
    successors_raw = parse_precedences(content)
    prec_pairs = [[j, s] for j, succs in successors_raw.items() for s in succs]

    # --- Durées & demandes renouvelables ---
    durations_raw, demands_raw = parse_renewable_requests(content, n_res)
    caps = parse_renewable_caps(content, n_res)

    n = n_jobs
    durations = [durations_raw.get(j, 0) for j in range(1, n + 1)]
    demands   = [demands_raw.get(j, [0] * n_res) for j in range(1, n + 1)]

    result = {
        'name':       name,
        'stem':       key,
        'inst_type':  inst_type,
        'n_total':    n,
        'H':          H,
        'n_res':      n_res,
        'n_nr':       n_nr,
        'caps':       caps,
        'durations':  durations,
        'demands':    demands,
        'prec_pairs': prec_pairs,
        'n_prec':     len(prec_pairs),
    }

    # --- Données enrichies CASA-LYC-14 ---
    if inst_type == 'BTP-ENRICH' and n_nr > 0:
        nr_demands_raw  = parse_nonrenewable_requests(content, n_nr)
        nr_caps         = parse_nonrenewable_caps(content, n_nr)
        nr_demands      = [nr_demands_raw.get(j, [0] * n_nr) for j in range(1, n + 1)]
        climatic        = parse_climatic(content)
        concrete_tasks  = parse_concrete_tasks(content)

        result.update({
            'nr_caps':       nr_caps,
            'nr_demands':    nr_demands,
            'climatic':      climatic,
            'concrete_tasks': concrete_tasks,
        })

    return result


# ===========================================================================
# 6. GÉNÉRATION DZN STANDARD (J30 / J60 / J90 / J120)
# ===========================================================================

def to_dzn_standard(data: dict, out_path: str) -> None:
    n, n_res, H = data['n_total'], data['n_res'], data['H']
    flat_demands = [d for row in data['demands'] for d in row]
    prec_flat = [
        1 if any(p[0] == i and p[1] == j for p in data['prec_pairs']) else 0
        for i in range(1, n + 1) for j in range(1, n + 1)
    ]

    lines = [
        f"% Instance PSPLIB standard : {data['name']}",
        f"% Type : {data['inst_type']} ({n} tâches dont {n-2} réelles)",
        f"% Modèle associé : model_standard.mzn",
        f"",
        f"n            = {n};",
        f"n_resources  = {n_res};",
        f"horizon      = {H};",
        f"",
        f"duration     = {data['durations']};",
        f"resource_avail = {data['caps']};",
        f"",
        f"req = array2d(1..n, 1..n_resources, [",
        f"    " + ", ".join(str(x) for x in flat_demands),
        f"]);",
        f"",
        f"precedence = array2d(1..n, 1..n, [",
        f"    " + ", ".join(str(x) for x in prec_flat),
        f"]);",
        f"",
        f"n_prec = {data['n_prec']};",
        f"",
        f"% === FIN ===",
    ]
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"  [STANDARD] {out_path}  (n={n}, H={H}, prec={data['n_prec']})")


# ===========================================================================
# 7. GÉNÉRATION DZN ENRICHI (CASA-LYC-14)
# ===========================================================================

def to_dzn_btp_enrich(data: dict, out_path: str) -> None:
    n, n_res, n_nr, H = data['n_total'], data['n_res'], data['n_nr'], data['H']
    cl  = data['climatic']
    ct  = data['concrete_tasks']

    flat_r  = [d for row in data['demands']    for d in row]
    flat_nr = [d for row in data['nr_demands'] for d in row]
    prec_flat = [
        1 if any(p[0] == i and p[1] == j for p in data['prec_pairs']) else 0
        for i in range(1, n + 1) for j in range(1, n + 1)
    ]

    # Masque binaire béton
    is_concrete = [1 if j in ct else 0 for j in range(1, n + 1)]

    lines = [
        f"% Instance BTP enrichie : {data['name']}",
        f"% Type : {data['inst_type']} ({n} tâches dont {n-2} réelles)",
        f"% Modèle associé : model_btp_enrich.mzn",
        f"",
        f"% ── Dimensions ──────────────────────────────────────",
        f"n              = {n};",
        f"n_resources    = {n_res};    % ressources renouvelables",
        f"n_nr_resources = {n_nr};    % ressources non-renouvelables",
        f"horizon        = {H};",
        f"",
        f"% ── Durées ───────────────────────────────────────────",
        f"duration       = {data['durations']};",
        f"",
        f"% ── Ressources renouvelables ─────────────────────────",
        f"resource_avail = {data['caps']};",
        f"req = array2d(1..n, 1..n_resources, [",
        f"    " + ", ".join(str(x) for x in flat_r),
        f"]);",
        f"",
        f"% ── Ressources non-renouvelables ─────────────────────",
        f"nr_resource_avail = {data['nr_caps']};",
        f"nr_req = array2d(1..n, 1..n_nr_resources, [",
        f"    " + ", ".join(str(x) for x in flat_nr),
        f"]);",
        f"",
        f"% ── Précédences ──────────────────────────────────────",
        f"precedence = array2d(1..n, 1..n, [",
        f"    " + ", ".join(str(x) for x in prec_flat),
        f"]);",
        f"n_prec = {data['n_prec']};",
        f"",
        f"% ── Contraintes climatiques (fenêtre estivale) ───────",
        f"% Tâches de bétonnage interdites du jour {cl['summer_start']} au jour {cl['summer_end']}",
        f"summer_start = {cl['summer_start']};   % 1er juin",
        f"summer_end   = {cl['summer_end']};   % 30 septembre",
        f"big_M        = {cl['big_m']};",
        f"working_days_only = {'true' if cl['working_days_only'] else 'false'};",
        f"",
        f"% ── Tâches de bétonnage ──────────────────────────────",
        f"% Sous-ensemble : {ct}",
        f"n_concrete_tasks = {len(ct)};",
        f"concrete_tasks   = {ct};",
        f"is_concrete      = {is_concrete};   % masque binaire",
        f"",
        f"% === FIN ===",
    ]
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"  [BTP-ENRICH] {out_path}  (n={n}, H={H}, béton={ct})")


# ===========================================================================
# 8. MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Parser PSPLIB unifié → .dzn")
    parser.add_argument("--input",  "-i", default="instancesdebtp.docx")
    parser.add_argument("--outdir", "-o", default="dzn_output")
    args = parser.parse_args()

    print(f"Chargement : {args.input}")
    raw = load_raw_text(args.input)

    all_blocks = re.split(
        r'(?=(?:\*{5,}\s*file with basedata\s*:\s*\S+|file with basedata\s*:\s*\S+|j\d+_\d+\.sm))',
        raw, flags=re.IGNORECASE
    )

    valid_blocks = [
        b.strip() for b in all_blocks
        if b.strip()
        and 'PRECEDENCE' in b
        and 'REQUESTS'   in b
        and 'RESOURCE'   in b
        and re.search(r'jobs.*?[:=]\s*\d+', b, re.IGNORECASE)
    ]

    if not valid_blocks:
        print("ERREUR : Aucun bloc valide trouvé.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(valid_blocks)} instance(s) détectée(s)\n")
    os.makedirs(args.outdir, exist_ok=True)

    for block in valid_blocks:
        try:
            data     = parse_block(block)
            dzn_path = os.path.join(args.outdir, f"{data['stem']}.dzn")
            if data['inst_type'] == 'BTP-ENRICH':
                to_dzn_btp_enrich(data, dzn_path)
            else:
                to_dzn_standard(data, dzn_path)
        except Exception as e:
            print(f"  ERREUR sur un bloc : {e}", file=sys.stderr)

    print(f"\nFichiers .dzn écrits dans : {args.outdir}/")


if __name__ == "__main__":
    main()