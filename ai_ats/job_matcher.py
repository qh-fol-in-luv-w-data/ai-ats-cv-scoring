import frappe
import json
from ai_ats.api import _gpt, _pdf_bytes, _docx_bytes

@frappe.whitelist()
def match_candidate_jobs(jobs_json: str = None, cv_text: str = "", **kwargs):
    """
    API Match Candidate CV with Multiple Jobs
    INPUT (Form Data):
        cv_file: Upload file CV (pdf, docx)
        cv_text: Text CV (nếu không có file)
        jobs_json: Chuỗi JSON array chứa danh sách jobs (id, title, jd_text)
    OUTPUT:
        JSON chứa danh sách kết quả matching (%) cho từng job
    """
    if jobs_json is None:
        jobs_json = frappe.form_dict.get("jobs_json")
        
    if not jobs_json:
        frappe.throw("Thiếu tham số jobs_json.", frappe.ValidationError)

    if frappe.request and frappe.request.files:
        f = frappe.request.files.get("cv_file")
        if f:
            raw = f.stream.read()
            cv_text = _pdf_bytes(raw) if (f.filename or "").lower().endswith(".pdf") else _docx_bytes(raw)

    if not cv_text:
        cv_text = frappe.form_dict.get("cv_text")
        
    if not cv_text:
        frappe.throw("Vui lòng cung cấp CV (cv_file hoặc cv_text).", frappe.ValidationError)

    try:
        jobs_list = json.loads(jobs_json)
    except Exception:
        frappe.throw("Tham số jobs_json không hợp lệ (phải là chuẩn JSON).", frappe.ValidationError)

    # Format danh sách JD
    jobs_context = ""
    for j in jobs_list:
        jobs_context += f"- JOB ID: {j.get('id')}\n  TITLE: {j.get('title')}\n  JD_TEXT: {str(j.get('jd_text', ''))[:1500]}\n\n"

    system_prompt = """Bạn là Chuyên gia Tuyển dụng AI (AI ATS Matcher) tại CT Group.
Nhiệm vụ: Phân tích CV của ứng viên và chấm điểm độ phù hợp với từng công việc trong danh sách được cung cấp.

- VỀ CÁCH CHẤM ĐIỂM (score): Chấm điểm linh hoạt và khách quan, tập trung vào kỹ năng cốt lõi (Core Skills) và tiềm năng. Nếu CV thiếu một chút số năm kinh nghiệm nhưng có kỹ năng nền tảng và dự án thực tế bù đắp, vẫn nên cho điểm tốt (60-75). Cho điểm cao (80-100) nếu ứng viên có các dự án, kỹ năng khớp với keyword chính của JD. Không trừ điểm quá gắt nếu thiếu các yêu cầu phụ.
- VỀ CÁCH GIẢI THÍCH (reason): Nêu rõ điểm mạnh nổi bật, các kỹ năng đã match tốt, và chỉ ra những điểm còn thiếu một cách mang tính xây dựng.

CHỈ được phép trả về kết quả dưới định dạng JSON theo đúng schema sau:
{
  "matches": [
    {
      "job_id": <Mã ID của job>,
      "job_name": "<Tên vị trí>",
      "score": <Số nguyên từ 0 đến 100>,
      "reason": "<Phân tích cặn kẽ: Điểm mạnh, điểm yếu chí mạng, lý do bị trừ điểm hoặc được cộng điểm so với JD>",
      "keywords_found": ["<từ khóa 1>", "<từ khóa 2>"],
      "keywords_missing": ["<từ khóa thiếu 1>", "<từ khóa thiếu 2>"]
    }
  ]
}"""

    user_msg = f"### CV ỨNG VIÊN:\n{cv_text[:10000]}\n\n### DANH SÁCH CÁC CÔNG VIỆC CẦN MATCH:\n{jobs_context}"

    resp = _gpt.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_msg}],
        response_format={"type":"json_object"},
        temperature=0.2,
        max_tokens=3000,
    )
    
    data = json.loads(resp.choices[0].message.content)

    # Save to DocType
    try:
        matches = data.get("matches", [])
        best_score = 0
        best_job = ""
        for m in matches:
            if m.get("score", 0) > best_score:
                best_score = m.get("score", 0)
                best_job = m.get("job_name", "")
        
        cv_name = "Ứng viên ẩn danh"
        if frappe.request and frappe.request.files:
            file_obj = frappe.request.files.get("cv_file")
            if file_obj and file_obj.filename:
                cv_name = f"CV: {file_obj.filename}"

        doc = frappe.get_doc({
            "doctype": "AI Job Match Result",
            "candidate_name": cv_name,
            "best_match_job": best_job,
            "best_match_score": best_score,
            "match_details": json.dumps(data, ensure_ascii=False, indent=2)
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error("Lỗi khi lưu DocType AI Job Match Result", str(e))
    
    return data
