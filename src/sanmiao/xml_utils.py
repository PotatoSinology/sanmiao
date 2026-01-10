# XML processing utilities for sanmiao

import re
import lxml.etree as et
from typing import Callable, Any

# Regex patterns for XML processing
WS_RE = re.compile(r"\s+")


def strip_ws_in_text_nodes(root: et._Element) -> et._Element:
    """
    Strip whitespace from text nodes in XML tree.

    :param root: Root XML element
    :return: Modified XML root
    """
    for elem in root.iter():
        if elem.text:
            elem.text = elem.text.strip()
        if elem.tail:
            elem.tail = elem.tail.strip()
    return root


def clean_attributes(xml_string: str) -> str:
    """
    Clean and normalize XML attributes.

    :param xml_string: XML string
    :return: Cleaned XML string
    """
    # Remove empty attributes
    xml_string = re.sub(r'\s+[a-zA-Z_][a-zA-Z0-9_]*=""', '', xml_string)

    # Normalize attribute spacing
    xml_string = re.sub(r'(\S)=', r'\1=', xml_string)
    xml_string = re.sub(r'=(\S)', r'=\1', xml_string)

    return xml_string


def remove_lone_tags(xml_string: str) -> et._Element:
    """
    Remove lone date tags that don't contain meaningful content.

    :param xml_string: XML string
    :return: XML element with lone tags removed
    """
    # Parse XML
    try:
        xml_root = et.fromstring(xml_string.encode('utf-8'))
    except et.ParseError:
        # Return a dummy element if parsing fails
        return et.Element("root")

    # Find and remove lone date tags
    for date_elem in xml_root.xpath('.//date'):
        has_content = False

        # Check if date has meaningful child elements or text
        for child in date_elem:
            if child.tag in ['year', 'month', 'day', 'gz', 'lp', 'sexYear', 'era', 'dyn', 'ruler']:
                has_content = True
                break

        # Remove if no meaningful content
        if not has_content:
            parent = date_elem.getparent()
            if parent is not None:
                parent.remove(date_elem)

    return xml_root


def strip_text(xml_root: et._Element) -> et._Element:
    """
    Remove all non-date text from XML string
    :param xml_string: str (XML)
    :return: str (XML)
    """
    # Create a new root element for the filtered output
    new_root = et.Element("root")
    # Copy only <date> elements into the new root
    for date in xml_root.findall(".//date"):
        date.tail = None
        new_root.append(date)
    return new_root


def replace_in_text_and_tail(xml_root: et._Element, pattern: re.Pattern,
                           replacement: Callable[[re.Match], Any],
                           skip_text_tags: set = None,
                           skip_all_tags: set = None) -> et._Element:
    """
    Replace text matching a regex pattern in XML text and tail nodes.

    :param xml_root: XML root element
    :param pattern: Compiled regex pattern
    :param replacement: Function to generate replacement element
    :param skip_text_tags: Tags to skip when processing text content
    :param skip_all_tags: Tags to skip entirely
    :return: Modified XML root
    """
    if skip_text_tags is None:
        skip_text_tags = set()
    if skip_all_tags is None:
        skip_all_tags = set()

    def process_element(elem: et._Element) -> None:
        # Skip certain tags entirely
        if elem.tag in skip_all_tags:
            return

        # Process tail text
        if elem.tail:
            matches = list(pattern.finditer(elem.tail))
            if matches:
                # Process matches in reverse order
                for match in reversed(matches):
                    # Create replacement element
                    replacement_elem = replacement(match)

                    # Insert replacement before current element
                    parent = elem.getparent()
                    if parent is not None:
                        idx = parent.index(elem)
                        parent.insert(idx + 1, replacement_elem)

                        # Update tail text
                        elem.tail = elem.tail[:match.start()] + elem.tail[match.end():]

        # Process text content (unless tag is in skip_text_tags)
        if elem.text and elem.tag not in skip_text_tags:
            matches = list(pattern.finditer(elem.text))
            if matches:
                # Process matches in reverse order
                for match in reversed(matches):
                    # Create replacement element
                    replacement_elem = replacement(match)

                    # Insert replacement as first child
                    if len(elem) == 0:
                        elem.text = elem.text[:match.start()]
                        elem.append(replacement_elem)
                        elem.tail = elem.text[match.end():]
                        elem.text = None
                    else:
                        # Insert before first child
                        elem.insert(0, replacement_elem)
                        # Update text
                        elem.text = elem.text[:match.start()] + elem.text[match.end():]

        # Process child elements
        for child in list(elem):
            process_element(child)

    process_element(xml_root)
    return xml_root