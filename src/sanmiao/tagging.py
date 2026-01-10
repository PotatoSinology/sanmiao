import re
import lxml.etree as et
from .loaders import (
    load_csv, load_tag_tables
)
from .config import get_cal_streams_from_civ
from .xml_utils import (
    strip_ws_in_text_nodes, clean_attributes, replace_in_text_and_tail
)

SKIP = {"date","year","month","day","gz","sexYear","era","ruler","dyn","suffix","int","lp",
        "nmdgz","lp_filler","filler","season","meta","pb","text","body"}  # adjust tags you want to skip

SKIP_ALL = {"date","year","month","day","gz","sexYear","era","ruler","dyn","suffix",
            "int","lp","nmdgz","lp_filler","filler","season"}

SKIP_TEXT_ONLY = {"pb", "meta"}

YEAR_RE   = re.compile(r"((?:[一二三四五六七八九十]+|元)[年載])")
# "廿<date><year>" fix disappears because we won't create that broken boundary in text mode.

# Months: order matters (more specific first)
LEAPMONTH_RE1 = re.compile(r"閏月")
LEAPMONTH_RE2 = re.compile(r"閏((?:十有[一二]|正)月)")
LEAPMONTH_RE3 = re.compile(r"閏((?:[一二三四五六七八九十]+|正)月)")
MONTH_RE1     = re.compile(r"((?:十有[一二]|正)月)")
MONTH_RE2     = re.compile(r"((?:[一二三四五六七八九十]+|正)月)")

DAY_RE    = re.compile(r"(([廿卅卌卄丗一二三四五六七八九十]+)日)")
GZ_RE     = re.compile(r"([甲乙丙景丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")
SEXYEAR_RE = re.compile(r"([甲乙丙景丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])(年|歲)")
SEASON_RE = re.compile(r"([春秋冬夏])")

LP_RE = re.compile(r"([朔晦])")
SEX_YEAR_PREFIX_RE = re.compile(r"(歲[次在])\s*$")
PUNCT_RE = re.compile(r"^[，,、\s]*")

ERA_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世)")
DYNASTY_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世)")
RULER_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世|即位)")


def replace_in_text_and_tail(
    xml_root,
    pattern: re.Pattern,
    make_element,
    skip_text_tags=frozenset(),
    skip_all_tags=frozenset(),
):
    """
    Replace pattern matches in text and tail attributes of XML elements.
    Uses iterative approach to handle newly inserted elements properly.
    
    Key point: Even if an element's tag is in skip_all_tags (like <date>),
    we still need to process its TAIL, because that tail might contain
    more patterns that need to be matched.
    """
    # Process elements depth-first, but need to re-scan for new elements
    # Keep processing until no more matches are found
    max_passes = 50  # Safety limit to prevent infinite loops
    changed = True
    
    for pass_num in range(max_passes):
        if not changed:
            break
        changed = False
        
        # Collect all elements to process in this pass
        # Use list() to create snapshot, but we'll re-scan if changes occur
        elements_to_check = []
        for el in xml_root.iter():
            # Always include elements to process their tail
            # We'll skip processing their text/children if tag is in skip_all_tags
            elements_to_check.append(el)
        
        for el in elements_to_check:
            # Skip if element was removed
            parent = el.getparent()
            if parent is None and el is not xml_root:
                continue
            
            # Decide which slots to process
            # CRITICAL: Even if element is in skip_all_tags, we still process its tail!
            # The tail of a <date> element might contain more patterns.
            if el.tag in skip_all_tags:
                # Skip processing text (children) of these elements, but process tail
                slots = ("tail",)
            elif el.tag in skip_text_tags:
                slots = ("tail",)
            else:
                slots = ("text", "tail")

            for slot in slots:
                s = getattr(el, slot)
                if not s or not pattern.search(s):
                    continue

                matches = list(pattern.finditer(s))
                if not matches:
                    continue

                chunks = []
                last = 0
                for m in matches:
                    chunks.append(s[last:m.start()])
                    chunks.append(m)
                    last = m.end()
                chunks.append(s[last:])

                if slot == "text":
                    el.text = chunks[0]
                    pos = 0
                    for i in range(1, len(chunks), 2):
                        new_el = make_element(chunks[i])
                        new_el.tail = chunks[i + 1]
                        el.insert(pos, new_el)
                        pos += 1
                    changed = True
                else:  # tail
                    parent = el.getparent()
                    if parent is None:
                        continue
                    idx = parent.index(el)
                    el.tail = chunks[0]
                    pos = idx + 1
                    for i in range(1, len(chunks), 2):
                        new_el = make_element(chunks[i])
                        new_el.tail = chunks[i + 1]
                        parent.insert(pos, new_el)
                        pos += 1
                    changed = True
                    
def make_simple_date(tagname, group=1):
    """
    Create a function that generates XML date elements with specified tag.

    :param tagname: str, XML tag name for the date element
    :param group: int, regex group number to extract text from
    :return: function that creates XML date elements
    """
    def _mk(m):
        d = et.Element("date")
        c = et.SubElement(d, tagname)
        c.text = m.group(group)
        return d
    return _mk

def make_sexyear(m):
    """
    Create a date element with sexYear structure: <date><sexYear>甲子<filler>年</filler></sexYear></date>
    """
    d = et.Element("date")
    sy = et.SubElement(d, "sexYear")
    sy.text = m.group(1)  # sexagenary part (甲子 etc.)
    filler = et.SubElement(sy, "filler")
    filler.text = m.group(2)  # suffix (年 or 歲)
    return d

def make_leap_month_exact_monthtext(month_text: str):
    """
    Create XML element for leap month with specific month text.

    :param month_text: str, text for the month element
    :return: et.Element, XML date element for leap month
    """
    d = et.Element("date")
    i = et.SubElement(d, "int"); i.text = "閏"
    m = et.SubElement(d, "month"); m.text = month_text
    return d

def make_leapmonth_from_group1(m):
    """
    Create leap month element from regex match group 1.

    :param m: regex match object
    :return: et.Element, XML date element for leap month
    """
    return make_leap_month_exact_monthtext(m.group(1))

def make_leapmonth_yue(m):
    # "閏月" -> <date><int>閏</int><month>月</month></date>
    return make_leap_month_exact_monthtext("月")

def tag_basic_tokens(xml_root):
    """
    Tag basic date tokens (year, month, day, etc.) in XML tree.

    :param xml_root: et.Element, root of XML tree to process
    :return: et.Element, modified XML root with tagged date elements
    """
    # year
    replace_in_text_and_tail(xml_root, YEAR_RE, make_simple_date("year"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # leap month variants (specific -> general)
    replace_in_text_and_tail(xml_root, LEAPMONTH_RE1, make_leapmonth_yue, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, LEAPMONTH_RE2, make_leapmonth_from_group1, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, LEAPMONTH_RE3, make_leapmonth_from_group1, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # month (specific -> general)
    replace_in_text_and_tail(xml_root, MONTH_RE1, make_simple_date("month"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, MONTH_RE2, make_simple_date("month"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # sexagenary year (before gz to avoid conflicts)
    replace_in_text_and_tail(xml_root, SEXYEAR_RE, make_sexyear, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # day, gz, season
    replace_in_text_and_tail(xml_root, DAY_RE, make_simple_date("day"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, GZ_RE, make_simple_date("gz"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, SEASON_RE, make_simple_date("season"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    return xml_root


def promote_gz_to_sexyear(xml_root):
    """
    Promote sexagenary day (gz) elements to sexagenary year (sexYear) when preceded by year markers.

    :param xml_root: et.Element, root of XML tree to process
    :return: et.Element, modified XML root
    """
    for d in xml_root.xpath(".//date[gz]"):
        prev = d.getprevious()
        if prev is None:
            s = d.getparent().text or ""
            loc = ("parent", d.getparent())
        else:
            s = prev.tail or ""
            loc = ("tail", prev)

        m = SEX_YEAR_PREFIX_RE.search(s)
        if not m:
            continue

        # Remove prefix text
        new_s = s[:m.start()]
        if loc[0] == "parent":
            loc[1].text = new_s
        else:
            loc[1].tail = new_s

        gz_text = d.findtext("gz")

        # Rewrite date contents
        for ch in list(d):
            d.remove(ch)
        f = et.SubElement(d, "filler")
        f.text = m.group(1)
        sy = et.SubElement(d, "sexYear")
        sy.text = gz_text

    return xml_root


def promote_nmdgz(xml_root):
    """
    Promote sexagenary day (gz) elements to numbered month day gz (nmdgz) when followed by day elements.

    :param xml_root: et.Element, root of XML tree to process
    :return: et.Element, modified XML root
    """
    for gz_date in list(xml_root.xpath(".//date[gz]")):
        parent = gz_date.getparent()
        gz_text = gz_date.findtext("gz")
        if not gz_text:
            continue

        # ---------- CASE 1 ----------
        # <date><gz>..</gz></date>朔，<date><day>..</day></date>
        tail = gz_date.tail or ""
        if tail.startswith("朔"):
            rest = PUNCT_RE.sub("", tail[1:])
            next_el = gz_date.getnext()

            if next_el is not None and next_el.tag == "date" and next_el.find("day") is not None:
                # Clean tail of gz_date
                gz_date.tail = rest

                # Add nmdgz + lp_filler to day date
                nmdgz = et.SubElement(next_el, "nmdgz")
                nmdgz.text = gz_text
                lp = et.SubElement(next_el, "lp_filler")
                lp.text = "朔"

                # Remove gz_date but preserve its tail
                prev = gz_date.getprevious()
                if prev is None:
                    parent.text = (parent.text or "") + (gz_date.tail or "")
                else:
                    prev.tail = (prev.tail or "") + (gz_date.tail or "")
                parent.remove(gz_date)
                continue

        # ---------- CASE 2 ----------
        # 朔<date><gz>..</gz></date>，<date><day>..</day></date>
        prev = gz_date.getprevious()
        if prev is None:
            s = parent.text or ""
            loc = ("parent", parent)
        else:
            s = prev.tail or ""
            loc = ("tail", prev)

        if s.endswith("朔"):
            next_el = gz_date.getnext()
            if next_el is not None and next_el.tag == "date" and next_el.find("day") is not None:
                # Remove trailing 朔
                new_s = s[:-1]
                if loc[0] == "parent":
                    loc[1].text = new_s
                else:
                    loc[1].tail = new_s

                # Move gz into day date
                nmdgz = et.SubElement(next_el, "nmdgz")
                nmdgz.text = gz_text
                lp = et.SubElement(next_el, "lp_filler")
                lp.text = "朔"

                # Remove gz_date, preserve its tail
                gz_tail = gz_date.tail or ""
                prev2 = gz_date.getprevious()
                if prev2 is None:
                    parent.text = (parent.text or "") + gz_tail
                else:
                    prev2.tail = (prev2.tail or "") + gz_tail
                parent.remove(gz_date)

    return xml_root


def attach_suffixes(xml_root: et.Element) -> et.Element:
    """
    Convert:
      <date><era>太和</era></date>初
    into:
      <date><era>太和</era><suffix>初</suffix></date>

    Same for <ruler> and <dyn>.
    """
    # Snapshot because we mutate tails
    for d in list(xml_root.xpath(".//date")):
        tail = d.tail or ""
        if not tail:
            continue

        # Decide which suffix regex applies based on content
        if d.find("ruler") is not None:
            m = RULER_SUFFIX_RE.match(tail)
        elif d.find("era") is not None:
            m = ERA_SUFFIX_RE.match(tail)
        elif d.find("dyn") is not None:
            m = DYNASTY_SUFFIX_RE.match(tail)
        else:
            continue

        if not m:
            continue

        suf = m.group(1)

        # Add/append suffix element
        s_el = et.SubElement(d, "suffix")
        s_el.text = suf

        # Remove suffix from tail; keep remainder intact
        d.tail = tail[m.end():]

    return xml_root


def tag_date_elements(text, civ=None):
    """
    Tag and clean Chinese string containing date with relevant elements for extraction. Each date element remains
    separated, awaiting "consolidation."
    :param text: str
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return: str (XML)
    """
    # Test if input is XML, if not, wrap in <root> tags to make it XML
    try:
        xml_root = et.fromstring(text.encode("utf-8"))
    except et.ParseError:
        try:
            xml_root = et.fromstring('<root>' + text + '</root>')
        except et.ParseError:
            # If both parsing attempts fail, create a minimal root element
            xml_root = et.Element("root")
            xml_root.text = text

    # Ensure xml_root is not None
    if xml_root is None:
        xml_root = et.Element("root")
        xml_root.text = text if text else ""
    
    # Defaults
    if civ is None:
        civ = ['c', 'j', 'k']

    # Retrieve tag tables
    era_tag_df = load_csv('era_table.csv')
    # Filter era_tag_df by cal_stream
    cal_streams = get_cal_streams_from_civ(civ)
    if cal_streams is not None:
        era_tag_df = era_tag_df[era_tag_df['cal_stream'].notna()]
        # Convert cal_stream to float for comparison to avoid int/float mismatch
        era_tag_df = era_tag_df[era_tag_df['cal_stream'].astype(float).isin(cal_streams)]
    dyn_tag_df, ruler_tag_df = load_tag_tables(civ=civ)
    # Reduce to lists
    era_tag_list = era_tag_df['era_name'].unique()
    dyn_tag_list = dyn_tag_df['string'].unique()
    ruler_tag_list = ruler_tag_df['string'].unique()
    # Normal dates #####################################################################################################
    # Year, month, day, gz, season, lp
    xml_root = tag_basic_tokens(xml_root)
    # Lunar phases
    replace_in_text_and_tail(xml_root, LP_RE, make_simple_date("lp"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    # Sexagenary year
    xml_root = promote_gz_to_sexyear(xml_root)
    # NM date
    xml_root = promote_nmdgz(xml_root)
    # Era names ########################################################################################################
    # Reduce list
    era_tag_list = [s for s in era_tag_list if isinstance(s, str) and s]
    if era_tag_list:
        era_tag_list.sort(key=len, reverse=True)
        era_pattern = re.compile("(" + "|".join(map(re.escape, era_tag_list)) + ")")

        def make_era(match):
            d = et.Element("date")
            e = et.SubElement(d, "era")
            e.text = match.group(1)
            return d

        replace_in_text_and_tail(xml_root, era_pattern, make_era, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # Ruler Names ######################################################################################################
    # Reduce list
    ruler_tag_list = [s for s in ruler_tag_list if isinstance(s, str) and s]
    if ruler_tag_list:
        ruler_tag_list.sort(key=len, reverse=True)
        ruler_pattern = re.compile("(" + "|".join(map(re.escape, ruler_tag_list)) + ")")

        def make_ruler(match):
            d = et.Element("date")
            e = et.SubElement(d, "ruler")
            e.text = match.group(1)
            return d

        replace_in_text_and_tail(xml_root, ruler_pattern, make_ruler, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
        
    # Dynasty Names ####################################################################################################
    # Reduce list
    dyn_tag_list = [s for s in dyn_tag_list if isinstance(s, str) and s]
    if dyn_tag_list:
        dyn_tag_list.sort(key=len, reverse=True)
        dyn_pattern = re.compile("(" + "|".join(map(re.escape, dyn_tag_list)) + ")")

        def make_dyn(match):
            d = et.Element("date")
            e = et.SubElement(d, "dyn")
            e.text = match.group(1)
            return d

        replace_in_text_and_tail(xml_root, dyn_pattern, make_dyn, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    
    # Suffixes #########################################################################################################
    xml_root = attach_suffixes(xml_root)
    # Clean nested tags ################################################################################################
    # Remove lone tags
    for node in xml_root.xpath('.//date'):
        s = node.xpath('string()')
        bad = ['一年', '一日']
        if s in bad:
            node.tag = 'to_remove'
    # Strip tags
    et.strip_tags(xml_root, 'to_remove')
    # Return to string
    text = et.tostring(xml_root, encoding='utf8').decode('utf8')
    
    return text


def consolidate_date(text):
    """
    Join separated date elements in the XML according to typical date order (year after era, month after year, etc.)
    :param text: str (XML)
    :return: str (XML)
    """
    # Remove spaces
    bu = text
    xml_root = et.ElementTree(et.fromstring(text)).getroot()
    xml_root = strip_ws_in_text_nodes(xml_root)
    text = et.tostring(xml_root, encoding='utf8').decode('utf8')
    ls = [
        ('dyn', 'ruler'),
        ('ruler', 'year'), ('ruler', 'era'),
        ('era', 'year'),
        ('era', 'filler'),
        ('ruler', 'filler'),
        ('dyn', 'filler'),
        ('year', 'season'),
        ('year', 'filler'),
        ('sexYear', 'int'),
        ('sexYear', 'month'),
        ('year', 'int'),
        ('year', 'month'),
        ('season', 'int'),
        ('season', 'month'),
        ('int', 'month'),
        ('month', 'gz'),
        ('month', 'lp'),
        ('month', 'day'),
        ('month', 'nmdgz'),
        ('gz', 'lp'),
        ('nmdgz', 'day'),
        ('day', 'gz'),
        ('month', 'lp_filler'),
        ('lp_filler', 'day'),
        ('gz', 'filler'),
        ('dyn', 'era')
    ]
    for tup in ls:
        text = re.sub(rf'</{tup[0]}></date>，*<date><{tup[1]}', f'</{tup[0]}><{tup[1]}', text)
        if 'metadata' in text:
            text = clean_attributes(text)
    # Parse to XML and return as string
    try:
        et.ElementTree(et.fromstring(text)).getroot()
        return text
    except et.ParseError:
        return "<root/>"


def clean_nested_tags(text):
    """
    Clean nested and invalid date tags from XML string.

    :param text: str, XML string with date tags
    :return: str, cleaned XML string
    """
    xml_root = et.ElementTree(et.fromstring(text)).getroot()
    # Clean
    for node in xml_root.xpath('.//date//date'):
        node.tag = 'to_remove'
    et.strip_tags(xml_root, 'to_remove')
    for tag in ['dyn', 'ruler', 'year', 'month', 'season', 'day', 'gz', 'lp', 'sexYear', 'nmdgz', 'lp_to_remove']:
        for node in xml_root.findall(f'.//{tag}//*'):
            node.tag = 'to_remove'
    for node in xml_root.findall('.//date'):
        heads = node.xpath('.//ancestor::head')
        if len(heads) == 0:
            elements = [sn.tag for sn in node.findall('./*')]
            # Clean dynasty only
            if elements == ['dyn'] or elements == ['season'] or elements == ['era'] or elements == ['ruler']:
                for sn in node.findall('.//*'):
                    sn.tag = 'to_remove'
                node.tag = 'to_remove'
    # Clean nonsense
    bad = ['一月', '一年', '一日']
    for node in xml_root.xpath('.//date'):
        if node.xpath('normalize-space(string())') in bad:
            node.tag = 'to_remove'
        tags = [sn.tag for sn in node.findall('./*')]
        # Remove lonely lunar phase
        if tags == ['lp']:
            node.tag = 'to_remove'
    # Strip tags
    et.strip_tags(xml_root, 'to_remove')
    et.strip_tags(xml_root, 'lp_to_remove')
    # Return to string
    text = et.tostring(xml_root, encoding='utf8').decode('utf8')
    return text


def index_date_nodes(xml_root) -> et._Element:
    """
    Index date nodes in XML element.
    """
    # Handle namespaces
    ns = {}
    if xml_root.tag.startswith('{'):
        ns_uri = xml_root.tag.split('}')[0][1:]
        ns = {'tei': ns_uri}

    index = 0
    date_xpath = './/tei:date' if ns else './/date'
    for node in xml_root.xpath(date_xpath, namespaces=ns):
        node.set('index', str(index))
        index += 1

    return xml_root
