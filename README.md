# AI ATS - Chấm điểm & Sàng lọc CV bằng AI (Frappe App)

AI ATS là một Frappe App tự động hoá quá trình đánh giá ứng viên: chấm điểm bài test (Odoo Survey / Jobtest.vn / 5G / AI Test / EQ), sàng lọc CV theo Job Description và ghép 1 CV với nhiều JD — sử dụng OpenAI GPT-4o.

- Repo: [qh-fol-in-luv-w-data/ai-ats-cv-scoring](https://github.com/qh-fol-in-luv-w-data/ai-ats-cv-scoring)
- Frappe app name: `ai_ats`

## Tính năng nổi bật

- **1 CV → 1 báo cáo Persona**: chấm điểm bài AI Test / 5G / EQ, tổng hợp SWAT, phân tích điểm mạnh/yếu.
- **1 CV → N Jobs (Job Matcher)**: quét hàng loạt JD, cho điểm % phù hợp và giải thích.
- **Trích xuất tự động**: hỗ trợ file DOCX, PDF hoặc scrape trực tiếp từ Public Link (Odoo Survey, Jobtest.vn) qua Playwright.
- **Lưu chuẩn Frappe**: kết quả ghi vào DocType `AI Candidate Report` và `AI Job Match Result`, có audit qua `ATS Session` / `ATS Action Log` / `ATS AI Call Log`.

## Cấu trúc thư mục

```
.
├── ai_ats/                         # Frappe app
│   ├── api.py                      # Endpoint chính: generate_candidate_report,
│   │                               # generate_candidate_only_report, score_tests, score_single, get_context
│   ├── job_matcher.py              # Endpoint match_candidate_jobs (1 CV vs N JD)
│   ├── generate_token.py           # Sinh Frappe API token
│   ├── test_score.py               # Logic chấm điểm bài test
│   ├── create_doctype.py           # Bootstrap DocType
│   ├── hooks.py                    # SPA route /aicenter/2as-ats
│   ├── ai_ats/doctype/             # DocType: ai_candidate_report, ai_job_match_result,
│   │                               # ats_session, ats_action_log, ats_ai_call_log
│   ├── utils/activity_logger.py    # Ghi log activity/AI call
│   ├── www/                        # Web template gắn SPA
│   └── public/frontend/            # Vite build output
├── frontend/                       # Vue 3 SPA (Vite)
├── docs/security/                  # Báo cáo bảo mật
├── docx_images/                    # Ảnh dùng cho file DOCX xuất báo cáo
├── pyproject.toml                  # setuptools; dep: openai, requests, pypdf, python-docx, bs4, lxml
├── requirements.txt
└── README.md
```

## Cài đặt

### 1. Cài app vào Frappe Bench

```bash
cd frappe-bench
bench get-app ai_ats https://github.com/qh-fol-in-luv-w-data/ai-ats-cv-scoring
bench --site <site> install-app ai_ats
```

### 2. Python dependencies

```bash
cd frappe-bench
./env/bin/pip install -r apps/ai_ats/requirements.txt

# Playwright dùng để scrape Odoo/Jobtest.vn
./env/bin/pip install playwright
./env/bin/playwright install chromium
```

### 3. Environment / API keys

Tạo `.env` tại `apps/ai_ats/ai_ats/.env`:

```env
OPENAI_API_KEY=sk-...
```

hoặc set qua bench config:

```bash
bench --site <site> set-config openai_api_key "sk-..."
```

### 4. Build Frontend

```bash
cd apps/ai_ats/frontend
npm install
npm run build   # output → ../ai_ats/public/frontend/
```

Dev server: `npm run dev` (port 5174/5175, có Vite proxy → `localhost:8000`).

### 5. Chạy

```bash
cd frappe-bench
bench start
```

Truy cập SPA tại `http://localhost:8000/aicenter/2as-ats`.

## Xác thực API (Frappe token)

Tạo API key + secret trong `/desk#user` → **API Access**, dùng header:

```
Authorization: token <api_key>:<api_secret>
```

## Whitelisted API

Tất cả prefix `/api/method/`:

| Endpoint | Mô tả |
|---|---|
| `ai_ats.api.generate_candidate_report` | Chấm CV + N bài test → báo cáo Persona đầy đủ |
| `ai_ats.api.generate_candidate_only_report` | Chỉ phân tích CV, không có bài test |
| `ai_ats.api.score_tests` | Chấm loạt bài test (Odoo AI / 5G / EQ) |
| `ai_ats.api.score_single` | Chấm 1 bài test (url + type) |
| `ai_ats.api.get_context` | Context SPA (session, user, config) |
| `ai_ats.job_matcher.match_candidate_jobs` | Ghép 1 CV với danh sách nhiều JD |

### Ví dụ: generate_candidate_report

```
POST /api/method/ai_ats.api.generate_candidate_report
Authorization: token <key>:<secret>
Content-Type: multipart/form-data
```

Fields:

- `ai_test_url` hoặc `ai_test_file` – bài AI Test (Odoo)
- `g5_test_url` hoặc `g5_test_file` – bài 5G
- `eq_test_url` – link Jobtest.vn
- `cv_file` (**bắt buộc**) – CV PDF/DOCX
- `jd_text` – nội dung JD
- `api_use_cache=0` để bỏ qua cache và bắt chấm lại

### Ví dụ: match_candidate_jobs

```
POST /api/method/ai_ats.job_matcher.match_candidate_jobs
```

- `cv_file` – CV PDF/DOCX
- `jobs_json` – JSON list, ví dụ:

```json
[{"id": 1, "title": "Dev", "jd_text": "Cần tuyển..."}]
```

## Công nghệ

- Backend: Python 3.10+, Frappe v15, OpenAI GPT-4o, Playwright (scrape).
- Data: MariaDB / Frappe DocType.
- Frontend: Vue 3.4, Vite 5, vanilla CSS.

## License

MIT © CT Group
