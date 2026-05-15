"""
MILP — RCPSP Étendu BTP (Projet P2 INSEA)
"""

import re
import os
import sys
import argparse
import time
from pathlib import Path

try:
    import pulp
except ImportError:
    print("PuLP non installé. Lancez : pip install pulp", file=sys.stderr)
    sys.exit(1)


# ===========================================================================
# 1. PARSING DU FICHIER .DZN
# ===========================================================================

def parse_dzn(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()

    def get_int(name):
        m = re.search(rf'{name}\s*=\s*(\d+)\s*;', text)
        return int(m.group(1)) if m else None

    def get_list(name):
        m = re.search(rf'{name}\s*=\s*\[([^\]]+)\]\s*;', text)
        if not m:
            return []
        return list(map(int, m.group(1).split(',')))

    def get_matrix(name):
        m = re.search(rf'{name}\s*=\s*\[\|(.*?)\|\]\s*;', text, re.DOTALL)
        if not m:
            return []
        rows_str = m.group(1).strip()
        rows = [r.strip() for r in re.split(r'\|', rows_str) if r.strip()]
        matrix = []
        for r in rows:
            vals = [v.strip() for v in r.split(',') if v.strip()]
            if vals:
                matrix.append(list(map(int, vals)))
        return matrix

    def get_set(name):
        m = re.search(rf'{name}\s*=\s*\{{([^}}]*)\}}\s*;', text)
        if not m or not m.group(1).strip():
            return []
        return list(map(int, m.group(1).split(',')))

    name_m = re.search(r'Instance\s*:\s*(\S+)', text)
    name = name_m.group(1) if name_m else Path(path).stem

    data = {
        'name':         name,
        'stem':         Path(path).stem,
        'n':            get_int('n'),
        'H':            get_int('H'),
        'n_res':        get_int('n_res'),
        'durations':    get_list('duree'),
        'capacities':   get_list('capacite'),
        'demands':      get_matrix('besoin'),
        'prec':         get_matrix('prec'),
        'debut_ete':    get_int('debut_ete'),
        'fin_ete':      get_int('fin_ete'),
        'stock_NR':     get_int('stock_NR'),
        'ciment':       get_list('ciment'),
        'taches_beton': get_set('TACHES_BETON'),
    }
    return data


# ===========================================================================
# 2. CONSTRUCTION DU MODÈLE MILP
# ===========================================================================

def build_and_solve(data: dict, time_limit: int = 60, gap: float = 0.05) -> dict:
    n         = data['n']
    H         = data['H']
    n_res     = data['n_res']
    d         = data['durations']
    cap       = data['capacities']
    req       = data['demands']
    prec      = data['prec']
    debut_ete = data['debut_ete']
    fin_ete   = data['fin_ete']
    stock_NR  = data['stock_NR']
    ciment    = data['ciment']
    beton_1   = data['taches_beton']
    beton_0   = [b - 1 for b in beton_1 if 1 <= b <= n]

    T = H

    print(f"\n{'='*65}")
    print(f"  Instance : {data['name']}")
    print(f"  n={n}, H={H}, n_res={n_res}, T={T}")
    print(f"  Tâches béton (0-based) : {beton_0}")
    print(f"  Stock ciment : {stock_NR} t, consommation totale : {sum(ciment)} t")
    print(f"{'='*65}")

    model = pulp.LpProblem(f"RCPSP_BTP_{data['stem']}", pulp.LpMinimize)

    x = [[pulp.LpVariable(f"x_{i}_{t}", cat='Binary')
          for t in range(T + 1)] for i in range(n)]

    Cmax = pulp.LpVariable("Cmax", lowBound=0, cat='Integer')

    model += Cmax, "Minimiser_makespan"

    for i in range(n):
        model += pulp.lpSum(x[i][t] for t in range(T + 1)) == 1, f"UniqueDemarrage_{i}"

    for i in range(n):
        model += (pulp.lpSum(t * x[i][t] for t in range(T + 1)) + d[i]
                  <= Cmax), f"Cmax_{i}"

    for i in range(n):
        for j in range(n):
            if prec[i][j] == 1:
                si = pulp.lpSum(t * x[i][t] for t in range(T + 1))
                sj = pulp.lpSum(t * x[j][t] for t in range(T + 1))
                model += sj >= si + d[i], f"Prec_{i}_{j}"

    for r in range(n_res):
        for tau in range(T + 1):
            model += (
                pulp.lpSum(
                    req[i][r] * pulp.lpSum(
                        x[i][t] for t in range(max(0, tau - d[i] + 1), min(tau + 1, T + 1))
                    )
                    for i in range(n) if req[i][r] > 0
                ) <= cap[r]
            ), f"Res_{r}_{tau}"

    model += (
        pulp.lpSum(ciment[i] for i in range(n)) <= stock_NR
    ), "Stock_ciment_global"

    M = T
    y_beton = {}
    for i in beton_0:
        y_beton[i] = pulp.LpVariable(f"y_beton_{i}", cat='Binary')
        si = pulp.lpSum(t * x[i][t] for t in range(T + 1))
        model += si + d[i] <= debut_ete + M * y_beton[i], f"Beton_avant_{i}"
        model += si >= fin_ete - M * (1 - y_beton[i]), f"Beton_apres_{i}"
    # Ajoute dans build_and_solve avant la résolution
    print(f"  Chemin critique estimé : {sum(d)} jours, H={H}")
    # -----------------------------------------------------------------------
    # Résolution
    # -----------------------------------------------------------------------
    solver = pulp.PULP_CBC_CMD(
        timeLimit=time_limit,
        gapRel=gap,
        msg=1
    )

    t0 = time.time()
    status = model.solve(solver)
    elapsed = round(time.time() - t0, 2)

    status_str = pulp.LpStatus[model.status]
    print(f"\n  Statut      : {status_str}")
    print(f"  Temps CPU   : {elapsed} s")

    result = {
        'name':    data['name'],
        'status':  status_str,
        'elapsed': elapsed,
        'Cmax':    None,
        'lb':      None,
        'gap':     None,
        'starts':  [],
    }

    if pulp.value(Cmax) is not None:
        cmax_val = int(round(pulp.value(Cmax)))

        # Borne inférieure et gap
        try:
            bb = model.bestBound
            lb_val = int(round(bb)) if bb is not None else '?'
        except:
            lb_val = '?'
        
        if isinstance(lb_val, int) and cmax_val > 0:
            gap_val = round(100 * (cmax_val - lb_val) / cmax_val, 1)
        else:
            gap_val = '?'

        result['Cmax'] = cmax_val
        result['lb']   = lb_val
        result['gap']  = gap_val

        # Dates de début
        starts = []
        for i in range(n):
            s = round(sum(t * pulp.value(x[i][t]) for t in range(T + 1)
                          if pulp.value(x[i][t]) is not None
                          and pulp.value(x[i][t]) > 0.5))
            starts.append(int(s))

        result['starts'] = starts
        print(f"  Makespan    : {cmax_val}")
        print(f"\n  Dates de début (0-based) :")
        for i in range(n):
            beton_flag = " [BÉTON]" if i in beton_0 else ""
            print(f"    Tâche {i+1:2d} : début={starts[i]:4d}  fin={starts[i]+d[i]:4d}"
                  f"  durée={d[i]:3d}{beton_flag}")

        # Vérification contrainte climatique
        ok = True
        for i in beton_0:
            s, e = starts[i], starts[i] + d[i]
            if s < fin_ete and e > debut_ete:
                print(f"  VIOLATION CLIMATIQUE tâche {i+1}: [{s}, {e}] ∩ [{debut_ete}, {fin_ete}]")
                ok = False
        if ok:
            print(f"  Contrainte climatique : OK (aucune violation)")

        # Vérification précédences
        prec_ok = True
        for i in range(n):
            for j in range(n):
                if prec[i][j] == 1:
                    if starts[i] + d[i] > starts[j]:
                        print(f"  VIOLATION PREC tâche {i+1} → {j+1}")
                        prec_ok = False
        if prec_ok:
            print(f"  Contraintes de précédence : OK")

    else:
        print(f"  Aucune solution trouvée.")

    return result


# ===========================================================================
# 3. MAIN
# ===========================================================================

def main():
    ap = argparse.ArgumentParser(description="MILP RCPSP BTP — Projet P2 INSEA")
    ap.add_argument("--dzn", nargs='+', default=None,
                    help="Fichier(s) .dzn à résoudre")
    ap.add_argument("--time-limit", type=int, default=60)
    ap.add_argument("--gap", type=float, default=0.05)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)

    if args.dzn is None:
        dzn_dir = os.path.join(base_dir, "dzn_output")
        dzn_files = sorted(Path(dzn_dir).glob("*.dzn"))
        print(f"Instances trouvées : {len(dzn_files)}")
    else:
        dzn_files = [Path(os.path.join(base_dir, p))
                     if not os.path.isabs(p) else Path(p)
                     for p in args.dzn]

    results = []
    for dzn_full in dzn_files:
        print(f"\nTraitement: {dzn_full}")
        if not dzn_full.is_file():
            print(f"Fichier introuvable : {dzn_full}", file=sys.stderr)
            continue
        data = parse_dzn(str(dzn_full))
        result = build_and_solve(data, time_limit=args.time_limit, gap=args.gap)
        results.append(result)

    # Résumé final
    print(f"\n{'='*55}")
    print(f"  RÉSUMÉ — {len(results)} instances résolues")
    print(f"{'='*55}")
    print(f"  {'Instance':<18} {'Statut':<14} {'Makespan':>10} {'Temps(s)':>10}")
    print(f"  {'-'*53}")
    for r in results:
        cmax = str(r['Cmax']) if r['Cmax'] is not None else "N/A"
        print(f"  {r['name']:<18} {r['status']:<14} {cmax:>10} {r['elapsed']:>10}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()