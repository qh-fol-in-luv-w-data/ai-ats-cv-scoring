# AI ATS - Hệ thống Chấm điểm & Sàng lọc CV AI (Frappe App)

AI ATS là một ứng dụng mở rộng trên nền tảng Frappe, giúp tự động hóa quá trình đánh giá ứng viên, chấm điểm bài test Odoo/Jobtest.vn và sàng lọc CV dựa trên N Job Descriptions thông qua sức mạnh của OpenAI GPT-4o.

## 🚀 Tính năng nổi bật
- **Đánh Giá (1 CV - 1 Bài Test):** Đánh giá bài test EQ/IQ, SWAT Elite, AI Readiness và phân tích điểm mạnh, điểm yếu của ứng viên.
- **Gợi ý công việc (1 CV - N Jobs):** Upload 1 CV duy nhất và quét hàng loạt JD (Job Descriptions) để tìm ra vị trí phù hợp nhất, kèm điểm phần trăm (%) và phân tích cặn kẽ.
- **Tự động trích xuất:** Hỗ trợ đọc file DOCX, PDF hoặc cào dữ liệu trực tiếp từ Public Links (Odoo Survey, Jobtest.vn).
- **Lưu trữ chuẩn Frappe:** Tự động lưu báo cáo vào DocType `AI Candidate Report` và `AI Job Match Result`.

---

## 🛠 Hướng dẫn Cài đặt & Triển khai

### 1. Cài đặt App vào Frappe Bench
Trên máy chủ đã cài sẵn Frappe Bench, hãy chạy lệnh sau để kéo source code về:
```bash
cd frappe-bench
bench get-app ai_ats https://github.com/ctg-ai-data/2as-ats
```

Tiếp theo, cài đặt App vào Site của bạn (ví dụ site của bạn là `ct-datalake.localhost`):
```bash
bench --site ct-datalake.localhost install-app ai_ats
```

### 2. Cài đặt Python Dependencies
Ứng dụng yêu cầu một số thư viện Python để xử lý file và kết nối API.
Cài đặt trực tiếp vào môi trường ảo (virtual environment) của Frappe:
```bash
cd frappe-bench
./env/bin/pip install -r apps/ai_ats/requirements.txt
```

### 3. Cấu hình Environment Variables (.env)
Bên trong thư mục ứng dụng `apps/ai_ats/ai_ats`, tạo file `.env` (hoặc copy từ `.env.example` nếu có) để khai báo API Key:
```env
OPENAI_API_KEY=sk-xxxx...
```

### 4. Build Frontend (Vue.js)
Giao diện người dùng được xây dựng bằng Vue.js + Vite, đặt trong thư mục `frontend`.
Để ứng dụng có thể chạy mượt mà trên Frappe, bạn cần cài thư viện Node và Build:
```bash
cd apps/ai_ats/frontend
npm install
npm run build
```

*(Trong môi trường dev, bạn có thể chạy `npm run dev` để khởi chạy server Frontend ở port `5174/5175`).*

### 5. Cấp quyền API Token (Dành cho Postman / Frontend)
Hệ thống sử dụng xác thực Token của Frappe. Để tạo Token:
1. Vào hệ thống Frappe UI -> Tên user của bạn (góc phải trên) -> My Settings.
2. Tìm phần **API Access**, tạo **API Secret** (Nhớ lưu lại vì nó chỉ hiện 1 lần).
3. API Token sẽ có dạng: `token <api_key>:<api_secret>`.

Ví dụ Header gọi API:
`Authorization: token aae39b3ed483be2:78623a82878aba3`

---

## 📚 API Endpoints

### 1. API Tạo báo cáo đánh giá Ứng viên (Candidate Report)
- **Endpoint:** `POST /api/method/ai_ats.api.generate_candidate_report`
- **Mô tả:** Chấm điểm dựa trên file bài test và JD.
- **Payload (FormData):**
  - `ai_test_url` (Text): Link Odoo bài test AI (Hoặc dùng `ai_test_file`).
  - `g5_test_url` (Text): Link Odoo bài test 5G (Hoặc dùng `g5_test_file`).
  - `eq_test_url` (Text): Link Jobtest.vn.
  - `cv_file` (File): File CV PDF/DOCX (bắt buộc).
  - `jd_text` (Text): Nội dung Job Description.
  - `api_use_cache` (Text): Set = `0` để bắt AI chấm lại từ đầu, bỏ qua cache.

### 2. API Gợi ý công việc (Job Matcher)
- **Endpoint:** `POST /api/method/ai_ats.job_matcher.match_candidate_jobs`
- **Mô tả:** Match 1 CV với nhiều JD.
- **Payload (FormData):**
  - `cv_file` (File): File CV của ứng viên (PDF/DOCX).
  - `jobs_json` (JSON String): Danh sách các Jobs cần match. VD:
    `[{"id": 1, "title": "Dev", "jd_text": "Cần tuyển..."}]`

---

## 🖥 Công nghệ sử dụng
- Backend: Python, Frappe Framework, OpenAI API.
- Cấu trúc Data: MariaDB / Frappe DocType.
- Frontend: Vue 3, Vite, Vanilla CSS.
