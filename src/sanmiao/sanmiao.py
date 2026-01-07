try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files
import re
import time
import numpy as np
import pandas as pd
import lxml.etree as et
from math import floor
from functools import lru_cache

# TODO add all possibilities for user filtering (web only)
# TODO clean up code and comments
# TODO testing in date extraction before anything else.
# TODO clean up table output
# TODO add sequential mode to web app

phrase_dic_en = {
    'ui': 'USER INPUT', 'matches': 'MATCHES', 'nonsense': 'ERROR: You did a nonsense',
    'rule-dyn': 'ERROR: ruler name does not match dynasty;', 'era-rule': "ERROR: era name does not match ruler/dynasty;",
    'rule-reign': "ERROR: no ruler with this long a reign;", 'era-year': "ERROR: no era this long;",
    'rule-sex': "ERROR: no ruler with this sexYear;", 'era-sex': "ERROR: no era with this sexYear;",
    'mult-sd': "ERROR: more than one sexagenary day;", 'mult-lp': "ERROR: more than one lunar phase;",
    'nmesd': "ERROR: newMoonEve sexDate does not match this or next month;",
    'sd-lp': "ERROR: sexDay-lunPhase mismatch;",
    'sd-lp-mo': "ERROR: lunPhase-sexDate-month mismatch;",
    'nd-sd': "ERROR: numerical and sexDay mismatch;",
    'ndsd-oob': "ERROR: numerical and sexagenary days out of bounds;",
    'sd-mo': "ERROR: sexDay not in month;",
    'lsd-mo': "ERROR: lone sexDay not in this OR next month;",
    'nmob-a': "ERROR: numerical day",
    'ob': "out of bounds",
    'er': 'ERROR'
}
phrase_dic_fr = {
    'ui': 'ENTRÉE UTILISATEUR ', 'matches': 'RÉSULTATS ', 'nonsense': "ERREUR : Vous avez fait n'importe quoi",
    'rule-dyn': 'ERREUR : le nom du souverain ne correspond pas à la dynastie ;',
    'era-rule': "ERREUR : le nom de l'ère ne correspond pas au souverain / dynastie ;",
    'rule-reign': "ERREUR : aucun souverain n'a régné aussi longtemps ;",
    'era-year': "ERREUR : il n'y a pas d'ère aussi longue ;",
    'rule-sex': "ERREUR : aucun souverain avec cette année sexagénaire ;",
    'era-sex': "ERREUR : aucune ère avec cette année sexagénaire ;",
    'mult-sd': "ERREUR : plus d'un jour sexagénéraire ;", 'mult-lp': "ERREUR : plus d'une phase lunaire ;",
    'nmesd': "ERREUR : date sexagénaire du réveillon ne correspond ni à ce mois-ci, ni au prochain ;",
    'sd-lp': "ERREUR : décalage entre jour sexagénaire et phase lunaire ;",
    'sd-lp-mo': "ERREUR : décalage entre jour sexagénaire, phase lunaire et mois ;",
    'nd-sd': "ERREUR : décalage entre jour numérique et sexagénaire ;",
    'ndsd-oob': "ERREUR : jours numériques et sexagénaire hors limites ;",
    'sd-mo': "ERREUR : jour sexagénaire n'est pas dans ce mois ;",
    'lsd-mo': "ERREUR : jour sexagénaire solitaire n'est ni dans ce mois-ci, ni le prochain ;",
    'nmob-a': "ERREUR : jour numérique",
    'ob': "hors limites ",
    'er': 'ERREUR '
}

data_dir = files("sanmiao") / "data"

# Define terms for conversion below
season_dic = {'春': 1, '夏': 2, '秋': 3, '冬': 4}
lp_dic = {'朔': 0, '晦': -1}


simplified_only = set("宝応暦寿観斉亀")
traditional_only = set("寶應曆壽觀齊龜")


def guess_variant(text):
    s_count = sum(ch in simplified_only for ch in text)
    t_count = sum(ch in traditional_only for ch in text)
    if t_count > s_count:
        return "1"
    elif s_count > t_count:
        return "3"
    else:
        return "0"


def sanitize_gs(gs):
    """
    Return a list [year, month, day] of ints if valid,
    otherwise the default [1582, 10, 15].
    """
    default = [1582, 10, 15]
    if not isinstance(gs, (list, tuple)):
        return default
    if len(gs) != 3:
        return default
    try:
        y, m, d = [int(x) for x in gs]
        return [y, m, d]
    except (ValueError, TypeError):
        return default


@lru_cache(maxsize=None)
def _load_csv_cached(csv_name: str) -> pd.DataFrame:
    csv_path = data_dir / csv_name
    try:
        return pd.read_csv(csv_path, index_col=False, encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file {csv_name} not found in package data")


def load_csv(csv_name: str) -> pd.DataFrame:
    """
    Public loader: returns a *copy* so callers can filter/mutate safely
    without poisoning the cached DataFrame.
    """
    return _load_csv_cached(csv_name).copy()


def prepare_tables(civ):
    era_df, dyn_df, ruler_df, lunar_table = load_num_tables(civ=civ)
    dyn_tag_df, ruler_tag_df = load_tag_tables(civ=civ)
    ruler_can_names = load_csv('rul_can_name.csv')[['person_id', 'string']].copy()
    return era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names


def get_cal_streams_from_civ(civ):
    """
    Convert civilization code(s) to list of cal_stream floats.
    
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) or None
    :return: list of floats (to match CSV data type) or None if civ is None
    """
    if civ is None:
        return None
    
    # Map civilization codes to cal_stream ranges
    civ_map = {
        'c': [1, 2, 3],  # China
        'j': [4],         # Japan
        'k': [5, 6, 7, 8]  # Korea
    }
    
    # Handle single string
    if isinstance(civ, str):
        civ = [civ]
    
    # Collect all cal_streams
    cal_streams = []
    for code in civ:
        if code.lower() in civ_map:
            cal_streams.extend(civ_map[code.lower()])
    
    # Remove duplicates, sort, and convert to float to match CSV data type
    return sorted([float(x) for x in set(cal_streams)]) if cal_streams else None


def load_num_tables(civ=None):
    # Default civilisations
    if civ is None:
        civ = ['c', 'j', 'k']

    # Load tables
    era_df = load_csv('era_table.csv')
    dyn_df = load_csv('dynasty_table_dump.csv')
    ruler_df = load_csv('ruler_table.csv')
    lunar_table = load_csv('lunar_table_dump.csv')
    
    # Filter by civilization
    cal_streams = get_cal_streams_from_civ(civ)
    if cal_streams is not None:
        # Filter dyn_df: drop null cal_stream and filter by cal_stream list
        dyn_df = dyn_df[dyn_df['cal_stream'].notna()]
        # Convert cal_stream to float for comparison to avoid int/float mismatch
        dyn_df = dyn_df[dyn_df['cal_stream'].astype(float).isin(cal_streams)]
        
        # Filter era_df: drop null cal_stream and filter by cal_stream list
        era_df = era_df[era_df['cal_stream'].notna()]
        era_df = era_df[era_df['cal_stream'].astype(float).isin(cal_streams)]
        
        # Filter ruler_df: drop null cal_stream and filter by cal_stream list
        ruler_df = ruler_df[ruler_df['cal_stream'].notna()]
        ruler_df = ruler_df[ruler_df['cal_stream'].astype(float).isin(cal_streams)]
        
        # Filter lunar_table: drop null cal_stream and filter by cal_stream list
        lunar_table = lunar_table[lunar_table['cal_stream'].notna()]
        lunar_table = lunar_table[lunar_table['cal_stream'].astype(float).isin(cal_streams)]
    
    return era_df, dyn_df, ruler_df, lunar_table


def load_tag_tables(civ=None):
    # Default civilisations
    if civ is None:
        civ = ['c', 'j', 'k']

    # Load tables
    dyn_tag_df = load_csv('dynasty_tags.csv')
    ruler_tag_df = load_csv('ruler_tags.csv')
    
    # Filter by civilization
    # Load filtered dynasties and rulers to get valid IDs
    _, dyn_df, ruler_df, _ = load_num_tables(civ=civ)
    
    # Filter dyn_tag_df by matching dyn_id to filtered dynasties
    if not dyn_df.empty:
        valid_dyn_ids = dyn_df['dyn_id'].unique()
        dyn_tag_df = dyn_tag_df[dyn_tag_df['dyn_id'].isin(valid_dyn_ids)]
    else:
        dyn_tag_df = dyn_tag_df.iloc[0:0]  # Empty dataframe with same structure
    
    # Filter ruler_tag_df by matching person_id to filtered rulers
    if not ruler_df.empty:
        valid_person_ids = ruler_df['person_id'].unique()
        ruler_tag_df = ruler_tag_df[ruler_tag_df['person_id'].isin(valid_person_ids)]
    else:
        ruler_tag_df = ruler_tag_df.iloc[0:0]  # Empty dataframe with same structure
    
    return dyn_tag_df, ruler_tag_df


def gz_year(num):
    """
    Converts Western calendar year to sexagenary year (numerical)
    :param num: int
    :return: int
    """
    x = (num - 4) % 60 + 1
    return x


def jdn_to_gz(jdn, en=False):
    """
    Convert from Julian day number (JDN) to sexagenary day, with output in Pinyin (en=True) or Chinese (en=False).
    :param jdn: float
    :param en: bool
    """
    jdn = int(jdn - 9.5) % 60
    gz = ganshu(jdn, en)
    return gz


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


def ganshu(input, en=False):
    """
    Convert from sexagenary counter (string) to number (int) and vice versa.
    :param input: str, int, or float
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
    if isinstance(input, str):
        s = input.strip()
        # Normalise for Chen dynasty taboo
        if not en:
            s = re.sub('景', '丙', s)
            return to_num.get(s, "ERROR")
        else:
            s = s.lower()
            return to_num.get(s, "ERROR")

    # number -> string
    try:
        n = int(input)
    except (TypeError, ValueError):
        return "ERROR"

    return to_str.get(n, "ERROR")


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
                try:
                    frankenstein = int(frankenstein)
                finally:
                    return frankenstein
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
                finally:
                    numeral = int(numeral)
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
    if gregorian_start is None:
        gs = [1582, 10, 15]

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
        gregorian_start = sanitize_gs(gregorian_start)
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
    if gregorian_start is None:
        gs = [1582, 10, 15]

    # Get Gregorian reform JDN
    gregorian_start = sanitize_gs(gregorian_start)
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
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return output_string: str
    """
    # Defaults
    if gregorian_start is None:
        gs = [1582, 10, 15]
    if civ is None:
        civ = ['c', 'j', 'k']

    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
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
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return output_string: str
    """
    # Defaults
    if civ is None:
        civ = ['c', 'j', 'k']

    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    if y > 0:
        if lang == 'en':
            fill = f"A.D. {int(y)}"
        else:
            fill = f"{int(y)} apr. J.-C."
    else:
        if lang == 'en':
            fill = f"{int(abs(y)) + 1} B.C."
        else:
            fill = f"{int(abs(y)) + 1} av. J.-C."
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


WS_RE = re.compile(r"\s+")


def strip_ws_in_text_nodes(root: et._Element) -> et._Element:
    """
    Remove all Unicode whitespace in XML text content, but leave tags/attributes intact.
    Applies to both .text and .tail.
    """
    for el in root.iter():
        if el.text:
            el.text = WS_RE.sub("", el.text)
        if el.tail:
            el.tail = WS_RE.sub("", el.tail)
    return root


def clean_attributes(xml_string):
    """
    Clean XML attributes of tags after regex tagging.
    :param xml_string: str
    :return: str
    """
    # Find all attribute strings
    find = r'=".+?"'
    attrib = re.findall(find, xml_string)
    # Find attribute stings with XML tags in them
    bad_attrib = []
    for i in attrib:
        if "<" in i:
            bad_attrib.append(i)
    # Make dirty, clean tuples of affected attribute strings
    ls = []
    for find in bad_attrib:
        replace = re.sub(r'<[\w\d\s_="/]+>', '', find)
        ls.append((find, replace))
    # Replace affected strings with clean versions
    for i in ls:
        xml_string = re.sub(i[0], i[1], xml_string)
    # Error check
    try:
        # Try parsing XML
        et.ElementTree(et.fromstring(xml_string))
    except et.XMLSyntaxError:
        # If fail, try again to remove tags in tag attributes
        find = r'(="[\w;:\.,\[\]\(\)\s]*?)<[\w\d\s_="/]+?>'
        hits = len(re.findall(find, xml_string))
        # Count iterations
        iterations = 0
        # Iterate until all attributes are clean
        while hits > 0:
            xml_string = re.sub(find, r'\1', xml_string)
            hits = len(re.findall(find, xml_string))
            iterations += 1
            if iterations > 100:
                raise Exception('\nAttribute cleaner reached 100 iterations. There is something wrong')
    try:
        # Try again to parse XML
        et.ElementTree(et.fromstring(xml_string))
    except et.XMLSyntaxError:
        raise Exception('Failed to scrub attributes after regex tagging.')
    return xml_string


def strip_text(xml_string):
    """
    Remove all non-date text from XML string
    :param xml_string: str (XML)
    :return: str (XML)
    """
    xml_root = et.ElementTree(et.fromstring(xml_string)).getroot()
    # Clean
    # Remove lone tags
    for node in xml_root.xpath('.//date'):
        # Single character dates
        s = len(node.xpath('string()'))
        if s == 1:
            node.tag = 'to_remove'
        # Dynasty, emperor, or era without anything else
        tags = [sn.tag for sn in node.xpath('./*')]
        if len(tags) == 1 and tags[0] in ('dyn', 'ruler', 'era'):
            node.tag = 'to_remove'
    # Find the <p> element
    # Create a new root element for the filtered output
    new_root = et.Element("root")
    # Copy only <date> elements into the new root
    for date in xml_root.findall(".//date"):
        date.tail = None
        new_root.append(date)
    # Return to string
    xml_string = et.tostring(new_root, encoding='utf8').decode('utf8')
    return xml_string


SKIP = {"date","year","month","day","gz","sexYear","era","ruler","dyn","suffix","int","lp",
        "nmdgz","lp_filler","filler","season","meta","pb","text","body"}  # adjust tags you want to skip

SKIP_ALL = {"date","year","month","day","gz","sexYear","era","ruler","dyn","suffix",
            "int","lp","nmdgz","lp_filler","filler","season"}

SKIP_TEXT_ONLY = {"pb", "meta"}

YEAR_RE   = re.compile(r"((?:[一二三四五六七八九十]+|元)[年載])")
# "廿<date><year>" fix disappears because we won't create that broken boundary in text mode.

# Months: order matters (more specific first)
LEAPMONTH_RE1 = re.compile(r"閏月")
LEAPMONTH_RE2 = re.compile(r"閏((?:十有[一二]|正)[月])")
LEAPMONTH_RE3 = re.compile(r"閏((?:[一二三四五六七八九十]+|正)[月])")
MONTH_RE1     = re.compile(r"((?:十有[一二]|正)[月])")
MONTH_RE2     = re.compile(r"((?:[一二三四五六七八九十]+|正)[月])")

DAY_RE    = re.compile(r"(([廿卅卌卄丗一二三四五六七八九十]+)日)")
GZ_RE     = re.compile(r"([甲乙丙景丁戊己庚辛壬癸景][子丑寅卯辰巳午未申酉戌亥])")
SEASON_RE = re.compile(r"([春秋冬夏])")

LP_RE = re.compile(r"([朔晦])")

def replace_in_text_and_tail(
    xml_root,
    pattern: re.Pattern,
    make_element,
    skip_text_tags=frozenset(),
    skip_all_tags=frozenset(),
):
    """
    Replace pattern matches in text and tail attributes of XML elements.
    Uses iterative approach to handle newly inserted elements properly.
    
    Key point: Even if an element's tag is in skip_all_tags (like <date>),
    we still need to process its TAIL, because that tail might contain
    more patterns that need to be matched.
    """
    # Process elements depth-first, but need to re-scan for new elements
    # Keep processing until no more matches are found
    max_passes = 50  # Safety limit to prevent infinite loops
    changed = True
    
    for pass_num in range(max_passes):
        if not changed:
            break
        changed = False
        
        # Collect all elements to process in this pass
        # Use list() to create snapshot, but we'll re-scan if changes occur
        elements_to_check = []
        for el in xml_root.iter():
            # Always include elements to process their tail
            # We'll skip processing their text/children if tag is in skip_all_tags
            elements_to_check.append(el)
        
        for el in elements_to_check:
            # Skip if element was removed
            parent = el.getparent()
            if parent is None and el is not xml_root:
                continue
            
            # Decide which slots to process
            # CRITICAL: Even if element is in skip_all_tags, we still process its tail!
            # The tail of a <date> element might contain more patterns.
            if el.tag in skip_all_tags:
                # Skip processing text (children) of these elements, but process tail
                slots = ("tail",)
            elif el.tag in skip_text_tags:
                slots = ("tail",)
            else:
                slots = ("text", "tail")

            for slot in slots:
                s = getattr(el, slot)
                if not s or not pattern.search(s):
                    continue

                matches = list(pattern.finditer(s))
                if not matches:
                    continue

                chunks = []
                last = 0
                for m in matches:
                    chunks.append(s[last:m.start()])
                    chunks.append(m)
                    last = m.end()
                chunks.append(s[last:])

                if slot == "text":
                    el.text = chunks[0]
                    pos = 0
                    for i in range(1, len(chunks), 2):
                        new_el = make_element(chunks[i])
                        new_el.tail = chunks[i + 1]
                        el.insert(pos, new_el)
                        pos += 1
                    changed = True
                else:  # tail
                    parent = el.getparent()
                    if parent is None:
                        continue
                    idx = parent.index(el)
                    el.tail = chunks[0]
                    pos = idx + 1
                    for i in range(1, len(chunks), 2):
                        new_el = make_element(chunks[i])
                        new_el.tail = chunks[i + 1]
                        parent.insert(pos, new_el)
                        pos += 1
                    changed = True
                    
def make_simple_date(tagname, group=1):
    def _mk(m):
        d = et.Element("date")
        c = et.SubElement(d, tagname)
        c.text = m.group(group)
        return d
    return _mk

def make_leap_month_exact_monthtext(month_text: str):
    d = et.Element("date")
    i = et.SubElement(d, "int"); i.text = "閏"
    m = et.SubElement(d, "month"); m.text = month_text
    return d

def make_leapmonth_from_group1(m):
    return make_leap_month_exact_monthtext(m.group(1))

def make_leapmonth_yue(m):
    # "閏月" -> <date><int>閏</int><month>月</month></date>
    return make_leap_month_exact_monthtext("月")

def tag_basic_tokens(xml_root):
    # year
    replace_in_text_and_tail(xml_root, YEAR_RE, make_simple_date("year"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # leap month variants (specific -> general)
    replace_in_text_and_tail(xml_root, LEAPMONTH_RE1, make_leapmonth_yue, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, LEAPMONTH_RE2, make_leapmonth_from_group1, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, LEAPMONTH_RE3, make_leapmonth_from_group1, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # month (specific -> general)
    replace_in_text_and_tail(xml_root, MONTH_RE1, make_simple_date("month"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, MONTH_RE2, make_simple_date("month"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # day, gz, season
    replace_in_text_and_tail(xml_root, DAY_RE, make_simple_date("day"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, GZ_RE, make_simple_date("gz"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    replace_in_text_and_tail(xml_root, SEASON_RE, make_simple_date("season"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    return xml_root

SEX_YEAR_PREFIX_RE = re.compile(r"(歲[次在])\s*$")

SEX_YEAR_PREFIX_RE = re.compile(r"(歲[次在])\s*$")

def promote_gz_to_sexyear(xml_root):
    for d in xml_root.xpath(".//date[gz]"):
        prev = d.getprevious()
        if prev is None:
            s = d.getparent().text or ""
            loc = ("parent", d.getparent())
        else:
            s = prev.tail or ""
            loc = ("tail", prev)

        m = SEX_YEAR_PREFIX_RE.search(s)
        if not m:
            continue

        # Remove prefix text
        new_s = s[:m.start()]
        if loc[0] == "parent":
            loc[1].text = new_s
        else:
            loc[1].tail = new_s

        gz_text = d.findtext("gz")

        # Rewrite date contents
        for ch in list(d):
            d.remove(ch)
        f = et.SubElement(d, "filler")
        f.text = m.group(1)
        sy = et.SubElement(d, "sexYear")
        sy.text = gz_text

    return xml_root

PUNCT_RE = re.compile(r"^[，,、\s]*")

def promote_nmdgz(xml_root):
    for gz_date in list(xml_root.xpath(".//date[gz]")):
        parent = gz_date.getparent()
        gz_text = gz_date.findtext("gz")
        if not gz_text:
            continue

        # ---------- CASE 1 ----------
        # <date><gz>..</gz></date>朔，<date><day>..</day></date>
        tail = gz_date.tail or ""
        if tail.startswith("朔"):
            rest = PUNCT_RE.sub("", tail[1:])
            next_el = gz_date.getnext()

            if next_el is not None and next_el.tag == "date" and next_el.find("day") is not None:
                # Clean tail of gz_date
                gz_date.tail = rest

                # Add nmdgz + lp_filler to day date
                nmdgz = et.SubElement(next_el, "nmdgz")
                nmdgz.text = gz_text
                lp = et.SubElement(next_el, "lp_filler")
                lp.text = "朔"

                # Remove gz_date but preserve its tail
                prev = gz_date.getprevious()
                if prev is None:
                    parent.text = (parent.text or "") + (gz_date.tail or "")
                else:
                    prev.tail = (prev.tail or "") + (gz_date.tail or "")
                parent.remove(gz_date)
                continue

        # ---------- CASE 2 ----------
        # 朔<date><gz>..</gz></date>，<date><day>..</day></date>
        prev = gz_date.getprevious()
        if prev is None:
            s = parent.text or ""
            loc = ("parent", parent)
        else:
            s = prev.tail or ""
            loc = ("tail", prev)

        if s.endswith("朔"):
            next_el = gz_date.getnext()
            if next_el is not None and next_el.tag == "date" and next_el.find("day") is not None:
                # Remove trailing 朔
                new_s = s[:-1]
                if loc[0] == "parent":
                    loc[1].text = new_s
                else:
                    loc[1].tail = new_s

                # Move gz into day date
                nmdgz = et.SubElement(next_el, "nmdgz")
                nmdgz.text = gz_text
                lp = et.SubElement(next_el, "lp_filler")
                lp.text = "朔"

                # Remove gz_date, preserve its tail
                gz_tail = gz_date.tail or ""
                prev2 = gz_date.getprevious()
                if prev2 is None:
                    parent.text = (parent.text or "") + gz_tail
                else:
                    prev2.tail = (prev2.tail or "") + gz_tail
                parent.remove(gz_date)

    return xml_root

ERA_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世)")
DYNASTY_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世)")
RULER_SUFFIX_RE = re.compile(r"^(之?初|中|之?末|之?季|末年|之?時|之世|即位)")

def attach_suffixes(xml_root: et._Element) -> et._Element:
    """
    Convert:
      <date><era>太和</era></date>初
    into:
      <date><era>太和</era><suffix>初</suffix></date>

    Same for <ruler> and <dyn>.
    """
    # Snapshot because we mutate tails
    for d in list(xml_root.xpath(".//date")):
        tail = d.tail or ""
        if not tail:
            continue

        # Decide which suffix regex applies based on content
        if d.find("ruler") is not None:
            m = RULER_SUFFIX_RE.match(tail)
        elif d.find("era") is not None:
            m = ERA_SUFFIX_RE.match(tail)
        elif d.find("dyn") is not None:
            m = DYNASTY_SUFFIX_RE.match(tail)
        else:
            continue

        if not m:
            continue

        suf = m.group(1)

        # Add/append suffix element
        s_el = et.SubElement(d, "suffix")
        s_el.text = suf

        # Remove suffix from tail; keep remainder intact
        d.tail = tail[m.end():]

    return xml_root

def tag_date_elements(text, civ=None):
    """
    Tag and clean Chinese string containing date with relevant elements for extraction. Each date element remains
    separated, awaiting "consolidation."
    :param text: str
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return: str (XML)
    """
    # Test if input is XML, if not, wrap in <root> tags to make it XML
    try:
        xml_root = et.ElementTree(et.fromstring(text.encode("utf-8"))).getroot()
    except et.XMLSyntaxError:
        xml_root = et.ElementTree(et.fromstring('<root>' + text + '</root>')).getroot()
    
    # Defaults
    if civ is None:
        civ = ['c', 'j', 'k']

    # Retrieve tag tables
    era_tag_df = load_csv('era_table.csv')
    # Filter era_tag_df by cal_stream
    cal_streams = get_cal_streams_from_civ(civ)
    if cal_streams is not None:
        era_tag_df = era_tag_df[era_tag_df['cal_stream'].notna()]
        # Convert cal_stream to float for comparison to avoid int/float mismatch
        era_tag_df = era_tag_df[era_tag_df['cal_stream'].astype(float).isin(cal_streams)]
    dyn_tag_df, ruler_tag_df = load_tag_tables(civ=civ)
    # Reduce to lists
    era_tag_list = era_tag_df['era_name'].unique()
    dyn_tag_list = dyn_tag_df['string'].unique()
    ruler_tag_list = ruler_tag_df['string'].unique()
    # Normal dates #####################################################################################################
    # Year, month, day, gz, season, lp
    xml_root = tag_basic_tokens(xml_root)
    # Lunar phases
    replace_in_text_and_tail(xml_root, LP_RE, make_simple_date("lp"), skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    # Sexagenary year
    xml_root = promote_gz_to_sexyear(xml_root)
    # NM date
    xml_root = promote_nmdgz(xml_root)
    # Era names ########################################################################################################
    # Reduce list
    era_tag_list = [s for s in era_tag_list if isinstance(s, str) and s]
    if era_tag_list:
        era_tag_list.sort(key=len, reverse=True)
        era_pattern = re.compile("(" + "|".join(map(re.escape, era_tag_list)) + ")")

        def make_era(match):
            d = et.Element("date")
            e = et.SubElement(d, "era")
            e.text = match.group(1)
            return d

        replace_in_text_and_tail(xml_root, era_pattern, make_era, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)

    # Ruler Names ######################################################################################################
    # Reduce list
    ruler_tag_list = [s for s in ruler_tag_list if isinstance(s, str) and s]
    if ruler_tag_list:
        ruler_tag_list.sort(key=len, reverse=True)
        ruler_pattern = re.compile("(" + "|".join(map(re.escape, ruler_tag_list)) + ")")

        def make_ruler(match):
            d = et.Element("date")
            e = et.SubElement(d, "ruler")
            e.text = match.group(1)
            return d

        replace_in_text_and_tail(xml_root, ruler_pattern, make_ruler, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
        
    # Dynasty Names ####################################################################################################
    # Reduce list
    dyn_tag_list = [s for s in dyn_tag_list if isinstance(s, str) and s]
    if dyn_tag_list:
        dyn_tag_list.sort(key=len, reverse=True)
        dyn_pattern = re.compile("(" + "|".join(map(re.escape, dyn_tag_list)) + ")")

        def make_dyn(match):
            d = et.Element("date")
            e = et.SubElement(d, "dyn")
            e.text = match.group(1)
            return d

        replace_in_text_and_tail(xml_root, dyn_pattern, make_dyn, skip_text_tags=SKIP_TEXT_ONLY, skip_all_tags=SKIP_ALL)
    
    # Suffixes #########################################################################################################
    xml_root = attach_suffixes(xml_root)
    # Clean nested tags ################################################################################################
    # Remove lone tags
    for node in xml_root.xpath('.//date'):
        s = node.xpath('string()')
        bad = ['一年', '一日']
        if s in bad:
            node.tag = 'to_remove'
    # Strip tags
    et.strip_tags(xml_root, 'to_remove')
    # Return to string
    text = et.tostring(xml_root, encoding='utf8', pretty_print=True).decode('utf8')
    
    return text


def consolidate_date(text):
    """
    Join separated date elements in the XML according to typical date order (year after era, month after year, etc.)
    :param text: str (XML)
    :return: str (XML)
    """
    bu = text
    # Remove spaces
    xml_root = et.ElementTree(et.fromstring(text)).getroot()
    xml_root = strip_ws_in_text_nodes(xml_root)
    text = et.tostring(xml_root, encoding='utf8').decode('utf8')
    ls = [
        ('dyn', 'ruler'),
        ('ruler', 'year'), ('ruler', 'era'),
        ('era', 'year'),
        ('era', 'filler'),
        ('ruler', 'filler'),
        ('dyn', 'filler'),
        ('year', 'season'),
        ('year', 'filler'),
        ('sexYear', 'int'),
        ('sexYear', 'month'),
        ('year', 'int'),
        ('year', 'month'),
        ('season', 'int'),
        ('season', 'month'),
        ('int', 'month'),
        ('month', 'gz'),
        ('month', 'lp'),
        ('month', 'day'),
        ('month', 'nmdgz'),
        ('gz', 'lp'),
        ('nmdgz', 'day'),
        ('day', 'gz'),
        ('month', 'lp_filler'),
        ('lp_filler', 'day'),
        ('gz', 'filler'),
        ('dyn', 'era')
    ]
    for tup in ls:
        text = re.sub(rf'</{tup[0]}></date>，*<date><{tup[1]}', f'</{tup[0]}><{tup[1]}', text)
        if 'metadata' in text:
            text = clean_attributes(text)
    # Parse to XML
    try:
        et.ElementTree(et.fromstring(text)).getroot()
        return text
    except et.XMLSyntaxError:
        print('error')
        return bu


def clean_nested_tags(text):
    xml_root = et.ElementTree(et.fromstring(text)).getroot()
    # Clean
    for node in xml_root.xpath('.//date//date'):
        node.tag = 'to_remove'
    et.strip_tags(xml_root, 'to_remove')
    for tag in ['dyn', 'ruler', 'year', 'month', 'season', 'day', 'gz', 'lp', 'sexYear', 'nmdgz', 'lp_to_remove']:
        for node in xml_root.findall(f'.//{tag}//*'):
            node.tag = 'to_remove'
    for node in xml_root.findall('.//date'):
        heads = node.xpath('.//ancestor::head')
        if len(heads) == 0:
            elements = [sn.tag for sn in node.findall('./*')]
            # Clean dynasty only
            if elements == ['dyn'] or elements == ['season'] or elements == ['era'] or elements == ['ruler']:
                for sn in node.findall('.//*'):
                    sn.tag = 'to_remove'
                node.tag = 'to_remove'
    # Clean nonsense
    bad = ['一月', '一年', '一日']
    for node in xml_root.xpath('.//date'):
        if node.xpath('normalize-space(string())') in bad:
            node.tag = 'to_remove'
        tags = [sn.tag for sn in node.findall('./*')]
        # Remove lonely lunar phase
        if tags == ['lp']:
            node.tag = 'to_remove'
    # Strip tags
    et.strip_tags(xml_root, 'to_remove')
    et.strip_tags(xml_root, 'lp_to_remove')
    # Return to string
    text = et.tostring(xml_root, encoding='utf8', pretty_print=True).decode('utf8')
    return text



# ============================================================================
# ORIGINAL IMPLEMENTATION - Kept for reference
# ============================================================================
# This function has been replaced by the bulk optimization approach
# (extract_date_table_bulk) which uses pandas operations for better performance.
# Keeping this commented out for reference and debugging purposes.
# ============================================================================

# def interpret_date(node, correct=False, implied=None, pg=False, gs=None, lang="en", tpq=-3000, taq=3000, jd_out=False, civ=None, tables=None):
#     """
#     Filter strings and numbers in date to find matches.
#
#     :param node: XML node
#     :param correct: bool
#     :param implied: dict
#     :param pg: bool
#     :param gs: list (YYYY, MM, DD)
#     :param lang: str
#     :param tpq: int
#     :param taq: int
#     :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
#     :return: df (DataFrame, output (str), implied (dict)
#     """
    if tables is None:
        era_df, dyn_df, ruler_df, lunar_table = load_num_tables(civ=civ)
        dyn_tag_df, ruler_tag_df = load_tag_tables(civ=civ)
        ruler_can_names = load_csv('rul_can_name.csv')[['person_id', 'string']]
    else:
        era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = tables

    # IMPORTANT: because interpret_date mutates/filters these,
    # use cheap views/copies where needed:
    era_df = era_df.copy()
    dyn_df = dyn_df.copy()
    ruler_df = ruler_df.copy()
    lunar_table = lunar_table.copy()
    dyn_tag_df = dyn_tag_df.copy()
    ruler_tag_df = ruler_tag_df.copy()
    
    # Defaults
    if gs is None:
        gs = [1582, 10, 15]
    if civ is None:
        civ = ['c', 'j', 'k']

    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    # Error check on Gregorian start date
    gs = sanitize_gs(gs)
    # Retrieve tables
    dyn_can_names = dyn_df[['dyn_id', 'dyn_name']].copy().drop_duplicates()
    rul_dyn = ruler_df[['person_id', 'dyn_id']].copy().rename(columns={'person_id': 'ruler_id'})

    def preference_filtering(table):
        if table.shape[0] < 2:
            return table
        else:
            bu = table.copy()
            era_id_ls = implied.get('era_id_ls')
            # to-do This doesn't work for emperors without eras
            if 'era_id' in table.columns and len(era_id_ls) > 0:
                table = table[table['era_id'].isin(era_id_ls)]
                if table.empty:
                    del table
                    table = bu.copy()
                else:
                    bu = table.copy()
            ruler_id_ls = implied.get('ruler_id_ls')
            if 'ruler_id' in table.columns and len(ruler_id_ls) > 0:
                table = table[table['ruler_id'].isin(ruler_id_ls)]
                if table.empty:
                    del table
                    table = bu.copy()
                else:
                    bu = table.copy()
            dyn_id_ls = implied.get('dyn_id_ls')
            if 'dyn_id' in table.columns and len(dyn_id_ls) > 0:
                table = table[table['dyn_id'].isin(dyn_id_ls)]
                if table.empty:
                    del table
                    table = bu.copy()
                else:
                    bu = table.copy()
            mn = implied.get('month')
            if 'month' in table.columns and mn is not None:
                # Test if already filtered for month
                if table.shape[0] > 1:
                    mos = table.dropna(subset=['month']).month.unique()
                    if len(mos) > 1:
                        table = table[table['month'] == mn]
                    if table.empty:
                        del table
                        table = bu.copy()
                    else:
                        bu = table.copy()
            inter = implied.get('intercalary')
            if 'intercalary' in table.columns and inter is not None:
                # Test if already filtered for intercalary
                if table.shape[0] > 1:
                    intercalarys = table.dropna(subset=['intercalary']).intercalary.unique()
                    if len(intercalarys) > 1:
                        table = table[table['intercalary'] == inter]
                    if table.empty:
                        del table
                        table = bu.copy()
                    else:
                        bu = table.copy()
            table = table.drop_duplicates()
            return table


    def add_can_names(table):
        nonlocal ruler_can_names
        table = table.reset_index(drop=True)
        # If dyn_id missing
        a = table[table['dyn_id'].isna()].copy()
        if not a.empty:
            del a['dyn_id']
            a = a.merge(rul_dyn, how='left', on='ruler_id')
            b = table.dropna(subset=['dyn_id'])
            table = pd.concat([a, b])
        # Filter ruler_can_names by filtered rulers
        # Note: ruler_df may have 'person_id' or 'ruler_id' depending on where we are in the function
        if not ruler_df.empty:
            if 'person_id' in ruler_df.columns:
                valid_person_ids = ruler_df['person_id'].unique()
            elif 'ruler_id' in ruler_df.columns:
                valid_person_ids = ruler_df['ruler_id'].unique()
            else:
                valid_person_ids = []
            if len(valid_person_ids) > 0:
                ruler_can_names = ruler_can_names[ruler_can_names['person_id'].isin(valid_person_ids)]
        temp = ruler_can_names.rename(columns={'person_id': 'ruler_id', 'string': 'ruler_name'})
        table = table.merge(temp, how='left', on='ruler_id')
        table = table.merge(dyn_can_names, how='left', on='dyn_id')
        return table


    output = f'{phrase_dic.get("ui")}: {node.xpath("normalize-space(string())").replace(" ", "")}\n{phrase_dic.get("matches")}:\n'
    year = None
    if implied is None:
        implied = {
            'dyn_id_ls': [],
            'ruler_id_ls': [],
            'era_id_ls': []
        }
    # Look for dynasty
    dyn_tags = node.xpath('.//dyn')
    if len(dyn_tags) > 0:
        dyn_id = dyn_tags[0].attrib.get('dyn_id')
        if dyn_id is not None:
            if '|' in dyn_id:
                dyn_ids = re.split('|', dyn_id)
            else:
                dyn_ids = [int(dyn_id)]
        else:
            dyn_string = dyn_tags[0].xpath('string()')
            # Find ids
            dyn_tag_df = dyn_tag_df[dyn_tag_df['string'] == dyn_string]
            dyn_ids = dyn_tag_df.dyn_id.to_list()
        # Filter DataFrames
        dyn_df = dyn_df[dyn_df['dyn_id'].isin(dyn_ids) | dyn_df['part_of'].isin(dyn_ids)]
        dyn_ids = dyn_df.dyn_id.to_list() + dyn_df.part_of.to_list()
        ls = []
        for dyn_id in dyn_ids:
            try:
                ls.append(int(dyn_id))
            except ValueError:
                pass
        ruler_df = ruler_df[ruler_df['dyn_id'].isin(dyn_ids)]
        era_df = era_df[era_df['dyn_id'].isin(dyn_ids)]
    # Look for ruler
    ruler_tags = node.xpath('.//ruler')
    if len(ruler_tags) > 0:
        ruler_id = ruler_tags[0].attrib.get('ruler_id')
        if ruler_id is not None:
            ruler_ids = [int(float(ruler_id))]
        else:
            ruler_string = ruler_tags[0].xpath('string()')
            # Find ids
            ruler_tag_df = ruler_tag_df[ruler_tag_df['string'] == ruler_string]
            ruler_ids = ruler_tag_df.person_id.unique()
        # Filter DataFrames
        ruler_df = ruler_df[ruler_df['person_id'].isin(ruler_ids)]
        era_df = era_df[era_df['ruler_id'].isin(ruler_ids)]
        dyn_ids = ruler_df.dyn_id.unique()
        dyn_df = dyn_df[dyn_df['dyn_id'].isin(dyn_ids)]
        # Errors:
        if ruler_df.empty:
            output += f'{phrase_dic.get("rule-dyn")}\n'
    # Look for era
    era_tags = node.xpath('.//era')
    if len(era_tags) > 0:
        era_id = era_tags[0].attrib.get('era_id')
        if era_id is not None:
            era_ids = [int(era_id)]
        else:
            era_string = era_tags[0].xpath('string()')
            # Find ids
            era_df = era_df[era_df['era_name'] == era_string]
            era_ids = era_df.era_id.unique()
        # Filter DataFrames
        era_df = era_df[era_df['era_id'].isin(era_ids)]
        ruler_ids = era_df.ruler_id.unique()
        ruler_df = ruler_df[ruler_df['person_id'].isin(ruler_ids)]
        dyn_ids = era_df.dyn_id.unique()
        dyn_df = dyn_df[dyn_df['dyn_id'].isin(dyn_ids)]
        if era_df.empty:
            output += f'{phrase_dic.get("era-rule")}\n'
    # Look for year
    year_tags = node.xpath('.//year')
    if len(year_tags) > 0:
        year_num = year_tags[0].attrib.get('year')
        if year_num is not None:
            year = int(float(year_num))
        else:
            try:
                year_string = year_tags[0].xpath('string()')
                year = int(numcon(year_string))
                # Add attribute
                node.set('year', str(year))
                # Filter DataFrames
                era_df = era_df[era_df['max_year'] >= year]
                ruler_df = ruler_df[ruler_df['max_year'] >= year]
                if ruler_df.empty:
                    output += f'{phrase_dic.get("rule-reign")}\n'
                # Test if there is anything Han or earlier
                test = dyn_df[dyn_df['dyn_id'] <= 43]
                if era_df.empty and not test.empty:
                    output += f'{phrase_dic.get("era-year")}\n'
            except ValueError:
                pass
        if implied.get('year') != year:
            implied.update({
                'year': None,
                'month': None,
                'intercalary': None
            })
    else:
        year = None
    # Look for sexagenary year NEW
    year_tags = node.xpath('.//sexYear')
    if len(year_tags) > 0:
        year_num = year_tags[0].attrib.get('sexYear')
        if year_num is not None:
            sex_year = int(float(year_num))
        else:
            try:
                year_string = year_tags[0].xpath('string()')
                sex_year = ganshu(year_string)
                # Add attribute
                node.set('sex_year', str(sex_year))
                # The year 4 is a jiazi year, so is -596
                era_min = era_df['era_start_year'].min()
                era_max = era_df['era_end_year'].max()
                # Get the year of the first instance after minimum
                gz_origin = -596 + sex_year - 1
                cycles_elapsed = int((era_min - gz_origin) / 60)
                last_instance = int(cycles_elapsed * 60 + gz_origin)
                # Get index years
                ind_years = [i for i in range(last_instance, int(era_max) + 1, 60)]
                # Filter era DataFrame
                temp = pd.DataFrame()
                for ind_year in ind_years:
                    bloc = era_df[(era_df['era_start_year'] <= ind_year) & (era_df['era_end_year'] >= ind_year)].copy()
                    if not bloc.empty:
                        temp = pd.concat([temp, bloc])
                era_df = temp.copy()
                # Filter ruler dataframe
                ruler_df = ruler_df[ruler_df['person_id'].isin(era_df['ruler_id'].unique())]
                if ruler_df.empty:
                    output += f'{phrase_dic.get("rule-sex")}\n'
                # Test if there is anything Han or earlier
                test = dyn_df[dyn_df['dyn_id'] <= 43]
                if era_df.empty and not test.empty:
                    output += f'{phrase_dic.get("era-sex")}\n'
            except ValueError:
                pass
        if implied.get('sex_year') != sex_year:
            implied.update({'sex_year': sex_year, 'month': None, 'intercalary': None})
    else:
        sex_year = None
    # Check suffixes
    for s in node.xpath('.//suffix'):
        if s.xpath('string()') in ['即位']:
            year = 1
            # Find eras
            era_df = era_df.drop_duplicates(subset=['ruler_id'])
    # Update implied
    a = dyn_df.dropna(subset=['dyn_id'])['dyn_id'].unique()
    if len(a) == 1:
        implied.update({'dyn_id_ls': [a[0]]})
    a = ruler_df.dropna(subset=['person_id'])['person_id'].unique()
    if len(a) == 1:
        implied.update({'ruler_id_ls': [a[0]]})
        b = ruler_df.dropna(subset=['person_id'])['dyn_id'].unique()
        if len(b) == 1:
            implied.update({'dyn_id_ls': [b[0]]})
    a = era_df.dropna(subset=['era_id'])['era_id'].unique()
    if len(a) == 1:
        implied.update({'era_id_ls': [a[0]]})
        b = era_df.dropna(subset=['era_id'])['ruler_id'].unique()
        if len(b) == 1:
            implied.update({'ruler_id_ls': [b[0]]})
        b = era_df.dropna(subset=['era_id'])['dyn_id'].unique()
        if len(b) == 1:
            implied.update({'dyn_id_ls': [b[0]]})
    ####################################################################################################################
    # Narrow calendar stream
    cal_streams = dyn_df['cal_stream'].to_list() + era_df['cal_stream'].to_list() + ruler_df['cal_stream'].to_list()
    cal_streams = list(set(cal_streams))
    lunar_table = lunar_table[lunar_table['cal_stream'].isin(cal_streams)]
    # Booleans
    base = len(node.xpath('.//day')) == 0 and len(node.xpath('.//month')) == 0 and len(node.xpath('.//season')) == 0
    base = base and len(node.xpath('.//season')) == 0 and len(node.xpath('.//int')) == 0 and year is None
    done = base and len(node.xpath('.//gz')) == 0
    sub_year = len(node.xpath('.//gz')) > 0 or len(node.xpath('.//day')) > 0 or len(node.xpath('.//month')) > 0
    sub_year = sub_year or len(node.xpath('.//season')) > 0 or len(node.xpath('.//lp')) > 0
    stop_at_month = len(node.xpath('.//month')) > 0 and len(node.xpath('.//day')) == 0
    stop_at_month = stop_at_month and len(node.xpath('.//gz')) == 0 and len(node.xpath('.//lp')) == 0
    # Ganzhi only
    gz_only = base and len(node.xpath('.//gz')) == 1
    #
    ruler_df = ruler_df[['person_id', 'dyn_id', 'emp_start_year', 'emp_end_year', 'max_year']].copy()
    ruler_df = ruler_df.rename(columns={'person_id': 'ruler_id'})
    df = ruler_df.copy()
    # Only dynasty or emperor given
    if done and len(era_tags) == 0:
        # Filter
        df = preference_filtering(df)
        # Output implications
        implied.update({
            'year': [],
            'month': [],
            'intercalary': []
        })
        imp_ls = ['dyn_id', 'ruler_id', 'era_id']
        for i in imp_ls:
            if i in df.columns:
                l = df.dropna(subset=[i])[i].unique()
                if len(l) == 1:
                    implied.update({f'{i}_ls': list(l)})
    else:
        # Now for emperors with no eras
        no_era_emps = ruler_df[~ruler_df.ruler_id.isin(era_df.ruler_id)].copy()
        if not no_era_emps.empty:
            no_era_emps = no_era_emps.rename(columns={'emp_start_year': 'era_start_year', 'emp_end_year': 'era_end_year'})
            no_era_emps = no_era_emps[['ruler_id', 'dyn_id', 'era_start_year', 'era_end_year', 'max_year']].copy()
            dyn_temp = dyn_df[['dyn_id', 'cal_stream']].copy()
            no_era_emps = no_era_emps.merge(dyn_temp, how='left', on='dyn_id')
        #
        era_temp = era_df[['cal_stream', 'era_id', 'era_name', 'ruler_id', 'era_start_year', 'era_end_year', 'max_year']].copy()
        ruler_df = ruler_df[['ruler_id', 'dyn_id']].copy()
        df = era_temp.merge(ruler_df, how='left', on='ruler_id')
        if not no_era_emps.empty:
            df = pd.concat([no_era_emps, df], ignore_index=True)
        # to-do Here, I am randomly assigning cal_stream 1 to all dynasties w/o
        df['cal_stream'] = df['cal_stream'].fillna(value=1)
    if done:
        # Filter
        df = preference_filtering(df)
        # Output implications
        implied.update({
            'year': [],
            'month': [],
            'intercalary': []
        })
        imp_ls = ['dyn_id', 'ruler_id', 'era_id']
        for i in imp_ls:
            if i in df.columns:
                l = df.dropna(subset=[i])[i].unique()
                if len(l) == 1:
                    implied.update({f'{i}_ls': list(l)})
        # output += f"MATCHES: "
        # Add lables
        df = add_can_names(df)
        if df.shape[0] > 1:
            if 'emp_start_year' in df.columns:
                temp = df[(df['emp_start_year'] >= tpq) & (df['emp_end_year'] <= taq)].copy()
                if not temp.empty:
                    df = temp
        for index, row in df.iterrows():
            output += f"{row['dyn_name']}{row['ruler_name']}"
            if 'era_name' in df.columns:
                output += f"{row['era_name']}年間（{row['era_start_year']}–{row['era_end_year']}）\n"
            else:
                output += f"年間（{row['emp_start_year']}–{row['emp_end_year']}）\n"
        output = output[:-1]
        output = output.replace('.0', '')
    else:
        # to-do fill out columns
        for col in ['season', 'day', 'gz', 'lp']:
            if col not in df.columns:
                df[col] = np.nan
        # Establish index year
        if year is not None:
            df['year'] = year
            df['ind_year'] = df['era_start_year'] + year - 1
        elif year is not None and not sub_year:
            implied.update({'month': None})
        elif year is None and sub_year:
            implied_year = implied.get('year')
            try:
                df['year'] = implied_year
                df['ind_year'] = df['era_start_year'] + implied_year - 1
            except Exception:
                ls = []
                for index, row in df.iterrows():
                    dic = row.to_dict()
                    if not pd.isna(row['max_year']):
                        for y in range(0, int(row['max_year'])):
                            ldic = {}
                            ldic.update(dic)
                            ldic.update({
                                'year': y,
                                'ind_year': row['era_start_year'] + y
                            })
                            ls.append(ldic)
                df = pd.DataFrame(ls)
        else:
            implied.update({'year': None})
        if 'ind_year' in df.columns:
            condition = True
            # Filter lunar table
            lunar_table = lunar_table[lunar_table['ind_year'].isin(df.ind_year)]
            # Set max day
            lunar_table['max_day'] = lunar_table['hui_jdn'] - lunar_table['nmd_jdn'] + 1
            # to-do seasons, insert this into lunar table to deal with wierd years
            # Filter by month
            if len(node.xpath('.//month[@month]')) > 0:
                months = [int(float(i.attrib.get('month'))) for i in node.xpath('.//month[@month]')]
                implied.update({'month': months[0], 'intercalary': None})
            elif len(node.xpath('.//month')) > 0:
                months = [i.xpath('string()') for i in node.xpath('.//month')]
                months = [numcon(i) for i in months]
                implied.update({'month': months[0], 'intercalary': None})
                # Add attribute
                if len(months) == 1:
                    node.set('month', str(months[0]))
            elif implied.get('month') is not None:
                months = [implied.get('month')]
            else:
                months = []
            ls = []
            for m in months:
                try:
                    #if isinstance(m, float):
                    #    m = int(m)
                    ls.append(m)
                except ValueError:
                    pass
            months = ls
            if len(months) == 0:
                condition = False
            # Filter by intercalary
            if len(node.xpath('.//int')) > 0 or implied.get('intercalary') == 1:
                lunar_table = lunar_table[lunar_table['intercalary'] == 1]
                implied.update({'intercalary': 1})
                condition = True
                # Add attribute
                node.set('int', '1')
            # Set condition to continue if we stop at the year or not
            next_condition = len(node.xpath('.//lp')) > 0 or len(node.xpath('.//gz')) > 0 or len(node.xpath('.//day')) > 0
            if condition or next_condition:
                # Merge dynasty, ruler, era, year dataframe with lunar table
                df = df.merge(lunar_table, how='left', on=['cal_stream', 'ind_year'])
            else:
                df['month'] = np.nan
            if next_condition:
                # Extract lunar phases, sexagenary dates, and days from XML
                lp = [i.xpath('string()') for i in node.xpath('.//lp')]
                gz_strings = [i.xpath('string()') for i in node.xpath('.//gz')]
                gz = [ganshu(i) for i in gz_strings]
                days = [i.xpath('string()') for i in node.xpath('.//day')]
                days = [numcon(i) for i in days]
                # set attributes
                if len(lp) == 1:
                    if '晦' in lp:
                        node.set('lp', '-1')
                    elif '朔' in lp:
                        node.set('lp', '0')
                if len(gz) == 1:
                    node.set('gz', str(gz[0]))
                if len(days) == 1:
                    node.set('day', str(days[0]))
                #
                if len(gz) > 1:
                    output += f"{phrase_dic.get('mult-sd')}\n"
                elif len(lp) > 1:
                    output += f"{phrase_dic.get('mult-lp')}\n"
                elif len(lp) == 1 and len(gz) == 0:  # If lunar phase and sexagenary date
                    if '晦' in lp:
                        df['nmd_jdn'] = df['nmd_jdn'] + df['max_day']
                        df['nmd_gz'] = (df['nmd_gz'] + df['max_day'] - 2) % 60 + 1
                        df['day'] = df['max_day']
                        df['lp'] = -1
                    else:
                        df['day'] = 1
                        df['lp'] = 0
                    df = df.copy().rename(columns={'nmd_jdn': 'jdn'})
                    df['gz'] = df['nmd_gz']
                    del df['nmd_gz']
                elif len(lp) == 1 and len(gz) == 1:
                    # hui is the last day of month x, not the eve of month y; update in Norbert
                    if '晦' in lp:
                        df['nmd_jdn'] = df['nmd_jdn'] + df['max_day']
                        df['nmd_gz'] = (df['nmd_gz'] + df['max_day'] - 2) % 60 + 1
                        df['day'] = df['max_day']
                        df['lp'] = -1
                    else:
                        df['day'] = 1
                        df['lp'] = 0
                    df = df[df['nmd_gz'] == gz[0]].copy().rename(columns={'nmd_jdn': 'jdn'})
                    # Filter by implied ids
                    df = preference_filtering(df)
                    test = df[df['month'].isin(months)]
                    if test.empty:
                        if '晦' in lp:
                            next_months = [i + 1 for i in months]
                            test = df[df['month'].isin(next_months)]
                            if not test.empty:
                                implied.update({'month': next_months[0]})
                                months = next_months
                            else:
                                output += f"{phrase_dic.get('nmesd')}\n"
                        else:
                            output += f"{phrase_dic.get('sd-lp')}\n"
                    df['gz'] = gz[0]
                    del df['nmd_gz']
                    if df.empty:
                        output += f"{phrase_dic.get('sd-lp-mo')}\n"
                elif len(gz) == 1 and len(days) == 1:
                    df['jdn'] = df['nmd_jdn'] + days[0] - 1
                    df['jdn2'] = (gz[0] - df['nmd_gz']) % 60 + df['nmd_jdn']
                    df = df[df['jdn'] == df['jdn2']].copy()
                    del df['nmd_jdn'], df['jdn2']
                    df['day'] = days[0]
                    df['gz'] = gz[0]
                    if df.empty:
                        output += f"{phrase_dic.get('nd-sd')}\n"
                    else:
                        df = df[df['day'] <= df['max_day']]
                        if df.empty:
                            output += f"{phrase_dic.get('ndsd-oob')}\n"
                elif len(gz) == 1:
                    try:
                        df['day'] = (gz[0] - df['nmd_gz']) % 60 + 1
                        df = df[df['day'] <= df['max_day']]
                        # Filter by implied ids
                        df = preference_filtering(df)
                        if len(months) > 0:
                            test = df[df['month'].isin(months)]
                            if test.empty:
                                if not gz_only:
                                    output += f"{phrase_dic.get('sd-mo')}\n"
                                else:
                                    next_months = [i + 1 for i in months]
                                    test = df[df['month'].isin(next_months)]
                                    if not test.empty:
                                        implied.update({'month': next_months[0]})
                                        months = next_months
                                    else:
                                        output += f"{phrase_dic.get('lsd-mo')}\n"
                            df = test.copy()
                        df['jdn'] = df['day'] + df['nmd_jdn'] - 1
                        del df['nmd_jdn']
                        df['gz'] = gz[0]
                    except TypeError:
                        pass
                elif len(days) == 1:
                    df['day'] = days[0]
                    df['jdn'] = df['day'] + df['nmd_jdn'] - 1
                    del df['nmd_jdn']
                    df['gz'] = (df['nmd_gz'] + days[0] - 2) % 60 + 1
                    df = df[df['day'] <= df['max_day']]
                    if df.empty:
                        output += f"{phrase_dic.get('nmob-a')} ({days[0]}) {phrase_dic.get('ob')};\n"
            elif stop_at_month:
                # Filter by implied ids
                df = preference_filtering(df).reset_index(drop=True)
                temp = df.copy().dropna(subset=['nmd_jdn', 'hui_jdn'])
                temp['nb_jdn'] = temp['nmd_jdn']
                temp['na_jdn'] = temp['hui_jdn']
                temp['ISO_Date_Start'] = temp['nb_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
                temp['ISO_Date_End'] = temp['na_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
                df = pd.concat([temp, df]).sort_index()
                cols = ['ruler_id', 'era_id', 'ind_year', 'month']
                try:
                    df = df.drop_duplicates(subset=cols)
                except KeyError:
                    pass
            # Filter by given months
            if df.shape[0] > 0 and len(months) > 0:
                bu = df.copy()
                df = df[df['month'].isin(months)]
                # print(node.xpath('string()'))
                # print(df)
                if df.empty:
                    df = bu
                elif len(months) == 1:
                    implied.update({'month': months[0]})
            # Filter
            df = preference_filtering(df)
            """
            if node.attrib.get('ind') == '9':
                # test = df[df['era_id'].isin(implied.get('era_id_ls'))]
                print(implied)
                print(months)
                print(df.to_string(index=False))
                sys.exit()
            """
            # Check for missing things
            st = ''
            for i in ['dyn_id', 'ruler_id', 'era_id']:
                vals = implied.get(f"{i}_ls")
                if len(vals) == 1:
                    if df[df[i] == vals[0]].empty:
                        st += f"{i[:-3].upper()}, "
            # if st != '' and 'ERROR' not in output:
            #    output += f"NOTE: implicit {st[:-2]} excluded from results for mismatch; "
            # If there is a date #######################################################################################
            if 'jdn' in df.columns:
                good = df.copy().dropna(subset=['jdn'])
                bad = df[~df.index.isin(good.index)].copy()
                good['ISO_Date'] = good['jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
                df = pd.concat([good, bad]).sort_index()
            elif 'nmd_jdn' in df.columns:
                good = df.copy().dropna(subset=['nmd_jdn', 'hui_jdn'])
                bad = df[~df.index.isin(good.index)].copy()
                good['ISO_Date_Start'] = good['nmd_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
                good['ISO_Date_End'] = good['hui_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
                df = pd.concat([good, bad]).sort_index()
            # Output implications
            imp_ls = ['dyn_id', 'ruler_id', 'era_id']
            for i in imp_ls:
                if i in df.columns:
                    l = df.dropna(subset=[i])[i].unique()
                    if len(l) == 1:
                        implied.update({f'{i}_ls': list(l)})
            temp = df.dropna(subset=['year'])['year'].unique()
            if len(temp) == 1:
                implied.update({'year': temp[0]})
            # Drop duplicates
            cols = ['jdn', 'nb_jdn', 'na_jdn']
            cols = [i for i in cols if i in df.columns]
            if len(cols) > 0:
                df = df.drop_duplicates(subset=cols)
            # Apply date range filter to narrow results if necessary
            if df.shape[0] > 1:
                temp = df[(df['ind_year'] >= tpq) & (df['ind_year'] <= taq)].copy()
                if not temp.empty:
                    df = temp
            # Limit on hits
            if df.shape[0] > 15:
                output += f'{phrase_dic.get("er")}: {df.shape[0]} {phrase_dic.get("matches").lower()}'
                if not correct:
                    df = pd.DataFrame([node.attrib]).rename(columns={'index': 'date_index'})
                else:
                    del df
                    df = pd.DataFrame()
            if df.empty and not correct:
                if not era_df.empty:
                    df = era_df.copy()
                    for key, value in node.attrib.items():
                        df[key] = value
                else:
                    df = pd.DataFrame([node.attrib]).rename(columns={'index': 'date_index'})
                df['mismatch'] = True              
            else:
                try:
                    # Add labels
                    df = add_can_names(df)
                    # Text output
                    temp_string = ""  # f"MATCHES: "
                    df = df.sort_values(by=['cal_stream', 'ind_year'])
                    for index, row in df.iterrows():
                        temp_string += f"{row['dyn_name']}{row['ruler_name']}"
                        if isinstance(row['era_name'], str):
                            temp_string += row['era_name']
                        if not pd.isna(row['year']):
                            implied.update({'year': row['year']})
                            if row['year'] == 1:
                                temp_string += '元年'
                            else:
                                temp_string += numcon(row['year']) + '年'
                        if not next_condition and len(months) == 0:  # If year only
                            temp_string += f"（{row['ind_year']}）"
                        if 'intercalary' in df.columns:
                            if row['intercalary'] == 1:
                                temp_string += '閏'
                        if not pd.isna(row['month']):
                            implied.update({'month': row['month']})
                            if row['month'] == 1:
                                temp_string += '正月'
                            else:
                                temp_string += numcon(row['month']) + '月'
                        if stop_at_month:
                            start_gz = ganshu(row['nmd_gz'])
                            end_gz = ganshu((row['nmd_gz'] + row['max_day'] - 2) % 60 + 1)
                            if jd_out:
                                temp_string += f'（JD {start_gz}{row["nmd_jdn"]} ~ {end_gz}{row["hui_jdn"]}''）'
                            else:
                                temp_string += f'（{start_gz}{row["ISO_Date_Start"]} ~ {end_gz}{row["ISO_Date_End"]}）'
                        if not pd.isna(row['day']) and row['lp'] != 0:
                            temp_string += numcon(row['day']) + '日'
                        if not pd.isna(row['gz']):
                            temp_string += ganshu(row['gz'])
                        if not pd.isna(row['lp']):
                            dic = {0: '朔', -1: '晦'}
                            temp_string += dic.get(row['lp'])
                        if 'jdn' in df.columns:
                            if jd_out:
                                temp_string += f'（JD {row["jdn"]}）'
                            else:
                                temp_string += f'（{row["ISO_Date"]}）'
                        temp_string += '\n'
                    if temp_string == "":
                        output += "No matches"
                    else:
                        output += temp_string[:-1]
                except KeyError:
                    pass
                # Update implications
                """
                implied.update({
                    'year': None,
                    'month': None,
                    'intercalary': None
                })
                """
                for i in ['year', 'month', 'intercalary']:
                    if i in df.columns:
                        temp = df.dropna(subset=[i])[i].unique()
                        if len(temp) == 1:
                            implied.update({i: temp[0]})
                imp_ls = ['dyn_id', 'ruler_id', 'era_id']
                for i in imp_ls:
                    if i in df.columns:
                        l = df.dropna(subset=[i])[i].unique()
                        if len(l) == 1:
                            implied.update({f'{i}_ls': list(l)})
    output = output.replace('.0', '')
    df = preference_filtering(df)
    return df, output, implied


def index_date_nodes(xml_string) -> str:
    """
    Index date nodes in XML string.
    """
    xml_root = et.ElementTree(et.fromstring(xml_string)).getroot()
    index = 0
    for node in xml_root.xpath('.//date'):
        node.set('index', str(index))
        index += 1
    xml_string = et.tostring(xml_root, encoding='utf8', pretty_print=True).decode('utf8')
    return xml_string


def extract_date_table(xml_string, pg=False, gs=None, lang='en', tpq=-3000, taq=3000, jd_out=False, civ=None, tables=None):
    """
    Extract date table from XML string using optimized bulk processing.
    
    This is a wrapper that calls extract_date_table_bulk() for consistency.
    
    :param xml_string: XML string with tagged date elements
    :param pg: bool, proleptic gregorian flag
    :param gs: list, gregorian start date [YYYY, MM, DD]
    :param lang: str, language ('en' or 'fr')
    :param tpq: int, terminus post quem
    :param taq: int, terminus ante quem
    :param jd_out: bool, output JDN in report
    :param civ: str or list, civilization filter
    :param tables: Optional pre-loaded tables tuple. If None, will load via prepare_tables().
    :return: tuple (xml_string, report, output_df)
    """
    # Defaults
    if gs is None:
        gs = [1582, 10, 15]
    if civ is None:
        civ = ['c', 'j', 'k']

    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    
    # Use the optimized bulk function (delegates to extract_date_table_bulk)
    return extract_date_table_bulk(
        xml_string, pg=pg, gs=gs, lang=lang,
        tpq=tpq, taq=taq, jd_out=jd_out, civ=civ, tables=tables, sequential=True
    )


def dates_xml_to_df(xml_string: str) -> pd.DataFrame:
    xml_root = et.ElementTree(et.fromstring(xml_string)).getroot()
    rows = []
    for node in xml_root.xpath('.//date'):
        get1 = lambda xp: (node.xpath(f'normalize-space(string({xp}[1]))') or None)
        row = {
            "date_index": node.attrib.get("index"),
            "date_string": node.xpath("normalize-space(string())"),

            "dyn_str": get1(".//dyn"),
            "ruler_str": get1(".//ruler"),
            "era_str": get1(".//era"),

            "year_str": get1(".//year"),
            "sexYear_str": get1(".//sexYear"),
            "month_str": get1(".//month"),
            "day_str": get1(".//day"),
            "gz_str": get1(".//gz"),
            "lp_str": get1(".//lp"),
            "has_int": 1 if node.xpath(".//int") else 0,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def normalise_date_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # year
    out["year"] = out["year_str"].where(out["year_str"].notna(), None)
    out.loc[out["year_str"] == "元年", "year"] = 1
    m = out["year_str"].notna() & (out["year_str"] != "元年")
    out.loc[m, "year"] = out.loc[m, "year_str"].map(numcon)

    # sexYear
    out["sex_year"] = out["sexYear_str"].map(lambda s: ganshu(s) if isinstance(s, str) and s else None)

    # month
    def month_to_int(s):
        if not isinstance(s, str) or not s:
            return None
        if s == "正月": return 1
        if s == "臘月": return 13
        if s == "一月": return 14
        return numcon(s)
    out["month"] = out["month_str"].map(month_to_int)

    # day
    out["day"] = out["day_str"].map(lambda s: numcon(s) if isinstance(s, str) and s else None)

    # gz (sexagenary day number)
    out["gz"] = out["gz_str"].map(lambda s: ganshu(s) if isinstance(s, str) and s else None)

    # lp
    out["lp"] = out["lp_str"].map(lambda s: lp_dic.get(s) if isinstance(s, str) else None)

    # intercalary
    out["intercalary"] = out["has_int"].replace({0: None, 1: 1})
    
    # Normalize date_string: remove all spaces from Chinese text
    if "date_string" in out.columns:
        out["date_string"] = out["date_string"].apply(
            lambda x: str(x).replace(" ", "") if pd.notna(x) and x else ""
        )

    return out


# ============================================================================
# BULK DATE INTERPRETATION FUNCTIONS (OPTIMIZED VERSION)
# ============================================================================
# These functions replace the iterative interpret_date() approach with
# bulk pandas operations for better performance.
# ============================================================================

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


def bulk_generate_date_candidates(df_with_ids, dyn_df, ruler_df, era_df):
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
    :return: Expanded DataFrame with all candidate combinations, with columns:
             date_index, dyn_id, ruler_id, era_id, cal_stream, era_start_year, era_end_year, max_year, etc.
    """
    out = df_with_ids.copy()
    
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
            # No identifiers specified - create one row with empty IDs but preserve date info
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
            all_candidates.append(candidate_row)
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
        candidates_df = pd.DataFrame(columns=['date_index'])
    
    # # Ensure cal_stream is set (default to 1 if missing)
    # # Commented out - problem is solved elsewhere
    # if 'cal_stream' in candidates_df.columns:
    #     candidates_df['cal_stream'] = candidates_df['cal_stream'].fillna(1.0)
    # else:
    #     candidates_df['cal_stream'] = 1.0
    
    return candidates_df


def preference_filtering_bulk(table, implied):
    """
    Apply preference filtering based on implied state.
    
    This filters candidate rows using implied state from previous dates.
    If filtering results in empty table, revert to original (fail gracefully).
    
    :param table: DataFrame with candidate rows to filter
    :param implied: dict with keys like 'dyn_id_ls', 'ruler_id_ls', 'era_id_ls', 'month', 'intercalary'
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
    return table


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


def solve_date_simple(g, implied, phrase_dic, ruler_can_names, dyn_df, tpq=-3000, taq=3000):
    """
    Solve dates that have only dynasty/ruler/era (no year/month/day constraints).

    These are "done" cases - dates that specify only the dynasty, ruler, or era,
    without any temporal constraints like year, month, or day.

    :param g: DataFrame with candidate rows for a single date_index
    :param implied: dict with implied state from previous dates
    :param phrase_dic: dict with phrase translations
    :param ruler_can_names: DataFrame with ruler canonical names
    :param dyn_df: DataFrame with dynasty information
    :param tpq: terminus post quem (earliest date)
    :param taq: terminus ante quem (latest date)
    :return: tuple (result_df, report_string, updated_implied)
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
    imp_ls = ['dyn_id', 'ruler_id', 'era_id']
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


def solve_date_with_year(g, implied, phrase_dic, ruler_can_names, dyn_df, era_df, tpq=-3000, taq=3000, has_month=False, has_day=False, has_gz=False, has_lp=False):
    """
    Solve dates that have year constraints (numeric or sexagenary).
    
    Handles:
    - Numeric year constraints (filter by max_year, calculate ind_year)
    - Sexagenary year constraints (expand to multiple index years, every 60 years)
    - Year-only dates (no month/day constraints)
    
    :param g: DataFrame with candidate rows for a single date_index
    :param implied: dict with implied state from previous dates
    :param phrase_dic: dict with phrase translations
    :param ruler_can_names: DataFrame with ruler canonical names
    :param dyn_df: DataFrame with dynasty information
    :param era_df: DataFrame with era information
    :param tpq: terminus post quem (earliest date)
    :param taq: terminus ante quem (latest date)
    :param has_month: bool, whether date has month constraint
    :param has_day: bool, whether date has day constraint
    :param has_gz: bool, whether date has sexagenary day constraint
    :param has_lp: bool, whether date has lunar phase constraint
    :return: tuple (result_df, report_string, updated_implied)
    """
    if g.empty:
        return pd.DataFrame(), "", implied.copy()
    
    df = g.copy()
    
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
            df = df[df['max_year'] >= year].copy()

        # Calculate index year (Western calendar year)
        if 'era_start_year' in df.columns:
            df['ind_year'] = df['era_start_year'] + year - 1
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
        imp_ls = ['dyn_id', 'ruler_id', 'era_id']
        for i in imp_ls:
            if i in df.columns:
                unique_vals = df.dropna(subset=[i])[i].unique()
                if len(unique_vals) == 1:
                    updated_implied.update({f'{i}_ls': list(unique_vals)})
        
        return df, updated_implied
    
    # If we have month/day constraints, we'll handle those in Phase 5
    # For now, just return with ind_year set up
    return df, updated_implied


def solve_date_with_lunar_constraints(g, implied, phrase_dic, ruler_can_names, dyn_df, lunar_table, 
                                      month=None, day=None, gz=None, lp=None, intercalary=None,
                                      tpq=-3000, taq=3000, pg=False, gs=None, jd_out=False):
    """
    Solve dates with month/day/sexagenary day/lunar phase constraints.
    
    This is the most complex constraint solving, involving:
    - Lunar table joins (month/day calculations)
    - Sexagenary day (gz) matching
    - Lunar phase (lp) handling (朔/new moon, 晦/last day)
    - Various combinations of constraints
    
    :param g: DataFrame with candidate rows (should already have ind_year calculated)
    :param implied: dict with implied state
    :param phrase_dic: dict with phrase translations
    :param ruler_can_names: DataFrame with ruler canonical names
    :param dyn_df: DataFrame with dynasty information
    :param lunar_table: DataFrame with lunar calendar data (must have ind_year, cal_stream, etc.)
    :param month: int or list of ints, month constraint(s)
    :param day: int, day constraint
    :param gz: int, sexagenary day constraint
    :param lp: str or int, lunar phase constraint ('朔' or '晦', or 0/-1)
    :param intercalary: int, intercalary month flag (1 if intercalary)
    :param tpq: terminus post quem
    :param taq: terminus ante quem
    :param pg: proleptic gregorian flag
    :param gs: gregorian start date
    :param jd_out: bool, whether to output JDN in report
    :return: tuple (result_df, report_string, updated_implied)
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
    
    # Calculate max_day for each lunar month
    lunar_filtered['max_day'] = lunar_filtered['hui_jdn'] - lunar_filtered['nmd_jdn'] + 1
    
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
    g = g.merge(lunar_filtered, how='left', on=['cal_stream', 'ind_year'])
    df = g.copy()
    # Filter by month if specified and not intercalary
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
                    df['error_str'] += "year-month mismatch; "
    else:
        # TODO this will require debugging with specific examples
        # For intercalary months or when no month constraint, just update the columns
        df['month'] = df['lunar_month']
        df['intercalary'] = df['lunar_intercalary']
    # Handle stop_at_month case (month only, no day/gz/lp)
    if stop_at_month:
        df = preference_filtering_bulk(df, updated_implied)
        # Generate date ranges
        if 'nmd_jdn' in df.columns and 'hui_jdn' in df.columns:
            df['ISO_Date_Start'] = df['nmd_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
            df['ISO_Date_End'] = df['hui_jdn'].apply(lambda jd: jdn_to_iso(jd, pg, gs))
            if 'nmd_gz' in df.columns:
                df['start_gz'] = df['nmd_gz'].apply(lambda g: ganshu(g))
                df['end_gz'] = df.apply(lambda row: ganshu((row['nmd_gz'] + row['max_day'] - 2) % 60 + 1), axis=1)
        
        return df, updated_implied

    # Handle combinations of day/gz/lp constraints
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
            df['hui_gz'] = df['hui_jdn'].apply(lambda jdn: jdn_to_gz(jdn))
            df = df[df['gz'] == df['hui_gz']].copy()
            del df['hui_gz']
            if df.empty:
                df = g.copy()
                df['error_str'] += "Lunar phase-gz mismatch; "
            else:
                df['jdn'] = df['hui_jdn']
                df['day'] = df['max_day']
        elif lp_value == 0:  # 朔
            df = df[df['gz'] == df['nmd_gz']].copy()
            if df.empty:
                df = g.copy()
                df['error_str'] += "Lunar phase-gz mismatch; "
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
                        df['error_str'] += "Lunar phase-gz-month mismatch; "
                else:
                    # Return original candidates if month matching fails
                    df = g.copy()
                    df['error_str'] += "Lunar phase-gz-month mismatch; "
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
                df['error_str'] += "Month-day-gz mismatch; "
        else:
            df = g.copy()
            df['error_str'] += "Month-day-gz mismatch; "
    
    elif has_gz and not has_day and not has_lp:
        # Sexagenary day only
        df['day'] = ((gz - df['nmd_gz']) % 60) + 1
        df = df[df['day'] <= df['max_day']]
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
                    df['error_str'] += "Month-gz mismatch; "
                else:
                    # Return original candidates if month matching fails
                    df = g.copy()
                    df['error_str'] += "Month-gz mismatch; "
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
            df['error_str'] += f"Month-day mismatch (out of bounds); "
    
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
    
    imp_ls = ['dyn_id', 'ruler_id', 'era_id']
    for i in imp_ls:
        if i in df.columns:
            unique_vals = df.dropna(subset=[i])[i].unique()
            if len(unique_vals) == 1:
                updated_implied.update({f'{i}_ls': list(unique_vals)})
    
    if df.empty:
        df = g.copy()
        df['error_str'] += "Anomaly in lunar constraint solving; "

    return df, updated_implied


def extract_date_table_bulk(xml_string, pg=False, gs=None, lang='en', tpq=-3000, taq=3000, jd_out=False, civ=None, tables=None, sequential=True):
    """
    Optimized bulk version of extract_date_table using pandas operations.
    
    This function replaces the iterative interpret_date() approach with:
    1. Bulk ID resolution (all dates at once)
    2. Bulk candidate generation (all combinations at once)
    3. Sequential constraint solving per date (preserving implied state)
    
    :param xml_string: XML string with tagged date elements
    :param pg: bool, proleptic gregorian flag
    :param gs: list, gregorian start date [YYYY, MM, DD]
    :param lang: str, language ('en' or 'fr')
    :param tpq: int, terminus post quem
    :param taq: int, terminus ante quem
    :param jd_out: bool, output JDN in report
    :param civ: str or list, civilization filter
    :param tables: Optional pre-loaded tables tuple. If None, will load via prepare_tables().
                   Should be tuple: (era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names)
    :return: tuple (xml_string, report, output_df) - same format as extract_date_table()
    """
    # Defaults
    if gs is None:
        gs = [1582, 10, 15]
    if civ is None:
        civ = ['c', 'j', 'k']
    
    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    
    # Parse XML
    xml_root = et.ElementTree(et.fromstring(xml_string)).getroot()
    
    # Step 1: Extract dates to DataFrame
    df = dates_xml_to_df(xml_string)
    if df.empty:
        return xml_string, pd.DataFrame()
    
    # Step 2: Normalize date fields (convert strings to numbers)
    df = normalise_date_fields(df)
    
    # Step 3: Load all tables once (or use provided tables)
    # Performance optimization: if tables are already loaded, reuse them to avoid copying
    if tables is None:
        tables = prepare_tables(civ=civ)
    era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = tables
    
    # Step 4: Bulk resolve IDs (Phase 1)
    df = bulk_resolve_dynasty_ids(df, dyn_tag_df, dyn_df)
    df = bulk_resolve_ruler_ids(df, ruler_tag_df)
    df = bulk_resolve_era_ids(df, era_df)
    
    # Step 5: Bulk generate candidates (Phase 2)
    df_candidates = bulk_generate_date_candidates(df, dyn_df, ruler_df, era_df)
    
    # Drop string columns that are no longer needed after ID resolution
    string_columns_to_drop = ['dyn_str', 'ruler_str', 'era_str', 'year_str', 'sexYear_str',
                             'month_str', 'day_str', 'gz_str', 'lp_str']
    df_candidates = df_candidates.drop(columns=[col for col in string_columns_to_drop
                                              if col in df_candidates.columns])
    
    # Add report note
    df_candidates['error_str'] = ""

    # Step 6: Process each date sequentially (preserving implied state)
    implied = {
        'dyn_id_ls': [],
        'ruler_id_ls': [],
        'era_id_ls': [],
        'year': None,
        'month': None,
        'intercalary': None,
        'sex_year': None
    }
    
    all_results = []
    
    # Group by date_index and process sequentially
    for date_idx in sorted(df_candidates['date_index'].dropna().unique(), key=lambda x: int(x) if str(x).isdigit() else 0):
        # Reset implied state for each date if not sequential
        if not sequential:
            implied = {
                'dyn_id_ls': [],
                'ruler_id_ls': [],
                'era_id_ls': [],
                'year': None,
                'month': None,
                'intercalary': None,
                'sex_year': None
            }

        g = df_candidates[df_candidates['date_index'] == date_idx].copy()
        if g.empty:
            continue
        
        # Determine what constraints this date has
        has_year = g['year'].notna().any()
        has_sex_year = g['sex_year'].notna().any()
        has_month = g['month'].notna().any() and not g['month'].isna().all()
        has_day = g['day'].notna().any() and not g['day'].isna().all()
        has_gz = g['gz'].notna().any() and not g['gz'].isna().all()
        has_lp = g['lp'].notna().any() and not g['lp'].isna().all()
        has_intercalary = g['intercalary'].notna().any() and g['intercalary'].notna().any() and (g['intercalary'] == 1).any()
        
        # Determine date type
        is_simple = not has_year and not has_sex_year and not has_month and not has_day and not has_gz and not has_lp
        # Solve based on date type
        if is_simple:
            # Simple date (dynasty/era only)
            result_df, implied = solve_date_simple(
                g, implied, phrase_dic, ruler_can_names, dyn_df, tpq, taq
            )
        elif has_month or has_day or has_gz or has_lp:
            # Date with lunar constraints
            # First handle year if present
            if has_year or has_sex_year:
                g, implied = solve_date_with_year(
                    g, implied, phrase_dic, ruler_can_names, dyn_df, era_df, tpq, taq,
                    has_month, has_day, has_gz, has_lp
                )
            # Then handle lunar constraints
            if g.empty:
                # If g became empty after year filtering, create empty result
                result_df = pd.DataFrame()
                
            else:
                month_val = g.iloc[0].get('month') if has_month and pd.notna(g.iloc[0].get('month')) else None
                day_val = g.iloc[0].get('day') if has_day and pd.notna(g.iloc[0].get('day')) else None
                gz_val = g.iloc[0].get('gz') if has_gz and pd.notna(g.iloc[0].get('gz')) else None
                lp_val = g.iloc[0].get('lp') if has_lp and pd.notna(g.iloc[0].get('lp')) else None
                intercalary_val = 1 if has_intercalary else None
                result_df, implied = solve_date_with_lunar_constraints(
                    g, implied, phrase_dic, ruler_can_names, dyn_df, lunar_table,
                    month=month_val, day=day_val, gz=gz_val, lp=lp_val, intercalary=intercalary_val,
                    tpq=tpq, taq=taq, pg=pg, gs=gs, jd_out=jd_out
                )
                # If lunar constraints resulted in no matches (likely due to corruption),
                # return the original input dataframe instead of empty
                if result_df.empty:
                    df = g.copy()
                    df['error_str'] += "Anomaly in lunar constraint solving; "
                    # raise Exception("External fallback sigma, should not be necessary")


            # Add metadata to result_df if not empty
            if not result_df.empty:
                if 'cal_stream' in result_df.columns and 'ind_year' in result_df.columns:
                    result_df = result_df.sort_values(by=['cal_stream', 'ind_year'])
        else:
            # Year-only date (no month/day constraints)
            result_df, implied = solve_date_with_year(
                g, implied, phrase_dic, ruler_can_names, dyn_df, era_df, tpq, taq,
                False, False, False, False
            )
            # If year-only date solving resulted in no matches, return original candidates
            if result_df.empty:
                result_df = g.copy()
                result_df['error_str'] += "Year-only date solving failed; "

        # Add date_index and date_string to result
        if not result_df.empty:
            result_df['date_index'] = date_idx
            result_df['date_string'] = g.iloc[0].get('date_string', '') if not g.empty else 'unknown'
            all_results.append(result_df)
    
    # Combine all results
    if all_results:
        output_df = pd.concat(all_results, ignore_index=True)
    else:
        output_df = pd.DataFrame()

    # Return XML string (unchanged)
    xml_string = et.tostring(xml_root, encoding='utf8', pretty_print=True).decode('utf8')

    return xml_string, output_df


def generate_report_from_dataframe(output_df, phrase_dic, jd_out):
    """
    Generate human-readable report from processed dataframe.

    :param output_df: DataFrame with processed date results (includes error_str, date_string, etc.)
    :param phrase_dic: Dictionary with UI phrases
    :param jd_out: Whether to output Julian Day numbers
    :return: Formatted report string
    """
    if output_df.empty:
        return "No matches found"

    # Prepare dataframe for vectorized formatting
    df = output_df.copy()

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
    df.loc[mask & (df["year"] != 1), "year_str"] = df.loc[mask & (df["year"] != 1), "year"].astype(int).map(lambda x: str(numcon(x)) + "年")

    # Format month strings
    df["month_str"] = ""
    m = df["month"].notna()
    df.loc[m & (df["month"] == 1), "month_str"] = "正月"
    df.loc[m & (df["month"] != 1), "month_str"] = df.loc[m & (df["month"] != 1), "month"].astype(int).map(lambda x: str(numcon(x)) + "月")

    # Intercalary marker
    df["int_str"] = ""
    df.loc[df.get("intercalary", pd.Series(index=df.index)).fillna(0).astype(int) == 1, "int_str"] = "閏"

    # Day strings
    df["day_str"] = ""
    d = (df["day"].notna()) & (df.get("lp", 0) != 0)
    df.loc[d, "day_str"] = df.loc[d, "day"].astype(int).map(lambda x: str(numcon(x)) + "日")

    # Sexagenary day
    df["gz_str"] = ""
    gz_mask = df["gz"].notna()
    df.loc[gz_mask, "gz_str"] = df.loc[gz_mask, "gz"].astype(int).map(ganshu)

    # Lunar phase
    df["lp_str"] = ""
    lp_mask = df["lp"].notna()
    lp_d = {0: '朔', -1: '晦'}
    df.loc[lp_mask, "lp_str"] = df.loc[lp_mask, "lp"].astype(int).map(lambda x: lp_d.get(x, ''))

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
                "年間（" + df.loc[era_only_mask, "era_start_year"].astype(int).astype(str) +
                "–" + df.loc[era_only_mask, "era_end_year"].astype(int).astype(str) + "）"
            )
        # else: no era processing needed
    except Exception as e:
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
        df.loc[year_only_mask, "jdn_str"] = "（" + df.loc[year_only_mask, "ind_year"].astype(int).astype(str) + "）"

    # Combine all components into report_line
    df["report_line"] = (
        df["dyn_name"] + df["ruler_name"] + df["era_name"] +
        df["year_str"] + df["int_str"] + df["month_str"] +
        df["day_str"] + df["gz_str"] + df["lp_str"] +
        df["range_str"] + df["jdn_str"]
    )

    # Group by date_index and combine lines
    lines_by_date = (
        df.groupby("date_index")["report_line"]
        .agg(lambda s: "\n".join([x for x in s if x]))
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


def cjk_date_interpreter(ui, lang='en', jd_out=False, pg=False, gs=None, tpq=-3000, taq=3000, civ=None, sequential=True):
    # Start overall timing
    start_time = time.time()
    timing_info = {}

    # Defaults
    if gs is None:
        gs = [1582, 10, 15]
    if civ is None:
        civ = ['c', 'j', 'k']

    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr

    if sequential:
        # Convert string to XML, tag all date elements
        xml_string = tag_date_elements(ui, civ=civ)

        # Consolidate adjacent date elements
        xml_string = consolidate_date(xml_string)

        # Remove non-date text
        xml_string = strip_text(xml_string)
        
        # Index date nodes
        xml_string = index_date_nodes(xml_string)
        
        # Load calendar tables
        tables = prepare_tables(civ=civ)
        
        # Extract dates using optimized bulk function
        xml_string, output_df = extract_date_table_bulk(
            xml_string, pg=pg, gs=gs, lang=lang,
            tpq=tpq, taq=taq, jd_out=jd_out, civ=civ, tables=tables, sequential=sequential
        )

        # Extract tables for canonical name addition
        era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = tables

        # Add canonical names to all results
        if not output_df.empty:
            output_df = add_can_names_bulk(output_df, ruler_can_names, dyn_df)

        # Generate report from dataframe
        output_string = generate_report_from_dataframe(output_df, phrase_dic, jd_out)

        output_df.to_csv('debug_output_df.csv')

    else:
        ui = ui.replace(' ', '')
        ui = re.sub(r'[,;]', r'\n', ui)
        items = re.split(r'\n', ui)
        output_string = ''
        for item in items:
            if item != '':
                # Reset implied state for each date in non-sequential mode
                implied = {
                    'dyn_id_ls': [],
                    'ruler_id_ls': [],
                    'era_id_ls': [],
                    'year': None,
                    'month': None,
                    'intercalary': None,
                    'sex_year': None
                }

                # Convert string to XML, tag all date elements
                xml_string = tag_date_elements(item, civ=civ)

                # Consolidate adjacent date elements
                xml_string = consolidate_date(xml_string)

                # Remove non-date text
                xml_string = strip_text(xml_string)
                
                # Index date nodes
                xml_string = index_date_nodes(xml_string)
                
                # Load calendar tables
                tables = prepare_tables(civ=civ)
                
                # Extract dates using optimized bulk function
                xml_string, output_df = extract_date_table_bulk(
                    xml_string, pg=pg, gs=gs, lang=lang,
                    tpq=tpq, taq=taq, jd_out=jd_out, civ=civ, tables=tables, sequential=False
                )

                # Extract tables for canonical name addition
                era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names = tables

                # Add canonical names to all results
                if not output_df.empty:
                    output_df = add_can_names_bulk(output_df, ruler_can_names, dyn_df)

                # Generate report from dataframe
                report = generate_report_from_dataframe(output_df, phrase_dic, jd_out)

                output_string += report + '\n\n'
    return output_string
