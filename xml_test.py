import lxml.etree as et
import sanmiao.sanmiao as sanmiao
# Import modules
from sanmiao.loaders import prepare_tables
from sanmiao.config import (
    DEFAULT_TPQ, DEFAULT_TAQ, DEFAULT_GREGORIAN_START,
    phrase_dic_en, phrase_dic_fr
)
from sanmiao.bulk_processing import extract_date_table_bulk, dates_xml_to_df

def xml_test(ui, tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, civ=None, proliferate=False):
    """
    Main Chinese calendar date interpreter that processes various input formats.

    :param ui: str, input date string (Chinese calendar, ISO format, or Julian Day Number)
    :param lang: str, language for output ('en' or 'fr')
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
    if civ is None:
        civ = ['c', 'j', 'k']
    
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
    
    xml_root = et.fromstring(ui)

    # Load calendar tables
    tables = prepare_tables(civ=civ)
    
    # Extract date table from XML (moved from extract_date_table_bulk)
    df = dates_xml_to_df(xml_root, attributes=True)
    
    # Extract dates using optimized bulk function
    xml_string, output_df, implied = extract_date_table_bulk(
        xml_root, df=df, implied=implied,
        tpq=tpq, taq=taq, civ=civ, tables=tables, sequential=True, proliferate=proliferate
    )

    return xml_string, output_df, implied


ui = """
<root>
<date index="0" dyn_id="50" ruler_id="3910" era_id="113" year="1"><era>鳳皇</era><year>元年</year></date>
<date index="1"><dyn>魏</dyn><suffix>末</suffix></date>
<date index="2"><era>太和</era><year>元年</year></date>
<date index="3"><era>太平</era><year>元年</year></date>
<date index="4" year="2"><year>三年</year><month>三月</month></date>
<date index="5"><era>鳳皇</era><year>二年</year></date>
</root>
"""
xml_string, output_df, implied = xml_test(
    ui, tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, civ=None, proliferate=False
    )

print(xml_string)
print()
print(output_df[['date_string', 'dyn_id', 'ruler_id', 'era_id', 'year', 'month', 'day', 'error_str']])

# TODO hard internal filtering

