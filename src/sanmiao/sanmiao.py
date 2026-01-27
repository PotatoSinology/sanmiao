import pandas as pd
import re
import lxml.etree as et
# Import modules
from .loaders import prepare_tables
from .config import (
    DEFAULT_TPQ, DEFAULT_TAQ, DEFAULT_GREGORIAN_START,
    get_phrase_dic
)
from .xml_utils import remove_lone_tags, strip_text
from .reporting import jdn_to_ccs, jy_to_ccs, generate_report_from_dataframe
from .tagging import tag_date_elements, consolidate_date, index_date_nodes
from .bulk_processing import extract_date_table_bulk, add_can_names_bulk, dates_xml_to_df

def cjk_date_interpreter(ui, lang='en', jd_out=False, pg=False, gs=None, tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, civ=None, sequential=True):
    """
    Main Chinese calendar date interpreter that processes various input formats.

    :param ui: str, input date string (Chinese calendar, ISO format, or Julian Day Number)
    :param lang: str, language for output ('en', 'fr', 'zh', 'ja', 'de'). Defaults to 'en' if not specified or invalid.
    :param jd_out: bool, whether to include Julian Day Numbers in output
    :param pg: bool, use proleptic Gregorian calendar
    :param gs: list, Gregorian start date [year, month, day]
    :param tpq: int, earliest date (terminus post quem)
    :param taq: int, latest date (terminus ante quem)
    :param civ: str or list, civilization filter
    :param sequential: bool, process dates sequentially
    :param proliferate: bool, allow date proliferation
    :return: str, formatted interpretation report
    """
    # Defaults
    if gs is None:
        gs = DEFAULT_GREGORIAN_START
    if civ is None:
        civ = ['c', 'j', 'k']
    proliferate = not sequential
    
    # Default to 'en' if lang is None or invalid
    if lang is None:
        lang = 'en'
    phrase_dic = get_phrase_dic(lang)

    ui = ui.replace(' ', '')
    ui = re.sub(r'[,;]', r'\n', ui)
    items = re.split(r'\n', ui)
    output_string = ''
    
    # Initialize implied state (moved from extract_date_table_bulk)
    implied = {
        'cal_stream_ls': [],
        'dyn_id_ls': [],
        'ruler_id_ls': [],
        'era_id_ls': [],
        'year': None,
        'month': None,
        'intercalary': None,
        'sex_year': None
    }
    
    for item in items:
        if item != '':
            # Determine input type
            # Find Chinese characters
            is_ccs = bool(re.search(r'[\u4e00-\u9fff]', item))
            # Find ISO strings
            isos = re.findall(r'-*\d+-\d+-\d+', item)
            is_iso = len(isos) > 0
            # Try to find year / jdn
            is_y = False
            is_jdn = False
            try:
                value = float(item)
                if value.is_integer():  # e.g. 10.0 → True
                    # it's an integer, so maybe a year
                    if len(item.split('.')[0]) > 5:
                        is_jdn = True  # large integer, probably JDN
                        item = float(item)
                    else:
                        is_y = True  # short integer, probably a year
                        item = int(float(item))
                else:
                    is_jdn = True  # non-integer numeric, e.g. 168497.5
                    item = float(item)
            except ValueError:
                pass
            
            # Proceed according to input type
            if is_jdn or is_iso:
                report = jdn_to_ccs(item, proleptic_gregorian=pg, gregorian_start=gs, lang=lang, civ=civ)
            elif is_y:
                report = jy_to_ccs(item, lang=lang, civ=civ)
            elif is_ccs:
                # Reset implied state for each date in non-sequential mode
                if not sequential:
                    implied = {
                        'cal_stream_ls': [],
                        'dyn_id_ls': [],
                        'ruler_id_ls': [],
                        'era_id_ls': [],
                        'year': None,
                        'month': None,
                        'intercalary': None,
                        'sex_year': None
                    }
                
                # Convert string to XML, tag all date elements
                xml_string = tag_date_elements(item, civ=civ)
                
                # Consolidate adjacent date elements
                xml_string = consolidate_date(xml_string)
                
                # Remove lone tags
                xml_root = remove_lone_tags(xml_string)
                
                # Remove non-date text
                xml_root = strip_text(xml_root)

                # Index date nodes
                xml_root = index_date_nodes(xml_root)
                
                # Load calendar tables
                tables = prepare_tables(civ=civ)
                
                # Extract dates using optimized bulk function
                xml_string, output_df, implied = extract_date_table_bulk(
                    xml_root, implied=implied, pg=pg, gs=gs, lang=lang, tpq=tpq, taq=taq, 
                    civ=civ, tables=tables, sequential=sequential, proliferate=proliferate
                )

                # Extract tables for canonical name addition
                era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = tables

                # Add canonical names to all results
                if not output_df.empty:
                    output_df = add_can_names_bulk(output_df, ruler_can_names, dyn_df, era_df)
                
                # Generate report from dataframe
                report = generate_report_from_dataframe(output_df, phrase_dic, jd_out, tpq=tpq, taq=taq)
            else:
                continue
            output_string += report + '\n\n'
    
    return output_string