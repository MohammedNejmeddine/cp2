include "cumulative.mzn";

% ... (garder tous tes paramètres identiques) ...

% ----------------------------------------------------------------
% VARIABLES DE DÉCISION
% ----------------------------------------------------------------

array[1..n] of var 0..H: debut;

% AJOUT : makespan comme variable bornée explicitement
var 0..H: makespan;

% ----------------------------------------------------------------
% CONTRAINTES
% ----------------------------------------------------------------

% 0. Lier makespan aux fins de tâches (plus efficace que max())
constraint forall(i in 1..n)(
    debut[i] + duree[i] <= makespan
);

% 1. Précédence
constraint forall(i in 1..n, j in 1..n where prec[i,j] = 1)(
    debut[i] + duree[i] <= debut[j]
);

% 2. Ressources renouvelables
constraint forall(r in 1..n_res)(
    cumulative(debut, duree, [besoin[i,r] | i in 1..n], capacite[r])
);

% 3. Fenêtre climatique — AJOUT de contrainte redondante pour aider le solver
constraint forall(i in TACHES_BETON)(
    debut[i] + duree[i] <= debut_ete
    \/
    debut[i] >= fin_ete
);

% AJOUT : contrainte redondante — tâches béton ne peuvent pas COMMENCER en été
constraint forall(i in TACHES_BETON)(
    not (debut[i] >= debut_ete /\ debut[i] < fin_ete)
);

% 4. Ciment (non-renouvelable)
constraint sum(i in 1..n)(ciment[i]) <= stock_NR;

% 5. Équipements lourds
constraint forall(e in 1..n_equipements)(
    cumulative(debut, duree, [besoin_equipement[i,e] | i in 1..n], capacite_equipement[e])
);

% ----------------------------------------------------------------
% OBJECTIF
% ----------------------------------------------------------------

solve
    :: seq_search([
        % D'abord fixer les tâches béton (les plus contraintes)
        int_search(
            [debut[i] | i in TACHES_BETON],
            first_fail,
            indomain_min
        ),
        % Ensuite les autres tâches
        int_search(debut, first_fail, indomain_min),
        % Enfin le makespan
        int_search([makespan], input_order, indomain_min)
    ])
    minimize makespan;
