from sanmiao import cjk_date_interpreter

# See README for entry types, separate entries by commas, semi-colons, or line breaks
ui = """
東漢孝獻皇帝劉協建安十八年二月
313-12-10
415
宋太祖三年四月
"""

print(cjk_date_interpreter(ui))
