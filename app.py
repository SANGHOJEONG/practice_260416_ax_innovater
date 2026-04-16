import streamlit as st
import pandas as pd
import io
from datetime import datetime

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="롯데온 Pro | 쿠폰 대량 업로드 시스템",
    page_icon="🎟️",
    layout="wide",
)

# ── 데이터 로드 ──────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    try:
        # 파일명을 'dummy_data.csv'로 가정 (사용자 업로드 파일 기반)
        df = pd.read_csv('./dummy_data.csv')
        
        # 요구사항 ①: MD 및 상품군 컬럼이 없을 경우를 대비한 가상 데이터 생성 로직
        if 'MD' not in df.columns:
            df['MD'] = '미지정'
        if '상품군' not in df.columns:
            df['상품군'] = '미지정'
            
        return df
    except FileNotFoundError:
        st.error("데이터 파일(dummy_data.csv)을 찾을 수 없습니다. 파일 경로를 확인해주세요.")
        return pd.DataFrame()

df_master = load_data()

# ── 사이드바 필터 (요구사항 ① 반영) ─────────────────────────────────────────────
st.sidebar.header("🔍 상품 검색 필터")

if not df_master.empty:
    # 5가지 필터 정의
    stores = st.sidebar.multiselect("점포(상위거래처) 선택", options=sorted(df_master['상위거래처'].unique()))
    brands = st.sidebar.multiselect("브랜드 선택", options=sorted(df_master['브랜드명'].unique()))
    mds = st.sidebar.multiselect("MD 선택", options=sorted(df_master['MD'].unique()))
    categories = st.sidebar.multiselect("상품군 선택", options=sorted(df_master['상품군'].unique()))
    statuses = st.sidebar.multiselect("상품 상태 선택", options=sorted(df_master['상태'].unique()))

    # 필터링 로직: 선택하지 않은 경우(리스트가 비어있을 때) 전체 선택으로 인식
    filtered_df = df_master.copy()
    if stores:
        filtered_df = filtered_df[filtered_df['상위거래처'].isin(stores)]
    if brands:
        filtered_df = filtered_df[filtered_df['브랜드명'].isin(brands)]
    if mds:
        filtered_df = filtered_df[filtered_df['MD'].isin(mds)]
    if categories:
        filtered_df = filtered_df[filtered_df['상품군'].isin(categories)]
    if statuses:
        filtered_df = filtered_df[filtered_df['상태'].isin(statuses)]
else:
    filtered_df = pd.DataFrame()

# ── 메인 화면 ─────────────────────────────────────────────────────────────────
st.title("🎟️ 쿠폰 대량 업로드 설정")

with st.container():
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 요구사항 ②: 매장범위 매칭
        range_map = {"전체": "A", "본매장": "M", "제휴채널": "O"}
        selected_range_label = st.selectbox("매장범위 선택", options=list(range_map.keys()))
        shop_range = range_map[selected_range_label]
        
        # 요구사항 ③: 할인유형 매칭
        type_map = {"정률": "10", "정액": "20"}
        selected_type_label = st.selectbox("할인유형 선택", options=list(type_map.keys()))
        type_code = type_map[selected_type_label]

    with col2:
        start_date = st.date_input("행사 시작일", value=datetime.now())
        end_date = st.date_input("행사 종료일", value=datetime.now())
        discount_val = st.number_input("할인액/율 입력", min_value=0, value=0)

    with col3:
        # 요구사항 ④: 분담율 설정 (기본값 0)
        v_share = st.number_input("거래처 분담율 (%)", min_value=0, max_value=100, value=0)
        p_share = st.number_input("제휴사 분담율 (%)", min_value=0, max_value=100, value=0)
        
        # 요구사항 ⑤: 사용요일 선택 (기본값 전체 선택)
        days_list = ["월", "화", "수", "목", "금", "토", "일"]
        selected_days = st.multiselect("사용요일 선택", options=days_list, default=days_list)
        
        # O/X 문자열 변환 로직 (월~일 순서)
        usage_days_str = "".join(["O" if day in selected_days else "X" for day in days_list])

# ── 데이터 처리 및 다운로드 ───────────────────────────────────────────────────
st.divider()
st.subheader(f"📊 대상 상품 목록 (총 {len(filtered_df)}건)")
st.dataframe(filtered_df, use_container_width=True)

if st.button("🚀 업로드용 파일 생성", type="primary"):
    if filtered_df.empty:
        st.warning("필터링된 상품이 없습니다.")
    else:
        # 양식에 맞춘 데이터프레임 구성
        upload_df = pd.DataFrame()
        upload_df['상품번호'] = filtered_df['상품번호']
        upload_df['매장범위'] = shop_range
        upload_df['행사시작일'] = start_date.strftime('%Y%m%d') + "0000"
        upload_df['행사종료일'] = end_date.strftime('%Y%m%d') + "2359"
        upload_df['할인유형'] = type_code
        upload_df['할인액'] = discount_val
        upload_df['거래처분담율'] = v_share
        upload_df['제휴사분담율'] = p_share
        upload_df['사용요일'] = usage_days_str # 요구사항 ⑤ 결과값
        upload_df['시작시간'] = "0000"
        upload_df['종료시간'] = "2359"
        upload_df['요일/시간 할인율'] = ""

        # 엑셀 파일로 변환
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            upload_df.to_excel(writer, index=False, sheet_name='Sheet1')
        
        st.success(f"총 {len(upload_df)}건의 파일이 생성되었습니다!")
        st.download_button(
            label="📥 엑셀 파일 다운로드",
            data=output.getvalue(),
            file_name=f"coupon_upload_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
