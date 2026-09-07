# AI ATS - Chấm điểm & Sàng lọc CV bằng AI

Frappe App tự động chấm điểm ứng viên và sàng lọc CV dựa trên Job Description, sử dụng OpenAI GPT-4o.

- Repo: [qh-fol-in-luv-w-data/ai-ats-cv-scoring](https://github.com/qh-fol-in-luv-w-data/ai-ats-cv-scoring)
- Frappe app: `ai_ats`

## Tính năng chính

- Chấm điểm bài test (AI Test / 5G / EQ, hỗ trợ Odoo Survey và Jobtest.vn), sinh báo cáo Persona kèm SWAT.
- Ghép 1 CV với danh sách nhiều JD, xếp hạng và giải thích mức độ phù hợp.
- Đọc CV từ PDF/DOCX hoặc scrape trực tiếp từ public link.
- Kết quả lưu chuẩn Frappe, có audit log đầy đủ.

## Yêu cầu

- Frappe Bench v15, Python 3.10+, Node.js 18+.
- `OPENAI_API_KEY`.

## Cài đặt

```bash
cd frappe-bench
bench get-app ai_ats https://github.com/qh-fol-in-luv-w-data/ai-ats-cv-scoring
bench --site <site> install-app ai_ats
./env/bin/pip install -r apps/ai_ats/requirements.txt
```

Cấu hình key qua bench config hoặc `.env` trong thư mục app:

```bash
bench --site <site> set-config openai_api_key "sk-..."
```

Frontend:

```bash
cd apps/ai_ats/frontend
npm install
npm run build   # dev: npm run dev
```

## Xác thực API

Tạo API key + secret trong `/desk#user` → **API Access**, gọi API với header:

```
Authorization: token <api_key>:<api_secret>
```

## License

MIT © CT Group
