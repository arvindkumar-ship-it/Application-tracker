from app.models.base import *

jd_analysis = table("jd_analysis", ref("job_id", "job.id", unique=True), field("must_have_keywords", JSONB, required=True, default="[]"), field("nice_to_have_keywords", JSONB, required=True, default="[]"), *lists("responsibilities_themes ats_exact_phrases"), *texts("seniority_signal domain analysis_model"))
tailored_resume = table("tailored_resume", ref("job_id", "job.id"), ref("base_variant_id", "resume_variant.id"), field("version_number", Integer, required=True), *texts("selected_summary_text pdf_path docx_path notes"), *objects("sections_json coverage_json validation_report_json"), field("is_final", Boolean, required=True, default="false"), constraints=(UniqueConstraint("job_id", "version_number"), CheckConstraint("version_number > 0")))
