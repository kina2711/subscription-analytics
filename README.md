# Subscription Analytics Dashboard

## 1. Executive Summary (Business Context)

Dự án này giải quyết bài toán phân tích hiệu suất kinh doanh cho mô hình SaaS/Subscription trong lĩnh vực EdTech. Mục tiêu là chuyển đổi dữ liệu giao dịch thô (Orders) thành các chỉ số tài chính và hành vi khách hàng có ý nghĩa chiến lược cho nhà đầu tư (VC).

**Vấn đề cốt lõi:**

Dữ liệu gốc ghi nhận theo phương pháp Kế toán tiền mặt (Cash-based), gây ra sự biến động ảo về doanh thu (ví dụ: tháng nhận tiền gói 1 năm doanh thu tăng vọt, các tháng sau bằng 0).

**Giải pháp:**

Xây dựng pipeline xử lý dữ liệu tự động để:

1. **Chuyển đổi sang Accrual Revenue:** Phân bổ doanh thu theo từng ngày thực tế sử dụng dịch vụ.
    
2. **Đo lường Retention chuẩn xác:** Sử dụng phương pháp _Activity-based Retention_ thay vì _Purchase-based_ để phản ánh đúng bản chất của các gói dài hạn.
    

## 2. Key Metrics & Methodology

### Accrual Revenue (Doanh thu dồn tích)

- **Định nghĩa:** Doanh thu được ghi nhận khi dịch vụ được cung cấp, không phải khi tiền được thanh toán.
    
- **Cách tính:**
    
    - `Daily Revenue` = `Total Contract Value` / `Duration Days`.
        
    - Sử dụng kỹ thuật "Data Explosion": Nhân bản mỗi đơn hàng thành N dòng (tương ứng số ngày sử dụng) để tính tổng doanh thu active trong bất kỳ ngày nào.
        

### Active Users (User Active)

- **Định nghĩa:** Khách hàng được coi là Active trong tháng nếu họ có ít nhất 1 ngày còn hạn sử dụng subscription.
    
- **Ý nghĩa:** Chỉ số này phản ánh đúng quy mô khách hàng thực tế được phục vụ, loại bỏ nhiễu do khách hàng rời bỏ hoặc chưa gia hạn.
    

### Cohort Retention (Activity-Based)

- **Định nghĩa:** Tỷ lệ % khách hàng của một đoàn hệ (theo tháng mua đầu tiên) vẫn còn "Active" ở các tháng tiếp theo.
    
- **Logic:** Khác với E-commerce truyền thống (tính retention khi khách mua lại), ở đây tôi tính retention dựa trên việc khách hàng **vẫn còn quyền lợi sử dụng**. Điều này đặc biệt quan trọng để đánh giá chất lượng của các gói dài hạn (6 tháng, 12 tháng).
    

## 3. Tech Stack

- **Language:** Python 3.9+
    
- **Core Libs:** Pandas (ETL & Manipulation), NumPy.
    
- **Visualization:** Plotly (Interactive Charts).
    
- **Framework:** Streamlit (Web App).
    
- **Data Source:** Google Sheets (Live Connection).
    

## 4. How to Run Locallybash

# 1. Clone repo

git clone

# 2. Install dependencies

pip install -r requirements.txt

# 3. Run app

streamlit run app.py

```

## 5. Project Structure
```

├── app.py # Main application logic

├── requirements.txt # Dependencies

└── README.md # Documentation

```

---
*Author: KIEN THAI TRUNG - Data Analyst*
```