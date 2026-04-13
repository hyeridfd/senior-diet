"""
app.py  ─  MENTOR Streamlit 웹 애플리케이션
============================================
노인요양시설 맞춤형 식단 설계 시스템
"""

import os
import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(
    page_title="MENTOR",
    page_icon="🍱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 스타일 ────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

[data-testid="stSidebar"] {
    background: #1F3B6E;
}
[data-testid="stSidebar"] * { color: white !important; }
[data-testid="stSidebar"] .stRadio label { color: white !important; }

.mentor-title {
    font-size: 2rem; font-weight: 700; color: #1F3B6E;
    border-left: 6px solid #2E5A9C; padding-left: 16px;
    margin-bottom: 8px;
}
.mentor-sub {
    color: #666; font-size: 0.9rem; margin-bottom: 24px;
    padding-left: 22px;
}
.stat-card {
    background: white; border: 1px solid #E0E8F0;
    border-radius: 10px; padding: 20px 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    text-align: center;
}
.stat-num { font-size: 2rem; font-weight: 700; color: #1F3B6E; }
.stat-label { font-size: 0.85rem; color: #888; margin-top: 4px; }
.log-box {
    background: #0d1117; color: #58a6ff;
    font-family: monospace; font-size: 0.82rem;
    padding: 16px; border-radius: 8px;
    height: 280px; overflow-y: auto;
    border: 1px solid #30363d;
}
.status-ok   { color: #2E7D52; font-weight: 600; }
.status-warn { color: #B85042; font-weight: 600; }
.badge-approve    { background:#2E7D52; color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem; }
.badge-reoptimize { background:#E07B39; color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem; }
.badge-revise     { background:#2E5A9C; color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem; }
</style>
""", unsafe_allow_html=True)

# ── 세션 상태 초기화 ──────────────────────────────────────────
def init_session():
    defaults = {
        "page":             "파이프라인 실행",
        "pipeline_done":    False,
        "hitl_waiting":     False,
        "pipeline_config":  None,
        "log_messages":     [],
        "df_menu":          None,
        "violation_rate":   None,
        "report_paths":     {},
        "waste_log":        [],
        "preference_weights": {},
        "lang_app":         None,
        "initial_state":    None,
        "facility_loaded":  False,
        "fac":              None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ── 사이드바 ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🍱 MENTOR")
    st.markdown("노인요양시설 맞춤형 식단 설계")
    st.divider()

    pages = [
        "파이프라인 실행",
        "영양사 검토 (HITL)",
        "결과 다운로드",
        "잔반 입력",
        "선호도 현황",
    ]
    icons = ["⚙️", "👨‍⚕️", "📥", "🍽️", "📊"]

    page = st.radio(
        "메뉴",
        pages,
        format_func=lambda x: f"{icons[pages.index(x)]}  {x}",
        index=pages.index(st.session_state["page"]),
        key="nav_radio",
    )
    st.session_state["page"] = page

    st.divider()
    st.markdown("**시스템 상태**")
    if st.session_state["facility_loaded"]:
        st.success("✅ 시설 데이터 로드됨")
    else:
        st.warning("⚠️ 시설 데이터 미로드")
    if st.session_state["pipeline_done"]:
        st.success("✅ 파이프라인 완료")
    if st.session_state["hitl_waiting"]:
        st.error("🔴 영양사 검토 대기 중")


# ══════════════════════════════════════════════════════════════
# 페이지 1 — 파이프라인 실행
# ══════════════════════════════════════════════════════════════
if page == "파이프라인 실행":
    st.markdown('<div class="mentor-title">파이프라인 실행</div>', unsafe_allow_html=True)
    st.markdown('<div class="mentor-sub">시설 데이터를 로드하고 NSGA-II 최적화 파이프라인을 실행합니다</div>', unsafe_allow_html=True)

    # ── 시설 설정 ────────────────────────────────────────────
    with st.expander("⚙️ 시설 설정", expanded=not st.session_state["facility_loaded"]):
        col1, col2 = st.columns(2)
        with col1:
            # 수정 — 파일 업로더
            uploaded_excel = st.file_uploader(
                "입소자 데이터 (Excel)",
                type=["xlsx"],
                help="고령자.xlsx 파일을 업로드하세요"
            )
            
            # 업로드된 파일을 임시 저장
            if uploaded_excel:
                os.makedirs("./data", exist_ok=True)
                excel_path = "./data/고령자_uploaded.xlsx"
                with open(excel_path, "wb") as f:
                    f.write(uploaded_excel.read())
            else:
                excel_path = None
            budget = st.number_input("끼니당 예산 (원)", value=10000, step=500)
        with col2:
            neo4j_uri  = st.text_input("Neo4j URI",      value=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
            neo4j_user = st.text_input("Neo4j 사용자",   value=os.getenv("NEO4J_USERNAME", "neo4j"))
            neo4j_pw   = st.text_input("Neo4j 비밀번호", value=os.getenv("NEO4J_PASSWORD", ""), type="password")

        if st.button("📂 시설 데이터 로드", type="primary"):
            with st.spinner("데이터 로드 중..."):
                try:
                    os.environ["NEO4J_URI"]      = neo4j_uri
                    os.environ["NEO4J_USERNAME"]  = neo4j_user
                    os.environ["NEO4J_PASSWORD"]  = neo4j_pw

                    from facility_optimization import setup_facility
                    fac = setup_facility(excel_path, budget_per_meal=budget)
                    st.session_state["fac"]             = fac
                    st.session_state["facility_loaded"] = True
                    st.session_state["budget"]          = budget
                    st.success(f"✅ 입소자 {len(fac['patients'])}명 로드 완료")

                    # 질환 분포 표시
                    from collections import Counter
                    type_cnt = Counter(p.disease_type_label for p in fac["patients"])
                    cols = st.columns(len(type_cnt))
                    for i, (t, n) in enumerate(sorted(type_cnt.items(), key=lambda x: -x[1])):
                        with cols[i]:
                            st.markdown(f"""
                            <div class="stat-card">
                                <div class="stat-num">{n}</div>
                                <div class="stat-label">{t}</div>
                            </div>""", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ 로드 실패: {e}")

    # ── 파이프라인 실행 ─────────────────────────────────────
    st.divider()
    st.subheader("🚀 파이프라인 실행")

    col_l, col_r = st.columns([1, 2])

    with col_l:
        pop_override = st.slider("NSGA-II pop_size", 100, 1000, 500, 100)
        gen_override = st.slider("NSGA-II n_gen",    50,  500,  300, 50)
        st.caption(f"예상 소요시간: 약 {gen_override//50 * 2}~{gen_override//50 * 4}분")

        run_btn = st.button(
            "▶ 파이프라인 시작",
            type="primary",
            disabled=not st.session_state["facility_loaded"],
            use_container_width=True,
        )

    with col_r:
        log_area = st.empty()

    if run_btn:
        if not st.session_state["facility_loaded"]:
            st.error("먼저 시설 데이터를 로드해 주세요.")
        else:
            st.session_state["log_messages"] = []
            st.session_state["pipeline_done"]  = False
            st.session_state["hitl_waiting"]   = False

            try:
                import registry
                from graph import build_graph
                from preference_update_agent import load_weights

                fac = st.session_state["fac"]

                registry.put("patients",      fac["patients"])
                registry.put("constraint",    fac["constraint"])
                registry.put("serving_agent", fac["serving"])

                prev_weights = load_weights()

                initial_state = {
                    "diseases":          fac["diseases"],
                    "patients_key":      "patients",
                    "constraint_key":    "constraint",
                    "serving_agent_key": "serving_agent",
                    "budget_per_meal":   st.session_state.get("budget", 10000),
                    "pool":              None,
                    "nsga_result_key":   None,
                    "violation_count":   0,
                    "df_menu_records":   None,
                    "df_menu_columns":   None,
                    "recommend_map":     None,
                    "violation_rate":    0.0,
                    "validator_msg":     "",
                    "hitl_action":       None,
                    "hitl_changes":      None,
                    "serving_map":       None,
                    "waste_log":         st.session_state.get("waste_log") or None,
                    "nutrition_history": None,
                    "alert_queue":       None,
                    "report_paths":      None,
                    "orchestrator_phase": "optimize",
                    "next_agent":         None,
                    "preference_weights": prev_weights,
                    "personal_menus":     None,
                    "messages":           [],
                }

                lang_app = build_graph()
                config   = {"configurable": {"thread_id": "mentor-run-001"}}

                st.session_state["lang_app"]      = lang_app
                st.session_state["pipeline_config"] = config
                st.session_state["initial_state"] = initial_state

                logs = []
                progress = st.progress(0, text="파이프라인 시작...")

                steps = {
                    "candidate": (10, "후보 메뉴 생성 중..."),
                    "optimizer":  (30, "NSGA-II 최적화 중..."),
                    "validator":  (50, "검증 중..."),
                    "meal_plan":  (65, "식단표 생성 중..."),
                    "hitl":       (70, "⏸ 영양사 검토 대기"),
                }

                for event in lang_app.stream(initial_state, config=config):
                    if "__interrupt__" in event:
                        st.session_state["hitl_waiting"] = True
                        logs.append("⏸ [HITL] 영양사 검토 대기 중...")
                        log_area.markdown(
                            '<div class="log-box">' +
                            "<br>".join(logs[-20:]) +
                            '</div>', unsafe_allow_html=True
                        )
                        progress.progress(70, text="⏸ 영양사 검토 필요")

                        # df_menu 저장
                        try:
                            snap = lang_app.get_state(config)
                            sv   = snap.values
                            if sv.get("df_menu_records"):
                                st.session_state["df_menu"] = pd.DataFrame(
                                    sv["df_menu_records"],
                                    columns=sv["df_menu_columns"]
                                )
                                st.session_state["violation_rate"] = sv.get("violation_rate", 0)
                        except Exception:
                            pass

                        st.session_state["page"] = "영양사 검토 (HITL)"
                        st.rerun()
                        break

                    node = list(event.keys())[0]
                    output = event.get(node, {})
                    if isinstance(output, dict):
                        for m in output.get("messages", []):
                            logs.append(f"[{node}] {m}")

                    pct, txt = steps.get(node, (None, None))
                    if pct:
                        progress.progress(pct, text=txt)

                    log_area.markdown(
                        '<div class="log-box">' +
                        "<br>".join(logs[-20:]) +
                        '</div>', unsafe_allow_html=True
                    )
                    st.session_state["log_messages"] = logs

                if not st.session_state["hitl_waiting"]:
                    progress.progress(100, text="✅ 완료")
                    st.session_state["pipeline_done"] = True
                    st.success("파이프라인 완료! 결과 다운로드 페이지로 이동하세요.")

            except Exception as e:
                st.error(f"❌ 오류 발생: {e}")
                import traceback
                st.code(traceback.format_exc())

    # 로그 표시 (실행 후)
    if st.session_state["log_messages"] and not run_btn:
        st.markdown("**최근 실행 로그**")
        st.markdown(
            '<div class="log-box">' +
            "<br>".join(st.session_state["log_messages"][-20:]) +
            '</div>', unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════════════════
# 페이지 2 — 영양사 검토 (HITL)
# ══════════════════════════════════════════════════════════════
elif page == "영양사 검토 (HITL)":
    st.markdown('<div class="mentor-title">영양사 검토</div>', unsafe_allow_html=True)
    st.markdown('<div class="mentor-sub">NSGA-II 최적화 결과를 검토하고 승인 여부를 결정합니다</div>', unsafe_allow_html=True)

    if not st.session_state["hitl_waiting"]:
        if st.session_state["pipeline_done"]:
            st.info("파이프라인이 이미 완료되었습니다.")
        else:
            st.warning("먼저 파이프라인을 실행해 주세요.")
    else:
        # 위반율 표시
        vr = st.session_state.get("violation_rate", 0)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""<div class="stat-card">
                <div class="stat-num" style="color:{'#2E7D52' if vr<=1 else '#B85042'}">{vr:.4f}</div>
                <div class="stat-label">영양 위반율 (f1)</div>
            </div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""<div class="stat-card">
                <div class="stat-num">{'통과' if vr<=1 else '주의'}</div>
                <div class="stat-label">기준값 1.0</div>
            </div>""", unsafe_allow_html=True)
        with col3:
            st.markdown(f"""<div class="stat-card">
                <div class="stat-num">28일</div>
                <div class="stat-label">식단 기간</div>
            </div>""", unsafe_allow_html=True)

        st.divider()

        # 식단표 미리보기
        df = st.session_state.get("df_menu")
        if df is not None:
            st.subheader("📋 28일 식단표 미리보기")

            days = sorted(df["일차"].unique(), key=lambda x: int(x.replace("일","")))
            sel_day = st.select_slider("일차 선택", options=days)
            filtered = df[df["일차"] == sel_day][["끼니","밥","국","주찬","부찬1","부찬2","김치","열량(kcal)","나트륨(mg)"]]
            st.dataframe(filtered, use_container_width=True, hide_index=True)

        st.divider()

        # 결정 폼
        st.subheader("✅ 영양사 결정")

        action = st.radio(
            "결정을 선택하세요",
            ["approve", "revise", "reoptimize"],
            format_func=lambda x: {
                "approve":    "✅ approve — 현재 식단표 승인",
                "revise":     "✏️ revise — 특정 메뉴 직접 수정",
                "reoptimize": "🔄 reoptimize — NSGA-II 재최적화 요청",
            }[x],
            horizontal=True,
        )

        changes = {}
        if action == "revise":
            st.info("수정 형식: `일차_끼니_슬롯` = `메뉴명`  예) `1일_점심_주찬` = `코다리조림`")
            n_changes = st.number_input("수정할 메뉴 수", 1, 10, 1)
            for i in range(n_changes):
                c1, c2 = st.columns(2)
                with c1:
                    k = st.text_input(f"키 {i+1}", placeholder="1일_점심_주찬", key=f"chg_k_{i}")
                with c2:
                    v = st.text_input(f"메뉴명 {i+1}", placeholder="코다리조림", key=f"chg_v_{i}")
                if k and v:
                    changes[k] = v

        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            confirm = st.button("결정 제출", type="primary", use_container_width=True)

        if confirm:
            with st.spinner("파이프라인 재개 중..."):
                try:
                    from langgraph.types import Command

                    lang_app = st.session_state["lang_app"]
                    config   = st.session_state["pipeline_config"]

                    resume_payload = {"action": action}
                    if changes:
                        resume_payload["changes"] = changes

                    logs = list(st.session_state["log_messages"])
                    logs.append(f"[HITL] 영양사 결정: {action}")

                    log_area2 = st.empty()

                    for event in lang_app.stream(Command(resume=resume_payload), config=config):
                        if "__interrupt__" in event:
                            break
                        node = list(event.keys())[0]
                        output = event.get(node, {})
                        if isinstance(output, dict):
                            for m in output.get("messages", []):
                                logs.append(f"[{node}] {m}")
                            # report_paths 저장
                            if output.get("report_paths"):
                                st.session_state["report_paths"] = output["report_paths"]

                        log_area2.markdown(
                            '<div class="log-box">' +
                            "<br>".join(logs[-15:]) +
                            '</div>', unsafe_allow_html=True
                        )

                    st.session_state["log_messages"] = logs
                    st.session_state["hitl_waiting"] = False
                    st.session_state["pipeline_done"] = True
                    st.success("✅ 파이프라인 완료! 결과 다운로드 페이지로 이동하세요.")
                    st.session_state["page"] = "결과 다운로드"
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ 오류: {e}")
                    import traceback
                    st.code(traceback.format_exc())


# ══════════════════════════════════════════════════════════════
# 페이지 3 — 결과 다운로드
# ══════════════════════════════════════════════════════════════
elif page == "결과 다운로드":
    st.markdown('<div class="mentor-title">결과 다운로드</div>', unsafe_allow_html=True)
    st.markdown('<div class="mentor-sub">생성된 식단표, 배식량, 조리 지침서를 다운로드합니다</div>', unsafe_allow_html=True)

    if not st.session_state["pipeline_done"]:
        st.warning("파이프라인을 먼저 완료해 주세요.")
    else:
        paths = st.session_state.get("report_paths", {})

        files = [
            ("meal_plan", "식단표_28일.xlsx",      "📊 식단표_28일.xlsx",     "28일 최적 식단표 + 영양소 + 권장재료"),
            ("serving",   "개인별_배식량.xlsx",    "👤 개인별_배식량.xlsx",   "배식량 + 개인화 부찬대체 지침 (조리팀용)"),
            ("cooking",   "조리_지침서.txt",        "📝 조리_지침서.txt",      "GPT-4o 메뉴별 조리 주의사항"),
        ]

        for key, default_path, label, desc in files:
            path = paths.get(key, default_path)
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{label}**  \n<span style='color:#888;font-size:0.85rem'>{desc}</span>", unsafe_allow_html=True)
            with col2:
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        st.download_button(
                            "⬇️ 다운로드",
                            data=f.read(),
                            file_name=os.path.basename(path),
                            key=f"dl_{key}",
                            use_container_width=True,
                        )
                else:
                    st.caption("파일 없음")
            with col3:
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    st.caption(f"{size//1024}KB")
            st.divider()

        # 개인화_부찬대체 시트 미리보기
        serving_path = paths.get("serving", "개인별_배식량.xlsx")
        if os.path.exists(serving_path):
            try:
                wb_sheets = pd.ExcelFile(serving_path).sheet_names
                if "개인화_부찬대체" in wb_sheets:
                    st.subheader("🍽️ 개인화 부찬 대체 지침 미리보기 (조리팀용)")
                    df_personal = pd.read_excel(serving_path, sheet_name="개인화_부찬대체", header=1)
                    st.dataframe(
                        df_personal.style.applymap(
                            lambda v: "color: #2E7D52; font-weight: bold"
                            if v not in ["-", "", None] and str(v) != "nan" else "",
                            subset=["대체 부찬1"] if "대체 부찬1" in df_personal.columns else []
                        ),
                        use_container_width=True, hide_index=True
                    )
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════
# 페이지 4 — 잔반 입력
# ══════════════════════════════════════════════════════════════
elif page == "잔반 입력":
    st.markdown('<div class="mentor-title">잔반 입력</div>', unsafe_allow_html=True)
    st.markdown('<div class="mentor-sub">입소자별 슬롯별 잔반율을 입력합니다 (0 = 모두 섭취, 1 = 전량 남김)</div>', unsafe_allow_html=True)

    WASTE_LEVELS = {
        "모두 섭취 (0%)": 0.0,
        "1/4 남김 (25%)": 0.25,
        "절반 남김 (50%)": 0.5,
        "3/4 남김 (75%)": 0.75,
        "전량 남김 (100%)": 1.0,
    }
    SLOTS = ["밥", "국", "주찬", "부찬1", "부찬2", "김치"]
    MEALS = ["아침", "점심", "저녁"]

    fac = st.session_state.get("fac")
    if fac is None:
        st.warning("먼저 파이프라인 실행 페이지에서 시설 데이터를 로드해 주세요.")
    else:
        patients = fac["patients"]
        p_names  = [p.name for p in patients]

        col1, col2, col3 = st.columns(3)
        with col1:
            sel_name = st.selectbox("입소자 선택", p_names)
        with col2:
            sel_day  = st.selectbox("일차 선택", [f"{i}일" for i in range(1, 29)])
        with col3:
            sel_meal = st.selectbox("끼니 선택", MEALS)

        st.divider()
        st.subheader(f"🍽️ {sel_name} | {sel_day} {sel_meal} 잔반율")

        waste_entry = {
            "name": sel_name, "일차": sel_day, "끼니": sel_meal
        }

        cols = st.columns(len(SLOTS))
        for i, slot in enumerate(SLOTS):
            with cols[i]:
                sel = st.selectbox(
                    slot,
                    list(WASTE_LEVELS.keys()),
                    index=0,
                    key=f"waste_{slot}",
                )
                waste_entry[slot] = WASTE_LEVELS[sel]

        if st.button("💾 잔반 데이터 추가", type="primary"):
            waste_log = st.session_state.get("waste_log", [])
            # 중복 제거 (같은 이름/일차/끼니면 덮어쓰기)
            waste_log = [
                w for w in waste_log
                if not (w["name"] == sel_name and w["일차"] == sel_day and w["끼니"] == sel_meal)
            ]
            waste_log.append(waste_entry)
            st.session_state["waste_log"] = waste_log
            st.success(f"✅ {sel_name} {sel_day} {sel_meal} 잔반 데이터 저장 완료")

        # 입력된 잔반 데이터 표시
        waste_log = st.session_state.get("waste_log", [])
        if waste_log:
            st.divider()
            st.subheader(f"📋 입력된 잔반 데이터 ({len(waste_log)}건)")
            df_waste = pd.DataFrame(waste_log)
            st.dataframe(df_waste, use_container_width=True, hide_index=True)

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🗑️ 전체 초기화", use_container_width=True):
                    st.session_state["waste_log"] = []
                    st.rerun()
            with col_b:
                csv = df_waste.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "⬇️ CSV 다운로드",
                    data=csv,
                    file_name="waste_log.csv",
                    use_container_width=True,
                )
        else:
            st.info("아직 입력된 잔반 데이터가 없습니다.")


# ══════════════════════════════════════════════════════════════
# 페이지 5 — 선호도 현황
# ══════════════════════════════════════════════════════════════
elif page == "선호도 현황":
    st.markdown('<div class="mentor-title">선호도 현황</div>', unsafe_allow_html=True)
    st.markdown('<div class="mentor-sub">잔반 기반 EMA 선호도 점수 현황 및 기피 메뉴 분석</div>', unsafe_allow_html=True)

    # preference_weights.json 로드
    weights_path = "preference_weights.json"
    weights = {}
    if os.path.exists(weights_path):
        with open(weights_path, "r", encoding="utf-8") as f:
            weights = json.load(f)
    elif st.session_state.get("preference_weights"):
        weights = st.session_state["preference_weights"]

    if not weights:
        st.info("아직 선호도 데이터가 없습니다. 파이프라인을 한 번 이상 실행해 주세요.")
    else:
        # pool_preference_scores.json 로드
        pool_scores = {}
        if os.path.exists("pool_preference_scores.json"):
            with open("pool_preference_scores.json", "r", encoding="utf-8") as f:
                pool_scores = json.load(f)

        p_names = list(weights.keys())
        sel_p   = st.selectbox("입소자 선택", ["전체"] + p_names)

        # ── 탭 구성 ─────────────────────────────────────────
        tab1, tab2, tab3 = st.tabs(["📊 기피 메뉴 현황", "🔥 선호도 히트맵", "📈 NSGA-II pool 반영"])

        with tab1:
            st.subheader("기피 메뉴 (선호도 0.65 미만)")

            if sel_p == "전체":
                # 시설 평균
                menu_avg = {}
                for name, prefs in weights.items():
                    for menu, score in prefs.items():
                        menu_avg.setdefault(menu, []).append(score)
                menu_avg = {m: round(sum(s)/len(s), 3) for m, s in menu_avg.items()}
                dislike = {m: s for m, s in menu_avg.items() if s < 0.65}
            else:
                dislike = {m: s for m, s in weights[sel_p].items() if s < 0.65}

            if dislike:
                df_dis = pd.DataFrame(
                    sorted(dislike.items(), key=lambda x: x[1]),
                    columns=["메뉴명", "선호도 점수"]
                )
                st.bar_chart(df_dis.set_index("메뉴명"), color="#E07B39")
                st.dataframe(df_dis, use_container_width=True, hide_index=True)
            else:
                st.success("기피 메뉴 없음 (모든 메뉴 선호도 0.65 이상)")

        with tab2:
            st.subheader("입소자별 선호도 히트맵")
            if sel_p == "전체":
                # 모든 메뉴 × 모든 입소자
                all_menus = sorted(set(
                    m for prefs in weights.values() for m in prefs
                ))
                data = {
                    name: [prefs.get(m, None) for m in all_menus]
                    for name, prefs in weights.items()
                }
                df_heat = pd.DataFrame(data, index=all_menus)
                # 기피 메뉴만 표시 (0.65 미만)
                df_heat_filtered = df_heat[df_heat.min(axis=1) < 0.65]
                if not df_heat_filtered.empty:
                    st.dataframe(
                        df_heat_filtered.style.background_gradient(
                            cmap="RdYlGn", vmin=0, vmax=1
                        ).format("{:.3f}"),
                        use_container_width=True,
                    )
                else:
                    st.success("기피 메뉴 없음")
            else:
                prefs = weights[sel_p]
                df_p = pd.DataFrame(
                    sorted(prefs.items(), key=lambda x: x[1]),
                    columns=["메뉴명", "점수"]
                )
                st.dataframe(
                    df_p.style.background_gradient(
                        subset=["점수"], cmap="RdYlGn", vmin=0, vmax=1
                    ).format({"점수": "{:.3f}"}),
                    use_container_width=True, hide_index=True
                )

        with tab3:
            st.subheader("NSGA-II pool 반영 현황")
            if pool_scores:
                penalized = {m: s for m, s in pool_scores.items() if s < 0.5}
                normal    = {m: s for m, s in pool_scores.items() if s >= 0.5}

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""<div class="stat-card">
                        <div class="stat-num" style="color:#B85042">{len(penalized)}</div>
                        <div class="stat-label">페널티 메뉴 (score 0.3)</div>
                    </div>""", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""<div class="stat-card">
                        <div class="stat-num" style="color:#2E7D52">{len(normal)}</div>
                        <div class="stat-label">정상 메뉴 (score 0.7)</div>
                    </div>""", unsafe_allow_html=True)

                if penalized:
                    st.divider()
                    st.markdown("**🔴 페널티 적용 메뉴 (다음 NSGA-II 실행 시 배제)**")
                    df_pen = pd.DataFrame(
                        sorted(penalized.items(), key=lambda x: x[1]),
                        columns=["메뉴명", "preference_score"]
                    )
                    st.dataframe(df_pen, use_container_width=True, hide_index=True)
            else:
                st.info("pool_preference_scores.json 파일이 없습니다. 파이프라인을 한 번 이상 실행해 주세요.")

        # 원시 데이터 다운로드
        st.divider()
        if weights:
            json_str = json.dumps(weights, ensure_ascii=False, indent=2)
            st.download_button(
                "⬇️ preference_weights.json 다운로드",
                data=json_str.encode("utf-8"),
                file_name="preference_weights.json",
            )
