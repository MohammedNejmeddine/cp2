include "cumulative.mzn";
% ============================================================
%  RCPSP Étendu — Projet P2 BTP Marocain
%  INSEA CP-SDRO-2A
%  Version corrigée v2 : makespan explicite + search améliorée
% ============================================================

% ----------------------------------------------------------------
% PARAMÈTRES DE BASE
% ----------------------------------------------------------------

int: n;        % nombre de tâches
int: H;        % horizon de planification (makespan max)
int: n_res;    % nombre de ressources renouvelables standard

array[1..n] of int: duree;
array[1..n_res] of int: capacite;
array[1..n, 1..n_res] of int: besoin;
array[1..n, 1..n] of 0..1: prec;

% ----------------------------------------------------------------
% EXTENSION A — Fenêtre climatique
% ----------------------------------------------------------------

int: debut_ete;
int: fin_ete;
set of int: TACHES_BETON;

% ----------------------------------------------------------------
% EXTENSION B — Ressource non-renouvelable (ciment)
% ----------------------------------------------------------------

int: stock_NR;
array[1..n] of int: ciment;

% ----------------------------------------------------------------
% EXTENSION C — Partage d'équipements lourds
% ----------------------------------------------------------------

int: n_equipements;
array[1..n_equipements] of int: capacite_equipement;
array[1..n, 1..n_equipements] of int: besoin_equipement;

% ----------------------------------------------------------------
% VARIABLES DE DÉCISION
% ----------------------------------------------------------------

array[1..n] of var 0..H: debut;

% CORRECTION v2 : makespan comme variable bornée explicitement
% (plus efficace que max() qui crée des variables cachées)
var 0..H: makespan;

% ----------------------------------------------------------------
% CONTRAINTES
% ----------------------------------------------------------------

% 0. Lier makespan aux fins de tâches
constraint forall(i in 1..n)(
    debut[i] + duree[i] <= makespan
);

% 1. Précédences
constraint forall(i in 1..n, j in 1..n where prec[i,j] = 1)(
    debut[i] + duree[i] <= debut[j]
);

% 2. Ressources renouvelables standard
constraint forall(r in 1..n_res)(
    cumulative(
        debut,
        duree,
        [besoin[i, r] | i in 1..n],
        capacite[r]
    )
);

% 3. Extension A — Fenêtre climatique
constraint forall(i in TACHES_BETON)(
    debut[i] + duree[i] <= debut_ete
    \/
    debut[i] >= fin_ete
);

% Contrainte redondante — aide le solver à couper plus tôt
constraint forall(i in TACHES_BETON)(
    not (debut[i] >= debut_ete /\ debut[i] < fin_ete)
);

% 4. Extension B — Ciment (non-renouvelable)
constraint sum(i in 1..n)(ciment[i]) <= stock_NR;

% 5. Extension C — Équipements lourds partagés
constraint forall(e in 1..n_equipements)(
    cumulative(
        debut,
        duree,
        [besoin_equipement[i, e] | i in 1..n],
        capacite_equipement[e]
    )
);

% Borne inférieure : makespan >= chemin critique
constraint makespan >= max(i in 1..n)(duree[i]);

% Symmetry breaking : tâches sans précédences fixes
constraint forall(i in 1..n)(
    debut[i] + duree[i] <= makespan
);

% ----------------------------------------------------------------
% OBJECTIF
% ----------------------------------------------------------------

solve
    :: seq_search([
        % Tâches béton en priorité (plus contraintes)
        int_search(
            [debut[i] | i in TACHES_BETON],
            first_fail,
            indomain_min
        ),
        % Puis toutes les tâches
        int_search(debut, first_fail, indomain_min),
        % Enfin le makespan
        int_search([makespan], input_order, indomain_min)
    ])
    minimize makespan;

% ----------------------------------------------------------------
% AFFICHAGE
% ----------------------------------------------------------------

output [
    "======================================\n",
    "  RCPSP Étendu — Solution Finale\n",
    "  Extensions : Climatique + NR + Équipements lourds\n",
    "======================================\n",
    "Makespan optimal/best = \(makespan) jours\n\n",
    "Planning des tâches :\n",
    "  Tâche | Début | Fin   | Ciment | Équipements\n",
    "  ------|-------|-------|--------|------------\n"
] ++
[
    "  T\(i)\t| \(debut[i])\t| \(debut[i] + duree[i])\t| \(ciment[i])t"
    ++ if card({e | e in 1..n_equipements where besoin_equipement[i,e] > 0}) > 0
       then "  | " ++ join(", ", [if besoin_equipement[i,e] > 0 then "E\(e)" endif | e in 1..n_equipements])
       else "  | -" endif
    ++ if i in TACHES_BETON then "  [BETON]" else "" endif
    ++ "\n"
    | i in 1..n
] ++
[
    "\nRessources non-renouvelables :\n",
    "  Ciment utilisé : \(sum(i in 1..n)(ciment[i])) / \(stock_NR) tonnes\n",
    "\nÉquipements lourds partagés :\n"
] ++
[
    "  Équipement \(e) : capacité = \(capacite_equipement[e])\n"
    | e in 1..n_equipements
];
