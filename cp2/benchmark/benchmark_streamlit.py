#!/usr/bin/env python3
"""
STREAMLIT APP — Benchmark RCPSP Scalabilité
============================================
Dashboard interactif pour comparer les instances PSPLIB (J30/J60/J90/J120)
avec l'instance BTP enrichie CASA-LYC-14.

Usage:
    streamlit run cp2/benchmark/benchmark_streamlit.py

Prérequis:
    pip install streamlit plotly pandas
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import sys
import subprocess
import time
import random
import re
from collections import defaultdict, deque
from io import StringIO

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Benchmark RCPSP",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS PERSONNALISÉ ────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .success-box {
        background: #d4edda;
        border-left: 5px solid #28a745;
        padding: 1rem;
        border-radius: 5px;
    }
    .warning-box {
        background: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 1rem;
        border-radius: 5px;
    }
    .danger-box {
        background: #f8d7da;
        border-left: 5px solid #dc3545;
        padding: 1rem;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ─── SOLVEUR RCPSP ───────────────────────────────────────────────────────

class RCPSPSolver:
    def __init__(self, data):
        self.n = data['n_total']
        self.H = data['H']
        self.n_res = data['n_res']
        self.n_nr = data.get('n_nr', 0)
        self.durations = data['durations']
        self.demands = data['demands']
        self.caps = data['caps']
        self.prec = defaultdict(list)
        self.pred = defaultdict(list)
        for pair in data['prec_pairs']:
            self.prec[pair[0]].append(pair[1])
            self.pred[pair[1]].append(pair[0])
        self.nr_demands = data.get('nr_demands', None)
        self.nr_caps = data.get('nr_caps', None)
        self.climatic = data.get('climatic', None)
        self.concrete_tasks = set(data.get('concrete_tasks', []))
    
    def compute_earliest_start(self):
        es = [0] * (self.n + 1)
        for i in range(1, self.n + 1):
            for p in self.pred[i]:
                es[i] = max(es[i], es[p] + self.durations[p - 1])
        return es
    
    def schedule_by_priority(self, priority_order):
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
                if scheduled[p]: est = max(est, end[p])
                else: return None
            
            s = est
            while s + self.durations[job - 1] <= self.H:
                climatic_ok = True
                if self.climatic and job in self.concrete_tasks:
                    ss, se = self.climatic['summer_start'], self.climatic['summer_end']
                    e = s + self.durations[job - 1]
                    if not (e <= ss or s >= se): climatic_ok = False
                if not climatic_ok: s += 1; continue
                
                feasible = True
                for r in range(self.n_res):
                    for t in range(s, s + self.durations[job - 1]):
                        if t >= len(res_usage[r]) or res_usage[r][t] + self.demands[job - 1][r] > self.caps[r]:
                            feasible = False; break
                    if not feasible: break
                if feasible: break
                s += 1
            
            if s + self.durations[job - 1] > self.H: return None
            start[job] = s; end[job] = s + self.durations[job - 1]; scheduled[job] = True
            for r in range(self.n_res):
                for t in range(s, end[job]):
                    if t < len(res_usage[r]): res_usage[r][t] += self.demands[job - 1][r]
        return start
    
    def check_nonrenewable(self):
        if self.n_nr == 0 or self.nr_demands is None: return True
        for nr in range(self.n_nr):
            total = sum(self.nr_demands[i - 1][nr] for i in range(1, self.n + 1))
            if total > self.nr_caps[nr]: return False
        return True
    
    def solve_greedy(self, time_limit=30, n_rand=50):
        best_makespan, best_start = self.H, None
        es = self.compute_earliest_start()
        mpm_makespan = max(es[i] + self.durations[i - 1] for i in range(1, self.n + 1))
        
        strategies = []
        # LST
        ls = [mpm_makespan] * (self.n + 1)
        ls[self.n] = mpm_makespan - self.durations[self.n - 1]
        for i in range(self.n, 0, -1):
            for s in self.prec[i]: ls[i] = min(ls[i], ls[s] - self.durations[i - 1])
        strategies.append(('LST', sorted(range(1, self.n + 1), key=lambda x: ls[x])))
        # EST
        strategies.append(('EST', sorted(range(1, self.n + 1), key=lambda x: es[x])))
        # LPT
        strategies.append(('LPT', sorted(range(1, self.n + 1), key=lambda x: -self.durations[x - 1])))
        # MRS
        total_dem = [sum(self.demands[i - 1]) for i in range(1, self.n + 1)]
        strategies.append(('MRS', sorted(range(1, self.n + 1), key=lambda x: -total_dem[x - 1])))
        # Random topologique
        for k in range(n_rand):
            random.seed(k)
            in_deg = [0] * (self.n + 1)
            for i in range(1, self.n + 1):
                for s in self.prec[i]: in_deg[s] += 1
            q = deque([i for i in range(1, self.n + 1) if in_deg[i] == 0])
            order = []
            while q:
                candidates = list(q); chosen = random.choice(candidates)
                order.append(chosen); q.remove(chosen)
                for s in self.prec[chosen]:
                    in_deg[s] -= 1
                    if in_deg[s] == 0: q.append(s)
            if len(order) == self.n: strategies.append((f'RAND_{k}', order))
        
        start_time = time.time()
        for name, order in strategies:
            if time.time() - start_time > time_limit: break
            result = self.schedule_by_priority(order)
            if result is not None:
                mk = result[self.n]
                if mk < best_makespan:
                    best_makespan = mk; best_start = result.copy()
        return best_makespan, best_start


# ─── DONNÉES DES INSTANCES ─────────────────────────────────────────────

@st.cache_data
def get_instances():
    return [
        {
            'name': 'j301_1', 'type': 'J30', 'n': 32, 'H': 158, 'n_prec': 48, 
            'n_res': 4, 'n_nr': 0, 'caps': [12, 13, 4, 12],
            'durations': [0, 8, 4, 6, 3, 8, 5, 9, 2, 7, 9, 2, 6, 3, 9, 10, 6, 5, 3, 7, 7, 2, 7, 2, 3, 3, 7, 8, 3, 7, 2, 2, 0],
            'demands': [[0]*4, [4,0,0,0], [10,0,0,0], [0,0,0,3], [3,0,0,0], [0,0,0,8], [4,0,0,0], [0,1,0,0], [6,0,0,0], [0,0,0,1], [0,5,0,0], [0,7,0,0], [4,0,0,0], [0,8,0,0], [3,0,0,0], [0,0,0,5], [0,0,0,8], [0,0,0,7], [0,1,0,0], [0,10,0,0], [0,0,0,6], [2,0,0,0], [3,0,0,0], [0,9,0,0], [4,0,0,0], [0,0,4,0], [0,0,0,7], [0,8,0,0], [0,0,2,0], [0,7,0,0], [0,7,0,0], [0,0,2,0], [0,0,0,0]],
            'prec_pairs': [[1,2],[1,3],[1,4],[2,6],[2,11],[2,15],[3,7],[3,8],[3,13],[4,5],[4,9],[4,10],[5,20],[6,30],[7,27],[8,12],[8,19],[8,27],[9,14],[10,16],[10,25],[11,20],[11,26],[12,14],[13,17],[13,18],[14,17],[15,25],[16,21],[16,22],[17,22],[18,20],[18,22],[19,24],[19,29],[20,23],[20,25],[21,28],[22,23],[23,24],[24,30],[25,30],[26,31],[27,28],[28,31],[29,32],[30,32],[31,32]],
            'n_total': 32
        },
        {
            'name': 'j3021_1', 'type': 'J30', 'n': 32, 'H': 171, 'n_prec': 58,
            'n_res': 4, 'n_nr': 0, 'caps': [11, 12, 12, 8],
            'durations': [0, 5, 9, 2, 10, 10, 1, 9, 8, 7, 5, 2, 4, 4, 1, 7, 6, 3, 8, 5, 9, 5, 8, 9, 3, 7, 6, 2, 10, 1, 5, 10, 0],
            'demands': [[0]*4, [3,0,0,0], [0,5,3,6], [0,0,4,0], [2,0,1,0], [4,6,4,0], [0,0,0,6], [6,0,4,0], [2,8,5,0], [0,0,9,7], [9,0,3,0], [5,8,0,3], [1,0,5,1], [0,4,0,0], [9,5,0,0], [0,9,4,1], [6,0,1,0], [9,9,2,0], [0,0,10,3], [0,4,0,0], [0,3,0,0], [2,0,0,0], [0,4,0,0], [4,0,5,6], [0,0,6,0], [2,0,6,1], [0,0,8,0], [10,6,0,0], [7,0,8,0], [2,1,9,7], [7,10,1,4], [0,9,8,0], [0,0,0,0]],
            'prec_pairs': [[1,2],[1,3],[1,4],[2,5],[2,8],[2,10],[3,15],[4,10],[4,14],[5,6],[5,16],[6,7],[7,9],[7,11],[7,12],[8,18],[8,23],[9,18],[9,27],[9,29],[10,26],[10,29],[10,30],[11,13],[11,21],[11,26],[12,19],[12,22],[12,25],[13,17],[13,23],[13,28],[14,15],[14,21],[15,16],[15,19],[16,17],[17,22],[18,20],[18,25],[19,20],[19,23],[19,27],[20,28],[21,31],[22,24],[22,26],[23,24],[23,31],[24,29],[24,30],[25,26],[26,28],[27,30],[28,31],[29,32],[30,32],[31,32]],
            'n_total': 32
        },
        {
            'name': 'j3029_1', 'type': 'J30', 'n': 32, 'H': 177, 'n_prec': 58,
            'n_res': 4, 'n_nr': 0, 'caps': [15, 16, 16, 15],
            'durations': [0, 9, 4, 9, 8, 4, 2, 4, 2, 4, 7, 5, 10, 5, 2, 9, 9, 3, 9, 9, 10, 6, 8, 9, 1, 1, 6, 9, 6, 3, 10, 2, 0],
            'demands': [[0]*4, [1,6,2,3], [5,2,10,6], [2,3,3,9], [6,4,7,1], [2,6,8,9], [7,7,5,6], [9,6,9,10], [8,5,2,6], [1,4,1,10], [9,9,8,9], [5,5,3,5], [5,7,3,2], [4,7,6,4], [4,2,2,10], [5,6,9,9], [8,8,5,5], [1,9,3,7], [3,3,7,3], [8,10,6,10], [7,4,4,4], [1,3,1,7], [6,4,8,1], [10,7,10,4], [6,7,1,7], [7,4,8,10], [10,9,6,10], [7,8,3,1], [2,1,9,7], [2,5,6,1], [5,5,2,8], [0,0,0,0]],
            'prec_pairs': [[1,2],[1,3],[1,4],[2,7],[2,19],[2,30],[3,6],[3,12],[4,5],[4,9],[4,20],[5,10],[5,17],[5,23],[6,13],[6,14],[6,20],[7,8],[8,11],[8,15],[8,25],[9,14],[9,15],[9,24],[10,16],[10,18],[10,29],[11,16],[11,20],[11,21],[12,26],[12,30],[13,27],[14,17],[15,21],[15,22],[15,23],[16,22],[16,24],[17,31],[18,21],[18,22],[18,24],[19,25],[19,26],[19,29],[20,29],[21,31],[22,26],[23,28],[24,27],[25,28],[26,27],[27,28],[28,31],[29,32],[30,32],[31,32]],
            'n_total': 32
        },
        {
            'name': 'j3045_1', 'type': 'J30', 'n': 32, 'H': 151, 'n_prec': 68,
            'n_res': 4, 'n_nr': 0, 'caps': [15, 14, 15, 14],
            'durations': [0, 2, 4, 4, 1, 10, 10, 7, 2, 7, 2, 3, 4, 3, 3, 5, 6, 1, 9, 7, 4, 5, 5, 5, 8, 4, 3, 8, 7, 9, 6, 2, 0],
            'demands': [[0]*4, [3,9,1,9], [8,8,3,10], [3,4,3,1], [1,7,6,4], [1,2,5,4], [7,5,7,10], [6,3,1,3], [1,8,7,6], [2,9,3,4], [8,5,3,3], [1,6,8,2], [1,9,10,7], [5,8,2,5], [3,10,4,9], [8,9,10,7], [9,8,8,5], [8,2,6,8], [8,1,7,9], [6,8,5,4], [5,3,4,10], [4,5,10,6], [8,5,5,7], [8,5,5,7], [4,4,4,2], [4,10,7,8], [4,10,3,1], [10,10,7,1], [7,3,6,6], [5,1,10,7], [3,2,4,5], [7,3,2,8], [0,0,0,0]],
            'prec_pairs': [[1,2],[1,3],[1,4],[2,5],[2,8],[2,14],[3,8],[3,22],[3,31],[4,6],[4,10],[4,11],[5,6],[5,7],[5,12],[6,19],[6,27],[7,15],[7,16],[7,23],[8,9],[8,25],[9,16],[9,17],[9,24],[10,12],[10,13],[11,17],[11,20],[11,27],[12,18],[12,19],[12,21],[13,15],[13,18],[13,20],[14,15],[14,16],[14,23],[15,17],[15,19],[15,21],[16,30],[17,29],[18,23],[18,26],[18,31],[19,22],[19,25],[19,31],[20,21],[20,22],[21,24],[21,25],[21,29],[22,24],[22,26],[23,27],[23,28],[24,28],[25,26],[25,28],[26,30],[27,29],[28,30],[29,32],[30,32],[31,32]],
            'n_total': 32
        },
        {
            'name': 'CASA-LYC-14', 'type': 'BTP-ENRICH', 'n': 16, 'H': 280, 'n_prec': 18,
            'n_res': 3, 'n_nr': 3, 'caps': [8, 2, 3],
            'nr_caps': [180, 40, 400],
            'durations': [0, 8, 14, 18, 10, 16, 12, 16, 12, 20, 25, 12, 20, 30, 22, 0],
            'demands': [[0,0,0], [2,1,1], [3,2,1], [5,2,1], [4,1,1], [5,1,1], [6,2,1], [5,1,1], [6,2,1], [7,2,2], [6,0,2], [3,1,1], [4,0,1], [5,0,2], [6,0,2], [0,0,0]],
            'nr_demands': [[0,0,0], [0,0,0], [0,0,0], [35,8,70], [18,2,45], [22,6,50], [25,5,55], [22,6,50], [25,5,55], [28,6,60], [5,0,5], [0,0,0], [0,0,0], [0,0,5], [0,0,5], [0,0,0]],
            'prec_pairs': [[1,2],[2,3],[3,4],[4,5],[4,6],[5,11],[6,7],[7,8],[8,9],[9,10],[10,11],[10,12],[11,13],[11,14],[12,14],[13,15],[14,15],[15,16]],
            'climatic': {'big_m': 280, 'summer_start': 108, 'summer_end': 192, 'working_days_only': True},
            'concrete_tasks': [4, 5, 6, 7, 8, 9, 10],
            'n_total': 16
        },
        {
            'name': 'J1201_1', 'type': 'J120', 'n': 122, 'H': 667, 'n_prec': 183,
            'n_res': 4, 'n_nr': 0, 'caps': [14, 12, 13, 9],
            'durations': [0, 6, 4, 2, 2, 3, 10, 2, 7, 4, 10, 6, 4, 7, 4, 10, 9, 1, 9, 10, 5, 9, 8, 3, 3, 9, 8, 10, 9, 5, 2, 10, 6, 9, 10, 9, 2, 10, 9, 2, 8, 4, 2, 2, 8, 2, 2, 1, 2, 7, 5, 7, 2, 9, 9, 1, 10, 10, 8, 9, 3, 4, 2, 7, 10, 2, 5, 5, 3, 2, 6, 3, 7, 5, 4, 1, 7, 5, 4, 6, 10, 1, 9, 1, 8, 7, 3, 7, 10, 3, 5, 4, 5, 3, 2, 3, 0, 6, 6, 10, 10, 6, 2, 2, 2, 10, 1, 3, 3, 4, 5, 9, 3, 1, 10, 3, 7, 8, 1, 5, 9, 3, 0, 6, 9, 6, 9, 9, 8, 7, 2, 2, 7, 10, 5, 2, 3, 8, 9, 3, 2, 0],
            'demands': [[0]*4]*122,
            'prec_pairs': [[1,2],[1,3],[1,4],[2,12],[2,65],[2,75],[3,5],[3,6],[3,10],[4,8],[4,9],[4,13],[5,25],[5,26],[5,99],[6,7],[6,21],[6,38],[7,11],[8,15],[8,23],[8,60],[9,16],[9,59],[9,110],[10,19],[10,53],[10,71],[11,18],[12,14],[12,17],[12,20],[13,33],[13,44],[13,78],[14,32],[14,34],[14,66],[15,22],[15,30],[15,39],[16,28],[17,19],[17,24],[17,51],[18,33],[18,61],[18,73],[19,83],[20,58],[20,76],[21,46],[21,69],[21,106],[22,56],[22,77],[22,97],[23,27],[23,29],[23,35],[24,25],[25,85],[25,101],[26,77],[27,90],[28,37],[29,31],[30,37],[30,42],[31,96],[32,43],[32,48],[33,36],[33,41],[33,45],[34,55],[35,48],[35,64],[36,43],[37,100],[38,47],[38,72],[38,95],[39,40],[39,54],[40,74],[41,116],[42,75],[43,49],[43,77],[44,91],[45,71],[46,57],[46,70],[47,58],[48,78],[49,50],[49,52],[50,110],[51,67],[51,91],[51,98],[52,63],[53,54],[54,88],[55,62],[55,105],[56,59],[56,103],[57,121],[58,87],[59,80],[59,113],[60,71],[61,68],[61,111],[62,67],[63,74],[64,109],[65,93],[66,106],[67,79],[68,93],[69,104],[70,95],[70,98],[71,81],[72,84],[72,86],[73,79],[73,94],[73,115],[74,87],[74,91],[74,98],[75,112],[76,112],[77,86],[78,112],[79,82],[79,113],[80,89],[81,103],[82,102],[83,118],[84,114],[85,108],[86,92],[87,105],[88,90],[89,107],[90,100],[91,102],[92,117],[93,100],[94,118],[95,118],[96,99],[97,107],[98,114],[99,103],[100,119],[101,111],[102,107],[103,105],[104,115],[105,115],[106,109],[107,116],[108,121],[109,119],[110,113],[111,119],[112,116],[113,117],[114,120],[115,120],[116,117],[117,121],[118,120],[119,122],[120,122],[121,122]],
            'n_total': 122
        },
        {
            'name': 'j901_1', 'type': 'J90', 'n': 92, 'H': 507, 'n_prec': 138,
            'n_res': 4, 'n_nr': 0, 'caps': [12, 14, 17, 13],
            'durations': [0]*92,
            'demands': [[0]*4]*92,
            'prec_pairs': [[1,2],[1,3],[1,4],[2,11],[2,24],[3,7],[3,8],[3,15],[4,5],[4,6],[4,19],[5,10],[5,30],[5,91],[6,9],[6,22],[6,26],[7,23],[7,27],[8,42],[9,17],[9,25],[9,61],[10,13],[10,52],[11,12],[11,29],[11,45],[12,14],[12,16],[12,18],[13,83],[14,56],[15,20],[15,35],[15,36],[16,38],[17,65],[18,21],[18,47],[18,66],[19,71],[20,28],[20,33],[21,32],[21,57],[21,88],[22,63],[23,34],[23,70],[24,31],[24,47],[24,67],[25,70],[26,37],[26,39],[26,54],[27,49],[28,41],[28,63],[28,77],[29,44],[30,85],[31,82],[32,51],[32,71],[33,52],[33,53],[33,78],[34,73],[35,55],[36,40],[36,43],[36,48],[37,46],[37,61],[38,82],[39,59],[40,63],[41,73],[41,76],[41,86],[42,50],[43,77],[44,58],[45,68],[46,90],[47,54],[48,50],[49,68],[50,87],[51,72],[52,61],[53,81],[54,84],[55,62],[56,60],[56,69],[56,80],[57,79],[58,59],[58,76],[59,85],[60,72],[60,74],[61,74],[62,64],[63,70],[64,75],[65,85],[66,79],[67,86],[68,78],[69,73],[69,83],[70,72],[71,78],[72,81],[72,90],[73,90],[74,79],[75,80],[76,83],[77,86],[78,84],[79,87],[80,82],[81,91],[82,89],[83,88],[84,91],[85,87],[86,88],[87,89],[88,89],[89,92],[90,92],[91,92]],
            'n_total': 92
        },
        {
            'name': 'j601_1', 'type': 'J60', 'n': 62, 'H': 329, 'n_prec': 93,
            'n_res': 4, 'n_nr': 0, 'caps': [13, 11, 12, 13],
            'durations': [0]*62,
            'demands': [[0]*4]*62,
            'prec_pairs': [[1,2],[1,3],[1,4],[2,5],[2,10],[2,15],[3,7],[3,14],[3,29],[4,8],[4,12],[4,16],[5,6],[5,22],[5,24],[6,17],[6,38],[7,23],[8,9],[8,20],[8,40],[9,13],[9,35],[10,11],[10,45],[11,26],[11,37],[11,44],[12,21],[12,27],[13,18],[14,18],[14,19],[14,34],[15,25],[15,59],[16,55],[16,58],[17,32],[17,43],[18,28],[18,33],[19,28],[20,27],[20,31],[21,39],[22,31],[23,51],[24,48],[25,40],[26,49],[26,54],[27,30],[27,51],[28,47],[28,61],[29,41],[29,57],[30,56],[31,43],[32,57],[33,39],[34,44],[35,36],[35,39],[36,42],[37,58],[38,50],[38,60],[39,53],[40,53],[41,46],[42,48],[43,51],[43,58],[44,50],[45,53],[46,56],[47,52],[48,55],[49,60],[50,61],[51,60],[52,54],[53,56],[54,55],[55,57],[56,61],[57,59],[58,59],[59,62],[60,62],[61,62]],
            'n_total': 62
        }
    ]

# ─── SIDEBAR ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Paramètres")
    
    uploaded_file = st.file_uploader("📁 Fichier instances (.docx)", type=['docx'])
    
    time_limit = st.slider("⏱️ Time limit (s)", 1, 120, 30)
    
    n_rand = st.slider("🔀 Random samples", 10, 200, 50)
    
    st.markdown("---")
    st.markdown("### 📊 Affichage")
    show_gantt = st.checkbox("Diagramme de Gantt", True)
    show_resource = st.checkbox("Profil ressources", True)
    show_comparison = st.checkbox("Comparaison scalabilité", True)
    
    st.markdown("---")
    if st.button("🚀 Lancer le benchmark", type="primary", use_container_width=True):
        st.session_state.run_benchmark = True
    else:
        if 'run_benchmark' not in st.session_state:
            st.session_state.run_benchmark = False

# ─── HEADER ──────────────────────────────────────────────────────────────

st.markdown('<div class="main-header">📊 Benchmark RCPSP — Évaluation de Scalabilité</div>', 
            unsafe_allow_html=True)

st.markdown("""
<div style="text-align: center; color: #666; margin-bottom: 2rem;">
    Comparaison des instances PSPLIB (J30 → J120) avec l'instance BTP enrichie CASA-LYC-14
</div>
""", unsafe_allow_html=True)

# ─── CHARGEMENT DES DONNÉES ─────────────────────────────────────────────

instances = get_instances()

# ─── MÉTRIQUES GLOBALES ─────────────────────────────────────────────────

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{len(instances)}</div>
        <div class="metric-label">Instances</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    max_n = max(r['n'] for r in instances)
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
        <div class="metric-value">{max_n}</div>
        <div class="metric-label">Max tâches</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    std_count = len([r for r in instances if r['type'] != 'BTP-ENRICH'])
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
        <div class="metric-value">{std_count}</div>
        <div class="metric-label">PSPLIB std</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    btp_count = len([r for r in instances if r['type'] == 'BTP-ENRICH'])
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
        <div class="metric-value">{btp_count}</div>
        <div class="metric-label">BTP enrichi</div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);">
        <div class="metric-value">4</div>
        <div class="metric-label">Familles</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ─── EXECUTION DU BENCHMARK ──────────────────────────────────────────────

# ─── EXECUTION DU BENCHMARK ──────────────────────────────────────────────

# Cherche le JSON produit par benchmark_rcpsp.py
JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "benchmark_output", "benchmark_results.json"
)

@st.cache_data
def load_json_results(path):
    with open(path) as f:
        return json.load(f)

def enrich_with_start_times(json_results, instances):
    """Ajoute les start_times via heuristique pour le Gantt uniquement"""
    instances_map = {inst['name']: inst for inst in instances}
    enriched = []
    for r in json_results:
        r = dict(r)
        inst_name = r['instance']
        # Cherche l'instance correspondante
        inst = instances_map.get(inst_name)
        if inst and r.get('makespan') is not None and r['status'] != 'INFEASIBLE':
            solver = RCPSPSolver(inst)
            _, start = solver.solve_greedy(time_limit=5, n_rand=20)
            r['start_times'] = start
        else:
            r['start_times'] = None
        enriched.append(r)
    return enriched

if os.path.exists(JSON_PATH):
    if st.session_state.run_benchmark or 'results' not in st.session_state:
        json_results = load_json_results(JSON_PATH)
        with st.spinner("🔄 Calcul des starts pour Gantt..."):
            results = enrich_with_start_times(json_results, instances)
        st.session_state.results = results

else:
    # Fallback heuristique si JSON absent
    st.warning("⚠️ JSON introuvable — calcul heuristique en cours...")
    if st.session_state.run_benchmark or 'results' not in st.session_state:
        with st.spinner("🔄 Exécution du benchmark en cours..."):
            progress_bar = st.progress(0)
            results = []
            for idx, data in enumerate(instances):
                progress_bar.progress((idx + 1) / len(instances))
                solver = RCPSPSolver(data)
                t0 = time.time()
                mk, start = solver.solve_greedy(time_limit=time_limit, n_rand=n_rand)
                t = time.time() - t0
                valid = mk < data['H']
                results.append({
                    'instance': data['name'], 'type': data['type'],
                    'n': data['n'], 'H': data['H'], 'n_prec': data['n_prec'],
                    'n_res': data['n_res'], 'n_nr': data.get('n_nr', 0),
                    'makespan': mk if valid else None, 'time': t,
                    'status': 'HEURISTIC' if valid else 'INFEASIBLE',
                    'start_times': start if valid else None, 'solver': 'HEURISTIC'
                })
            st.session_state.results = results
            progress_bar.empty()

results = st.session_state.results

# ─── TABLEAU RÉSULTATS ──────────────────────────────────────────────────

st.markdown("### 📋 Résultats du Benchmark")

df = pd.DataFrame(results)
df_display = df[['instance', 'type', 'n', 'H', 'n_prec', 'n_res', 'n_nr', 'makespan', 'time', 'status']].copy()
df_display['makespan'] = df_display['makespan'].fillna('N/A')
df_display['time'] = df_display['time'].round(3)

def highlight_status(val):
    if val in ('HEURISTIC', 'FEASIBLE', 'OPTIMAL'): 
        return 'background-color: #d4edda'
    if val == 'INFEASIBLE': 
        return 'background-color: #f8d7da'
    return ''

st.dataframe(
    df_display.style.map(highlight_status, subset=['status']),
    use_container_width=True,
    height=350
)

# ─── VISUALISATIONS ─────────────────────────────────────────────────────

if show_comparison:
    st.markdown("---")
    st.markdown("### 📈 Analyse de Scalabilité")
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        fig_time = px.scatter(
            df[df['type'] != 'BTP-ENRICH'], 
            x='n', y='time', 
            color='type', size='n_prec',
            hover_data=['instance', 'makespan'],
            title="Temps de résolution vs Taille",
            labels={'n': 'Nombre de tâches', 'time': 'Temps (s)', 'type': 'Famille'},
            log_x=True, log_y=True
        )
        casa = df[df['type'] == 'BTP-ENRICH']
        if not casa.empty:
            fig_time.add_scatter(
                x=casa['n'], y=casa['time'],
                mode='markers', marker=dict(size=20, color='red', symbol='x'),
                name='CASA-LYC-14 (infaisable)'
            )
        fig_time.update_layout(height=400)
        st.plotly_chart(fig_time, use_container_width=True)
    
    with col_right:
        df_valid = df[df['makespan'].notna()]
        fig_mk = go.Figure()
        
        for t in df_valid['type'].unique():
            d = df_valid[df_valid['type'] == t]
            fig_mk.add_trace(go.Bar(
                name=t, x=d['instance'], y=d['makespan'],
                text=d['makespan'], textposition='auto'
            ))
        
        fig_mk.add_trace(go.Scatter(
            x=df['instance'], y=df['H'],
            mode='markers+lines', name='Horizon',
            line=dict(dash='dash', color='gray')
        ))
        
        fig_mk.update_layout(
            title="Makespan vs Horizon",
            xaxis_title="Instance",
            yaxis_title="Jours",
            barmode='group',
            height=400
        )
        st.plotly_chart(fig_mk, use_container_width=True)

# ─── DÉTAIL PAR INSTANCE ────────────────────────────────────────────────

st.markdown("---")
st.markdown("### 🔍 Détail par Instance")

selected = st.selectbox(
    "Choisir une instance à analyser",
    options=[r['instance'] for r in results],
    format_func=lambda x: f"{x} ({[r['type'] for r in results if r['instance']==x][0]})"
)

selected_data = [r for r in results if r['instance'] == selected][0]
selected_raw = [i for i in instances if i['name'] == selected][0]

if selected_data['status'] == 'INFEASIBLE':
    st.markdown("""
    <div class="danger-box">
        <h4>⚠️ Instance INFAISABLE</h4>
        <p>Les contraintes climatiques (bétonnage interdit en été) rendent cette instance 
        infaisable avec l'heuristique SGS sériel. Le gap de 100 jours entre la fin du béton 
        avant l'été et le début après l'été ne peut être rempli car toutes les tâches 
        intermédiaires dépendent du bétonnage.</p>
        <p><b>Recommandation :</b> Utiliser un solveur MIP/CP (OR-Tools, Gurobi) ou 
        relaxer les contraintes climatiques.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    col_d1, col_d2, col_d3, col_d4 = st.columns(4)
    col_d1.metric("Makespan", f"{selected_data['makespan']} j")
    col_d2.metric("Temps", f"{selected_data['time']:.3f}s")
    col_d3.metric("Utilisation", f"{selected_data['makespan']/selected_data['H']*100:.1f}%")
    col_d4.metric("Tâches", selected_data['n'])
    
if show_gantt and selected_data['start_times']:
    st.markdown("#### 📅 Diagramme de Gantt")
    
    starts = selected_data['start_times']
    
    fig_gantt = go.Figure()
    
    for i in range(1, selected_raw['n_total'] + 1):
        s = starts[i]
        dur = selected_raw['durations'][i - 1]
        if dur == 0:
            continue
        is_concrete = i in selected_raw.get('concrete_tasks', [])
        color = '#e74c3c' if is_concrete else '#3498db'
        
        fig_gantt.add_trace(go.Bar(
            x=[dur],
            y=[f"Job {i}"],
            base=s,
            orientation='h',
            marker_color=color,
            name='Béton' if is_concrete else 'Standard',
            showlegend=(i == 1),  # évite doublons dans la légende
            hovertemplate=f"Job {i}<br>Début: {s}<br>Fin: {s+dur}<br>Durée: {dur}<extra></extra>"
        ))
    
    # Zone été si applicable
    if 'climatic' in selected_raw:
        cl = selected_raw['climatic']
        fig_gantt.add_vrect(
            x0=cl['summer_start'], x1=cl['summer_end'],
            fillcolor="orange", opacity=0.2,
            annotation_text="ÉTÉ", annotation_position="top left"
        )
    
    fig_gantt.update_layout(
        title=f"Ordonnancement — {selected}",
        xaxis_title="Jours",
        yaxis=dict(autorange="reversed"),
        barmode='overlay',
        height=max(400, selected_raw['n_total'] * 20)
    )
    st.plotly_chart(fig_gantt, use_container_width=True)
    
    if show_resource and selected_data['start_times']:
        st.markdown("#### 📊 Profil des Ressources")
        
        starts = selected_data['start_times']
        H = selected_raw['H']
        n_res = selected_raw['n_res']
        
        fig_res = make_subplots(rows=n_res, cols=1, 
                                subplot_titles=[f"Ressource {r+1} (cap={selected_raw['caps'][r]})" 
                                               for r in range(n_res)])
        
        for r in range(n_res):
            timeline = [0] * (H + 1)
            for i in range(1, selected_raw['n_total'] + 1):
                s = starts[i]
                e = s + selected_raw['durations'][i-1]
                for t in range(s, e):
                    if t <= H:
                        timeline[t] += selected_raw['demands'][i-1][r]
            
            fig_res.add_trace(
                go.Scatter(x=list(range(H+1)), y=timeline, 
                          fill='tozeroy', name=f'R{r+1}'),
                row=r+1, col=1
            )
            fig_res.add_hline(y=selected_raw['caps'][r], line_dash="dash", 
                             line_color="red", row=r+1, col=1)
        
        fig_res.update_layout(height=200 * n_res, showlegend=False)
        st.plotly_chart(fig_res, use_container_width=True)

# ─── EXPORT ─────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("### 💾 Export")

col_e1, col_e2 = st.columns(2)

with col_e1:
    json_str = json.dumps(results, indent=2, default=str)
    st.download_button(
        label="📥 Télécharger JSON",
        data=json_str,
        file_name="benchmark_results.json",
        mime="application/json"
    )

with col_e2:
    csv_str = df_display.to_csv(index=False)
    st.download_button(
        label="📥 Télécharger CSV",
        data=csv_str,
        file_name="benchmark_results.csv",
        mime="text/csv"
    )

# ─── FOOTER ────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #999; font-size: 0.8rem;">
    Benchmark RCPSP — Généré le 2026-05-16 | Solveur: SGS Sériel + Heuristiques Multi-stratégies
</div>
""", unsafe_allow_html=True)