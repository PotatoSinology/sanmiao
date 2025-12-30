try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files
import re
import numpy as np
import pandas as pd
import lxml.etree as et
from math import floor
import warnings

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

# Suppress FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning)

# Define terms for conversion below
season_dic = {'春': 1, '夏': 2, '秋': 3, '冬': 4}
lp_dic = {'朔': 0, '晦': -1}

# TODO load tables only once


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


def load_csv(csv_name):
    csv_path = data_dir / csv_name
    try:
        df = pd.read_csv(csv_path, index_col=False, encoding='utf-8')
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file {csv_name} not found in package data")
    return df


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


def load_num_tables(civ=['c', 'j', 'k']):
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


def load_tag_tables(civ=['c', 'j', 'k']):
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


def ganshu(input, en=False):
    """
    Convert from sexagenary counter (string) to number (int) and vice versa.
    :param input: str, int, or float
    :param en: Boolean, whether into Pinyin (vs Chinese)
    :return: int or str
    """
    result = 'ERROR'
    if not en:
        ganzhi_dict = {
            '甲子': 1, '乙丑': 2, '丙寅': 3, '丁卯': 4, '戊辰': 5, '己巳': 6, '庚午': 7, '辛未': 8, '壬申': 9,
            '癸酉': 10,
            '甲戌': 11, '乙亥': 12, '丙子': 13, '丁丑': 14, '戊寅': 15, '己卯': 16, '庚辰': 17, '辛巳': 18, '壬午': 19,
            '癸未': 20,
            '甲申': 21, '乙酉': 22, '丙戌': 23, '丁亥': 24, '戊子': 25, '己丑': 26, '庚寅': 27, '辛卯': 28, '壬辰': 29,
            '癸巳': 30,
            '甲午': 31, '乙未': 32, '丙申': 33, '丁酉': 34, '戊戌': 35, '己亥': 36, '庚子': 37, '辛丑': 38, '壬寅': 39,
            '癸卯': 40,
            '甲辰': 41, '乙巳': 42, '丙午': 43, '丁未': 44, '戊申': 45, '己酉': 46, '庚戌': 47, '辛亥': 48, '壬子': 49,
            '癸丑': 50,
            '甲寅': 51, '乙卯': 52, '丙辰': 53, '丁巳': 54, '戊午': 55, '己未': 56, '庚申': 57, '辛酉': 58, '壬戌': 59,
            '癸亥': 60
        }
    else:
        ganzhi_dict = {
            'jiazi₀₁': 1, 'yichou₀₂': 2, 'bingyin₀₃': 3, 'dingmao₀₄': 4, 'wuchen₀₅': 5, 'jisi₀₆': 6, 'gengwu₀₇': 7,
            'xinwei₀₈': 8, 'renshen₀₉': 9, 'guiyou₁₀': 10,
            'jiaxu₁₁': 11, 'yihai₁₂': 12, 'bingzi₁₃': 13, 'dingchou₁₄': 14, 'wuyin₁₅': 15, 'jimao₁₆': 16,
            'gengchen₁₇': 17, 'xinsi₁₈': 18, 'renwu₁₉': 19, 'guiwei₂₀': 20,
            'jiashen₂₁': 21, 'yiyou₂₂': 22, 'bingxu₂₃': 23, 'dinghai₂₄': 24, 'wuzi₂₅': 25, 'jichou₂₆': 26,
            'gengyin₂₇': 27, 'xinmao₂₈': 28, 'renchen₂₉': 29, 'guisi₃₀': 30,
            'jiawu₃₁': 31, 'yiwei₃₂': 32, 'bingshen₃₃': 33, 'dingyou₃₄': 34, 'wuxu₃₅': 35, 'jihai₃₆': 36,
            'gengzi₃₇': 37, 'xinchou₃₈': 38, 'renyin₃₉': 39, 'guimao₄₀': 40,
            'jiachen₄₁': 41, 'yisi₄₂': 42, 'bingwu₄₃': 43, 'dingwei₄₄': 44, 'wushen₄₅': 45, 'jiyou₄₆': 46,
            'gengxu₄₇': 47, 'xinhai₄₈': 48, 'renzi₄₉': 49, 'guichou₅₀': 50,
            'jiayin₅₁': 51, 'yimao₅₂': 52, 'bingchen₅₃': 53, 'dingsi₅₄': 54, 'wuwu₅₅': 55, 'jiwei₅₆': 56,
            'gengshen₅₇': 57, 'xinyou₅₈': 58, 'renxu₅₉': 59, 'guihai₆₀': 60
        }
    if isinstance(input, str):
        input = re.sub('景', '丙', input)
        result = ganzhi_dict.get(input)
    else:
        try:
            input = int(input)
            input = int((input - 1) % 60 + 1)
            for key, val in ganzhi_dict.items():
                if val == int(input):
                    result = key
        except Exception:
            pass
    return result


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


def iso_to_jdn(date_string, proleptic_gregorian=False, gregorian_start=[1582, 10, 15]):
    """
    Convert a date string (YYYY-MM-DD) to a Julian Day Number (JDN).

    :param date_string: str (date in "YYYY-MM-DD" format, e.g., "2023-01-01" or "-0044-03-15")
    :param proleptic_gregorian: bool
    :param gregorian_start: list
    :return: float (Julian Day Number) or None if invalid
    """
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


def jdn_to_iso(jdn, proleptic_gregorian=False, gregorian_start=[1582, 10, 15]):
    """
    Convert a Julian Day Number (JDN) to a date string (YYYY-MM-DD).

    :param jdn: int or float (e.g., 2299159.5 = 1582-10-15)
    :param proleptic_gregorian: bool
    :param gregorian_start: list
    :return: str (ISO date string) or None if invalid
    """
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


def jdn_to_ccs(x, by_era=True, proleptic_gregorian=False, gregorian_start=[1582, 10, 15], lang='en', civ=['c', 'j', 'k']):
    """
    Convert Julian Day Number to Chinese calendar string.
    :param x: float (Julian Day Number) or str (ISO date string Y-M-D)
    :param by_era: bool (filter from era JDN vs index year)
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return output_string: str
    """
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


def jy_to_ccs(y, lang='en', civ=['c', 'j', 'k']):
    """
    Convert Western year to Chinese calendar string.
    :param y: int
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return output_string: str
    """
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


def tag_date_elements(text, civ=['c', 'j', 'k']):
    """
    Tag and clean Chinese string containing date with relevant elements for extraction. Each date element remains
    separated, awaiting "consolidation."
    :param text: str
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return: str (XML)
    """
    bu = text
    # Retrieve tag tables
    era_tag_df = load_csv('era_table.csv')
    # Filter era_tag_df by cal_stream
    cal_streams = get_cal_streams_from_civ(civ)
    if cal_streams is not None:
        era_tag_df_before = era_tag_df.copy()
        era_tag_df = era_tag_df[era_tag_df['cal_stream'].notna()]
        # Convert cal_stream to float for comparison to avoid int/float mismatch
        era_tag_df = era_tag_df[era_tag_df['cal_stream'].astype(float).isin(cal_streams)]
    dyn_tag_df, ruler_tag_df = load_tag_tables(civ=civ)
    # Sort tables by character length
    era_tag_df['nbcar'] = era_tag_df['era_name'].str.len()
    era_tag_df = era_tag_df[['era_name', 'nbcar']]
    era_tag_df = era_tag_df.sort_values(by=['nbcar'], ascending=False)
    dyn_tag_df['nbcar'] = dyn_tag_df['string'].str.len()
    dyn_tag_df = dyn_tag_df[['string', 'nbcar']]
    dyn_tag_df = dyn_tag_df.sort_values(by=['nbcar'], ascending=False)
    ruler_tag_df['nbcar'] = ruler_tag_df['string'].str.len()
    ruler_tag_df = ruler_tag_df[['string', 'nbcar']]
    ruler_tag_df = ruler_tag_df.sort_values(by=['nbcar'], ascending=False)
    # Reduce to lists
    era_tag_list = era_tag_df['era_name'].unique()
    dyn_tag_list = dyn_tag_df['string'].unique()
    ruler_tag_list = ruler_tag_df['string'].unique()
    # Normal dates #####################################################################################################
    # Year (must come before era names to avoid conflicts on 元)
    re_year = r'(([一二三四五六七八九十]+|元)[年|載])'
    text = re.sub(re_year, r'<date><year>\1</year></date>', text)
    re_year = r'([廿卅卌卄丗])<date><year>'
    text = re.sub(re_year, r'<date><year>\1', text)
    # I have to follow year
    text = re.sub('閏月', f'<date><int>閏</int><month>月</month></date>', text)
    re_month = r'閏((十有[一二]|正)[月])'
    text = re.sub(re_month, r'<date><int>閏</int><month>\1</month></date>', text)
    re_month = r'((十有[一二]|正)[月])'
    text = re.sub(re_month, r'<date><month>\1</month></date>', text)
    re_month = r'閏(([一二三四五六七八九十]+|正)[月])'
    text = re.sub(re_month, r'<date><int>閏</int><month>\1</month></date>', text)
    re_month = r'(([一二三四五六七八九十]+|正)[月])'
    text = re.sub(re_month, r'<date><month>\1</month></date>', text)
    # I have to follow month
    re_day = r'(([廿卅卌卄丗一二三四五六七八九十]+)日)'
    text = re.sub(re_day, r'<date><day>\1</day></date>', text)
    # Sexegenary
    re_gz = r'([甲乙丙丁戊己庚辛壬癸景][子丑寅卯辰巳午未申酉戌亥])'
    text = re.sub(re_gz, r'<date><gz>\1</gz></date>', text)
    # Sexagenary year
    find = r'(歲[次在])<date><gz>(\w+)</gz>'
    replace = r'<date><filler>\1</filler><sexYear>\2</sexYear>'
    text = re.sub(find, replace, text)
    # NM date
    find = r'<date><gz>(\w+)</gz></date>朔，*<date><day>'
    replace = r'<date><nmdgz>\1</nmdgz><lp_filler>朔</lp_filler><day>'
    text = re.sub(find, replace, text)
    find = r'朔<date><gz>(\w+)</gz></date>，*<date><day>'
    replace = r'<date><lp_filler>朔</lp_filler><nmdgz>\1</nmdgz><day>'
    text = re.sub(find, replace, text)
    # Season
    text = re.sub(r'([春秋冬夏])', r'<date><season>\1</season></date>', text)
    # Lunar phases
    text = re.sub(rf'>([朔晦])', r'><date><lp>\1</lp></date>', text)
    if 'metadata' in text:
        text = clean_attributes(text)
    # Era names ########################################################################################################
    # Reduce list
    era_tag_list = [i for i in era_tag_list if isinstance(i, str)]
    era_tag_list = [i for i in era_tag_list if i in text]
    # Tag
    for string in era_tag_list:
        # In longer format
        text = re.sub(string, f'<date><era>{string}</era></date>', text)
        # Lone
        find = r'</era></date>(之?初|中|之?末|之?季|末年|之?時|之世)'
        replace = r'</era><suffix>\1</suffix></date>'
        text = re.sub(find, replace, text)
    if 'metadata' in text:
        text = clean_attributes(text)
    # Ruler Names ######################################################################################################
    # Reduce list
    ruler_tag_list = [i for i in ruler_tag_list if i in text]
    # Tag
    for string in ruler_tag_list:
        text = re.sub(string, f'<date><ruler>{string}</ruler></date>', text)
        # Lone
        find = r'</ruler></date>(之?初|中|之?末|之?季|末年|之?時|之世|即位)'
        replace = r'</ruler><suffix>\1</suffix></date>'
        text = re.sub(find, replace, text)
    if 'metadata' in text:
        text = clean_attributes(text)
    # Dynasty Names ####################################################################################################
    # Reduce list
    dyn_tag_list = [i for i in dyn_tag_list if i in text]
    # Tag
    for string in dyn_tag_list:
        text = re.sub(string, f'<date><dyn>{string}</dyn></date>', text)
        # Lone
        find = r'</dyn></date>(之?初|中|之?末|之?季|末年|之?時|之世)'
        replace = r'</dyn><suffix>\1</suffix></date>'
        text = re.sub(find, replace, text)
    if 'metadata' in text:
        text = clean_attributes(text)
    else:
        text = '<root>' + text + '</root>'
    # Clean nested tags ################################################################################################
    # Convert to XML
    try:
        xml_root = et.ElementTree(et.fromstring(text)).getroot()
    except Exception:
        text = '<root>Oops</root>'
        xml_root = et.ElementTree(et.fromstring(text)).getroot()
    # Iterate through nodes
    base_tags = ['year', 'int', 'month', 'day', 'gz', 'ruler', 'era', 'dyn', 'suffix', 'lp', 'sexYear', 'nmdgz', 'lp_filler']
    for tag in base_tags:
        for node in xml_root.xpath(f'.//{tag}'):
            for sn in node.xpath('.//*'):
                sn.tag = 'to_remove'
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
    # Remove spaces and line breaks
    text = re.sub(r'[\s\n\r]', '', text)
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
        return bu


def clean_nested_tags(text):
    xml_root = et.ElementTree(et.fromstring(text)).getroot()
    # Clean
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


def xml_to_table(text, filter=True):
    # Parse XML
    xml_root = et.ElementTree(et.fromstring(text)).getroot()
    # Iterate through nodes
    ind = 1
    list_for_df = []
    implied = {}
    for node in xml_root.xpath('.//date'):
        # Blank dictionary
        dic = {'index': ind, 'source_text': node.xpath('normalize-space(string())')}
        # Set index
        node.set('index', str(ind))
        ind += 1
        # Pull strings of dynasty, ruler, era
        d = node.xpath('.//dyn')
        if node.attrib.get('dyn_id') is not None:
            dic.update({'dyn_id': node.attrib.get('dyn_id')})
        elif len(d) > 0:
            dic.update({'dyn_str': d[0].xpath('normalize-space(string())')})
        d = node.xpath('.//ruler')
        if node.attrib.get('ruler_id') is not None:
            dic.update({'ruler_id': node.attrib.get('ruler_id')})
        elif len(d) > 0:
            dic.update({'ruler_str': d[0].xpath('normalize-space(string())')})
        d = node.xpath('.//era')
        if node.attrib.get('era_id') is not None:
            dic.update({'era_id': node.attrib.get('era_id')})
        elif len(d) > 0:
            dic.update({'era_str': d[0].xpath('normalize-space(string())')})
        # Convert year
        d = node.xpath('.//year')
        if node.attrib.get('year') is not None:
            dic.update({'year': node.attrib.get('year')})
        elif len(d) > 0:
            year_str = d[0].xpath('normalize-space(string())')
            if year_str == '元年':
                dic.update({'year': 1})
            else:
                dic.update({'year': numcon(year_str)})
        # Convert sexagenary year
        d = node.xpath('.//sexYear')
        if node.attrib.get('sex_year') is not None:
            dic.update({'sex_year': node.attrib.get('sex_year')})
        elif len(d) > 0:
            dic.update({'sex_year': ganshu(d[0].xpath('normalize-space(string())'))})
        # Convert season
        d = node.xpath('.//season')
        if node.attrib.get('season') is not None:
            dic.update({'season': node.attrib.get('season')})
        elif len(d) > 0:
            dic.update({'season': season_dic.get(d[0].xpath('normalize-space(string())'))})
        # Intercalary
        d = node.xpath('.//int')
        if node.attrib.get('int') is not None:
            dic.update({'int': node.attrib.get('int')})
        elif len(d) > 0:
            dic.update({'intercalary': 1})
        # Convert month
        d = node.xpath('.//month')
        if node.attrib.get('int') is not None:
            dic.update({'int': node.attrib.get('int')})
        if len(d) > 0:
            month_str = d[0].xpath('normalize-space(string())')
            if month_str == '正月':
                dic.update({'month': 1})
            elif month_str == '臘月':
                dic.update({'month': 12})
            elif month_str == '一月':
                dic.update({'month': 14})
            else:
                dic.update({'month': numcon(month_str)})
        # Convert new moon sexagenary day
        d = node.xpath('.//nmdgz')
        if node.attrib.get('nmd_gz') is not None:
            dic.update({'nmd_gz': node.attrib.get('nmd_gz')})
        elif len(d) > 0:
            dic.update({'nmd_gz': ganshu(d[0].xpath('normalize-space(string())'))})
        # Convert sexagenary day
        d = node.xpath('.//gz')
        if node.attrib.get('gz') is not None:
            dic.update({'gz': node.attrib.get('gz')})
        elif len(d) > 0:
            dic.update({'gz': ganshu(d[0].xpath('normalize-space(string())'))})
        # Convert day date
        d = node.xpath('.//day')
        if node.attrib.get('day') is not None:
            dic.update({'day': node.attrib.get('day')})
        elif len(d) > 0:
            dic.update({'day': numcon(d[0].xpath('normalize-space(string())'))})
        # Convert lunar phase
        d = node.xpath('.//lp')
        if node.attrib.get('lp') is not None:
            dic.update({'lp': node.attrib.get('lp')})
        elif len(d) > 0:
            dic.update({'lp': lp_dic.get(d[0].xpath('normalize-space(string())'))})
        # Check suffixes
        for s in node.xpath('.//suffix'):
            if s.xpath('string()') in ['即位']:
                dic.update({'year': 1})
        # Filter #######################################################################################################
        new = {}
        new.update(implied)
        new.update(dic)
        new.pop('index')
        offload_bool = True
        # Remove sequential duplicates
        if len(list_for_df) > 0:
            if new == implied and filter:
                offload_bool = False
        # Offload
        if offload_bool:
            list_for_df.append(dic)
            # print(dic)
        implied = new
    # Return to string
    text = et.tostring(xml_root, encoding='utf8', pretty_print=True).decode('utf8')
    # Export
    return text, list_for_df


def interpret_date(node, correct=True, implied=None, pg=False, gs=[1582, 10, 15], lang="en", tpq=-3000, taq=3000, jd_out=False, civ=['c', 'j', 'k']):
    """
    Filter strings and numbers in date to find matches.

    :param node: XML node
    :param correct: bool
    :param implied: dict
    :param pg: bool
    :param gs: list (YYYY, MM, DD)
    :param lang: str
    :param tpq: int
    :param taq: int
    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) to filter by civilization
    :return: df (DataFrame, output (str), implied (dict)
    """

    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    # Error check on Gregorian start date
    gs = sanitize_gs(gs)
    # Retrieve tables
    era_df, dyn_df, ruler_df, lunar_table = load_num_tables(civ=civ)
    dyn_tag_df, ruler_tag_df = load_tag_tables(civ=civ)
    dyn_can_names = dyn_df[['dyn_id', 'dyn_name']].copy().drop_duplicates()
    rul_dyn = ruler_df[['person_id', 'dyn_id']].copy().rename(columns={'person_id': 'ruler_id'})


    def preference_filtering(table):
        if table.shape[0] < 2:
            return table
        else:
            bu = table.copy()
            era_id_ls = implied.get('era_id_ls')
            # TODO This doesn't work for emperors without eras
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
        table = table.reset_index(drop=True)
        # If dyn_id missing
        a = table[table['dyn_id'].isna()].copy()
        if not a.empty:
            del a['dyn_id']
            a = a.merge(rul_dyn, how='left', on='ruler_id')
            b = table.dropna(subset=['dyn_id'])
            table = pd.concat([a, b])
        # Add names
        ruler_can_names = load_csv('rul_can_name.csv')[['person_id', 'string']]
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
        ruler_can_names = ruler_can_names.rename(columns={'person_id': 'ruler_id', 'string': 'ruler_name'})
        table = table.merge(ruler_can_names, how='left', on='ruler_id')
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
                # Filter DataFrames TODO
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
        # TODO Here, I am randomly assigning cal_stream 1 to all dynasties w/o
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
        # TODO fill out columns
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
            # TODO seasons, insert this into lunar table to deal with wierd years
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
                    # TODO hui is the last day of month x, not the eve of month y; update in Norbert
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
                    df = pd.DataFrame([node.attrib])
                else:
                    del df
                    df = pd.DataFrame()
            if df.empty and not correct:
                df = pd.DataFrame([node.attrib])
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


def cjk_date_interpreter(ui, lang='en', jd_out=False, pg=False, gs=[1582, 10, 15], tpq=-3000, taq=3000, civ=['c', 'j', 'k']):
    if lang == 'en':
        phrase_dic = phrase_dic_en
    else:
        phrase_dic = phrase_dic_fr
    ui = ui.replace(' ', '')
    ui = re.sub(r'[,;]', r'\n', ui)
    items = re.split(r'\n', ui)
    output_string = ''
    for item in items:
        if item != '':
            # Find Chinese characters
            is_ccs = bool(re.search(r'[\u4e00-\u9fff]', item))
            # Find ISO strings
            isos = re.findall(r'-*\d+-\d+-\d+', item)
            is_iso = len(isos) > 0
            # Try to find year / jdn
            is_y = False
            is_jdn = False
            try:
                value = float(item)
                if value.is_integer():  # e.g. 10.0 → True
                    # it's an integer, so maybe a year
                    if len(item.split('.')[0]) > 5:
                        is_jdn = True  # large integer, probably JDN
                        item = float(item)
                    else:
                        is_y = True  # short integer, probably a year
                        item = int(float(item))
                else:
                    is_jdn = True  # non-integer numeric, e.g. 168497.5
                    item = float(item)
            except ValueError:
                pass
            # Proceed accordingly
            if is_jdn or is_iso:
                result = jdn_to_ccs(item, proleptic_gregorian=pg, gregorian_start=gs, lang=lang, civ=civ)
            elif is_y:
                result = jy_to_ccs(item, lang=lang, civ=civ)
            elif is_ccs:
                # Convert string to XML, tag all date elements
                xml_string = tag_date_elements(item, civ=civ)
                # Consolidate
                xml_string = consolidate_date(xml_string)
                # Remove non-date text
                xml_string = strip_text(xml_string)
                # Index XML, convert numbers, export list of dictionaries
                xml_string, ls = xml_to_table(xml_string)
                result = ''
                implied = None
                for node in et.ElementTree(et.fromstring(xml_string)).getroot().xpath('.//date'):
                    # Interpret the date
                    df, report, implied = interpret_date(node, implied=implied, pg=pg, gs=gs, lang=lang, tpq=tpq, taq=taq, jd_out=jd_out, civ=civ)
                    result += report + '\n\n'
            else:
                result = f'{phrase_dic.get("ui")}: {item}\n{phrase_dic.get("nonsense")}'
            if result is not None:
                result = result.rstrip("\n")
                output_string += result + '\n\n'
    output_string = output_string.rstrip("\n")
    return output_string
