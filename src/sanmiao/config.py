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
    'insufficient-information': 'Insufficient information; ',
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
    'month-sexday-mismatch': 'Month-sexDay mismatch; ',
    'month-day-oob': 'Month-day mismatch (out of bounds); '
}

phrase_dic_fr = {
    'ui': 'ENTRÉE UTILISATEUR ', 'matches': 'RÉSULTATS ',
    'unknown-date': 'date inconnue',
    'no-matches': 'Aucun résultat trouvé',
    'insuff-data': 'Données insuffisantes',
    'insufficient-information': 'Informations insuffisantes ; ',
    'too-many-cand': 'candidats. Veuillez affiner la plage de dates.',
    'lunar-constraint-failed': 'Résolution des contraintes lunaires échouée ; ',
    'year-over-max': 'Année hors limites; ',
    'year-solving-failed': 'Résolution de l\'année échouée ; ',
    'year-lun-mismatch': 'Incompatibilité année-lunaison',
    'year-sex-mismatch': 'Incompatibilité année-annéeSex.',
    'dyn-rul-era-mismatch': 'Incompatibilité dyn-souv-ère ; ',
    'year-month-mismatch': 'incompatibilité année-mois ; ',
    'year-int-month-mismatch': 'Incompatibilité année-moisInt. ; ',
    'lp-gz-day-mismatch': 'Incompatibilité phaseLun.-jour-jourSex. ; ',
    'lp-gz-nmdgz-mismatch': 'Incompatibilité phaseLun.-jourSex.-NLjourSex. ; ',
    'lp-gz-mismatch': 'Incompatibilité phaseLun.-jourSex. ; ',
    'lp-gz-month-mismatch': 'Incompatibilité mois-phaseLun.-jourSex. ; ',
    'month-day-gz-mismatch': 'Incompatibilité mois-jour-jourSex. ; ',
    'month-gz-mismatch': 'Incompatibilité mois-jourSex. ; ',
    'month-sexday-mismatch': 'Incompatibilité mois-jourSex. ; ',
    'month-day-oob': 'Incompatibilité mois-jour (hors limites) ; '
}

# Calendar stream mappings
CAL_STREAM_MAPPINGS = {
    'c': [1, 2, 3],  # China
    'j': [4],         # Japan
    'k': [5, 6, 7, 8]  # Korea
}

# Date element types used in tagging
date_elements = ['date', 'year', 'month', 'day', 'gz', 'sexYear', 'era', 'ruler', 'dyn', 'suffix', 'int', 'lp', 'nmdgz', 'lp_filler', 'filler', 'season']


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

# Define terms for conversion below
SEASON_DIC = {'春': 1, '夏': 2, '秋': 3, '冬': 4}
LP_DIC = {'朔': 0, '晦': -1}