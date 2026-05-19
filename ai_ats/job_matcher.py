import frappe
import json
from ai_ats.api import _get_gpt, _pdf_bytes, _docx_bytes, _ensure_session, _logger
from ai_ats.utils.activity_logger import Timer

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
    Logging: ATS Session + ATS Action Log + ATS AI Call Log
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

    # ── Session ───────────────────────────────────────────────────────────────
    session_id   = (frappe.get_request_header("X-App-Session-Id") or "")
    session_name = _ensure_session(session_id)

    # ── Action Log: start ─────────────────────────────────────────────────────
    action_name = _logger.start_action(
        session_name,
        action_type="match_candidate_jobs",
        input_summary=f"cv={'file' if frappe.request and frappe.request.files else 'text'}, jobs={len(jobs_list)}",
        input_detail={"num_jobs": len(jobs_list), "job_ids": [j.get("id") for j in jobs_list]},
    )

    try:
        # Format danh sách JD
        jobs_context = ""
        for j in jobs_list:
            jobs_context += f"- JOB ID: {j.get('id')}\n  TITLE: {j.get('title')}\n  JD_TEXT: {str(j.get('jd_text', ''))[:1500]}\n\n"

        system_prompt = """Bạn là Chuyên gia Tuyển dụng AI (AI ATS Matcher) tại CT Group.
Nhiệm vụ: Phân tích CV của ứng viên và chấm điểm độ phù hợp với từng công việc trong danh sách được cung cấp.

- VỀ CÁCH CHẤM ĐIỂM (score): Chấm điểm linh hoạt và khách quan, tập trung vào kỹ năng cốt lõi (Core Skills) và tiềm năng.
- VỀ CÁCH GIẢI THÍCH (reason): Nêu rõ điểm mạnh nổi bật, các kỹ năng đã match tốt, và chỉ ra những điểm còn thiếu.

CHỈ được phép trả về kết quả dưới định dạng JSON theo đúng schema sau:
{
  "matches": [
    {
      "job_id": <Mã ID của job>,
      "job_name": "<Tên vị trí>",
      "score": <Số nguyên từ 0 đến 100>,
      "reason": "<Phân tích cặn kẽ>",
      "keywords_found": ["<từ khóa 1>", "<từ khóa 2>"],
      "keywords_missing": ["<từ khóa thiếu 1>", "<từ khóa thiếu 2>"]
    }
  ]
}"""

        user_msg = f"### CV ỨNG VIÊN:\n{cv_text[:10000]}\n\n### DANH SÁCH CÁC CÔNG VIỆC CẦN MATCH:\n{jobs_context}"

        # GPT Call
        with Timer() as t:
            resp = _get_gpt().chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=3000,
            )
        data = json.loads(resp.choices[0].message.content)
        usage = resp.usage
        prompt_tokens     = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        # ── AI Call Log ───────────────────────────────────────────────────────
        _logger.log_ai_call(
            session_name, action_name,
            call_type="match_candidate_jobs", ai_model="gpt-4o",
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            duration_seconds=t.elapsed, status="success",
        )

        # Lưu DocType
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

        # ── Action Log: finish ────────────────────────────────────────────────
        _logger.finish_action(
            action_name, status="success",
            output_summary=f"matched {len(data.get('matches',[]))} jobs, best={best_job}({best_score}%)",
            ai_model="gpt-4o",
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            duration_seconds=t.elapsed,
        )

        return data

    except Exception as e:
        try: frappe.db.rollback()
        except: pass
        _logger.finish_action(action_name, status="failed", error_message=str(e)[:500])
        frappe.log_error(f"match_candidate_jobs error: {e}")
        frappe.throw(str(e))
