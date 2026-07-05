"""TEI namespace and tei_bridge tests."""

import lxml.etree as et
import pytest

from sanmiao import propose_dates, dates_xml_to_df, tag_date_elements, index_date_nodes
from sanmiao.tei_bridge import extract_date_fragment, resolve_date_element, row_to_tei_attrs
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


def test_extract_and_resolve_date_fragment():
    frag_xml = "<date index=\"0\"><era>太和</era><year>元年</year></date>"
    proposals = resolve_date_element(frag_xml, civ=["c"], sequential=True, fuzzy=False)
    assert isinstance(proposals, list)


def test_detect_wrapper_namespace_from_tei():
    root = et.fromstring(f'<TEI xmlns="{TEI}"><text><body><p>x</p></body></text></TEI>'.encode())
    assert detect_wrapper_namespace(root) == TEI
