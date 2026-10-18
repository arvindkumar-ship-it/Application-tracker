import json
from bs4 import BeautifulSoup


def parse_jsonld(html):
    def walk(node):
        if isinstance(node, list):
            for item in node: yield from walk(item)
        elif isinstance(node, dict):
            types = node.get('@type', [])
            if types == 'JobPosting' or isinstance(types,list) and 'JobPosting' in types: yield node
            yield from walk(node.get('@graph', []))
    for script in BeautifulSoup(html,'html.parser').find_all('script',type='application/ld+json'):
        try:
            for job in walk(json.loads(script.string or script.get_text())):
                if all(job.get(key) for key in ['title','hiringOrganization','description']): return job
        except (ValueError,TypeError): continue
    return None
