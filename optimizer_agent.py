"""
optimizer_agent.py  ─  OptimizerAgent 노드 (registry 버전)
"""

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination
from pymoo.core.problem import Problem

import registry
from state import MealPlanState

DAILY_SLOTS = [
    ("아침_밥","밥"),  ("아침_국","국"),    ("아침_주찬","주찬"),
    ("아침_부찬1","부찬"),("아침_부찬2","부찬"),("아침_김치","김치"),
    ("점심_밥","밥"),  ("점심_국","국"),    ("점심_주찬","주찬"),
    ("점심_부찬1","부찬"),("점심_부찬2","부찬"),("점심_김치","김치"),
    ("저녁_밥","밥"),  ("저녁_국","국"),    ("저녁_주찬","주찬"),
    ("저녁_부찬1","부찬"),("저녁_부찬2","부찬"),("저녁_김치","김치"),
]
N_DAYS   = 28
N_SLOTS  = len(DAILY_SLOTS)
MEAL_SETS = {
    "아침": [0,1,2,3,4,5],
    "점심": [6,7,8,9,10,11],
    "저녁": [12,13,14,15,16,17],
}
WHITELIST = ["쌀밥", "배추김치"]


class MealPlanProblem(Problem):
    def __init__(self, pool, constraint, budget_per_meal):
        self.pool       = pool
        self.constraint = constraint
        self.budget     = budget_per_meal * N_DAYS * 3
        self.slot_sizes = [len(pool[cat]) for _, cat in DAILY_SLOTS]
        super().__init__(
            n_var=N_DAYS * N_SLOTS, n_obj=5,
            xl=np.zeros(N_DAYS * N_SLOTS, dtype=int),
            xu=np.array([s-1 for s in self.slot_sizes] * N_DAYS, dtype=int),
            vtype=int,
        )

    def _get_menu(self, day, slot, idx):
        _, cat = DAILY_SLOTS[slot]
        return self.pool[cat][int(idx) % len(self.pool[cat])]

    def _evaluate(self, X, out, *args, **kwargs):
        out["F"] = np.array([self._eval_one(c) for c in X])

    def _eval_one(self, chrom):
        all_menus = [self._get_menu(d, s, chrom[d*N_SLOTS+s])
                     for d in range(N_DAYS) for s in range(N_SLOTS)]
        return [
            self._nutrition_violation(all_menus),
            max(0.0, sum(m["cost"] for m in all_menus) - self.budget) / self.budget,
            # individual
            -self._preference_weighted_diversity(all_menus),
            #-self._simpson_diversity(all_menus),
            self._same_side_dish_penalty(chrom),
            self._carry_over_penalty(all_menus),
        ]

    def _nutrition_violation(self, menus):
        c = self.constraint
        v = 0.0
        for day in range(N_DAYS):
            daily = {k: 0.0 for k in
                ["energy","carb","sugar","fat","sodium","sat_fat","potassium","fiber","vit_d"]}
            base = day * N_SLOTS
            day_menus = menus[base:base+N_SLOTS]
            for _, slots in MEAL_SETS.items():
                mm = [day_menus[s] for s in slots]
                mn = {
                    "energy":    sum(m["energy"]    for m in mm),
                    "sugar":     sum(m["sugar"]     for m in mm),
                    "protein":   sum(m["protein"]   for m in mm),
                    "fat":       sum(m["fat"]        for m in mm),
                    "sat_fat":   sum(m["sat_fat"]   for m in mm),
                    "sodium":    sum(m["sodium"]    for m in mm),
                    "potassium": sum(m["potassium"] for m in mm),
                    "fiber":     sum(m["fiber"]     for m in mm),
                    "carb":      sum(m["carb"]       for m in mm),
                }
                for k, val in mn.items():
                    lo = getattr(c, f"{k}_min", None)
                    hi = getattr(c, f"{k}_max", None)
                    if lo and val < lo: v += (lo - val) / lo
                    if hi and val > hi: v += (val - hi) / hi
                for k in daily:
                    daily[k] += sum(m.get(k, 0.0) for m in mm)
            for k, val in daily.items():
                lo = getattr(c, f"daily_{k}_min", None)
                hi = getattr(c, f"daily_{k}_max", None)
                if lo and val < lo: v += (lo - val) / lo
                if hi and val > hi: v += (val - hi) / hi
        return v / (N_DAYS * 3)

    def _simpson_diversity(self, menus):
        names = [m["menu_name"] for m in menus]
        N = len(names)
        counts: dict = {}
        for n in names: counts[n] = counts.get(n, 0) + 1
        M = len(counts)
        if M <= 1: return 0.0
        return (1 - sum((c/N)**2 for c in counts.values())) / (1 - 1/M) * 100

    def _preference_weighted_diversity(self, menus):
        # 기존 simpson diversity + preference_score 혼합
        diversity = self._simpson_diversity(menus)
        pref_avg  = sum(m.get("preference_score", 0.7) for m in menus) / len(menus)
        return diversity * 0.7 + pref_avg * 100 * 0.3  # 가중 합산

    def _same_side_dish_penalty(self, chrom):
        penalty = 0
        for day in range(N_DAYS):
            base = day * N_SLOTS
            for s1, s2 in [(3,4),(9,10),(15,16)]:
                if int(chrom[base+s1]) == int(chrom[base+s2]):
                    penalty += 1
        return penalty / (N_DAYS * 3)

    def _carry_over_penalty(self, menus, look_back=1):
        penalty = total = 0
        for day in range(1, N_DAYS):
            cur  = [m["menu_name"] for m in menus[day*N_SLOTS:(day+1)*N_SLOTS]]
            past = [m["menu_name"] for m in
                    menus[max(0,day-look_back)*N_SLOTS:day*N_SLOTS]]
            for name in cur:
                if name in WHITELIST: continue
                if name in past: penalty += 1
                total += 1
        return penalty / total if total else 0.0


def optimizer_agent(state: MealPlanState) -> dict:
    # ── registry에서 직렬화 불가 객체 꺼내기 ─────────────────
    constraint = registry.get(state["constraint_key"])

    count    = state.get("violation_count", 0)
    pop_size = 500 + count * 100
    n_gen    = 300 + count * 50

    print(f"\n[OptimizerAgent] 최적화 시작 (시도 #{count+1} | pop={pop_size} | gen={n_gen})")

    problem   = MealPlanProblem(state["pool"], constraint, state["budget_per_meal"])
    algorithm = NSGA2(pop_size=pop_size, eliminate_duplicates=True)
    result    = minimize(problem, algorithm,
                         termination=get_termination("n_gen", n_gen),
                         seed=42, verbose=True)

    f1_min = result.F[:, 0].min()
    print(f"[OptimizerAgent] 완료 — Pareto {len(result.X)}개 | f1={f1_min:.4f}")

    # ── pymoo Result도 registry에 저장 ───────────────────────
    result_key = f"nsga_result_{count}"
    registry.put(result_key, result)

    return {
        "nsga_result_key": result_key,   # state에는 키만
        "violation_count": count,
        "messages": [f"[OptimizerAgent] 시도 #{count+1} | f1={f1_min:.4f}"],
    }


def get_menu(pool: dict, slot_idx: int, chrom_val: int) -> dict:
    _, cat = DAILY_SLOTS[slot_idx]
    return pool[cat][int(chrom_val) % len(pool[cat])]