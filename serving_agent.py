"""
serving_agent.py  ─  ServingAgent 노드 (registry 버전)
"""

import pandas as pd
import registry
from state import MealPlanState

SLOT_CATS = [
    ("밥",   "밥"),
    ("국",   "국"),
    ("주찬", "주찬"),
    ("부찬1","부찬"),
    ("부찬2","부찬"),
    ("김치", "김치"),
]

BASE_SERVING = {"밥": 210, "국": 200, "주찬": 100, "부찬": 70, "김치": 40}

RATIO_BY_DISEASE = {
    "일반형": 1.0, "H형": 0.9,  "D형": 0.95, "K형": 0.85,
    "DH형":  0.9, "HK형": 0.8, "DK형": 0.8, "DHK형": 0.75,
}


def serving_agent(state: MealPlanState) -> dict:
    """
    LangGraph 노드 함수.
    개인별 배식량(g/ml) 및 예상 영양소를 계산합니다.
    """
    print("\n[ServingAgent] 개인별 배식량 산출 시작...")
    print(f"  meal_plan 키: {list((state.get('meal_plan') or {}).keys())[:3]}")
    print(f"  df_menu_records: {state.get('df_menu_records')}")
    print(f"  approved_plan: {type(state.get('approved_plan'))}")

    # ── registry에서 직렬화 불가 객체 꺼내기 ─────────────────
    patients = registry.get(state["patients_key"])
    serving_obj = (
        registry.get(state["serving_agent_key"])
        if state.get("serving_agent_key") and registry.has(state["serving_agent_key"])
        else None
    )

    # ── df_menu: records → DataFrame 복원 ────────────────────
    df = None
    if state.get("df_menu_records"):
        df = pd.DataFrame(state["df_menu_records"], columns=state["df_menu_columns"])

    pool = state.get("pool") or {}

    # pool 빠른 조회 인덱스
    pool_index = {
        (cat, m["menu_name"]): m
        for cat, menus in pool.items()
        for m in menus
    }

    serving_map: dict = {}

    if df is None:
        print("[ServingAgent] df_menu 없음 — 건너뜀")
        return {"serving_map": {}, "messages": ["[ServingAgent] df_menu 없음"]}

    for _, menu_row in df.iterrows():
        day  = menu_row["일차"]
        meal = menu_row["끼니"]

        menu_by_slot = {
            slot: pool_index.get((cat, menu_row.get(slot, "")), {})
            for slot, cat in SLOT_CATS
        }

        for p in patients:
            # 배식 비율 결정
            if serving_obj is not None:
                try:
                    srv   = serving_obj.get_serving(p.name, menu_by_slot)
                    ratio = srv.get("ratio", 1.0)
                except Exception:
                    ratio = _default_ratio(p)
                    srv   = _make_serving(ratio)
            else:
                ratio = _default_ratio(p)
                srv   = _make_serving(ratio)

            # 예상 영양소 (ratio 반영)
            def _sum(key):
                return sum(menu_by_slot[s].get(key, 0) or 0 for s, _ in SLOT_CATS) * ratio

            entry = {
                **srv,
                "ratio":          round(ratio, 2),
                "예상열량":       round(_sum("energy"),  1),
                "예상단백질":     round(_sum("protein"), 1),
                "예상나트륨":     round(_sum("sodium"),  1),
                "예상탄수화물":   round(_sum("carb"),    1),
            }

            # state 직렬화를 위해 key를 list로 저장
            key_str = f"{p.name}||{day}||{meal}"
            serving_map[key_str] = entry

    print(f"[ServingAgent] 완료 — {len(serving_map)}건")
    return {
        "serving_map": serving_map,
        "messages":    [f"[ServingAgent] {len(serving_map)}건 배식량 산출 완료"],
    }


def _default_ratio(patient) -> float:
    label = getattr(patient, "disease_type_label", "일반형")
    return RATIO_BY_DISEASE.get(label, 1.0)


def _make_serving(ratio: float) -> dict:
    return {
        slot: round(BASE_SERVING[cat] * ratio)
        for slot, cat in SLOT_CATS
    }