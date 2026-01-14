import lxml.etree as et
import pandas as pd
from sanmiao import extract_date_table_bulk, filter_annals, backwards_fill_days
from sanmiao.config import DEFAULT_TPQ, DEFAULT_TAQ


ui = """
<root>
<date index="0" dyn_id="50" ruler_id="3910" era_id="113" year="1"><era>鳳皇</era><year>元年</year></date>
<date index="1"><dyn>魏</dyn><suffix>末</suffix></date>
<date index="2"><era>太和</era><year>元年</year></date>
<date index="3"><era>太平</era><year>元年</year></date>
<date index="4" year="2"><year>三年</year><month>三月</month></date>
<date index="5"><era>鳳皇</era><year>二年</year></date>
</root>
"""

def my_post_normalize(df):
    df = backwards_fill_days(df)
    df = filter_annals(df)
    return df


# Extract and resolve dates using optimized bulk function
xml_string, output_df, implied = extract_date_table_bulk(
    ui, sequential=True, proliferate=False, attributes=True, 
    post_normalisation_func=None
)

print(output_df[['date_string', 'dyn_id', 'ruler_id', 'era_id', 'error_str']])