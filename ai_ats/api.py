"""
AI ATS – API Endpoints
/api/method/ai_ats.api.generate_candidate_report
/api/method/ai_ats.api.get_context
"""
import io, json, re, warnings, hashlib, uuid
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

def _scrape_playwright(url: str) -> str:
    """Dùng Playwright headless để render JS rồi lấy text. Dùng khi HTTP scrape thất bại."""
    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(viewport={"width": 1280, "height": 900})
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(2000)
                    return await page.inner_text("body")
                finally:
                    await browser.close()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, _run()).result(timeout=40)
            else:
                return loop.run_until_complete(_run())
        except RuntimeError:
            return asyncio.run(_run())
    except Exception:
        return ""

def _scrape_many_playwright(urls: list) -> list:
    """Scrape nhiều URL song song trong 1 browser — nhanh hơn gọi riêng lẻ."""
    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    async def fetch(url):
                        if not url:
                            return ""
                        try:
                            page = await browser.new_page(viewport={"width": 1280, "height": 900})
                            await page.goto(url, wait_until="networkidle", timeout=30000)
                            await page.wait_for_timeout(2000)
                            txt = await page.inner_text("body")
                            await page.close()
                            return txt
                        except Exception:
                            return ""
                    return await asyncio.gather(*[fetch(u) for u in urls])
                finally:
                    await browser.close()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return list(pool.submit(asyncio.run, _run()).result(timeout=60))
            else:
                return list(loop.run_until_complete(_run()))
        except RuntimeError:
            return list(asyncio.run(_run()))
    except Exception:
        return [""] * len(urls)

def _scrape(url: str) -> str:
    """Scrape URL. Thử HTTP trước, nếu không lấy được data (JS-only, 403, empty...)
    thì tự động fallback sang Playwright headless. Trả "" nếu cả hai đều fail."""
    if not url: return ""
    # Bước 1: HTTP scrape (nhanh ~1-2s)
    try:
        r = requests.get(url, timeout=15, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script","style","nav","footer","header"]): t.decompose()
        txt = soup.get_text(separator="\n", strip=True)
        if len(txt) > 100:
            return txt
    except Exception:
        pass
    # Bước 2: Playwright fallback
    txt = _scrape_playwright(url)
    return txt if len(txt) > 100 else ""

def _scrape_parallel(urls: dict) -> dict:
    """Scrape nhiều URL song song. urls = {key: url}. Trả {key: text}."""
    keys = list(urls.keys())
    url_list = [urls[k] for k in keys]

    # Bước 1: HTTP scrape song song
    import concurrent.futures
    results = {}
    need_playwright = []

    def http_scrape(key_url):
        key, url = key_url
        if not url:
            return key, ""
        try:
            r = requests.get(url, timeout=15, verify=False)
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script","style","nav","footer","header"]): t.decompose()
            txt = soup.get_text(separator="\n", strip=True)
            return key, txt if len(txt) > 100 else None  # None = cần Playwright
        except Exception:
            return key, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for key, result in pool.map(http_scrape, [(k, urls[k]) for k in keys]):
            results[key] = result

    # Bước 2: Playwright cho các URL HTTP thất bại — song song trong 1 browser
    pw_keys = [k for k in keys if results[k] is None]
    pw_urls = [urls[k] for k in pw_keys]
    if pw_keys:
        pw_results = _scrape_many_playwright(pw_urls)
        for k, txt in zip(pw_keys, pw_results):
            results[k] = txt if len(txt) > 100 else ""

    # Đảm bảo không có None
    return {k: (results[k] or "") for k in keys}




def _extract_citation_value(line: str) -> str:
    """Lấy phần nội dung trong '...' của một dòng citation."""
    m = re.search(r"→\s*\[[^\]]+\]\s*'([^']+)'", line)
    if m: return m.group(1).strip()
    m = re.search(r'→\s*\[[^\]]+\]\s*"([^"]+)"', line)
    if m: return m.group(1).strip()
    m = re.search(r"→\s*\[[^\]]+\]\s*(.+)", line)
    if m: return m.group(1).strip()
    return ""

def _clean_citations(text: str) -> str:
    """Gộp nội dung citation →[Nguồn] '...' vào dòng bullet chính, không xóa trắng."""
    if not text or not isinstance(text, str):
        return text
    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Dòng citation độc lập → gộp vào dòng main trước đó
        if stripped.startswith("→[") or stripped.startswith("→ ["):
            val = _extract_citation_value(stripped)
            if val and result:
                last = result[-1].rstrip(".").rstrip(";")
                sep = " — " if (" — " not in last and " —" not in last) else "; "
                result[-1] = last + sep + val
            i += 1
            continue

        # Inline citation trong câu → bóc nội dung gộp vào
        if "→[" in line or "→ [" in line:
            vals = re.findall(r"→\s*\[[^\]]+\]\s*'([^']+)'", line)
            if not vals:
                vals = re.findall(r'→\s*\[[^\]]+\]\s*"([^"]+)"', line)
            # Xóa phần →[...] khỏi dòng
            clean = re.sub(r"→\s*\[[^\]]+\]\s*'[^']*'", "", line)
            clean = re.sub(r'→\s*\[[^\]]+\]\s*"[^"]*"', "", clean)
            clean = re.sub(r"→\s*\[[^\]]+\]", "", clean)
            clean = clean.strip().rstrip(";,").strip()
            if vals:
                suffix = "; ".join(v.strip() for v in vals if v.strip())
                if clean:
                    sep = " — " if (" — " not in clean) else "; "
                    clean = clean + sep + suffix
                else:
                    clean = suffix
            if clean:
                result.append(clean)
            i += 1
            continue

        if stripped:
            result.append(line)
        i += 1
    # Xóa pattern "– [Level]" hoặc "– [Thành thạo/Advanced/Intermediate/...]" còn sót
    cleaned = []
    for line in result:
        line = re.sub(r'\s*[–-]\s*\[(Advanced|Intermediate|Basic|Thành thạo|Trung cấp|Cơ bản|Nâng cao|Proficient|Beginner|Expert|Senior|Junior)[^\]]*\]', '', line)
        cleaned.append(line)
    return "\n".join(cleaned)

def _add_spacing(text: str) -> str:
    """Thêm blank line giữa các mục bullet ●/• để dễ đọc hơn."""
    if not text:
        return text
    lines = text.split("\n")
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Nếu dòng hiện tại là bullet mới và dòng trước không phải blank → thêm blank line
        if stripped and (stripped.startswith("●") or stripped.startswith("•")) and result and result[-1] != "":
            result.append("")
        result.append(line)
    return "\n".join(result)

def _clean_data(data: dict) -> dict:
    """Xóa citation + thêm spacing cho tất cả các text field trong response."""
    text_fields = [
        "strength_tech_skills", "strength_exceeding",
        "gap_missing_skills", "gap_risks",
        "best_at_core", "best_at_2as_ops", "best_at_2as_ready", "best_at_global",
    ]
    for field in text_fields:
        if field in data and isinstance(data[field], str):
            data[field] = _add_spacing(_clean_citations(data[field]))
    return data

# ── Schema prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """Bạn là AI Agent đánh giá ứng viên cho CT Group (NoAI-NoHire).

⚠️ QUY TẮC VIẾT VĂN PHONG BẮT BUỘC (ưu tiên cao nhất):
TUYỆT ĐỐI KHÔNG dùng format citation kiểu "→[CV] '...'" hay "→[AI Test Câu X] '...'" hay "→[Nguồn] '...'" trong bất kỳ phần phân tích nào.
Thay vào đó: viết văn xuôi tiếng Việt tự nhiên, tổng hợp thông tin từ tất cả nguồn vào một câu/đoạn mạch lạc.
VÍ DỤ SAI (không được viết thế này):
  "• Python – Thành thạo →[CV] 'Built platform' →[AI Test Câu 4] 'Soạn tài liệu'"
VÍ DỤ ĐÚNG (viết như thế này):
  "• Python ở mức thành thạo — ứng viên đã xây dựng và vận hành nền tảng thương mại điện tử công nghiệp, phỏng vấn hội đồng chuyên môn cho 4/5 điểm kỹ năng áp dụng công nghệ thực tế."

Áp dụng quy tắc xuất báo cáo gồm 2 phần BẮT BUỘC:

Phần I: Tổng quan Hồ sơ & Điểm số (Executive Summary)
- AI Readiness Index (Chỉ số sẵn sàng AI): Điểm số tổng hợp (Thang điểm 100) -> ai_test_total.
- Phân loại Ứng viên (ai_test_label): Dựa trên kết quả, phân loại thành [AI-Ready] hoặc [Non-AI].
- Chấm điểm SWAT Elite (Thang 10) -> swat_total.
- Kết quả SWAT Elite (swat_label): Đánh giá [Swat-Elite] (nếu swat_total >= 6.0) hoặc [KHÔNG ĐẠT] (nếu swat_total < 6.0) (chấm nới điểm để dễ pass).
- Chấm điểm 5G Test (Thang 100) -> g5_total. CÁCH CHẤM 5G (tài liệu 04.06.2026): Phần A = 15 câu TN (30đ). Phần B = 15 câu TL (70đ). PHẢI điền g5_table đủ 9 hàng với diem_toi_da ĐÚNG như sau: G1=7đ (TN câu1:2đ + TL câu16:5đ), G2=16đ (TN câu2-4:6đ + TL câu17-18:10đ), G3=12đ (TN câu5:2đ + TL câu19-20:10đ), G4=26đ (TN câu6-13:16đ + TL câu21-22:10đ), G5=14đ (TN câu14-15:4đ + TL câu23-24:10đ), Thích nghi=5đ (TL câu25), Đàm phán=5đ (TL câu26), Quản lý thời gian=10đ (TL câu27:3đ+câu28:3đ+câu29:4đ), Đánh giá level=5đ (TL câu30). Tổng g5_total = 100đ. Đối chiếu đáp án từ Rubric 5G để tính điểm chính xác. KHÔNG để nguyên giá trị mặc định 0.
- LƯU Ý CHỐNG BỊA ĐẶT (Hallucination): Điểm AI Test PHẢI được chấm hoàn toàn dựa trên nội dung TEST AI. Điểm SWAT và 5G PHẢI dựa hoàn toàn trên nội dung TEST 5G. Nếu nội dung test bị lỗi, rỗng hoặc thiếu thông tin, TUYỆT ĐỐI KHÔNG tự bịa điểm (phải cho 0 điểm).
- LỌC NHIỄU TÀI LIỆU HƯỚNG DẪN: Trong các tài liệu Hướng dẫn chấm điểm (Rubric) có thể có nhiều thông tin dư thừa. Bạn PHẢI BỎ QUA các phần râu ria và CHỈ TẬP TRUNG vào đúng "khung tiêu chuẩn chấm điểm" (barem/rubric) cốt lõi để đối chiếu với bài làm của ứng viên.
- QUY TẮC TÀN KHỐC ĐỂ RA QUYẾT ĐỊNH (decision): Vì công ty áp dụng "No AI - No Hire", nếu ai_test_label là "Non-AI" HOẶC g5_total < 60.0 HOẶC swat_total < 6.0, thì BẮT BUỘC Quyết định (decision) = "KHÔNG ĐẠT" (Cúc luôn!). Chỉ được đánh giá "ĐẠT" khi tất cả đều qua môn.

Phần II: Phân tích Năng lực Chuyên sâu (Core Analysis)

📋 HƯỚNG DẪN ĐỌC DỮ LIỆU PHỎNG VẤN (BẢNG DỮ LIỆU ỨNG VIÊN / Survey):
Dữ liệu Survey thường là "BẢNG DỮ LIỆU ỨNG VIÊN" từ hệ thống HR, gồm nhiều vòng phỏng vấn:
  - Vòng 1 (Sơ loại/HR): điểm từng tiêu chí, nhận xét ban đầu
  - Vòng 2 (Hội đồng chuyên môn): điểm 1–5 theo 21 tiêu chí năng lực (giao tiếp, ra quyết định, tư duy logic, văn hóa tốc độ...)
  - Vòng 3 (BOD): đánh giá tổng quan, điểm nghẽn, lý do trao cơ hội, kế hoạch KPI thử việc, kết luận cuối
KHI CÓ DỮ LIỆU SURVEY, BẮT BUỘC:
  - Trích điểm cụ thể từng vòng (ví dụ: "Vòng 2: Tiêu chí 13 – Văn hóa tốc độ: 5/5")
  - Trích nguyên văn nhận xét của phỏng vấn viên (không diễn giải lại)
  - Nêu kết luận từng vòng (Qua vòng / Không qua) và lý do BOD
  - Đối chiếu chéo: điểm từng vòng Survey ↔ điểm AI Test ↔ CV để tìm mâu thuẫn hoặc xác nhận chéo
Nguồn evidence từ Survey: dùng format "[Survey Vòng X] '...(trích nguyên văn nhận xét hoặc điểm tiêu chí)...'"

QUY TẮC VIẾT PHÂN TÍCH (áp dụng cho TOÀN BỘ Phần II):
Viết bằng tiếng Việt, văn xuôi tự nhiên, mạch lạc — KHÔNG dùng format citation cứng nhắc như "→[CV] '...'" hay "→[Nguồn] '...'".
Thay vào đó: tổng hợp thông tin từ tất cả nguồn (CV, 5G, Survey, JD) rồi viết thành đoạn văn hoặc bullet point tự nhiên.

ĐỊNH DẠNG MARKDOWN BẮT BUỘC:
- Dùng **bold** để nhấn mạnh kỹ năng quan trọng, điểm số nổi bật, kết luận chính
- Dùng xuống dòng và bullet • để phân tách rõ từng ý
- Mỗi bullet point phải đủ dài (2–5 câu), không viết quá ngắn kiểu liệt kê
- Dùng emoji tiết kiệm để đánh dấu mức độ: ✅ tốt, ⚠️ cần cải thiện, ❌ thiếu hụt nghiêm trọng

VÍ DỤ ĐÚNG:
"• **Python** ở mức nâng cao — ứng viên đã xây dựng và vận hành nền tảng thương mại điện tử công nghiệp hơn 3 năm, thể hiện qua dự án recruitment portal xử lý hàng nghìn đơn ứng tuyển mỗi ngày. Hội đồng chuyên môn Vòng 2 đánh giá **4/5** tiêu chí áp dụng công nghệ thực tế — cao hơn mức trung bình của pool ứng viên cùng vị trí."
VÍ DỤ SAI (quá ngắn): "• Python – ứng viên có kinh nghiệm Python."

KHÔNG được tự bịa thông tin không có trong dữ liệu. Nếu không có dữ liệu, bỏ qua hoặc ghi "Không có thông tin".
Mỗi trường tối thiểu 5–8 bullet, mỗi bullet 3–5 câu phân tích sâu. KHÔNG rút gọn. Viết càng chi tiết càng tốt.

1. strengths (ĐIỂM MẠNH) — Đối chiếu chéo: CV ↔ JD ↔ điểm test ↔ Survey:

  strength_tech_skills: Kỹ năng công nghệ & năng lực chuyên môn nổi trội. Phân tích theo 3 tầng:
  ⛔ CẤM TUYỆT ĐỐI: strength_tech_skills KHÔNG được dùng [AI Test Câu X] làm evidence.
  VÍ DỤ SAI: "• [Python] → [AI Test Câu 4] '...'" — SAI, AI Test không được phép ở đây.
  NGUỒN DUY NHẤT được phép: [CV], [JD], [5G Câu Y], [Survey Vòng X].
    [A] NĂNG LỰC KỸ THUẬT — Với TỪNG tool/tech/platform, nêu: tên công nghệ + mức độ thành thạo + evidence từ ÍT NHẤT 2 nguồn khác nhau (CV xác nhận kinh nghiệm, test chứng minh hiểu sâu). Format: "• **[Tool/Tech]** — [3–5 câu mô tả: số năm kinh nghiệm, dự án cụ thể đã làm, mức độ thành thạo thực tế, điểm/nhận xét phỏng vấn nếu có]"
    [B] KỸ NĂNG MỀM & TƯ DUY — Trích dẫn ÍT NHẤT 2 nguồn từ 5G, Survey hoặc nhận xét phỏng vấn viên thể hiện tư duy phân tích, giao tiếp, ra quyết định. Ưu tiên trích điểm tiêu chí Survey Vòng 2 (21 tiêu chí). Format: "• **[Kỹ năng]** — [3–5 câu phân tích: biểu hiện cụ thể từ phỏng vấn, điểm tiêu chí Survey nếu có, nhận xét hội đồng, ví dụ thực tế]"
    [C] PHÙ HỢP JD — Liệt kê từng yêu cầu cốt lõi trong JD, đánh dấu ✓✓/✓/~ kèm evidence. Format: "• [Yêu cầu JD: ...] ✓✓ — [đánh giá mức độ đáp ứng kèm mô tả cụ thể]"

  strength_exceeding: Các điểm VƯỢT CHUẨN so với JD (added value ứng viên mang lại).
  ❌ NGUỒN BỊ CUẤM: Tuyệt đối KHÔNG dùng AI Test làm evidence cho mục này. Chỉ dùng: CV, JD, 5G, Survey.
    Tối thiểu 3 điểm, mỗi điểm: nêu năng lực + giải thích giá trị với CT Group/2AS + evidence cụ thể. Format: "• **[Năng lực X]** — JD không yêu cầu nhưng mang lại giá trị cho CT Group/2AS vì [lý do cụ thể, liên kết đến business impact]. [3–4 câu mô tả: biểu hiện thực tế từ CV/phỏng vấn, ví dụ cụ thể, tiềm năng đóng góp từ tuần đầu]"

2. gaps (ĐIỂM HẠN CHẾ) — Phân tích thẳng thắn, có bằng chứng:

  gap_missing_skills: KỸ NĂNG & TƯ DUY THIẾU HỤT
  ✅ NGUỒN DẪN CHỨNG HỢP LỆ: CV, JD, Survey, 5G Câu Y, AI Test Câu X (phần này ĐƯỢC PHÉP dùng AI Test làm dẫn chứng).
  Phân loại:
    ❌ **[THIẾU CỨNG – CRITICAL]** Thiếu hoàn toàn, ảnh hưởng trực tiếp năng suất: nêu kỹ năng cụ thể + giải thích tại sao critical với vai trò này + bằng chứng từ CV và bài thi + đánh giá rủi ro nếu tuyển dụng. Viết ít nhất 3–4 câu.
    ⚠️ **[CẦN CẢI THIỆN – MODERATE]** Có nhưng chưa đủ sâu: so sánh yêu cầu JD vs năng lực hiện tại cụ thể, mô tả biểu hiện thiếu hụt từ bài thi hoặc phỏng vấn, đề xuất timeline cải thiện. Viết ít nhất 3–4 câu.
    [TƯ DUY AI-FIRST – MINOR/MODERATE] Trích dẫn ÍT NHẤT 1 câu trả lời cụ thể từ AI Test chứng minh ứng viên chỉ surface-level: "[AI Test Câu X] '...(nguyên văn)...' — Nhận xét: câu này cho thấy ứng viên chưa hiểu sâu về [...] vì [...]"

  gap_risks: 🛡️ RỦI RO VẬN HÀNH & BẢO MẬT
  ✅ NGUỒN DẪN CHỨNG HỢP LỆ: CV, Survey, 5G, AI Test Câu X (phần này ĐƯỢC PHÉP dùng AI Test làm dẫn chứng).
  MỖI rủi ro phải kèm evidence từ bài làm:
    • Rủi ro bảo mật: đánh giá xem có dấu hiệu tiết lộ thông tin nhạy cảm không, mô tả cụ thể.
    • Rủi ro hiệu suất: đánh giá mức độ cần hỗ trợ dựa trên kết quả bài thi và phỏng vấn, nêu cụ thể điểm yếu.
    • Rủi ro văn hóa AI: đánh giá thái độ với AI từ bài thi AI Test, nêu dấu hiệu cụ thể nếu có.
    • Rủi ro reliability: câu trả lời mâu thuẫn hoặc thiếu nhất quán? → so sánh [Nguồn A] '...' với [Nguồn B] '...'

3. best_at (NĂNG LỰC NỔI BẬT NHẤT) — Tổng hợp & định vị:

  best_at_core: Trả lời thẳng: "Ứng viên này BEST AT [X]" — X là 1 câu rõ ràng, đầy đủ, gắn với JD.
  ⛔ CẤM TUYỆT ĐỐI: best_at_core KHÔNG được dùng [AI Test Câu X] làm evidence.
  VÍ DỤ SAI: "• [Tư duy AI First] → [AI Test Câu 8] '...'" — SAI, AI Test không được phép ở đây.
  NGUỒN DUY NHẤT được phép: [CV], [JD], [5G Câu X], [Survey Vòng X].
    Sau đó liệt kê top 3 năng lực core có thể đóng góp ngay từ tuần đầu, mỗi năng lực kèm:
    - Evidence từ CV (kinh nghiệm thực tế đã làm)
    - Evidence từ 5G hoặc Survey (chứng minh hiểu sâu, không chỉ nói suông)
    Format: "• **[Năng lực]** — [4–6 câu phân tích sâu: mô tả năng lực cụ thể, kinh nghiệm thực tế từ CV, kết quả phỏng vấn/Survey, impact tiềm năng trong tuần đầu tại CT Group]"

  best_at_2as_ops: NĂNG LỰC VẬN HÀNH AI / 2AS
  ✅ NGUỒN DẪN CHỨNG HỢP LỆ: CV, Survey, AI Test Câu X (phần này ĐƯỢC PHÉP dùng AI Test làm dẫn chứng).
  Trả lời 3 câu hỏi có evidence:
    **(1) AI Tools đang dùng:** Liệt kê từng tool theo format "**[Tên tool]** — [cách dùng cụ thể trong công việc hàng ngày, frequency, use case]". Mỗi tool ít nhất 2 câu.
    **(2) Mức hands-on:** Phân tích chi tiết mức độ: chỉ prompt cơ bản / custom prompt / config workflow / orchestrate multi-agent? Dẫn chứng cụ thể từ bài thi. Ít nhất 3 câu.
    (3) Tiềm năng 30–60 ngày: dựa trên điểm AI Test Câu 5 (Prompt Engineering) + Câu 10 (AI Growth Plan) → trích dẫn
    Kết luận: Sơ cấp / Trung cấp / Nâng cao — giải thích tại sao

  best_at_2as_ready: MỨC ĐỘ AI-READINESS. Phân loại [AI-Native/Willing/Hesitant/Resistant]:
  ✅ NGUỒN DẪN CHỨNG HỢP LỆ: CV, Survey, AI Test Câu X (phần này ĐƯỢC PHÉP dùng AI Test làm dẫn chứng).
    - AI Test Câu 8 (AI Mindset): trích dẫn nguyên văn + phân tích thái độ
    - AI Test Câu 6 (AI x Teamwork): trích dẫn nguyên văn + phân tích mức độ ứng dụng nhóm
    - Từ Survey Vòng 3 (BOD): nhận xét về AI mindset, tư duy tự động hóa → '[Survey Vòng 3] ...'
    - Từ Survey Vòng 2: điểm tiêu chí liên quan AI/công nghệ → '[Survey Vòng 2] Tiêu chí X: Y/5'
    - Từ CV: có dự án AI thực chiến nào không? → '[CV] ...'
    Kết luận phân loại kèm lý do cụ thể dựa trên các nguồn trên

  best_at_global: Ngoại ngữ & thực chiến quốc tế:
  ❌ NGUỒN BỊ CUẤM: Tuyệt đối KHÔNG dùng AI Test làm evidence cho mục này. Chỉ dùng: CV, 5G, Survey.
    (1) Trình độ thực tế: có câu trả lời nào bằng tiếng Anh không? Chất lượng thế nào? → [đánh giá trình độ thực tế dựa trên CV và bài thi]
    (2) Kinh nghiệm quốc tế: → [mô tả kinh nghiệm quốc tế nếu có]
    (3) Multicultural readiness: → [đánh giá dựa trên thông tin có sẵn]


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
    {"tieu_chi":"G1 – Giao tiếp (Communication)",                             "diem_toi_da":7,  "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G2 – Giao lưu/Cọ xát thực tế (Exposure & Interaction)",     "diem_toi_da":16, "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G3 – Giám sát (Supervision)",                               "diem_toi_da":12, "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G4 – Giải quyết vấn đề/Gỡ rối (Problem Solving)",          "diem_toi_da":26, "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"G5 – Giảng dạy/Hướng dẫn (Training & Coaching)",           "diem_toi_da":14, "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"Kỹ năng thích nghi (Adaptability)",                         "diem_toi_da":5,  "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"Kỹ năng đàm phán (Negotiation)",                            "diem_toi_da":5,  "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"Kỹ năng quản lý thời gian & ưu tiên (Time Management)",    "diem_toi_da":10, "diem_cham":0.0,"ly_do":""},
    {"tieu_chi":"Đánh giá level cá nhân (Self-Assessment)",                 "diem_toi_da":5,  "diem_cham":0.0,"ly_do":""}
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

@frappe.whitelist(allow_guest=True)
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

        # Scrape links — nếu không đọc được thì trả rỗng, AI bỏ qua section đó
        _scraped = _scrape_parallel({"ai": ai_test_url, "g5": g5_test_url, "eq": eq_test_url, "sv": survey_url})
        ai_txt = _scraped["ai"]; g5_txt = _scraped["g5"]; eq_txt = _scraped["eq"]; sv_txt = _scraped["sv"]

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
### PHỎNG VẤN / BẢNG DỮ LIỆU ỨNG VIÊN (Survey): {sv_txt[:20000]}
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
                max_tokens=8000,
            )
        data = _clean_data(json.loads(resp.choices[0].message.content))
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

@frappe.whitelist(allow_guest=True)
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
@frappe.whitelist(allow_guest=True)
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

        # Scrape links — nếu không đọc được thì trả rỗng, AI bỏ qua section đó
        _scraped = _scrape_parallel({"ai": ai_test_url, "g5": g5_test_url, "eq": eq_test_url, "sv": survey_url})
        ai_txt = _scraped["ai"]; g5_txt = _scraped["g5"]; eq_txt = _scraped["eq"]; sv_txt = _scraped["sv"]

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
### PHỎNG VẤN / BẢNG DỮ LIỆU ỨNG VIÊN (Survey): {sv_txt[:20000]}
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
                max_tokens=8000,
            )
        data = _clean_data(json.loads(resp.choices[0].message.content))
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
    # ── Session & Action Logging ──
    session_id = frappe.get_request_header("X-App-Session-Id") or ""
    session_name = _ensure_session(session_id)
    action_name = _logger.start_action(
        session_name,
        action_type="score_tests",
        input_summary=f"ai={ai_test_url[:80]}, g5={g5_test_url[:80]}",
    )

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

    _scraped = _scrape_parallel({"ai": ai_test_url, "g5": g5_test_url, "eq": eq_test_url, "sv": survey_url})
    ai_txt = _scraped["ai"]; g5_txt = _scraped["g5"]; eq_txt = _scraped["eq"]; sv_txt = _scraped["sv"]

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
### PHỎNG VẤN / BẢNG DỮ LIỆU ỨNG VIÊN (Survey): {sv_txt[:20000]}
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

    with Timer() as t:
        resp = _get_gpt().chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=8000,
        )
    data = json.loads(resp.choices[0].message.content)
    _usage = resp.usage
    _p_tok = _usage.prompt_tokens if _usage else 0
    _c_tok = _usage.completion_tokens if _usage else 0
    _logger.log_ai_call(
        session_name, action_name,
        call_type="score_tests", ai_model="gpt-4o",
        prompt_tokens=_p_tok, completion_tokens=_c_tok,
        duration_seconds=t.elapsed, status="success",
    )

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

    _logger.finish_action(
        action_name, status="success",
        output_summary=f"ai={data.get('ai_test_total',0)}, swat={data.get('swat_total',0)}, g5={data.get('g5_total',0)}",
        ai_model="gpt-4o",
        prompt_tokens=_p_tok, completion_tokens=_c_tok,
        duration_seconds=t.elapsed,
    )
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
- Phần B: 15 câu tự luận (câu 16–30) = 70 điểm. Phân bổ điểm theo tài liệu 04.06.2026:
  G1 Giao tiếp: câu 16 (5đ).
  G2 Giao lưu/Cọ xát: câu 17 (5đ) + câu 18 (5đ).
  G3 Giám sát: câu 19 (5đ) + câu 20 (5đ).
  G4 Giải quyết vấn đề: câu 21 (5đ) + câu 22 (5đ).
  G5 Giảng dạy/Hướng dẫn: câu 23 (5đ) + câu 24 (5đ).
  Kỹ năng thích nghi: câu 25 (5đ).
  Kỹ năng đàm phán: câu 26 (5đ).
  Quản lý thời gian & ưu tiên: câu 27 (3đ) + câu 28 (3đ) + câu 29 (4đ).
  Đánh giá level cá nhân: câu 30 (5đ).

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
    # ── Session & Action Logging ──
    session_id = frappe.get_request_header("X-App-Session-Id") or ""
    session_name = _ensure_session(session_id)
    action_name = _logger.start_action(
        session_name,
        action_type="score_single",
        input_summary=f"type={type}, url={url[:80]}",
    )

    test_type = str(type).strip().lower()
    if test_type not in ("ai", "5g"):
        _logger.finish_action(action_name, status="failed", error_message="Invalid type")
        frappe.throw("type phải là 'ai' hoặc '5g'", frappe.ValidationError)
    if not url:
        _logger.finish_action(action_name, status="failed", error_message="Missing url")
        frappe.throw("url không được để trống", frappe.ValidationError)

    if isinstance(api_use_cache, str):
        api_use_cache = api_use_cache.lower() in ['true', '1', 't', 'yes']
    else:
        api_use_cache = bool(api_use_cache)

    # Scrape bài làm
    content = _scrape(url)
    if content.startswith("["):
        _logger.finish_action(action_name, status="failed", error_message=f"Scrape failed: {content[:200]}")
        frappe.throw(f"Không scrape được nội dung từ URL: {content}", frappe.ValidationError)

    if api_use_cache:
        import hashlib
        raw_key = f"score_single_{test_type}_{url}_{content[:1000]}"
        req_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        cache_key = f"ai_ats_score_single_{req_hash}"
        cached = frappe.cache().get_value(cache_key)
        if cached:
            _logger.finish_action(action_name, status="success", output_summary="from_cache", from_cache=True)
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

    with Timer() as t:
        resp = _get_gpt().chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=max_tok,
        )
    data = json.loads(resp.choices[0].message.content)
    _usage = resp.usage
    _p_tok = _usage.prompt_tokens if _usage else 0
    _c_tok = _usage.completion_tokens if _usage else 0
    _logger.log_ai_call(
        session_name, action_name,
        call_type=f"score_single_{test_type}", ai_model="gpt-4o",
        prompt_tokens=_p_tok, completion_tokens=_c_tok,
        duration_seconds=t.elapsed, status="success",
    )

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
        
        # Map sang giá trị Select hợp lệ: "", "AI-Ready", "Non-AI", "SWAT Elite"
        if ai_label == "Xuất sắc":
            ai_label_db = "SWAT Elite"
        elif ai_label in ("Khá", "Cơ bản"):
            ai_label_db = "AI-Ready"
        else:
            ai_label_db = "Non-AI"

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
            "ai_test_label":        ai_label_db,
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
            ket_luan = "Xuất sắc"
        elif total >= 75:
            ket_luan = "Giỏi"
        elif total >= 50:
            ket_luan = "Trung bình"
        else:
            ket_luan = "Không phù hợp"

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
        swat_label_db = "ĐẠT" if ket_luan in ("Xuất sắc", "Giỏi") else "KHÔNG ĐẠT"

        doc = frappe.get_doc({
            "doctype":              "AI Candidate Report",
            "candidate_name":       data.get("candidate_name") or "Unknown",
            "g5_test_url":          url,
            "swat_total":           total,
            "swat_label":           swat_label_db,
            "swat_table":           json.dumps(swat_table, ensure_ascii=False),
            "analysis_date":        datetime.now(),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

    if api_use_cache:
        frappe.cache().set_value(cache_key, result, expires_in_sec=86400)

    _logger.finish_action(
        action_name, status="success",
        output_summary=f"type={test_type}, total={result.get('total',0)}",
        ai_model="gpt-4o",
        prompt_tokens=_p_tok, completion_tokens=_c_tok,
        duration_seconds=t.elapsed,
    )
    return result

