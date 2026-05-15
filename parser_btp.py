"""
Parser PSPLIB — Projet P2 RCPSP étendu (CP-INSEA-SDRO-2A)
=============================================================
Lit le fichier instancesdebtp.docx (ou un .txt extrait),
parse les 5 instances j301_1, j3021_1, j3029_1, j3045_1, j3082_1,
et génère les fichiers .dzn prêts pour MiniZinc avec les 3 extensions :
  A. Ressources renouvelables (cumulative)
  B. Fenêtres climatiques (debut_ete / fin_ete)
  C. Ressource non-renouvelable (stock ciment)
  D. Partage d'équipements lourds (Extension C du sujet)
  python parser_btp.py --input instancesdebtp.docx
"""

import re
import os
import argparse
import sys


# ===========================================================================
# 1. PARAMÈTRES D'EXTENSION
# ===========================================================================

DEBUT_ETE = 80
FIN_ETE   = 140

STOCK_CIMENT = {
    "j301_1":   200,
    "j3021_1":  250,
    "j3029_1":  300,
    "j3045_1":  280,
    "j3082_1":  160,
}

CIMENT_PAR_TACHE = {
    "j301_1":   {1: 40, 2: 35, 5: 50, 8: 30, 11: 45},
    "j3021_1":  {0: 30, 3: 40, 6: 55, 10: 35, 14: 40},
    "j3029_1":  {1: 50, 4: 40, 7: 30, 12: 45, 18: 35},
    "j3045_1":  {0: 40, 3: 50, 6: 35, 9: 40, 15: 30},
    "j3082_1":  {2: 35, 3: 18, 4: 22, 5: 25, 6: 22, 7: 25, 8: 28},
}

TACHES_BETON = {
    "j301_1":   [2, 3, 6, 9, 12],
    "j3021_1":  [1, 4, 7, 11, 15],
    "j3029_1":  [2, 5, 8, 13, 19],
    "j3045_1":  [1, 4, 7, 10, 16],
    "j3082_1":  [4, 5, 6, 7, 8, 9, 10],
}

# ===========================================================================
# EXTENSION C — ÉQUIPEMENTS LOURDS PARTAGÉS
# ===========================================================================

# Nombre de types d'équipements lourds (ex: grues, bétonnières)
N_EQUIPEMENTS = {
    "j301_1":   2,   # 2 grues, 1 bétonnière
    "j3021_1":  2,
    "j3029_1":  2,
    "j3045_1":  2,
    "j3082_1":  2,
}

# Capacité de chaque équipement lourd (partagé entre chantiers)
CAPACITE_EQUIPEMENT = {
    "j301_1":   [2, 1],   # 2 grues, 1 bétonnière
    "j3021_1":  [2, 1],
    "j3029_1":  [2, 1],
    "j3045_1":  [2, 1],
    "j3082_1":  [1, 1],   # instance plus petite
}

# Besoins en équipements lourds par tâche (index 0-based)
# e=0 : grue, e=1 : bétonnière
# Les tâches lourdes (levage, coulée) nécessitent une grue
# Les tâches béton nécessitent aussi une bétonnière
BESOIN_EQUIPEMENT = {
    "j301_1": {
        1:  [1, 1],   # T2 : grue + bétonnière (coulée béton)
        2:  [1, 1],   # T3 : grue + bétonnière
        5:  [1, 1],   # T6 : grue + bétonnière
        8:  [1, 1],   # T9 : grue + bétonnière
        11: [1, 1],   # T12 : grue + bétonnière
        3:  [1, 0],   # T4 : grue seule
        6:  [1, 0],   # T7 : grue seule
        9:  [1, 0],   # T10 : grue seule
        12: [1, 0],   # T13 : grue seule
    },
    "j3021_1": {
        0:  [1, 1],   # T1 : grue + bétonnière
        3:  [1, 1],   # T4 : grue + bétonnière
        6:  [1, 1],   # T7 : grue + bétonnière
        10: [1, 1],   # T11 : grue + bétonnière
        14: [1, 1],   # T15 : grue + bétonnière
        1:  [1, 0],   # T2 : grue seule
        4:  [1, 0],   # T5 : grue seule
        7:  [1, 0],   # T8 : grue seule
        11: [1, 0],   # T12 : grue seule
    },
    "j3029_1": {
        1:  [1, 1],   # T2 : grue + bétonnière
        4:  [1, 1],   # T5 : grue + bétonnière
        7:  [1, 1],   # T8 : grue + bétonnière
        12: [1, 1],   # T13 : grue + bétonnière
        18: [1, 1],   # T19 : grue + bétonnière
        2:  [1, 0],   # T3 : grue seule
        5:  [1, 0],   # T6 : grue seule
        8:  [1, 0],   # T9 : grue seule
        13: [1, 0],   # T14 : grue seule
    },
    "j3045_1": {
        0:  [1, 1],   # T1 : grue + bétonnière
        3:  [1, 1],   # T4 : grue + bétonnière
        6:  [1, 1],   # T7 : grue + bétonnière
        9:  [1, 1],   # T10 : grue + bétonnière
        15: [1, 1],   # T16 : grue + bétonnière
        1:  [1, 0],   # T2 : grue seule
        4:  [1, 0],   # T5 : grue seule
        7:  [1, 0],   # T8 : grue seule
        10: [1, 0],   # T11 : grue seule
    },
    "j3082_1": {
        2:  [1, 1],   # T3 : grue + bétonnière
        3:  [1, 1],   # T4 : grue + bétonnière
        4:  [1, 1],   # T5 : grue + bétonnière
        5:  [1, 1],   # T6 : grue + bétonnière
        6:  [1, 1],   # T7 : grue + bétonnière
        7:  [1, 1],   # T8 : grue + bétonnière
        8:  [1, 1],   # T9 : grue + bétonnière
        9:  [1, 0],   # T10 : grue seule
        10: [1, 0],   # T11 : grue seule
    },
}


# ===========================================================================
# 2. EXTRACTION DU TEXTE
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
    name_match = re.search(r'(j30\d+_\d+\.sm)', content)
    if not name_match:
        raise ValueError("Impossible de trouver le nom de l'instance dans le bloc.")
    name = name_match.group(1)

    H      = int(re.search(r'horizon\s*:\s*(\d+)', content).group(1))
    n_jobs = int(re.search(r'jobs.*?:\s*(\d+)', content).group(1))
    n_real = n_jobs - 2
    n_res  = int(re.search(r'renewable\s*:\s*(\d+)', content).group(1))

    # Précédences
    prec_sec = re.search(r'PRECEDENCE RELATIONS:(.*?)REQUESTS', content, re.DOTALL).group(1)
    successors_raw = {}
    for line in prec_sec.strip().split('\n'):
        line = line.strip()
        if not line or line.lower().startswith('job') or line.lower().startswith('jobnr'):
            continue
        parts = line.split()
        if len(parts) >= 3:
            job    = int(parts[0])
            n_succ = int(parts[2])
            succs  = [int(x) for x in parts[3:3 + n_succ]]
            successors_raw[job] = succs

    # Durées et demandes
    req_sec = re.search(r'REQUESTS/DURATIONS:(.*?)RESOURCEAVAIL', content, re.DOTALL).group(1)
    durations_raw = {}
    demands_raw   = {}
    for line in req_sec.strip().split('\n'):
        line = line.strip()
        if not line or line.lower().startswith('job') or line.startswith('-'):
            continue
        parts = line.split()
        if len(parts) >= 3 + n_res:
            job = int(parts[0])
            durations_raw[job] = int(parts[2])
            demands_raw[job]   = [int(parts[3 + r]) for r in range(n_res)]

    # Capacités
    cap_sec = re.search(r'RESOURCEAVAILABILITIES:(.*?)(?:\*{5}|\Z)', content, re.DOTALL).group(1)
    cap_lines = [l.strip() for l in cap_sec.strip().split('\n')
                 if l.strip() and not l.strip().startswith('R') and not l.strip().startswith('*')]
    caps = list(map(int, cap_lines[0].split()))

    # Réorganisation 0-based
    real_jobs = list(range(2, n_jobs))
    job_map   = {j: i for i, j in enumerate(real_jobs)}

    durations = [durations_raw[j] for j in real_jobs]
    demands   = [demands_raw[j]   for j in real_jobs]

    prec_matrix = [[0] * n_real for _ in range(n_real)]
    for job, succs in successors_raw.items():
        if job in job_map:
            for s in succs:
                if s in job_map:
                    prec_matrix[job_map[job]][job_map[s]] = 1

    return {
        'name':        name,
        'stem':        re.sub(r'\.sm$', '', name),
        'n':           n_real,
        'H':           H,
        'n_res':       n_res,
        'caps':        caps,
        'durations':   durations,
        'demands':     demands,
        'prec_matrix': prec_matrix,
    }


# ===========================================================================
# 4. GÉNÉRATION DU FICHIER .DZN
# ===========================================================================

def format_list(lst: list) -> str:
    return "[" + ", ".join(str(x) for x in lst) + "]"


def format_2d(matrix: list) -> str:
    rows = " | ".join(", ".join(str(x) for x in row) for row in matrix)
    return "[| " + rows + " |]"


def to_dzn(data: dict, out_path: str,
           debut_ete: int, fin_ete: int,
           stock_ciment: int,
           ciment_par_tache: dict,
           taches_beton: list,
           n_equipements: int,
           capacite_equipement: list,
           besoin_equipement: dict) -> None:
    
    n = data['n']
    stem = data['stem']

    # Consommation ciment
    ciment = [0] * n
    for idx, qty in ciment_par_tache.items():
        if 0 <= idx < n:
            ciment[idx] = qty

    # Besoins équipements (matrice n × n_equipements)
    besoin_eq = [[0] * n_equipements for _ in range(n)]
    for idx, needs in besoin_equipement.items():
        if 0 <= idx < n:
            for e in range(min(len(needs), n_equipements)):
                besoin_eq[idx][e] = needs[e]

    lines = [
        f"% Instance : {data['name']}",
        f"% Générée par parser_btp.py — Projet P2 RCPSP étendu INSEA",
        f"% Extensions : Climatique + NR + Équipements lourds",
        f"",
        f"% --- Paramètres de base ---",
        f"n     = {n};",
        f"H     = {data['H']};",
        f"n_res = {data['n_res']};",
        f"",
        f"% --- Durées des tâches (jours) ---",
        f"duree = {format_list(data['durations'])};",
        f"",
        f"% --- Capacités ressources renouvelables standard ---",
        f"capacite = {format_list(data['caps'])};",
        f"",
        f"% --- Demandes en ressources renouvelables [tâche, ressource] ---",
        f"besoin = {format_2d(data['demands'])};",
        f"",
        f"% --- Matrice de précédence [i,j]=1 si i doit finir avant j ---",
        f"prec = {format_2d(data['prec_matrix'])};",
        f"",
        f"% --- Extension A : Fenêtre climatique ---",
        f"debut_ete = {debut_ete};",
        f"fin_ete   = {fin_ete};",
        f"",
        f"% --- Extension B : Tâches béton ---",
        f"TACHES_BETON = {{{', '.join(str(t) for t in taches_beton)}}};",
        f"",
        f"% --- Extension C : Ressource non-renouvelable (ciment) ---",
        f"stock_NR = {stock_ciment};",
        f"ciment   = {format_list(ciment)};",
        f"",
        f"% --- Extension D : Équipements lourds partagés ---",
        f"n_equipements = {n_equipements};",
        f"capacite_equipement = {format_list(capacite_equipement)};",
        f"besoin_equipement = {format_2d(besoin_eq)};",
    ]

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"  [OK] {out_path} écrit ({n} tâches, H={data['H']}, "
          f"équipements={n_equipements}, béton={taches_beton})")


# ===========================================================================
# 5. RÉSUMÉ
# ===========================================================================

def print_summary(data: dict) -> None:
    stem = data['stem']
    n    = data['n']
    print(f"\n{'='*60}")
    print(f"Instance : {data['name']}")
    print(f"  Tâches réelles     : {n}")
    print(f"  Horizon H          : {data['H']}")
    print(f"  Ressources         : {data['n_res']}")
    print(f"  Capacités          : {data['caps']}")

    uses_res = sum(1 for d in data['demands'] if any(x > 0 for x in d))
    rf = round(uses_res / n, 2)
    rs_vals = []
    for r in range(data['n_res']):
        col = [data['demands'][i][r] for i in range(n)]
        mx  = max(col) if col else 1
        rs_vals.append(round(data['caps'][r] / mx if mx > 0 else 99, 2))
    rs = round(sum(rs_vals) / len(rs_vals), 2)
    total_prec = sum(data['prec_matrix'][i][j]
                     for i in range(n) for j in range(n))
    os_val = round(total_prec / (n * (n - 1) / 2), 3)

    print(f"  RF (couverture)    : {rf}")
    print(f"  RS (pression)      : {rs}")
    print(f"  OS (précédences)   : {os_val}")
    print(f"  Stock ciment       : {STOCK_CIMENT.get(stem, 'N/A')} t")
    print(f"  Tâches béton       : {TACHES_BETON.get(stem, [])}")
    print(f"  Équipements lourds : {N_EQUIPEMENTS.get(stem, 0)} types")
    print(f"  Capacité équip.    : {CAPACITE_EQUIPEMENT.get(stem, [])}")


# ===========================================================================
# 6. MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Parser PSPLIB → .dzn MiniZinc")
    parser.add_argument("--input", "-i", default="instancesdebtp.docx",
                        help="Chemin vers le fichier source (.docx ou .txt)")
    parser.add_argument("--outdir", "-o", default="dzn_output",
                        help="Dossier de sortie pour les fichiers .dzn")
    parser.add_argument("--verify", "-v", action="store_true",
                        help="Afficher le résumé uniquement")
    args = parser.parse_args()

    print(f"Chargement de : {args.input}")
    try:
        raw = load_raw_text(args.input)
    except Exception as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        sys.exit(1)

    blocks = re.split(r'(?=j30\d+_\d+\.sm)', raw)
    blocks = [b.strip() for b in blocks if b.strip() and 'PRECEDENCE' in b]

    if not blocks:
        print("ERREUR : Aucun bloc trouvé.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(blocks)} instance(s) détectée(s)\n")

    if not args.verify:
        os.makedirs(args.outdir, exist_ok=True)

    for block in blocks:
        try:
            data = parse_block(block)
            stem = data['stem']

            print_summary(data)

            if not args.verify:
                dzn_path = os.path.join(args.outdir, f"{stem}.dzn")
                to_dzn(
                    data=data,
                    out_path=dzn_path,
                    debut_ete=DEBUT_ETE,
                    fin_ete=FIN_ETE,
                    stock_ciment=STOCK_CIMENT.get(stem, 300),
                    ciment_par_tache=CIMENT_PAR_TACHE.get(stem, {}),
                    taches_beton=TACHES_BETON.get(stem, []),
                    n_equipements=N_EQUIPEMENTS.get(stem, 2),
                    capacite_equipement=CAPACITE_EQUIPEMENT.get(stem, [2, 1]),
                    besoin_equipement=BESOIN_EQUIPEMENT.get(stem, {}),
                )

        except Exception as e:
            print(f"ERREUR lors du parsing : {e}", file=sys.stderr)

    if not args.verify:
        print(f"\nFichiers .dzn écrits dans : {args.outdir}/")


if __name__ == "__main__":
    main()