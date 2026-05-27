"""
test_score_api.py – Local test script cho endpoint score_tests
Usage:
    python test_score_api.py
    python test_score_api.py --no-cache
    python test_score_api.py --endpoint generate_candidate_report
"""
import requests, json, sys, os, argparse
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL    = "http://127.0.0.1:8000"
API_TOKEN   = os.getenv("FRAPPE_TOKEN", "")   # export FRAPPE_TOKEN=key:secret

# Các link bài test (thay bằng link thật khi cần)
AI_TEST_URL  = "https://hr-dev.ctgroupvietnam.com/survey/print/888e33e9-fdba-4da7-9f3a-d670f0cf7f20?answer_token=37a3d8e6-35cf-42c0-828e-c8020e044eaa"
G5_TEST_URL  = "https://hr-dev.ctgroupvietnam.com/survey/print/01146d26-7f68-4390-b0d4-5bb683b02aee?answer_token=bad215b1-dee6-4409-a098-f4e02f8e937c"
EQ_TEST_URL  = ""
SURVEY_URL   = "http://10.6.10.12:8069/survey/result/819/53d69ba4-ead8-4a0d-b831-72bb8e1b0567"
JD_TEXT      = "Vị trí Senior Fullstack Developer thuộc Khối DAIT, yêu cầu AI First mindset."

# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers():
    h = {"Accept": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"token {API_TOKEN}"
    return h

def _print_section(title: str):
    bar = "═" * 70
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)

def _print_table(rows: list, columns: list, widths: list):
    """In bảng ASCII từ list of dict."""
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = "| " + " | ".join(f"{{:<{w}}}" for w in widths) + " |"
    print(sep)
    print(fmt.format(*[c[:w] for c, w in zip(columns, widths)]))
    print(sep)
    for r in rows:
        vals = [str(r.get(c, ""))[:w] for c, w in zip(columns, widths)]
        print(fmt.format(*vals))
    print(sep)

# ── Endpoint: score_tests ─────────────────────────────────────────────────────

def test_score_tests(use_cache: bool = False):
    _print_section("POST /api/method/ai_ats.api.score_tests")

    url = f"{BASE_URL}/api/method/ai_ats.api.score_tests"
    payload = {
        "ai_test_url":  AI_TEST_URL,
        "g5_test_url":  G5_TEST_URL,
        "eq_test_url":  EQ_TEST_URL,
        "survey_url":   SURVEY_URL,
        "jd_text":      JD_TEXT,
        "api_use_cache": "1" if use_cache else "0",
    }

    print(f"  URL    : {url}")
    print(f"  Cache  : {'ON' if use_cache else 'OFF'}")
    print()

    try:
        r = requests.post(url, data=payload, headers=_headers(), timeout=300)
    except requests.exceptions.ConnectionError:
        print("❌ Không kết nối được tới server. Chạy: bench start")
        return

    print(f"  Status : {r.status_code}")

    if r.status_code != 200:
        print(f"  Error  : {r.text[:500]}")
        return

    body = r.json()
    data = body.get("message", body)   # Frappe wrap trong "message"

    # 1. In bảng AI Test
    _print_section("BẢNG AI TEST (thang 100)")
    ai_rows = data.get("ai_test_table", [])
    if ai_rows:
        _print_table(
            ai_rows,
            columns=["cau", "noi_dung", "diem_toi_da", "diem_cham", "ly_do"],
            widths  =[4,     28,          8,             8,           50],
        )
    print(f"\n  ► TỔNG AI TEST : {data.get('ai_test_total', 0)}/100  →  [{data.get('ai_test_label', '')}]")

    # 2. In bảng SWAT
    _print_section("BẢNG SWAT ELITE (thang 10)")
    swat_rows = data.get("swat_table", [])
    if swat_rows:
        _print_table(
            swat_rows,
            columns=["tru_cot", "ty_trong", "diem_tho", "diem_trong_so", "co_so"],
            widths  =[30,        8,           8,          10,              45],
        )
    print(f"\n  ► TỔNG SWAT    : {data.get('swat_total', 0)}/10  →  [{data.get('swat_label', '')}]")

    # 3. In bảng 5G
    _print_section("BẢNG 5G TEST (thang 100)")
    g5_rows = data.get("g5_table", [])
    if g5_rows:
        _print_table(
            g5_rows,
            columns=["tieu_chi", "diem_toi_da", "diem_cham", "ly_do"],
            widths  =[45,         8,             8,           50],
        )
    print(f"\n  ► TỔNG 5G      : {data.get('g5_total', 0)}/100")

    # 4. Decision
    _print_section("QUYẾT ĐỊNH CUỐI")
    decision = data.get("decision", "")
    icon = "✅" if decision == "ĐẠT" else "❌"
    print(f"\n  {icon}  {decision}")
    print(f"  Ứng viên: {data.get('candidate_name', '(không có)')}")

    # 5. In raw tables_text nếu có (server đã format sẵn)
    if data.get("tables_text"):
        _print_section("tables_text (từ server)")
        print(data["tables_text"])

# ── Endpoint: generate_candidate_report ──────────────────────────────────────

def test_generate_report(use_cache: bool = True):
    _print_section("POST /api/method/ai_ats.api.generate_candidate_report")

    url = f"{BASE_URL}/api/method/ai_ats.api.generate_candidate_report"
    cv_path = Path(__file__).parent / "Hồ Đắc Quân_CV.pdf"

    payload = {
        "ai_test_url":  AI_TEST_URL,
        "g5_test_url":  G5_TEST_URL,
        "eq_test_url":  EQ_TEST_URL,
        "survey_url":   SURVEY_URL,
        "jd_text":      JD_TEXT,
        "api_use_cache": "1" if use_cache else "0",
    }

    files = {}
    if cv_path.exists():
        files["cv_file"] = ("cv.pdf", cv_path.read_bytes(), "application/pdf")
        print(f"  CV file : {cv_path.name}")
    else:
        print(f"  CV file : (không tìm thấy {cv_path.name}, bỏ qua)")

    try:
        r = requests.post(url, data=payload, files=files or None,
                          headers=_headers(), timeout=300)
    except requests.exceptions.ConnectionError:
        print("❌ Không kết nối được tới server. Chạy: bench start")
        return

    print(f"  Status : {r.status_code}")
    if r.status_code != 200:
        print(f"  Error  : {r.text[:500]}")
        return

    body = r.json()
    data = body.get("message", body)

    # In report_text
    if data.get("report_text"):
        _print_section("REPORT TEXT")
        print(data["report_text"])

    _print_section("SCORES SUMMARY")
    print(f"  AI Test : {data.get('ai_test_total', 0)}/100  [{data.get('ai_test_label', '')}]")
    print(f"  SWAT    : {data.get('swat_total', 0)}/10  [{data.get('swat_label', '')}]")
    print(f"  5G      : {data.get('g5_total', 0)}/100")
    icon = "✅" if data.get("decision") == "ĐẠT" else "❌"
    print(f"  Decision: {icon}  {data.get('decision', '')}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local API test cho AI ATS")
    parser.add_argument("--endpoint", choices=["score_tests", "generate_candidate_report"],
                        default="score_tests", help="Endpoint cần test (mặc định: score_tests)")
    parser.add_argument("--cache", action="store_true", default=False,
                        help="Bật cache (mặc định OFF cho score_tests)")
    parser.add_argument("--base-url", default=BASE_URL,
                        help=f"Base URL (mặc định: {BASE_URL})")
    args = parser.parse_args()

    BASE_URL = args.base_url

    if args.endpoint == "score_tests":
        test_score_tests(use_cache=args.cache)
    else:
        test_generate_report(use_cache=args.cache)
