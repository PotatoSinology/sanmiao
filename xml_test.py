import lxml.etree as et
import pandas as pd
from sanmiao import extract_date_table_bulk, filter_annals, backwards_fill_days
from sanmiao.config import DEFAULT_TPQ, DEFAULT_TAQ


ui = """
<root>
<p>世宗明皇帝諱毓，小名統萬突，太祖長子也。母曰姚夫人，
<date index="0"><era>永熙</era><year>三年</year></date>，太祖臨<season>夏</season>州，生帝於統萬城，因以名焉。
<date index="1"><era>大統</era><year>十四年</year></date>，封寧都郡公。
<date index="3"><dyn>魏</dyn><ruler>恭帝</ruler><year>三年</year></date>，授大將軍，鎮隴右。
</p>
</root>
"""
# <date index="4"><season>秋</season><month>九月</month><gz>癸亥</gz></date>，至京師，止於舊邸。<date index="5"><gz>甲子</gz></date>，群臣上表勸進，備法駕奉迎。帝固讓，群臣固請，是日，即天王位，大赦天下。<date index="6"><gz>乙丑</gz></date>，朝群臣於延壽殿。</p>

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