import frappe

def generate_admin_token():
    user = frappe.get_doc("User", "Administrator")
    api_secret = frappe.generate_hash(length=15)
    
    # Frappe expects api_key to be set directly
    if not user.api_key:
        user.api_key = frappe.generate_hash(length=15)
        
    user.api_secret = api_secret
    user.save(ignore_permissions=True)
    frappe.db.commit()
    
    print("====================================")
    print(f"API_KEY: {user.api_key}")
    print(f"API_SECRET: {api_secret}")
    print(f"FULL_TOKEN: {user.api_key}:{api_secret}")
    print("====================================")
