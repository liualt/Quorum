from pathlib import Path
import json
import re
from zipfile import ZipFile
from lxml import etree

root = Path(__file__).resolve().parents[2]
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
md = (root / 'PRD.md').read_text(encoding='utf-8')
readme = (root / 'README.md').read_text(encoding='utf-8')
assert len(re.findall(r'^## \d+\.', md, re.M)) == 19
assert all(not line.endswith(' ') for line in md.splitlines())
assert not re.search(r'TODO|TBD|turn\d+(?:view|search)|\uE200|\uE201', md)
assert len(readme.split()) < 180
assert (root / 'PRD.docx').is_file()
with ZipFile(root / 'PRD.docx') as z:
    assert z.testzip() is None
    xml = etree.fromstring(z.read('word/document.xml'))
    w = '{' + ns['w'] + '}'
    sec = xml.find('.//w:sectPr', ns)
    pg = sec.find('w:pgSz', ns)
    mar = sec.find('w:pgMar', ns)
    available = int(pg.get(w+'w')) - int(mar.get(w+'left')) - int(mar.get(w+'right'))
    tables = xml.findall('.//w:tbl', ns)
    for table in tables:
        grid = table.findall('w:tblGrid/w:gridCol', ns)
        assert sum(int(c.get(w+'w')) for c in grid) <= available + 2
        assert table.find('w:tr/w:trPr/w:tblHeader', ns) is not None
        assert table.find('w:tblPr/w:tblBorders', ns) is not None
    headings = xml.xpath('//w:p[w:pPr/w:pStyle[@w:val="Heading1"]]', namespaces=ns)
    assert len(headings) == 19
    assert not xml.findall('.//w:altChunk', ns)
report_path = Path(__file__).parent / 'verification.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
report.update({'structural_checks': 'passed', 'visual_review': 'unavailable: bundled LibreOffice absent; canonical renderer attempted', 'readme_words':len(readme.split()), 'sections':19})
report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
