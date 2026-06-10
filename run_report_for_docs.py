#!/usr/bin/env python3
"""
Script tạo báo cáo ứng viên thực tế + HTML + chụp ảnh cho tài liệu
"""
import io, json, os, sys, warnings, hashlib, time
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")

# ─── Paths & env ──────────────────────────────────────────────────────────────
APP_DIR  = Path("/Users/_qh.fol_/frappe-bench/apps/ai_ats")
AI_DIR   = Path("/Users/_qh.fol_/AI_ATS")
OUT_DIR  = Path("/Users/_qh.fol_/.gemini/antigravity-ide/brain/c209b6ea-a7d9-4b64-a951-2459f413a1ef/screenshots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY = "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"

# ─── Input URLs & files ────────────────────────────────────────────────────────
AI_TEST_URL = "https://hr-dev.ctgroupvietnam.com/survey/print/888e33e9-fdba-4da7-9f3a-d670f0cf7f20?answer_token=37a3d8e6-35cf-42c0-828e-c8020e044eaa"
G5_TEST_URL = "https://hr-dev.ctgroupvietnam.com/survey/print/01146d26-7f68-4390-b0d4-5bb683b02aee?answer_token=bad215b1-dee6-4409-a098-f4e02f8e937c"
EQ_TEST_URL = "https://jobtest.vn/test/report/6a067fcf3289816e794732c3"
CV_PDF_PATH = AI_DIR / "BDLUV - IT TEST TRUONG HOANG VU (full kn) 1.pdf"
AI_SCORING_PDF  = AI_DIR / "CTG-KNC-TD-QĐ04.BM02-HƯỚNG DẪN CHẤM ĐIỂM BÀI TEST NĂNG LỰC AI (1).pdf"
SWAT_PRD_DOCX   = AI_DIR / "18052026_RD - PRD - AI Candidate Persona Report.docx"
G5_SCORING_DOCX = AI_DIR / "CTG-KNC-TD-QT01.BM16 - BỘ CÂU HỎI ĐÁNH GIÁ TIỀM NĂNG ỨNG VIÊN 4.docx"

JD_TEXT = """
JOB DESCRIPTION: Full-Stack Developer (AI-First)
Công ty: CT Group – Ban DAIT (Digital AI Innovation & Transformation)
Vị trí: Kỹ sư Phát triển Full-Stack (AI-First)
Cấp bậc: Middle → Senior
Địa điểm: TP. Hồ Chí Minh

MÔ TẢ CÔNG VIỆC:
- Phát triển và duy trì các hệ thống nội bộ sử dụng Python/FastAPI + Vue.js/React
- Xây dựng và tích hợp AI Agent vào quy trình vận hành (LLM APIs: GPT-4o, Gemini, Claude)
- Thiết kế database (MySQL/PostgreSQL), REST API, và hệ thống xử lý dữ liệu lớn
- Làm việc trực tiếp với Frappe Framework (ERPNext) để custom và mở rộng tính năng
- Phát triển pipeline ETL, automation workflow và báo cáo tự động
- Code review, viết tài liệu kỹ thuật, mentor junior developer

YÊU CẦU BẮT BUỘC:
- 2+ năm kinh nghiệm Python (FastAPI/Flask/Django)
- Thành thạo JavaScript/TypeScript + Vue.js hoặc React
- Hiểu biết sâu về RESTful API, microservices architecture
- Có kinh nghiệm với LLM APIs (OpenAI, Anthropic, Google AI)
- Sử dụng AI tools hàng ngày trong công việc (Cursor, Copilot, v.v.)
- Mindset AI-First: luôn tìm cách tự động hóa bằng AI

YÊU CẦU PHỤ:
- Kinh nghiệm với Frappe Framework / ERPNext là lợi thế lớn
- Biết Docker, CI/CD, Git workflow
- Tiếng Anh đọc hiểu tài liệu kỹ thuật
- Kỹ năng trình bày và giao tiếp rõ ràng

PHÚC LỢI:
- Lương: 25-45 triệu VNĐ (thỏa thuận theo năng lực)
- Môi trường AI-First, làm việc với công nghệ mới nhất
- Đào tạo AI liên tục, budget cho tools và khóa học
- Làm việc trực tiếp với leadership, ít bureaucracy
"""

# ─── Helpers ──────────────────────────────────────────────────────────────────
import requests
from bs4 import BeautifulSoup
import pypdf

def scrape(url):
    if not url: return "[Chưa có]"
    try:
        r = requests.get(url, timeout=30, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script","style","nav","footer","header"]): t.decompose()
        txt = soup.get_text(separator="\n", strip=True)
        return txt if len(txt) > 100 else f"[Rỗng: {url}]"
    except Exception as e:
        return f"[Lỗi: {e}]"

def pdf_text(path):
    b = Path(path).read_bytes()
    r = pypdf.PdfReader(io.BytesIO(b))
    return "\n".join(p.extract_text() or "" for p in r.pages).strip()

def docx_text(path):
    from docx import Document as DocxDocument
    doc = DocxDocument(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for i, t in enumerate(doc.tables):
        parts.append(f"[TABLE {i+1}]")
        for row in t.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts).strip()

# ─── System Prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Bạn là AI Agent đánh giá ứng viên cho CT Group (NoAI-NoHire).
Áp dụng quy tắc xuất báo cáo gồm 2 phần BẮT BUỘC:

Phần I: Tổng quan Hồ sơ & Điểm số (Executive Summary)
- AI Readiness Index (Chỉ số sẵn sàng AI): Điểm số tổng hợp (Thang điểm 100) -> ai_test_total.
- Phân loại Ứng viên (ai_test_label): Dựa trên kết quả, phân loại thành [AI-Ready] hoặc [Non-AI].
- Chấm điểm SWAT Elite (Thang 10) -> swat_total.
- Kết quả SWAT Elite (swat_label): Đánh giá [Swat-Elite] (nếu swat_total >= 6.0) hoặc [KHÔNG ĐẠT] (nếu swat_total < 6.0).
- Chấm điểm 5G Test (Thang 100) -> g5_total.
- QUY TẮC: nếu ai_test_label là "Non-AI" HOẶC g5_total < 60.0 HOẶC swat_total < 6.0, thì decision = "KHÔNG ĐẠT".

Phần II: Phân tích Năng lực Chuyên sâu
Mỗi nhận xét PHẢI kèm evidence theo format: "→ [NGUỒN] \"trích dẫn\""

CHỈ trả JSON theo schema:
{
  "candidate_name":"", "position":"", "email":"", "phone":"",
  "ai_test_table":[
    {"cau":1,"noi_dung":"AI Awareness","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":2,"noi_dung":"AI Daily Use","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":3,"noi_dung":"AI Self-Assessment","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":4,"noi_dung":"AI Problem Solving","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":5,"noi_dung":"Prompt Engineering","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":6,"noi_dung":"AI x Teamwork","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":7,"noi_dung":"AI Productivity","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":8,"noi_dung":"AI Mindset","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":9,"noi_dung":"AI Limitation","diem_toi_da":10,"diem_cham":0,"ly_do":""},
    {"cau":10,"noi_dung":"AI Growth Plan","diem_toi_da":10,"diem_cham":0,"ly_do":""}
  ],
  "ai_test_total":0, "ai_test_label":"AI-Ready",
  "swat_table":[
    {"tru_cot":"AI First Mindset","ty_trong":"50%","diem_tho":0,"diem_trong_so":0.0,"co_so":""},
    {"tru_cot":"2AS Execution Capability","ty_trong":"20%","diem_tho":0,"diem_trong_so":0.0,"co_so":""},
    {"tru_cot":"Practical Efficiency & Productivity","ty_trong":"20%","diem_tho":0,"diem_trong_so":0.0,"co_so":""},
    {"tru_cot":"Risk Control & Language","ty_trong":"10%","diem_tho":0,"diem_trong_so":0.0,"co_so":""}
  ],
  "swat_total":0.0, "swat_label":"ĐẠT",
  "g5_table":[
    {"tieu_chi":"G1 – Giao tiếp (Communication)","diem_toi_da":20,"diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G2 – Giao lưu/Cọ xát thực tế (Exposure & Interaction)","diem_toi_da":20,"diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G3 – Giám sát (Supervision)","diem_toi_da":20,"diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G4 – Giải quyết vấn đề/Gỡ rối (Problem Solving)","diem_toi_da":20,"diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G5 – Giảng dạy/Hướng dẫn (Teaching & Mentoring)","diem_toi_da":20,"diem_cham":0.0,"ly_do":""}
  ],
  "g5_total": 0.0,
  "strength_tech_skills": "", "strength_exceeding": "",
  "gap_missing_skills": "", "gap_risks": "",
  "best_at_core": "", "best_at_2as_ops": "", "best_at_2as_ready": "", "best_at_global": "",
  "decision":"ĐẠT"
}"""

# ─── Main execution ────────────────────────────────────────────────────────────
print("=" * 60)
print("🚀 Bắt đầu tạo báo cáo ứng viên...")
print("=" * 60)

# 1. Scrape tất cả URLs
print("\n📡 Scraping test URLs...")
print(f"  AI Test: {AI_TEST_URL[:70]}...")
ai_txt = scrape(AI_TEST_URL)
print(f"  → {len(ai_txt)} chars")

print(f"  5G Test: {G5_TEST_URL[:70]}...")
g5_txt = scrape(G5_TEST_URL)
print(f"  → {len(g5_txt)} chars")

print(f"  IQ Test: {EQ_TEST_URL[:70]}...")
eq_txt = scrape(EQ_TEST_URL)
print(f"  → {len(eq_txt)} chars")

# 2. Đọc CV
print(f"\n📄 Đọc CV PDF...")
cv_text = pdf_text(CV_PDF_PATH)
print(f"  → {len(cv_text)} chars")

# 3. Đọc scoring guides
print("\n📚 Đọc scoring guides...")
ai_guide = pdf_text(AI_SCORING_PDF) if AI_SCORING_PDF.exists() else ""
swat_prd = docx_text(SWAT_PRD_DOCX) if SWAT_PRD_DOCX.exists() else ""
g5_guide = docx_text(G5_SCORING_DOCX) if G5_SCORING_DOCX.exists() else ""
print(f"  AI guide: {len(ai_guide)} chars")
print(f"  SWAT PRD: {len(swat_prd)} chars")
print(f"  5G guide: {len(g5_guide)} chars")

# 4. Tạo user message
user_msg = f"""
### CV: {cv_text[:8000]}
### JD: {JD_TEXT[:5000]}
### AI SCORING GUIDE: {ai_guide[:12000]}
### SWAT PRD: {swat_prd[:10000]}
### G5 GUIDE: {g5_guide[:15000]}
### TEST AI (link): {ai_txt[:8000]}
### TEST 5G (link): {g5_txt[:8000]}
### IQ/EQ TEST (link): {eq_txt[:3000]}
Ngày: {datetime.now().strftime("%d/%m/%Y %H:%M")}
Trả về JSON hợp lệ, điền đủ mọi trường. Viết ly_do, co_so, và các phân tích bằng tiếng Việt có evidence cụ thể."""

# 5. Gọi GPT-4o
print("\n🤖 Gọi GPT-4o...")
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_msg}
    ],
    response_format={"type": "json_object"},
    temperature=0.2,
    max_tokens=4500,
)

data = json.loads(resp.choices[0].message.content)
print(f"  ✅ Xong! Tokens: {resp.usage.prompt_tokens}p + {resp.usage.completion_tokens}c")
print(f"  Ứng viên: {data.get('candidate_name', 'N/A')}")
print(f"  AI Score: {data.get('ai_test_total', 0)}/100 [{data.get('ai_test_label', '')}]")
print(f"  SWAT:     {data.get('swat_total', 0)}/10 [{data.get('swat_label', '')}]")
print(f"  5G:       {data.get('g5_total', 0)}/100")
print(f"  Decision: {data.get('decision', '')}")

# 6. Lưu JSON
json_path = OUT_DIR / "report_data.json"
json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n💾 Saved JSON: {json_path}")

# ─── Render HTML báo cáo ──────────────────────────────────────────────────────
decision = data.get("decision", "KHÔNG ĐẠT")
decision_color = "#16a34a" if "ĐẠT" in decision and "KHÔNG" not in decision else "#dc2626"
decision_bg    = "#f0fdf4" if "ĐẠT" in decision and "KHÔNG" not in decision else "#fef2f2"
ai_label       = data.get("ai_test_label", "")
ai_label_color = "#16a34a" if ai_label == "AI-Ready" else "#dc2626"

def nl2br(s):
    return (s or "").replace("\n", "<br>")

def score_badge(score, max_score=100):
    pct = (score / max_score) * 100 if max_score else 0
    if pct >= 80: color = "#16a34a"
    elif pct >= 60: color = "#d97706"
    else: color = "#dc2626"
    return f'<span style="color:{color};font-weight:700;font-size:1.3em">{score}</span><span style="color:#6b7280;font-size:0.9em">/{max_score}</span>'

ai_rows = ""
for r in data.get("ai_test_table", []):
    pct = (r.get("diem_cham", 0) / r.get("diem_toi_da", 10)) * 100
    bar_color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 60 else "#dc2626"
    ai_rows += f"""<tr>
      <td style="padding:8px 12px;color:#374151">Câu {r.get('cau','')}: {r.get('noi_dung','')}</td>
      <td style="padding:8px 12px;text-align:center;font-weight:600">{r.get('diem_cham',0)}/{r.get('diem_toi_da',10)}</td>
      <td style="padding:8px 12px">
        <div style="background:#e5e7eb;border-radius:4px;height:8px">
          <div style="background:{bar_color};width:{pct:.0f}%;height:8px;border-radius:4px"></div>
        </div>
      </td>
      <td style="padding:8px 12px;color:#6b7280;font-size:0.85em">{r.get('ly_do','')[:120]}</td>
    </tr>"""

swat_rows = ""
for r in data.get("swat_table", []):
    swat_rows += f"""<tr>
      <td style="padding:8px 12px;color:#374151">{r.get('tru_cot','')}</td>
      <td style="padding:8px 12px;text-align:center;color:#6b7280">{r.get('ty_trong','')}</td>
      <td style="padding:8px 12px;text-align:center;font-weight:600">{r.get('diem_tho',0)}/10</td>
      <td style="padding:8px 12px;text-align:center;font-weight:700;color:#4f46e5">{r.get('diem_trong_so',0):.1f}</td>
      <td style="padding:8px 12px;color:#6b7280;font-size:0.85em">{r.get('co_so','')[:100]}</td>
    </tr>"""

g5_rows = ""
for r in data.get("g5_table", []):
    pct = (r.get("diem_cham", 0) / r.get("diem_toi_da", 20)) * 100
    bar_color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 60 else "#dc2626"
    g5_rows += f"""<tr>
      <td style="padding:8px 12px;color:#374151">{r.get('tieu_chi','')}</td>
      <td style="padding:8px 12px;text-align:center;font-weight:600">{r.get('diem_cham',0)}/{r.get('diem_toi_da',20)}</td>
      <td style="padding:8px 12px">
        <div style="background:#e5e7eb;border-radius:4px;height:8px">
          <div style="background:{bar_color};width:{pct:.0f}%;height:8px;border-radius:4px"></div>
        </div>
      </td>
      <td style="padding:8px 12px;color:#6b7280;font-size:0.85em">{r.get('ly_do','')[:150]}</td>
    </tr>"""

html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Báo cáo Ứng viên – {data.get('candidate_name','')}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', -apple-system, sans-serif; background: #f1f5f9; color: #1e293b; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
  .header {{ background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%); color: white; border-radius: 16px; padding: 32px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }}
  .header-left h1 {{ font-size: 1.8em; font-weight: 700; margin-bottom: 4px; }}
  .header-left p {{ opacity: 0.8; font-size: 0.95em; }}
  .decision-badge {{ background: {decision_bg}; color: {decision_color}; border: 2px solid {decision_color}; border-radius: 12px; padding: 16px 28px; text-align: center; font-size: 1.4em; font-weight: 800; letter-spacing: 1px; }}
  .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }}
  .score-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .score-card .label {{ color: #6b7280; font-size: 0.8em; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
  .score-card .value {{ font-size: 2.2em; font-weight: 800; color: #1e293b; }}
  .score-card .badge {{ display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.8em; font-weight: 600; margin-top: 6px; }}
  .badge-green {{ background: #dcfce7; color: #16a34a; }}
  .badge-red {{ background: #fee2e2; color: #dc2626; }}
  .badge-blue {{ background: #dbeafe; color: #2563eb; }}
  .section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .section-title {{ font-size: 1.1em; font-weight: 700; color: #1e293b; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px; }}
  .section-title .icon {{ font-size: 1.2em; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th {{ background: #f8fafc; color: #374151; font-weight: 600; padding: 10px 12px; text-align: left; border-bottom: 2px solid #e5e7eb; }}
  td {{ border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
  tr:hover td {{ background: #f8fafc; }}
  .analysis-block {{ background: #f8fafc; border-radius: 8px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #4338ca; }}
  .analysis-block h4 {{ font-size: 0.85em; font-weight: 600; color: #4338ca; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
  .analysis-block p {{ color: #374151; font-size: 0.9em; line-height: 1.7; }}
  .gap-block {{ border-left-color: #dc2626; }}
  .gap-block h4 {{ color: #dc2626; }}
  .best-block {{ border-left-color: #16a34a; }}
  .best-block h4 {{ color: #16a34a; }}
  .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 20px; }}
  .info-item {{ background: #f8fafc; border-radius: 8px; padding: 12px 16px; }}
  .info-item .key {{ color: #6b7280; font-size: 0.8em; font-weight: 500; }}
  .info-item .val {{ color: #1e293b; font-weight: 600; font-size: 0.95em; }}
  .footer {{ text-align: center; color: #94a3b8; font-size: 0.8em; padding: 20px; }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <h1>🤖 AI Candidate Report</h1>
      <p>CT Group · Ban DAIT · Hệ thống đánh giá ứng viên tự động</p>
      <p style="margin-top:8px;opacity:0.7">Ngày: {datetime.now().strftime("%d/%m/%Y %H:%M")} · Mô hình: GPT-4o</p>
    </div>
    <div class="decision-badge">
      {"✅" if "ĐẠT" in decision and "KHÔNG" not in decision else "❌"} {decision}
    </div>
  </div>

  <!-- Info ứng viên -->
  <div class="section">
    <div class="section-title"><span class="icon">👤</span> Thông tin Ứng viên</div>
    <div class="info-grid">
      <div class="info-item"><div class="key">Họ và tên</div><div class="val">{data.get('candidate_name','N/A')}</div></div>
      <div class="info-item"><div class="key">Vị trí ứng tuyển</div><div class="val">{data.get('position','N/A')}</div></div>
      <div class="info-item"><div class="key">Email</div><div class="val">{data.get('email','N/A')}</div></div>
      <div class="info-item"><div class="key">Điện thoại</div><div class="val">{data.get('phone','N/A')}</div></div>
    </div>
  </div>

  <!-- Score summary -->
  <div class="grid-3">
    <div class="score-card">
      <div class="label">🧠 AI Readiness Index</div>
      <div class="value">{data.get('ai_test_total',0)}<span style="font-size:0.5em;color:#6b7280">/100</span></div>
      <div class="badge {'badge-green' if ai_label=='AI-Ready' else 'badge-red'}">{ai_label}</div>
    </div>
    <div class="score-card">
      <div class="label">⚡ SWAT Elite Score</div>
      <div class="value">{data.get('swat_total',0)}<span style="font-size:0.5em;color:#6b7280">/10</span></div>
      <div class="badge {'badge-green' if float(data.get('swat_total',0))>=6 else 'badge-red'}">{data.get('swat_label','')}</div>
    </div>
    <div class="score-card">
      <div class="label">🎯 5G Potential Score</div>
      <div class="value">{data.get('g5_total',0)}<span style="font-size:0.5em;color:#6b7280">/100</span></div>
      <div class="badge {'badge-green' if float(data.get('g5_total',0))>=75 else 'badge-blue' if float(data.get('g5_total',0))>=60 else 'badge-red'}">{'Giỏi' if float(data.get('g5_total',0))>=75 else 'Trung bình' if float(data.get('g5_total',0))>=60 else 'Không phù hợp'}</div>
    </div>
  </div>

  <!-- AI Test Table -->
  <div class="section">
    <div class="section-title"><span class="icon">🧠</span> Chi tiết Bài test AI – {data.get('ai_test_total',0)}/100</div>
    <table>
      <thead><tr><th>Tiêu chí</th><th style="text-align:center">Điểm</th><th>Progress</th><th>Lý do</th></tr></thead>
      <tbody>{ai_rows}</tbody>
    </table>
  </div>

  <!-- SWAT Table -->
  <div class="section">
    <div class="section-title"><span class="icon">⚡</span> SWAT Elite Assessment – {data.get('swat_total',0)}/10</div>
    <table>
      <thead><tr><th>Trụ cột</th><th style="text-align:center">Tỷ trọng</th><th style="text-align:center">Điểm thô</th><th style="text-align:center">Điểm trọng số</th><th>Cơ sở đánh giá</th></tr></thead>
      <tbody>{swat_rows}</tbody>
    </table>
  </div>

  <!-- 5G Table -->
  <div class="section">
    <div class="section-title"><span class="icon">🎯</span> Bài test 5G (Tiềm năng Quản lý) – {data.get('g5_total',0)}/100</div>
    <table>
      <thead><tr><th>Tiêu chí</th><th style="text-align:center">Điểm</th><th>Progress</th><th>Lý do</th></tr></thead>
      <tbody>{g5_rows}</tbody>
    </table>
  </div>

  <!-- Strengths -->
  <div class="section">
    <div class="section-title"><span class="icon">💪</span> Điểm Mạnh (Strengths)</div>
    <div class="analysis-block best-block">
      <h4>Kỹ năng công nghệ & Năng lực chuyên môn</h4>
      <p>{nl2br(data.get('strength_tech_skills',''))}</p>
    </div>
    <div class="analysis-block best-block">
      <h4>Năng lực vượt chuẩn JD (Added Value)</h4>
      <p>{nl2br(data.get('strength_exceeding',''))}</p>
    </div>
  </div>

  <!-- Gaps -->
  <div class="section">
    <div class="section-title"><span class="icon">⚠️</span> Điểm Hạn chế (Gaps & Risks)</div>
    <div class="analysis-block gap-block">
      <h4>Kỹ năng/Năng lực còn thiếu</h4>
      <p>{nl2br(data.get('gap_missing_skills',''))}</p>
    </div>
    <div class="analysis-block gap-block">
      <h4>Rủi ro vận hành & Bảo mật</h4>
      <p>{nl2br(data.get('gap_risks',''))}</p>
    </div>
  </div>

  <!-- Best At -->
  <div class="section">
    <div class="section-title"><span class="icon">🏆</span> Năng lực Nổi bật Nhất (Best At)</div>
    <div class="analysis-block">
      <h4>Chuyên môn Core</h4>
      <p>{nl2br(data.get('best_at_core',''))}</p>
    </div>
    <div class="analysis-block">
      <h4>Vận hành 2AS Tools</h4>
      <p>{nl2br(data.get('best_at_2as_ops',''))}</p>
    </div>
    <div class="analysis-block">
      <h4>Mức độ sẵn sàng AI</h4>
      <p>{nl2br(data.get('best_at_2as_ready',''))}</p>
    </div>
    <div class="analysis-block">
      <h4>Ngoại ngữ & Thực chiến quốc tế</h4>
      <p>{nl2br(data.get('best_at_global',''))}</p>
    </div>
  </div>

  <div class="footer">
    🤖 Báo cáo được tạo tự động bởi AI ATS · CT Group 2026 · Powered by GPT-4o
  </div>
</div>
</body>
</html>"""

html_path = OUT_DIR / "report.html"
html_path.write_text(html, encoding="utf-8")
print(f"💾 Saved HTML: {html_path}")
print("\n✅ Script hoàn thành! Chạy screenshot bằng Playwright...")
