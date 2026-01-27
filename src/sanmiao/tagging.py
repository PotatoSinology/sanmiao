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
        "nmdgz","lp_filler","filler","season","gy","rel","meta","pb","text","body"}  # adjust tags you want to skip

SKIP_ALL = {"date","year","month","day","gz","sexYear","era","ruler","dyn","suffix",
            "int","lp","nmdgz","lp_filler","filler","season","gy","rel"}

SKIP_TEXT_ONLY = {"pb", "meta"}

YEAR_RE   = re.compile(r"((?<![一二三四五六七八九])(?:[一二三四五六七八九十]+|十有[一二三四五六七八九]|元)[年載])")
# "廿<date><year>" fix disappears because we won't create that broken boundary in text mode.

# Months: order matters (more specific first)
LEAPMONTH_RE1 = re.compile(r"閏月")
LEAPMONTH_RE2 = re.compile(r"閏((?:十[一二]|十有[一二]|正)月)")
LEAPMONTH_RE3 = re.compile(r"閏((?:[一二三四五六七八九十]|正|臘)月)")
MONTH_RE1     = re.compile(r"((?:十有[一二]|十[一二]|正)月)")
MONTH_RE2     = re.compile(r"((?<![一二三四五六七八九])(?:[一二三四五六七八九十]|正|臘)月)")

DAY_RE    = re.compile(r"((?<![一二三四五六七八九])(?:[一二三四五六七八九]|[一二]*十[一二三四五六七八九]*|[廿卄][一二三四五六七八九]*|卅|丗|三十)日)")
GZ_RE     = re.compile(r"([甲乙丙景丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")
SEXYEAR_RE = re.compile(r"(([甲乙丙景丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]))(年|歲)")
SEASON_RE = re.compile(r"([春秋冬夏])")

LP_RE = re.compile(r"([朔晦])")
GY_RE = re.compile(r"(改元)")

# Relational prefixes.
#
# User rules (2026-01):
# - Only "其" and "先是" may be tagged with unit="" (handled structurally later, not by regex).
# - All other rel markers require an explicit unit (年/歲/月); without a unit they MUST NOT be tagged.
# - "是歲，" / "今年，" / "今月，" may precede anything; whether it is *attached into* the following date is decided later.
# - "明月" means "bright moon", not "next month", so we exclude "明" when followed by just "月".
#
# Groups:
#   1 = dir char (後/次/來/明/昨/前/去/其/是/今)
#   2 = unit (年/歲/月), must be present in this regex
#   3 = trailing Chinese comma(s) immediately following the unit (optional)
# Note: Two patterns - one for "明" (must start with 年 or 歲), one for others
REL_RE_MING = re.compile(r"(明)([年歲][月]?)(，*)")  # "明" must be followed by 年 or 歲 (optionally 月 after)
REL_RE_OTHER = re.compile(r"([後次來昨前去其是今])([年歲月]+)(，*)")  # Other direction chars with any unit
REL_RE_XIANSHI = re.compile(r"(先是)(，*)")  # "先是" (previously/before this) - special compound pattern
SEX_YEAR_PREFIX_RE = re.compile(r"(歲[次在])\s*$")
PUNCT_RE = re.compile(r"^[，,、\s]*")

ERA_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世)")
DYNASTY_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世)")
RULER_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世|即位|踐阼)")


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
    filler.text = m.group(3)  # suffix (年 or 歲)
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
    Promote sexagenary day (gz) elements to sexagenary year (sexYear) when:
    1. Preceded by explicit year markers like 歲次 or 歲在, OR
    2. Followed by 年 or 歲 (e.g., "甲子年" where gz wasn't caught by SEXYEAR_RE)
    
    Lonely sexagenary binomes without fillers should remain as gz (day), not be
    promoted to sexYear (year).

    :param xml_root: et.Element, root of XML tree to process
    :return: et.Element, modified XML root
    """
    for d in xml_root.xpath(".//date[gz]"):
        prev = d.getprevious()
        has_year_marker = False
        filler_text = ""
        filler_position = "before"  # "before" for 歲次/歲在, "after" for 年/歲 suffix

        # Check for prefix markers (歲次 or 歲在)
        if prev is None:
            s = d.getparent().text or ""
            loc = ("parent", d.getparent())
        else:
            s = prev.tail or ""
            loc = ("tail", prev)

        m = SEX_YEAR_PREFIX_RE.search(s)
        if m:
            has_year_marker = True
            filler_text = m.group(1)
            filler_position = "before"
            # Remove prefix text
            new_s = s[:m.start()]
            if loc[0] == "parent":
                loc[1].text = new_s
            else:
                loc[1].tail = new_s

        # Check for suffix markers (年 or 歲) if no prefix found
        if not has_year_marker:
            tail = d.tail or ""
            # Check if tail starts with 年 or 歲 (possibly with punctuation)
            suffix_match = re.match(r"^([，,\s]*)([年歲])", tail)
            if suffix_match:
                has_year_marker = True
                filler_text = suffix_match.group(2)
                filler_position = "after"
                # Remove the filler from tail
                d.tail = suffix_match.group(1) + tail[suffix_match.end():]

        if not has_year_marker:
            continue

        gz_text = d.findtext("gz")

        # Find the gz element and replace it with sexYear
        gz_elem = d.find("gz")
        if gz_elem is not None:
            # Create sexYear element to replace gz
            sy = et.Element("sexYear")
            sy.text = gz_text

            # Replace gz with sexYear
            d.replace(gz_elem, sy)

            # Add filler element
            if filler_text:
                f = et.Element("filler")
                f.text = filler_text
                if filler_position == "before":
                    d.insert(d.index(sy), f)
                else:  # after
                    d.insert(d.index(sy) + 1, f)

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

    # Relational prefixes (unit-based) ###################################################################################
    # Tag early so we don't accidentally tag e.g. "明年" as the Ming dynasty "明".
    # IMPORTANT: bare "其" (unit="") is handled later structurally, not here.
    def make_rel(match):
        dir_ = match.group(1) or ""
        unit = match.group(2) or ""
        comma = (match.group(3) or "")
        rel_text = dir_ + unit + comma

        el = et.Element("rel")
        el.set("dir", dir_)
        el.set("unit", unit)
        el.text = rel_text
        # Note: el.tail is set by replace_in_text_and_tail to preserve text after the match
        return el
    
    def make_xianshi(match):
        """Handle '先是' (previously/before this) - special compound pattern"""
        comma = (match.group(2) or "")
        rel_text = "先是" + comma
        
        el = et.Element("rel")
        el.set("dir", "先")
        el.set("unit", "")  # No unit for "先是"
        el.text = rel_text
        # Note: el.tail is set by replace_in_text_and_tail to preserve text after the match
        
        return el

    # Apply patterns in order: "先是" first (most specific), then "明", then others
    # "先是" must come before REL_RE_OTHER to avoid matching "先" separately
    replace_in_text_and_tail(xml_root, REL_RE_XIANSHI, make_xianshi, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, REL_RE_MING, make_rel, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, REL_RE_OTHER, make_rel, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

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
    
    # Split ruler tags into regular and era_prefix_only
    if 'era_prefix_only' in ruler_tag_df.columns:
        era_prefix_ruler_tags = ruler_tag_df[ruler_tag_df['era_prefix_only'] == True]['string'].unique()
        regular_ruler_tags = ruler_tag_df[ruler_tag_df['era_prefix_only'] != True]['string'].unique()
    else:
        era_prefix_ruler_tags = []
        regular_ruler_tags = ruler_tag_df['string'].unique()
    ruler_tag_list = list(regular_ruler_tags) + list(era_prefix_ruler_tags)  # Keep for backward compatibility
    # Normal dates #####################################################################################################
    # Tag 改元 first so later passes don't mis-tag the 元 inside it (e.g. as a dynasty).
    def make_gy(match):
        el = et.Element("gy")
        el.text = match.group(1)
        return el
    replace_in_text_and_tail(xml_root, GY_RE, make_gy, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # Year, month, day, gz, season, lp
    xml_root = tag_basic_tokens(xml_root)
    # Lunar phases
    replace_in_text_and_tail(xml_root, LP_RE, make_simple_date("lp"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
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

        # First pass: Tag eras immediately before <date> elements
        def tag_eras_before_dates(xml_root, pattern, make_element):
            """Tag era names that occur immediately before <date> elements."""
            changed = True
            max_passes = 10
            for _ in range(max_passes):
                if not changed:
                    break
                changed = False
                
                # Collect only top-level date elements (filter nested ones during collection)
                date_elements = []
                for date_el in xml_root.iter("date"):
                    # Skip if nested inside another date element (check only direct parent)
                    parent = date_el.getparent()
                    if parent is not None and parent.tag == "date":
                        continue
                    date_elements.append(date_el)
                
                for date_el in date_elements:
                    parent = date_el.getparent()
                    if parent is None:
                        continue
                    
                    idx = parent.index(date_el)
                    text_to_check = None
                    is_tail = False
                    target_element = None
                    
                    # Check the tail of the previous sibling (if exists)
                    if idx > 0:
                        prev_sibling = parent[idx - 1]
                        if prev_sibling.tail:
                            text_to_check = prev_sibling.tail
                            is_tail = True
                            target_element = prev_sibling
                    # Otherwise check parent's text before this date element
                    elif parent.text:
                        text_to_check = parent.text
                        is_tail = False
                        target_element = parent
                    
                    if text_to_check:
                        # Use regex to find all matches ending at the end of the text
                        # This is more efficient than iterating through era list
                        matches_at_end = [m for m in pattern.finditer(text_to_check) if m.end() == len(text_to_check)]
                        if matches_at_end:
                            # Take the longest match (first in sorted list is longest)
                            match = matches_at_end[0]
                            new_el = make_element(match)
                            
                            if is_tail:
                                target_element.tail = text_to_check[:match.start()]
                                parent.insert(idx, new_el)
                            else:
                                target_element.text = text_to_check[:match.start()]
                                parent.insert(0, new_el)
                            changed = True
                            # Break to restart iteration with updated structure
                            break
        
        tag_eras_before_dates(xml_root, era_pattern, make_era)
        
        # Second pass: Tag eras anywhere else
        replace_in_text_and_tail(xml_root, era_pattern, make_era, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # Ruler Names ######################################################################################################
    # First pass: Tag era_prefix_only ruler tags immediately before era elements
    if len(era_prefix_ruler_tags) > 0:
        era_prefix_ruler_list = [s for s in era_prefix_ruler_tags if isinstance(s, str) and s]
        if era_prefix_ruler_list:
            era_prefix_ruler_list.sort(key=len, reverse=True)
            era_prefix_ruler_pattern = re.compile("(" + "|".join(map(re.escape, era_prefix_ruler_list)) + ")")

            def make_ruler(match):
                d = et.Element("date")
                e = et.SubElement(d, "ruler")
                e.text = match.group(1)
                return d

            def tag_era_prefix_rulers_before_eras(xml_root, pattern, make_element):
                """Tag era_prefix_only ruler names that occur immediately before <date> elements containing eras."""
                changed = True
                max_passes = 10
                for _ in range(max_passes):
                    if not changed:
                        break
                    changed = False
                    
                    # Find all date elements that contain era elements
                    date_elements_with_era = []
                    for date_el in xml_root.iter("date"):
                        # Check if this date element contains an era
                        if date_el.find("era") is not None:
                            # Skip if nested inside another date element
                            parent = date_el.getparent()
                            if parent is not None and parent.tag == "date":
                                continue
                            date_elements_with_era.append(date_el)
                    
                    for date_el in date_elements_with_era:
                        parent = date_el.getparent()
                        if parent is None:
                            continue
                        
                        idx = parent.index(date_el)
                        text_to_check = None
                        is_tail = False
                        target_element = None
                        
                        # Check the tail of the previous sibling (if exists)
                        if idx > 0:
                            prev_sibling = parent[idx - 1]
                            if prev_sibling.tail:
                                text_to_check = prev_sibling.tail
                                is_tail = True
                                target_element = prev_sibling
                        # Otherwise check parent's text before this date element
                        elif parent.text:
                            text_to_check = parent.text
                            is_tail = False
                            target_element = parent
                        
                        if text_to_check:
                            # Use regex to find all matches ending at the end of the text
                            matches_at_end = [m for m in pattern.finditer(text_to_check) if m.end() == len(text_to_check)]
                            if matches_at_end:
                                # Take the longest match
                                match = matches_at_end[0]
                                new_el = make_element(match)
                                
                                if is_tail:
                                    target_element.tail = text_to_check[:match.start()]
                                    parent.insert(idx, new_el)
                                else:
                                    target_element.text = text_to_check[:match.start()]
                                    parent.insert(0, new_el)
                                changed = True
                                # Break to restart iteration with updated structure
                                break
            
            tag_era_prefix_rulers_before_eras(xml_root, era_prefix_ruler_pattern, make_ruler)
    
    # Second pass: Tag regular ruler tags anywhere (exclude era_prefix_only tags)
    regular_ruler_list = [s for s in regular_ruler_tags if isinstance(s, str) and s]
    if regular_ruler_list:
        regular_ruler_list.sort(key=len, reverse=True)
        ruler_pattern = re.compile("(" + "|".join(map(re.escape, regular_ruler_list)) + ")")

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

    # Sexagenary year promotion (must happen after era/ruler/dynasty tagging)
    xml_root = promote_gz_to_sexyear(xml_root)

    # Suffixes #########################################################################################################
    xml_root = attach_suffixes(xml_root)

    # Bare "其" without unit (structural tagging) #######################################################################
    #
    # Rule: tag standalone "其" only when it is directly adjacent to a following <date>
    # (no punctuation between), and that immediate <date> begins with year/sexYear or lower.
    #
    # This prevents tagging discourse "其，" and prevents gluing "其" onto dynasty/ruler/era-only dates.
    YEAR_OR_LOWER_TAGS = {"year", "sexYear", "month", "day", "gz", "nmdgz", "int", "lp", "season", "lp_filler", "filler"}

    def _date_child_tags(d: et._Element) -> set[str]:
        return {c.tag for c in d if isinstance(c.tag, str)}

    def _maybe_insert_bare_qi_before_next_date(parent: et._Element, before_node: et._Element | None) -> None:
        """
        If the text slot right before the next sibling <date> ends with bare '其' (optionally followed by whitespace),
        replace that '其' with a <rel dir="其" unit="">其</rel> element.
        """
        # Determine the string slot we are checking and the next sibling <date>
        if before_node is None:
            s = parent.text or ""
            next_el = parent[0] if len(parent) > 0 else None
            setter = ("text", parent)
        else:
            s = before_node.tail or ""
            next_el = before_node.getnext()
            setter = ("tail", before_node)

        if not s or next_el is None or next_el.tag != "date":
            return

        # Must end with bare '其' (allow trailing whitespace only)
        m = re.search(r"其(\s*)$", s)
        if not m:
            return

        # The immediate next <date> must begin with year/sexYear or lower
        next_tags = _date_child_tags(next_el)
        if not (next_tags & YEAR_OR_LOWER_TAGS):
            return

        ws = m.group(1) or ""
        prefix = s[:m.start()]

        rel_el = et.Element("rel")
        rel_el.set("dir", "其")
        rel_el.set("unit", "")
        rel_el.text = "其"
        rel_el.tail = ws

        if setter[0] == "text":
            parent.text = prefix
            parent.insert(0, rel_el)
        else:
            before_node.tail = prefix
            # insert after before_node
            idx = parent.index(before_node)
            parent.insert(idx + 1, rel_el)

    for parent in list(xml_root.iter()):
        # Only consider parents that actually have a following element to attach to
        if len(parent) > 0:
            _maybe_insert_bare_qi_before_next_date(parent, None)
            for child in list(parent):
                _maybe_insert_bare_qi_before_next_date(parent, child)

    # Attach/wrap standalone <rel> #########################################################################
    #
    # Rules:
    # - If <rel> immediately precedes a <date>, move it into that <date> as first child ONLY if allowed by rules below.
    # - If <rel> is standalone, keep only those with non-empty unit by wrapping as <date><rel .../></date>.
    # - Otherwise drop standalone rel (unit="").
    #
    # Attachment rules (user rules):
    # - "其" and "先是" with unit="" can only attach if the immediate next <date> begins with year/sexYear or lower.
    # - "是歲" / "其歲" / "今歲" (and "是年"/"其年"/"今年") may precede anything, but can only attach if the *date cluster* has year/sexYear or lower.
    # - "是月" / "其月" / "今月" can only attach if the *date cluster* has month or lower.
    # - All other rel markers require a unit; they can only attach if the immediate next <date> begins with month or lower.
    MONTH_OR_LOWER_TAGS = {"month", "day", "gz", "nmdgz", "int", "lp", "season", "lp_filler", "filler"}
    JOINER_TAIL_RE = re.compile(r"^[，,\s]*$")

    def _collect_date_cluster(start: et._Element) -> list[et._Element]:
        cluster = [start]
        cur = start
        while True:
            tail = cur.tail or ""
            if not JOINER_TAIL_RE.match(tail):
                break
            nxt = cur.getnext()
            if nxt is None or nxt.tag != "date":
                break
            cluster.append(nxt)
            cur = nxt
        return cluster

    def _cluster_child_tags(cluster: list[et._Element]) -> set[str]:
        out: set[str] = set()
        for d in cluster:
            out |= _date_child_tags(d)
        return out

    for rel in list(xml_root.xpath(".//rel")):
        # Skip rel already inside a date
        if rel.xpath("boolean(ancestor::date)"):
            continue

        parent = rel.getparent()
        if parent is None:
            continue

        next_el = rel.getnext()
        rel_tail = rel.tail or ""

        # Case A: immediately before a <date>
        if next_el is not None and next_el.tag == "date" and rel_tail.strip() == "":
            dir_ = (rel.get("dir") or "").strip()
            unit = (rel.get("unit") or "").strip()

            next_tags = _date_child_tags(next_el)
            cluster = _collect_date_cluster(next_el)
            cluster_tags = _cluster_child_tags(cluster)

            attach_ok = False

            # Bare 其 or 先是 (unit="") is only allowed if the immediate next date begins with year/sexYear or lower.
            if unit == "" and dir_ in ("其", "先"):
                attach_ok = bool(next_tags & YEAR_OR_LOWER_TAGS)

            # 是歲 / 其歲 / 今歲 (and 是年/其年/今年) may precede dyn/ruler/era, but only attach if the cluster has year/sexYear or lower.
            elif dir_ in {"是", "其", "今"} and unit in {"歲", "年"}:
                attach_ok = bool(cluster_tags & YEAR_OR_LOWER_TAGS)

            # Optional: 是月 / 其月 / 今月 attach only if the cluster has month or lower.
            elif dir_ in {"是", "其", "今"} and unit == "月":
                attach_ok = bool(cluster_tags & MONTH_OR_LOWER_TAGS)

            # All other rel markers require a unit and only attach if what follows begins with month or lower.
            else:
                if unit != "":
                    attach_ok = bool(next_tags & MONTH_OR_LOWER_TAGS)

            if attach_ok:
                idx = parent.index(rel)
                parent.remove(rel)
                rel.tail = None
                next_el.insert(0, rel)
                continue

        # Case B: standalone rel with unit -> wrap into its own <date>
        unit = rel.get("unit") or ""
        if unit.strip() != "":
            idx = parent.index(rel)
            # Preserve any tail outside the new <date>
            tail_to_preserve = rel.tail
            rel.tail = None

            # Create <date> wrapper and move rel inside it
            d = et.Element("date")
            parent.insert(idx, d)
            parent.remove(rel)
            d.append(rel)

            # Reattach preserved tail to the wrapper <date> (so surrounding text stays in document)
            if tail_to_preserve:
                d.tail = (d.tail or "") + tail_to_preserve
            continue

        # Case C: standalone rel with empty unit -> drop it, preserve tail in parent
        prev = rel.getprevious()
        tail = rel.tail or ""
        if prev is None:
            parent.text = (parent.text or "") + tail
        else:
            prev.tail = (prev.tail or "") + tail
        parent.remove(rel)

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
        ('era', 'sexYear'),
        ('era', 'filler'),
        ('ruler', 'filler'),
        ('dyn', 'filler'),
        ('year', 'season'),
        ('year', 'filler'),
        ('year', 'sexYear'),
        ('sexYear', 'season'),
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
