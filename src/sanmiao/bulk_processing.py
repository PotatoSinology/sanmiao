import re
import pandas as pd
import lxml.etree as et
from .config import (
    DEFAULT_TPQ, DEFAULT_TAQ, DEFAULT_GREGORIAN_START, LP_DIC,
    phrase_dic_en, phrase_dic_fr,
)
from .converters import (
    numcon, ganshu
)
from .loaders import prepare_tables
from .config import get_cal_streams_from_civ, LP_DIC
from .solving import (
    solve_date_simple, solve_date_with_year, solve_date_with_lunar_constraints
)

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
    if gs is None:
        gs = DEFAULT_GREGORIAN_START
    if civ is None:
        civ = ['c', 'j', 'k']
    
    # Use the optimized bulk function (delegates to extract_date_table_bulk)
    return extract_date_table_bulk(
        xml_string, pg=pg, gs=gs, lang=lang,
        tpq=tpq, taq=taq, civ=civ, tables=tables, sequential=True
    )


def dates_xml_to_df(xml_root: str) -> pd.DataFrame:
    """
    Convert XML string with date elements to pandas DataFrame.

    :param xml_string: str, XML string containing date elements
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
    date_xpath = './/tei:date' if ns else './/date'
    for node in xml_root.xpath(date_xpath, namespaces=ns):
        def get1(xp):
            result = node.xpath(f'normalize-space(string({xp}))', namespaces=ns)
            return result if result and result.strip() else None

        row = {
            "date_index": node.attrib.get("index"),
            "date_string": node.xpath("normalize-space(string())", namespaces=ns) if node.xpath("normalize-space(string())", namespaces=ns) else "",
            "dyn_str": get1(".//tei:dyn" if ns else ".//dyn"),
            "ruler_str": get1(".//tei:ruler" if ns else ".//ruler"),
            "era_str": get1(".//tei:era" if ns else ".//era"),
            "year_str": get1(".//tei:year" if ns else ".//year"),
            "sexYear_str": get1(".//tei:sexYear" if ns else ".//sexYear"),
            "month_str": get1(".//tei:month" if ns else ".//month"),
            "day_str": get1(".//tei:day" if ns else ".//day"),
            "gz_str": get1(".//tei:gz" if ns else ".//gz"),
            "lp_str": get1(".//tei:lp" if ns else ".//lp"),
            "has_int": 1 if node.xpath(".//tei:int" if ns else ".//int", namespaces=ns) else 0,
        }
        if row['sexYear_str'] is not None:
            row['sexYear_str'] = re.sub(r'[歲年]', '', row['sexYear_str'])
        rows.append(row)
    return pd.DataFrame(rows)


def normalise_date_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize and convert string date fields to numeric values in DataFrame.

    :param df: pd.DataFrame, DataFrame with string date fields
    :return: pd.DataFrame, DataFrame with normalized numeric date fields
    """
    out = df.copy()
    # year
    out["year"] = out["year_str"].where(out["year_str"].notna(), None)
    out.loc[out["year_str"] == "元年", "year"] = 1
    m = out["year_str"].notna() & (out["year_str"] != "元年")
    # Strip 年 character before converting numerals
    out.loc[m, "year"] = out.loc[m, "year_str"].str.rstrip('年').map(numcon)

    # sexYear
    out["sex_year"] = out["sexYear_str"].map(lambda s: ganshu(s) if isinstance(s, str) and s else None)
    
    # month
    def month_to_int(s):
        if not isinstance(s, str) or not s:
            return None
        if s == "正月": return 1
        if s == "臘月": return 13
        if s == "一月": return 14
        # Strip 月 character before converting numerals
        return numcon(s.rstrip('月'))
    out["month"] = out["month_str"].map(month_to_int)

    # day
    out["day"] = out["day_str"].map(lambda s: numcon(s.rstrip('日')) if isinstance(s, str) and s else None)

    # gz (sexagenary day number)
    out["gz"] = out["gz_str"].map(lambda s: ganshu(s) if isinstance(s, str) and s else None)

    # lp
    out["lp"] = out["lp_str"].map(lambda s: LP_DIC.get(s) if isinstance(s, str) else None)

    # intercalary
    # out["intercalary"] = out["has_int"].replace({0: None, 1: 1})
    out["intercalary"] = out["has_int"].replace({0: None, 1: 1}).infer_objects(copy=False)
    
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
    
    # If we have both original and resolved, keep resolved (drop original if it exists)
    if 'dyn_id' in out.columns and out['dyn_id'].dtype != 'object':
        # Keep the resolved one
        if '_resolved' in str(out.columns):
            out = out.drop(columns=[col for col in out.columns if col.endswith('_resolved')])
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
    
    # If we have both original and resolved, keep resolved (drop original if it exists)
    if 'ruler_id' in out.columns and out['ruler_id'].dtype != 'object':
        # Keep the resolved one
        if '_resolved' in str(out.columns):
            out = out.drop(columns=[col for col in out.columns if col.endswith('_resolved')])
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
    
    # If no era strings, return as-is
    if 'era_str' not in out.columns or out['era_str'].notna().sum() == 0:
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
    
    # If we have both original and resolved, keep resolved (drop original if it exists)
    if 'era_id' in out.columns and out['era_id'].dtype != 'object':
        # Keep the resolved one
        if '_resolved' in str(out.columns):
            out = out.drop(columns=[col for col in out.columns if col.endswith('_resolved')])
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
        date_rows = out[out['date_index'] == date_idx].copy()
        
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
                candidate_row = {
                    'date_index': date_idx,
                    'dyn_id': None,
                    'ruler_id': None,
                    'era_id': None,
                }
                for col in out.columns:
                    if col not in candidate_row and col != 'date_index':
                        candidate_row[col] = first_row.get(col)
                all_candidates.append(candidate_row)
            else:
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
                cols = ['year_str', 'sexYear_str', 'month_str', 'day_str', 'gz_str', 'lp_str']
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
                
                # Merge with master table
                t_out = t_out.merge(master_table, on=['cal_stream'], how='left')
                
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
                        date_rows['date_index'] = date_idx
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
                        date_rows['date_index'] = date_idx
                        if 'error_str' not in date_rows.columns:
                            date_rows['error_str'] = ""
                        date_rows['error_str'] += phrase_dic['year-sex-mismatch']
                        all_candidates.extend(date_rows.to_dict('records'))
                        continue
                
                date_rows = t_out
                
                # Clean columns
                cols = ['_ind_year', 'nmd_gz', 'nmd_jdn', 'hui_jdn', 'ind_year']
                cols = [i for i in cols if i in t_out.columns]
                date_rows = date_rows.drop(columns=cols)
                
                date_rows['date_index'] = date_idx

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
                # Find dynasty info
                dyn_info = dyn_df[dyn_df['dyn_id'] == combo['dyn_id']]
                if not dyn_info.empty:
                    dyn_row = dyn_info.iloc[0]
                    # Create candidate using dynasty's reign period
                    candidate_row = {
                        'date_index': date_idx,
                        'dyn_id': combo['dyn_id'],
                        'ruler_id': None,  # No specific ruler
                        'era_id': None,  # No specific era
                        'cal_stream': dyn_row['cal_stream'],
                        'era_start_year': dyn_row['dyn_start_year'],
                        'era_end_year': dyn_row['dyn_end_year'],
                        'max_year': None,  # Dynasty doesn't have max_year
                        'era_name': None,  # No era name for dynasty-only
                    }
                    # Copy ALL date fields to preserve month, intercalary, day, etc.
                    for col in date_rows.columns:
                        if col not in candidate_row and col != 'date_index':
                            candidate_row[col] = combo['source_row'].get(col)
                    all_candidates.append(candidate_row)
                continue  # Skip the normal era-based logic

            # Special case: ruler specified but no era - use ruler's reign period
            if (combo['ruler_id'] is not None and
                combo['era_id'] is None):
                # Find ruler info
                ruler_info = ruler_df[ruler_df['person_id'] == combo['ruler_id']]
                if not ruler_info.empty:
                    ruler_row = ruler_info.iloc[0]

                    # If dynasty is also specified, check if it matches
                    if combo['dyn_id'] is not None and ruler_row['dyn_id'] != combo['dyn_id']:
                        continue  # Dynasty doesn't match, skip this ruler

                    # Create candidate using ruler's reign period
                    candidate_row = {
                        'date_index': date_idx,
                        'dyn_id': ruler_row['dyn_id'],
                        'ruler_id': combo['ruler_id'],
                        'era_id': None,  # No specific era
                        'cal_stream': ruler_row['cal_stream'],
                        'era_start_year': ruler_row['emp_start_year'],
                        'era_end_year': ruler_row['emp_end_year'],
                        'max_year': ruler_row['max_year'],
                        'era_name': None,  # No era name for ruler-only
                    }
                    # Copy ALL date fields to preserve month, intercalary, day, etc.
                    for col in date_rows.columns:
                        if col not in candidate_row and col != 'date_index':
                            candidate_row[col] = combo['source_row'].get(col)
                    all_candidates.append(candidate_row)
                continue  # Skip the normal era-based logic

            # Build filter for era_df based on this combination
            era_filter = era_df.copy()
            
            # Filter by era_id if specified
            if combo['era_id'] is not None:
                era_filter = era_filter[era_filter['era_id'] == combo['era_id']]
            
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
                        candidate_row = {
                            'date_index': date_idx,
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
            candidate_row = {
                'date_index': date_idx,
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

    cols = ['dyn_str', 'ruler_str', 'era_str', 'year_str', 'sexYear_str', 'month_str', 'day_str', 'gz_str', 'lp_str', 'year_gz']
    cols = [i for i in cols if i in candidates_df.columns]
    candidates_df = candidates_df.drop(columns=cols)
    
    return candidates_df.drop_duplicates().reset_index(drop=True)


def add_can_names_bulk(table, ruler_can_names, dyn_df):
    """
    Add canonical names (dyn_name, ruler_name) to candidate DataFrame.
    
    :param table: DataFrame with ruler_id and/or dyn_id columns
    :param ruler_can_names: DataFrame with ['person_id', 'string'] columns
    :param dyn_df: DataFrame with ['dyn_id', 'dyn_name'] columns
    :return: DataFrame with added 'ruler_name' and 'dyn_name' columns
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
    
    return out


def extract_date_table_bulk(xml_root, implied=None, pg=False, gs=None, lang='en', tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, civ=None, tables=None, sequential=True, proliferate=False):
    """
    Optimized bulk version of extract_date_table using pandas operations.
    
    This function replaces the iterative interpret_date() approach with:
    1. Bulk ID resolution (all dates at once)
    2. Bulk candidate generation (all combinations at once)
    3. Sequential constraint solving per date (preserving implied state)
    
    :param xml_root:
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
    :return: tuple (xml_string, output_df, implied) - same format as extract_date_table()
    """
    # Defaults
    if gs is None:
        gs = DEFAULT_GREGORIAN_START
    if civ is None:
        civ = ['c', 'j', 'k']
    
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
    
    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    
    # Step 1: Extract table
    df = dates_xml_to_df(xml_root)
    if df.empty:
        xml_string = et.tostring(xml_root, encoding='utf8').decode('utf8')
        return xml_string, pd.DataFrame(), implied
    
    # Step 2: Normalize date fields (convert strings to numbers)
    df = normalise_date_fields(df)
    
    # Step 3: Load all tables once (or use provided tables)
    # Performance optimization: if tables are already loaded, reuse them to avoid copying
    if tables is None:
        tables = prepare_tables(civ=civ)
    era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = tables
    master_table = era_df[['cal_stream', 'dyn_id', 'ruler_id', 'era_id', 'era_start_year', 'era_end_year', 'era_start_jdn', 'era_end_jdn']].copy()
    
    # Step 4: Bulk resolve IDs (Phase 1)
    df = bulk_resolve_dynasty_ids(df, dyn_tag_df, dyn_df)
    df = bulk_resolve_ruler_ids(df, ruler_tag_df)
    df = bulk_resolve_era_ids(df, era_df)
    
    # Step 5: Bulk generate candidates (Phase 2) 
    df_candidates = bulk_generate_date_candidates(df, dyn_df, ruler_df, era_df, master_table, lunar_table, phrase_dic=phrase_dic_en, tpq=tpq, taq=taq, civ=civ, proliferate=proliferate)
    
    # Add report note
    df_candidates['error_str'] = ""
    
    all_results = []
    
    # Group by date_index and process sequentially [sex_year is fine at this point]
    for date_idx in sorted(df_candidates['date_index'].dropna().unique(), key=lambda x: int(x) if str(x).isdigit() else 0):
        # Reset implied state for each date if not sequential

        g = df_candidates[df_candidates['date_index'] == date_idx].copy()
        if g.empty:
            continue
        print('*'*120)
        print(implied)
        # Determine what constraints this date has
        has_year = g['year'].notna().any()
        has_sex_year = g['sex_year'].notna().any()
        has_month = g['month'].notna().any() and not g['month'].isna().all()
        has_day = g['day'].notna().any() and not g['day'].isna().all()
        has_gz = g['gz'].notna().any() and not g['gz'].isna().all()
        has_lp = g['lp'].notna().any() and not g['lp'].isna().all()
        has_intercalary = g[g['has_int'] == 1].shape[0] == g.shape[0]
        
        # Apply implied values to incomplete candidates
        no_year = not (has_year or has_sex_year)
        no_month = not (has_month or has_intercalary)
        no_day = not (has_day or has_gz or has_lp)
        
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
                if no_month:
                    if implied.get('month') is not None and ('month' not in g.columns or g['month'].isna().all()):
                        g['month'] = implied['month']
                    if implied.get('intercalary') is not None and ('intercalary' not in g.columns or g['intercalary'].isna().all()):
                        g['intercalary'] = implied['intercalary']
                    has_month = True
        
        # Determine date type
        is_simple = not has_year and not has_sex_year and not has_month and not has_day and not has_gz and not has_lp
        # Solve based on date type
        if is_simple:
            # Simple date (dynasty/era only)
            result_df, implied = solve_date_simple(
                g, implied, phrase_dic, tpq, taq
            )
        elif has_month or has_day or has_gz or has_lp:
            # Date with lunar constraints
            # First handle year if present
            
            if has_year or has_sex_year:
                g, implied = solve_date_with_year(
                    g, implied, era_df, phrase_dic, tpq, taq,
                    has_month, has_day, has_gz, has_lp
                )
            print(g[['ind_year', 'year', 'sex_year']].to_string())
            # Apply lunar constraints to the candidates (whether year was solved or not)
            month_val = g.iloc[0].get('month') if has_month and pd.notna(g.iloc[0].get('month')) else None
            day_val = g.iloc[0].get('day') if has_day and pd.notna(g.iloc[0].get('day')) else None
            gz_val = g.iloc[0].get('gz') if has_gz and pd.notna(g.iloc[0].get('gz')) else None
            lp_val = g.iloc[0].get('lp') if has_lp and pd.notna(g.iloc[0].get('lp')) else None
            intercalary_val = 1 if has_intercalary else None

            result_df, implied = solve_date_with_lunar_constraints(
                g, implied, lunar_table, phrase_dic,
                month=month_val, day=day_val, gz=gz_val, lp=lp_val, intercalary=intercalary_val,
                tpq=tpq, taq=taq, pg=pg, gs=gs
            )
            # If lunar constraints resulted in no matches (likely due to corruption),
            # return the original input dataframe instead of empty
            if result_df.empty:
                result_df = g.copy()
                phrase_dic = phrase_dic_fr if lang == 'fr' else phrase_dic_en
                result_df['error_str'] += phrase_dic.get('lunar-constraint-failed', 'Lunar constraint solving failed; ')
                xml_string = et.tostring(xml_root, encoding='utf8').decode('utf8')
                return xml_string, result_df, implied

            # Add metadata to result_df if not empty
            if not result_df.empty:
                if 'cal_stream' in result_df.columns and 'ind_year' in result_df.columns:
                    result_df = result_df.sort_values(by=['cal_stream', 'ind_year'])
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
        if not result_df.empty:
            result_df['date_index'] = date_idx
            result_df['date_string'] = g.iloc[0].get('date_string', '') if not g.empty else 'unknown'
            all_results.append(result_df)
    
    # Combine all results
    if all_results:
        # output_df = pd.concat(all_results, ignore_index=True)
        # Filter out empty DataFrames to avoid the warning
        non_empty_results = [df for df in all_results if not df.empty]
        if non_empty_results:
            output_df = pd.concat(non_empty_results, ignore_index=True)
        else:
            output_df = pd.DataFrame()
    else:
        output_df = pd.DataFrame()

    # Return XML string (unchanged) and output dataframe
    xml_string = et.tostring(xml_root, encoding='utf8').decode('utf8')
    
    return xml_string, output_df, implied
