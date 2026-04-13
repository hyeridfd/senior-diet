"""
candidate_agent.py  ─  CandidateAgent 노드
==========================================
Neo4j Graph-RAG 기반으로 질환별 후보 메뉴 풀을 생성합니다.
기존 get_candidates_by_category() 로직을 LangGraph 노드로 래핑합니다.
"""

import os
from langchain_neo4j import Neo4jGraph
from state import MealPlanState
from preference_update_agent import load_pool_scores


CYPHER_QUERY = """
    CALL () {
        WITH $diseases AS ds
        MATCH (d:Disease) WHERE d.name IN ds
        OPTIONAL MATCH (d)-[:FORBIDDEN_INGREDIENT]->(fi:Recipe)
        OPTIONAL MATCH (d)-[:RECOMMENDED_INGREDIENT]->(ri:Recipe)
        RETURN collect(DISTINCT elementId(fi)) AS forbidden_ids,
               collect(DISTINCT elementId(ri)) AS recommended_ids
    }
    MATCH (f:Food)-[:CATEGORY_IS]->(mc:Meal_Category)
    WHERE (
        NONE(r IN [(f)-[:HAS_INGREDIENT]->(recipe)|recipe]
             WHERE elementId(r) IN forbidden_ids)
        AND ANY(r IN [(f)-[:HAS_INGREDIENT]->(recipe)|recipe]
            WHERE elementId(r) IN recommended_ids)
    ) OR f.title IN ['쌀밥','배추김치']
    MATCH (f)-[hi:HAS_INGREDIENT]->(r:Recipe)-[:CONTAINS]->(n:Nutrition)
    WITH f, mc, r, hi,
        toFloat(coalesce(n.energy_kcal,0))       *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_energy,
        toFloat(coalesce(n.protein_g,0))         *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_protein,
        toFloat(coalesce(n.fat_g,0))             *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_fat,
        toFloat(coalesce(n.sugar_g,0))           *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_sugar,
        toFloat(coalesce(n.fiber_g,0))           *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_fiber,
        toFloat(coalesce(n.sodium_mg,0))         *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_sodium,
        toFloat(coalesce(n.carbo_g,0))           *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_carbo,
        toFloat(coalesce(n.saturated_fat_g,0))   *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_saturated_fat,
        toFloat(coalesce(n.potassium_mg,0))      *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_potassium,
        toFloat(coalesce(n.vitD_ug,0))           *toFloat(coalesce(hi.nutri_weight,0))/100 AS r_vitD,
        hi.nutri_weight AS nutri_w
    OPTIONAL MATCH (r)-[:MAPPED_TO]->(p:Product)
    WITH f, mc, r, r_energy, r_protein, r_fat, r_sugar, r_fiber,
         r_sodium, r_carbo, r_saturated_fat, r_potassium, r_vitD, nutri_w,
         p ORDER BY p.price_today ASC
    WITH f, mc, r, r_energy, r_protein, r_fat, r_sugar, r_fiber,
         r_sodium, r_carbo, r_saturated_fat, r_potassium, r_vitD, nutri_w,
         head(collect(p)) AS cheapest_p
    WITH f, mc, r, r_energy, r_protein, r_fat, r_sugar, r_fiber,
         r_sodium, r_carbo, r_saturated_fat, r_potassium, r_vitD, nutri_w,
         CASE WHEN cheapest_p IS NOT NULL
              THEN toFloat(cheapest_p.price_today)/toFloat(coalesce(cheapest_p.unit_g,1))
              ELSE 0.0 END AS unit_price
    WITH f, mc,
         sum(r_energy) AS total_energy, sum(r_protein) AS total_protein,
         sum(r_fat) AS total_fat,       sum(r_sugar) AS total_sugar,
         sum(r_fiber) AS total_fiber,   sum(r_sodium) AS total_sodium,
         sum(r_carbo) AS total_carbo,   sum(r_saturated_fat) AS total_saturated_fat,
         sum(r_potassium) AS total_potassium, sum(r_vitD) AS total_vitD,
         sum(unit_price * nutri_w) AS total_cost, sum(nutri_w) AS total_weight
    RETURN mc.name AS category, f.title AS menu_name,
           round(total_energy,2) AS energy,       round(total_protein,2) AS protein,
           round(total_fat,2) AS fat,             round(total_sugar,2) AS sugar,
           round(total_fiber,2) AS fiber,         round(total_sodium,2) AS sodium,
           round(total_carbo,2) AS carb,          round(total_saturated_fat,2) AS sat_fat,
           round(total_potassium,2) AS potassium, round(total_vitD,2) AS vit_d,
           round(total_cost,0) AS cost,           round(total_weight,1) AS weight
    ORDER BY mc.name, total_energy ASC
"""


def candidate_agent(state: MealPlanState) -> dict:
    print("\n[CandidateAgent] 후보 메뉴 조회 시작...")

    graph = Neo4jGraph(
        url=os.getenv("NEO4J_URI"),
        username=os.getenv("NEO4J_USERNAME"),
        password=os.getenv("NEO4J_PASSWORD"),
        database="senior-diet-new",
    )

    results = graph.query(
        CYPHER_QUERY,
        params={"diseases": state["diseases"]}
    )

    pool: dict = {"밥": [], "국": [], "주찬": [], "부찬": [], "김치": []}

    # ① 먼저 결과를 pool에 채우기
    for row in results:
        cat = row["category"]
        if cat in pool:
            pool[cat].append(dict(row))

    # ② 카테고리별 메뉴 수 검증
    for cat, menus in pool.items():
        if len(menus) == 0:
            raise ValueError(
                f"[CandidateAgent] '{cat}' 카테고리 후보 메뉴가 0개입니다. "
                f"질환 목록({state['diseases']})과 Neo4j 데이터를 확인하세요."
            )

    # ③ 그 다음 저장된 선호도 점수 적용 (← 여기로 이동)
    saved_scores = load_pool_scores()
    if saved_scores:
        for cat, menus in pool.items():
            for m in menus:
                if m["menu_name"] in saved_scores:
                    m["preference_score"] = saved_scores[m["menu_name"]]
        print(f"  [CandidateAgent] 저장된 선호도 점수 {len(saved_scores)}건 적용")

    summary = {cat: len(m) for cat, m in pool.items()}
    print(f"[CandidateAgent] 완료: {summary}")

    return {
        "pool": pool,
        "messages": [f"[CandidateAgent] 후보 풀 생성 완료 {summary}"],
    }