import frappe
import json
from ai_ats.api import _gpt, _SYSTEM, _read_cached, _AI_SCORING_PDF, _G5_SCORING_DOCX, _SWAT_PRD_DOCX, _docx_bytes

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
[Hướng dẫn chấm AI]: {ai_guide[:3000]}
[Hướng dẫn chấm SWAT]: {swat_prd[:3000]}
[Hướng dẫn chấm 5G]: {g5_guide[:3000]}
"""

    print("Sending to OpenAI...")
    resp = _gpt.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":_SYSTEM},{"role":"user","content":user_msg}],
        response_format={"type":"json_object"},
        temperature=0.2
    )

    data = json.loads(resp.choices[0].message.content)

    print("\n--- KẾT QUẢ CHẤM ĐIỂM AI TEST ---")
    for row in data.get("ai_test_table", []):
        print(f"Câu {row.get('cau')}: {row.get('diem_cham')}/{row.get('diem_toi_da')} - Lý do: {row.get('ly_do')}")
    print(f"Tổng: {data.get('ai_test_total')} -> {data.get('ai_test_label')}")

    print("\n--- KẾT QUẢ CHẤM ĐIỂM SWAT ---")
    for row in data.get("swat_table", []):
        print(f"[{row.get('tru_cot')}] Thô: {row.get('diem_tho')} -> {row.get('diem_trong_so')} điểm. Cở sở: {row.get('co_so')}")
    print(f"Tổng SWAT: {data.get('swat_total')} -> {data.get('swat_label')}")

    print(f"\n--- KẾT QUẢ 5G TEST ---")
    print(f"Tổng điểm 5G: {data.get('g5_total')}")
