import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import date, datetime, timedelta

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Coupon Generator | 롯데백화점몰",
    page_icon="🎫",
    layout="wide",
)

# ── DB setup (in-memory demo) ─────────────────────────────────────────────────
DB_PATH = "coupon_generator.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            pid         TEXT PRIMARY KEY,
            brand       TEXT NOT NULL,
            product_name TEXT NOT NULL,
            status      TEXT NOT NULL,   -- ON_SALE / HIDDEN
            price       INTEGER NOT NULL,
            registered_at DATE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS coupon_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_name TEXT NOT NULL,
            brand       TEXT NOT NULL,
            discount_rate INTEGER NOT NULL,
            start_date  DATE NOT NULL,
            end_date    DATE NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            pid_count   INTEGER NOT NULL
        );
    """)
    # Seed demo data if empty
    if cur.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        import random
        brands = ["나이키", "아디다스", "폴로", "타미힐피거", "MLB"]
        statuses = ["ON_SALE"] * 4 + ["HIDDEN"]
        rows = []
        for b in brands:
            for i in range(1, 21):
                pid = f"{b[:2].upper()}{i:04d}"
                rows.append((
                    pid, b, f"{b} 상품 {i:02d}", random.choice(statuses),
                    random.randint(30000, 300000) // 1000 * 1000,
                    str(date.today() - timedelta(days=random.randint(0, 200)))
                ))
        cur.executemany(
            "INSERT OR IGNORE INTO products VALUES (?,?,?,?,?,?)", rows
        )
    con.commit()
    con.close()

init_db()

def get_brands():
    con = sqlite3.connect(DB_PATH)
    brands = [r[0] for r in con.execute(
        "SELECT DISTINCT brand FROM products ORDER BY brand").fetchall()]
    con.close()
    return brands

def fetch_products(brand: str) -> pd.DataFrame:
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT pid, product_name, price, status, registered_at "
        "FROM products WHERE brand=? AND status='ON_SALE'",
        con, params=(brand,)
    )
    con.close()
    return df

def get_history() -> pd.DataFrame:
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT id, campaign_name, brand, discount_rate, start_date, end_date, "
        "created_at, pid_count FROM coupon_history ORDER BY id DESC LIMIT 50",
        con
    )
    con.close()
    return df

def save_history(campaign_name, brand, discount_rate, start_date, end_date, pid_count):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO coupon_history "
        "(campaign_name, brand, discount_rate, start_date, end_date, pid_count) "
        "VALUES (?,?,?,?,?,?)",
        (campaign_name, brand, discount_rate,
         str(start_date), str(end_date), pid_count)
    )
    con.commit()
    con.close()

# ── Validation logic ──────────────────────────────────────────────────────────
def validate_100_day_rule(products_df: pd.DataFrame, start_date: date) -> pd.DataFrame:
    """Flag products registered within 100 days of start_date."""
    df = products_df.copy()
    df["registered_at"] = pd.to_datetime(df["registered_at"]).dt.date
    df["days_since_reg"] = (start_date - df["registered_at"]).apply(lambda x: x.days)
    df["100일_룰_위반"] = df["days_since_reg"] < 100
    return df

def build_csv(df: pd.DataFrame, campaign_name: str,
              discount_rate: int, start_date: date, end_date: date) -> bytes:
    """Generate Lotte ON SO upload-format CSV."""
    out = df[~df["100일_룰_위반"]].copy()
    out = out.rename(columns={"pid": "상품ID", "product_name": "상품명", "price": "판매가"})
    out["행사명"] = campaign_name
    out["할인율(%)"] = discount_rate
    out["쿠폰시작일"] = start_date.strftime("%Y%m%d")
    out["쿠폰종료일"] = end_date.strftime("%Y%m%d")
    cols = ["상품ID", "상품명", "판매가", "행사명", "할인율(%)", "쿠폰시작일", "쿠폰종료일"]
    return out[cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0d/Lotte_Department_Store_logo.svg/200px-Lotte_Department_Store_logo.svg.png",
    width=160,
)
st.sidebar.title("Coupon Generator")
st.sidebar.caption("롯데백화점몰 AMD 전용")
menu = st.sidebar.radio(
    "메뉴",
    ["🎫 쿠폰 생성", "📋 등록 이력", "🗄️ 상품 데이터 마트"],
    index=0,
)

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 – 쿠폰 생성
# ═══════════════════════════════════════════════════════════════════════════════
if menu == "🎫 쿠폰 생성":
    st.title("🎫 쿠폰 생성")
    st.caption("7가지 필수 항목을 입력하면 업로드용 CSV가 자동 생성됩니다.")

    # ── Step 1: 사용자 입력 ──────────────────────────────────────────────────
    with st.expander("📝 STEP 1 · 기초 정보 입력", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            brand = st.selectbox("① 브랜드 *", get_brands())
            campaign_name = st.text_input("② 행사명 *", placeholder="예) 나이키 여름 시즌오프")
            discount_rate = st.number_input(
                "③ 할인율 (%) *", min_value=1, max_value=80, value=10, step=1
            )
            min_price = st.number_input(
                "④ 최소 적용 금액 (원)", min_value=0, value=0, step=10000
            )
        with col2:
            start_date = st.date_input("⑤ 쿠폰 시작일 *", value=date.today())
            end_date = st.date_input(
                "⑥ 쿠폰 종료일 *",
                value=date.today() + timedelta(days=30),
                min_value=start_date,
            )
            include_hidden = st.checkbox("⑦ 전시 중단 상품 포함", value=False)

    # ── Step 2: 지능형 탐색 ─────────────────────────────────────────────────
    if st.button("🔍 STEP 2 · 상품 자동 탐색", type="primary", use_container_width=True):
        with st.spinner("DB에서 판매 중인 최신 상품 리스트(PID) 추출 중…"):
            products = fetch_products(brand)
            if include_hidden:
                con = sqlite3.connect(DB_PATH)
                products = pd.read_sql_query(
                    "SELECT pid, product_name, price, status, registered_at "
                    "FROM products WHERE brand=?", con, params=(brand,)
                )
                con.close()

            if min_price > 0:
                products = products[products["price"] >= min_price]

        st.session_state["products"] = products
        st.session_state["search_done"] = True

    if st.session_state.get("search_done"):
        products = st.session_state["products"]
        st.success(f"✅ {brand} 판매 상품 {len(products)}개 추출 완료")

        # ── Step 3: 자동 검증 ──────────────────────────────────────────────
        with st.expander("🔎 STEP 3 · 자동 검증 결과", expanded=True):
            validated = validate_100_day_rule(products, start_date)
            pass_df = validated[~validated["100일_룰_위반"]]
            fail_df = validated[validated["100일_룰_위반"]]

            c1, c2, c3 = st.columns(3)
            c1.metric("전체 상품", len(validated))
            c2.metric("✅ 등록 가능", len(pass_df), delta=None)
            c3.metric("❌ 100일 룰 위반", len(fail_df),
                      delta=f"-{len(fail_df)}" if len(fail_df) else None,
                      delta_color="inverse")

            if not fail_df.empty:
                st.warning(f"⚠️ {len(fail_df)}개 상품이 100일 룰로 제외됩니다.")
                with st.expander("제외 상품 목록 보기"):
                    st.dataframe(
                        fail_df[["pid", "product_name", "price", "days_since_reg"]],
                        use_container_width=True,
                    )

            if start_date >= end_date:
                st.error("❌ 종료일이 시작일보다 앞설 수 없습니다.")

            if not campaign_name.strip():
                st.error("❌ 행사명이 비어 있습니다.")

        # ── Step 4: 파일 생성 ──────────────────────────────────────────────
        st.subheader("📄 STEP 4 · CSV 파일 생성")
        if pass_df.empty:
            st.error("등록 가능한 상품이 없어 파일을 생성할 수 없습니다.")
        elif not campaign_name.strip() or start_date >= end_date:
            st.warning("입력 항목을 다시 확인해주세요.")
        else:
            csv_bytes = build_csv(pass_df, campaign_name, discount_rate, start_date, end_date)
            filename = f"coupon_{brand}_{start_date.strftime('%Y%m%d')}.csv"

            st.download_button(
                label=f"⬇️ CSV 다운로드 ({len(pass_df)}개 상품)",
                data=csv_bytes,
                file_name=filename,
                mime="text/csv",
                type="primary",
                use_container_width=True,
            )

            # Preview
            with st.expander("미리보기 (상위 10행)"):
                preview = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")
                st.dataframe(preview.head(10), use_container_width=True)

            if st.button("💾 이력 저장", use_container_width=True):
                save_history(
                    campaign_name, brand, discount_rate,
                    start_date, end_date, len(pass_df)
                )
                st.success("이력이 저장되었습니다.")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 2 – 등록 이력
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "📋 등록 이력":
    st.title("📋 쿠폰 등록 이력")
    hist = get_history()
    if hist.empty:
        st.info("아직 저장된 이력이 없습니다. 쿠폰을 생성한 뒤 이력 저장을 눌러주세요.")
    else:
        # Expiry warning: flag coupons ending within 7 days
        hist["end_date"] = pd.to_datetime(hist["end_date"]).dt.date
        hist["만료_임박"] = hist["end_date"].apply(
            lambda d: "⚠️ 만료 임박" if d - date.today() <= timedelta(days=7) else ""
        )
        st.dataframe(
            hist[["id", "campaign_name", "brand", "discount_rate",
                  "start_date", "end_date", "pid_count", "만료_임박", "created_at"]],
            use_container_width=True,
        )

        # 100-day expiry monitor
        st.subheader("⏰ 100일 만료 모니터")
        st.caption("종료일 기준으로 7일 이내 만료되는 캠페인을 자동으로 탐지합니다.")
        expiring = hist[hist["만료_임박"] != ""]
        if expiring.empty:
            st.success("현재 만료 임박 캠페인 없음")
        else:
            st.warning(f"{len(expiring)}개 캠페인이 곧 만료됩니다. 쿠폰 연장을 검토하세요.")
            st.dataframe(expiring, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 3 – 상품 데이터 마트
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "🗄️ 상품 데이터 마트":
    st.title("🗄️ 상품 데이터 마트")
    st.caption("브랜드별 최신 판매/전시 상태를 확인합니다.")

    con = sqlite3.connect(DB_PATH)
    all_df = pd.read_sql_query(
        "SELECT brand, status, COUNT(*) as cnt FROM products GROUP BY brand, status ORDER BY brand",
        con
    )
    full_df = pd.read_sql_query("SELECT * FROM products ORDER BY brand, pid", con)
    con.close()

    # Summary metrics
    total = len(full_df)
    on_sale = len(full_df[full_df["status"] == "ON_SALE"])
    col1, col2, col3 = st.columns(3)
    col1.metric("전체 상품", total)
    col2.metric("판매 중", on_sale)
    col3.metric("전시 중단", total - on_sale)

    # Brand breakdown chart
    pivot = all_df.pivot_table(index="brand", columns="status", values="cnt", fill_value=0)
    st.bar_chart(pivot)

    # Full table with filter
    selected_brand = st.selectbox("브랜드 필터", ["전체"] + get_brands())
    view_df = full_df if selected_brand == "전체" else full_df[full_df["brand"] == selected_brand]
    st.dataframe(view_df, use_container_width=True)
