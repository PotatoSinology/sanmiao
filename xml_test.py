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
ui = """
  <body>
    <head>隋書·志·卷二十一·志第十六·天文下·五代災變應</head>
    <p>五代災變應</p>
    <p><date index="0"><dyn>梁</dyn><ruler>武帝</ruler><era>天監</era><year>元年</year><month>八月</month><gz>壬寅</gz></date>，熒惑守南斗。占曰：「糴貴，五穀不成，大旱，多火災，吳、越有憂，宰相死。」是歲大旱，米斗五千，人多餓死。其<date index="1"><year>二年</year><month>五月</month></date>，尚書范雲卒。</p>
    
    <p><astPhen phen="solar_eclipse"><date index="16"><era>普通</era><year>元年</year><season>春</season><month>正月</month><gz>丙子</gz></date>，&lt;ast&gt;日&lt;/ast&gt;&lt;astVerb&gt;有食之&lt;/astVerb&gt;。占曰：「日食，陰侵陽，陽不克陰也，為大水。」其年</astPhen></p>
  </body>
"""


def my_post_normalize(df):
    df = backwards_fill_days(df)
    df = filter_annals(df)
    return df


# Extract and resolve dates using optimized bulk function
xml_string, output_df, implied = extract_date_table_bulk(
    ui, sequential=True, proliferate=False, attributes=True, 
    post_normalisation_func=my_post_normalize
)

print(output_df[['date_string', 'dyn_id', 'ruler_id', 'era_id', 'error_str']])
