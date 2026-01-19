# Date conversion utilities for sanmiao

import re
import pandas as pd
from math import floor
from typing import Tuple, Union

from .config import normalize_defaults, get_phrase_dic
from .loaders import load_csv, load_num_tables
from .utils import guess_variant

# Ganzhi conversion constants
_GANZHI_ZH_TO_NUM = {
    '甲子': 1, '乙丑': 2, '丙寅': 3, '丁卯': 4, '戊辰': 5, '己巳': 6, '庚午': 7, '辛未': 8, '壬申': 9, '癸酉': 10,
    '甲戌': 11, '乙亥': 12, '丙子': 13, '丁丑': 14, '戊寅': 15, '己卯': 16, '庚辰': 17, '辛巳': 18, '壬午': 19, '癸未': 20,
    '甲申': 21, '乙酉': 22, '丙戌': 23, '丁亥': 24, '戊子': 25, '己丑': 26, '庚寅': 27, '辛卯': 28, '壬辰': 29, '癸巳': 30,
    '甲午': 31, '乙未': 32, '丙申': 33, '丁酉': 34, '戊戌': 35, '己亥': 36, '庚子': 37, '辛丑': 38, '壬寅': 39, '癸卯': 40,
    '甲辰': 41, '乙巳': 42, '丙午': 43, '丁未': 44, '戊申': 45, '己酉': 46, '庚戌': 47, '辛亥': 48, '壬子': 49, '癸丑': 50,
    '甲寅': 51, '乙卯': 52, '丙辰': 53, '丁巳': 54, '戊午': 55, '己未': 56, '庚申': 57, '辛酉': 58, '壬戌': 59, '癸亥': 60,
}
_NUM_TO_GANZHI_ZH = {v: k for k, v in _GANZHI_ZH_TO_NUM.items()}

_GANZHI_PINYIN_TO_NUM = {
    'jiazi': 1, 'yichou': 2, 'bingyin': 3, 'dingmao': 4, 'wuchen': 5, 'jisi': 6, 'gengwu': 7, 'xinwei': 8, 'renshen': 9, 'guiyou': 10,
    'jiaxu': 11, 'yihai': 12, 'bingzi': 13, 'dingchou': 14, 'wuyin': 15, 'jimao': 16, 'gengchen': 17, 'xinsi': 18, 'renwu': 19, 'guiwei': 20,
    'jiashen': 21, 'yiyou': 22, 'bingxu': 23, 'dinghai': 24, 'wuzi': 25, 'jichou': 26, 'gengyin': 27, 'xinmao': 28, 'renchen': 29, 'guisi': 30,
    'jiawu': 31, 'yiwei': 32, 'bingshen': 33, 'dingyou': 34, 'wuxu': 35, 'jihai': 36, 'gengzi': 37, 'xinchou': 38, 'renyin': 39, 'guimao': 40,
    'jiachen': 41, 'yisi': 42, 'bingwu': 43, 'dingwei': 44, 'wushen': 45, 'jiyou': 46, 'gengxu': 47, 'xinhai': 48, 'renzi': 49, 'guichou': 50,
    'jiayin': 51, 'yimao': 52, 'bingchen': 53, 'dingsi': 54, 'wuwu': 55, 'jiwei': 56, 'gengshen': 57, 'xinyou': 58, 'renxu': 59, 'guihai': 60,
}
_NUM_TO_GANZHI_PINYIN = {v: k for k, v in _GANZHI_PINYIN_TO_NUM.items()}


def gz_year(num: int) -> int:
    """
    Converts Western calendar year to sexagenary year (numerical)
    :param num: int
    :return: int
    """
    x = (num - 4) % 60 + 1
    return x


def jdn_to_gz(jdn: int, en: bool = False) -> str:
    """
    Convert from Julian day number (JDN) to sexagenary day, with output in Pinyin (en=True) or Chinese (en=False).
    :param jdn: float
    :param en: bool
    """
    jdn = int(jdn - 9.5) % 60
    if jdn == 0:
        jdn = 60
    gz = ganshu(jdn, en)
    return gz


def ganshu(gz_in, en=False):
    """
    Convert from sexagenary counter (string) to number (int) and vice versa.
    :param gz_in: str, int, or float
    :param en: Boolean, whether into Pinyin (vs Chinese)
    :return: int or str
    """

    if en:
        to_num = _GANZHI_PINYIN_TO_NUM
        to_str = _NUM_TO_GANZHI_PINYIN
    else:
        to_num = _GANZHI_ZH_TO_NUM
        to_str = _NUM_TO_GANZHI_ZH

    # string -> number
    if isinstance(gz_in, str):
        s = gz_in.strip()
        # Normalise for Chen dynasty taboo
        if not en:
            s = re.sub('景', '丙', s)
            return to_num.get(s, None)
        else:
            s = s.lower()
        out = to_num.get(s, None)
        if out is None:
            raise ValueError(f"Invalid ganzhi string: {gz_in}")
        return out

    # number -> string
    try:
        n = int(gz_in)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid ganzhi string: {gz_in}")
        return None

    return to_str.get(n, None)


def numcon(x):
    """
    Convert Chinese numerals into arabic numerals (from 9999 down) and from arabic into Chinese (from 99 down)
    :param x: str, int, or float
    :return: int
    """
    chinese_numerals = '〇一二三四五六七八九'
    if isinstance(x, str):  # If string
        if x in ['正月', '元年']:
            return 1
        else:
            # Normalize number string
            tups = [
                ('元', '一'),
                ('廿', '二十'), ('卅', '三十'), ('卌', '四十'), ('兩', '二'),
                ('初', '〇'), ('無', '〇'), ('卄', '二十'), ('丗', '三十')
            ]
            for tup in tups:
                x = re.sub(tup[0], tup[1], x)
            # Variables
            arab_numerals = '0123456789'
            w_place_values = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '〇', '百', '千', '萬']
            # Remove all non number characters
            only_numbers = ''
            for char in x:
                if char in w_place_values:
                    only_numbers += char
            # Convert to Frankenstein string
            frankenstein = only_numbers.translate(str.maketrans(chinese_numerals, arab_numerals))
            # Determine if place value words occur
            place_values = ['十', '百', '千', '萬']
            count = 0
            for i in place_values:
                if i in frankenstein:
                    count = 1
                    break
            # Logic tree
            if count == 0:  # If there are no place values
                # Try to return as integer
                if frankenstein.strip():  # Only try to convert non-empty strings
                    try:
                        return int(frankenstein)
                    except (ValueError, TypeError):
                        return None
                else:
                    return None
            else:  # If there are place value words
                # Remove zeros
                frankenstein = frankenstein.replace('0', '')
                # Empty result to which to add each place value
                numeral = 0
                # Thousands
                thousands = frankenstein.split('千')
                if len(thousands) == 2 and len(thousands[0]) == 0:
                    numeral += 1000
                elif len(thousands) == 2 and len(thousands[0]) == 1:
                    numeral += 1000 * int(thousands[0])
                # Hundreds
                hundreds = thousands[-1].split('百')
                if len(hundreds) == 2 and len(hundreds[0]) == 0:
                    numeral += 100
                elif len(hundreds) == 2 and len(hundreds[0]) == 1:
                    numeral += 100 * int(hundreds[0])
                # Tens
                tens = hundreds[-1].split('十')
                if len(tens) == 2 and len(tens[0]) == 0:
                    numeral += 10
                elif len(tens) == 2 and len(tens[0]) == 1:
                    numeral += 10 * int(tens[0])
                remainder = tens[-1]
                # Units
                try:
                    numeral += int(remainder[0])
                except (IndexError, ValueError):
                    # If remainder is empty or not a digit, skip it
                    pass
                return int(numeral)
    else:  # To convert from integer/float to Chinese
        x = int(x)
        # Blank string
        s = ''
        # Find number of thousands
        x %= 10000
        thousands = x // 1000
        if thousands > 0:
            if thousands > 1:
                s += chinese_numerals[thousands]
            s += '千'
        # Find number of hundreds
        x %= 1000
        hundreds = x // 100
        if hundreds > 0:
            if hundreds > 1:
                s += chinese_numerals[hundreds]
            s += '百'
        # Find number of tens
        x %= 100
        tens = x // 10
        if tens > 0:
            if tens > 1:
                s += chinese_numerals[tens]
            s += '十'
        # Find units
        rem = int(x % 10)
        if rem > 0:
            s += chinese_numerals[rem]
        return s


def iso_to_jdn(date_string, proleptic_gregorian=False, gregorian_start=None):
    """
    Convert a date string (YYYY-MM-DD) to a Julian Day Number (JDN).

    :param date_string: str (date in "YYYY-MM-DD" format, e.g., "2023-01-01" or "-0044-03-15")
    :param proleptic_gregorian: bool
    :param gregorian_start: list
    :return: float (Julian Day Number) or None if invalid
    """
    # Defaults
    gregorian_start, civ = normalize_defaults(gregorian_start)

    # Validate inputs
    if not re.match(r'^-?\d+-\d+-\d+$', date_string):
        return None

    try:
        # Handle negative year
        if date_string[0] == '-':
            mult = -1
            date_string = date_string[1:]
        else:
            mult = 1

        # Split and convert to integers
        year, month, day = map(int, date_string.split("-"))
        year *= mult

        # Validate month and day
        if not (1 <= month <= 12) or not (1 <= day <= 31):  # Basic validation
            return None

        # Determine calendar for historical mode
        is_julian = False
        a, b, c = gregorian_start
        if not proleptic_gregorian:
            if year < a:
                is_julian = True
            elif year == a and month < b:
                is_julian = True
            elif year == a and month == b and day <= c:
                is_julian = True

        # Adjust months and years so March is the first month
        if month <= 2:
            year -= 1
            month += 12

        # Calculate JDN
        if proleptic_gregorian or not is_julian:
            # Gregorian calendar
            a = floor(year / 100)
            b = floor(a / 4)
            c = 2 - a + b
            jdn = floor(365.25 * (year + 4716)) + floor(30.6001 * (month + 1)) + day + c - 1524.5
        else:
            # Julian calendar
            jdn = floor(365.25 * (year + 4716)) + floor(30.6001 * (month + 1)) + day - 1524.5

        return jdn
    except ValueError:
        return None


def jdn_to_iso(jdn, proleptic_gregorian=False, gregorian_start=None):
    """
    Convert a Julian Day Number (JDN) to a date string (YYYY-MM-DD).

    :param jdn: int or float (e.g., 2299159.5 = 1582-10-15)
    :param proleptic_gregorian: bool
    :param gregorian_start: list
    :return: str (ISO date string) or None if invalid
    """
    # Defaults
    gregorian_start, civ = normalize_defaults(gregorian_start)

    # Get Gregorian reform JDN
    gs_str = f"{gregorian_start[0]}-{gregorian_start[1]}-{gregorian_start[2]}"
    gs_jdn = iso_to_jdn(gs_str, proleptic_gregorian, gregorian_start)
    if not isinstance(jdn, (int, float)):
        return None
    try:
        jdn = floor(jdn + 0.5)
        is_julian = not proleptic_gregorian and jdn < gs_jdn
        if proleptic_gregorian or not is_julian:
            a = jdn + 32044
            b = floor((4 * a + 3) / 146097)
            c = a - floor((146097 * b) / 4)
            d = floor((4 * c + 3) / 1461)
            e = c - floor((1461 * d) / 4)
            m = floor((5 * e + 2) / 153)
            day = e - floor((153 * m + 2) / 5) + 1
            month = m + 3 - 12 * floor(m / 10)
            year = 100 * b + d - 4800 + floor(m / 10)
        else:
            a = jdn + 32082
            b = floor((4 * a + 3) / 1461)
            c = a - floor((1461 * b) / 4)
            m = floor((5 * c + 2) / 153)
            day = c - floor((153 * m + 2) / 5) + 1
            month = m + 3 - 12 * floor(m / 10)
            year = b - 4800 + floor(m / 10)
        if year <= 0:
            year_str = f"-{abs(year):04d}"
        else:
            year_str = f"{year:04d}"
        date_str = f"{year_str}-{month:02d}-{day:02d}"
        if not re.match(r'^-?\d{4}-\d{2}-\d{2}$', date_str):
            return None
        return date_str
    except (ValueError, OverflowError):
        return None


def jdn_to_ccs(x, by_era=True, proleptic_gregorian=False, gregorian_start=None, lang='en', civ=None):
    """
    Convert Julian Day Number to Chinese calendar string.
    :param x: float (Julian Day Number) or str (ISO date string Y-M-D)
    :param by_era: bool (filter from era JDN vs index year)
    :param proleptic_gregorian: bool
    :param gregorian_start: list
    :param lang: str, language ('en' or 'fr')
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return output_string: str
    """
    # Defaults
    gregorian_start, civ = normalize_defaults(gregorian_start, civ)
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
    era_df, dyn_df, ruler_df, lunar_table = load_num_tables(civ=civ)
    ruler_tag_df = load_csv('rul_can_name.csv')[['person_id', 'string']]
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
        df = df.merge(ruler_tag_df, how='left', on='person_id')
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
        """
        Note: where era and ruler start years differ, I sometimes get duplicates:

        ,dyn_id,cal_stream,era_id,ruler_id,era_name,era_start_year,ruler_name,dyn_name,ind_year,year_gz,month,intercalary,nmd_gz,nmd_jdn,hui_jdn,max_day,hui_gz,emp_start_year
        0,124,3.0,636,15353.0,至正,1341,順帝妥懽帖睦爾,元,1342,19,1,0,10,2211259.5,2211287.5,29.0,辛丑,1333.0
        1,133,4.0,930,16394.0,興国,1340,後村上天皇,日本,1342,19,1,0,10,2211259.5,2211288.5,30.0,壬寅,1339.0
        2,133,4.0,939,16398.0,暦応,1338,光明天皇,日本,1342,19,1,0,10,2211259.5,2211288.5,30.0,壬寅,1336.0
        3,141,8.0,1175,16597.0,後元,1340,忠惠王,高麗,1342,19,1,0,10,2211259.5,2211287.5,29.0,辛丑,1331.0
        4,141,8.0,1175,16597.0,後元,1340,忠惠王,高麗,1342,19,1,0,10,2211259.5,2211287.5,29.0,辛丑,1340.0

        This merits rethinking, but the following will work for now.
        """
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
    _gs, civ = normalize_defaults(None, civ)
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
    era_df, dyn_df, ruler_df, lunar_table = load_num_tables(civ=civ)
    ruler_tag_df = load_csv('rul_can_name.csv')[['person_id', 'string']]
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
