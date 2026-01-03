import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# 1. CẤU HÌNH TRANG & CONSTANTS
st.set_page_config(
    page_title="SaaS Financial Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Link Google Sheet đã chuyển sang định dạng CSV export
DATA_URL = "https://docs.google.com/spreadsheets/d/14h1dp9hV7V2aEx17jX7ubf8_j3K6c_oP_rK6L0t7Bh8/export?format=csv&gid=1004861213"


# 2. HÀM XỬ LÝ DỮ LIỆU (ETL)

@st.cache_data(ttl=600)
def load_data():
    """Load dữ liệu trực tiếp từ Google Sheet."""
    try:
        df = pd.read_csv(DATA_URL)
        # Chuẩn hóa tên cột để tránh lỗi typo/space
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Lỗi khi tải dữ liệu: {e}")
        return pd.DataFrame()

def parse_duration(product_str):
    """Phân tích tên sản phẩm để lấy số ngày (Duration)."""
    if pd.isna(product_str): return 30

    p_lower = str(product_str).lower()

    # Logic mapping từ khóa sang số ngày
    if '12 tháng' in p_lower or '1 năm' in p_lower: return 365
    if '06 tháng' in p_lower or '6 tháng' in p_lower: return 180
    if '03 tháng' in p_lower or '3 tháng' in p_lower: return 90
    if '02 tháng' in p_lower or '2 tháng' in p_lower: return 60
    if '01 tháng' in p_lower or '1 tháng' in p_lower: return 30
    if '2 tuần' in p_lower: return 14
    if '1 tuần' in p_lower: return 7
    if 'học thử' in p_lower: return 30

    return 30  # Default nếu không tìm thấy pattern


@st.cache_data
def process_financial_data(df):
    """
    Xử lý làm sạch và tính toán Accrual Revenue (Doanh thu dồn tích).
    """
    # 1. Làm sạch ngày tháng
    df['Ngày thanh toán'] = pd.to_datetime(df['Ngày thanh toán'], format='%d/%m/%Y', errors='coerce')

    # Loại bỏ đơn chưa thanh toán hoặc lỗi ngày
    df_clean = df.dropna(subset=['Ngày thanh toán']).copy()

    # 2. Parse thời gian và tính Daily Rate
    df_clean = df_clean.apply(parse_duration)
    # Xử lý chuỗi tiền tệ (bỏ dấu phẩy nếu có, hoặc ép kiểu số)
    if df_clean.dtype == 'O':
        df_clean = df_clean.astype(str).str.replace(',', '').astype(float)

    df_clean = df_clean / df_clean

    # 3. Kỹ thuật "Explode" để tạo bảng doanh thu theo ngày (Daily Ledger)
    daily_records =
    for _, row in df_clean.iterrows():
        # Tạo dải ngày từ ngày thanh toán đến hết hạn
        date_range = pd.date_range(start=row['Ngày thanh toán'], periods=row, freq='D')

        # DataFrame nhỏ cho từng đơn hàng
        temp_df = pd.DataFrame({
            'Date': date_range,
            'Daily_Revenue': row,
            'Customer_ID': row['Mã khách hàng'],
            'Product': row
        })
        daily_records.append(temp_df)

    # Gộp tất cả lại thành một bảng master
    if daily_records:
        daily_revenue_df = pd.concat(daily_records, ignore_index=True)
    else:
        daily_revenue_df = pd.DataFrame(columns=)

    return df_clean, daily_revenue_df


@st.cache_data
def calculate_cohorts(df_clean, daily_revenue_df):
    """Tính toán Retention Matrix theo Activity-Based."""
    # 1. Xác định tháng gia nhập (Acquisition Month)
    df_clean['Acquisition_Month'] = df_clean.groupby('Mã khách hàng')['Ngày thanh toán'].transform('min').dt.to_period(
        'M')
    cohort_map = df_clean[['Mã khách hàng', 'Acquisition_Month']].drop_duplicates()

    # 2. Xác định tháng hoạt động (Activity Month) dựa trên việc 'còn hạn sử dụng'
    daily_revenue_df['Activity_Month'] = daily_revenue_df.dt.to_period('M')
    active_customers = daily_revenue_df[['Mã khách hàng', 'Activity_Month']].drop_duplicates()

    # 3. Join lại
    cohort_data = pd.merge(active_customers, cohort_map, on='Mã khách hàng')

    # 4. Tính Cohort Index
    def diff_months(x):
        return (x['Activity_Month'].year - x['Acquisition_Month'].year) * 12 + \
            (x['Activity_Month'].month - x['Acquisition_Month'].month)

    cohort_data['Cohort_Index'] = cohort_data.apply(diff_months, axis=1)

    # 5. Pivot Table
    cohort_counts = cohort_data.groupby(['Acquisition_Month', 'Cohort_Index'])['Mã khách hàng'].nunique().reset_index()
    cohort_pivot = cohort_counts.pivot(index='Acquisition_Month', columns='Cohort_Index', values='Mã khách hàng')

    # 6. Tính Retention Rate
    cohort_size = cohort_pivot.iloc[:, 0]
    retention_matrix = cohort_pivot.divide(cohort_size, axis=0)

    return retention_matrix, cohort_size


# 3. GIAO DIỆN DASHBOARD

def main():
    st.title("Subscription Analytics & Financial Dashboard")
    st.markdown("### Bài giải Technical Test - Vị trí Data Analyst")
    st.markdown("---")

    # Load Data
    with st.spinner('Đang kết nối tới Google Sheet & Xử lý dữ liệu...'):
        raw_df = load_data()

    if raw_df.empty:
        st.warning("Không thể tải dữ liệu. Vui lòng kiểm tra lại đường truyền.")
        return

    # Process Data
    df_clean, daily_df = process_financial_data(raw_df)

    # Tính Monthly Stats
    monthly_stats = daily_df.groupby(daily_df.dt.to_period('M')).agg({
        'Daily_Revenue': 'sum',
        'Customer_ID': 'nunique'
    }).rename(columns={'Daily_Revenue': 'Accrual_Revenue', 'Customer_ID': 'Active_Users'}).reset_index()

    monthly_stats = monthly_stats.astype(str)

    # KPI SECTION
    col1, col2, col3, col4 = st.columns(4)

    total_rev_accrual = monthly_stats.sum()
    avg_mau = monthly_stats['Active_Users'].mean()
    current_month_rev = monthly_stats.iloc[-1] if not monthly_stats.empty else 0
    active_now = daily_df == daily_df.max()].nunique()

    col1.metric("Tổng Accrual Revenue", f"{total_rev_accrual:,.0f} VND")
    col2.metric("Revenue Tháng Gần Nhất", f"{current_month_rev:,.0f} VND")
    col3.metric("Avg. Monthly Active Users", f"{int(avg_mau)}")
    col4.metric("Active Users Hiện Tại", f"{active_now}")

    st.markdown("---")

    # TAB 1: DOANH THU & TĂNG TRƯỞNG
    tab1, tab2, tab3 = st.tabs()

    with tab1:
        st.subheader("Diễn biến Doanh thu Dồn tích (Accrual Revenue)")
    st.caption(
        "Doanh thu được ghi nhận dựa trên số ngày thực tế sử dụng dịch vụ (Accrual Basis), loại bỏ yếu tố mùa vụ của việc thanh toán trả trước.")

    # Biểu đồ Line kết hợp Bar
    fig_rev = go.Figure()
    fig_rev.add_trace(go.Bar(
        x=monthly_stats,
        y=monthly_stats,
        name='Accrual Revenue',
        marker_color='#4F46E5'
    ))
    fig_rev.add_trace(go.Scatter(
        x=monthly_stats,
        y=monthly_stats['Active_Users'],
        name='Active Users',
        yaxis='y2',
        mode='lines+markers',
        line=dict(color='#F59E0B', width=3)
    ))

    fig_rev.update_layout(
    title = 'Accrual Revenue vs Active Users theo Tháng',
    yaxis = dict(title='Doanh Thu (VND)'),
    yaxis2 = dict(title='Số User Active', overlaying='y', side='right'),
    hovermode = "x unified",
    legend = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)

)
st.plotly_chart(fig_rev, use_container_width=True)

# TAB 2: COHORT ANALYSIS
with tab2:
    st.subheader("Phân Tích Cohort Retention (Activity-Based)")
st.caption("Tỷ lệ % khách hàng vẫn còn Active (còn hạn subscription) sau các tháng kể từ khi gia nhập.")

retention_matrix, cohort_size = calculate_cohorts(df_clean, daily_df)

# Format lại index cho đẹp
retention_matrix.index = retention_matrix.index.astype(str)

# Vẽ Heatmap
z = retention_matrix.values * 100
x = retention_matrix.columns.astype(str)
y = retention_matrix.index.tolist()

# Annotation text
text_data = [[f"{val:.1f}%" if not pd.isna(val) else "" for val in row] for row in z]

fig_cohort = go.Figure(data=go.Heatmap(
    z=z, x=x, y=y,
    text=text_data,
    texttemplate="%{text}",
    colorscale='Blues',
    hoverongaps=False,
    showscale=True
))

fig_cohort.update_layout(
xaxis_title = "Số tháng kể từ khi mua lần đầu (Month Index)",
yaxis_title = "Tháng Gia Nhập (Cohort Month)",
height = 700
)
st.plotly_chart(fig_cohort, use_container_width=True)

with st.expander("Xem bảng số liệu Cohort Size"):
    st.dataframe(cohort_size.reset_index().rename(columns={0: 'Cohort Size'}))

# TAB 3: DATA PREVIEW
with tab3:
    st.subheader("Dữ liệu sau khi làm sạch (Silver Layer)")
st.dataframe(df_clean)

if __name__ == "__main__":
    main()