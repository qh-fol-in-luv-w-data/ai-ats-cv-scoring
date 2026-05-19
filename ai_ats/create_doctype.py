import frappe

def run():
    if not frappe.db.exists("DocType", "AI Job Match Result"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "AI Job Match Result",
            "module": "AI ATS",
            "custom": 0,
            "is_submittable": 0,
            "fields": [
                {"fieldname": "candidate_name", "fieldtype": "Data", "label": "Tên Ứng Viên", "in_list_view": 1},
                {"fieldname": "best_match_job", "fieldtype": "Data", "label": "Job Phù Hợp Nhất", "in_list_view": 1},
                {"fieldname": "best_match_score", "fieldtype": "Float", "label": "Điểm Cao Nhất", "in_list_view": 1},
                {"fieldname": "match_details", "fieldtype": "Code", "options": "JSON", "label": "Chi Tiết (JSON)"}
            ],
            "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
            "autoname": "format:MATCH-{YYYY}-{MM}-{####}"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("DocType AI Job Match Result created!")
    else:
        print("DocType already exists.")
