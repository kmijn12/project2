import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(layout="wide")
st.title("📏 분전반 최소 피더 폭 계산기 (Module 2)")
st.caption("배치(Rev) CSV와 교차표(Cross-tab) 형태의 표준 이격거리 엑셀을 바탕으로 최소 피더 폭을 계산합니다.")

# ==========================================
# [추가됨] 1단계 텍스트 정제 함수 (안전장치)
# ==========================================
def clean_frame_name(val):
    """
    입력된 프레임 명칭의 양끝 공백을 제거하고 대문자로 통일합니다.
    (예: ' 100 af ' -> '100AF', '100' -> '100')
    """
    if pd.isna(val):
        return ""
    # 엑셀에서 숫자로만 입력되어 float형(예: 100.0)으로 읽히는 경우를 대비해 소수점 제거
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    return str(val).strip().upper()

# ==========================================
# 1. 사이드바: 파일 업로드
# ==========================================
st.sidebar.header("📁 데이터 업로드")

csv_file = st.sidebar.file_uploader("1️⃣ 배치 완료된 CSV 파일 (Module 1 추출본)", type=["csv"])
excel_file = st.sidebar.file_uploader("2️⃣ 표준 이격거리 규격 (Excel 교차표)", type=["xlsx"])

st.sidebar.markdown("""
**💡 이격거리 엑셀표 작성 가이드**
- 첫 번째 열과 첫 번째 행에 MCCB 프레임(AF)을 적어주세요.
- 교차하는 셀에 두 차단기 사이의 '표준 여유폭(mm)'을 입력합니다. (차단기 자체 폭 포함된 러프한 기준치)
""")

# ==========================================
# 2. 데이터 처리 및 계산 로직
# ==========================================
if csv_file and excel_file:
    try:
        # 1. 배치 데이터 로드 ('미지정' 제외)
        layout_df = pd.read_csv(csv_file)
        layout_df = layout_df[layout_df['Section'] != '미지정'].copy()
        
        # [핵심] CSV의 차단기 명칭 정제
        layout_df['mccb_clean'] = layout_df['mccb'].apply(clean_frame_name)
        
        # 2. 규격 데이터 로드 (첫 번째 열을 인덱스로 지정하여 교차표 형태로 읽음)
        gap_df = pd.read_excel(excel_file, index_col=0)
        
        # [핵심] 엑셀표의 행(Index)과 열(Columns) 명칭 정제
        gap_df.columns = [clean_frame_name(c) for c in gap_df.columns]
        gap_df.index = [clean_frame_name(i) for i in gap_df.index]

        def get_gap(m1_clean, m2_clean):
            """교차표에서 두 프레임 간의 이격거리를 찾습니다. (순서 무관)"""
            try:
                # m1행 m2열에서 값을 찾음
                if m2_clean in gap_df.columns and m1_clean in gap_df.index:
                    val = gap_df.at[m1_clean, m2_clean]
                # 없으면 m2행 m1열에서 찾음 (대칭 구조 지원)
                elif m1_clean in gap_df.columns and m2_clean in gap_df.index:
                    val = gap_df.at[m2_clean, m1_clean]
                else:
                    raise ValueError # 둘 다 없으면 에러로 넘김
                
                # 만약 빈칸(NaN)이면 에러 발생
                if pd.isna(val):
                    raise ValueError
                    
                return float(val)
            except:
                # 표에 누락된 조합이 있을 경우 눈에 띄게 비정상적인 값(-999) 반환
                return -999.0

        # ==========================================
        # 3. 섹션별 / 행별 Width 계산 및 UI 출력
        # ==========================================
        sections = layout_df['Section'].unique()
        
        for section in sorted(sections):
            st.markdown(f"### 🗄️ Section: {section}")
            sec_data = layout_df[layout_df['Section'] == section]
            
            section_max_width = 0.0
            row_details = []
            
            # 행(Row)별로 그룹화하여 계산
            for row_num, row_group in sec_data.groupby('Row'):
                # 열(Col) 순서대로 정렬 (왼쪽에서 오른쪽으로 배치)
                sorted_row = row_group.sort_values(by='Col')
                
                # 정제된 명칭(mccb_clean)과 원본 명칭(mccb)을 함께 가져옴
                mccbs_clean = sorted_row['mccb_clean'].tolist()
                mccbs_original = sorted_row['mccb'].astype(str).tolist()
                
                if not mccbs_clean:
                    continue
                
                # 단독 배치 처리
                if len(mccbs_clean) == 1:
                    row_total_width = 0.0
                    calc_string = f"[{mccbs_original[0]}] ➔ 단독 배치 (0mm)"
                else:
                    # 2개 이상 배치된 경우 이격거리 합산
                    row_total_width = 0.0
                    calc_parts = [f"[{mccbs_original[0]}]"]
                    
                    for i in range(len(mccbs_clean) - 1):
                        current_mccb = mccbs_clean[i]
                        next_mccb = mccbs_clean[i+1]
                        
                        # 화면에는 사용자가 입력한 원본 명칭을 보여주기 위함
                        next_mccb_original = mccbs_original[i+1] 
                        
                        gap = get_gap(current_mccb, next_mccb)
                        
                        if gap == -999.0:
                            calc_parts.append(f" ↔ (⚠️표준누락) ↔ [{next_mccb_original}]")
                            # 누락 발생 시 합산 폭도 에러 상태로 처리 (경각심 부여)
                            row_total_width = -999.0 
                        else:
                            # 이전에 에러가 없었을 때만 누적 합산
                            if row_total_width != -999.0: 
                                row_total_width += gap
                            calc_parts.append(f" ↔ ({gap}mm) ↔ [{next_mccb_original}]")
                            
                    calc_string = "".join(calc_parts)
                
                # 최대폭 갱신 (에러가 없는 정상적인 계산 결과일 경우에만)
                if row_total_width > section_max_width and row_total_width != -999.0:
                    section_max_width = row_total_width
                    
                row_details.append({
                    "행(Row)": int(row_num),
                    "차단기 배열 및 산출식": calc_string,
                    "합산 폭(mm)": "계산불가(누락)" if row_total_width == -999.0 else row_total_width
                })
            
            # 1. 최종 결과 (최소 피더 폭) 표시
            # 에러(누락)가 하나라도 있었는지 체크
            has_error = any(str(r["합산 폭(mm)"]) == "계산불가(누락)" for r in row_details)
            
            if has_error:
                st.error("🚨 이 섹션에 엑셀 표준표에 정의되지 않은 조합이 있습니다. 아래 상세 검증을 확인하세요.")
            else:
                st.success(f"**최종 산출 피더 폭 : {section_max_width} mm**")
            
            # 2. 계산 과정 검증 UI (Expander 버튼)
            with st.expander(f"🔍 '{section}' 계산 과정 상세 검증 (클릭하여 열기)"):
                detail_df = pd.DataFrame(row_details)
                
                # 최대값을 가진 행을 시각적으로 강조하기 위한 함수
                def highlight_max(row):
                    # 최대값이면서 정상 계산된 값일 경우 (옅은 빨간색)
                    if row['합산 폭(mm)'] == section_max_width and section_max_width > 0:
                        return ['background-color: #ffcccc'] * len(row)
                    # 에러가 발생한 행 강조 (노란색 텍스트 경고)
                    elif str(row['합산 폭(mm)']) == "계산불가(누락)":
                        return ['background-color: #fff3cd; color: #856404'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(
                    detail_df.style.apply(highlight_max, axis=1),
                    use_container_width=True,
                    hide_index=True
                )
                
            st.divider()

    except Exception as e:
        st.error(f"데이터 처리 중 오류가 발생했습니다. CSV 또는 규격 파일 양식을 확인해주세요.\n\n에러 상세: {e}")
        
else:
    st.info("👈 왼쪽 사이드바에서 배치(Rev) CSV 파일과 표준 이격거리 규격(Excel) 파일을 모두 업로드해주세요.")