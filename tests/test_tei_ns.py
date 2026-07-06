"""TEI namespace and tei_bridge tests."""

import lxml.etree as et
import pytest

from sanmiao import propose_dates, dates_xml_to_df, tag_date_elements, index_date_nodes
from sanmiao.tei_bridge import (
    extract_date_fragment,
    resolve_date_element,
    row_to_tei_attrs,
    propose_dates_batch,
    tag_dates_batch,
    resolve_dates_batch,
)
from sanmiao.ns import is_tag, xpath_dates, detect_wrapper_namespace

TEI = "http://www.tei-c.org/ns/1.0"


def test_dates_xml_to_df_tei_date_unprefixed_children():
    """TEI <date> with unprefixed sanmiao children (LJB convention)."""
    xml = f"""<root xmlns="{TEI}">
      <date index="0"><era>太和</era><year>元年</year></date>
    </root>"""
    root = et.fromstring(xml.encode())
    df = dates_xml_to_df(root, attributes=False)
    assert len(df) == 1
    assert df.iloc[0]["era_str"] == "太和"
    assert df.iloc[0]["year_str"] == "元年"


def test_dates_xml_to_df_namespaced_date_and_children():
    """All elements in TEI namespace."""
    xml = f"""<root xmlns="{TEI}">
      <date index="0"><era>建安</era><year>十八年</year></date>
    </root>"""
    root = et.fromstring(xml.encode())
    df = dates_xml_to_df(root, attributes=False)
    assert df.iloc[0]["era_str"] == "建安"


def test_tag_date_elements_inside_tei_paragraph():
    """New <date> wrappers inherit TEI namespace; children stay unprefixed."""
    xml = f'<p xmlns="{TEI}">魏太和元年</p>'
    root = et.fromstring(xml.encode())
    out = tag_date_elements(et.tostring(root, encoding="unicode"))
    tagged = et.fromstring(out.encode())
    dates = xpath_dates(tagged)
    assert len(dates) >= 1
    d = dates[0]
    assert is_tag(d, "date")
    assert d.tag == f"{{{TEI}}}date"
    child_local = [c.tag.split("}")[-1] if "}" in c.tag else c.tag for c in d]
    assert "dyn" in child_local or "era" in child_local


def test_propose_dates_plain_text():
    proposals = propose_dates("魏太和元年", civ=["c"], sequential=True, fuzzy=False)
    assert len(proposals) >= 1
    assert proposals[0]["status"] in ("unique", "ambiguous", "unresolved")
    assert "date_string" in proposals[0]


def test_propose_dates_fuzzy_preserves_original_script():
    """Fuzzy tags on simplified forms but returns the user's original characters."""
    proposals = propose_dates("義熙八年", civ=["c"], sequential=True, fuzzy=True)
    assert len(proposals) >= 1
    assert proposals[0]["date_string"] == "義熙八年"
    inner = proposals[0].get("parseInnerXml") or ""
    assert "義熙" in inner
    assert "义熙" not in inner


def test_propose_dates_batch_carries_sequential_context():
    """Implied era from chunk 1 resolves 其三年 in chunk 2 (bare relative date)."""
    batch = propose_dates_batch(["義熙元年", "其三年"], civ=["c"], sequential=True, fuzzy=False)
    alone = propose_dates("其三年", civ=["c"], sequential=True, fuzzy=False)
    assert batch[1][0]["status"] == "unique"
    assert "義熙三年" in batch[1][0]["candidates"][0]["displayLine"]
    assert alone[0]["candidates"][0]["displayLine"] == "Insufficient data"


def test_extract_and_resolve_date_fragment():
    frag_xml = "<date index=\"0\"><era>太和</era><year>元年</year></date>"
    proposals = resolve_date_element(frag_xml, civ=["c"], sequential=True, fuzzy=False)
    assert isinstance(proposals, list)


def test_detect_wrapper_namespace_from_tei():
    root = et.fromstring(f'<TEI xmlns="{TEI}"><text><body><p>x</p></body></text></TEI>'.encode())
    assert detect_wrapper_namespace(root) == TEI


def test_tag_dates_batch_parse_only():
    batch = tag_dates_batch(["魏太和元年"], civ=["c"], fuzzy=False)
    assert len(batch) == 1
    assert len(batch[0]) >= 1
    assert batch[0][0]["status"] == "tagged"
    assert batch[0][0]["candidates"] == []
    assert "parseInnerXml" in batch[0][0]


def test_resolve_dates_batch_sequential_context():
    """Resolve in document order carries implied state across dates."""
    first = "<date index=\"0\"><era>義熙</era><year>元年</year></date>"
    second = "<date index=\"0\"><year>三年</year></date>"
    results = resolve_dates_batch([first, second], civ=["c"], sequential=True, fuzzy=False)
    assert results[0] is not None
    assert results[1] is not None
    assert results[1]["status"] == "unique"
    assert "義熙三年" in results[1]["candidates"][0]["displayLine"]
