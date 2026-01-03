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

# Link Google Sheet (dạng CSV export)
DATA_URL = "https://docs.google.com/spreadsheets/d/14h1dp9hV7V2aEx17jX7ubf8_j3K6c_oP_rK6L0t7Bh8/export?format=csv&gid=1004861213"

# 2. HÀM HỖ TRỢ & XỬ LÝ DỮ LIỆU (ETL)

@st.cache_data(ttl=600)
def load_data():
    """Load dữ liệu trực tiếp từ Google Sheet."""
    try:
        df = pd.read_csv(DATA_URL)
        # Chuẩn hóa tên cột: xóa khoảng trắng thừa ở đầu/cuối tên cột
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Lỗi khi tải dữ liệu: {e}")
        return pd.DataFrame()

def parse_duration(product_str):
    """
    Phân tích tên sản phẩm để lấy số ngày (Duration).
    Mặc định là 0 ngày nếu không tìm thấy từ khóa.
    """
    if pd.isna(product_str): return 0

    p_lower = str(product_str).lower()

    # Logic mapping từ khóa sang số ngày
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
    """Làm sạch chuỗi tiền tệ thành số float."""
    try:
        # Xóa dấu phẩy, dấu chấm, ký tự tiền tệ
        clean_str = str(x).replace(',', '').replace('.', '').replace('₫', '').replace('VNĐ', '').strip()
        return float(clean_str)
    except:
        return 0.0

@st.cache_data
def process_financial_data(df):
    """
    Xử lý làm sạch và tính toán Accrual Revenue (Doanh thu dồn tích).
    """
    # Copy để tránh warning SettingWithCopy
    df_clean = df.copy()

    # 1. XỬ LÝ NGÀY THÁNG
    if 'Ngày thanh toán' not in df_clean.columns:
        return pd.DataFrame(), pd.DataFrame()

    # Chuyển đổi ngày tháng: dayfirst=True ưu tiên định dạng dd/mm/yyyy (Việt Nam)
    df_clean['Ngày thanh toán'] = pd.to_datetime(df_clean['Ngày thanh toán'], dayfirst=True, errors='coerce')

    # Loại bỏ các dòng mà ngày thanh toán bị lỗi (NaT)
    df_clean = df_clean.dropna(subset=['Ngày thanh toán'])

    if df_clean.empty:
        return pd.DataFrame(), pd.DataFrame()

    # 2. TỰ ĐỘNG NHẬN DIỆN CỘT
    # Xác định cột Tiền
    col_amount = 'Đã thanh toán'
    if 'Đã thanh toán' not in df_clean.columns:
        col_amount = df_clean.columns[2]  # Fallback

    # Xác định cột Sản phẩm
    col_product = 'Sản phẩm' if 'Sản phẩm' in df_clean.columns else df_clean.columns[1]

    # 3. TÍNH TOÁN DURATION & DAILY RATE
    df_clean['Duration'] = df_clean[col_product].apply(parse_duration)
    df_clean['Amount_Clean'] = df_clean[col_amount].apply(clean_currency)

    # Tính giá trị mỗi ngày (Daily Rate)
    df_clean['Daily_Rate'] = df_clean['Amount_Clean'] / df_clean['Duration']

    # 4. EXPLODE RA DAILY LEDGER (SỔ CÁI HÀNG NGÀY)
    daily_records = []

    for _, row in df_clean.iterrows():
        try:
            duration = int(row['Duration'])
            # Tạo dải ngày từ ngày thanh toán đến hết hạn
            date_range = pd.date_range(start=row['Ngày thanh toán'], periods=duration, freq='D')

            # Tạo DataFrame con cho từng đơn hàng
            temp_df = pd.DataFrame({
                'Date': date_range,
                'Daily_Revenue': row['Daily_Rate'],
                'Customer_ID': row.get('Mã khách hàng', 'Unknown'),
                'Product': row[col_product]
            })
            daily_records.append(temp_df)
        except Exception:
            continue

    # Gộp tất cả lại thành một bảng master
    if daily_records:
        daily_revenue_df = pd.concat(daily_records, ignore_index=True)
    else:
        daily_revenue_df = pd.DataFrame(columns=['Date', 'Daily_Revenue', 'Customer_ID', 'Product'])

    return df_clean, daily_revenue_df

@st.cache_data
def calculate_cohorts(df_clean, daily_revenue_df):
    """Tính toán Retention Matrix theo Activity-Based."""
    if daily_revenue_df.empty:
        return pd.DataFrame(), pd.Series()

    # Đảm bảo cột Date là datetime
    daily_revenue_df['Date'] = pd.to_datetime(daily_revenue_df['Date'])

    # 1. Xác định tháng gia nhập (Acquisition Month)
    df_clean['Acquisition_Month'] = df_clean.groupby('Mã khách hàng')['Ngày thanh toán'].transform('min').dt.to_period(
        'M')
    cohort_map = df_clean[['Mã khách hàng', 'Acquisition_Month']].drop_duplicates()

    # 2. Xác định tháng hoạt động (Activity Month) - Dựa trên việc "còn hạn sử dụng" trong ngày đó
    daily_revenue_df['Activity_Month'] = daily_revenue_df['Date'].dt.to_period('M')
    active_customers = daily_revenue_df[['Mã khách hàng', 'Activity_Month']].drop_duplicates()

    # 3. Join lại
    cohort_data = pd.merge(active_customers, cohort_map, on='Mã khách hàng')

    # 4. Tính Cohort Index (Khoảng cách tháng)
    def diff_months(x):
        return (x['Activity_Month'].year - x['Acquisition_Month'].year) * 12 + \
            (x['Activity_Month'].month - x['Acquisition_Month'].month)

    cohort_data['Cohort_Index'] = cohort_data.apply(diff_months, axis=1)

    # 5. Pivot Table đếm số lượng user
    cohort_counts = cohort_data.groupby(['Acquisition_Month', 'Cohort_Index'])['Mã khách hàng'].nunique().reset_index()
    cohort_pivot = cohort_counts.pivot(index='Acquisition_Month', columns='Cohort_Index', values='Mã khách hàng')

    # 6. Tính Retention Rate (%)
    cohort_size = cohort_pivot.iloc[:, 0]
    retention_matrix = cohort_pivot.divide(cohort_size, axis=0)

    return retention_matrix, cohort_size

# 3. GIAO DIỆN DASHBOARD (MAIN)

def main():
    st.title("Subscription Analytics & Financial Dashboard")
    st.markdown("### Bài giải Technical Test - Vị trí Data Analyst")
    st.markdown("---")

    # Load Data
    with st.spinner('Đang kết nối tới Google Sheet & Xử lý dữ liệu...'):
        raw_df = load_data()

    if raw_df.empty:
        st.error("Không thể tải dữ liệu. Vui lòng kiểm tra lại đường truyền.")
        return

    # Process Data
    df_clean, daily_df = process_financial_data(raw_df)

    # Validation
    if daily_df.empty:
        st.error("Dữ liệu sau khi xử lý bị trống!")
        st.warning(f"Hệ thống tìm thấy các cột: {raw_df.columns.tolist()}")
        st.info(
            "Vui lòng kiểm tra lại định dạng ngày tháng trong file Google Sheet (nên là dd/mm/yyyy hoặc yyyy-mm-dd) và cột Tiền.")
        st.stop()

    # Tính Monthly Stats cho biểu đồ
    monthly_stats = daily_df.groupby(daily_df['Date'].dt.to_period('M')).agg({
        'Daily_Revenue': 'sum',
        'Customer_ID': 'nunique'
    }).rename(columns={'Daily_Revenue': 'Accrual_Revenue', 'Customer_ID': 'Active_Users'}).reset_index()

    monthly_stats.rename(columns={'Date': 'Month_Period'}, inplace=True)
    monthly_stats['Month_Str'] = monthly_stats['Month_Period'].astype(str)

    # KPI SECTION
    col1, col2, col3, col4 = st.columns(4)

    total_rev_accrual = monthly_stats['Accrual_Revenue'].sum()
    avg_mau = monthly_stats['Active_Users'].mean()
    current_month_rev = monthly_stats.iloc[-1]['Accrual_Revenue'] if not monthly_stats.empty else 0

    max_date = daily_df['Date'].max()
    active_now = daily_df[daily_df['Date'] == max_date]['Customer_ID'].nunique()

    col1.metric("Tổng Accrual Revenue", f"{total_rev_accrual:,.0f} VND")
    col2.metric("Revenue Tháng Gần Nhất", f"{current_month_rev:,.0f} VND")
    col3.metric("Avg. Monthly Active Users", f"{int(avg_mau) if not pd.isna(avg_mau) else 0}")
    col4.metric("Active Users Hiện Tại", f"{active_now}")

    st.markdown("---")

    # TABS SECTION
    tab1, tab2, tab3 = st.tabs(["Doanh Thu & Users", "Cohort Retention", "Dữ liệu Chi tiết"])

    # TAB 1: DOANH THU
    with tab1:
        st.subheader("Diễn biến Doanh thu Dồn tích (Accrual Revenue)")
        st.caption(
            "Doanh thu được ghi nhận rải đều theo số ngày sử dụng dịch vụ thực tế, phản ánh chính xác hiệu quả kinh doanh hơn Cash-based.")

        # Biểu đồ Combo: Bar (Revenue) + Line (Users)
        fig_rev = go.Figure()
        fig_rev.add_trace(go.Bar(
            x=monthly_stats['Month_Str'],
            y=monthly_stats['Accrual_Revenue'],
            name='Accrual Revenue',
            marker_color='#4F46E5'
        ))
        fig_rev.add_trace(go.Scatter(
            x=monthly_stats['Month_Str'],
            y=monthly_stats['Active_Users'],
            name='Active Users',
            yaxis='y2',
            mode='lines+markers',
            line=dict(color='#F59E0B', width=3)
        ))

        fig_rev.update_layout(
            title='Accrual Revenue vs Active Users theo Tháng',
            yaxis=dict(title='Doanh Thu (VND)'),
            yaxis2=dict(title='Số User Active', overlaying='y', side='right'),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_rev, use_container_width=True)

    # TAB 2: COHORT ANALYSIS
    with tab2:
        st.subheader("Phân Tích Cohort Retention")
        st.caption("Tỷ lệ % khách hàng tiếp tục sử dụng dịch vụ (Retention) qua các tháng kể từ khi gia nhập.")

        retention_matrix, cohort_size = calculate_cohorts(df_clean, daily_df)

        if not retention_matrix.empty:
            # Chuyển index thành string để hiển thị đẹp
            retention_matrix.index = retention_matrix.index.astype(str)

            # Chuẩn bị dữ liệu vẽ Heatmap
            z = retention_matrix.values * 100
            x = retention_matrix.columns.astype(str)
            y = retention_matrix.index.tolist()

            # Tạo text hiển thị trên từng ô
            text_data = [[f"{val:.1f}%" if not pd.isna(val) else "" for val in row] for row in z]

            fig_cohort = go.Figure(data=go.Heatmap(
                z=z, x=x, y=y,
                text=text_data, texttemplate="%{text}",
                colorscale='Blues', hoverongaps=False
            ))

            fig_cohort.update_layout(
                xaxis_title="Tháng thứ n (kể từ khi mua lần đầu)",
                yaxis_title="Tháng Gia Nhập (Cohort)",
                height=600
            )
            st.plotly_chart(fig_cohort, use_container_width=True)

            with st.expander("Xem chi tiết số lượng khách hàng (Cohort Size)"):
                st.dataframe(cohort_size.reset_index().rename(columns={0: 'Cohort Size'}))
        else:
            st.info("Chưa đủ dữ liệu để vẽ biểu đồ Cohort.")

    # TAB 3: DATA PREVIEW
    with tab3:
        st.subheader("Dữ liệu gốc (đã làm sạch)")
        st.dataframe(df_clean)


if __name__ == "__main__":
    main()
