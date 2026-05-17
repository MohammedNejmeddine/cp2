import matplotlib.pyplot as plt
import numpy as np

# =========================
# Données
# =========================
cp_data = {
    "j30_17": [61,57,53,50,49,46,43],
    "j30_37": [95,92,91,90,89,87,86,85,84],
    "j30_21": [100,99,98,97,95,94,93,92,90,89,88,87,86,85],
    "j30_45": [96,93,89,88,87,86,85,84,83,82],
}

# =========================
# Plot - Makespan CP uniquement
# =========================
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
axes = axes.flatten()

colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

for idx, (instance, values) in enumerate(cp_data.items()):
    ax = axes[idx]
    iterations = list(range(1, len(values)+1))
    
    # Courbe CP uniquement
    ax.plot(iterations, values, marker='o', color=colors[idx], 
            linewidth=2, markersize=8, label=f"CP")
    
    # Mise en forme
    ax.set_title(f"Instance {instance}", fontsize=12, fontweight='bold')
    ax.set_xlabel("Itérations")
    ax.set_ylabel("Makespan")
    ax.set_xticks(iterations)
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    
    # Ajustement échelle Y
    margin = (max(values) - min(values)) * 0.15 if len(values) > 1 else max(values)*0.1
    ax.set_ylim(min(values) - margin, max(values) + margin)
    
    # Annotation valeur finale
    final_value = values[-1]
    ax.annotate(f'{final_value}', 
                xy=(len(values), final_value),
                xytext=(len(values), final_value + margin*0.3),
                ha='center', fontsize=10, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=colors[idx], lw=1.5))

plt.suptitle("Évolution du makespan (CP uniquement)", fontsize=14, fontweight='bold')
plt.tight_layout()


plt.savefig('cp_makespan_only.png', dpi=150, bbox_inches='tight')
plt.show()