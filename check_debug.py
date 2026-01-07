import pandas as pd
df = pd.read_csv('debug_df_candidates.csv')
print('Resolved combinations for 漢獻帝中:')
print(df[['date_index', 'era_id', 'ruler_id', 'dyn_id']].to_string())
