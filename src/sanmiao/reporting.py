import re
import pandas as pd
from .converters import (
    gz_year, ganshu, numcon, iso_to_jdn, jdn_to_iso, jdn_to_gz
)
from .config import (
    phrase_dic_en, get_phrase_dic
)
from .loaders import (
    prepare_tables, load_csv
)
from .utils import guess_variant


def generate_report_from_dataframe(output_df, phrase_dic=phrase_dic_en, jd_out=False, tpq=None, taq=None):
    """
    Generate human-readable report from processed dataframe.

    :param output_df: DataFrame with processed date results (includes error_str, date_string, etc.)
    :param phrase_dic: Dictionary with UI phrases
    :param jd_out: Whether to output Julian Day numbers
    :param tpq: Terminus post quem (earliest date filter)
    :param taq: Terminus ante quem (latest date filter)
    :return: Formatted report string
    """
    if output_df.empty:
        return f'{phrase_dic["ui"]}: {phrase_dic["unknown-date"]}\n{phrase_dic["matches"]}:\n{phrase_dic["no-matches"]}'

    # Add missing columns with NaN values (so they can be used in boolean operations)
    cols = ["dyn_name", "ruler_name", "era_name", "year", "sex_year", "month", "intercalary", "day", "gz", "lp", "nmd_gz"]
    for col in cols:
        if col not in output_df.columns:
            output_df[col] = pd.NA
    
    # Check if any rows have resolved historical entities (dyn_id, ruler_id, or era_id)
    has_resolved_entities = (
        ('dyn_id' in output_df.columns and output_df['dyn_id'].notna().any()) or
        ('ruler_id' in output_df.columns and output_df['ruler_id'].notna().any()) or
        ('era_id' in output_df.columns and output_df['era_id'].notna().any())
    )

    if not has_resolved_entities:
        # Format as a proper report entry
        if not output_df.empty and 'date_string' in output_df.columns:
            date_string = output_df['date_string'].iloc[0]
        else:
            date_string = "unknown date"
        return f'{phrase_dic["ui"]}: {date_string}\n{phrase_dic["matches"]}:\n{phrase_dic["insuff-data"]}'

    # Check for too many candidates - filter by tpq/taq if provided
    if len(output_df) > 15:
        # Filter by tpq/taq if provided
        if tpq is not None or taq is not None:
            # Use ind_year if available, otherwise use era_start_year or era_end_year
            filter_mask = pd.Series([True] * len(output_df), index=output_df.index)
            
            if 'ind_year' in output_df.columns:
                if tpq is not None:
                    filter_mask &= output_df['ind_year'].notna() & (output_df['ind_year'] >= tpq)
                if taq is not None:
                    filter_mask &= output_df['ind_year'].notna() & (output_df['ind_year'] <= taq)
            elif 'era_start_year' in output_df.columns:
                if tpq is not None:
                    filter_mask &= output_df['era_start_year'].notna() & (output_df['era_start_year'] >= tpq)
                if taq is not None:
                    filter_mask &= output_df['era_start_year'].notna() & (output_df['era_start_year'] <= taq)
            elif 'era_end_year' in output_df.columns:
                if tpq is not None:
                    filter_mask &= output_df['era_end_year'].notna() & (output_df['era_end_year'] >= tpq)
                if taq is not None:
                    filter_mask &= output_df['era_end_year'].notna() & (output_df['era_end_year'] <= taq)
            
            output_df = output_df[filter_mask].copy()
        
        # If still too many after filtering, return error message
        if len(output_df) > 15:
            date_string = output_df['date_string'].iloc[0] if not output_df.empty and 'date_string' in output_df.columns else "unknown date"
            return f'{phrase_dic["ui"]}: {date_string}\n{phrase_dic["matches"]}:\n{len(output_df)} {phrase_dic["too-many-cand"]}'

    # Prepare dataframe for vectorized formatting
    df = output_df.copy()

    # If this date has a relative year marker, append a simple warning to error_str
    # (we keep using existing rel_* columns; no new schema required).
    if all(c in df.columns for c in ["rel_dir", "rel_unit"]):
        rel_dir = df["rel_dir"].astype("string").str.strip()
        rel_unit = df["rel_unit"].astype("string").str.strip()
        relative_dirs = {"明", "來", "次", "去", "昨", "前", "後"}
        is_relative_year = rel_unit.isin(["年", "歲"]) & rel_dir.isin(list(relative_dirs))
        if is_relative_year.any():
            if "error_str" not in df.columns:
                df["error_str"] = ""
            # Avoid duplicating if upstream already added the warning.
            existing = df.loc[is_relative_year, "error_str"].fillna("")
            needs = ~existing.str.contains("relative date", regex=False)
            df.loc[is_relative_year & needs, "error_str"] = existing[needs] + "relative date"

    # Ensure strings for concatenation (handle missing columns)
    for col in ["dyn_name", "ruler_name", "era_name"]:
        if col in df.columns:
            df[col] = df[col].fillna("")
        else:
            df[col] = ""

    # Format year strings
    df["year_str"] = ""
    mask = df["year"].notna()
    df.loc[mask & (df["year"] == 1), "year_str"] = "元年"
    df.loc[mask & (df["year"] != 1), "year_str"] = df.loc[mask & (df["year"] != 1) & df["year"].notna(), "year"].astype(int).map(lambda x: str(numcon(x)) + "年")
    
    # Format month strings
    df["month_str"] = ""
    m = df["month"].notna()
    df.loc[m & (df["month"] == 1), "month_str"] = "正月"
    df.loc[m & (df["month"] == 13), "month_str"] = "臘月"
    df.loc[m & (df["month"] == 14), "month_str"] = "一月"
    df.loc[m & ~df["month"].isin([1, 13, 14]), "month_str"] = df.loc[m & ~df["month"].isin([1, 13, 14]), "month"].astype(int).map(lambda x: str(numcon(x)) + "月")

    # Intercalary marker
    df["int_str"] = ""
    df.loc[df.get("intercalary", pd.Series(0, index=df.index, dtype=int)) == 1, "int_str"] = "閏"

    # Day strings
    df["day_str"] = ""
    d = (df["day"].notna()) & (df["lp"] != 0)
    df.loc[d, "day_str"] = df.loc[d & df["day"].notna(), "day"].astype(int).map(lambda x: str(numcon(x)) + "日")

    # Sexagenary day
    df["gz_str"] = ""
    gz_mask = df["gz"].notna()
    df.loc[gz_mask, "gz_str"] = df.loc[gz_mask & df["gz"].notna(), "gz"].astype(int).map(ganshu)

    # Lunar phase
    df["lp_str"] = ""
    lp_mask = df["lp"].notna()
    lp_d = {0: '朔', -1: '晦'}
    df.loc[lp_mask, "lp_str"] = df.loc[lp_mask & df["lp"].notna(), "lp"].astype(int).map(lambda x: lp_d.get(x, ''))

    # Date range strings
    df["range_str"] = ""

    # Era year spans for dynasty/ruler/era only dates (no year specified)
    try:
        if (not df.empty and "era_start_year" in df.columns and "era_end_year" in df.columns and
            "year" in df.columns and "month" in df.columns and "day" in df.columns and
            "gz" in df.columns and "lp" in df.columns):
            era_only_mask = (
                df["era_start_year"].notna() & df["era_end_year"].notna() &
                df["year"].isna() & df["month"].isna() & df["day"].isna() & df["gz"].isna() & df["lp"].isna()
            )
            df.loc[era_only_mask, "range_str"] = (
                "年間（" + df.loc[era_only_mask & df["era_start_year"].notna() & df["era_end_year"].notna(), "era_start_year"].astype(int).astype(str) +
                "–" + df.loc[era_only_mask & df["era_start_year"].notna() & df["era_end_year"].notna(), "era_end_year"].astype(int).astype(str) + "）"
            )
        # else: no era processing needed
    except Exception:
        # If anything goes wrong with era processing, skip it
        pass
    
    # Lunar month ranges (for month-only dates)
    # Only create lunar range strings if the necessary lunar columns exist
    if all(col in df.columns for col in ["nmd_gz", "ISO_Date_Start", "start_gz", "ISO_Date_End", "end_gz"]):
        lunar_range_mask = (
            df["month"].notna() & df["day"].isna() & df["gz"].isna() & df["lp"].isna() &
            df["nmd_gz"].notna() & df["ISO_Date_Start"].notna()
        )
        if jd_out:
            df.loc[lunar_range_mask, "range_str"] = (
                "（JD " + df.loc[lunar_range_mask, "nmd_jdn"].astype(str) +
                " ~ " + df.loc[lunar_range_mask, "hui_jdn"].astype(str) + "）"
            )
        else:
            df.loc[lunar_range_mask, "range_str"] = (
                "（" + df.loc[lunar_range_mask, "start_gz"] +
                df.loc[lunar_range_mask, "ISO_Date_Start"] +
                " ~ " + df.loc[lunar_range_mask, "end_gz"] +
                df.loc[lunar_range_mask, "ISO_Date_End"] + "）"
            )

    # Final date strings
    df["jdn_str"] = ""

    # For dates with specific JDN (calculated from day/gz/lp)
    if "jdn" in df.columns:
        jdn_mask = df["jdn"].notna()
        if jd_out:
            df.loc[jdn_mask, "jdn_str"] = "（JD " + df.loc[jdn_mask, "jdn"].astype(str) + "）"
        elif "ISO_Date" in df.columns:
            iso_mask = jdn_mask & df["ISO_Date"].notna()
            df.loc[iso_mask, "jdn_str"] = "（" + df.loc[iso_mask, "ISO_Date"] + "）"

    # For dates with years but no specific JDN, show western year
    if "ind_year" in df.columns:
        year_only_mask = (
            df["ind_year"].notna() &
            (df["jdn"].isna() if "jdn" in df.columns else True) &
            df["year"].notna() & df["month"].isna() & df["day"].isna() & df["gz"].isna() & df["lp"].isna()
        )
        df.loc[year_only_mask, "jdn_str"] = "（" + df.loc[year_only_mask & df["ind_year"].notna(), "ind_year"].astype(int).astype(str) + "）"

    # Sexagenary year (like in jy_to_ccs)
    df["sex_year_str"] = ""
    if "ind_year" in df.columns:
        sex_year_mask = df["ind_year"].notna()
        df.loc[sex_year_mask, "sex_year_str"] = df.loc[sex_year_mask & df["ind_year"].notna(), "ind_year"].astype(int).map(lambda y: f"（歲在{ganshu(gz_year(y))}）")

    # Combine all components into report_line
    df["report_line"] = (
        df["dyn_name"] + df["ruler_name"] + df["era_name"] +
        df["year_str"] + df["sex_year_str"] + df["int_str"] + df["month_str"] +
        df["day_str"] + df["gz_str"] + df["lp_str"] +
        df["range_str"] + df["jdn_str"]
    )

    # Group by date_index and combine lines
    # Deduplicate report_line values to avoid showing the same line multiple times
    lines_by_date = (
        df.groupby("date_index")["report_line"]
        .agg(lambda s: "\n".join([x for x in s.unique() if x]))
    )

    # Generate final report with headers and errors
    # Group by date_index to get metadata for each date
    metadata_by_date = df.groupby("date_index").agg({
        "date_string": "first",  # All rows for same date_index have same date_string
        "error_str": lambda x: next((s for s in x if s), "")  # Get first non-empty error_str
    })

    report_blocks = []
    for idx, meta in metadata_by_date.iterrows():
        header = f'{phrase_dic["ui"]}: {meta["date_string"]}\n{phrase_dic["matches"]}:\n'
        body = lines_by_date.get(idx, "")
        err = meta["error_str"] or ""
        block = header + (body + "\n" if body else "") + err
        report_blocks.append(block.rstrip())

    return "\n\n".join(report_blocks)


def jdn_to_ccs(x, by_era=True, proleptic_gregorian=False, gregorian_start=None, lang='en', civ=None):
    """
    Convert Julian Day Number to Chinese calendar string.
    :param x: float (Julian Day Number) or str (ISO date string Y-M-D)
    :param by_era: bool (filter from era JDN vs index year)
    :param proleptic_gregorian: bool
    :param gregorian_start: list
    :param lang: str, language ('en', 'fr', 'zh', 'ja', 'de'). Defaults to 'en' if not specified or invalid.
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return output_string: str
    """
    # Defaults
    if gregorian_start is None:
        gregorian_start = [1582, 10, 15]
    if civ is None:
        civ = ['c', 'j', 'k']
    if lang is None:
        lang = 'en'
    phrase_dic = get_phrase_dic(lang)
    if isinstance(x, str):
        iso = x
        jdn = iso_to_jdn(x, proleptic_gregorian, gregorian_start)
    else:
        jdn = x
        iso = jdn_to_iso(jdn, proleptic_gregorian, gregorian_start)
    output_string = f'{phrase_dic.get("ui")}: {iso} (JD {jdn})\n{phrase_dic.get("matches")}:\n'
    # Load CSV tables
    era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = prepare_tables(civ=civ)
    # Filter ruler_tag_df by filtered rulers
    if not ruler_df.empty:
        valid_person_ids = ruler_df['person_id'].unique()
        ruler_tag_df = ruler_tag_df[ruler_tag_df['person_id'].isin(valid_person_ids)]
    # Filter lunar table by JDN
    lunar_table = lunar_table[(lunar_table['nmd_jdn'] <= jdn) & (lunar_table['hui_jdn'] + 1 > jdn)]
    #
    if by_era:
        # Filter era dataframe by JDN
        df = era_df[(era_df['era_start_jdn'] <= jdn) & (era_df['era_end_jdn'] > jdn)].drop_duplicates(subset=['era_id'])
        df = df[['dyn_id', 'cal_stream', 'era_id', 'ruler_id', 'era_name', 'era_start_year']].rename(columns={'ruler_id': 'person_id'})
        # Get ruler names
        df = df.merge(ruler_can_names, how='left', on='person_id')
        df = df.rename(columns={'person_id': 'ruler_id', 'string': 'ruler_name'})
        # Get dynasty names
        df = df.merge(dyn_df[['dyn_id', 'dyn_name']], how='left', on='dyn_id')
        # Merge with lunar table
        lunar_table = df.merge(lunar_table, how='left', on='cal_stream')
        # Add ruler start year, just to be safe
        temp = ruler_df[['person_id', 'emp_start_year']]
        temp = temp.rename(columns={'person_id': 'ruler_id'})
        lunar_table = lunar_table.merge(temp, how='left', on='ruler_id')
    else:
        # Merge dynasties
        lunar_table = lunar_table.merge(dyn_df, how='left', on='cal_stream')
        # Filter by index year
        lunar_table = lunar_table[lunar_table['dyn_start_year'] <= lunar_table['ind_year']]
        lunar_table = lunar_table[lunar_table['dyn_end_year'] > lunar_table['ind_year']]
        del lunar_table['dyn_start_year'], lunar_table['dyn_end_year']
        # Merge rulers
        del ruler_df['cal_stream'], ruler_df['max_year']
        lunar_table = lunar_table.merge(ruler_df, how='left', on='dyn_id')
        # Merge ruler tags
        lunar_table = lunar_table.merge(ruler_tag_df, how='left', on='person_id')
        lunar_table = lunar_table.rename(columns={'person_id': 'ruler_id', 'string': 'ruler_name'})
        # Filter by index year
        lunar_table = lunar_table[lunar_table['emp_start_year'] <= lunar_table['ind_year']]
        lunar_table = lunar_table[lunar_table['emp_end_year'] > lunar_table['ind_year']]
        del lunar_table['emp_end_year']
        # Clean eras
        del era_df['max_year']
        era_df = era_df.drop_duplicates(subset=['era_id'])
        # Merge eras
        lunar_table = lunar_table.merge(era_df, how='left', on=['dyn_id', 'cal_stream', 'ruler_id'])
        # Filter by index year
        lunar_table = lunar_table[lunar_table['era_start_year'] <= lunar_table['ind_year']]
        lunar_table = lunar_table[lunar_table['era_end_year'] > lunar_table['ind_year']]
        del lunar_table['era_end_year']
    if not lunar_table.empty:
        lunar_table = lunar_table.sort_values(by=['cal_stream', 'dyn_id'])
        lunar_table = lunar_table.drop_duplicates(subset=['era_id'])
        # Create strings
        for index, row in lunar_table.iterrows():
            # Output dynasty and ruler name
            output_string += f"{row['dyn_name']}{row['ruler_name']}"
            # Find Julian year
            iso_string = jdn_to_iso(jdn, proleptic_gregorian, gregorian_start)
            if iso_string[0] == '-':
                iso_string = iso_string[1:]
                mult = -1
            else:
                mult = 1
            year = int(re.split('-', iso_string)[0]) * mult
            # Convert to era or ruler year
            # Check if era_start_year is valid (not NaN) - works for both int and float
            if pd.notna(row['era_start_year']):
                # We have a valid era, use it (even if era_name is blank)
                if isinstance(row['era_name'], str) and row['era_name'] != '':
                    output_string += f"{row['era_name']}"
                # Find era year
                era_year = year - int(row['era_start_year']) + 1
                era_year = numcon(era_year) + '年'
                if era_year == "一年":
                    era_year = "元年"
                output_string += era_year
            else:
                # No valid era, fall back to ruler start year
                ruler_year = year - row['emp_start_year'] + 1
                ruler_year = numcon(ruler_year) + '年'
                if ruler_year == "一年":
                    ruler_year = "元年"
                output_string += ruler_year
            # Sexegesimal year
            sex_year = ganshu(row['year_gz'])
            output_string += f"（歲在{sex_year}）"
            # Month
            if row['intercalary'] == 1:
                output_string += '閏'
            if row['month'] == 1:
                month = '正月'
            elif row['month'] == 13:
                month = '臘月'
            elif row['month'] == 14:
                month = '一月'
            else:
                month = numcon(row['month']) + '月'
            output_string += month
            # Find day
            if int(jdn - .5) + .5 == row['nmd_jdn']:
                day = '朔'
            elif int(jdn - .5) + .5 == row['hui_jdn']:
                num = numcon(row['hui_jdn'] - row['nmd_jdn'] + 1) + '日'
                day = f"晦（{num}）"
            else:
                day = numcon(int(jdn - row['nmd_jdn']) + 1) + '日'
            output_string += day
            # Sexagenary day
            output_string += jdn_to_gz(jdn)
            # Line break
            output_string += '\n'
        output_string = output_string[:-1]
        # Output
        return output_string
    else:
        return None


def jy_to_ccs(y, lang='en', civ=None):
    """
    Convert Western year to Chinese calendar string.
    :param y: int
    :param lang: str, language ('en', 'fr', 'zh', 'ja', 'de'). Defaults to 'en' if not specified or invalid.
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return output_string: str
    """
    # Defaults
    if civ is None:
        civ = ['c', 'j', 'k']
    if lang is None:
        lang = 'en'
    phrase_dic = get_phrase_dic(lang)
    
    # Year format strings for different languages
    if y > 0:
        if lang == 'en':
            fill = f"A.D. {int(y)}"
        elif lang == 'fr':
            fill = f"{int(y)} apr. J.-C."
        elif lang == 'de':
            fill = f"{int(y)} n. Chr."
        elif lang == 'zh':
            fill = f"公元{int(y)}年"
        elif lang == 'ja':
            fill = f"西暦{int(y)}年"
        else:
            fill = f"A.D. {int(y)}"  # Default to English
    else:
        if lang == 'en':
            fill = f"{int(abs(y)) + 1} B.C."
        elif lang == 'fr':
            fill = f"{int(abs(y)) + 1} av. J.-C."
        elif lang == 'de':
            fill = f"{int(abs(y)) + 1} v. Chr."
        elif lang == 'zh':
            fill = f"公元前{int(abs(y)) + 1}年"
        elif lang == 'ja':
            fill = f"紀元前{int(abs(y)) + 1}年"
        else:
            fill = f"{int(abs(y)) + 1} B.C."  # Default to English
    output_string = f'{phrase_dic.get("ui")}: {y} ({fill})\n{phrase_dic.get("matches")}:\n'
    # Load CSV tables
    era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = prepare_tables(civ=civ)
    # Filter ruler_tag_df by filtered rulers
    if not ruler_df.empty:
        valid_person_ids = ruler_df['person_id'].unique()
        ruler_tag_df = ruler_tag_df[ruler_tag_df['person_id'].isin(valid_person_ids)]
    ruler_tag_df = ruler_tag_df[['person_id', 'string']]
    # Filter dynasties by year
    df = dyn_df[(dyn_df['dyn_start_year'] <= y) & (dyn_df['dyn_end_year'] >= y)]
    cols = ['dyn_id', 'dyn_name', 'cal_stream']
    df = df[cols]
    # Merge rulers
    del ruler_df['cal_stream']
    df = df.merge(ruler_df, how='left', on=['dyn_id'])
    # Filter by year
    df = df[(df['emp_start_year'] <= y) & (df['emp_end_year'] >= y)]
    # Merge ruler strings
    df = df.merge(ruler_tag_df, how='left', on='person_id')
    df = df.rename(columns={'person_id': 'ruler_id', 'string': 'ruler_name'})
    cols = ['dyn_id', 'dyn_name', 'cal_stream', 'ruler_id', 'emp_start_year', 'ruler_name']
    df = df[cols]
    # Merge era
    era_df = era_df[['era_id', 'ruler_id', 'era_name', 'era_start_year', 'era_end_year']]
    df = df.merge(era_df, how='left', on='ruler_id')
    # Filter by year
    df = df[(df['era_start_year'] <= y) & (df['era_end_year'] >= y)].sort_values(by=['cal_stream', 'dyn_id'])
    # Filter duplicates
    try:
        df['variant_rank'] = df['era_name'].apply(guess_variant)
        df = (
            df.sort_values(by='variant_rank')
            .drop_duplicates(subset=['ruler_id', 'era_id'], keep="first")
            .drop(columns="variant_rank")
        )
    except TypeError:
        df = df.drop_duplicates(subset=['ruler_id', 'era_id'], keep="first")
    if not df.empty:
        # Create strings
        for index, row in df.iterrows():
            # Output dynasty and ruler name
            output_string += f"{row['dyn_name']}{row['ruler_name']}"
            # Convert to era or ruler year
            if isinstance(row['era_name'], str):
                output_string += f"{row['era_name']}"
                # Find era year
                era_year = y - row['era_start_year'] + 1
                era_year = numcon(era_year) + '年'
                if era_year == "一年":
                    era_year = "元年"
                output_string += era_year
            else:
                ruler_year = y - row['emp_start_year'] + 1
                ruler_year = numcon(ruler_year) + '年'
                if ruler_year == "一年":
                    ruler_year = "元年"
                output_string += ruler_year
            # Sexegesimal year
            sex_year = ganshu(gz_year(y))
            output_string += f"（歲在{sex_year}）"
            # Line break
            output_string += '\n'
        output_string = output_string[:-1]
        # Output
        return output_string
    else:
        return None