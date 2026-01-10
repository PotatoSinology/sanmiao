try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files
import pandas as pd
from pathlib import Path
from functools import lru_cache
from .config import get_cal_streams_from_civ


data_dir = files("sanmiao") / "data"


@lru_cache(maxsize=None)
def _load_csv_cached(csv_name: str) -> pd.DataFrame:
    """
    Load CSV file from package data with caching.

    :param csv_name: str, name of the CSV file to load
    :return: pd.DataFrame, loaded CSV data
    :raises FileNotFoundError: if CSV file is not found
    """
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


def prepare_tables(civ=None):
    """
    Load and prepare all necessary tables for date processing.

    :param civ: list or str, civilization codes to filter by ('c', 'j', 'k')
    :return: tuple of DataFrames (era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names)
    """
    # Default civilisations
    if civ is None:
        civ = ['c', 'j', 'k']
    
    era_df, dyn_df, ruler_df, lunar_table = load_num_tables(civ=civ)
    dyn_tag_df, ruler_tag_df = load_tag_tables(civ=civ)
    ruler_can_names = load_csv('rul_can_name.csv')[['person_id', 'string']].copy()
    
    return era_df, dyn_df, ruler_df, lunar_table, dyn_tag_df, ruler_tag_df, ruler_can_names




def load_num_tables(civ=None):
    """
    Load and filter numerical tables (era, dynasty, ruler, lunar) by civilization.

    :param civ: list or str, civilization codes to filter by ('c', 'j', 'k')
    :return: tuple of DataFrames (era_df, dyn_df, ruler_df, lunar_table)
    """
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
    """
    Load and filter tag tables (dynasty_tags, ruler_tags) by civilization.

    :param civ: list or str, civilization codes to filter by ('c', 'j', 'k')
    :return: tuple of DataFrames (dyn_tag_df, ruler_tag_df)
    """
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