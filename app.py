import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# 1. CẤU HÌNH TRANG & CSS
st.set_page_config(
    page_title="SaaS Financial Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { font-family: 'Segoe UI', sans-serif; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    div[data-testid="stMetricValue"] { color: #4F46E5; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# Link Google Sheet
DATA_URL = "https://docs.google.com/spreadsheets/d/14h1dp9hV7V2aEx17jX7ubf8_j3K6c_oP_rK6L0t7Bh8/export?format=csv&gid=1004861213"

# 2. XỬ LÝ DỮ LIỆU
@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(DATA_URL)
        # Chuẩn hóa tên cột (xóa khoảng trắng thừa)
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Lỗi khi tải dữ liệu: {e}")
        return pd.DataFrame()

def parse_duration(product_str):
    if pd.isna(product_str): return 0
    p_lower = str(product_str).lower()
    if '12 tháng' in p_lower or '1 năm' in p_lower: return 365
    if '06 tháng' in p_lower or '6 tháng' in p_lower: return 180
    if '03 tháng' in p_lower or '3 tháng' in p_lower: return 90
    if '02 tháng' in p_lower or '2 tháng' in p_lower: return 60
    if '01 tháng' in p_lower or '1 tháng' in p_lower: return 30
    if '2 tuần' in p_lower: return 14
    if '1 tuần' in p_lower: return 7
    if 'học thử' in p_lower: return 1
    return 0

def clean_currency(x):
    try:
        clean_str = str(x).replace(',', '').replace('.', '').replace('₫', '').replace('VNĐ', '').strip()
        return float(clean_str)
    except:
        return 0.0

@st.cache_data
def process_financial_data(df):
    """
    Xử lý làm sạch và tính toán Accrual Revenue.
    """
    df_clean = df.copy()

    # 1. DROP NA
    df_clean = df_clean.dropna(subset=['Sản phẩm', 'Ngày thanh toán'])

    if df_clean.empty:
        return pd.DataFrame(), pd.DataFrame()

    # 2. XỬ LÝ NGÀY THÁNG
    df_clean['Ngày thanh toán'] = pd.to_datetime(df_clean['Ngày thanh toán'], dayfirst=True, errors='coerce')
    df_clean = df_clean.dropna(subset=['Ngày thanh toán'])

    # 3. NHẬN DIỆN CỘT TIỀN
    col_amount = 'Đã thanh toán'
    if 'Đã thanh toán' not in df_clean.columns:
        col_amount = df_clean.columns[2]

    # 4. TÍNH TOÁN
    df_clean['Duration'] = df_clean['Sản phẩm'].apply(parse_duration)
    df_clean['Amount_Clean'] = df_clean[col_amount].apply(clean_currency)
    df_clean['Daily_Rate'] = df_clean['Amount_Clean'] / df_clean['Duration']

    # 5. EXPLODE RA DAILY LEDGER
    daily_records = []
    for _, row in df_clean.iterrows():
        try:
            duration = int(row['Duration'])
            date_range = pd.date_range(start=row['Ngày thanh toán'], periods=duration, freq='D')

            # Lấy Customer ID
            cust_id = row.get('Mã khách hàng', row.get('Mã đơn hàng', 'Unknown'))

            temp_df = pd.DataFrame({
                'Date': date_range,
                'Daily_Revenue': row['Daily_Rate'],
                'Mã khách hàng': cust_id,
                'Product': row['Sản phẩm'],
                'Duration_Days': duration
            })
            daily_records.append(temp_df)
        except Exception:
            continue

    if daily_records:
        daily_revenue_df = pd.concat(daily_records, ignore_index=True)
    else:
        daily_revenue_df = pd.DataFrame(columns=['Date', 'Daily_Revenue', 'Mã khách hàng', 'Product', 'Duration_Days'])

    return df_clean, daily_revenue_df

@st.cache_data
def calculate_cohorts(df_clean, daily_revenue_df):
    if daily_revenue_df.empty:
        return pd.DataFrame(), pd.Series()

    daily_revenue_df['Date'] = pd.to_datetime(daily_revenue_df['Date'])

    # 1. Tháng gia nhập
    if 'Mã khách hàng' not in df_clean.columns:
        return pd.DataFrame(), pd.Series()

    df_clean['Acquisition_Month'] = df_clean.groupby('Mã khách hàng')['Ngày thanh toán'].transform('min').dt.to_period(
        'M')
    cohort_map = df_clean[['Mã khách hàng', 'Acquisition_Month']].drop_duplicates()

    # 2. Tháng hoạt động
    daily_revenue_df['Activity_Month'] = daily_revenue_df['Date'].dt.to_period('M')
    active_customers = daily_revenue_df[['Mã khách hàng', 'Activity_Month']].drop_duplicates()

    # 3. Join
    cohort_data = pd.merge(active_customers, cohort_map, on='Mã khách hàng')

    # 4. Cohort Index
    def diff_months(x):
        return (x['Activity_Month'].year - x['Acquisition_Month'].year) * 12 + \
            (x['Activity_Month'].month - x['Acquisition_Month'].month)

    cohort_data['Cohort_Index'] = cohort_data.apply(diff_months, axis=1)

    # 5. Pivot
    cohort_counts = cohort_data.groupby(['Acquisition_Month', 'Cohort_Index'])['Mã khách hàng'].nunique().reset_index()
    cohort_pivot = cohort_counts.pivot(index='Acquisition_Month', columns='Cohort_Index', values='Mã khách hàng')

    # 6. Retention & Sorting
    cohort_size = cohort_pivot.iloc[:, 0]
    retention_matrix = cohort_pivot.divide(cohort_size, axis=0)

    # Sort
    retention_matrix = retention_matrix.sort_index(ascending=True)
    cohort_size = cohort_size.sort_index(ascending=True)

    return retention_matrix, cohort_size

# 3. GIAO DIỆN DASHBOARD
def main():
    # --- SIDEBAR ---
    with st.sidebar:
        st.header("Cấu hình Dashboard")
        st.markdown("---")
        with st.status("Đang tải dữ liệu...", expanded=True) as status:
            raw_df = load_data()
            if not raw_df.empty:
                df_clean, daily_df = process_financial_data(raw_df)
                status.update(label="Dữ liệu đã sẵn sàng!", state="complete", expanded=False)
            else:
                status.update(label="Lỗi tải dữ liệu", state="error")
                st.stop()

        # Filters
        st.subheader("Bộ lọc")
        all_products = daily_df['Product'].unique().tolist()
        selected_products = st.multiselect("Sản phẩm:", all_products, default=all_products)

        min_date = daily_df['Date'].min().date()
        max_date = daily_df['Date'].max().date()
        date_range = st.date_input("Thời gian:", [min_date, max_date])

    # Apply Filters
    filtered_daily_df = daily_df[daily_df['Product'].isin(selected_products)]
    if len(date_range) == 2:
        start_d, end_d = date_range
        mask = (filtered_daily_df['Date'].dt.date >= start_d) & (filtered_daily_df['Date'].dt.date <= end_d)
        filtered_daily_df = filtered_daily_df.loc[mask]

    # --- MAIN UI ---
    st.title("SaaS Financial Dashboard")
    st.markdown("---")

    # KPI Calculation
    monthly_stats = filtered_daily_df.groupby(filtered_daily_df['Date'].dt.to_period('M')).agg({
        'Daily_Revenue': 'sum',
        'Mã khách hàng': 'nunique'
    }).rename(columns={'Daily_Revenue': 'Accrual_Revenue', 'Mã khách hàng': 'Active_Users'}).reset_index()
    monthly_stats['Month_Str'] = monthly_stats['Date'].astype(str)

    total_rev = monthly_stats['Accrual_Revenue'].sum()
    avg_users = monthly_stats['Active_Users'].mean() if not monthly_stats.empty else 0
    current_rev = monthly_stats.iloc[-1]['Accrual_Revenue'] if not monthly_stats.empty else 0
    last_date = filtered_daily_df['Date'].max()
    active_now = filtered_daily_df[filtered_daily_df['Date'] == last_date]['Mã khách hàng'].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng Accrual Revenue", f"{total_rev:,.0f} đ", delta="Tích lũy")
    c2.metric("Doanh thu tháng cuối", f"{current_rev:,.0f} đ")
    c3.metric("Avg Active Users", f"{int(avg_users)}")
    c4.metric("Active Now", f"{active_now}")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["Tăng Trưởng", "Cohort Retention", "Dữ Liệu"])

    # TAB 1: Chart
    with tab1:
        fig_rev = go.Figure()
        fig_rev.add_trace(go.Bar(
            x=monthly_stats['Month_Str'], y=monthly_stats['Accrual_Revenue'],
            name='Doanh thu', marker_color='#6366f1'
        ))
        fig_rev.add_trace(go.Scatter(
            x=monthly_stats['Month_Str'], y=monthly_stats['Active_Users'],
            name='Users', yaxis='y2', line=dict(color='#f59e0b', width=3)
        ))
        fig_rev.update_layout(
            template="plotly_white", height=500,
            yaxis=dict(title='Doanh Thu'),
            yaxis2=dict(title='User', overlaying='y', side='right'),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig_rev, use_container_width=True)

    # TAB 2: COHORT
    with tab2:
        st.subheader("Phân tích Retention")

        cohort_input_df = daily_df[daily_df['Product'].isin(selected_products)]
        retention_matrix, cohort_size = calculate_cohorts(df_clean, cohort_input_df)

        if not retention_matrix.empty:
            y_labels_final = []
            for idx in retention_matrix.index:
                size = cohort_size.loc[idx]
                y_labels_final.append(f"{idx} (n={size})")

            x_labels = [str(int(x)) for x in retention_matrix.columns]

            z = retention_matrix.values * 100
            text_data = [[f"{val:.0f}%" if not pd.isna(val) else "" for val in row] for row in z]

            # 3. Color Scale: YlGnBu (Yêu cầu mới)
            fig_cohort = go.Figure(data=go.Heatmap(
                z=z,
                x=x_labels,
                y=y_labels_final,
                text=text_data,
                texttemplate="%{text}",
                colorscale='YlGnBu',
                zmin=0, zmax=100,
                xgap=2, ygap=2,
                showscale=True
            ))

            fig_cohort.update_layout(
                height=700,
                xaxis_title="Tháng thứ (Month Index)",
                yaxis_title="Cohort (Tháng Gia Nhập)",
                plot_bgcolor='white',
                xaxis=dict(
                    type='category',
                    tickmode='linear'
                )
            )
            fig_cohort['layout']['yaxis']['autorange'] = "reversed"

            st.plotly_chart(fig_cohort, use_container_width=True)
        else:
            st.info("Chưa đủ dữ liệu.")

    # TAB 3: DATA
    with tab3:
        st.dataframe(df_clean, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
