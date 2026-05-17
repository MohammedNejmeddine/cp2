"""
parser_btp.py
=============
Lit instancesdebtp.docx et génère un fichier .dzn MiniZinc par instance.

Projet P2 — CP-INSEA-SDRO-2A — RCPSP étendu BTP marocain
Encadrant : Dr. Jabrane SLIMANI

Usage :
    python parser_btp.py                                    # tout générer
    python parser_btp.py --docx chemin/instancesdebtp.docx # docx custom
    python parser_btp.py --out mon_dossier/                 # dossier de sortie
    python parser_btp.py --list                             # lister les instances
    python parser_btp.py --instance CASA-LYC-14            # une seule instance
"""

import re
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import docx
except ImportError:
    sys.exit("❌  Installe python-docx :  pip install python-docx")


# ══════════════════════════════════════════════════════════════════════════════
# Structures
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Instance:
    name: str
    n_jobs: int = 0
    horizon: int = 0
    n_RR: int = 0
    n_NR: int = 0
    durations:   List[int]       = field(default_factory=list)
    demand_RR:   List[List[int]] = field(default_factory=list)
    cap_RR:      List[int]       = field(default_factory=list)
    demand_NR:   List[List[int]] = field(default_factory=list)
    budget_NR:   List[int]       = field(default_factory=list)
    predecessors: List[List[int]] = field(default_factory=list)  # 1-based
    # Extensions climatiques
    summer_start:   int       = 108
    summer_end:     int       = 192
    concrete_tasks: List[int] = field(default_factory=list)      # 1-based


# ══════════════════════════════════════════════════════════════════════════════
# Lecture du .docx → texte brut
# ══════════════════════════════════════════════════════════════════════════════

def read_docx(path: str) -> str:
    """Extrait tout le texte du .docx en un seul bloc."""
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def split_into_blocks(text: str) -> List[tuple]:
    """
    Découpe le texte en blocs (nom, contenu) en cherchant
    'file with basedata' comme marqueur de début d'instance.
    """
    # Positions de chaque 'file with basedata'
    markers = [m.start() for m in re.finditer(r'file with basedata', text, re.IGNORECASE)]
    if not markers:
        return []

    blocks = []
    for i, start in enumerate(markers):
        end = markers[i + 1] if i + 1 < len(markers) else len(text)
        chunk = text[start:end]

        # Extraire le nom : ce qui suit ':'
        m = re.search(r'file with basedata\s*:\s*(.+)', chunk, re.IGNORECASE)
        raw_name = m.group(1).strip() if m else f"instance_{i+1}"
        # Nettoyer le nom pour en faire un nom de fichier
        name = re.sub(r'[^\w\-]', '_', raw_name.split()[0]).strip('_')
        blocks.append((name, chunk))

    return blocks


# ══════════════════════════════════════════════════════════════════════════════
# Parser générique PSPLIB (blocs standard)
# ══════════════════════════════════════════════════════════════════════════════

def _int(s: str) -> int:
    return int(s.strip())


def parse_header(text: str, inst: Instance):
    m = re.search(r'jobs\s*\(incl\.\s*supersource/sink\s*\)\s*:\s*(\d+)', text)
    if m: inst.n_jobs = _int(m.group(1))

    m = re.search(r'horizon\s*:\s*(\d+)', text)
    if m: inst.horizon = _int(m.group(1))

    m = re.search(r'renewable\s*:\s*(\d+)\s*R', text)
    if m: inst.n_RR = _int(m.group(1))

    m = re.search(r'nonrenewable\s*:\s*(\d+)\s*N', text)
    if m: inst.n_NR = _int(m.group(1))


def parse_precedence(text: str, inst: Instance):
    """Construit predecessors[i] depuis la section PRECEDENCE RELATIONS."""
    sec = re.search(r'PRECEDENCE RELATIONS(.*?)(?=REQUESTS|$)', text, re.DOTALL | re.IGNORECASE)
    if not sec:
        return

    # successors[job] = [s1, s2, ...]  (1-based)
    successors: dict = {}
    for line in sec.group(1).split('\n'):
        m = re.match(r'\s*(\d+)\s+\d+\s+(\d+)(.*)', line)
        if m:
            job    = int(m.group(1))
            n_succ = int(m.group(2))
            rest   = m.group(3).strip().split()
            successors[job] = [int(x) for x in rest[:n_succ]]

    # Inverser → predecessors
    preds = {i: [] for i in range(1, inst.n_jobs + 1)}
    for j, succs in successors.items():
        for s in succs:
            if 1 <= s <= inst.n_jobs:
                preds[s].append(j)
    inst.predecessors = [preds.get(i, []) for i in range(1, inst.n_jobs + 1)]


def _parse_job_lines(section_text: str, n_jobs: int, n_res: int):
    """Parse les lignes 'jobnr mode duration r1 r2 ...' et retourne (durations, demands)."""
    durations = [0] * n_jobs
    demands   = [[0] * n_res for _ in range(n_jobs)]
    for line in section_text.split('\n'):
        m = re.match(r'\s*(\d+)\s+1\s+(\d+)(.*)', line)
        if m:
            job = int(m.group(1)) - 1          # 0-based
            dur = int(m.group(2))
            vals = list(map(int, m.group(3).strip().split()))
            if 0 <= job < n_jobs:
                durations[job] = dur
                demands[job]   = (vals[:n_res] + [0] * n_res)[:n_res]
    return durations, demands


def parse_requests_standard(text: str, inst: Instance):
    """Parse REQUESTS/DURATIONS (format PSPLIB standard, pas de sous-sections RR/NR)."""
    sec = re.search(
        r'REQUESTS/DURATIONS[^(].*?(?=RESOURCE\s*AVAIL|$)',
        text, re.DOTALL | re.IGNORECASE)
    if not sec:
        return
    inst.durations, inst.demand_RR = _parse_job_lines(sec.group(0), inst.n_jobs, inst.n_RR)


def parse_requests_extended(text: str, inst: Instance):
    """Parse REQUESTS/DURATIONS (RENEWABLE) et (NONRENEWABLE) pour CASA-LYC-14."""
    # ── Renouvelables ──
    sec_rr = re.search(
        r'REQUESTS/DURATIONS\s*\(RENEWABLE[^)]*\)(.*?)REQUESTS/DURATIONS\s*\(NONRENEWABLE',
        text, re.DOTALL | re.IGNORECASE)
    if sec_rr:
        inst.durations, inst.demand_RR = _parse_job_lines(
            sec_rr.group(1), inst.n_jobs, inst.n_RR)

    # ── Non-renouvelables ──
    sec_nr = re.search(
        r'REQUESTS/DURATIONS\s*\(NONRENEWABLE[^)]*\)(.*?)RESOURCE\s*AVAIL',
        text, re.DOTALL | re.IGNORECASE)
    if sec_nr:
        _, inst.demand_NR = _parse_job_lines(
            sec_nr.group(1), inst.n_jobs, inst.n_NR)


def parse_availabilities_standard(text: str, inst: Instance):
    """Capacités RR pour instances PSPLIB standard."""
    sec = re.search(r'RESOURCE\s*AVAIL.*?(?=\*{3,}|$)', text, re.DOTALL | re.IGNORECASE)
    if not sec:
        return
    lines = [l.strip() for l in sec.group(0).split('\n') if l.strip()]
    # La dernière ligne numérique contient les valeurs
    for line in reversed(lines):
        nums = re.findall(r'\d+', line)
        if len(nums) >= inst.n_RR:
            inst.cap_RR = list(map(int, nums[:inst.n_RR]))
            break


def parse_availabilities_extended(text: str, inst: Instance):
    """Capacités RR et budgets NR pour CASA-LYC-14."""
    # ── RR : chercher la ligne de valeurs après 'R 1 R 2 ...' ──
    sec_rr = re.search(
        r'RESOURCE\s*AVAIL.*?\(RENEWABLE\)[^\n]*\n'   # titre
        r'[^\n]*R\s*1[^\n]*\n'                        # en-tête colonnes
        r'[ \t]*([\d][\d\s]*)',                        # valeurs
        text, re.IGNORECASE)
    if sec_rr:
        nums = list(map(int, sec_rr.group(1).strip().split()))
        inst.cap_RR = nums[:inst.n_RR]

    # ── NR ──
    sec_nr = re.search(
        r'RESOURCE\s*AVAIL.*?\(NONRENEWABLE\)[^\n]*\n'
        r'[^\n]*N\s*1[^\n]*\n'
        r'[ \t]*([\d][\d\s]*)',
        text, re.IGNORECASE)
    if sec_nr:
        nums = list(map(int, sec_nr.group(1).strip().split()))
        inst.budget_NR = nums[:inst.n_NR]


def parse_climatic(text: str, inst: Instance):
    """Extrait les contraintes climatiques de CASA-LYC-14."""
    m = re.search(r'Summer window start[^:]*:\s*(\d+)', text, re.IGNORECASE)
    if m: inst.summer_start = int(m.group(1))

    m = re.search(r'Summer window end[^:]*:\s*(\d+)', text, re.IGNORECASE)
    if m: inst.summer_end = int(m.group(1))

    m = re.search(r'Task subset\s*:\s*\{([^}]+)\}', text, re.IGNORECASE)
    if m:
        inst.concrete_tasks = [int(x) for x in re.findall(r'\d+', m.group(1))]


def is_moroccan(text: str) -> bool:
    """Détecte si le bloc est l'instance marocaine étendue."""
    return bool(re.search(r'CASA-LYC|RENEWABLE RESOURCES|NONRENEWABLE RESOURCES|CLIMATIC', 
                           text, re.IGNORECASE))


def parse_block(name: str, text: str) -> Optional[Instance]:
    """Parse un bloc complet et retourne une Instance."""
    inst = Instance(name=name)
    try:
        parse_header(text, inst)
        parse_precedence(text, inst)

        if is_moroccan(text):
            parse_requests_extended(text, inst)
            parse_availabilities_extended(text, inst)
            parse_climatic(text, inst)
        else:
            parse_requests_standard(text, inst)
            parse_availabilities_standard(text, inst)
            # Tâches béton heuristiques : durée ≥ 5, hors source/sink
            inst.concrete_tasks = [
                i + 1 for i in range(1, inst.n_jobs - 1)
                if inst.durations[i] >= 5
            ][:5]

        # Valider les dimensions minimales
        assert len(inst.durations) == inst.n_jobs,  "durations mismatch"
        assert len(inst.demand_RR) == inst.n_jobs,  "demand_RR mismatch"
        assert len(inst.cap_RR)    == inst.n_RR,    f"cap_RR mismatch ({len(inst.cap_RR)} vs {inst.n_RR})"

    except Exception as e:
        print(f"  ⚠  [{name}] erreur parsing : {e}")
        return None

    return inst


# ══════════════════════════════════════════════════════════════════════════════
# Générateur .dzn
# ══════════════════════════════════════════════════════════════════════════════

def fmt_array(lst: List[int]) -> str:
    return "[" + ", ".join(map(str, lst)) + "]"


def fmt_matrix(mat: List[List[int]]) -> str:
    rows = [
        "  " + ", ".join(map(str, row)) + " |"
        for row in mat[:-1]
    ]

    last = "  " + ", ".join(map(str, mat[-1]))

    return "[|\n" + "\n".join(rows) + "\n" + last + "\n|]"


def fmt_prec(predecessors: List[List[int]], n: int) -> str:
    mat = [[False] * n for _ in range(n)]

    for j in range(n):
        for p in predecessors[j]:
            i = p - 1
            if 0 <= i < n:
                mat[i][j] = True

    rows = [
        "  " + ", ".join(
            "true" if v else "false"
            for v in row
        ) + " |"
        for row in mat[:-1]
    ]

    last = "  " + ", ".join(
        "true" if v else "false"
        for v in mat[-1]
    )

    return "[|\n" + "\n".join(rows) + "\n" + last + "\n|]"


def to_dzn(inst: Instance) -> str:
    n  = inst.n_jobs
    nr = inst.n_RR
    nn = inst.n_NR
    moroccan = nn > 0 or bool(inst.concrete_tasks and inst.summer_start != 0)

    lines = []
    lines.append(f"""\
%% ================================================================
%% Instance   : {inst.name}
%% Généré par : parser_btp.py  —  Projet P2 CP-INSEA-SDRO-2A
%% RCPSP étendu  RR={nr}  NR={nn}  Climatique={'oui' if moroccan else 'non (heuristique)'}
%% ================================================================
""")

    # ── Dimensions ──────────────────────────────────────────────
    lines.append(f"n    = {n};")
    lines.append(f"H    = {inst.horizon};")
    lines.append(f"n_RR = {nr};")
    lines.append(f"n_NR = {nn};")
    lines.append("")

    # ── Durées ──────────────────────────────────────────────────
    lines.append("% Durées des tâches (jours ouvrés)")
    lines.append(f"duree = {fmt_array(inst.durations)};")
    lines.append("")

    # ── Ressources renouvelables ─────────────────────────────────
    lines.append(f"% Capacités RR [R1..R{nr}]")
    lines.append(f"capacite_RR = {fmt_array(inst.cap_RR)};")
    lines.append("")
    lines.append(f"% Besoins RR  [tâche 1..{n}] × [ressource 1..{nr}]")
    lines.append(f"besoin_RR = {fmt_matrix(inst.demand_RR)};")
    lines.append("")

    # ── Ressources non-renouvelables ─────────────────────────────
    if nn > 0:
        budget = inst.budget_NR if inst.budget_NR else [0] * nn
        dnr    = inst.demand_NR if inst.demand_NR else [[0]*nn for _ in range(n)]
        lines.append(f"% Budgets NR [N1..N{nn}]  (matériaux consommés définitivement)")
        lines.append(f"budget_NR = {fmt_array(budget)};")
        lines.append("")
        lines.append(f"% Consommations NR  [tâche 1..{n}] × [ressource 1..{nn}]")
        lines.append(f"besoin_NR = {fmt_matrix(dnr)};")
    else:
        lines.append("% Pas de ressources non-renouvelables pour cette instance")
        lines.append("budget_NR = [];")
        lines.append("besoin_NR = [||];")
    lines.append("")

    # ── Contraintes climatiques ──────────────────────────────────
    lines.append("% Fenêtre estivale — coulée béton interdite")
    lines.append(f"debut_ete = {inst.summer_start};   % ≈ 1er juin (jour ouvré)")
    lines.append(f"fin_ete   = {inst.summer_end};   % ≈ 30 sept  (jour ouvré)")
    lines.append("")
    lines.append("% Tâches béton soumises à la contrainte climatique")
    lines.append(f"n_beton      = {len(inst.concrete_tasks)};")
    lines.append(f"taches_beton = {fmt_array(inst.concrete_tasks)};")
    lines.append("")

    # ── Précédences ──────────────────────────────────────────────
    lines.append("% Matrice de précédence  prec[i,j] = true  ⟺  i doit finir avant j")
    lines.append(f"prec = {fmt_prec(inst.predecessors, n)};")
    lines.append("")

    lines.append("% Nombre de prédécesseurs par tâche (format alternatif)")
    n_pred = [len(inst.predecessors[i]) for i in range(n)]
    lines.append(f"n_pred = {fmt_array(n_pred)};")
    lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrateur
# ══════════════════════════════════════════════════════════════════════════════

def run(docx_path: str, out_dir: str, only: Optional[str] = None):
    print(f"📄  Lecture de  {docx_path} …")
    text   = read_docx(docx_path)
    blocks = split_into_blocks(text)

    if not blocks:
        sys.exit("❌  Aucun bloc 'file with basedata' trouvé dans le document.")

    print(f"   {len(blocks)} instance(s) détectée(s)\n")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    results = []
    for name, chunk in blocks:
        if only and name.lower() != only.lower():
            continue
        print(f"→  {name}")
        inst = parse_block(name, chunk)
        if inst is None:
            continue
        dzn  = to_dzn(inst)
        path = Path(out_dir) / f"{name}.dzn"
        path.write_text(dzn, encoding="utf-8")
        print(f"   ✓  {path}   ({inst.n_jobs} tâches, H={inst.horizon}, "
              f"RR={inst.n_RR}, NR={inst.n_NR}, béton={len(inst.concrete_tasks)})")
        results.append(inst)

    # ── Tableau récapitulatif ──
    if results:
        print(f"\n{'═'*72}")
        print(f"{'Instance':<20} {'n':>5} {'H':>6} {'RR':>4} {'NR':>4} "
              f"{'Béton':>7} {'Climatique':>11}")
        print(f"{'─'*72}")
        for inst in results:
            clim = "✓ réelle" if inst.n_NR > 0 else "heuristique"
            print(f"{inst.name:<20} {inst.n_jobs:>5} {inst.horizon:>6} "
                  f"{inst.n_RR:>4} {inst.n_NR:>4} {len(inst.concrete_tasks):>7} {clim:>11}")
        print(f"{'═'*72}")
        print(f"\n✅  {len(results)} fichier(s) .dzn → {out_dir}/\n")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Parser BTP → .dzn MiniZinc (Projet P2 INSEA)")
    ap.add_argument("--docx",     default="instancesdebtp.docx",
                    help="Chemin vers le fichier .docx (défaut : instancesdebtp.docx)")
    ap.add_argument("--out",  "-o", default="dzn_output",
                    help="Dossier de sortie des .dzn  (défaut : dzn_output/)")
    ap.add_argument("--instance", "-i", metavar="NOM",
                    help="Générer une seule instance (ex: CASA-LYC-14, j30_17)")
    ap.add_argument("--list", "-l", action="store_true",
                    help="Lister les instances détectées sans générer")
    args = ap.parse_args()

    # Résoudre le chemin du docx
    docx_path = Path(args.docx)
    if not docx_path.exists():
        # Chercher à côté du script
        alt = Path(__file__).parent / args.docx
        if alt.exists():
            docx_path = alt
        else:
            sys.exit(f"❌  Fichier introuvable : {args.docx}")

    if args.list:
        text   = read_docx(str(docx_path))
        blocks = split_into_blocks(text)
        print(f"Instances dans {docx_path} :")
        for name, chunk in blocks:
            inst = Instance(name=name)
            parse_header(chunk, inst)
            tag = " [ÉTENDUE]" if is_moroccan(chunk) else ""
            print(f"  {name:<20}  {inst.n_jobs} tâches  H={inst.horizon}{tag}")
        return

    run(str(docx_path), args.out, only=args.instance)


if __name__ == "__main__":
    main()