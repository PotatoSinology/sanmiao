import lxml.etree as et
import pandas as pd
from .loaders import prepare_tables
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