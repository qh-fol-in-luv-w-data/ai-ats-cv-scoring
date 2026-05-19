"""
AI ATS – API Endpoints
/api/method/ai_ats.api.generate_candidate_report
"""
import io, json, warnings, hashlib, uuid
import frappe, requests
import pypdf
from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from openai import OpenAI
from pathlib import Path
from datetime import datetime
from ai_ats.utils.activity_logger import ActivityLogger, Timer

warnings.filterwarnings("ignore")

# ── Activity Logger ───────────────────────────────────────────────────────────
_logger = ActivityLogger(prefix="ATS", module="AI ATS")

# ── Internal scoring guides (cố định, không đổi) ─────────────────────────────
import os

# Thư mục chứa tài liệu nội bộ — set qua env var AI_ATS_DIR
_BASE = Path(os.getenv("AI_ATS_DIR", str(Path(__file__).parent.parent.parent.parent / "AI_ATS")))
_AI_SCORING_PDF  = _BASE / "CTG-KNC-TD-QĐ04.BM02-HƯỚNG DẪN CHẤM ĐIỂM BÀI TEST NĂNG LỰC AI (1).pdf"
_SWAT_PRD_DOCX   = _BASE / "18052026_RD - PRD - AI Candidate Persona Report.docx"
_G5_SCORING_DOCX = _BASE / "CTG-KNC-TD-QT01.BM16 - BỘ CÂU HỎI ĐÁNH GIÁ TIỀM NĂNG ỨNG VIÊN 4.docx"

# ── OpenAI client — đọc từ Frappe Single DocType hoặc env var ─────────────────
def _get_openai_key() -> str:
    try:
        return frappe.db.get_single_value("AI ATS Settings", "openai_api_key") or os.getenv("OPENAI_API_KEY", "")
    except Exception:
        return os.getenv("OPENAI_API_KEY", "")

_gpt = None
def _get_gpt():
    global _gpt
    if _gpt is None:
        _gpt = OpenAI(api_key=_get_openai_key())
    return _gpt

# ── Helpers ───────────────────────────────────────────────────────────────────

def _pdf_bytes(b: bytes) -> str:
    r = pypdf.PdfReader(io.BytesIO(b))
    return "\n".join(p.extract_text() or "" for p in r.pages).strip()

def _docx_bytes(b: bytes) -> str:
    doc = DocxDocument(io.BytesIO(b))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for i, t in enumerate(doc.tables):
        parts.append(f"[TABLE {i+1}]")
        for row in t.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts).strip()

def _read(path: Path) -> str:
    if not path.exists(): return ""
    b = path.read_bytes()
    return _pdf_bytes(b) if path.suffix == ".pdf" else _docx_bytes(b)

def _read_cached(path: Path, use_cache: bool = True) -> str:
    """Reads from file and caches into RAM using frappe.cache()"""
    if not path.exists(): return ""
    cache_key = f"ai_ats_doc_{path.name}"
    
    if use_cache:
        cached_content = frappe.cache().get_value(cache_key)
        if cached_content:
            return cached_content
    
    # Not in cache or cache bypassed, read from disk
    content = _read(path)
    # Cache for 24 hours (86400 seconds)
    frappe.cache().set_value(cache_key, content, expires_in_sec=86400)
    return content

def _scrape(url: str) -> str:
    if not url: return "[Chưa có]"
    try:
        r = requests.get(url, timeout=20, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script","style","nav","footer","header"]): t.decompose()
        txt = soup.get_text(separator="\n", strip=True)
        return txt if len(txt) > 100 else f"[Rỗng: {url}]"
    except Exception as e:
        return f"[Lỗi: {e}]"

# ── Schema prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """Bạn là AI Agent đánh giá ứng viên cho CT Group (NoAI-NoHire).
Áp dụng quy tắc xuất báo cáo gồm 2 phần BẮT BUỘC:

Phần I: Tổng quan Hồ sơ & Điểm số (Executive Summary)
- AI Readiness Index (Chỉ số sẵn sàng AI): Điểm số tổng hợp (Thang điểm 100) -> ai_test_total.
- Phân loại Ứng viên (ai_test_label): Dựa trên kết quả, phân loại thành [AI-Ready] hoặc [Non-AI].
- Chấm điểm SWAT Elite (Thang 10) -> swat_total.
- Kết quả SWAT Elite (swat_label): Đánh giá [Swat-Elite] (nếu swat_total >= 6.0) hoặc [KHÔNG ĐẠT] (nếu swat_total < 6.0).
- Chấm điểm 5G Test (Thang 10) -> g5_total.
- LƯU Ý CHỐNG BỊA ĐẶT (Hallucination): Điểm AI Test PHẢI được chấm hoàn toàn dựa trên nội dung TEST AI. Điểm SWAT và 5G PHẢI dựa hoàn toàn trên nội dung TEST 5G. Nếu nội dung test bị lỗi, rỗng hoặc thiếu thông tin, TUYỆT ĐỐI KHÔNG tự bịa điểm (phải cho 0 điểm).
- LỌC NHIỄU TÀI LIỆU HƯỚNG DẪN: Trong các tài liệu Hướng dẫn chấm điểm (Rubric) có thể có nhiều thông tin dư thừa. Bạn PHẢI BỎ QUA các phần râu ria và CHỈ TẬP TRUNG vào đúng "khung tiêu chuẩn chấm điểm" (barem/rubric) cốt lõi để đối chiếu với bài làm của ứng viên.
- QUY TẮC TÀN KHỐC ĐỂ RA QUYẾT ĐỊNH (decision): Vì công ty áp dụng "No AI - No Hire", nếu ai_test_label là "Non-AI" HOẶC g5_total < 6.0 HOẶC swat_total < 6.0, thì BẮT BUỘC Quyết định (decision) = "KHÔNG ĐẠT" (Cúc luôn!). Chỉ được đánh giá "ĐẠT" khi tất cả đều qua môn.

Phần II: Phân tích Năng lực Chuyên sâu (Core Analysis)
Phân tích theo đúng cấu trúc sau (PHẢI PHÂN TÍCH KỸ, ĐỐI CHIẾU CHÉO GIỮA CV, JD, BÀI TEST VÀ PHỎNG VẤN/SURVEY):
1. strengths (ĐIỂM MẠNH):
  - Kỹ năng công nghệ và năng lực chuyên môn nổi trội (Nhớ bám sát yêu cầu JD và kết hợp thông tin từ Survey) -> strength_tech_skills.
  - Các chỉ số đánh giá vượt chuẩn (Exceeding Standards) so với JD hiện tại -> strength_exceeding.
2. gaps (ĐIỂM HẠN CHẾ):
  - Kỹ năng/năng lực còn thiếu hoặc tư duy chưa tương thích với văn hóa AI First (Đối chiếu kỹ với những gì JD đòi hỏi và Survey) -> gap_missing_skills.
  - Các rủi ro về mặt vận hành hoặc bảo mật dữ liệu dựa trên các bài test -> gap_risks.
3. best_at (NĂNG LỰC NỔI BẬT NHẤT):
  - Chuyên môn mạnh nhất: Lĩnh vực lõi tạo giá trị ngay (Tổng hợp từ CV, JD và Survey) -> best_at_core.
  - Năng lực vận hành 2AS: Mức độ khai thác Agentic AI Staff (Harvey, Patlytics...) -> best_at_2as_ops.
  - Mức độ sẵn sàng sử dụng 2AS: Sự thích ứng, không e ngại giao việc cho AI -> best_at_2as_ready.
  - Ngoại ngữ & Thực chiến: Khả năng triển khai dự án thực tế trong môi trường quốc tế -> best_at_global.

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
  "g5_total": 0.0,
  "strength_tech_skills": "", "strength_exceeding": "",
  "gap_missing_skills": "", "gap_risks": "",
  "best_at_core": "", "best_at_2as_ops": "", "best_at_2as_ready": "", "best_at_global": "",
  "decision":"ĐẠT"
}"""

# ══════════════════════════════════════════════════════════════════════════════
@frappe.whitelist()
def generate_candidate_report(
    ai_test_url: str = "",
    g5_test_url: str = "",
    eq_test_url: str = "",
    survey_url: str = "",
    jd_text: str = "",
    cv_text: str = "",
    api_use_cache = 1,
):
    """
    INPUT  (qua form-data hoặc JSON payload):
        ai_test_url, g5_test_url, eq_test_url  – link bài test (bắt buộc)
        survey_url                              – link phỏng vấn (tuỳ chọn)
        jd_text                                 – nội dung JD (string)
        cv_text                                 – nội dung CV (nếu truyền thẳng text)
        cv_file                                 – file CV upload (pdf/docx)
        api_use_cache                           - dùng bộ nhớ đệm (mặc định 1)

    OUTPUT : dict + lưu vào DocType "AI Candidate Report"
    """
    # Convert use_cache to bool if passed as string
    if isinstance(api_use_cache, str):
        api_use_cache = api_use_cache.lower() in ['true', '1', 't', 'yes']
    else:
        api_use_cache = bool(api_use_cache)

    # CV từ upload (nếu có sẽ ghi đè cv_text)
    if frappe.request and frappe.request.files:
        f = frappe.request.files.get("cv_file")
        if f:
            raw = f.stream.read()
            cv_text = _pdf_bytes(raw) if (f.filename or "").lower().endswith(".pdf") else _docx_bytes(raw)

    # Scrape links (do caller truyền vào, không hard-code)
    ai_txt = _scrape(ai_test_url)
    g5_txt = _scrape(g5_test_url)
    eq_txt = _scrape(eq_test_url)
    sv_txt = _scrape(survey_url) if survey_url else "[Chưa có]"

    # Scoring guides nội bộ (Sử dụng cache RAM để tối ưu tốc độ)
    ai_guide = _read_cached(_AI_SCORING_PDF, api_use_cache)
    swat_prd = _read_cached(_SWAT_PRD_DOCX, api_use_cache)
    g5_guide = _read_cached(_G5_SCORING_DOCX, api_use_cache)

    user_msg = f"""
### CV: {cv_text[:8000]}
### JD: {jd_text[:5000]}
### AI SCORING GUIDE: {ai_guide[:15000]}
### SWAT PRD: {swat_prd[:15000]}
### G5 GUIDE: {g5_guide[:20000]}
### TEST AI (link): {ai_txt[:10000]}
### TEST 5G (link): {g5_txt[:10000]}
### EQ/IQ (link): {eq_txt[:5000]}
### PHỎNG VẤN: {sv_txt[:5000]}
Ngày: {datetime.now().strftime("%d/%m/%Y %H:%M")}
Trả về JSON hợp lệ, điền đủ mọi trường."""
    # ---- API CACHING ----
    if api_use_cache:
        raw_key = f"v4_{cv_text}{jd_text}{ai_test_url}{g5_test_url}{eq_test_url}{survey_url}"
        req_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        cache_key = f"ai_ats_api_resp_{req_hash}"
        cached_resp = frappe.cache().get_value(cache_key)
        if cached_resp:
            return cached_resp

    resp = _get_gpt().chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":_SYSTEM},{"role":"user","content":user_msg}],
        response_format={"type":"json_object"},
        temperature=0.2,
        max_tokens=4000,
    )
    data = json.loads(resp.choices[0].message.content)

    # Lưu DocType – 2 bảng dưới dạng JSON text
    doc = frappe.get_doc({
        "doctype":        "AI Candidate Report",
        "candidate_name": data.get("candidate_name") or "Unknown",
        "position":       data.get("position") or "",
        "email":          data.get("email") or "",
        "phone":          data.get("phone") or "",
        "analysis_date":  datetime.now(),
        "ai_test_url":    ai_test_url,
        "g5_test_url":    g5_test_url,
        "eq_test_url":    eq_test_url,
        "survey_url":     survey_url,
        "jd_text":        jd_text[:2000],
        "ai_test_total":  data.get("ai_test_total",0),
        "ai_test_label":  data.get("ai_test_label",""),
        "swat_total":     data.get("swat_total",0),
        "swat_label":     data.get("swat_label",""),
        "strength_tech_skills": data.get("strength_tech_skills",""),
        "strength_exceeding":   data.get("strength_exceeding",""),
        "gap_missing_skills":   data.get("gap_missing_skills",""),
        "gap_risks":            data.get("gap_risks",""),
        "best_at_core":         data.get("best_at_core",""),
        "best_at_2as_ops":      data.get("best_at_2as_ops",""),
        "best_at_2as_ready":    data.get("best_at_2as_ready",""),
        "best_at_global":       data.get("best_at_global",""),
        "decision":             data.get("decision",""),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    report_text = f"""BÁO CÁO ĐẦU RA (OUTPUT AI REPORT PROFILE)

Phần I: Tổng quan Hồ sơ & Điểm số (Executive Summary)
- AI Readiness Index (Chỉ số sẵn sàng AI): {data.get('ai_test_total', 0)}/100
- Phân loại Ứng viên: [{data.get('ai_test_label', '')}]
- Điểm SWAT Elite: {data.get('swat_total', 0)}/10 ([{data.get('swat_label', '')}])

Phần II: Phân tích Năng lực Chuyên sâu (Core Analysis)

1. ĐIỂM MẠNH (Strengths):
- Kỹ năng công nghệ và năng lực chuyên môn nổi trội:
  {data.get('strength_tech_skills', '')}
- Các chỉ số đánh giá vượt chuẩn (Exceeding Standards) so với JD hiện tại:
  {data.get('strength_exceeding', '')}

2. ĐIỂM HẠN CHẾ (Gaps & Misalignments):
- Kỹ năng/năng lực còn thiếu hoặc tư duy chưa tương thích với văn hóa AI First:
  {data.get('gap_missing_skills', '')}
- Các rủi ro về mặt vận hành hoặc bảo mật dữ liệu dựa trên các bài test:
  {data.get('gap_risks', '')}

3. NĂNG LỰC NỔI BẬT NHẤT (“BEST AT”):
- Chuyên môn mạnh nhất: {data.get('best_at_core', '')}
- Năng lực vận hành 2AS: {data.get('best_at_2as_ops', '')}
- Mức độ sẵn sàng sử dụng 2AS: {data.get('best_at_2as_ready', '')}
- Ngoại ngữ & Thực chiến: {data.get('best_at_global', '')}

QUYẾT ĐỊNH: {data.get('decision', '')}
"""

    final_resp = {
        "report_text": report_text,
        **data
    }
    
    # Save cache if applicable
    if api_use_cache:
        frappe.cache().set_value(cache_key, final_resp, expires_in_sec=86400 * 7) # Cache for 7 days

    return final_resp


# ══════════════════════════════════════════════════════════════════════════════
# CT Group Template — Session & Access Control
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=False)
def get_context():
    """
    Entry point cho Frontend (initSession).
    - Xac thuc quyen qua ct_agent_hub.check_app_access (cookie-based)
    - Tao ATS Session moi
    - Tra ve csrf_token + session_id + user info
    """
    dept = ""
    role = ""
    try:
        from ct_agent_hub.api import check_app_access
        agents_data = check_app_access("ai_ats")
        user_depts = agents_data.get("user_departments", [])
        dept = ",".join(user_depts) if user_depts else ""
        role = agents_data.get("user_role", "")
    except ImportError:
        pass  # ct_agent_hub chua duoc cai dat

    session_id   = str(uuid.uuid4())
    session_name = _logger.create_session(session_id, dept=dept, role=role)

    return {
        "csrf_token":   frappe.sessions.get_csrf_token(),
        "session_id":   session_id,
        "session_name": session_name,
        "user":         frappe.session.user,
        "full_name":    frappe.utils.get_fullname(frappe.session.user),
    }


def _resolve_session(session_id: str) -> str:
    """Tim session_name tu session_id. Fallback tra ve chuoi rong."""
    if not session_id:
        return ""
    try:
        rows = frappe.db.get_all(
            "ATS Session",
            filters={"session_id": session_id},
            fields=["name"],
            limit=1,
            ignore_permissions=True,
        )
        return rows[0].name if rows else ""
    except Exception:
        return ""
