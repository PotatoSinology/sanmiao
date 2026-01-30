__version__ = "0.2.3"

# Import from modules
from .converters import gz_year, jdn_to_gz, ganshu, numcon, iso_to_jdn, jdn_to_iso
from .config import get_cal_streams_from_civ
from .xml_utils import strip_ws_in_text_nodes, clean_attributes, remove_lone_tags, strip_text, replace_in_text_and_tail
from .config import phrase_dic_en, phrase_dic_fr, phrase_dic_zh, phrase_dic_ja, phrase_dic_de, get_phrase_dic, date_elements, sanitize_gs
from .utils import guess_variant
from .solving import solve_date_simple, solve_date_with_year, solve_date_with_lunar_constraints
from .reporting import jdn_to_ccs, jy_to_ccs, generate_report_from_dataframe
from .bulk_processing import extract_date_table, extract_date_table_bulk, dates_xml_to_df, normalise_date_fields, bulk_resolve_dynasty_ids, bulk_resolve_ruler_ids, bulk_resolve_era_ids
from .tagging import tag_date_elements, consolidate_date, index_date_nodes
from .xml_processing import filter_annals, backwards_fill_days
from .loaders import prepare_tables

# Import from main module
from .sanmiao import cjk_date_interpreter
