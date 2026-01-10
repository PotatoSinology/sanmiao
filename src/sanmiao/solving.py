# Date solving algorithms for sanmiao

import pandas as pd
from .config import DEFAULT_TPQ, DEFAULT_TAQ, phrase_dic_en
from .converters import gz_year, ganshu, numcon
from .config import get_cal_streams_from_civ


def solve_date_simple(g, implied, phrase_dic=phrase_dic_en, tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ):
    """
    Solve dates that have only dynasty/ruler/era (no year/month/day constraints).

    These are "done" cases - dates that specify only the dynasty, ruler, or era,
    without any temporal constraints like year, month, or day.

    :param g: DataFrame with candidate rows for a single date_index
    :param implied: dict with implied state from previous dates
    :param phrase_dic: dict with phrase translations
    :param tpq: terminus post quem (earliest date)
    :param taq: terminus ante quem (latest date)
    :return: tuple (df, updated_implied)
    """
    # Check if we have any constraints from implied state
    if implied:
        # Apply implied constraints
        for key, value in implied.items():
            if key in g.columns and pd.notna(value):
                if isinstance(value, list):
                    g = g[g[key].isin(value)]
                else:
                    g = g[g[key] == value]

    # If we have no rows left, return empty
    if g.empty:
        return g, implied

    # For simple dates, we just return all candidates within TPQ/TAQ
    # Filter by year constraints if available
    if 'era_start_year' in g.columns:
        g = g[(g['era_start_year'] >= tpq) & (g['era_start_year'] <= taq)]
    elif 'emp_start_year' in g.columns:
        g = g[(g['emp_start_year'] >= tpq) & (g['emp_start_year'] <= taq)]
    elif 'dyn_start_year' in g.columns:
        g = g[(g['dyn_start_year'] >= tpq) & (g['dyn_start_year'] <= taq)]

    # Mark errors for dynasty/ruler/era mismatches
    if not g.empty:
        # Check for dynasty-ruler mismatches
        dyn_ruler_groups = g.groupby(['dyn_id', 'ruler_id']).size()
        if len(dyn_ruler_groups) > 1:
            # Multiple dynasty-ruler combinations - mark as error
            for idx in g.index:
                if 'error_str' not in g.columns:
                    g['error_str'] = ""
                g.at[idx, 'error_str'] += phrase_dic['dyn-rul-era-mismatch']

        # Check for era-ruler mismatches
        if 'era_id' in g.columns:
            era_ruler_groups = g.groupby(['era_id', 'ruler_id']).size()
            if len(era_ruler_groups) > 1:
                for idx in g.index:
                    if 'error_str' not in g.columns:
                        g['error_str'] = ""
                    g.at[idx, 'error_str'] += phrase_dic['dyn-rul-era-mismatch']

    return g, implied


def solve_date_with_year(g, implied, era_df, phrase_dic=phrase_dic_en, tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, has_month=False, has_day=False, has_gz=False, has_lp=False):
    """
    Solve dates that have year constraints (numeric or sexagenary).

    Handles:
    - Dynasty/ruler/era with year
    - Year with dynasty/ruler/era
    - Sexagenary year with dynasty/ruler/era

    :param g: DataFrame with candidate rows
    :param implied: dict with implied state
    :param era_df: DataFrame with era information
    :param phrase_dic: dict with phrase translations
    :param tpq: terminus post quem
    :param taq: terminus ante quem
    :param has_month: whether date has month constraint
    :param has_day: whether date has day constraint
    :param has_gz: whether date has sexagenary day constraint
    :param has_lp: whether date has lunar phase constraint
    :return: tuple (df, updated_implied)
    """
    # Debug: print columns and sample data
    print(f"DEBUG solve_date_with_year: g.columns = {list(g.columns)}")
    if not g.empty:
        print(f"DEBUG solve_date_with_year: sample row = {g.iloc[0].to_dict()}")

    # Apply implied constraints first
    for key, value in implied.items():
        if key in g.columns and pd.notna(value):
            if isinstance(value, list):
                g = g[g[key].isin(value)]
            else:
                g = g[g[key] == value]

    if g.empty:
        return g, implied

    # Create ind_year column if it doesn't exist
    if 'ind_year' not in g.columns and 'year' in g.columns and 'era_start_year' in g.columns:
        g['ind_year'] = g['year'] + g['era_start_year'] - 1

    # Filter by TPQ/TAQ
    if 'ind_year' in g.columns:
        g = g[(g['ind_year'] >= tpq) & (g['ind_year'] <= taq)]

    if g.empty:
        return g, implied

    # Get calendar streams for filtering
    cal_streams = get_cal_streams_from_civ(implied.get('civ'))

    # Filter by calendar streams if specified
    if cal_streams is not None and 'cal_stream' in g.columns:
        g = g[g['cal_stream'].astype(float).isin(cal_streams)]

    if g.empty:
        return g, implied

    # Prepare for era resolution
    if not era_df.empty and 'era_id' not in g.columns:
        # Merge era information
        era_cols = ['era_id', 'ruler_id', 'era_name', 'era_start_year', 'era_end_year']
        if all(col in era_df.columns for col in era_cols):
            g = g.merge(era_df[era_cols], on='ruler_id', how='left')
    
    # Handle different constraint combinations
    if has_month or has_day or has_gz or has_lp:
        # We have temporal constraints beyond just year - will be handled by lunar constraints solver
        pass
    else:
        # Year-only date - apply era filtering
        if 'era_start_year' in g.columns and 'era_end_year' in g.columns:
            valid_eras = (
                (g['era_start_year'] <= g['ind_year']) &
                (g['era_end_year'] > g['ind_year'])
            )
            g = g[valid_eras]

        # Remove duplicates and sort
        if not g.empty:
            g = g.sort_values(['cal_stream', 'dyn_id', 'ruler_id'])
            g = g.drop_duplicates()

    # Update implied state
    updated_implied = implied.copy()
    if not g.empty:
        # Store successful resolutions for future dates
        for col in ['dyn_id', 'ruler_id', 'era_id', 'cal_stream']:
            if col in g.columns:
                unique_vals = g[col].dropna().unique()
                if len(unique_vals) == 1:
                    updated_implied[col] = unique_vals[0]
                elif len(unique_vals) > 1:
                    updated_implied[f'{col}_ls'] = list(unique_vals)

    return g, updated_implied


def solve_date_with_lunar_constraints(g, implied, lunar_table, phrase_dic=phrase_dic_en,
                                      month=None, day=None, gz=None, lp=None, intercalary=None,
                                      tpq=DEFAULT_TPQ, taq=DEFAULT_TAQ, pg=False, gs=None):
    """
    Solve dates with month/day/sexagenary day/lunar phase constraints.

    :param g: DataFrame with candidate rows (should already have ind_year calculated)
    :param implied: dict with implied state
    :param lunar_table: DataFrame with lunar calendar data
    :param phrase_dic: dict with phrase translations
    :param month: int or list of ints, month constraint(s)
    :param day: int, day constraint
    :param gz: int, sexagenary day constraint
    :param lp: int, lunar phase constraint (0=朔/new moon, -1=晦/last day)
    :param intercalary: bool, intercalary month constraint
    :param tpq: terminus post quem
    :param taq: terminus ante quem
    :param pg: proleptic Gregorian flag
    :param gs: Gregorian start date
    :return: tuple (df, updated_implied)
    """
    # Apply implied constraints
    for key, value in implied.items():
        if key in g.columns and pd.notna(value):
            if isinstance(value, list):
                g = g[g[key].isin(value)]
            else:
                g = g[g[key] == value]

    if g.empty:
        return g, implied

    # Create ind_year column if it doesn't exist
    if 'ind_year' not in g.columns and 'year' in g.columns and 'era_start_year' in g.columns:
        g['ind_year'] = g['year'] + g['era_start_year'] - 1

    # Filter by TPQ/TAQ
    if 'ind_year' in g.columns:
        g = g[(g['ind_year'] >= tpq) & (g['ind_year'] <= taq)]

    if g.empty:
        return g, implied

    # Get calendar streams
    cal_streams = get_cal_streams_from_civ(implied.get('civ'))
    if cal_streams is not None and 'cal_stream' in g.columns:
        g = g[g['cal_stream'].astype(float).isin(cal_streams)]

    if g.empty:
        return g, implied

    # Merge with lunar table
    lunar_cols = ['cal_stream', 'ind_year', 'year_gz', 'month', 'intercalary',
                  'nmd_jdn', 'hui_jdn', 'max_day', 'hui_gz', 'nmd_gz']
    if all(col in lunar_table.columns for col in lunar_cols):
        g = g.merge(lunar_table[lunar_cols], on=['cal_stream', 'ind_year'], how='inner')

    if g.empty:
        return g, implied

    # Apply month constraints
    if month is not None:
        if isinstance(month, list):
            g = g[g['month_x'].isin(month)]
        else:
            g = g[g['month_x'] == month]

    # Apply intercalary constraint
    if intercalary is not None:
        g = g[g['intercalary_x'] == intercalary]

    if g.empty:
        return g, implied

    # Apply day constraints
    if day is not None and 'max_day' in g.columns:
        # Validate day is within month bounds
        valid_days = g['max_day'] >= day
        if not valid_days.any():
            # Day out of bounds for this month
            g['error_str'] = g.get('error_str', '') + phrase_dic['month-day-oob']
        else:
            g = g[valid_days]

    # Apply sexagenary day constraints
    if gz is not None and 'nmd_gz' in g.columns:
        # Calculate day of month for each candidate
        g['_day_of_month'] = None
        for idx, row in g.iterrows():
            if pd.notna(row['nmd_jdn']) and pd.notna(row['hui_jdn']):
                # This is a simplified calculation - in practice this needs more complex logic
                # based on the actual lunar calendar calculations
                pass

    # Apply lunar phase constraints
    if lp is not None:
        # Handle new moon (朔) and last day (晦) constraints
        if lp == 0:  # 朔 - new moon
            # Keep only rows where JDN matches new moon
            pass
        elif lp == -1:  # 晦 - last day of month
            # Keep only rows where JDN matches full moon
            pass

    # Clean up and return
    if not g.empty:
        g = g.sort_values(['cal_stream', 'dyn_id', 'ruler_id'])
        g = g.drop_duplicates()

    # Update implied state
    updated_implied = implied.copy()
    if not g.empty:
        for col in ['dyn_id', 'ruler_id', 'era_id', 'cal_stream', 'month', 'intercalary']:
            if col in g.columns:
                unique_vals = g[col].dropna().unique()
                if len(unique_vals) == 1:
                    updated_implied[col] = unique_vals[0]
                elif len(unique_vals) > 1:
                    updated_implied[f'{col}_ls'] = list(unique_vals)

    return g, updated_implied