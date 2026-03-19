import streamlit as st
import pandas as pd
import re

st.set_page_config(layout="wide")
st.title("⚡ 분전반 배치 및 리비전 관리기 (고급 부스바 선정 버전)")

@st.cache_data
def load_excel_data(file_bytes):
    raw_df = pd.read_excel(file_bytes, sheet_name="RawData")
    sections_df = pd.read_excel(file_bytes, sheet_name="SectionConfig")
    
    try:
        busbar_df = pd.read_excel(file_bytes, sheet_name="BusbarSpec")
    except ValueError:
        busbar_df = pd.DataFrame(columns=["Size", "Thickness", "Type", "Ampacity"]) 
        
    return raw_df, sections_df, busbar_df

# ==========================================
# [신규] 텍스트에서 두께(숫자/소수점)만 추출하는 함수
# ==========================================
def extract_thickness(text):
    # 소수점을 포함한 숫자 추출 (예: "10.5t 더블" -> 10.5)
    numbers = re.findall(r'\d+(?:\.\d+)?', text)
    if numbers:
        return float(numbers[0])
    return 999.0 # 숫자를 못 찾으면 제한을 두지 않음

# ==========================================
# [업데이트] 싱글/더블 분리 및 두께 제한 적용 서칭
# ==========================================
def get_recommended_busbars(total_amp, busbar_df, main_bar_text):
    if busbar_df.empty or 'Thickness' not in busbar_df.columns:
        return "⚠️ BusbarSpec 시트 양식을 확인해주세요."
    if total_amp == 0:
        return "-"
        
    # 1. 메인바 두께 제한 필터링
    main_thickness = extract_thickness(main_bar_text)
    thickness_valid_df = busbar_df[busbar_df['Thickness'] <= main_thickness]
    
    # 2. 허용 전류 필터링
    amp_valid_df = thickness_valid_df[thickness_valid_df['Ampacity'] >= total_amp]
    
    if amp_valid_df.empty:
        return f"⚠️ 두께 {main_thickness}t 이하에서 {total_amp}A를 만족하는 규격이 없습니다."
        
    # 3. Single / Double 각각 최소 규격 찾기
    single_df = amp_valid_df[amp_valid_df['Type'] == 'Single'].sort_values(by='Ampacity')
    double_df = amp_valid_df[amp_valid_df['Type'] == 'Double'].sort_values(by='Ampacity')
    
    result_lines = []
    
    if not single_df.empty:
        best_s = single_df.iloc[0]
        result_lines.append(f"• **Single:** {best_s['Size']} ({best_s['Ampacity']}A)")
    else:
        result_lines.append("• **Single:** 만족 규격 없음")
        
    if not double_df.empty:
        best_d = double_df.iloc[0]
        result_lines.append(f"• **Double:** {best_d['Size']} ({best_d['Ampacity']}A)")
    else:
        result_lines.append("• **Double:** 만족 규격 없음")
        
    return "\n\n".join(result_lines)

# ==========================================
# 1. 사이드바: 엑셀 파일 업로드 및 복원
# ==========================================
st.sidebar.header("📁 1. 기준 데이터 업로드")
uploaded_file = st.sidebar.file_uploader("새 Raw Data 엑셀 파일을 올려주세요.", type=["xlsx"])

if uploaded_file is not None:
    try:
        raw_df, sections_df, busbar_df = load_excel_data(uploaded_file)
        available_sections = ["미지정"] + sections_df['section_name'].dropna().astype(str).tolist()
        
        st.session_state.raw_data = raw_df
        st.session_state.sections = available_sections
        st.session_state.busbar_spec = busbar_df
        
        if 'last_file' not in st.session_state or st.session_state.last_file != uploaded_file.name:
            st.session_state.layout_mapping = pd.DataFrame({
                "circuit_no": raw_df["circuit_no"],
                "Section": ["미지정"] * len(raw_df),
                "Row": [1] * len(raw_df),
                "Col": [1] * len(raw_df)
            })
            st.session_state.last_file = uploaded_file.name
            st.session_state.pop('last_layout_file', None)
            
    except Exception as e:
        st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
        st.stop()
else:
    st.info("👈 왼쪽 사이드바에서 설계 Raw Data(엑셀)를 먼저 업로드해주세요.")
    st.stop()

st.sidebar.divider()
st.sidebar.header("🔄 2. 리비전(Rev) 복원 및 백업")
layout_file = st.sidebar.file_uploader("📂 과거 배치 내역 복원 (CSV)", type=["csv"])
if layout_file is not None:
    if 'last_layout_file' not in st.session_state or st.session_state.last_layout_file != layout_file.name:
        try:
            restored_df = pd.read_csv(layout_file)
            # 여기(복원 로직)에도 이미 인덱스 기반 업데이트가 적용되어 있습니다.
            curr_mapping = st.session_state.layout_mapping.set_index('circuit_no')
            rest_mapping = restored_df.set_index('circuit_no')
            curr_mapping.update(rest_mapping)
            
            st.session_state.layout_mapping = curr_mapping.reset_index()
            st.session_state.last_layout_file = layout_file.name
            st.rerun() 
        except Exception as e:
            st.sidebar.error(f"복원 파일 형식이 맞지 않습니다: {e}")

csv_export = st.session_state.layout_mapping.to_csv(index=False).encode('utf-8-sig')
st.sidebar.download_button(
    label="💾 현재 배치 결과 저장 (CSV)",
    data=csv_export,
    file_name="Panel_Layout_Rev.csv",
    mime="text/csv",
)

# ==========================================
# 3. 배치 컨트롤러 및 그리드 UI
# ==========================================
st.markdown("### ⚙️ 패널 환경 설정")
main_busbar_input = st.text_input("메인 부스바 정보 기입 (예: 8t 더블, 10.5t 등)", value="10t")
st.divider()

col_control, col_grid = st.columns([1, 1.5], gap="large")

with col_control:
    st.subheader("🛠️ 배치 컨트롤러")
    merged_view = pd.merge(st.session_state.raw_data, st.session_state.layout_mapping, on="circuit_no")
    
    with st.form("batch_update_form"):
        st.caption("목록을 자유롭게 수정한 뒤, 아래의 업데이트 버튼을 눌러야 도면에 반영됩니다.")
        
        edited_mapping = st.data_editor(
            merged_view,
            disabled=["circuit_no", "mccb", "current"], 
            column_config={
                "Section": st.column_config.SelectboxColumn("섹션 지정", options=st.session_state.sections),
                "Row": st.column_config.NumberColumn("행(1~10)", min_value=1, max_value=10),
                "Col": st.column_config.NumberColumn("열(1~10)", min_value=1, max_value=10)
            },
            hide_index=True,
            use_container_width=True
        )
        update_btn = st.form_submit_button("🔄 배치 업데이트 및 계산 실행", type="primary")
        
    # ==============================================================
    # [핵심 변경 사항] 충돌 검증 및 이름표(Index) 기반 안전한 업데이트 로직
    # ==============================================================
    if update_btn:
        assigned_data = edited_mapping[edited_mapping["Section"] != "미지정"]
        duplicates = assigned_data[assigned_data.duplicated(subset=['Section', 'Row', 'Col'], keep=False)]
        
        if not duplicates.empty:
            st.error("🚨 **[충돌 발생]** 동일한 위치에 두 개 이상의 회로가 지정되었습니다. 수정 후 다시 시도해주세요.")
            dup_grouped = duplicates.groupby(['Section', 'Row', 'Col'])['circuit_no'].apply(list).reset_index()
            
            for _, row in dup_grouped.iterrows():
                st.warning(f"📍 **{row['Section']}** (행: {row['Row']}, 열: {row['Col']}) ➔ 중복 회로: {', '.join(row['circuit_no'])}")
        else:
            # 1. 'circuit_no'를 고유 이름표(Index)로 설정합니다.
            curr_mapping = st.session_state.layout_mapping.set_index('circuit_no')
            new_mapping = edited_mapping[['circuit_no', 'Section', 'Row', 'Col']].set_index('circuit_no')
            
            # 2. 순서와 무관하게 같은 이름표를 가진 행끼리만 안전하게 덮어씁니다.
            curr_mapping.update(new_mapping)
            
            # 3. 업데이트가 끝난 후 인덱스를 다시 원래대로 돌려놓습니다.
            st.session_state.layout_mapping = curr_mapping.reset_index()
            
            st.rerun()

with col_grid:
    current_view = pd.merge(st.session_state.raw_data, st.session_state.layout_mapping, on="circuit_no")
    target_sections = [sec for sec in st.session_state.sections if sec != "미지정"]
    
    for target_section in target_sections:
        st.subheader(f"🎛️ 현황판: {target_section}")
        sec_data = current_view[current_view["Section"] == target_section]
        
        grid_text = pd.DataFrame([["" for _ in range(10)] for _ in range(10)], 
                                 index=[f"행 {i+1}" for i in range(10)], 
                                 columns=[f"열 {i+1}" for i in range(10)])
        row_sums = [0.0] * 10
        total_current = 0.0
        
        for _, row_data in sec_data.iterrows():
            r = int(row_data['Row']) - 1
            c = int(row_data['Col']) - 1
            
            grid_text.iat[r, c] = f"[{row_data['circuit_no']}]\n{row_data['mccb']}AF\n{row_data['current']}A"
            row_sums[r] += float(row_data['current'])
            total_current += float(row_data['current'])
            
        g_col1, g_col2 = st.columns([3, 1])
        with g_col1:
            st.dataframe(grid_text, use_container_width=True)
            
        with g_col2:
            st.markdown("**📌 가로줄 합산(A)**")
            for i, val in enumerate(row_sums):
                if val > 0: st.write(f"행 {i+1} : **{val}A**")
            
            st.divider()
            st.metric("Total Load", f"{total_current}A")
            
            recommended_text = get_recommended_busbars(total_current, st.session_state.busbar_spec, main_busbar_input)
            st.info(f"**추천 분기 부스바 (메인 이하):**\n\n{recommended_text}")
            
        st.write("---")
