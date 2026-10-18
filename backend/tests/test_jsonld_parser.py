import unittest
import json
from app.services.jsonld_parser import parse_jsonld


class JsonLdChecks(unittest.TestCase):
    def test_object_array_graph_and_bad_json(self):
        job={'@type':'JobPosting','title':'Fixture role','hiringOrganization':{'name':'Fixture Co'},'description':'Required: Python.'}
        for node in [job,[{'@type':'WebPage'},job],{'@graph':[job]}]:
            with self.subTest(node=node):self.assertEqual(parse_jsonld('<script type="application/ld+json">'+json.dumps(node)+'</script>')['title'],'Fixture role')
        self.assertIsNone(parse_jsonld('<script type="application/ld+json">invalid</script>'))
