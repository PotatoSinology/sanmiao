# Configuration constants and phrase dictionaries for sanmiao

# Default date ranges
DEFAULT_TPQ = -500  # terminus post quem (earliest date)
DEFAULT_TAQ = 2050  # terminus ante quem (latest date)

# Default Gregorian start date [YYYY, MM, DD]
DEFAULT_GREGORIAN_START = [1582, 10, 15]

# Phrase dictionaries for internationalization
phrase_dic_en = {
    'ui': 'USER INPUT', 'matches': 'MATCHES',
    'unknown-date': 'unknown date',
    'no-matches': 'No matches found',
    'insuff-data': 'Insufficient data',
    'too-many-cand': 'candidates. Please narrow date range.',
    'lunar-constraint-failed': 'Lunar constraint solving failed; ',
    'year-over-max': 'Year out of bounds; ',
    'year-solving-failed': 'Year resolution failed; ',
    'year-lun-mismatch': 'Year-lunation mismatch',
    'year-sex-mismatch': 'Year-sex. year mismatch',
    'dyn-rul-era-mismatch': 'Dyn-rul-era mismatch; ',
    'year-month-mismatch': 'Year-month mismatch; ',
    'year-int-month-mismatch': 'Year-int. month mismatch; ',
    'lp-gz-day-mismatch': 'Lunar phase-sexDay-day mismatch; ',
    'lp-gz-nmdgz-mismatch': 'Lunar phase-day-NMsexDay mismatch; ',
    'lp-gz-mismatch': 'Lunar phase-gz mismatch; ',
    'lp-gz-month-mismatch': 'Lunar phase-gz-month mismatch; ',
    'month-day-gz-mismatch': 'Month-day-gz mismatch; ',
    'month-gz-mismatch': 'Month-gz mismatch; ',
    'month-day-oob': 'Month-day mismatch (out of bounds); '
}

phrase_dic_fr = {
    'ui': 'ENTRÉE UTILISATEUR ', 'matches': 'RÉSULTATS ',
    'unknown-date': 'date inconnue',
    'no-matches': 'Aucun résultat trouvé',
    'insuff-data': 'Données insuffisantes',
    'too-many-cand': 'candidats. Veuillez affiner la plage de dates.',
    'lunar-constraint-failed': 'Résolution des contraintes lunaires échouée ; ',
    'year-over-max': 'Année hors limites; ',
    'year-solving-failed': 'Résolution de l\'année échouée ; ',
    'year-lun-mismatch': 'Incompatibilité année-lunaison',
    'year-sex-mismatch': 'Incompatibilité année-annéeSex.',
    'dyn-rul-era-mismatch': 'Incompatibilité dyn-souv-ère ; ',
    'year-month-mismatch': 'incompatibilité année-mois ; ',
    'year-int-month-mismatch': 'Incompatibilité année-intercal. ; ',
    'lp-gz-day-mismatch': 'Incompatibilité phaseLun.-jour-jourSex. ; ',
    'lp-gz-nmdgz-mismatch': 'Incompatibilité phaseLun.-jourSex.-NLjourSex. ; ',
    'lp-gz-mismatch': 'Incompatibilité phaseLun.-jourSex. ; ',
    'lp-gz-month-mismatch': 'Incompatibilité mois-phaseLun.-jourSex. ; ',
    'month-day-gz-mismatch': 'Incompatibilité mois-jour-jourSex. ; ',
    'month-gz-mismatch': 'Incompatibilité mois-jourSex. ; ',
    'month-day-oob': 'Incompatibilité mois-jour (hors limites) ; '
}

phrase_dic_zh = {
    'ui': '用戶輸入', 'matches': '結果',
    'unknown-date': '未知日期',
    'no-matches': '未找到匹配項',
    'insuff-data': '信息不足',
    'too-many-cand': '候選結果。請縮小日期範圍。',
    'lunar-constraint-failed': '月份約束求解失敗；',
    'year-over-max': '年份超出範圍；',
    'year-solving-failed': '年份解析失敗；',
    'year-lun-mismatch': '年份與月相不匹配',
    'year-sex-mismatch': '年份與干支年不匹配',
    'dyn-rul-era-mismatch': '朝代、君主、年號不匹配；',
    'year-month-mismatch': '年份與月份不匹配；',
    'year-int-month-mismatch': '年份與閏月不匹配；',
    'lp-gz-day-mismatch': '月相、干支日、日期不匹配；',
    'lp-gz-nmdgz-mismatch': '月相、日期、朔日干支不匹配；',
    'lp-gz-mismatch': '月相與干支日不匹配；',
    'lp-gz-month-mismatch': '月份、月相、干支日不匹配；',
    'month-day-gz-mismatch': '月份、日期、干支日不匹配；',
    'month-gz-mismatch': '月份與干支日不匹配；',
    'month-day-oob': '月份與日期不匹配（超出範圍）；'
}

phrase_dic_ja = {
    'ui': 'ユーザー入力', 'matches': '結果',
    'unknown-date': '不明な日付',
    'no-matches': '一致する結果が見つかりません',
    'insuff-data': 'データ不足',
    'too-many-cand': '候補。日付範囲を絞り込んでください。',
    'lunar-constraint-failed': '月制約の解決に失敗しました；',
    'year-over-max': '年が範囲外です；',
    'year-solving-failed': '年の解決に失敗しました；',
    'year-lun-mismatch': '年と月の不一致',
    'year-sex-mismatch': '年と干支年の不一致',
    'dyn-rul-era-mismatch': '王朝・君主・年号の不一致；',
    'year-month-mismatch': '年と月の不一致；',
    'year-int-month-mismatch': '年と閏月の不一致；',
    'lp-gz-day-mismatch': '月相・干支日・日の不一致；',
    'lp-gz-nmdgz-mismatch': '月相・日・朔日干支の不一致；',
    'lp-gz-mismatch': '月相と干支日の不一致；',
    'lp-gz-month-mismatch': '月相・干支日・月の不一致；',
    'month-day-gz-mismatch': '月・日・干支日の不一致；',
    'month-gz-mismatch': '月と干支日の不一致；',
    'month-day-oob': '月と日の不一致（範囲外）；'
}

phrase_dic_de = {
    'ui': 'BENUTZEREINGABE', 'matches': 'ERGEBNISSE',
    'unknown-date': 'unbekanntes Datum',
    'no-matches': 'Keine Übereinstimmungen gefunden',
    'insuff-data': 'Unzureichende Daten',
    'too-many-cand': 'Kandidaten. Bitte Datumsbereich eingrenzen.',
    'lunar-constraint-failed': 'Lösung der Mondphasen-Einschränkung fehlgeschlagen; ',
    'year-over-max': 'Jahr außerhalb des Bereichs; ',
    'year-solving-failed': 'Jahresauflösung fehlgeschlagen; ',
    'year-lun-mismatch': 'Jahr-Mondphase Unstimmigkeit',
    'year-sex-mismatch': 'Jahr-Himmelsstamm-Jahr Unstimmigkeit',
    'dyn-rul-era-mismatch': 'Dynastie-Herrscher-Ära Unstimmigkeit; ',
    'year-month-mismatch': 'Jahr-Monat Unstimmigkeit; ',
    'year-int-month-mismatch': 'Jahr-Schaltmonat Unstimmigkeit; ',
    'lp-gz-day-mismatch': 'Mondphase-Himmelsstamm-Tag Unstimmigkeit; ',
    'lp-gz-nmdgz-mismatch': 'Mondphase-Tag-Nicht-Mond-Himmelsstamm Unstimmigkeit; ',
    'lp-gz-mismatch': 'Mondphase-Himmelsstamm Unstimmigkeit; ',
    'lp-gz-month-mismatch': 'Mondphase-Himmelsstamm-Monat Unstimmigkeit; ',
    'month-day-gz-mismatch': 'Monat-Tag-Himmelsstamm Unstimmigkeit; ',
    'month-gz-mismatch': 'Monat-Himmelsstamm Unstimmigkeit; ',
    'month-day-oob': 'Monat-Tag Unstimmigkeit (außerhalb des Bereichs); '
}

# Helper function to get phrase dictionary based on language code
def get_phrase_dic(lang='en'):
    """
    Get phrase dictionary for the specified language.
    
    :param lang: str, language code ('en', 'fr', 'zh', 'ja', 'de'). Defaults to 'en' if invalid.
    :return: dict, phrase dictionary for the language
    """
    phrase_dics = {
        'en': phrase_dic_en,
        'fr': phrase_dic_fr,
        'zh': phrase_dic_zh,
        'ja': phrase_dic_ja,
        'de': phrase_dic_de
    }
    return phrase_dics.get(lang, phrase_dic_en)  # Default to English if language not found

# Calendar stream mappings
CAL_STREAM_MAPPINGS = {
    'c': [1, 2, 3],  # China
    'j': [4],         # Japan
    'k': [5, 6, 7, 8]  # Korea
}

# Date element types used in tagging
date_elements = ['date', 'year', 'month', 'day', 'gz', 'sexYear', 'era', 'ruler', 'dyn', 'suffix', 'int', 'lp', 'nmdgz', 'lp_filler', 'filler', 'season', 'gy', 'rel']


def get_cal_streams_from_civ(civ) -> list:
    """
    Convert civilization code(s) to list of cal_stream floats.

    :param civ: str ('c', 'j', 'k') or list (['c', 'j', 'k']) or None
    :return: list of floats (to match CSV data type) or None if civ is None
    """
    if civ is None:
        return None

    if isinstance(civ, str):
        civ = [civ]

    streams = []
    for c in civ:
        if c in CAL_STREAM_MAPPINGS:
            streams.extend(CAL_STREAM_MAPPINGS[c])

    # Remove duplicates, sort, and convert to float to match CSV data type
    return sorted([float(x) for x in set(streams)]) if streams else None


def sanitize_gs(gs):
    """
    Return a list [year, month, day] of ints if valid,
    otherwise the default [1582, 10, 15].
    """
    if not isinstance(gs, (list, tuple)):
        return DEFAULT_GREGORIAN_START
    if len(gs) != 3:
        return DEFAULT_GREGORIAN_START
    try:
        y, m, d = [int(x) for x in gs]
        return [y, m, d]
    except (ValueError, TypeError):
        return DEFAULT_GREGORIAN_START


def normalize_defaults(gs=None, civ=None):
    """
    Normalize gs and civ parameters to their default values if None.
    Also sanitizes gs to ensure it's valid (returns default if invalid).
    
    :param gs: Gregorian start date (list or None)
    :param civ: Civilization code(s) (str, list, or None)
    :return: tuple (gs, civ) with defaults applied and gs sanitized
    """
    if gs is None:
        gs = DEFAULT_GREGORIAN_START
    else:
        # Sanitize gs to ensure it's valid, even if provided
        gs = sanitize_gs(gs)
    if civ is None:
        civ = ['c', 'j', 'k']
    return gs, civ

# Define terms for conversion below
SEASON_DIC = {'春': 1, '夏': 2, '秋': 3, '冬': 4}
LP_DIC = {'朔': 0, '晦': -1}