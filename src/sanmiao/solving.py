# Date solving algorithms for sanmiao

import pandas as pd
from .config import DEFAULT_TPQ, DEFAULT_TAQ, phrase_dic_en
from .converters import ganshu, jdn_to_iso, gz_year


def preference_filtering_bulk(table, implied):
    """
    Apply preference filtering based on implied state.
    
    This filters candidate rows using implied state from previous dates.
    If filtering results in empty table, revert to original (fail gracefully).
    
    :param table: DataFrame with candidate rows to filter
    :param implied: dict with keys like 'dyn_id_ls', 'ruler_id_ls', 'era_id_ls', 'cal_stream_ls', 'month', 'intercalary'
    :return: Filtered DataFrame (or original if filtering fails)
    """
    if table.shape[0] < 2:
        return table
    
    bu = table.copy()
    
    # Filter by implied era_id list
    era_id_ls = implied.get('era_id_ls', [])
    if 'era_id' in table.columns and len(era_id_ls) > 0:
        table = table[table['era_id'].isin(era_id_ls)]
        if table.empty:
            table = bu.copy()
        else:
            bu = table.copy()
    
    # Filter by implied ruler_id list
    ruler_id_ls = implied.get('ruler_id_ls', [])
    if 'ruler_id' in table.columns and len(ruler_id_ls) > 0:
        table = table[table['ruler_id'].isin(ruler_id_ls)]
        if table.empty:
            table = bu.copy()
        else:
            bu = table.copy()
    
    # Filter by implied dyn_id list
    dyn_id_ls = implied.get('dyn_id_ls', [])
    if 'dyn_id' in table.columns and len(dyn_id_ls) > 0:
        table = table[table['dyn_id'].isin(dyn_id_ls)]
        if table.empty:
            table = bu.copy()
        else:
            bu = table.copy()

    # Filter by implied cal_stream list
    cal_stream_ls = implied.get('cal_stream_ls', [])
    if 'cal_stream' in table.columns and len(cal_stream_ls) > 0:
        table = table[table['cal_stream'].isin(cal_stream_ls)]
        if table.empty:
            table = bu.copy()
        else:
            bu = table.copy()

    # Filter by implied month
    mn = implied.get('month')
    if 'month' in table.columns and mn is not None:
        if table.shape[0] > 1:
            mos = table.dropna(subset=['month'])['month'].unique()
            if len(mos) > 1:
                table = table[table['month'] == mn]
            if table.empty:
                table = bu.copy()
            else:
                bu = table.copy()
    
    # Filter by implied intercalary
    inter = implied.get('intercalary')
    bu = table.copy()
    if 'intercalary' in table.columns and inter is not None:
        if table.shape[0] > 1:
            intercalarys = table.dropna(subset=['intercalary'])['intercalary'].unique()
            if len(intercalarys) > 1:
                table = table[table['intercalary'] == inter]
            if table.empty:
                table = bu.copy()
            else:
                bu = table.copy()
    
    table = table.drop_duplicates()
    return table.copy()


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
    if g.empty:
        return pd.DataFrame(), f"{phrase_dic.get('ui')}: (empty)\n{phrase_dic.get('matches')}:\nNo matches", implied.copy()

    # Apply preference filtering
    df = preference_filtering_bulk(g.copy(), implied)
    
    # Update implied state (clear year/month/intercalary for simple dates)
    updated_implied = implied.copy()
    updated_implied.update({
        'year': None,
        'month': None,
        'intercalary': None
    })

    # Update implied ID lists if we have unique matches
    imp_ls = ['cal_stream', 'dyn_id', 'ruler_id', 'era_id']
    for i in imp_ls:
        if i in df.columns:
            unique_vals = df.dropna(subset=[i])[i].unique()
            if len(unique_vals) == 1:
                updated_implied.update({f'{i}_ls': list(unique_vals)})
    
    # Apply date range filter if we have multiple matches
    if df.shape[0] > 1:
        # Check if we have era date range info
        if 'era_start_year' in df.columns and 'era_end_year' in df.columns:
            if df.dropna(subset=['era_start_year', 'era_end_year']).empty:
                temp = df[(df['era_start_year'] >= tpq) & (df['era_end_year'] <= taq)].copy()
                if not temp.empty:
                    df = temp
                else:
                    df = g.copy()
                    df['error_str'] += "Dyn-rul-era mismatch; "
    
    return df, updated_implied


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
    if g.empty:
        return pd.DataFrame(), "", implied.copy()

    df = g.copy()

    # Initialize updated_implied to avoid UnboundLocalError
    updated_implied = implied.copy()

    # Get year value from candidates (should be same for all rows in group)
    year = None
    if 'year' in df.columns:
        year_vals = df['year'].dropna().unique()
        if len(year_vals) > 0:
            year = int(year_vals[0])
    
    # Get sexagenary year value
    sex_year = None
    if 'sex_year' in df.columns:
        sex_year_vals = df['sex_year'].dropna().unique()
        if len(sex_year_vals) > 0:
            sex_year = int(sex_year_vals[0])
    
    # Handle numeric year constraint
    if year is not None:
        # If dataframe has no era information (all NaN), populate with implied era
        if ('era_id' not in df.columns or df['era_id'].isna().all()) and implied.get('era_id_ls'):
            # Use the implied era to populate missing era information
            implied_era_id = implied['era_id_ls'][0]
            era_info = era_df[era_df['era_id'] == implied_era_id].iloc[0] if not era_df[era_df['era_id'] == implied_era_id].empty else None
            if era_info is not None:
                df = df.copy()  # Ensure we have a copy to modify
                df['era_id'] = implied_era_id
                df['ruler_id'] = era_info['ruler_id']
                df['dyn_id'] = era_info['dyn_id']
                df['cal_stream'] = era_info['cal_stream']
                df['era_start_year'] = era_info['era_start_year']
                df['era_end_year'] = era_info['era_end_year']
                df['max_year'] = era_info['max_year']
                df['era_name'] = era_info['era_name']
        
        # Filter by max_year (era must have lasted at least this many years)
        if 'max_year' in df.columns:
            bu = df.copy()
            df = df[df['max_year'] >= year].copy()
            if df.empty:
                df = bu.copy()
                df['error_str'] += phrase_dic.get('year-over-max', 'Year out of bounds; ')

        # Calculate index year (Western calendar year)
        if 'era_start_year' in df.columns:
            df['ind_year'] = df['era_start_year'] + year - 1
            if sex_year is None:
                df['sex_year'] = df['ind_year'].apply(lambda x: gz_year(x))
        else:
            df['ind_year'] = None
        
        # Update implied state if year changed
        if implied.get('year') != year:
            updated_implied = implied.copy()
            updated_implied.update({
                'year': year,
                'month': None,
                'intercalary': None
            })
        else:
            updated_implied = implied.copy()
            updated_implied['year'] = year
    
    # Handle sexagenary year constraint
    elif sex_year is not None:
        # Expand to multiple index years (every 60 years)
        # The year 4 is a jiazi year, so is -596
        # gz_origin = -596 + sex_year - 1
        gz_origin = -596 + sex_year - 1
        
        # Get era date ranges
        if 'era_start_year' in df.columns and 'era_end_year' in df.columns:
            era_min = df['era_start_year'].min()
            era_max = df['era_end_year'].max()

            # Check for NaN values
            if pd.isna(era_min) or pd.isna(era_max) or pd.isna(gz_origin):
                df['error_str'] = 'Missing era or sexagenary year data'
                return df, implied

            # Calculate cycles elapsed
            cycles_elapsed = int((era_min - gz_origin) / 60)
            last_instance = int(cycles_elapsed * 60 + gz_origin)
            
            # Get all index years (every 60 years)
            ind_years = [i for i in range(last_instance, int(era_max) + 1, 60)]
            
            # Filter eras to those that contain these index years
            if len(ind_years) > 0:
                # Expand rows for each matching index year
                expanded_rows = []
                for _, row in df.iterrows():
                    era_start = row['era_start_year']
                    era_end = row['era_end_year']
                    for ind_year in ind_years:
                        if era_start <= ind_year <= era_end:
                            new_row = row.copy()
                            new_row['ind_year'] = ind_year
                            new_row['year'] = ind_year - era_start + 1  # Calculate era year
                            expanded_rows.append(new_row)
                
                if expanded_rows:
                    df = pd.DataFrame(expanded_rows)
                else:
                    df = pd.DataFrame()  # No matches
        
        updated_implied = implied.copy()
        updated_implied.update({
            'sex_year': sex_year,
            'month': None,
            'intercalary': None
        })
    
    # Handle implied year (from previous dates)
    elif not has_month and not has_day and not has_gz and not has_lp:
        # Year-only date, try to use implied year
        implied_year = implied.get('year')
        if implied_year is not None:
            if 'era_start_year' in df.columns:
                df['year'] = implied_year
                df['ind_year'] = df['era_start_year'] + implied_year - 1
            updated_implied = implied.copy()
            updated_implied['year'] = implied_year
        else:
            # No year constraint at all - expand all possible years
            expanded_rows = []
            for _, row in df.iterrows():
                if pd.notna(row.get('max_year')):
                    max_yr = int(row['max_year'])
                    era_start = row.get('era_start_year', 0)
                    for y in range(1, max_yr + 1):
                        new_row = row.copy()
                        new_row['year'] = y
                        new_row['ind_year'] = era_start + y - 1
                        expanded_rows.append(new_row)
            if expanded_rows:
                df = pd.DataFrame(expanded_rows)
            updated_implied = implied.copy()
            updated_implied['year'] = None
    
    # Apply preference filtering
    df = preference_filtering_bulk(df, updated_implied)
    
    # If no month/day constraints, we're done (year-only date)
    if not has_month and not has_day and not has_gz and not has_lp:
        # Apply date range filter
        if df.shape[0] > 1 and 'ind_year' in df.columns:
            temp = df[(df['ind_year'] >= tpq) & (df['ind_year'] <= taq)].copy()
            if not temp.empty:
                df = temp

        # Update implied ID lists
        imp_ls = ['cal_stream', 'dyn_id', 'ruler_id', 'era_id']
        for i in imp_ls:
            if i in df.columns:
                unique_vals = df.dropna(subset=[i])[i].unique()
                if len(unique_vals) == 1:
                    updated_implied.update({f'{i}_ls': list(unique_vals)})

        if df.empty:
            df = g.copy()
            df['error_str'] += phrase_dic.get('year-solving-failed', 'Year resolution failed; ')

        return df, updated_implied

    # If we have month/day constraints, we'll handle those in Phase 5
    # For now, just return with ind_year set up
    if df.empty:
        df = g.copy()
        df['error_str'] += phrase_dic.get('year-solving-failed', 'Year resolution failed; ')

    return df, updated_implied


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
    if g.empty or 'ind_year' not in g.columns:
        return pd.DataFrame(), implied.copy()
    
    updated_implied = implied.copy()
    
    # Determine if we have month/day constraints
    has_month = month is not None and str(month) != '' and str(month) != 'nan'
    has_day = day is not None and str(day) != '' and str(day) != 'nan'
    has_gz = gz is not None and str(gz) != '' and str(gz) != 'nan'
    has_lp = lp is not None and str(lp) != '' and str(lp) != 'nan'
    stop_at_month = has_month and not has_day and not has_gz and not has_lp
    
    # Normalize month to list
    if has_month and month is not None:
        if isinstance(month, (list, tuple)):
            months = [int(m) for m in month if m is not None and str(m) != '']
        else:
            if month is not None and str(month) != '':
                months = [int(month)]
            else:
                months = []
    else:
        months = []
    

    # lp is already normalized from the DataFrame's lp column
    lp_value = lp if has_lp else None
    
    # Filter lunar table by ind_year and cal_stream
    ind_years = g['ind_year'].dropna().unique()
    if 'cal_stream' in g.columns:
        cal_streams = g['cal_stream'].dropna().unique()
    else:
        # Fallback: use all cal_streams from lunar_table
        cal_streams = lunar_table['cal_stream'].dropna().unique()
    
    lunar_filtered = lunar_table[
        (lunar_table['ind_year'].isin(ind_years)) & 
        (lunar_table['cal_stream'].isin(cal_streams))
    ].copy()
    
    if lunar_filtered.empty:
        return g, updated_implied
    
    # Filter by intercalary if specified
    if intercalary == 1:
        lunar_filtered = lunar_filtered[lunar_filtered['intercalary'] == 1]
        updated_implied['intercalary'] = 1

    # Rename lunar table columns to avoid conflicts with candidate dataframe
    lunar_filtered = lunar_filtered.rename(columns={
        'month': 'lunar_month',
        'intercalary': 'lunar_intercalary'
    })

    # Merge lunar table with candidate dataframe
    cols = [col for col in g.columns if col not in lunar_filtered.columns] + ['cal_stream', 'ind_year']
    g = g[cols]
    g = g.merge(lunar_filtered, how='left', on=['cal_stream', 'ind_year'])
    df = g.copy()
    # For intercalary months, we already filtered lunar table to intercalary entries,
    # so accept them regardless of month matching
    if len(months) > 0 and intercalary != 1:
        df_month = df[df['lunar_month'].isin(months)].copy()
        if not df_month.empty:
            df = df_month
            df['month'] = df['lunar_month']
            df['intercalary'] = df['lunar_intercalary']
            if len(months) == 1:
                updated_implied['month'] = months[0]
        else:
            # Try next month for 晦 (last day of month)
            if lp_value == -1 and len(months) > 0:
                next_months = [m + 1 for m in months]
                df_month = df[df['lunar_month'].isin(next_months)].copy()
                if not df_month.empty:
                    df = df_month
                    updated_implied['month'] = next_months[0]
                else:
                    # Return original candidates if month matching fails completely
                    df = g.copy()
                    df = df[df['month'] == df['lunar_month']].copy()
                    if 'error_str' not in df.columns:
                        df['error_str'] = ""
                    df['error_str'] += phrase_dic.get('year-month-mismatch', 'year-month mismatch; ')
    elif len(months) > 0 and intercalary == 1:
        df = df[(df['month'] == df['lunar_month']) & (df['intercalary'] == df['lunar_intercalary'])].copy()
        if df.empty:
            df = g.copy()
            if not df[df['month'] == df['lunar_month']].empty:
                df = df[df['month'] == df['lunar_month']].copy()
            if 'error_str' not in df.columns:
                df['error_str'] = ""
            df['error_str'] += phrase_dic.get('year-int-month-mismatch', 'Year-int. month mismatch; ')
    else:  # If no month constraint but intercalary
        # Fetch month from lunar table
        # Note: this should be fine, because we have matched on cal_stream and ind_year,
        #       so the only worry is that said year doesn't have an intercalary month.
        if not df.dropna(subset=['lunar_intercalary']).empty:
            df['month'] = df['lunar_month']
        else:
            if 'error_str' not in df.columns:
                df['error_str'] = ""
            df['error_str'] += phrase_dic.get('year-int-month-mismatch', 'Year-int. month mismatch; ')
    
    # Handle stop_at_month case (month only, no day/gz/lp)
    if stop_at_month:
        df = preference_filtering_bulk(df, updated_implied)
        # Generate date ranges
        if 'nmd_jdn' in df.columns and 'hui_jdn' in df.columns:
            df['ISO_Date_Start'] = df['nmd_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
            df['ISO_Date_End'] = df['hui_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
            if 'nmd_gz' in df.columns:
                if not df.dropna(subset=['nmd_gz']).empty:
                    df['start_gz'] = df['nmd_gz'].apply(lambda g: ganshu(g))
                    # Remove duplicate columns before apply
                    df['end_gz'] = df.apply(lambda row: ganshu((row['nmd_gz'] + row['max_day'] - 2) % 60 + 1), axis=1)
        
        return df, updated_implied

    # Handle combinations of day/gz/lp constraints
    if has_lp and has_gz and has_day:
        # Filter
        temp = df.copy()
        temp['_gz'] = ((temp['nmd_gz'] + temp['day'] - 2) % 60) + 1
        temp = temp[temp['gz'] == temp['_gz']]
        del temp['_gz']
        if temp.empty:
            df = g.copy()
            df = df[df['month'] == df['lunar_month']].copy()
            if 'error_str' not in df.columns:
                df['error_str'] = ""
            df['error_str'] += phrase_dic.get('lp-gz-day-mismatch', 'Lunar phase-gz-day mismatch; ')
        else:
            df = temp
            df['jdn'] = df['nmd_jdn'] + df['day'] - 1
    
    if has_lp and not has_gz and not has_day:
        # Lunar phase only (朔 or 晦)
        if lp_value == -1:  # 晦 (last day)
            df['jdn'] = df['nmd_jdn'] + df['max_day'] - 1
            df['day'] = df['max_day']
            df['gz'] = (df['nmd_gz'] + df['max_day'] - 2) % 60 + 1
            df['lp'] = -1
        elif lp_value == 0:  # 朔 (new moon, first day)
            df['jdn'] = df['nmd_jdn']
            df['day'] = 1
            df['gz'] = df['nmd_gz']
            df['lp'] = 0
        
        if 'nmd_gz' in df.columns:
            df = df.drop(columns=['nmd_gz'])
    
    elif has_lp and has_gz and not has_day:
        # Lunar phase + sexagenary day
        if lp_value == -1:  # 晦
            
            df = df[df['gz'] == df['hui_gz']].copy()
            del df['hui_gz']
            if df.empty:
                df = g.copy()
                df = df[df['month'] == df['lunar_month']].copy()
                if 'error_str' not in df.columns:
                    df['error_str'] = ""
                df['error_str'] += phrase_dic.get('lp-gz-mismatch', 'Lunar phase-gz mismatch; ')
            else:
                df['jdn'] = df['hui_jdn']
                df['day'] = df['max_day']
        elif lp_value == 0:  # 朔
            df = df[df['gz'] == df['nmd_gz']].copy()
            if df.empty:
                df = g.copy()
                df = df[df['month'] == df['lunar_month']].copy()
                if 'error_str' not in df.columns:
                    df['error_str'] = ""
                df['error_str'] += phrase_dic.get('lp-gz-mismatch', 'Lunar phase-gz mismatch; ')
            else:
                df['jdn'] = df['nmd_jdn']
                df['day'] = 1
        
        # Check month match
        if len(months) > 0:
            month_match = df[df['lunar_month'].isin(months)]
            if month_match.empty:
                if lp_value == -1:
                    # Try next month
                    next_months = [m + 1 for m in months]
                    month_match = df[df['lunar_month'].isin(next_months)]
                    if not month_match.empty:
                        df = month_match
                        updated_implied['month'] = next_months[0]
                    else:
                        # Return original candidates if month matching fails completely
                        df = g.copy()
                        df = df[df['month'] == df['lunar_month']].copy()
                        df['error_str'] += phrase_dic.get('lp-gz-month-mismatch', 'Lunar phase-gz-month mismatch; ')
                else:
                    # Return original candidates if month matching fails
                    df = g.copy()
                    df = df[df['month'] == df['lunar_month']].copy()
                    df['error_str'] += phrase_dic.get('lp-gz-month-mismatch', 'Lunar phase-gz-month mismatch; ')
            else:
                df = month_match
    
    elif has_gz and has_day and not has_lp:
        # Sexagenary day + numeric day
        df['jdn'] = df['nmd_jdn'] + day - 1
        df['jdn2'] = ((gz - df['nmd_gz']) % 60) + df['nmd_jdn']
        df = df[df['jdn'] == df['jdn2']].copy()
        df = df.drop(columns=['jdn2'])
        
        if not df.empty:
            df['day'] = day
            df['gz'] = gz
            # Check if day is within month bounds
            df = df[df['day'] <= df['max_day']]
            if df.empty:
                # Return original candidates if day filtering results in no matches
                df = g.copy()
                df = df[df['month'] == df['lunar_month']].copy()
                df['error_str'] += phrase_dic.get('month-day-gz-mismatch', 'Month-day-gz mismatch; ')
        else:
            df = g.copy()
            df = df[df['month'] == df['lunar_month']].copy()
            df['error_str'] += "Month-day-gz mismatch; "
    
    elif has_gz and not has_day and not has_lp:
        # Sexagenary day only
        df['day'] = ((gz - df['nmd_gz']) % 60) + 1
        df = df[df['day'] <= df['max_day']]
        if df.empty:
            df = g.copy()
            df = df[df['month'] == df['lunar_month']].copy()
            if 'error_str' not in df.columns:
                df['error_str'] = ""
            df['error_str'] += phrase_dic.get('month-day-gz-oob', 'Month-day-gz mismatch (out of bounds); ')
        else:
            df = preference_filtering_bulk(df, updated_implied)

            if len(months) > 0:
                month_match = df[df['lunar_month'].isin(months)]
                if month_match.empty:
                    # Try next month
                    next_months = [m + 1 for m in months]
                    month_match = df[df['month'].isin(next_months)]
                    if not month_match.empty:
                        df = month_match
                        updated_implied['month'] = next_months[0]
                        if 'error_str' not in df.columns:
                            df['error_str'] = ""
                        df['error_str'] += phrase_dic.get('month-gz-mismatch', 'Month-gz mismatch; ')
                    else:
                        # Return original candidates if month matching fails
                        df = g.copy()
                        df = df[df['month'] == df['lunar_month']].copy()
                        if 'error_str' not in df.columns:
                            df['error_str'] = ""
                        df['error_str'] += phrase_dic.get('month-gz-mismatch', 'Month-gz mismatch; ')
                else:
                    df = month_match
            
            df['jdn'] = df['day'] + df['nmd_jdn'] - 1
            df['gz'] = gz
            if 'nmd_gz' in df.columns:
                df = df.drop(columns=['nmd_gz'])
    
    elif has_day and not has_gz and not has_lp:
        # Numeric day only
        df['day'] = day
        df['jdn'] = df['day'] + df['nmd_jdn'] - 1
        if 'nmd_gz' in df.columns:
            df['gz'] = (df['nmd_gz'] + day - 2) % 60 + 1
            df = df.drop(columns=['nmd_gz'])
        
        df = df[df['day'] <= df['max_day']]
        if df.empty:
            # Return original candidates if day filtering results in no matches
            df = g.copy()
            df = df[df['month'] == df['lunar_month']].copy()
            if 'error_str' not in df.columns:
                df['error_str'] = ""
            df['error_str'] += phrase_dic.get('month-day-oob', 'Month-day mismatch (out of bounds); ')
    
    # Clean up and add names
    df = preference_filtering_bulk(df, updated_implied)
    
    # Apply date range filter
    if df.shape[0] > 1 and 'ind_year' in df.columns:
        temp = df[(df['ind_year'] >= tpq) & (df['ind_year'] <= taq)].copy()
        if not temp.empty:
            df = temp
    
    # Calculate ISO dates if we have JDN
    if 'jdn' in df.columns:
        df['ISO_Date'] = df['jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
    
    # Update implied state
    if 'month' in df.columns:
        month_vals = df['month'].dropna().unique()
        if len(month_vals) == 1:
            updated_implied['month'] = int(month_vals[0])

    imp_ls = ['cal_stream', 'dyn_id', 'ruler_id', 'era_id']
    for i in imp_ls:
        if i in df.columns:
            unique_vals = df.dropna(subset=[i])[i].unique()
            if len(unique_vals) == 1:
                updated_implied.update({f'{i}_ls': list(unique_vals)})
    
    if df.empty:
        df = g.copy()
        df = df[df['month'] == df['lunar_month']].copy()
        if 'error_str' not in df.columns:
            df['error_str'] = ""
        df['error_str'] += phrase_dic.get('lunar-constraint-failed', 'Anomaly in lunar constraint solving; ')
    
    return df, updated_implied