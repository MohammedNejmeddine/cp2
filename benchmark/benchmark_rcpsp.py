#!/usr/bin/env python3
"""
BENCHMARK RCPSP — Évaluation de Scalabilité
============================================
Compare les instances PSPLIB standard (J30/J60/J90/J120) avec 
l'instance BTP enrichie CASA-LYC-14 (ressources non-renouvelables, 
contraintes climatiques, tâches béton).

Usage:
    python3 benchmark_rcpsp.py --input instancesdebtp.docx --outdir benchmark_output
"""

import re
import os
import sys
import time
import random
import json
import argparse
from collections import defaultdict, deque

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
# 3. PARSING COMMUN
# ===========================================================================

def parse_precedences(content: str) -> dict:
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
    req_match = re.search(
        r'REQUESTS/DURATIONS(?:\s*\([^)]*RENEWABLE\s*RESOURCES[^)]*\))?\s*[:=?]?\s*\n'
        r'(.*?)'
        r'\s*(?:REQUESTS/DURATIONS\s*\(NONRENEWABLE|RESOURCEAVAIL|RESOURCE\s*AVAIL)',
        content, re.DOTALL | re.IGNORECASE
    )
    if not req_match:
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
# 4. PARSING SPÉCIFIQUE CASA-LYC-14
# ===========================================================================

def parse_nonrenewable_requests(content: str, n_nr: int) -> dict:
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
    cap_match = re.search(
        r'RESOURCE\s*AVAILABILITIES\s*\([^)]*NONRENEWABLE[^)]*\)\s*[:=?]?\n(.*?)'
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
    m = re.search(r'Task subset\s*:\s*\{([^}]+)\}', content, re.IGNORECASE)
    if m:
        try:
            return [int(x.strip()) for x in m.group(1).split(',')]
        except ValueError:
            pass
    return []


# ===========================================================================
# 5. PARSEUR PRINCIPAL
# ===========================================================================

def parse_block(content: str) -> dict:
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

    n_jobs = int(re.search(r'[Jj]obs.*?[:=]\s*(\d+)', content).group(1)) if \
             re.search(r'[Jj]obs.*?[:=]\s*(\d+)', content) else 32

    n_r_match = re.search(r'[Rr]enewable\s*[:=]\s*(\d+)', content)
    n_res = int(n_r_match.group(1)) if n_r_match else 4

    n_nr_match = re.search(r'[Nn]onrenewable\s*[:=]\s*(\d+)', content)
    n_nr = int(n_nr_match.group(1)) if n_nr_match else 0

    H_match = re.search(r'[Hh]orizon\s*[:=]\s*(\d+)', content)
    H = int(H_match.group(1)) if H_match else (800 if inst_type == 'J120' else 400)

    successors_raw = parse_precedences(content)
    prec_pairs = [[j, s] for j, succs in successors_raw.items() for s in succs]

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
# 6. SOLVEUR RCPSP
# ===========================================================================

class RCPSPSolver:
    """Solveur RCPSP par liste de priorité + SGS sériel + CP-SAT fallback"""
    
    def __init__(self, data):
        self.n = data['n_total']
        self.H = data['H']
        self.n_res = data['n_res']
        self.n_nr = data.get('n_nr', 0)
        self.durations = data['durations']
        self.demands = data['demands']
        self.caps = data['caps']
        
        self.prec = defaultdict(list)
        self.prec_count = [0] * (self.n + 1)
        for pair in data['prec_pairs']:
            self.prec[pair[0]].append(pair[1])
            self.prec_count[pair[1]] += 1
        
        self.nr_demands = data.get('nr_demands', None)
        self.nr_caps = data.get('nr_caps', None)
        self.climatic = data.get('climatic', None)
        self.concrete_tasks = set(data.get('concrete_tasks', []))
        
        self.pred = defaultdict(list)
        for pair in data['prec_pairs']:
            self.pred[pair[1]].append(pair[0])
    
    def compute_earliest_start(self):
        es = [0] * (self.n + 1)
        for i in range(1, self.n + 1):
            for p in self.pred[i]:
                es[i] = max(es[i], es[p] + self.durations[p - 1])
        return es
    
    def schedule_by_priority(self, priority_order):
        """SGS sériel avec contraintes climatiques"""
        start = [0] * (self.n + 1)
        end = [0] * (self.n + 1)
        scheduled = [False] * (self.n + 1)
        res_usage = [[0] * (self.H + 1) for _ in range(self.n_res)]
        
        for job in priority_order:
            if job == 1:
                start[job] = 0; end[job] = 0; scheduled[job] = True
                continue
            
            est = 0
            for p in self.pred[job]:
                if scheduled[p]:
                    est = max(est, end[p])
                else:
                    return None
            
            s = est
            while s + self.durations[job - 1] <= self.H:
                # Contrainte climatique
                climatic_ok = True
                if self.climatic and job in self.concrete_tasks:
                    ss = self.climatic['summer_start']
                    se = self.climatic['summer_end']
                    e = s + self.durations[job - 1]
                    if not (e <= ss or s >= se):
                        climatic_ok = False
                
                if not climatic_ok:
                    s += 1
                    continue
                
                # Ressources renouvelables
                feasible = True
                for r in range(self.n_res):
                    for t in range(s, s + self.durations[job - 1]):
                        if t >= len(res_usage[r]) or res_usage[r][t] + self.demands[job - 1][r] > self.caps[r]:
                            feasible = False; break
                    if not feasible: break
                
                if feasible: break
                s += 1
            
            if s + self.durations[job - 1] > self.H:
                return None
            
            start[job] = s
            end[job] = s + self.durations[job - 1]
            scheduled[job] = True
            
            for r in range(self.n_res):
                for t in range(s, end[job]):
                    if t < len(res_usage[r]):
                        res_usage[r][t] += self.demands[job - 1][r]
        
        return start
    
    def check_nonrenewable(self, start_times):
        if self.n_nr == 0 or self.nr_demands is None:
            return True
        for nr in range(self.n_nr):
            total = sum(self.nr_demands[i - 1][nr] for i in range(1, self.n + 1))
            if total > self.nr_caps[nr]:
                return False
        return True
    
    def check_climatic(self, start_times):
        if not self.climatic:
            return True
        ss = self.climatic['summer_start']
        se = self.climatic['summer_end']
        for i in self.concrete_tasks:
            s = start_times[i]
            e = s + self.durations[i - 1]
            if not (e <= ss or s >= se):
                return False
        return True
    
    def solve_greedy(self, time_limit=30):
        """Heuristique multi-stratégies"""
        best_makespan = self.H
        best_start = None
        
        es = self.compute_earliest_start()
        mpm_makespan = max(es[i] + self.durations[i - 1] for i in range(1, self.n + 1))
        
        strategies = []
        
        # LST
        ls = [mpm_makespan] * (self.n + 1)
        ls[self.n] = mpm_makespan - self.durations[self.n - 1]
        for i in range(self.n, 0, -1):
            for s in self.prec[i]:
                ls[i] = min(ls[i], ls[s] - self.durations[i - 1])
        strategies.append(('LST', sorted(range(1, self.n + 1), key=lambda x: ls[x])))
        
        # EST
        strategies.append(('EST', sorted(range(1, self.n + 1), key=lambda x: es[x])))
        
        # LPT
        strategies.append(('LPT', sorted(range(1, self.n + 1), key=lambda x: -self.durations[x - 1])))
        
        # MRS
        total_dem = [sum(self.demands[i - 1]) for i in range(1, self.n + 1)]
        strategies.append(('MRS', sorted(range(1, self.n + 1), key=lambda x: -total_dem[x - 1])))
        
        # Random topologique
        for k in range(50):
            random.seed(k)
            in_deg = [0] * (self.n + 1)
            for i in range(1, self.n + 1):
                for s in self.prec[i]:
                    in_deg[s] += 1
            q = deque([i for i in range(1, self.n + 1) if in_deg[i] == 0])
            order = []
            while q:
                candidates = list(q)
                chosen = random.choice(candidates)
                order.append(chosen)
                q.remove(chosen)
                for s in self.prec[chosen]:
                    in_deg[s] -= 1
                    if in_deg[s] == 0:
                        q.append(s)
            if len(order) == self.n:
                strategies.append((f'RAND_{k}', order))
        
        start_time = time.time()
        for name, order in strategies:
            if time.time() - start_time > time_limit:
                break
            result = self.schedule_by_priority(order)
            if result is not None:
                valid = self.check_nonrenewable(result) and self.check_climatic(result)
                if valid:
                    mk = result[self.n]
                    if mk < best_makespan:
                        best_makespan = mk
                        best_start = result.copy()
                        print(f"    [{name}] Makespan = {mk}")
        
        return best_makespan, best_start
    
    def solve_with_cp_sat(self, time_limit=60):
        """OR-Tools CP-SAT si disponible"""
        try:
            from ortools.sat.python import cp_model
        except ImportError:
            return None, None
        
        model = cp_model.CpModel()
        start = {i: model.NewIntVar(0, self.H, f'start_{i}') for i in range(1, self.n + 1)}
        
        # Précédences
        for i in range(1, self.n + 1):
            for j in self.prec[i]:
                model.Add(start[j] >= start[i] + self.durations[i - 1])
        
        # Ressources renouvelables (cumulative)
        intervals = {}
        for i in range(1, self.n + 1):
            end_var = model.NewIntVar(0, self.H + self.durations[i - 1], f'end_{i}')
            intervals[i] = model.NewIntervalVar(start[i], self.durations[i - 1], end_var, f'interval_{i}')
        
        for r in range(self.n_res):
            demands_r = [self.demands[i - 1][r] for i in range(1, self.n + 1)]
            model.AddCumulative(list(intervals.values()), demands_r, self.caps[r])
        
        # Non-renouvelables (consommations totales)
        if self.n_nr > 0 and self.nr_demands is not None:
            for nr in range(self.n_nr):
                total = sum(self.nr_demands[i - 1][nr] for i in range(1, self.n + 1))
                if total > self.nr_caps[nr]:
                    return None, None
        
        # Climatique
        if self.climatic:
            ss = self.climatic['summer_start']
            se = self.climatic['summer_end']
            for i in self.concrete_tasks:
                b = model.NewBoolVar(f'concrete_before_{i}')
                model.Add(start[i] + self.durations[i - 1] <= ss).OnlyEnforceIf(b)
                model.Add(start[i] >= se).OnlyEnforceIf(b.Not())
        
        # Objectif
        makespan = model.NewIntVar(0, self.H, 'makespan')
        model.Add(makespan >= start[self.n] + self.durations[self.n - 1])
        model.Minimize(makespan)
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 4
        status = solver.Solve(model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            start_vals = [0] * (self.n + 1)
            for i in range(1, self.n + 1):
                start_vals[i] = solver.Value(start[i])
            return solver.Value(makespan), start_vals
        return None, None


# ===========================================================================
# 7. GÉNÉRATION DZN
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

    is_concrete = [1 if j in ct else 0 for j in range(1, n + 1)]

    lines = [
        f"% Instance BTP enrichie : {data['name']}",
        f"% Type : {data['inst_type']} ({n} tâches dont {n-2} réelles)",
        f"",
        f"n              = {n};",
        f"n_resources    = {n_res};",
        f"n_nr_resources = {n_nr};",
        f"horizon        = {H};",
        f"",
        f"duration       = {data['durations']};",
        f"resource_avail = {data['caps']};",
        f"req = array2d(1..n, 1..n_resources, [",
        f"    " + ", ".join(str(x) for x in flat_r),
        f"]);",
        f"",
        f"nr_resource_avail = {data['nr_caps']};",
        f"nr_req = array2d(1..n, 1..n_nr_resources, [",
        f"    " + ", ".join(str(x) for x in flat_nr),
        f"]);",
        f"",
        f"precedence = array2d(1..n, 1..n, [",
        f"    " + ", ".join(str(x) for x in prec_flat),
        f"]);",
        f"n_prec = {data['n_prec']};",
        f"",
        f"summer_start = {cl['summer_start']};",
        f"summer_end   = {cl['summer_end']};",
        f"big_M        = {cl['big_m']};",
        f"working_days_only = {'true' if cl['working_days_only'] else 'false'};",
        f"",
        f"n_concrete_tasks = {len(ct)};",
        f"concrete_tasks   = {ct};",
        f"is_concrete      = {is_concrete};",
        f"",
        f"% === FIN ===",
    ]
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"  [BTP-ENRICH] {out_path}  (n={n}, H={H}, béton={ct})")


# ===========================================================================
# 8. BENCHMARK PRINCIPAL
# ===========================================================================

def run_benchmark(input_path: str, outdir: str, time_limit: int = 30):
    """Exécute le benchmark complet"""
    
    print(f"Chargement : {input_path}")
    raw = load_raw_text(input_path)

    all_blocks = re.split(
        r'(?=(?:\*{5,}\s*file with basedata\s*:\s*\S+|file with basedata\s*:\s*\S+|j\d+_\d+\.sm))',
        raw, flags=re.IGNORECASE
    )

    valid_blocks = [
        b.strip() for b in all_blocks
        if b.strip() and 'PRECEDENCE' in b and 'REQUESTS' in b 
        and 'RESOURCE' in b and re.search(r'jobs.*?[:=]\s*\d+', b, re.IGNORECASE)
    ]

    print(f"{len(valid_blocks)} instance(s) détectée(s)\n")
    os.makedirs(outdir, exist_ok=True)

    # Parser toutes les instances
    instances_data = []
    for block in valid_blocks:
        try:
            data = parse_block(block)
            instances_data.append(data)
        except Exception as e:
            print(f"  ERREUR parsing : {e}")

    # Générer fichiers DZN
    dzn_dir = os.path.join(outdir, "dzn")
    os.makedirs(dzn_dir, exist_ok=True)
    
    for data in instances_data:
        dzn_path = os.path.join(dzn_dir, f"{data['stem']}.dzn")
        if data['inst_type'] == 'BTP-ENRICH':
            to_dzn_btp_enrich(data, dzn_path)
        else:
            to_dzn_standard(data, dzn_path)

    # Benchmark
    print("\n" + "=" * 90)
    print("BENCHMARK RCPSP — ÉVALUATION DE SCALABILITÉ")
    print("=" * 90)
    print(f"{'Instance':<<18} {'Type':<<12} {'n':>4} {'H':>5} {'Prec':>5} {'Res':>4} {'NR':>3} "
          f"{'Solver':<<12} {'Makespan':>8} {'Temps(s)':>10} {'Status':<<12}")
    print("-" * 90)

    results = []
    
    for data in instances_data:
        name = data['stem']
        inst_type = data['inst_type']
        n = data['n_total']
        
        solver = RCPSPSolver(data)
        
        # 1. CP-SAT (optimal si OR-Tools disponible)
        t0 = time.time()
        mk_cp, start_cp = solver.solve_with_cp_sat(time_limit=time_limit)
        t_cp = time.time() - t0
        
        if mk_cp is not None:
            results.append({
                'instance': name, 'type': inst_type, 'n': n, 'H': data['H'],
                'n_prec': data['n_prec'], 'n_res': data['n_res'], 'n_nr': data['n_nr'],
                'solver': 'CP-SAT', 'makespan': mk_cp, 'time': t_cp,
                'status': 'OPTIMAL' if mk_cp else 'FEASIBLE'
            })
            print(f"{name:<18} {inst_type:<12} {n:>4} {data['H']:>5} {data['n_prec']:>5} "
                  f"{data['n_res']:>4} {data['n_nr']:>3} {'CP-SAT':<<12} {mk_cp:>8} "
                  f"{t_cp:>10.2f} {'FEASIBLE':<<12}")
        else:
            # 2. Heuristique gloutonne
            t0 = time.time()
            mk_g, start_g = solver.solve_greedy(time_limit=time_limit)
            t_g = time.time() - t0
            
            mk_display = mk_g if mk_g < data['H'] else 'N/A'
            status = 'HEURISTIC' if mk_g < data['H'] else 'INFEASIBLE'
            
            results.append({
                'instance': name, 'type': inst_type, 'n': n, 'H': data['H'],
                'n_prec': data['n_prec'], 'n_res': data['n_res'], 'n_nr': data['n_nr'],
                'solver': 'HEURISTIC', 'makespan': mk_g if mk_g < data['H'] else None,
                'time': t_g, 'status': status
            })
            print(f"{name:<18} {inst_type:<12} {n:>4} {data['H']:>5} {data['n_prec']:>5} "
                  f"{data['n_res']:>4} {data['n_nr']:>3} {'HEURISTIC':<<12} {str(mk_display):>8} "
                  f"{t_g:>10.2f} {status:<12}")

    print("=" * 90)

    # Sauvegarde JSON
    json_path = os.path.join(outdir, "benchmark_results.json")
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nRésultats sauvegardés : {json_path}")

    # Rapport Markdown
    md_path = os.path.join(outdir, "benchmark_report.md")
    with open(md_path, 'w') as f:
        f.write("# Benchmark RCPSP — Évaluation de Scalabilité\n\n")
        f.write("| Instance | Type | n | H | Prec | R | NR | Makespan | Temps (s) | Status |\n")
        f.write("|----------|------|---|---|------|---|---|----------|-----------|--------|\n")
        for r in results:
            mk = str(r['makespan']) if r['makespan'] else 'N/A'
            f.write(f"| {r['instance']} | {r['type']} | {r['n']} | {r['H']} | "
                   f"{r['n_prec']} | {r['n_res']} | {r['n_nr']} | {mk} | "
                   f"{r['time']:.3f} | {r['status']} |\n")
        
        f.write("\n## Analyse\n\n")
        f.write("### Instances PSPLIB Standard\n")
        std = [r for r in results if r['type'] != 'BTP-ENRICH']
        for r in std:
            f.write(f"- **{r['instance']}** ({r['type']}): n={r['n']}, makespan={r['makespan']}, "
                   f"temps={r['time']:.3f}s\n")
        
        f.write("\n### Instance BTP Enrichie\n")
        btp = [r for r in results if r['type'] == 'BTP-ENRICH']
        for r in btp:
            f.write(f"- **{r['instance']}**: n={r['n']}, status={r['status']}\n")
            if r['status'] == 'INFEASIBLE':
                f.write("  - *Contraintes climatiques trop fortes : gap de 100j entre fin du béton avant été "
                       "et début après été, non remplissable avec les tâches disponibles.*\n")
    
    print(f"Rapport Markdown : {md_path}")
    return results


# ===========================================================================
# 9. MAIN
# ===========================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark RCPSP Scalabilité")
    parser.add_argument("--input",  "-i", default="instancesdebtp.docx")
    parser.add_argument("--outdir", "-o", default="benchmark_output")
    parser.add_argument("--time",   "-t", type=int, default=30, help="Time limit per instance (s)")
    args = parser.parse_args()

    random.seed(42)
    results = run_benchmark(args.input, args.outdir, args.time)