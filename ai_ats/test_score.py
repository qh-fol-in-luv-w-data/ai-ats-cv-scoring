import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

import frappe
import json
from ai_ats.api import _get_gpt, _SYSTEM, _read_cached, _AI_SCORING_PDF, _G5_SCORING_DOCX, _SWAT_PRD_DOCX, _docx_bytes

def run():
    print("Reading files...")
    ai_ans = _docx_bytes(open("/Users/_qh.fol_/frappe-bench/apps/ai_ats/Bai_lam_AI.docx", "rb").read())
    g5_ans = _docx_bytes(open("/Users/_qh.fol_/frappe-bench/apps/ai_ats/Bai_lam_5g.docx", "rb").read())
    ai_guide = _read_cached(_AI_SCORING_PDF, False)
    g5_guide = _read_cached(_G5_SCORING_DOCX, False)
    swat_prd = _read_cached(_SWAT_PRD_DOCX, False)

    user_msg = f"""### CV:
[Không có]
### JD:
[Không có]
### KẾT QUẢ BÀI TEST ỨNG VIÊN:
[AI Test]: {ai_ans}
[5G Test]: {g5_ans}
[EQ/IQ]: [Chưa cung cấp]
[Phỏng vấn]: [Chưa cung cấp]

### TÀI LIỆU HƯỚNG DẪN CHẤM ĐIỂM (RUBRIC TỪ CT GROUP):
[Hướng dẫn chấm AI]: {ai_guide[:15000]}
[Hướng dẫn chấm SWAT]: {swat_prd[:15000]}
[Hướng dẫn chấm 5G]: {g5_guide[:20000]}
Trả về JSON hợp lệ, điền đủ mọi trường."""

    print("Sending to OpenAI...")
    resp = _get_gpt().chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0.2
    )

    data = json.loads(resp.choices[0].message.content)

    # ── Helpers in bảng ───────────────────────────────────────────────────────
    def box(title):
        bar = "═" * 66
        print(f"\n╔{bar}╗")
        print(f"║  {title:<64}║")
        print(f"╚{bar}╝")

    # ── Bảng 1: AI Test ───────────────────────────────────────────────────────
    box("BẢNG CHẤM ĐIỂM AI TEST (thang 100)")
    sep = "+" + "-"*5 + "+" + "-"*30 + "+" + "-"*8 + "+" + "-"*8 + "+" + "-"*45 + "+"
    print(sep)
    print(f"| {'Câu':<3} | {'Nội dung':<28} | {'Tối đa':>6} | {'Điểm':>6} | {'Lý do':<43} |")
    print(sep)
    for r in data.get("ai_test_table", []):
        print(f"| {str(r.get('cau','')):<3} | {str(r.get('noi_dung',''))[:28]:<28} | {str(r.get('diem_toi_da',''))[:6]:>6} | {str(r.get('diem_cham',''))[:6]:>6} | {str(r.get('ly_do',''))[:43]:<43} |")
    print(sep)
    print(f"  ► TỔNG AI TEST: {data.get('ai_test_total', 0)}/100  →  [{data.get('ai_test_label', '')}]")

    # ── Bảng 2: SWAT ──────────────────────────────────────────────────────────
    box("BẢNG CHẤM ĐIỂM SWAT ELITE (thang 10)")
    sep2 = "+" + "-"*32 + "+" + "-"*9 + "+" + "-"*9 + "+" + "-"*10 + "+" + "-"*45 + "+"
    print(sep2)
    print(f"| {'Trụ cột':<30} | {'Tỷ trọng':>7} | {'Điểm thô':>7} | {'Trọng số':>8} | {'Cơ sở':<43} |")
    print(sep2)
    for r in data.get("swat_table", []):
        print(f"| {str(r.get('tru_cot',''))[:30]:<30} | {str(r.get('ty_trong',''))[:7]:>7} | {str(r.get('diem_tho',''))[:7]:>7} | {str(r.get('diem_trong_so',''))[:8]:>8} | {str(r.get('co_so',''))[:43]:<43} |")
    print(sep2)
    print(f"  ► TỔNG SWAT: {data.get('swat_total', 0)}/10  →  [{data.get('swat_label', '')}]")

    # ── Bảng 3: 5G ────────────────────────────────────────────────────────────
    box("BẢNG CHẤM ĐIỂM 5G TEST (thang 100)")
    sep3 = "+" + "-"*47 + "+" + "-"*8 + "+" + "-"*8 + "+" + "-"*45 + "+"
    print(sep3)
    print(f"| {'Tiêu chí':<45} | {'Tối đa':>6} | {'Điểm':>6} | {'Lý do':<43} |")
    print(sep3)
    for r in data.get("g5_table", []):
        print(f"| {str(r.get('tieu_chi',''))[:45]:<45} | {str(r.get('diem_toi_da',''))[:6]:>6} | {str(r.get('diem_cham',''))[:6]:>6} | {str(r.get('ly_do',''))[:43]:<43} |")
    print(sep3)
    print(f"  ► TỔNG 5G: {data.get('g5_total', 0)}/100")

    # ── Decision ──────────────────────────────────────────────────────────────
    decision = data.get('decision', '')
    print(f"\n{'═'*68}")
    print(f"  ⚡ QUYẾT ĐỊNH CUỐI: {decision}")
    print(f"{'═'*68}")
