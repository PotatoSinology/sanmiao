import re
import numpy as np
import pandas as pd
import lxml.etree as et
from .config import (
    DEFAULT_TPQ, DEFAULT_TAQ, LP_DIC,
    phrase_dic_en, phrase_dic_fr,
)
from .converters import (
    numcon, ganshu
)
from .loaders import prepare_tables
from .config import get_cal_streams_from_civ, LP_DIC, normalize_defaults
from .solving import (
    solve_date_simple, solve_date_with_year, solve_date_with_lunar_constraints,
    add_jdn_and_iso_to_proliferate_candidates
)

# Helper functions to reduce redundancy

def prioritize_resolved_values(df):
    """
    Helper function to prioritize attributes over resolved values in DataFrame.
    
    When resolving string identifiers to IDs, this function ensures that explicit
    attributes (set in the original data) take precedence over values resolved
    from string matching.
    
    :param df: DataFrame with columns ending in '_resolved' that need to be merged
    :return: DataFrame with resolved values copied to base columns only where attributes don't exist
    """
    resolved_cols = [col for col in df.columns if col.endswith('_resolved')]
    if resolved_cols:
        for resolved_col in resolved_cols:
            base_col = resolved_col.replace('_resolved', '')
            # Only copy resolved values where base column is NaN (no explicit attribute set)
            if base_col in df.columns:
                mask_no_attr = df[base_col].isna()
                mask_resolved = df[resolved_col].notna()
                mask_to_copy = mask_no_attr & mask_resolved
            else:
                # Base column doesn't exist, copy all resolved values
                mask_to_copy = df[resolved_col].notna()
            
            if mask_to_copy.any():
                df.loc[mask_to_copy, base_col] = df.loc[mask_to_copy, resolved_col]
            # Drop the resolved column
            df = df.drop(columns=[resolved_col])
    return df


def check_explicit_attribute(row_before_resolution, attr_name):
    """
    Check if an attribute existed as an explicit value before string resolution.
    
    :param row_before_resolution: Series representing a row before resolution
    :param attr_name: str, name of the attribute to check (e.g., 'era_id', 'dyn_id')
    :return: tuple (bool, value) - (has_explicit_attr, attr_value)
    """
    if attr_name in row_before_resolution and pd.notna(row_before_resolution.get(attr_name)):
        return True, row_before_resolution[attr_name]
    return False, None


def reset_implied_state_for_era(implied, era_id, era_df):
    """
    Reset implied state to match a specific era's context.
    
    :param implied: dict, current implied state
    :param era_id: int, era_id to reset to
    :param era_df: DataFrame, era table
    :return: None (modifies implied in place)
    """
    era_info = era_df[era_df['era_id'] == era_id]
    if not era_info.empty:
        era_row = era_info.iloc[0]
        if pd.notna(era_row.get('cal_stream')):
            implied['cal_stream_ls'] = [era_row['cal_stream']]
        if pd.notna(era_row.get('dyn_id')):
            implied['dyn_id_ls'] = [era_row['dyn_id']]
        if pd.notna(era_row.get('ruler_id')):
            implied['ruler_id_ls'] = [era_row['ruler_id']]
        implied['era_id_ls'] = [era_id]
        # Reset year/month when era changes (new context)
        implied['year'] = None
        implied['month'] = None
        implied['intercalary'] = None


def reset_implied_state_for_ruler(implied, ruler_id, ruler_df):
    """
    Reset implied state to match a specific ruler's context.
    
    :param implied: dict, current implied state
    :param ruler_id: int, ruler_id to reset to
    :param ruler_df: DataFrame, ruler table
    :return: None (modifies implied in place)
    """
    ruler_info = ruler_df[ruler_df['person_id'] == ruler_id]
    if not ruler_info.empty:
        ruler_row = ruler_info.iloc[0]
        if 'cal_stream' in ruler_df.columns and pd.notna(ruler_row.get('cal_stream')):
            implied['cal_stream_ls'] = [ruler_row['cal_stream']]
        if pd.notna(ruler_row.get('dyn_id')):
            implied['dyn_id_ls'] = [ruler_row['dyn_id']]
        implied['ruler_id_ls'] = [ruler_id]
        # Clear era (ruler is less specific than era)
        implied['era_id_ls'] = []
        # Reset year/month when ruler changes (new context)
        implied['year'] = None
        implied['month'] = None
        implied['intercalary'] = None


def reset_implied_state_for_dynasty(implied, dyn_id, dyn_df):
    """
    Reset implied state to match a specific dynasty's context.
    
    :param implied: dict, current implied state
    :param dyn_id: int, dyn_id to reset to
    :param dyn_df: DataFrame, dynasty table
    :return: None (modifies implied in place)
    """
    dyn_info = dyn_df[dyn_df['dyn_id'] == dyn_id]
    if not dyn_info.empty:
        dyn_row = dyn_info.iloc[0]
        if 'cal_stream' in dyn_df.columns and pd.notna(dyn_row.get('cal_stream')):
            implied['cal_stream_ls'] = [dyn_row['cal_stream']]
        implied['dyn_id_ls'] = [dyn_id]
        # Clear ruler and era (dynasty is less specific)
        implied['ruler_id_ls'] = []
        implied['era_id_ls'] = []
        # Reset year/month when dynasty changes (new context)
        implied['year'] = None
        implied['month'] = None
        implied['intercalary'] = None


def clear_preliminary_errors(result_df):
    """
    Clear preliminary error messages from successfully resolved dates.
    
    Removes "No candidates generated" and "Year out of bounds" errors when
    a date has been successfully resolved (has ind_year and context).
    
    :param result_df: DataFrame with solved date results
    :return: DataFrame with cleaned error strings
    """
    # Check if date was successfully resolved
    is_resolved = (
        'ind_year' in result_df.columns and result_df['ind_year'].notna().any() and
        (('era_id' in result_df.columns and result_df['era_id'].notna().any()) or
         ('dyn_id' in result_df.columns and result_df['dyn_id'].notna().any()) or
         ('ruler_id' in result_df.columns and result_df['ruler_id'].notna().any()))
    )
    
    if is_resolved and 'error_str' in result_df.columns:
        # Remove "No candidates generated" and "Year out of bounds" if date was resolved
        result_df['error_str'] = result_df['error_str'].str.replace(
            r'No candidates generated;?\s*', '', regex=True
        )
        result_df['error_str'] = result_df['error_str'].str.replace(
            r'Year out of bounds;?\s*', '', regex=True
        )
        # Clean up any double semicolons or trailing spaces
        result_df['error_str'] = result_df['error_str'].str.replace(r';\s*;', ';', regex=True).str.strip()
        # If error_str is now empty or just whitespace, set to empty string
        result_df.loc[result_df['error_str'].str.strip() == '', 'error_str'] = ''
    
    return result_df


def extract_date_table(xml_string, pg=False, gs=None, lang='en', tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, civ=None, tables=None):
    """
    Extract date table from XML string using optimized bulk processing.
    
    This is a wrapper that calls extract_date_table_bulk() for consistency.
    
    :param xml_string: XML string with tagged date elements
    :param pg: bool, proleptic gregorian flag
    :param gs: list, gregorian start date [YYYY, MM, DD]
    :param lang: str, language ('en' or 'fr')
    :param tpq: int, terminus post quem
    :param taq: int, terminus ante quem
    :param civ: str or list, civilization filter
    :param tables: Optional pre-loaded tables tuple. If None, will load via prepare_tables().
    :return: tuple (xml_string, report, output_df)
    """
    # Defaults
    gs, civ = normalize_defaults(gs, civ)
    
    # Use the optimized bulk function (delegates to extract_date_table_bulk)
    return extract_date_table_bulk(
        xml_string, pg=pg, gs=gs, lang=lang,
        tpq=tpq, taq=taq, civ=civ, tables=tables, sequential=True
    )


def dates_xml_to_df(xml_root, attributes: bool = False) -> pd.DataFrame:
    """
    Convert XML string with date elements to pandas DataFrame.

    :param xml_root: ElementTree element, XML root containing date elements
    :param attributes: bool, if True, extract both attributes and child elements from <date> elements.
                       Attributes take precedence during normalization when both are present.
                       If False, extract only child elements (default behavior).
                       Attributes extracted: cal_stream, dyn_id, ruler_id, era_id, ind_year, year, 
                       sex_year, month, intercalary, day, gz, nmd_gz, lp
    :return: pd.DataFrame, DataFrame with extracted date information
    """
    # Handle namespaces - check if root has a default namespace
    ns = {}
    if xml_root.tag.startswith('{'):
        # Extract namespace from root tag
        ns_uri = xml_root.tag.split('}')[0][1:]
        ns = {'tei': ns_uri}

    rows = []
    # Use namespace-aware XPath
    date_xpath = './/tei:date[@index]' if ns else './/date[@index]'
    for node in xml_root.xpath(date_xpath, namespaces=ns):
        # Always extract date_index and date_string
        row = {
            "date_index": int(node.attrib.get("index")),
            "date_string": node.xpath("normalize-space(string())", namespaces=ns) if node.xpath("normalize-space(string())", namespaces=ns) else "",
        }
        
        # Extract child elements (always done, as fallback for incomplete attributes)
        def get1(xp):
            result = node.xpath(f'normalize-space(string({xp}))', namespaces=ns)
            return result if result and result.strip() else None

        row.update({
            "dyn_str": get1(".//tei:dyn" if ns else ".//dyn"),
            "ruler_str": get1(".//tei:ruler" if ns else ".//ruler"),
            "era_str": get1(".//tei:era" if ns else ".//era"),
            "year_str": get1(".//tei:year" if ns else ".//year"),
            "sexYear_str": get1(".//tei:sexYear" if ns else ".//sexYear"),
            "month_str": get1(".//tei:month" if ns else ".//month"),
            "day_str": get1(".//tei:day" if ns else ".//day"),
            "gz_str": get1(".//tei:gz" if ns else ".//gz"),
            "lp_str": get1(".//tei:lp" if ns else ".//lp"),
            "nmd_gz_str": get1(".//tei:nmd_gz" if ns else ".//nmdgz"),
            "has_int": 1 if node.xpath(".//tei:int" if ns else ".//int", namespaces=ns) else 0,
        })
        
        # If we have gz and lp = 0, also set nmd_gz to equal gz
        if row.get("gz_str") and row.get("lp_str") == "朔" and not row.get("nmd_gz_str"):
            row["nmd_gz_str"] = row["gz_str"]

        # If attributes=True, also extract attributes from <date> element
        # Attributes will take precedence over child elements during normalization
        if attributes:
            attr_names = [
                'cal_stream', 'dyn_id', 'ruler_id', 'era_id', 'ind_year',
                'year', 'sex_year', 'month', 'intercalary', 'day', 'gz', 'nmd_gz', 'lp'
            ]
            for attr_name in attr_names:
                attr_value = node.attrib.get(attr_name)
                if attr_value is not None:
                    # Convert to appropriate type - all these attributes are numeric (including negative values like lp=-1)
                    try:
                        # Try to convert to int (handles strings like "1", "23", "-1", etc.)
                        row[attr_name] = int(attr_value)
                    except (ValueError, TypeError):
                        # If conversion fails, keep as string
                        row[attr_name] = attr_value

        # Build present_elements string - prioritize attributes if present, otherwise use child elements
        present_elements = ""
        if ('dyn_id' in row and pd.notna(row.get('dyn_id'))) or (row['dyn_str'] and row['dyn_str'].strip()):
            present_elements += "h"
        if ('ruler_id' in row and pd.notna(row.get('ruler_id'))) or (row['ruler_str'] and row['ruler_str'].strip()):
            present_elements += "r"
        if ('era_id' in row and pd.notna(row.get('era_id'))) or (row['era_str'] and row['era_str'].strip()):
            present_elements += "e"
        if ('year' in row and pd.notna(row.get('year'))) or (row['year_str'] and row['year_str'].strip()):
            present_elements += "y"
        if ('sex_year' in row and pd.notna(row.get('sex_year'))) or (row['sexYear_str'] and row['sexYear_str'].strip()):
            present_elements += "s"
        if ('month' in row and pd.notna(row.get('month'))) or (row['month_str'] and row['month_str'].strip()):
            present_elements += "m"
        if ('intercalary' in row and pd.notna(row.get('intercalary'))) or (row['has_int'] == 1):
            present_elements += "i"
        if ('lp' in row and pd.notna(row.get('lp'))) or (row['lp_str'] and row['lp_str'].strip()):
            present_elements += "l"
        if ('nmd_gz' in row and pd.notna(row.get('nmd_gz'))) or (row['nmd_gz_str'] and row['nmd_gz_str'].strip()):
            present_elements += "z"
        if ('day' in row and pd.notna(row.get('day'))) or (row['day_str'] and row['day_str'].strip()):
            present_elements += "d"
        if ('gz' in row and pd.notna(row.get('gz'))) or (row['gz_str'] and row['gz_str'].strip()):
            present_elements += "g"
        row['present_elements'] = present_elements

        if row['sexYear_str'] is not None:
            row['sexYear_str'] = re.sub(r'[歲年]', '', row['sexYear_str'])
        
        rows.append(row)
    return pd.DataFrame(rows)


def normalise_date_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize and convert string date fields to numeric values in DataFrame.
    
    If attribute values already exist (from <date> element attributes), they take precedence
    over string values extracted from child elements. String processing only occurs for rows
    where the attribute is missing or NaN.

    :param df: pd.DataFrame, DataFrame with string date fields
    :return: pd.DataFrame, DataFrame with normalized numeric date fields
    """
    out = df.copy()
    
    # year - only process string if attribute doesn't exist or is NaN for that row
    # Initialize year column if it doesn't exist
    if 'year' not in out.columns:
        out['year'] = pd.Series(index=out.index, dtype='float64')  # Initialize with proper dtype
    
    # Process string only for rows where year attribute is missing/NaN
    mask_no_attr = out['year'].isna()
    
    if 'year_str' in out.columns and mask_no_attr.any():
        # Handle "元年" case first
        yuan_mask = mask_no_attr & (out["year_str"] == "元年")
        if yuan_mask.any():
            out.loc[yuan_mask, "year"] = 1.0
        # Convert numeric strings
        m = mask_no_attr & out["year_str"].notna() & (out["year_str"] != "元年")
        if m.any():
            out.loc[m, "year"] = out.loc[m, "year_str"].str.rstrip('年').map(numcon).astype('float64')

    # sexYear - only process string if attribute doesn't exist or is NaN for that row
    if 'sex_year' not in out.columns:
        out['sex_year'] = pd.Series(index=out.index, dtype='float64')  # Initialize with proper dtype
    
    mask_no_attr = out['sex_year'].isna()
    
    if 'sexYear_str' in out.columns and mask_no_attr.any():
        # Convert values before assignment to avoid dtype warnings
        sex_year_values = out.loc[mask_no_attr, "sexYear_str"].map(
            lambda s: ganshu(s) if isinstance(s, str) and s else None
        )
        # Convert None to NaN for float64 column compatibility
        sex_year_values = sex_year_values.where(sex_year_values.notna(), np.nan).astype('float64')
        out.loc[mask_no_attr, "sex_year"] = sex_year_values
    
    # month - only process string if attribute doesn't exist or is NaN for that row
    def month_to_int(s):
        if not isinstance(s, str) or not s:
            return None
        if s == "正月": return 1
        if s == "臘月": return 13
        if s == "一月": return 14
        # Strip 月 character before converting numerals
        return numcon(s.rstrip('月'))
    
    if 'month' not in out.columns:
        out['month'] = None
    
    mask_no_attr = out['month'].isna()
    
    if 'month_str' in out.columns and mask_no_attr.any():
        out.loc[mask_no_attr, "month"] = out.loc[mask_no_attr, "month_str"].map(month_to_int)

    # day - only process string if attribute doesn't exist or is NaN for that row
    if 'day' not in out.columns:
        out['day'] = None
    
    mask_no_attr = out['day'].isna()
    
    if 'day_str' in out.columns and mask_no_attr.any():
        out.loc[mask_no_attr, "day"] = out.loc[mask_no_attr, "day_str"].map(
            lambda s: numcon(s.rstrip('日')) if isinstance(s, str) and s else None
        )

    # gz (sexagenary day number) - only process string if attribute doesn't exist or is NaN for that row
    if 'gz' not in out.columns:
        out['gz'] = None
    
    mask_no_attr = out['gz'].isna()
    
    if 'gz_str' in out.columns and mask_no_attr.any():
        out.loc[mask_no_attr, "gz"] = out.loc[mask_no_attr, "gz_str"].map(
            lambda s: ganshu(s) if isinstance(s, str) and s else None
        )

    # lp - only process string if attribute doesn't exist or is NaN for that row
    if 'lp' not in out.columns:
        out['lp'] = None
    
    mask_no_attr = out['lp'].isna()
    
    if 'lp_str' in out.columns and mask_no_attr.any():
        out.loc[mask_no_attr, "lp"] = out.loc[mask_no_attr, "lp_str"].map(
            lambda s: LP_DIC.get(s) if isinstance(s, str) else None
        )

    # nmd_gz (next month's day sexagenary number) - only process string if attribute doesn't exist or is NaN for that row
    if 'nmd_gz' not in out.columns:
        out['nmd_gz'] = None
    
    mask_no_attr = out['nmd_gz'].isna()
    
    if 'nmd_gz_str' in out.columns and mask_no_attr.any():
        out.loc[mask_no_attr, "nmd_gz"] = out.loc[mask_no_attr, "nmd_gz_str"].map(
            lambda s: ganshu(s) if isinstance(s, str) and s else None
        )
    
    # intercalary - only process has_int if attribute doesn't exist or is NaN for that row
    if 'intercalary' not in out.columns:
        out['intercalary'] = None
    
    mask_no_attr = out['intercalary'].isna()
    
    if 'has_int' in out.columns and mask_no_attr.any():
        out.loc[mask_no_attr, "intercalary"] = out.loc[mask_no_attr, "has_int"].replace({0: None, 1: 1}).infer_objects(copy=False)
    
    # Normalize date_string: remove all spaces from Chinese text
    if "date_string" in out.columns:
        out["date_string"] = out["date_string"].apply(
            lambda x: str(x).replace(" ", "") if pd.notna(x) and x else ""
        )

    return out


def bulk_resolve_dynasty_ids(df, dyn_tag_df, dyn_df):
    """
    Bulk resolve dynasty string identifiers to dynasty IDs.
    
    Takes a DataFrame with 'dyn_str' column and returns expanded DataFrame
    with 'dyn_id' column(s). Handles:
    - Multiple matches (expands rows)
    - part_of relationships (includes dynasties that have matched dynasty as part_of)
    - Missing/null values (preserved)
    
    :param df: DataFrame with 'dyn_str' column (and 'date_index')
    :param dyn_tag_df: DataFrame with columns ['string', 'dyn_id']
    :param dyn_df: DataFrame with columns ['dyn_id', 'part_of']
    :return: DataFrame with additional 'dyn_id' column(s), expanded for multiple matches
    """
    out = df.copy()
    
    # If no dynasty strings, return as-is
    if 'dyn_str' not in out.columns or out['dyn_str'].notna().sum() == 0:
        return out
    
    # Step 1: Merge with dyn_tag_df to get initial dynasty IDs
    # Use left merge to preserve all rows, even those without matches
    dyn_merge = out[['date_index', 'dyn_str']].dropna(subset=['dyn_str']).merge(
        dyn_tag_df[['string', 'dyn_id']],
        how='left',
        left_on='dyn_str',
        right_on='string',
        suffixes=('', '_tag')
    )
    
    # Drop the temporary 'string' column from merge
    if 'string' in dyn_merge.columns:
        dyn_merge = dyn_merge.drop(columns=['string'])
    
    # Step 2: Handle part_of relationships
    # Find all dyn_ids that matched directly
    matched_dyn_ids = dyn_merge['dyn_id'].dropna().unique()
    
    # Find dynasties that have these matched IDs as their 'part_of'
    # This means if we matched "Tang", we also want "Later Tang" (if part_of = Tang)
    if len(matched_dyn_ids) > 0 and 'part_of' in dyn_df.columns:
        part_of_dyns = dyn_df[dyn_df['part_of'].isin(matched_dyn_ids)][['dyn_id', 'part_of']].copy()
        
        if not part_of_dyns.empty:
            # Create additional rows for part_of relationships
            # For each original match, add rows for dynasties that have it as part_of
            part_of_rows = []
            for _, row in dyn_merge.iterrows():
                if pd.notna(row['dyn_id']):
                    # Find dynasties that have this dyn_id as their part_of
                    related = part_of_dyns[part_of_dyns['part_of'] == row['dyn_id']]
                    if not related.empty:
                        # Create a row for each related dynasty
                        for _, rel_row in related.iterrows():
                            new_row = row.copy()
                            new_row['dyn_id'] = rel_row['dyn_id']
                            part_of_rows.append(new_row)
            
            if part_of_rows:
                part_of_df = pd.DataFrame(part_of_rows)
                # Combine original matches with part_of matches
                dyn_merge = pd.concat([dyn_merge, part_of_df], ignore_index=True)
    
    # Step 3: Also include the part_of values themselves if they're in dyn_df
    # This handles the reverse: if we matched "Later Tang", include "Tang" too
    if len(matched_dyn_ids) > 0 and 'part_of' in dyn_df.columns:
        # Get dyn_ids that matched and find their part_of values
        matched_with_part_of = dyn_df[dyn_df['dyn_id'].isin(matched_dyn_ids) & dyn_df['part_of'].notna()]
        if not matched_with_part_of.empty:
            part_of_values = matched_with_part_of[['dyn_id', 'part_of']].copy()
            # For each matched dynasty with a part_of, add a row with part_of as dyn_id
            part_of_reverse_rows = []
            for _, row in dyn_merge.iterrows():
                if pd.notna(row['dyn_id']):
                    parent_dyns = part_of_values[part_of_values['dyn_id'] == row['dyn_id']]
                    for _, parent_row in parent_dyns.iterrows():
                        if pd.notna(parent_row['part_of']):
                            new_row = row.copy()
                            new_row['dyn_id'] = parent_row['part_of']
                            part_of_reverse_rows.append(new_row)
            
            if part_of_reverse_rows:
                part_of_reverse_df = pd.DataFrame(part_of_reverse_rows)
                dyn_merge = pd.concat([dyn_merge, part_of_reverse_df], ignore_index=True)
    
    # Step 4: Merge back to original DataFrame
    # Remove duplicates that might have been created
    dyn_merge = dyn_merge.drop_duplicates(subset=['date_index', 'dyn_id'])
    
    # Merge with original, expanding rows where multiple matches exist
    # Rows without dyn_str get preserved with NaN dyn_id
    out = out.merge(
        dyn_merge[['date_index', 'dyn_id']],
        how='left',
        on='date_index',
        suffixes=('', '_resolved')
    )
    
    # Prioritize attributes over resolved values
    out = prioritize_resolved_values(out)
    return out


def bulk_resolve_ruler_ids(df, ruler_tag_df):
    """
    Bulk resolve ruler string identifiers to ruler (person) IDs.
    
    Takes a DataFrame with 'ruler_str' column and returns expanded DataFrame
    with 'ruler_id' column. Handles multiple matches (expands rows).
    
    :param df: DataFrame with 'ruler_str' column (and 'date_index')
    :param ruler_tag_df: DataFrame with columns ['string', 'person_id']
    :return: DataFrame with additional 'ruler_id' column, expanded for multiple matches
    """
    out = df.copy()
    
    # If no ruler strings, return as-is
    if 'ruler_str' not in out.columns or out['ruler_str'].notna().sum() == 0:
        return out
    
    # Merge with ruler_tag_df to get person_id (ruler_id)
    # Use left merge to preserve all rows
    ruler_merge = out[['date_index', 'ruler_str']].dropna(subset=['ruler_str']).merge(
        ruler_tag_df[['string', 'person_id']],
        how='left',
        left_on='ruler_str',
        right_on='string',
        suffixes=('', '_tag')
    )
    
    # Drop the temporary 'string' column from merge
    if 'string' in ruler_merge.columns:
        ruler_merge = ruler_merge.drop(columns=['string'])
    
    # Rename person_id to ruler_id for consistency
    ruler_merge = ruler_merge.rename(columns={'person_id': 'ruler_id'})
    
    # Remove duplicates
    ruler_merge = ruler_merge.drop_duplicates(subset=['date_index', 'ruler_id'])
    
    # Merge back to original DataFrame, expanding rows where multiple matches exist
    out = out.merge(
        ruler_merge[['date_index', 'ruler_id']],
        how='left',
        on='date_index',
        suffixes=('', '_resolved')
    )
    
    # Prioritize attributes over resolved values
    out = prioritize_resolved_values(out)
    return out


def bulk_resolve_era_ids(df, era_df):
    """
    Bulk resolve era string identifiers to era IDs.
    
    Takes a DataFrame with 'era_str' column and returns expanded DataFrame
    with 'era_id' column. Handles multiple matches (expands rows for variants).
    
    :param df: DataFrame with 'era_str' column (and 'date_index')
    :param era_df: DataFrame with columns ['era_name', 'era_id', 'ruler_id', 'dyn_id', 
                                          'cal_stream', 'era_start_year', 'era_end_year', 'max_year']
    :return: DataFrame with additional era-related columns, expanded for multiple matches
    """
    out = df.copy()
    
    # Get no-era rulers
    if 'ruler_id' in out.columns:
        bloc = out.copy()
        bloc = bloc[bloc['era_str'].isna()].dropna(subset=['ruler_id', 'year'])
        del bloc['dyn_id']
        bloc = bloc.drop_duplicates()
        
        if not bloc.empty:
            # Isolate the first era of each ruler
            temp = era_df.copy()[[i for i in era_df.columns if i not in ['cal_stream']]].sort_values(by=['era_start_year'])
            temp = temp.drop_duplicates(subset=['ruler_id'])
            # Remove problem cases from main DataFrame
            out = out[~out['date_index'].isin(bloc['date_index'])].copy()
            dfs = []
            for idx in bloc['date_index'].dropna().unique():
                # Isolate date index
                sub_bloc = bloc[bloc['date_index'] == idx].copy()
                # Merge to pick up era_id of ruler's first era
                sub_bloc = sub_bloc.merge(era_df, how='left', on=['ruler_id'])
                sub_bloc['era_str'] = sub_bloc['era_name']
                dfs.append(sub_bloc)
            # Recombine
            dfs = [i for i in dfs if not i.empty]
            out = pd.concat([out] + dfs).sort_values(by=['date_index']).drop_duplicates(subset=['date_index', 'era_id'])
            return out

    # If no era strings, return as-is
    if 'era_str' not in out.columns or out['era_str'].notna().sum() == 0:
        # raise ValueError("No era strings found in DataFrame")
        return out
    
    # Create minimal era mapping with all needed columns
    era_cols = ['era_name', 'era_id', 'ruler_id', 'dyn_id', 'cal_stream', 
                'era_start_year', 'era_end_year']
    if 'max_year' in era_df.columns:
        era_cols.append('max_year')
    
    era_map = era_df[era_cols].drop_duplicates()
    
    # Merge with era_df to get era_id and related columns
    # Use left merge to preserve all rows
    era_merge = out[['date_index', 'era_str']].dropna(subset=['era_str']).merge(
        era_map,
        how='left',
        left_on='era_str',
        right_on='era_name',
        suffixes=('', '_era')
    )
    
    # Drop the temporary 'era_name' column from merge (we keep era_str for reference)
    if 'era_name' in era_merge.columns:
        era_merge = era_merge.drop(columns=['era_name'])
    
    # Remove duplicates
    era_merge = era_merge.drop_duplicates(subset=['date_index', 'era_id'])
    
    # Merge back to original DataFrame, expanding rows where multiple matches exist
    # Merge all era-related columns
    era_cols_to_merge = ['era_id', 'ruler_id', 'dyn_id', 'cal_stream', 
                        'era_start_year', 'era_end_year']
    if 'max_year' in era_merge.columns:
        era_cols_to_merge.append('max_year')
    
    out = out.merge(
        era_merge[['date_index'] + era_cols_to_merge],
        how='left',
        on='date_index',
        suffixes=('', '_resolved')
    )
    
    # Prioritize attributes over resolved values
    out = prioritize_resolved_values(out)
    return out


def bulk_generate_date_candidates(df_with_ids, dyn_df, ruler_df, era_df, master_table, lunar_table, phrase_dic=phrase_dic_en, tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, civ=None, proliferate=False):
    """
    Generate all possible dynasty/ruler/era combinations for each date.
    
    Takes a DataFrame with resolved IDs (from bulk_resolve_* functions) and
    expands it to include all valid combinations of dyn/ruler/era per date_index.
    This creates candidate rows for constraint solving.
    
    Logic:
    - If dynasty specified: filter to that dynasty (including part_of relationships)
    - If ruler specified: filter to that ruler (and its dynasty)
    - If era specified: filter to that era (and its ruler/dynasty)
    - Generate all valid combinations
    - Handle part_of relationships in dynasty table
    
    :param df_with_ids: DataFrame with resolved IDs (dyn_id, ruler_id, era_id columns)
    :param dyn_df: Full dynasty DataFrame with ['dyn_id', 'part_of', 'cal_stream']
    :param ruler_df: Full ruler DataFrame with ['person_id', 'dyn_id', 'emp_start_year', 'emp_end_year', 'max_year']
    :param era_df: Full era DataFrame with ['era_id', 'ruler_id', 'dyn_id', 'cal_stream', 
                                          'era_start_year', 'era_end_year', 'max_year', 'era_name']
    :param master_table: Full master DataFrame
    :param lunar_table: Lunation DataFrame
    :param tpq: int, terminus post quem
    :param taq: int, terminus ante quem
    :param civ: str or list, civilization filter
    :return: Expanded DataFrame with all candidate combinations, with columns:
             date_index, dyn_id, ruler_id, era_id, cal_stream, era_start_year, era_end_year, max_year, etc.
    """
    out = df_with_ids.copy()
    # Defaults
    if civ is None:
        civ = ['c', 'j', 'k']
    
    # We'll build candidate rows per date_index
    all_candidates = []

    for date_idx in out['date_index'].dropna().unique():
        # Get ALL rows for this date_index (not just first one)
        # This is important because bulk_resolve_era_ids can expand one date_index
        # into multiple rows with different era_id values
        # Convert date_idx to match the dtype in out['date_index'] for comparison
        if 'date_index' in out.columns:
            date_idx_for_filter = pd.to_numeric(date_idx, errors='coerce')
            if pd.isna(date_idx_for_filter):
                date_idx_for_filter = date_idx
            out_date_index_numeric = pd.to_numeric(out['date_index'], errors='coerce')
            date_rows = out[out_date_index_numeric == date_idx_for_filter].copy()
        else:
            date_rows = pd.DataFrame()
        
        # Extract all unique combinations of resolved IDs from these rows
        resolved_combinations = []
        for _, row in date_rows.iterrows():
            # Original IDs represent explicit matches from strings
            dyn_id = row.get('dyn_id') if pd.notna(row.get('dyn_id')) else None
            ruler_id = row.get('ruler_id') if pd.notna(row.get('ruler_id')) else None
            era_id = row.get('era_id') if pd.notna(row.get('era_id')) else None

            # Store the combination and source row for later use
            resolved_combinations.append({
                'dyn_id': dyn_id,
                'ruler_id': ruler_id,
                'era_id': era_id,
                'source_row': row
            })
        date_rows['lunar_solution'] = 1
        # Skip if ALL IDs are None (no identifiers specified)
        # Don't generate candidates for every possible era
        all_none = all(
            combo['dyn_id'] is None and 
            combo['ruler_id'] is None and 
            combo['era_id'] is None
            for combo in resolved_combinations
        )
        if all_none:
            if not proliferate:
                first_row = date_rows.iloc[0]
                # Ensure date_index is numeric
                date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
                if pd.isna(date_idx_numeric):
                    date_idx_numeric = date_idx
                candidate_row = {
                    'date_index': date_idx_numeric,
                    'dyn_id': None,
                    'ruler_id': None,
                    'era_id': None,
                }
                for col in out.columns:
                    if col not in candidate_row and col != 'date_index':
                        candidate_row[col] = first_row.get(col)
                all_candidates.append(candidate_row)
            else:  # If proliferate is True
                t_out = date_rows.copy()
                # Copy lunar table
                t_lt = lunar_table.copy()
                
                # Filter by civ
                cal_streams = get_cal_streams_from_civ(civ)
                if cal_streams is not None:
                    t_lt = t_lt[t_lt['cal_stream'].isin(cal_streams)]
                
                # Filter by tpq and taq
                t_lt = t_lt[(t_lt['ind_year'] >= tpq) & (t_lt['ind_year'] <= taq)]
                
                # Clean columns
                cols = ['year_str', 'sexYear_str', 'month_str', 'day_str', 'gz_str', 'lp_str', 'nmd_gz_str']
                cols = [i for i in cols if i in t_out.columns]
                t_out = t_out.drop(columns=cols)
                
                # Merge on month and/or intercalary
                a = t_out.copy().dropna(subset=['intercalary', 'month'], how='any')
                b = t_out[~t_out.index.isin(a.index)].copy().dropna(subset=['month'], how='any')
                c = b.copy().dropna(subset=['intercalary'], how='any')
                b = b[~b.index.isin(c.index)].copy().dropna(subset=['month'], how='any')
                del c['month'], b['intercalary']

                d = a.merge(t_lt, on=['month', 'intercalary'], how='left')
                e = b.merge(t_lt, on=['month'], how='left')
                f = c.merge(t_lt, on=['intercalary'], how='left')
                t_out = pd.concat([d, e, f])
                
                # Separate into those with and without new moon sex. date (nmd_gz_x)
                a = t_out.copy().dropna(subset=['nmd_gz_x'])  # nmd_gz from text
                b = t_out[~t_out.index.isin(a.index)].copy()  # nmd_gz to take from lunar table
                # Filter those with to those matching the lunar table
                a = a[a['nmd_gz_x'] == a['nmd_gz_y']]
                b['nmd_gz_x'] = b['nmd_gz_y']
                t_out = pd.concat([i for i in [a, b] if not i.empty])
                t_out = t_out.drop(columns=['nmd_gz_y'])
                t_out = t_out.rename(columns={'nmd_gz_x': 'nmd_gz'})

                if not t_out.dropna(subset=['lp']).empty:  # If there is a lunar phase constraint
                    # If there is a sexagenary day constraint
                    if not t_out.dropna(subset=['gz']).empty:
                        if t_out['lp'].iloc[0] == -1:  # 晦
                            t_out = t_out[t_out['gz'] == t_out['hui_gz']]
                        else:  # 朔
                            t_out = t_out[t_out['gz'] == t_out['nmd_gz']]
                    
                    # Add day column
                    if t_out['lp'].iloc[0] == -1:  # 晦
                        t_out['day'] = t_out['max_day']
                    else:  # 朔
                        t_out['day'] = 1
                
                else:  # If there is no lunar phase constraint
                    if not t_out.dropna(subset=['gz']).empty:  # If there is a sexagenary day constraint
                        t_out['_day'] = ((t_out['gz'] - t_out['nmd_gz']) % 60) + 1
                        if t_out.dropna(subset=['day']).empty:  # If there is no numeric day constraint
                            t_out['day'] = t_out['_day']
                        else:  # If there is a numeric day constraint
                            # Filter 
                            t_out = t_out[t_out['day'] == t_out['_day']]
                    if not t_out.dropna(subset=['day']).empty:  # If there is a numeric day constraint
                        t_out = t_out[t_out['day'] <= t_out['max_day']]
                
                # Clean columns
                cols = ['max_day', 'hui_gz']
                t_out = t_out.drop(columns=cols)
                
                # Filter master table
                temp = master_table.copy()
                temp = temp[(temp['era_end_year'] >= tpq) & (temp['era_start_year'] <= taq)]
                # Merge with master table
                t_out = t_out.merge(temp, on=['cal_stream'], how='left')
                
                # Filter by lunar table ind_year
                t_out = t_out[
                    (t_out['nmd_jdn'] >= t_out['era_start_jdn']) &
                    (t_out['hui_jdn'] <= t_out['era_end_jdn'])
                ]
                
                # Filter by year
                if not t_out.dropna(subset=['year']).empty:
                    t_out['_ind_year'] = t_out['year'] + t_out['era_start_year'] - 1
                    t_out = t_out[t_out['_ind_year'] == t_out['ind_year']]
                    
                    if t_out.empty:
                        # Ensure date_index is numeric
                        date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
                        if pd.isna(date_idx_numeric):
                            date_idx_numeric = date_idx
                        date_rows['date_index'] = date_idx_numeric
                        if 'error_str' not in date_rows.columns:
                            date_rows['error_str'] = ""
                        date_rows['error_str'] += phrase_dic['year-lun-mismatch']
                        all_candidates.extend(date_rows.to_dict('records'))
                        continue
                else:
                    t_out['year'] = t_out['ind_year'] - t_out['era_start_year'] + 1
                
                # Filter by sexagenary year
                if not t_out.dropna(subset=['sex_year']).empty:
                    t_out = t_out[t_out['sex_year'] == t_out['year_gz']]
                    if t_out.empty:
                        # Ensure date_index is numeric
                        date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
                        if pd.isna(date_idx_numeric):
                            date_idx_numeric = date_idx
                        date_rows['date_index'] = date_idx_numeric
                        if 'error_str' not in date_rows.columns:
                            date_rows['error_str'] = ""
                        date_rows['error_str'] += phrase_dic['year-sex-mismatch']
                        all_candidates.extend(date_rows.to_dict('records'))
                        continue
                
                date_rows = t_out
                
                # Clean columns
                cols = ['_ind_year']  #
                cols = [i for i in cols if i in t_out.columns]
                date_rows = date_rows.drop(columns=cols)

                # Add marker to disable lunar solution processing
                date_rows['lunar_solution'] = 0
                
                # Ensure date_index is numeric
                date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
                if pd.isna(date_idx_numeric):
                    date_idx_numeric = date_idx
                date_rows['date_index'] = date_idx_numeric

                all_candidates.extend(date_rows.to_dict('records'))
        
            continue

            
        # Filter these combinations against the loaded tables to find valid ones
        valid_candidates = []
        seen_combinations = set()
        
        for combo in resolved_combinations:
            # Skip combinations with no IDs
            if (combo['dyn_id'] is None and
                combo['ruler_id'] is None and
                combo['era_id'] is None):
                continue

            # Special case: dynasty specified but no ruler/era - use dynasty's reign period
            if (combo['dyn_id'] is not None and
                combo['ruler_id'] is None and
                combo['era_id'] is None):
                # Find dynasty info - pandas handles int/float comparison automatically
                # But ensure we're comparing like types by converting both sides
                dyn_id_val = combo['dyn_id']
                if pd.notna(dyn_id_val):
                    # Convert to float for consistent comparison (handles both int and float input)
                    dyn_id_val = float(dyn_id_val)
                    
                    # Compare: convert dyn_df['dyn_id'] to float for comparison (NaN-safe)
                    dyn_df_numeric = pd.to_numeric(dyn_df['dyn_id'], errors='coerce')
                    dyn_info = dyn_df[dyn_df_numeric == dyn_id_val]
                    
                    if not dyn_info.empty:
                        dyn_row = dyn_info.iloc[0]
                        # Create candidate using dynasty's reign period
                        # Use .get() to safely handle missing columns or NaN values
                        # Ensure date_index is numeric for consistent comparison
                        date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
                        if pd.isna(date_idx_numeric):
                            date_idx_numeric = date_idx
                        candidate_row = {
                            'date_index': date_idx_numeric,
                            'dyn_id': dyn_id_val,  # Store as float for consistency
                            'ruler_id': None,  # No specific ruler
                            'era_id': None,  # No specific era
                            'cal_stream': dyn_row.get('cal_stream'),
                            'era_start_year': dyn_row.get('dyn_start_year'),
                            'era_end_year': dyn_row.get('dyn_end_year'),
                            'max_year': None,  # Dynasty doesn't have max_year
                            'era_name': None,  # No era name for dynasty-only
                        }
                        # Copy ALL date fields to preserve month, intercalary, day, etc.
                        # But don't overwrite dyn_id, ruler_id, era_id we just set
                        protected_cols = {'dyn_id', 'ruler_id', 'era_id', 'date_index'}
                        for col in date_rows.columns:
                            if col not in candidate_row and col not in protected_cols:
                                candidate_row[col] = combo['source_row'].get(col)
                                all_candidates.append(candidate_row)
                continue  # Skip the normal era-based logic

            # Special case: ruler specified but no era - use ruler's reign period
            if (combo['ruler_id'] is not None and
                combo['era_id'] is None):
                # Find ruler info - convert to same type for comparison
                ruler_id_val = int(combo['ruler_id']) if pd.notna(combo['ruler_id']) else None
                if ruler_id_val is not None:
                    # Ensure ruler_df['person_id'] is comparable (convert to int if needed)
                    ruler_info = ruler_df[ruler_df['person_id'].astype(int) == ruler_id_val]
                    if not ruler_info.empty:
                        ruler_row = ruler_info.iloc[0]

                        # When both dynasty and ruler are specified, filter by dynasty
                        # If combo has a dyn_id that doesn't match the ruler's actual dynasty, skip this ruler
                        if combo['dyn_id'] is not None and pd.notna(ruler_row.get('dyn_id')):
                            if int(combo['dyn_id']) != int(ruler_row['dyn_id']):
                                # Dynasty mismatch: skip this ruler (don't include in candidates)
                                continue

                        # Create candidate using ruler's reign period
                        # Ensure date_index is numeric for consistent comparison
                        date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
                        if pd.isna(date_idx_numeric):
                            date_idx_numeric = date_idx
                        candidate_row = {
                            'date_index': date_idx_numeric,
                            'dyn_id': ruler_row['dyn_id'],  # Use ruler's actual dynasty
                            'ruler_id': ruler_id_val,
                            'era_id': None,  # No specific era
                            'cal_stream': ruler_row.get('cal_stream'),
                            'era_start_year': ruler_row.get('emp_start_year'),
                            'era_end_year': ruler_row.get('emp_end_year'),
                            'max_year': ruler_row.get('max_year'),
                            'era_name': None,  # No era name for ruler-only
                        }
                        # Copy ALL date fields to preserve month, intercalary, day, etc.
                        # But don't overwrite dyn_id, ruler_id, era_id we just set
                        protected_cols = {'dyn_id', 'ruler_id', 'era_id', 'date_index'}
                        for col in date_rows.columns:
                            if col not in candidate_row and col not in protected_cols:
                                candidate_row[col] = combo['source_row'].get(col)
                        all_candidates.append(candidate_row)
                continue  # Skip the normal era-based logic

            # Build filter for era_df based on this combination
            era_filter = era_df.copy()
            
            # Filter by era_id if specified
            if combo['era_id'] is not None:
                era_filter = era_filter[era_filter['era_id'] == combo['era_id']]
                
                # When both dynasty/ruler and era are specified, filter by both
                # If the era doesn't match the specified dynasty/ruler, it will be filtered out
                if not era_filter.empty:
                    # Filter by ruler_id if specified
                    if combo['ruler_id'] is not None:
                        era_filter = era_filter[era_filter['ruler_id'] == combo['ruler_id']]
                    
                    # Filter by dyn_id if specified (with part_of relationships)
                    if combo['dyn_id'] is not None:
                        # Handle part_of relationships for dynasty
                        matched_dyn_ids = [combo['dyn_id']]
                        if 'part_of' in dyn_df.columns:
                            # Find dynasties that have this as part_of
                            part_of_dyns = dyn_df[dyn_df['part_of'] == combo['dyn_id']]['dyn_id'].tolist()
                            matched_dyn_ids.extend(part_of_dyns)
                            # Also include the part_of value if it exists
                            part_of_value = dyn_df[dyn_df['dyn_id'] == combo['dyn_id']]['part_of'].values
                            if len(part_of_value) > 0 and pd.notna(part_of_value[0]):
                                matched_dyn_ids.append(part_of_value[0])
                            matched_dyn_ids = list(set(matched_dyn_ids))  # Remove duplicates
                        era_filter = era_filter[era_filter['dyn_id'].isin(matched_dyn_ids)]
            else:
                # No era_id specified, apply normal filtering logic
                # Filter by ruler_id if specified (this enforces that era belongs to this ruler)
                if combo['ruler_id'] is not None:
                    era_filter = era_filter[era_filter['ruler_id'] == combo['ruler_id']]
                
                # Filter by dyn_id if specified (with part_of relationships)
                if combo['dyn_id'] is not None:
                    # Handle part_of relationships for dynasty
                    matched_dyn_ids = [combo['dyn_id']]
                    if 'part_of' in dyn_df.columns:
                        # Find dynasties that have this as part_of
                        part_of_dyns = dyn_df[dyn_df['part_of'] == combo['dyn_id']]['dyn_id'].tolist()
                        matched_dyn_ids.extend(part_of_dyns)
                        # Also include the part_of value if it exists
                        part_of_value = dyn_df[dyn_df['dyn_id'] == combo['dyn_id']]['part_of'].values
                        if len(part_of_value) > 0 and pd.notna(part_of_value[0]):
                            matched_dyn_ids.append(part_of_value[0])
                        matched_dyn_ids = list(set(matched_dyn_ids))  # Remove duplicates
                    era_filter = era_filter[era_filter['dyn_id'].isin(matched_dyn_ids)]
            
            # If we have valid era matches, use them
            # The filter ensures that if multiple IDs are specified, they must all match together
            if not era_filter.empty:
                for _, era_row in era_filter.iterrows():
                    # Create a unique key for this combination to avoid duplicates
                    combo_key = (
                        era_row['era_id'],
                        era_row['ruler_id'],
                        era_row['dyn_id']
                    )
                    
                    if combo_key not in seen_combinations:
                        seen_combinations.add(combo_key)
                        
                        # Create candidate row with validated IDs from era_df
                        # Ensure date_index is numeric
                        date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
                        if pd.isna(date_idx_numeric):
                            date_idx_numeric = date_idx
                        candidate_row = {
                            'date_index': date_idx_numeric,
                            'era_id': era_row['era_id'],
                            'ruler_id': era_row['ruler_id'],
                            'dyn_id': era_row['dyn_id'],
                            'cal_stream': era_row.get('cal_stream'),
                            'era_start_year': era_row.get('era_start_year'),
                            'era_end_year': era_row.get('era_end_year'),
                            'max_year': era_row.get('max_year'),
                            'era_name': era_row.get('era_name'),
                        }
                        
                        # Copy ALL other date fields from the source row (month, intercalary, day, etc.)
                        source_row = combo['source_row']
                        for col in out.columns:
                            if col not in candidate_row and col != 'date_index':
                                candidate_row[col] = source_row.get(col)
                        
                        valid_candidates.append(candidate_row)
        
        # If no valid candidates found, create one row with empty IDs
        # but preserve all date information (month, day, etc.)
        if not valid_candidates:
            first_row = date_rows.iloc[0]
            # Ensure date_index is numeric
            date_idx_numeric = pd.to_numeric(date_idx, errors='coerce')
            if pd.isna(date_idx_numeric):
                date_idx_numeric = date_idx
            candidate_row = {
                'date_index': date_idx_numeric,
                'dyn_id': None,
                'ruler_id': None,
                'era_id': None,
            }
            # Copy ALL date fields to preserve month, intercalary, day, etc.
            for col in out.columns:
                if col not in candidate_row and col != 'date_index':
                    candidate_row[col] = first_row.get(col)
            valid_candidates.append(candidate_row)
        
        all_candidates.extend(valid_candidates)

    # Convert to DataFrame
    if all_candidates:
        candidates_df = pd.DataFrame(all_candidates)
        # Ensure consistent NaN values for missing IDs
        for col in ['dyn_id', 'ruler_id', 'era_id', 'max_year']:
            if col in candidates_df.columns:
                candidates_df[col] = candidates_df[col].astype('float64')
    else:
        # Return empty DataFrame with expected columns
        candidates_df = df_with_ids.copy()
    
    # # Ensure cal_stream is set (default to 1 if missing)
    # # Commented out - problem is solved elsewhere
    # if 'cal_stream' in candidates_df.columns:
    #     candidates_df['cal_stream'] = candidates_df['cal_stream'].fillna(1.0)
    # else:
    #     candidates_df['cal_stream'] = 1.0

    cols = ['dyn_str', 'ruler_str', 'era_str', 'year_str', 'sexYear_str', 'month_str', 'day_str', 'gz_str', 'lp_str', 'nmd_gz_str', 'year_gz']
    cols = [i for i in cols if i in candidates_df.columns]
    candidates_df = candidates_df.drop(columns=cols)
    
    # Stop-gap for problem I don't understand
    bu = candidates_df.copy()
    if 'dyn_id' in candidates_df.columns:
        candidates_df = candidates_df.dropna(subset=['dyn_id'])
        if candidates_df.empty:
            candidates_df = bu.copy()
    
    return candidates_df.drop_duplicates().reset_index(drop=True)


def add_can_names_bulk(table, ruler_can_names, dyn_df, era_df=None):
    """
    Add canonical names (dyn_name, ruler_name, era_name) to candidate DataFrame.
    
    :param table: DataFrame with ruler_id, dyn_id, and/or era_id columns
    :param ruler_can_names: DataFrame with ['person_id', 'string'] columns
    :param dyn_df: DataFrame with ['dyn_id', 'dyn_name'] columns
    :param era_df: Optional DataFrame with ['era_id', 'era_name'] columns
    :return: DataFrame with added 'ruler_name', 'dyn_name', and 'era_name' columns
    """
    out = table.copy()
    
    # Add ruler names
    if 'ruler_id' in out.columns:
        ruler_map = ruler_can_names.rename(columns={'person_id': 'ruler_id', 'string': 'ruler_name'})
        out = out.merge(ruler_map[['ruler_id', 'ruler_name']], how='left', on='ruler_id')
    else:
        out['ruler_name'] = None
    
    # Add dynasty names
    if 'dyn_id' in out.columns:
        dyn_map = dyn_df[['dyn_id', 'dyn_name']].drop_duplicates()
        out = out.merge(dyn_map, how='left', on='dyn_id')
    else:
        out['dyn_name'] = None
    
    # Add era names
    if era_df is not None and 'era_id' in out.columns:
        era_map = era_df[['era_id', 'era_name']].drop_duplicates()
        out = out.merge(era_map, how='left', on='era_id')
    else:
        out['era_name'] = None
    
    return out


def extract_date_table_bulk(
    xml_root, implied=None, pg=False, gs=None, lang='en', tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, civ=None, tables=None, 
    sequential=True, proliferate=False, attributes=False, post_normalisation_func=None):
    """
    Optimized bulk version of extract_date_table using pandas operations.
    
    This function replaces the iterative interpret_date() approach with:
    1. Bulk ID resolution (all dates at once)
    2. Bulk candidate generation (all combinations at once)
    3. Sequential constraint solving per date (preserving implied state)
    
    :param xml_root: ElementTree element, XML root containing date elements
    :param implied: Optional dict, implied state for sequential processing. If None, will be initialized with defaults
    :param pg: bool, proleptic gregorian flag
    :param gs: list, gregorian start date [YYYY, MM, DD]
    :param lang: str, language ('en' or 'fr')
    :param tpq: int, terminus post quem
    :param taq: int, terminus ante quem
    :param civ: str or list, civilization filter
    :param tables: Optional pre-loaded tables tuple. If None, will load via prepare_tables().
                   Should be tuple: (era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names)
    :param sequential: bool, intelligently forward fills missing date elements from previous Sinitic date string
    :param proliferate: bool, finds all candidates for date strings without dynasty, ruler, or era
    :param attributes: bool, if True, extract attributes from <date> elements when df is None
    :return: tuple (xml_string, output_df, implied) - same format as extract_date_table()
    """
    # Defaults
    gs, civ = normalize_defaults(gs, civ)
    
    # DPM: set in new inner scope
    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    
    if implied is None:
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

    # Handle both string and Element inputs
    if isinstance(xml_root, str):
        xml_root = et.fromstring(xml_root)
    
    # Step 1: Extract table  DPM: Moved to outer scope
    df = dates_xml_to_df(xml_root, attributes=attributes)

    df['lunar_solution'] = 1
    
    if df.empty:
        output_df = df
    else:
        # Step 2: Normalize date fields (convert strings to numbers)  DPM: ready for outer scope
        df = normalise_date_fields(df)

        # Save copy before resolution to check which IDs were explicit attributes vs resolved from strings
        df_before_resolution = df.copy()
        
        # Step 4: Load all tables once (or use provided tables)  
        if tables is None:
            tables = prepare_tables(civ=civ)
        era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = tables
        master_table = era_df[['cal_stream', 'dyn_id', 'ruler_id', 'era_id', 'era_start_year', 'era_end_year', 'era_start_jdn', 'era_end_jdn']].copy()
        
        # Step 5: Bulk resolve IDs (Phase 1)
        df = bulk_resolve_dynasty_ids(df, dyn_tag_df, dyn_df)
        df = bulk_resolve_ruler_ids(df, ruler_tag_df)
        df = bulk_resolve_era_ids(df, era_df)
        
        # Save copy after ID resolution but before post_normalisation_func
        df_after_resolution = df.copy()
        
        # Step 3: Post-normalisation function
        # Save date_indices BEFORE post_normalisation_func (in case it filters rows)
        # Ensure date_indices are numeric for consistent comparison later
        date_indices_raw = df['date_index'].dropna().unique()
        all_date_indices = sorted([pd.to_numeric(x, errors='coerce') if not isinstance(x, (int, float, np.integer, np.floating)) else x 
                                   for x in date_indices_raw], 
                                  key=lambda x: float(x) if pd.notna(x) else 0)
        # Remove any NaN values that resulted from failed conversions
        all_date_indices = [x for x in all_date_indices if pd.notna(x)]
        if post_normalisation_func is not None:
            df = post_normalisation_func(df)
        
        # Step 6: Bulk generate candidates (Phase 2)
        df_candidates = bulk_generate_date_candidates(df, dyn_df, ruler_df, era_df, master_table, lunar_table, phrase_dic=phrase_dic_en, tpq=tpq, taq=taq, civ=civ, proliferate=proliferate)
        df_candidates['error_str'] = ""
        
        #############################################################################
        all_results = []
        
        # Track previous date's results to check if it had multiple solved options
        prev_date_idx = None
        prev_date_results = None
        
        # Group by date_index and process sequentially [sex_year is fine at this point]
        for date_idx in all_date_indices:
            # Reset implied state for each date if not sequential
            
            # Check if previous date had multiple solved results - if so, reset implied state
            # because we can't reliably carry forward ambiguous information
            if sequential and prev_date_idx is not None and prev_date_results is not None:
                if len(prev_date_results) > 1:
                    # Previous date had multiple options after solving - reset implied state
                    # Clear all implied values to avoid carrying forward ambiguous context
                    implied['cal_stream_ls'] = []
                    implied['dyn_id_ls'] = []
                    implied['ruler_id_ls'] = []
                    implied['era_id_ls'] = []
                    implied['year'] = None
                    implied['month'] = None
                    implied['intercalary'] = None
                    implied['sex_year'] = None
            
            # Get original row from df_before_resolution to check for explicit attributes
            # (before string resolution, so we can distinguish attributes from resolved values)
            # Convert date_idx for comparison (handle type mismatch)
            if 'date_index' in df_before_resolution.columns:
                date_idx_for_compare = pd.to_numeric(date_idx, errors='coerce')
                if pd.isna(date_idx_for_compare):
                    date_idx_for_compare = date_idx
                original_rows_before = df_before_resolution[pd.to_numeric(df_before_resolution['date_index'], errors='coerce') == date_idx_for_compare]
            else:
                original_rows_before = pd.DataFrame()
            if original_rows_before.empty:
                continue
            original_row_before = original_rows_before.iloc[0]
            
            # Get row from df_after_resolution (after ID resolution, before post_normalisation_func)
            # This ensures we have the data even if post_normalisation_func filtered rows
            # Convert date_idx for comparison (handle type mismatch)
            if 'date_index' in df_after_resolution.columns:
                date_idx_for_compare = pd.to_numeric(date_idx, errors='coerce')
                if pd.isna(date_idx_for_compare):
                    date_idx_for_compare = date_idx
                original_rows = df_after_resolution[pd.to_numeric(df_after_resolution['date_index'], errors='coerce') == date_idx_for_compare]
            else:
                original_rows = pd.DataFrame()
            if original_rows.empty:
                continue
            original_row = original_rows.iloc[0]
            
            # Check if an era is explicitly specified via ATTRIBUTE (not via string resolution)
            # Only reset implied state when era_id is an explicit attribute
            # When era_str resolves to multiple eras, let candidate generation filter them
            has_explicit_era, explicit_era_id = check_explicit_attribute(original_row_before, 'era_id')
            
            # If era is explicitly specified, reset implied state to match that era's context
            if sequential and has_explicit_era and explicit_era_id is not None:
                reset_implied_state_for_era(implied, explicit_era_id, era_df)
            
            # Check if a dynasty is explicitly specified via ATTRIBUTE (not via string resolution)
            # When a dynasty is explicitly specified, it should reset implied cal_stream, dyn_id
            # (era is most specific, then ruler, then dynasty - check in order)
            has_explicit_dynasty = False
            explicit_dyn_id = None
            if not has_explicit_era:  # Only check if no explicit era (era takes precedence)
                has_explicit_dynasty, explicit_dyn_id = check_explicit_attribute(original_row_before, 'dyn_id')
            
            # Check if a ruler is explicitly specified via ATTRIBUTE (not via string resolution)
            # When a ruler is explicitly specified, it should reset implied cal_stream, dyn_id, ruler_id
            has_explicit_ruler = False
            explicit_ruler_id = None
            if not has_explicit_era:  # Only check if no explicit era (era takes precedence)
                has_explicit_ruler, explicit_ruler_id = check_explicit_attribute(original_row_before, 'ruler_id')
            
            # Reset implied state based on explicit specifications (ruler > dynasty in specificity)
            if sequential:
                if has_explicit_ruler and explicit_ruler_id is not None:
                    reset_implied_state_for_ruler(implied, explicit_ruler_id, ruler_df)
                elif has_explicit_dynasty and explicit_dyn_id is not None:
                    reset_implied_state_for_dynasty(implied, explicit_dyn_id, dyn_df)

            # Convert date_idx to match df_candidates['date_index'] dtype for proper comparison
            # This handles cases where date_idx is a string but date_index column is numeric
            if not df_candidates.empty and 'date_index' in df_candidates.columns:
                # Convert date_idx to numeric to match the column dtype
                date_idx_converted = pd.to_numeric(date_idx, errors='coerce')
                if pd.isna(date_idx_converted):
                    # If conversion fails, try direct comparison (fallback)
                    date_idx_converted = date_idx
                comparison_result = df_candidates['date_index'] == date_idx_converted
                g = df_candidates[comparison_result].copy()
            else:
                g = df_candidates[df_candidates['date_index'] == date_idx].copy()
            no_candidates_generated = False

            if g.empty:
                # If no candidates were generated, create a fallback row from original df TODO verify this
                if not original_rows.empty:
                    g = original_rows.iloc[[0]].copy()
                    if 'error_str' not in g.columns:
                        g['error_str'] = ""
                    phrase_dic = phrase_dic_fr if lang == 'fr' else phrase_dic_en
                    g['error_str'] += phrase_dic.get('no-candidates', 'No candidates generated; ')
                    no_candidates_generated = True
                else:
                    continue
            
            # Determine what constraints this date has
            has_year = g['year'].notna().any() if 'year' in g.columns else False
            has_sex_year = g['sex_year'].notna().any() if 'sex_year' in g.columns else False
            has_month = g['month'].notna().any() and not g['month'].isna().all() if 'month' in g.columns else False
            has_day = g['day'].notna().any() and not g['day'].isna().all() if 'day' in g.columns else False
            has_gz = g['gz'].notna().any() and not g['gz'].isna().all() if 'gz' in g.columns else False
            has_lp = g['lp'].notna().any() and not g['lp'].isna().all() if 'lp' in g.columns else False
            has_nmd_gz = g['nmd_gz'].notna().any() and not g['nmd_gz'].isna().all() if 'nmd_gz' in g.columns else False
            has_intercalary = g[g['has_int'] == 1].shape[0] == g.shape[0] if 'has_int' in g.columns else False
            
            # Apply implied values to incomplete candidates
            no_year = not (has_year or has_sex_year)
            no_month = not (has_month or has_intercalary)
            no_day = not (has_day or has_gz or has_lp or has_nmd_gz)
            
            if 'era_id' in g.columns:
                no_era = g.dropna(subset=['era_id']).empty
            else:
                no_era = True
            
            if sequential:
                if no_year:  # No year but some sort of day
                    if not no_month or not no_day:
                        # Pick up year and everything higher from implied
                        if (implied.get('cal_stream_ls') and len(implied['cal_stream_ls']) == 1 and ('cal_stream' not in g.columns or g['cal_stream'].isna().all())):
                            g['cal_stream'] = implied['cal_stream_ls'][0]
                        if (implied.get('dyn_id_ls') and len(implied['dyn_id_ls']) == 1 and ('dyn_id' not in g.columns or g['dyn_id'].isna().all())):
                            g['dyn_id'] = implied['dyn_id_ls'][0]
                        if (implied.get('ruler_id_ls') and len(implied['ruler_id_ls']) == 1 and ('ruler_id' not in g.columns or g['ruler_id'].isna().all())):
                            g['ruler_id'] = implied['ruler_id_ls'][0]
                        if (implied.get('era_id_ls') and len(implied['era_id_ls']) == 1 and ('era_id' not in g.columns or g['era_id'].isna().all())):
                            g['era_id'] = implied['era_id_ls'][0]
                            bloc = era_df[era_df['era_id'] == g['era_id'].values[0]]
                            g['era_start_year'] = bloc['era_start_year'].values[0]
                        if implied.get('year') is not None and ('year' not in g.columns or g['year'].isna().all()):
                            g['year'] = implied['year']
                        if implied.get('sex_year') is not None and ('sex_year' not in g.columns or g['sex_year'].isna().all()):
                            g['sex_year'] = implied['sex_year']
                        has_year = True
                    # If there is no month, pick that up
                    if no_month and not no_day:
                        if implied.get('month') is not None and ('month' not in g.columns or g['month'].isna().all()):
                            g['month'] = implied['month']
                        if implied.get('intercalary') is not None and ('intercalary' not in g.columns or g['intercalary'].isna().all()):
                            g['intercalary'] = implied['intercalary']
                        has_month = True
                """
                # NOTE: These implied values are applied elsewhere. Adding this here is a mistake.
                elif no_era and len(implied['era_id_ls']) == 1:
                    era_id = implied['era_id_ls'][0]
                    bloc = era_df[era_df['era_id'] == g['era_id'].values[0]]
                    g['cal_stream'] = bloc['cal_stream'].values[0]
                    g['dyn_id'] = bloc['dyn_id'].values[0]
                    g['ruler_id'] = bloc['ruler_id'].values[0]
                    g['era_id'] = era_id
                    g['era_start_year'] = bloc['era_start_year'].values[0]
                """

            # Check if we have sufficient context for dates with year/month/day constraints
            # If date has temporal constraints but no era/dynasty/ruler context, report insufficient information
            has_temporal_constraints = has_year or has_sex_year or has_month or has_day or has_gz or has_lp or has_nmd_gz
            has_context = False
            
            if has_temporal_constraints and no_candidates_generated:
                # Check if we have era/dynasty/ruler context (either explicit or from implied, after applying implied)
                has_era = ('era_id' in g.columns and g['era_id'].notna().any()) or (implied.get('era_id_ls') and len(implied['era_id_ls']) > 0)
                has_dyn = ('dyn_id' in g.columns and g['dyn_id'].notna().any()) or (implied.get('dyn_id_ls') and len(implied['dyn_id_ls']) > 0)
                has_ruler = ('ruler_id' in g.columns and g['ruler_id'].notna().any()) or (implied.get('ruler_id_ls') and len(implied['ruler_id_ls']) > 0)
                has_context = has_era or has_dyn or has_ruler
                
                # If we have temporal constraints but no context and no candidates were generated
                if not has_context:
                    # Replace "no candidates" error with "insufficient information"
                    g['error_str'] = phrase_dic.get('insufficient-information', 'Insufficient information; ')
                    # Skip solving - just return the error row
                    result_df = g.copy()
                    result_df['date_index'] = date_idx
                    result_df['date_string'] = g.iloc[0].get('date_string', '') if not g.empty else 'unknown'
                    all_results.append(result_df)
                    prev_date_results = result_df
                    prev_date_idx = date_idx
                    continue
            
            # Determine date type
            is_simple = not has_year and not has_sex_year and not has_month and not has_day and not has_gz and not has_lp and not has_nmd_gz
            # Solve based on date type
            if is_simple:
                # Simple date (dynasty/era only)
                result_df, implied = solve_date_simple(
                    g, implied, phrase_dic, tpq, taq
                )
            elif has_month or has_day or has_gz or has_lp or has_nmd_gz:
                # Date with lunar constraints
                # First handle year if present            
                if has_year or has_sex_year:
                    g, implied = solve_date_with_year(
                        g, implied, era_df, phrase_dic, tpq, taq,
                        has_month, has_day, has_gz, has_lp
                    )
                
                # Separate into those needing lunar solution and those not needing lunar solution
                g_a = g[g['lunar_solution'] == 1].copy()
                result_df_a = pd.DataFrame()
                result_df_b = g[g['lunar_solution'] == 0].copy()
                if not g_a.empty:
                    # Apply lunar constraints to the candidates (whether year was solved or not)
                    month_val = g_a.iloc[0].get('month') if has_month and pd.notna(g_a.iloc[0].get('month')) else None
                    day_val = g_a.iloc[0].get('day') if has_day and pd.notna(g_a.iloc[0].get('day')) else None
                    gz_val = g_a.iloc[0].get('gz') if has_gz and pd.notna(g_a.iloc[0].get('gz')) else None
                    lp_val = g_a.iloc[0].get('lp') if has_lp and pd.notna(g_a.iloc[0].get('lp')) else None
                    nmd_gz_val = g_a.iloc[0].get('nmd_gz') if has_nmd_gz and pd.notna(g_a.iloc[0].get('nmd_gz')) else None
                    intercalary_val = 1 if has_intercalary else None

                    result_df_a, implied = solve_date_with_lunar_constraints(
                        g_a, implied, lunar_table, phrase_dic,
                        month=month_val, day=day_val, gz=gz_val, lp=lp_val, nmd_gz=nmd_gz_val, intercalary=intercalary_val,
                        tpq=tpq, taq=taq, pg=pg, gs=gs
                    )
                # Add JDN and ISO dates to proliferate candidates
                if not result_df_b.empty:
                    result_df_b = add_jdn_and_iso_to_proliferate_candidates(result_df_b, pg=pg, gs=gs)
                to_concat = [i for i in [result_df_a, result_df_b] if not i.empty]
                
                # If lunar constraints resulted in no matches (likely due to corruption),
                # use the original input dataframe instead of empty
                if len(to_concat) == 0:
                    result_df = g.copy()
                    phrase_dic = phrase_dic_fr if lang == 'fr' else phrase_dic_en
                    result_df['error_str'] += phrase_dic.get('lunar-constraint-failed', 'Lunar constraint solving failed; ')
                else:
                    result_df = pd.concat(to_concat)
                    # Add metadata to result_df if not empty
                    if 'cal_stream' in result_df.columns and 'ind_year' in result_df.columns:
                        result_df = result_df.sort_values(by=['cal_stream', 'ind_year'])
                del g_a, result_df_a, result_df_b
                    
            else:
                # Year-only date (no month/day constraints)
                result_df, implied = solve_date_with_year(
                    g, implied, era_df, phrase_dic, tpq, taq,
                    False, False, False, False
                )
                # If year-only date solving resulted in no matches, return original candidates
                if result_df.empty:
                    result_df = g.copy()
                    phrase_dic = phrase_dic_fr if lang == 'fr' else phrase_dic_en
                    result_df['error_str'] += phrase_dic.get('year-solving-failed', 'Year resolution failed; ')
            
            # Add date_index and date_string to result
            # Ensure we always include the date, even if solving failed
            if result_df.empty:
                # If solving completely failed, create a fallback row from original candidates
                result_df = g.iloc[[0]].copy() if not g.empty else pd.DataFrame()
                if not result_df.empty:
                    # Preserve present_elements if it exists
                    if 'present_elements' not in result_df.columns and 'present_elements' in g.columns:
                        present_elements_val = g.iloc[0].get('present_elements', '')
                        if pd.notna(present_elements_val):
                            result_df['present_elements'] = present_elements_val
                    if 'error_str' not in result_df.columns:
                        result_df['error_str'] = ""
                    phrase_dic = phrase_dic_fr if lang == 'fr' else phrase_dic_en
                    result_df['error_str'] += phrase_dic.get('solving-failed', 'Date solving failed; ')
            
            if not result_df.empty:
                # Clear preliminary errors if date was successfully resolved
                result_df = clear_preliminary_errors(result_df)
                
                # Preserve metadata columns from original candidates
                result_df['date_index'] = date_idx
                result_df['date_string'] = g.iloc[0].get('date_string', '') if not g.empty else 'unknown'
                # Preserve present_elements from original candidates if it exists
                # (solving functions may not preserve this column)
                if 'present_elements' in g.columns and not g.empty:
                    present_elements_val = g.iloc[0].get('present_elements', '')
                    if pd.notna(present_elements_val) and present_elements_val != '':
                        # Copy to all rows in result_df (in case solving expanded to multiple rows)
                        result_df['present_elements'] = present_elements_val
                
                all_results.append(result_df)
                # Store this date's results for next iteration
                prev_date_results = result_df
            elif not g.empty:
                # Last resort: create a minimal row from the first candidate to ensure date is not lost
                fallback_row = g.iloc[[0]].copy()
                fallback_row['date_index'] = date_idx
                fallback_row['date_string'] = g.iloc[0].get('date_string', '') if not g.empty else 'unknown'
                # Preserve present_elements if it exists
                if 'present_elements' not in fallback_row.columns and 'present_elements' in g.columns:
                    present_elements_val = g.iloc[0].get('present_elements', '')
                    if pd.notna(present_elements_val):
                        fallback_row['present_elements'] = present_elements_val
                if 'error_str' not in fallback_row.columns:
                    fallback_row['error_str'] = ""
                phrase_dic = phrase_dic_fr if lang == 'fr' else phrase_dic_en
                fallback_row['error_str'] += phrase_dic.get('solving-failed', 'Date solving failed; ')
                all_results.append(fallback_row)
                # Store this date's results for next iteration (single row fallback)
                prev_date_results = fallback_row
            else:
                # No results - clear previous results
                prev_date_results = None
            
            # Update previous date_index for next iteration
            prev_date_idx = date_idx
        
        # Combine all results
        non_empty_results = [df for df in all_results if not df.empty]
        if non_empty_results:
            output_df = pd.concat(non_empty_results, ignore_index=True)
            output_df = output_df.drop_duplicates().reset_index(drop=True)
        else:
            output_df = pd.DataFrame()

    # Return XML string (unchanged) and output dataframe
    xml_string = et.tostring(xml_root, encoding='utf8').decode('utf8')
    
    return xml_string, output_df, implied
