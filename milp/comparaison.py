import matplotlib.pyplot as plt
import numpy as np

# =========================
# Données
# =========================
cp_data = {
    "j301_1": [54],
    "j3021_1": [100, 99, 98, 97,95],
    "j3029_1": [153, 94, 90],
    "j3045_1": [155, 99]
}

milp_data = {
    "j301_1": 60,
    "j3029_1": 62,
    "j3021_1": 172,
    "j3045_1": 56
}

# =========================
# Plot avec subplots
# =========================
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
axes = axes.flatten()

colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

for idx, (instance, values) in enumerate(cp_data.items()):
    ax = axes[idx]
    iterations = list(range(1, len(values)+1))
    
    # Courbe CP
    ax.plot(iterations, values, marker='o', color=colors[idx], 
            linewidth=2, markersize=8, label=f"CP")
    
    # Ligne MILP sur toute la largeur
    milp_value = milp_data[instance]
    max_iter = max(len(v) for v in cp_data.values())  # 6
    ax.hlines(milp_value, 1, max_iter, colors=colors[idx], 
              linestyles='dashed', alpha=0.7, label=f"MILP = {milp_value}")
    
    # Mise en forme
    ax.set_title(f"Instance {instance}", fontsize=12, fontweight='bold')
    ax.set_xlabel("Itérations")
    ax.set_ylabel("Makespan")
    ax.set_xticks(range(1, max_iter+1))
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    
    # Ajustement échelle Y
    all_values = values + [milp_value]
    margin = (max(all_values) - min(all_values)) * 0.1
    ax.set_ylim(min(all_values) - margin, max(all_values) + margin)

plt.suptitle("Convergence CP vs MILP par instance", fontsize=14, fontweight='bold')
plt.tight_layout()

# ✅ CHEMIN CORRIGÉ pour votre Mac
plt.savefig('convergence_cp_milp.png', dpi=150, bbox_inches='tight')
plt.show()