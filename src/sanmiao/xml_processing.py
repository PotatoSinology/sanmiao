import lxml.etree as et
import pandas as pd
from .config import DEFAULT_TPQ, DEFAULT_TAQ
from .bulk_processing import extract_date_table_bulk, dates_xml_to_df


def filter_annals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter annals dates: if head row has context, apply it to month-only dates.
    
    Checks if the head date (date_index == 0) has cal_stream, dyn_id, ruler_id,
    era_id, year, and sex_year. If it does, applies those values to all rows
    that only have months and sub-month elements (no higher-level context).
    
    :param df: pd.DataFrame, DataFrame with date information
    :return: pd.DataFrame, DataFrame with context applied from head row
    """
    # Make a copy to avoid modifying the original
    result_df = df.copy()
    if 'date_index' not in result_df.columns:
        return result_df
    # Align data type
    result_df = result_df.dropna(subset=['date_index'])
    result_df['date_index'] = result_df['date_index'].astype(int)
    # Identify head date (date_index == 0)
    head_rows = result_df[result_df['date_index'] == 0]
    if len(head_rows) == 0:
        # No head date found, return unchanged
        return result_df
    # Take the first head row (in case there are multiple with date_index == 0)
    head_row = head_rows.iloc[0]
    
    # Check if head row has all required context fields
    # Note: ind_year is calculated later in the pipeline, so we don't check for it here
    required_fields = ['cal_stream', 'dyn_id', 'ruler_id', 'era_id', 'year', 'sex_year']
    has_all_context = all(
        field in head_row.index and pd.notna(head_row.get(field))
        for field in required_fields
    )
    
    if not has_all_context:
        # Head row doesn't have all required fields, return unchanged
        return result_df

    # Identify rows that only have months and sub-month elements
    # (present_elements doesn't contain 'h', 'r', 'e', 'y', 's' but contains 'm')
    month_only_mask = (
        ~result_df['present_elements'].str.contains(r'[hreys]', na=False) &
        result_df['present_elements'].str.contains('m', na=False)
    )
    
    if not month_only_mask.any():
        # No month-only rows to update
        return result_df

    # Apply head row context to month-only rows
    # Only apply fields that are missing in the target rows
    for field in required_fields:
        if field in result_df.columns:
            # Only fill where the field is missing (NaN) in month-only rows
            month_only_indices = result_df.index[month_only_mask]
            missing_mask = result_df.loc[month_only_indices, field].isna()
            if missing_mask.any():
                result_df.loc[month_only_indices[missing_mask], field] = head_row[field]
    
    return result_df


def backwards_fill_days(df: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-fill month and intercalary from month-only dates to day-only dates.
    
    For rows that have only day/lp/gz/nmd_gz (no month), fill in the month
    and intercalary from the most recent row that has a month.
    """
    df = df.dropna(subset=['date_index'])
    df['date_index'] = df['date_index'].astype(int)
    result_df = df.copy()
    
    # Create a lookup table with month and intercalary for each date_index
    # Only use rows that have 'm' in present_elements (month present)
    month_rows = result_df[result_df['present_elements'].str.contains('m', na=False)].copy()
    
    # Create a complete date_index range
    all_indices = pd.DataFrame({'date_index': range(0, int(result_df['date_index'].max()) + 1)})
    
    # Merge month data and forward-fill
    month_lookup = month_rows[['date_index', 'month']].copy()
    if 'intercalary' in month_rows.columns:
        month_lookup['_intercalary'] = month_rows['intercalary']
    else:
        month_lookup['_intercalary'] = None
    
    month_lookup = month_lookup.rename(columns={'month': '_month'})
    month_lookup = all_indices.merge(month_lookup, on='date_index', how='left')
    # Suppress downcasting warning by opting into future behavior
    with pd.option_context('future.no_silent_downcasting', True):
        month_lookup = month_lookup.ffill()
    month_lookup = month_lookup.infer_objects(copy=False)
    
    # Merge back to result_df
    result_df = result_df.merge(month_lookup[['date_index', '_month', '_intercalary']], on='date_index', how='left')
    
    # Identify rows that need month filling:
    # - Don't have 'm' in present_elements (no month)
    # - But have at least one of: 'd' (day), 'l' (lp), 'g' (gz), 'z' (nmd_gz)
    needs_month = (
        ~result_df['present_elements'].str.contains('m', na=False) &
        (
            result_df['present_elements'].str.contains('d', na=False) |
            result_df['present_elements'].str.contains('l', na=False) |
            result_df['present_elements'].str.contains('g', na=False) |
            result_df['present_elements'].str.contains('z', na=False)
        )
    )
    
    # Fill month for rows that need it
    result_df.loc[needs_month & result_df['_month'].notna(), 'month'] = result_df.loc[needs_month & result_df['_month'].notna(), '_month']
    
    # Fill intercalary for rows that need it
    if 'intercalary' in result_df.columns:
        result_df.loc[needs_month & result_df['_intercalary'].notna(), 'intercalary'] = result_df.loc[needs_month & result_df['_intercalary'].notna(), '_intercalary']
    
    # Drop temporary columns
    result_df = result_df.drop(columns=['_month', '_intercalary'], errors='ignore')
    
    return result_df
