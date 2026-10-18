from app.models.base import *

intake = table("intake", choice("input_type", "url screenshots text pdf"), *texts("source_url raw_text status_detail llm_model_used error_trace"), field("original_files", JSONB, required=True, default="[]"), choice("status", "queued processing needs_manual_input needs_review approved rejected failed", default="queued"), choice("fetch_method", "jsonld http playwright vision pasted pdf_text none", default="none"), *objects("extraction_json verification_report"), ref("duplicate_of_job_id", "job.id", required=False), field("processing_ms", Integer))
