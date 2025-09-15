from sanmiao import cjk_date_interpreter

# See README for entry types, separate entries by commas, semi-colons, or line breaks
ui = """
東漢孝獻皇帝劉協建安十八年二月, 
宋太祖三年四月
313-12-10, -215-10-14
415, 416, -181
"""

print(cjk_date_interpreter(ui, tpq=300, taq=800, jd_out=False, lang='fr'))
