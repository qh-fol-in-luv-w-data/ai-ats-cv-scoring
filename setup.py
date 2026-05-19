from setuptools import setup, find_packages

setup(
    name="ai_ats",
    version="0.0.1",
    description="AI Candidate Persona Report System",
    author="CT Group",
    author_email="dev@ctgroup.vn",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["frappe"],
)
