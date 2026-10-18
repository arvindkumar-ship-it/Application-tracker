import re
from bs4 import BeautifulSoup


def normalize_whitespace(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select('script,style,nav,footer,header,noscript,[role="navigation"],.cookie-banner,#cookie-banner'):
        node.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
