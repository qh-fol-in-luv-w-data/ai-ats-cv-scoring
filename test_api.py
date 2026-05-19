import requests

url = "http://127.0.0.1:8000/api/method/ai_ats.api.generate_candidate_report"
data = {
    "jd_text": "Yêu cầu vị trí Senior Fullstack Developer thuộc Khối DAIT...",
    "ai_test_url": "http://10.6.10.12:8069/survey/print/c5094f3b-a3f5-4626-96f1-333b1f4fbc8e",
    "g5_test_url": "http://10.6.10.12:8069/survey/print/df4405cb-3e24-40c9-874d-51c0a39a53ea",
    "eq_test_url": "https://jobtest.vn/kq-bai-test-abc",
    "survey_url": "http://10.6.10.12:8069/survey/result/819/53d69ba4-ead8-4a0d-b831-72bb8e1b0567",
    "api_use_cache": "1"
}

r = requests.post(url, data=data)
print(r.status_code)
print(r.text)
