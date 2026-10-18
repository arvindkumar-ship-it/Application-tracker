import re
from datetime import date
from dateutil.parser import parse


def parse_date(text):
    if not text or not re.search(r"\b(?:19|20)\d{2}\b", text): return None
    if re.search(r"within|today|tomorrow|next\s|days?\s+(?:from|after)", text, re.I): return None
    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", text, flags=re.I)
    try:
        if not re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b|\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", cleaned, re.I): return None
        # A day must be explicitly present; dateutil must not invent today's day/month.
        tokens = re.findall(r"\d+", cleaned)
        if len(tokens) < 2: return None
        return parse(cleaned, fuzzy=True, dayfirst=not bool(re.search(r"\d{4}[-/]", cleaned)), default=__import__('datetime').datetime(2000,1,1)).date()
    except (ValueError, OverflowError): return None


def compensation(text):
    s = (text or "").lower().replace(",", "")
    result = {"comp_min": None, "comp_max": None, "comp_currency": None, "comp_period": "unspecified"}
    if "unpaid" in s: return {**result, "comp_min": 0}
    amounts = re.findall(r"\d+(?:\.\d+)?", s)
    if not amounts or any(x in s for x in ['performance based','negotiable']): return result
    multiplier = 100000 if re.search(r"\blpa\b|lakh", s) else 1000 if re.search(r"\d\s*k\b", s) else 1
    result.update(comp_min=float(amounts[0])*multiplier, comp_max=float(amounts[1])*multiplier if len(amounts)>1 else None)
    result['comp_currency'] = 'INR' if '₹' in s or 'inr' in s or 'lpa' in s else 'USD' if '$' in s or 'usd' in s else 'EUR' if '€' in s else None
    result['comp_period'] = 'year' if re.search(r'lpa|year|annual|annum',s) else 'month' if re.search(r'month|/mo\b',s) else 'hour' if re.search(r'hour|/hr\b',s) else 'one_time' if 'one-time' in s else 'unspecified'
    return result


def experience(text):
    s = (text or '').lower()
    nums = re.findall(r'\d+(?:\.\d+)?', s)
    return {'experience_min_years':0 if 'fresher' in s else float(nums[0]) if nums and re.search(r'year|yr',s) else None,'experience_max_years':float(nums[1]) if len(nums)>1 and re.search(r'year|yr',s) else None}
