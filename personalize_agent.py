"""
personalize_agent.py  ─  PersonalizeAgent 노드
================================================
잔반 기반 선호도 점수(preference_weights)를 활용해
개인별 부찬1을 1개 대체합니다.

대체 조건 (이중 필터):
  ① 개인 선호도 점수 < PERSONAL_DISLIKE  (이 사람이 싫어함)
  AND
  ② 시설 전체 기피 Top N 목록에 app포함    (조리팀도 인지 가능한 수준)

이 두 조건을 동시에 만족할 때만 대체 → 운영 가능한 가짓수 유지
"""

import pandas as pd
import registry
from state import MealPlanState
from preference_update_agent import FACILITY_DISLIKE_THRESHOLD


#PERSONAL_DISLIKE  = 0.4   # 개인 선호도 점수 임계값 (이하면 기피)
PERSONAL_DISLIKE  = 0.6   # 개인 선호도 점수 임계값 (이하면 기피)
FACILITY_DISLIKE = FACILITY_DISLIKE_THRESHOLD   # 시설 평균 점수 임계값 (이하면 기피 메뉴 후보)
# FACILITY_DISLIKE  = 0.5   # 시설 평균 점수 임계값 (이하면 기피 메뉴 후보)
MAX_DISLIKE_MENUS = 5     # 운영 가능한 최대 기피 메뉴 가짓수
ALT_MIN_SCORE     = 0.5   # 대체 메뉴 최소 선호도 점수

SLOTS = ["밥", "국", "주찬", "부찬1", "부찬2", "김치"]


def personalize_agent(state: MealPlanState) -> dict:
    print("\n[PersonalizeAgent] 개인화 부찬 대체 시작...")

    # ── 사전 조건 확인 ────────────────────────────────────────
    weights    = state.get("preference_weights") or {}
    pool       = state.get("pool") or {}
    df_records = state.get("df_menu_records")
    patients   = registry.get(state["patients_key"]) if state.get("patients_key") else []

    if not df_records or not weights or not pool:
        print("  [PersonalizeAgent] preference_weights 또는 df_menu 없음 — 건너뜀")
        return {
            "personal_menus": {},
            "messages": ["[PersonalizeAgent] 선호도 데이터 없음 — 건너뜀"],
        }

    df = pd.DataFrame(df_records, columns=state["df_menu_columns"])

    # ── Step 1: 시설 전체 메뉴 평균 점수 계산 ────────────────
    menu_avg: dict = {}
    for name, prefs in weights.items():
        for menu, score in prefs.items():
            menu_avg.setdefault(menu, []).append(score)
    menu_avg = {m: round(sum(s) / len(s), 3) for m, s in menu_avg.items()}

    # ── Step 2: 시설 기피 메뉴 Top N 추출 ───────────────────
    dislike_candidates = sorted(
        [(m, s) for m, s in menu_avg.items() if s < FACILITY_DISLIKE],
        key=lambda x: x[1],
    )[:MAX_DISLIKE_MENUS]

    dislike_set = {m for m, _ in dislike_candidates}

    print(f"  [시설 기피 메뉴 Top{MAX_DISLIKE_MENUS}]")
    for m, s in dislike_candidates:
        print(f"    {m}: {s:.3f}")

    if not dislike_set:
        print("  [PersonalizeAgent] 시설 기피 메뉴 없음 — 대체 없음")
        return {
            "personal_menus": {},
            "messages": ["[PersonalizeAgent] 기피 메뉴 없음"],
        }

    # ── Step 3: 부찬 대체 후보 풀 준비 (선호도 높은 순 정렬) ──
    alt_pool = sorted(
        pool.get("부찬", []),
        key=lambda m: menu_avg.get(m["menu_name"], 0.7),
        reverse=True,
    )

    # ── Step 4: 개인별 부찬1 대체 (이중 필터) ────────────────
    personal_menus: dict = {}
    replace_log: dict = {}   # {name: [(day, meal, 기존메뉴, 대체메뉴)]}

    for p in patients:
        pref = weights.get(p.name, {})

        alt_candidates = sorted(
            pool.get("부찬", []),
            key=lambda m: pref.get(m["menu_name"], 0.7),
            reverse=True,
        )

        for _, row in df.iterrows():
            override = {}

            # 부찬1, 부찬2 모두 체크 (기피 메뉴가 어느 슬롯에 있든 대체)
            for slot in ["부찬1", "부찬2"]:
                menu  = row.get(slot, "")
                score = pref.get(menu, 0.7)

                # 이중 필터: 개인 기피 AND 시설 기피 목록
                if score >= PERSONAL_DISLIKE:
                    continue
                if menu not in dislike_set:
                    continue

                # 현재 끼니에 없는 메뉴 중 선호도 높은 것 선택
                current_menus = set(
                    row[s] for s in ["밥", "국", "주찬", "부찬1", "부찬2", "김치"]
                    if row.get(s)
                )
                alt = next(
                    (m["menu_name"] for m in alt_candidates
                    if m["menu_name"] not in current_menus
                    and pref.get(m["menu_name"], 0.7) >= ALT_MIN_SCORE),
                    None,
                )
                if alt:
                    override[slot] = alt   # 기피 슬롯(부찬1 또는 부찬2)에 대체 적용
                    break  # 1개 슬롯만 대체

            if override:
                key = f"{p.name}||{row['일차']}||{row['끼니']}"
                personal_menus[key] = override
                if p.name not in replace_log:
                    replace_log[p.name] = []
                replace_log[p.name].append(
                    (row["일차"], row["끼니"],
                    list(override.keys())[0],          # 슬롯명
                    row.get(list(override.keys())[0]), # 기존 메뉴
                    list(override.values())[0])         # 대체 메뉴
                )

    # ── 결과 출력 ─────────────────────────────────────────────
    if replace_log:
        print(f"\n  [개인별 대체 현황]")
        for name, logs in replace_log.items():
            print(f"  [{name}] {len(logs)}끼 대체")
            for day, meal, slot, old, new in logs[:3]:   # ← 이 줄
                print(f"    {day} {meal} [{slot}]: {old} → {new}")
            if len(logs) > 3:
                print(f"    ... 외 {len(logs)-3}건")
    else:
        print("  [PersonalizeAgent] 대체 대상 없음")

    print(f"\n[PersonalizeAgent] 완료 — {len(personal_menus)}건 개인화 적용")
    return {
        "personal_menus": personal_menus,
        "messages": [f"[PersonalizeAgent] {len(personal_menus)}건 개인화 적용"],
    }