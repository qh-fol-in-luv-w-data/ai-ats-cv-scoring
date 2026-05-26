"""
AI ATS – API Endpoints
/api/method/ai_ats.api.generate_candidate_report
/api/method/ai_ats.api.get_context
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

# ── Internal scoring guides ───────────────────────────────────────────────────
import os
from dotenv import load_dotenv
# Load .env từ app dir để đảm bảo OPENAI_API_KEY luôn có (kể cả bench serve không load env)
load_dotenv(Path(__file__).parent / ".env", override=True)
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

_BASE = Path(os.getenv("AI_ATS_DIR", str(Path(__file__).parent.parent.parent.parent / "AI_ATS")))
_AI_SCORING_PDF  = _BASE / "CTG-KNC-TD-QĐ04.BM02-HƯỚNG DẪN CHẤM ĐIỂM BÀI TEST NĂNG LỰC AI (1).pdf"
_SWAT_PRD_DOCX   = _BASE / "18052026_RD - PRD - AI Candidate Persona Report.docx"
_G5_SCORING_DOCX  = _BASE / "CTG-KNC-TD-QT01.BM16 - BỘ CÂU HỎI ĐÁNH GIÁ TIỀM NĂNG ỨNG VIÊN 4.docx"
_G5_QUESTION_DOCX  = Path(__file__).parent.parent / "CTG-KNC-TD-QT01.BM16 - BỘ CÂU HỎI ĐÁNH GIÁ TIỀM NĂNG ỨNG VIÊN 4 (1).docx"
_AI_QUESTION_DOCX  = Path(__file__).parent.parent / "Demo hướng dẫn đánh giá bài test AI (1).docx"

# ── OpenAI client — lazy init từ Frappe Single DocType hoặc env var ───────────
def _get_openai_key() -> str:
    # Ưu tiên 1: Agent DocType (cùng pattern với các app khác)
    try:
        agent = frappe.get_doc("Agent", "2AS-ATS")
        key = agent.get_password("api_key") if agent.get("api_key") else None
        if key: return key
    except Exception:
        pass
    # Ưu tiên 2: AI ATS Settings Single DocType (nếu có)
    try:
        if frappe.db.exists("DocType", "AI ATS Settings"):
            key = frappe.db.get_single_value("AI ATS Settings", "openai_api_key")
            if key: return key
    except Exception:
        pass
    # Fallback: biến môi trường OPENAI_API_KEY
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
- Kết quả SWAT Elite (swat_label): Đánh giá [Swat-Elite] (nếu swat_total >= 6.0) hoặc [KHÔNG ĐẠT] (nếu swat_total < 6.0) (chấm nới điểm để dễ pass).
- Chấm điểm 5G Test (Thang 100) -> g5_total. CÁCH CHẤM 5G: Bài 5G gồm Phần A (trắc nghiệm 15 câu, mỗi câu 2đ, tổng 30đ) và Phần B (tự luận 15 câu, tổng 70đ). PHẢI điền g5_table đủ 5 hàng (G1–G5), mỗi hàng chấm trên thang diem_toi_da=20.0 (bao gồm tổng điểm trắc nghiệm và tự luận thuộc tiêu chí đó), tổng g5_total = tổng điểm 5 tiêu chí (thang 100). Đối chiếu đáp án từ Rubric 5G để tính điểm chính xác từng tiêu chí. KHÔNG được để nguyên giá trị mặc định 0.
- LƯU Ý CHỐNG BỊA ĐẶT (Hallucination): Điểm AI Test PHẢI được chấm hoàn toàn dựa trên nội dung TEST AI. Điểm SWAT và 5G PHẢI dựa hoàn toàn trên nội dung TEST 5G. Nếu nội dung test bị lỗi, rỗng hoặc thiếu thông tin, TUYỆT ĐỐI KHÔNG tự bịa điểm (phải cho 0 điểm).
- LỌC NHIỄU TÀI LIỆU HƯỚNG DẪN: Trong các tài liệu Hướng dẫn chấm điểm (Rubric) có thể có nhiều thông tin dư thừa. Bạn PHẢI BỎ QUA các phần râu ria và CHỈ TẬP TRUNG vào đúng "khung tiêu chuẩn chấm điểm" (barem/rubric) cốt lõi để đối chiếu với bài làm của ứng viên.
- QUY TẮC TÀN KHỐC ĐỂ RA QUYẾT ĐỊNH (decision): Vì công ty áp dụng "No AI - No Hire", nếu ai_test_label là "Non-AI" HOẶC g5_total < 60.0 HOẶC swat_total < 6.0, thì BẮT BUỘC Quyết định (decision) = "KHÔNG ĐẠT" (Cúc luôn!). Chỉ được đánh giá "ĐẠT" khi tất cả đều qua môn.

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

# ══════════════════════════════════════════════════════════════════════════════
# Session helpers
# ══════════════════════════════════════════════════════════════════════════════

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

def _ensure_session(session_id: str = "") -> str:
    """Resolve hoặc tự tạo session mới (dùng cho API token calls từ bên thứ 3)."""
    if session_id:
        name = _resolve_session(session_id)
        if name:
            return name
    new_id = str(uuid.uuid4())
    return _logger.create_session(new_id, dept="api", role="api_token")

# ══════════════════════════════════════════════════════════════════════════════
# Endpoint 1: generate_candidate_report
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def generate_candidate_report(
    ai_test_url: str = "",
    g5_test_url: str = "",
    eq_test_url: str = "",
    survey_url: str = "",
    jd_text: str = "",
    cv_text: str = "",
    api_use_cache=1,
):
    """
    INPUT  (qua form-data hoặc JSON payload):
        ai_test_url, g5_test_url, eq_test_url  – link bài test
        survey_url                              – link phỏng vấn
        jd_text                                 – nội dung JD
        cv_text                                 – nội dung CV text
        cv_file                                 – file CV upload (pdf/docx)
        api_use_cache                           - dùng cache (mặc định 1)
    OUTPUT : dict + lưu vào DocType "AI Candidate Report"
    Logging: ATS Session + ATS Action Log + ATS AI Call Log
    """
    # ── Session (auto-create nếu không có header) ─────────────────────────────
    session_id   = (frappe.get_request_header("X-App-Session-Id") or "")
    session_name = _ensure_session(session_id)

    # ── Action Log: start ─────────────────────────────────────────────────────
    action_name = _logger.start_action(
        session_name,
        action_type="generate_candidate_report",
        input_summary=f"cv={'file' if frappe.request and frappe.request.files else 'text'}, ai_test={ai_test_url[:60]}",
        input_detail={"ai_test_url": ai_test_url, "g5_test_url": g5_test_url, "has_jd": bool(jd_text)},
    )

    try:
        # Convert cache flag
        if isinstance(api_use_cache, str):
            api_use_cache = api_use_cache.lower() in ['true', '1', 't', 'yes']
        else:
            api_use_cache = bool(api_use_cache)

        # Validate bắt buộc
        if not survey_url:
            frappe.throw("survey_url là bắt buộc. Vui lòng cung cấp link phỏng vấn.", frappe.ValidationError)

        # CV từ upload
        if frappe.request and frappe.request.files:
            f = frappe.request.files.get("cv_file")
            if f:
                raw = f.stream.read()
                cv_text = _pdf_bytes(raw) if (f.filename or "").lower().endswith(".pdf") else _docx_bytes(raw)

        # Scrape links
        ai_txt = _scrape(ai_test_url)
        g5_txt = _scrape(g5_test_url)
        eq_txt = _scrape(eq_test_url)
        sv_txt = _scrape(survey_url) if survey_url else "[Chưa có]"

        # Scoring guides
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

        # Cache check
        cache_key = ""
        if api_use_cache:
            raw_key = f"v4_{cv_text}{jd_text}{ai_test_url}{g5_test_url}{eq_test_url}{survey_url}"
            req_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
            cache_key = f"ai_ats_api_resp_{req_hash}"
            cached_resp = frappe.cache().get_value(cache_key)
            if cached_resp:
                _logger.finish_action(action_name, status="success",
                    output_summary="served_from_cache", from_cache=True)
                return cached_resp

        # GPT Call
        with Timer() as t:
            resp = _get_gpt().chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=4000,
            )
        data = json.loads(resp.choices[0].message.content)
        usage = resp.usage
        prompt_tokens     = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        # ── AI Call Log ───────────────────────────────────────────────────────
        _logger.log_ai_call(
            session_name, action_name,
            call_type="generate_candidate_report", ai_model="gpt-4o",
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            duration_seconds=t.elapsed, status="success",
        )

        # Lưu DocType
        doc = frappe.get_doc({
            "doctype":              "AI Candidate Report",
            "candidate_name":       data.get("candidate_name") or "Unknown",
            "position":             data.get("position") or "",
            "email":                data.get("email") or "",
            "phone":                data.get("phone") or "",
            "analysis_date":        datetime.now(),
            "ai_test_url":          ai_test_url,
            "g5_test_url":          g5_test_url,
            "eq_test_url":          eq_test_url,
            "survey_url":           survey_url,
            "jd_text":              jd_text[:2000],
            "ai_test_total":        data.get("ai_test_total", 0),
            "ai_test_label":        data.get("ai_test_label", ""),
            "ai_test_table":        json.dumps(data.get("ai_test_table", []), ensure_ascii=False) if isinstance(data.get("ai_test_table"), list) else (data.get("ai_test_table") or ""),
            "swat_total":           data.get("swat_total", 0),
            "swat_label":           data.get("swat_label", ""),
            "swat_table":           json.dumps(data.get("swat_table", []), ensure_ascii=False) if isinstance(data.get("swat_table"), list) else (data.get("swat_table") or ""),
            "strength_tech_skills": data.get("strength_tech_skills", ""),
            "strength_exceeding":   data.get("strength_exceeding", ""),
            "gap_missing_skills":   data.get("gap_missing_skills", ""),
            "gap_risks":            data.get("gap_risks", ""),
            "best_at_core":         data.get("best_at_core", ""),
            "best_at_2as_ops":      data.get("best_at_2as_ops", ""),
            "best_at_2as_ready":    data.get("best_at_2as_ready", ""),
            "best_at_global":       data.get("best_at_global", ""),
            "decision":             data.get("decision", ""),
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

3. NĂNG LỰC NỔI BẬT NHẤT ("BEST AT"):
- Chuyên môn mạnh nhất: {data.get('best_at_core', '')}
- Năng lực vận hành 2AS: {data.get('best_at_2as_ops', '')}
- Mức độ sẵn sàng sử dụng 2AS: {data.get('best_at_2as_ready', '')}
- Ngoại ngữ & Thực chiến: {data.get('best_at_global', '')}

QUYẾT ĐỊNH: {data.get('decision', '')}
"""
        final_resp = {
            # Trường chính — bên thứ 3 chỉ cần report_text
            "report_text": report_text,
            "decision":    data.get("decision", ""),
            "candidate_name": data.get("candidate_name", ""),
            "position":    data.get("position", ""),
            "email":       data.get("email", ""),
            "phone":       data.get("phone", ""),
            # Điểm số tổng hợp
            "ai_test_total": data.get("ai_test_total", 0),
            "ai_test_label": data.get("ai_test_label", ""),
            "swat_total":    data.get("swat_total", 0),
            "swat_label":    data.get("swat_label", ""),
            "g5_total":      data.get("g5_total", 0),
            # Chi tiết bảng — dùng cho UI
            "ai_test_table": data.get("ai_test_table", []),
            "swat_table":    data.get("swat_table", []),
            # Phân tích định tính
            "strength_tech_skills": data.get("strength_tech_skills", ""),
            "strength_exceeding":   data.get("strength_exceeding", ""),
            "gap_missing_skills":   data.get("gap_missing_skills", ""),
            "gap_risks":            data.get("gap_risks", ""),
            "best_at_core":         data.get("best_at_core", ""),
            "best_at_2as_ops":      data.get("best_at_2as_ops", ""),
            "best_at_2as_ready":    data.get("best_at_2as_ready", ""),
            "best_at_global":       data.get("best_at_global", ""),
            "doctype_name":         data.get("doctype_name", ""),
        }

        # ── Action Log: finish ────────────────────────────────────────────────
        _logger.finish_action(
            action_name, status="success",
            output_summary=f"decision={data.get('decision','')} ai={data.get('ai_test_total',0)} swat={data.get('swat_total',0)}",
            ai_model="gpt-4o",
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            duration_seconds=t.elapsed,
        )

        if api_use_cache and cache_key:
            frappe.cache().set_value(cache_key, final_resp, expires_in_sec=86400 * 7)

        return final_resp

    except Exception as e:
        try: frappe.db.rollback()
        except: pass
        _logger.finish_action(action_name, status="failed", error_message=str(e)[:500])
        frappe.log_error(f"generate_candidate_report error: {str(e)[:80]}")
        frappe.throw(str(e))


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

 
# endpoint for anh zũ
@frappe.whitelist()
def generate_candidate_only_report(
    ai_test_url: str = "",
    g5_test_url: str = "",
    eq_test_url: str = "",
    survey_url: str = "",
    jd_text: str = "",
    cv_text: str = "",
    api_use_cache=1,
):
    """
    INPUT  (qua form-data hoặc JSON payload):
        ai_test_url, g5_test_url, eq_test_url  – link bài test
        survey_url                              – link phỏng vấn
        jd_text                                 – nội dung JD
        cv_text                                 – nội dung CV text
        cv_file                                 – file CV upload (pdf/docx)
        api_use_cache                           - dùng cache (mặc định 1)
    OUTPUT : dict + lưu vào DocType "AI Candidate Report"
    Logging: ATS Session + ATS Action Log + ATS AI Call Log
    """
    # ── Session (auto-create nếu không có header) ─────────────────────────────
    session_id   = (frappe.get_request_header("X-App-Session-Id") or "")
    session_name = _ensure_session(session_id)

    # ── Action Log: start ─────────────────────────────────────────────────────
    action_name = _logger.start_action(
        session_name,
        action_type="generate_candidate_report",
        input_summary=f"cv={'file' if frappe.request and frappe.request.files else 'text'}, ai_test={ai_test_url[:60]}",
        input_detail={"ai_test_url": ai_test_url, "g5_test_url": g5_test_url, "has_jd": bool(jd_text)},
    )

    try:
        # Convert cache flag
        if isinstance(api_use_cache, str):
            api_use_cache = api_use_cache.lower() in ['true', '1', 't', 'yes']
        else:
            api_use_cache = bool(api_use_cache)

        # Validate bắt buộc
        if not survey_url:
            frappe.throw("survey_url là bắt buộc. Vui lòng cung cấp link phỏng vấn.", frappe.ValidationError)

        # CV từ upload
        if frappe.request and frappe.request.files:
            f = frappe.request.files.get("cv_file")
            if f:
                raw = f.stream.read()
                cv_text = _pdf_bytes(raw) if (f.filename or "").lower().endswith(".pdf") else _docx_bytes(raw)

        # Scrape links
        ai_txt = _scrape(ai_test_url)
        g5_txt = _scrape(g5_test_url)
        eq_txt = _scrape(eq_test_url)
        sv_txt = _scrape(survey_url) if survey_url else "[Chưa có]"

        # Scoring guides
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

        # Cache check
        cache_key = ""
        if api_use_cache:
            raw_key = f"v4_{cv_text}{jd_text}{ai_test_url}{g5_test_url}{eq_test_url}{survey_url}"
            req_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
            cache_key = f"ai_ats_api_resp_{req_hash}"
            cached_resp = frappe.cache().get_value(cache_key)
            if cached_resp:
                _logger.finish_action(action_name, status="success",
                    output_summary="served_from_cache", from_cache=True)
                return cached_resp

        # GPT Call
        with Timer() as t:
            resp = _get_gpt().chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=4000,
            )
        data = json.loads(resp.choices[0].message.content)
        usage = resp.usage
        prompt_tokens     = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        # ── AI Call Log ───────────────────────────────────────────────────────
        _logger.log_ai_call(
            session_name, action_name,
            call_type="generate_candidate_report", ai_model="gpt-4o",
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            duration_seconds=t.elapsed, status="success",
        )

        # Chuẩn hoá swat_label
        raw_swat = str(data.get("swat_label", "")).strip().upper()
        if "KHÔNG ĐẠT" in raw_swat or "KHONG DAT" in raw_swat or "FAIL" in raw_swat:
            clean_swat = "KHÔNG ĐẠT"
        elif "ĐẠT" in raw_swat or "DAT" in raw_swat or "PASS" in raw_swat:
            clean_swat = "ĐẠT"
        else:
            clean_swat = ""

        # Lưu DocType
        doc = frappe.get_doc({
            "doctype":              "AI Candidate Report",
            "candidate_name":       data.get("candidate_name") or "Unknown",
            "position":             data.get("position") or "",
            "email":                data.get("email") or "",
            "phone":                data.get("phone") or "",
            "analysis_date":        datetime.now(),
            "ai_test_url":          ai_test_url,
            "g5_test_url":          g5_test_url,
            "eq_test_url":          eq_test_url,
            "survey_url":           survey_url,
            "jd_text":              jd_text[:2000],
            "ai_test_total":        data.get("ai_test_total", 0),
            "ai_test_label":        data.get("ai_test_label", ""),
            "ai_test_table":        json.dumps(data.get("ai_test_table", []), ensure_ascii=False) if isinstance(data.get("ai_test_table"), list) else (data.get("ai_test_table") or ""),
            "swat_total":           data.get("swat_total", 0),
            "swat_label":           clean_swat,
            "swat_table":           json.dumps(data.get("swat_table", []), ensure_ascii=False) if isinstance(data.get("swat_table"), list) else (data.get("swat_table") or ""),
            "strength_tech_skills": data.get("strength_tech_skills", ""),
            "strength_exceeding":   data.get("strength_exceeding", ""),
            "gap_missing_skills":   data.get("gap_missing_skills", ""),
            "gap_risks":            data.get("gap_risks", ""),
            "best_at_core":         data.get("best_at_core", ""),
            "best_at_2as_ops":      data.get("best_at_2as_ops", ""),
            "best_at_2as_ready":    data.get("best_at_2as_ready", ""),
            "best_at_global":       data.get("best_at_global", ""),
            "decision":             data.get("decision", ""),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        report_text = f"""BÁO CÁO ĐẦU RA (OUTPUT AI REPORT PROFILE)

<strong>Phần I: Tổng quan Hồ sơ & Điểm số (Executive Summary)</strong>
- <strong>AI Readiness Index (Chỉ số sẵn sàng AI):</strong> {data.get('ai_test_total', 0)}/100
- <strong>Phân loại Ứng viên:</strong> [{data.get('ai_test_label', '')}]
- <strong>Điểm SWAT Elite:</strong> {data.get('swat_total', 0)}/10 ([{data.get('swat_label', '')}])

<strong>Phần II: Phân tích Năng lực Chuyên sâu (Core Analysis)</strong>

<strong>ĐIỂM MẠNH (Strengths):</strong>
- <strong>Kỹ năng công nghệ và năng lực chuyên môn nổi trội:</strong>
  {data.get('strength_tech_skills', '')}
- <strong>Các chỉ số đánh giá vượt chuẩn (Exceeding Standards) so với JD hiện tại:</strong>
  {data.get('strength_exceeding', '')}

<strong>ĐIỂM HẠN CHẾ (Gaps & Misalignments):</strong>
- <strong>Kỹ năng/năng lực còn thiếu hoặc tư duy chưa tương thích với văn hóa AI First:</strong>
  {data.get('gap_missing_skills', '')}
- <strong>Các rủi ro về mặt vận hành hoặc bảo mật dữ liệu dựa trên các bài test:</strong>
  {data.get('gap_risks', '')}

<strong>NĂNG LỰC NỔI BẬT NHẤT ("BEST AT"):</strong>
- <strong>Chuyên môn mạnh nhất:</strong> {data.get('best_at_core', '')}
- <strong>Năng lực vận hành 2AS:</strong> {data.get('best_at_2as_ops', '')}
- <strong>Mức độ sẵn sàng sử dụng 2AS:</strong> {data.get('best_at_2as_ready', '')}
- <strong>Ngoại ngữ & Thực chiến:</strong> {data.get('best_at_global', '')}

<strong>QUYẾT ĐỊNH:</strong> {data.get('decision', '')}
"""
        final_resp = {
            # Trường chính — bên thứ 3 chỉ cần report_text
            "report_text": report_text
        }

        # ── Action Log: finish ────────────────────────────────────────────────
        _logger.finish_action(
            action_name, status="success",
            output_summary=f"decision={data.get('decision','')} ai={data.get('ai_test_total',0)} swat={data.get('swat_total',0)}",
            ai_model="gpt-4o",
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            duration_seconds=t.elapsed,
        )

        if api_use_cache and cache_key:
            frappe.cache().set_value(cache_key, final_resp, expires_in_sec=86400 * 7)

        return final_resp

    except Exception as e:
        try: frappe.db.rollback()
        except: pass
        _logger.finish_action(action_name, status="failed", error_message=str(e)[:500])
        frappe.log_error(f"generate_candidate_report error: {str(e)[:80]}")
        frappe.throw(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Endpoint: score_tests  — Chấm điểm & trả bảng chi tiết (không lưu DocType)
# /api/method/ai_ats.api.score_tests
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True)
def score_tests(
    ai_test_url: str = "",
    g5_test_url: str = "",
    eq_test_url: str = "",
    survey_url: str = "",
    jd_text: str = "",
    cv_text: str = "",
    api_use_cache=0,
):
    """
    Chấm điểm bài test và trả bảng chi tiết AI Test / SWAT / 5G.
    Không lưu DocType. Tập trung vào scoring tables để dễ review.

    OUTPUT:
        tables_text  — bảng ASCII dễ đọc (copy ra terminal/chat)
        ai_test_table, swat_table, g5_table  — raw JSON
        ai_test_total, swat_total, g5_total, decision
    """
    if isinstance(api_use_cache, str):
        api_use_cache = api_use_cache.lower() in ['true', '1', 't', 'yes']
    else:
        api_use_cache = bool(api_use_cache)

    # CV từ upload
    if frappe.request and frappe.request.files:
        f = frappe.request.files.get("cv_file")
        if f:
            raw = f.stream.read()
            cv_text = _pdf_bytes(raw) if (f.filename or "").lower().endswith(".pdf") else _docx_bytes(raw)

    ai_txt = _scrape(ai_test_url)
    g5_txt = _scrape(g5_test_url)
    eq_txt = _scrape(eq_test_url)
    sv_txt = _scrape(survey_url) if survey_url else "[Chưa có]"

    ai_guide = _read_cached(_AI_SCORING_PDF, api_use_cache)
    swat_prd = _read_cached(_SWAT_PRD_DOCX, api_use_cache)
    g5_guide = _read_cached(_G5_SCORING_DOCX, api_use_cache)

    user_msg = f"""### CV: {cv_text[:8000]}
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

    # Cache (off mặc định vì endpoint này dùng để review)
    if api_use_cache:
        raw_key = f"score_tests_v1_{cv_text}{jd_text}{ai_test_url}{g5_test_url}{eq_test_url}{survey_url}"
        req_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        cache_key = f"ai_ats_score_{req_hash}"
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached

    resp = _get_gpt().chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=4000,
    )
    data = json.loads(resp.choices[0].message.content)

    # ── Build bảng ASCII dễ đọc ───────────────────────────────────────────────
    sep  = "+" + "-"*5 + "+" + "-"*35 + "+" + "-"*10 + "+" + "-"*10 + "+" + "-"*50 + "+"
    hdr  = "| {:<3} | {:<33} | {:>8} | {:>8} | {:<48} |"
    row  = "| {:<3} | {:<33} | {:>8} | {:>8} | {:<48} |"

    lines = []

    # Bảng 1: AI Test
    lines.append("\n╔══════════════════════════════════════════════════════════════════╗")
    lines.append(  "║          BẢNG CHẤM ĐIỂM AI TEST (thang 100)                     ║")
    lines.append(  "╚══════════════════════════════════════════════════════════════════╝")
    lines.append(sep)
    lines.append(hdr.format("Câu", "Nội dung", "Tối đa", "Điểm", "Lý do"))
    lines.append(sep)
    for r in data.get("ai_test_table", []):
        lines.append(row.format(
            str(r.get("cau", "")),
            str(r.get("noi_dung", ""))[:33],
            str(r.get("diem_toi_da", "")),
            str(r.get("diem_cham", "")),
            str(r.get("ly_do", ""))[:48],
        ))
    lines.append(sep)
    lines.append(f"  TỔNG AI TEST: {data.get('ai_test_total', 0)}/100  →  [{data.get('ai_test_label', '')}]")

    # Bảng 2: SWAT
    sep2 = "+" + "-"*35 + "+" + "-"*8 + "+" + "-"*8 + "+" + "-"*10 + "+" + "-"*50 + "+"
    hdr2 = "| {:<33} | {:>6} | {:>6} | {:>8} | {:<48} |"
    lines.append("\n╔══════════════════════════════════════════════════════════════════╗")
    lines.append(  "║          BẢNG CHẤM ĐIỂM SWAT ELITE (thang 10)                   ║")
    lines.append(  "╚══════════════════════════════════════════════════════════════════╝")
    lines.append(sep2)
    lines.append(hdr2.format("Trụ cột", "Tỷ trọng", "Điểm thô", "Trọng số", "Cơ sở"))
    lines.append(sep2)
    for r in data.get("swat_table", []):
        lines.append(hdr2.format(
            str(r.get("tru_cot", ""))[:33],
            str(r.get("ty_trong", "")),
            str(r.get("diem_tho", "")),
            str(r.get("diem_trong_so", "")),
            str(r.get("co_so", ""))[:48],
        ))
    lines.append(sep2)
    lines.append(f"  TỔNG SWAT: {data.get('swat_total', 0)}/10  →  [{data.get('swat_label', '')}]")

    # Bảng 3: 5G
    sep3 = "+" + "-"*45 + "+" + "-"*10 + "+" + "-"*10 + "+" + "-"*50 + "+"
    hdr3 = "| {:<43} | {:>8} | {:>8} | {:<48} |"
    lines.append("\n╔══════════════════════════════════════════════════════════════════╗")
    lines.append(  "║          BẢNG CHẤM ĐIỂM 5G TEST (thang 10)                      ║")
    lines.append(  "╚══════════════════════════════════════════════════════════════════╝")
    lines.append(sep3)
    lines.append(hdr3.format("Tiêu chí", "Tối đa", "Điểm", "Lý do"))
    lines.append(sep3)
    for r in data.get("g5_table", []):
        lines.append(hdr3.format(
            str(r.get("tieu_chi", ""))[:43],
            str(r.get("diem_toi_da", "")),
            str(r.get("diem_cham", "")),
            str(r.get("ly_do", ""))[:48],
        ))
    lines.append(sep3)
    lines.append(f"  TỔNG 5G: {data.get('g5_total', 0)}/100")

    lines.append(f"\n{'═'*68}")
    lines.append(f"  ⚡ QUYẾT ĐỊNH CUỐI: {data.get('decision', '')}")
    lines.append(f"{'═'*68}")

    tables_text = "\n".join(lines)

    result = {
        "tables_text":     tables_text,
        "ai_test_table":   data.get("ai_test_table", []),
        "ai_test_total":   data.get("ai_test_total", 0),
        "ai_test_label":   data.get("ai_test_label", ""),
        "swat_table":      data.get("swat_table", []),
        "swat_total":      data.get("swat_total", 0),
        "swat_label":      data.get("swat_label", ""),
        "g5_table":        data.get("g5_table", []),
        "g5_total":        data.get("g5_total", 0),
        "decision":        data.get("decision", ""),
        "candidate_name":  data.get("candidate_name", ""),
    }

    if api_use_cache:
        frappe.cache().set_value(cache_key, result, expires_in_sec=86400)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Endpoint: score_single  — Chấm 1 bài theo type (ai | 5g)
# /api/method/ai_ats.api.score_single
# Params: url=<link bài làm>  type=ai|5g
# ══════════════════════════════════════════════════════════════════════════════

# System prompt riêng cho từng loại — gọn hơn _SYSTEM, không hallucinate
_SYSTEM_AI = """Bạn là chuyên gia chấm bài TEST AI của CT Group.
CHỈ chấm bài AI Test bên dưới dựa trên rubric được cung cấp.
Trả JSON:
{
  "candidate_name": "",
  "table": [
    {"cau": 1, "noi_dung": "AI Awareness",       "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 2, "noi_dung": "AI Daily Use",        "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 3, "noi_dung": "AI Self-Assessment",  "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 4, "noi_dung": "AI Problem Solving",  "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 5, "noi_dung": "Prompt Engineering",  "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 6, "noi_dung": "AI x Teamwork",       "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 7, "noi_dung": "AI Productivity",     "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 8, "noi_dung": "AI Mindset",          "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 9, "noi_dung": "AI Limitation",       "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau":10, "noi_dung": "AI Growth Plan",      "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""}
  ],
  "total": 0,
  "label": "AI-Ready",
  "nhan_xet": ""
}
Quy tắc: label = "AI-Ready" nếu total >= 75, "AI-Khá" nếu 50–74, "Non-AI" nếu < 50. KHÔNG bịa điểm."""

_SYSTEM_AI = """Bạn là chuyên gia chấm bài TEST AI của CT Group.
CHỈ chấm bài AI Test bên dưới dựa trên rubric được cung cấp.
Rubric có 10 câu x 10 điểm = 100 điểm, mỗi câu có 4 mức: 0–3 / 4–6 / 7–9 / 10 điểm.
Chấm CHÍNH XÁC theo từng mức, giải thích rõ lý do dựa vào nội dung bài làm.
Trả JSON:
{
  "candidate_name": "",
  "table": [
    {"cau": 1, "noi_dung": "AI Awareness",       "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 2, "noi_dung": "AI Daily Use",        "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 3, "noi_dung": "AI Self-Assessment",  "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 4, "noi_dung": "AI Problem Solving",  "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 5, "noi_dung": "Prompt Engineering",  "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 6, "noi_dung": "AI x Teamwork",       "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 7, "noi_dung": "AI Productivity",     "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 8, "noi_dung": "AI Mindset",          "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau": 9, "noi_dung": "AI Limitation",       "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""},
    {"cau":10, "noi_dung": "AI Growth Plan",      "diem_toi_da": 10, "diem_cham": 0, "ly_do": ""}
  ],
  "total": 0,
  "label": "",
  "nhan_xet": ""
}
Quy tắc: label = "Xuất sắc" (90-100) | "Khá" (75-89) | "Cơ bản" (50-74) | "Không đạt" (<50). KHÔNG bịa điểm."""

_SYSTEM_5G = """Bạn là chuyên gia chấm bài TEST 5G (tiềm năng quản lý) của CT Group.
Bài 5G gồm 2 phần, TỔNG ĐIỂM THANG 100:
- Phần A: 15 câu trắc nghiệm = 30 điểm (mỗi câu đúng = 2đ, sai = 0đ). Đáp án đúng lấy từ rubric.
- Phần B: 15 câu tự luận (câu 16–30) = 70 điểm. Mỗi nhóm tiêu chí (G1-G5) có 3 câu, tổng 14 điểm/nhóm (phân bổ điểm tối đa là 5, 5, 4 cho 3 câu tương ứng).

YÊU CẦU OUTPUT:
1. phan_a: mảng 15 phần tử — từng câu trắc nghiệm: số câu, đáp án ứng viên chọn, đáp án đúng, đúng/sai, điểm (2 hoặc 0)
2. phan_b: mảng 15 phần tử — từng câu tự luận: số câu, nội dung câu hỏi ngắn gọn, diem_toi_da (từ rubric), diem_cham, nhan_xet
3. total_phan_a: tổng điểm phần A (tối đa 30)
4. total_phan_b: tổng điểm phần B (tối đa 70)
5. total: tổng cộng (tối đa 100)
6. ket_luan: "Xuất sắc" (91-100) | "Giỏi" (75-90) | "Trung bình" (50-74) | "Không phù hợp" (<50)
7. candidate_name

JSON schema:
{
  "candidate_name": "",
  "phan_a": [
    {"cau": 1, "dap_an_chon": "", "dap_an_dung": "", "ket_qua": "Đúng", "diem": 2},
    {"cau": 2, "dap_an_chon": "", "dap_an_dung": "", "ket_qua": "Sai",  "diem": 0}
  ],
  "phan_b": [
    {"cau": 16, "noi_dung": "G1 - Mô tả tình huống truyền đạt thông tin khó", "diem_toi_da": 5, "diem_cham": 0.0, "nhan_xet": ""}
  ],
  "total_phan_a": 0,
  "total_phan_b": 0.0,
  "total": 0.0,
  "ket_luan": "",
  "nhan_xet_chung": ""
}
LƯU Ý: PHẢI điền đủ 15 phần tử phan_a và 15 phần tử phan_b. KHÔNG bịa điểm. Nếu ứng viên không trả lời câu nào thì diem_cham=0."""


@frappe.whitelist(allow_guest=True)
def score_single(url: str = "", type: str = "ai", api_use_cache=1):
    """
    Chấm 1 bài test theo loại.

    INPUT:
        url   – link bài làm (survey print URL)
        type  – "ai" hoặc "5g"

    OUTPUT (JSON):
        type, candidate_name, total, label (AI only), table, nhan_xet, tables_text
    """
    test_type = str(type).strip().lower()
    if test_type not in ("ai", "5g"):
        frappe.throw("type phải là 'ai' hoặc '5g'", frappe.ValidationError)
    if not url:
        frappe.throw("url không được để trống", frappe.ValidationError)

    if isinstance(api_use_cache, str):
        api_use_cache = api_use_cache.lower() in ['true', '1', 't', 'yes']
    else:
        api_use_cache = bool(api_use_cache)

    # Scrape bài làm
    content = _scrape(url)
    if content.startswith("["):
        frappe.throw(f"Không scrape được nội dung từ URL: {content}", frappe.ValidationError)

    if api_use_cache:
        import hashlib
        raw_key = f"score_single_{test_type}_{url}_{content[:1000]}"
        req_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        cache_key = f"ai_ats_score_single_{req_hash}"
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached

    # Load rubric tương ứng
    if test_type == "ai":
        # Ưu tiên dùng file docx mới có thang điểm 4 mức chi tiết
        if _AI_QUESTION_DOCX.exists():
            ai_guide = _docx_bytes(_AI_QUESTION_DOCX.read_bytes())
        else:
            ai_guide = _read_cached(_AI_SCORING_PDF, True)
        system   = _SYSTEM_AI
        max_tok  = 2500
        user_msg = f"""### RUBRIC CHẤM ĐIỂM AI TEST (thang 4 mức, 10 câu x 10đ):\n{ai_guide}\n\n### BÀI LÀM ỨNG VIÊN:\n{content[:12000]}\n\nChấm từng câu theo đúng mức điểm từ rubric, trả JSON."""
    else:
        # Dùng file BM16 (1).docx có đủ câu hỏi + thang điểm tự luận
        if _G5_QUESTION_DOCX.exists():
            from ai_ats.api import _docx_bytes as _db
            q_content = _db(_G5_QUESTION_DOCX.read_bytes())
        else:
            q_content = _read_cached(_G5_SCORING_DOCX, True)
        system   = _SYSTEM_5G
        max_tok  = 5000
        user_msg = f"""### BỘ CÂU HỎI + THANG ĐIỂM 5G (đây là rubric chuẩn, dùng để đối chiếu đáp án TN và chấm TL):\n{q_content[:25000]}\n\n### BÀI LÀM ỨNG VIÊN:\n{content[:12000]}\n\nChấm điểm đầy đủ 15 câu TN + 15 câu TL và trả JSON."""

    resp = _get_gpt().chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=max_tok,
    )
    data = json.loads(resp.choices[0].message.content)

    # ── Server tự tính điểm lại (không tin GPT cộng) ──────────────────────────
    if test_type == "ai":
        rows = data.get("table", [])
        ai_total = round(sum(float(r.get("diem_cham", 0)) for r in rows), 1)
        if ai_total >= 90:
            ai_label = "Xuất sắc"
        elif ai_total >= 75:
            ai_label = "Khá"
        elif ai_total >= 50:
            ai_label = "Cơ bản"
        else:
            ai_label = "Không đạt"

        result = {
            "type":           "ai",
            "candidate_name": data.get("candidate_name", ""),
            "table":          rows,
            "total":          ai_total,
            "label":          ai_label,
            "nhan_xet":       data.get("nhan_xet", ""),
        }
        
        # LƯU VÀO DATABASE
        doc = frappe.get_doc({
            "doctype":              "AI Candidate Report",
            "candidate_name":       data.get("candidate_name") or "Unknown",
            "ai_test_url":          url,
            "ai_test_total":        ai_total,
            "ai_test_label":        ai_label,
            "ai_test_table":        json.dumps(rows, ensure_ascii=False),
            "analysis_date":        datetime.now(),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    else:
        phan_a = data.get("phan_a", [])
        phan_b = data.get("phan_b", [])

        # Tính lại từng phần
        total_a = round(sum(float(r.get("diem", 0)) for r in phan_a), 1)
        total_b = round(sum(float(r.get("diem_cham", 0)) for r in phan_b), 1)
        total   = round(total_a + total_b, 1)

        if total >= 91:
            ket_luan = "XUẤT SẮC"
        elif total >= 75:
            ket_luan = "GIỎI"
        elif total >= 50:
            ket_luan = "TRUNG BÌNH"
        else:
            ket_luan = "KHÔNG PHÙ HỢP"

        result = {
            "type":           "5g",
            "candidate_name": data.get("candidate_name", ""),
            "phan_a":         phan_a,
            "phan_b":         phan_b,
            "total_phan_a":   total_a,
            "total_phan_b":   total_b,
            "total":          total,
            "ket_luan":       ket_luan,
            "nhan_xet_chung": data.get("nhan_xet_chung", ""),
        }
        
        # LƯU VÀO DATABASE
        swat_table = []
        if phan_a: swat_table.extend(phan_a)
        if phan_b: swat_table.extend(phan_b)
        
        # Map sang giá trị Select hợp lệ của DocType (chỉ cho phép "ĐẠT" hoặc "KHÔNG ĐẠT")
        # swat_label_db = "ĐẠT" if ket_luan in ("Xuất sắc", "Giỏi") else "KHÔNG ĐẠT"

        doc = frappe.get_doc({
            "doctype":              "AI Candidate Report",
            "candidate_name":       data.get("candidate_name") or "Unknown",
            "g5_test_url":          url,
            "swat_total":           total,
            "swat_label":           ket_luan,
            "swat_table":           json.dumps(swat_table, ensure_ascii=False),
            "analysis_date":        datetime.now(),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

    if api_use_cache:
        frappe.cache().set_value(cache_key, result, expires_in_sec=86400)

    return result

