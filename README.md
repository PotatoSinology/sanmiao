# Sanmiao

> **Chinese, Japanese, and Korean historical date conversion in Python**.

Author: Daniel Patrick Morgan (CNRS-CRCAO)

Sanmiao is a Python package for date conversion to and from Chinese, Japanese, and Korean historical calendars (3rd cent. B.C.–20th cent.) written by a historian of astronomy. This package is the back end for the [Sanmiao web app](https://norbert.huma-num.fr/app/sanmiao/index.html).

GitHub: [https://github.com/PotatoSinology/sanmiao](https://github.com/PotatoSinology/sanmiao)

## Installation

The easiest way of installing Sanmiao is using pip:

```sh
pip install sanmiao
```

If you prefer Python3, you can use:

```sh
pip3 install --user sanmiao
```

If you have Sanmiao already installed, but want to upgrade to the latest version:

```sh
pip3 install -U sanmiao
```

## Using Sanmiao

Sanmiao provides a variety of functions for date conversion, which are aggregated in `sanmiao.cjk_date_interpreter()`, which is the back-end for the user-friendly [Sanmiao web app](https://norbert.huma-num.fr/en/sanmiao/index.html). The function `sanmiao.cjk_date_interpreter()` recognises years (e.g., 534), Y-M-D date strings (e.g., -99-3-5, 1532-6-4), Julian Day Numbers (e.g., 1684971.5), and Chinese date strings of differing precision and completeness (e.g., "東漢孝獻皇帝劉協建安十八年二月," "太祖元年," or "三年三月甲申"). These should be separated by commas, semicolons, or line breaks:

```Python
import sanmiao

user_input = """
獻帝建安十八年二月, 
宋太祖三年四月
1313-12-10, -215-10-14
415, -181
"""
result = sanmiao.cjk_date_interpreter(user_input)
print(result)
```

Note that Sanmiao uses the astronomical year, where 1 B.C. = 0, 100 B.C. = -99, etc. The function `sanmiao.cjk_date_interpreter()` has the following parameters and defaults passed to its sub-functions: 

```Python
result = sanmiao.cjk_date_interpreter(
    user_input,  # User input, accepts strings
            lang='en',  # Language: 'en' (English), 'fr' (French), 'zh' (Chinese), 'ja' (Japanese), 'de' (German). Defaults to 'en' if not specified or invalid.
    jd_out=False,  # Julian Day Number in output reports (vs ISO date string)
    pg=False,  # Proleptic Gregorian calendar
    gs=None,  # Start of Gregorian calendar, defaults to [1582, 10, 15] if None
    tpq=-500,  # Terminus post quem (earliest date), defaults to -500
    taq=2050,  # Terminus ante quem (latest date), defaults to 2050
    civ=None,  # Civilisation/s, defaults to ['c', 'j', 'k'] if None; set to ['c'] for China only, ['j'] for Japan only, ['k'] for Korea only
    sequential=True,  # Intelligently fills missing fields in Sinitic date strings from previous ones (when False, proliferate mode finds all candidates for date strings without dynasty, ruler, or era)
    fuzzy=True,  # Cross-script matching (traditional/simplified Chinese, Japanese forms); default True for reports
    )
```

Sanmiao works via XML tagging, and its subcomponents are designed to function independantly of `sanmiao.cjk_date_interpreter()`. The block of functions that handle XML tagging and table extraction are:

```
# Convert string to XML (if necessary), tag all date elements
xml_string = tag_date_elements(text, civ=civ)

# Consolidate adjacent date elements
xml_string = consolidate_date(xml_string)

# Remove lone dynasties, rulers, and eras
xml_root = remove_lone_tags(xml_string)

# Remove non-date text
xml_root = strip_text(xml_root)

# Load calendar tables
tables = prepare_tables(civ=civ)

# Extract dates using optimized bulk function
xml_string, output_df, implied, xml_modified = extract_date_table_bulk(
    xml_root, implied=implied, pg=pg, gs=gs, lang=lang,
    tpq=tpq, taq=taq, civ=civ, tables=tables, sequential=sequential, proliferate=not sequential
)
```

## 'Fuzzy matching'

As of version 0.2.6, Sanmiao features **fuzzy matching**, which normalises input and matches dynasty, era, and ruler names using simplified Chinese forms (`string_simp` / `era_name_simp` in the tag tables). This allows date strings in traditional Chinese, simplified Chinese, or Japanese character forms to be interpreted correctly. Report **headers** echo the user’s original input; resolved **match lines** use traditional canonical names from the tables.

- `cjk_date_interpreter(..., fuzzy=True)` — default for conversion reports (web app).
- `tag_date_elements()`, `extract_date_table_bulk()`, and related XML functions — default `fuzzy=False` for backward-compatible tagging.

For bulk/XML pipelines with `fuzzy=True`, pass `original_text` and `normalized_text` to `extract_date_table_bulk()` to preserve original script in `date_string`, or call `restore_original_date_strings()` on the output dataframe.

## Sources

Sanmiao uses historical tables based on those of Zhang Peiyu[^1] and Uchida Masao,[^2] and it is updated to include new archaeological evidence[^3] as well as minor dynasties and reign eras. The tables are based on calculation from contemporary procedure texts (_lifa_ 曆法), eclipses, and recorded dates. I have supplemented these for the moment with tables from the [Buddhist Studies Time Authority Databases](https://authority.dila.edu.tw/time/) for the Sun-Wu, Liu-Shu, Liao, Jin, and Korea.

The character conversion table used for 'fuzzy matching' was compiled with the help of M. Pandolfino ([mpandolfino](https://github.com/mpandolfino)) as part of [marinaMoji](https://github.com/marinaMoji/marinaMoji).

In future versions, I plan to:

- improve tables and functionalities
- supply supporting textual evidence to table items and, somehow, outputted reports
- provide a concorance and critical comparison of the aforementioned tables, textual evidence, and calculations using contemporary procedure texts
- add Vietnamese tables with the aid of Phạm Vũ Lộc 范武禄
- add Chinese, Japanese, and Vietnamese translations to outputs and to the web app

[^1]: Zhang Peiyu 張培瑜, _Sanqianwubai nian liri tianxiang_ 三千五百年曆日天象 (Zhengzhou: Daxiang chubanshe, 1997).
[^2]: Uchida Masao, _Nihon rekijitsu genten_ 日本暦日原典 (Tōkyō : Yūzankaku shuppan , 1975).
[^3]: E.g., Zhang Peiyu 張培瑜, "Genju xinchu liri jiandu shilun Qin he Han chu de lifa" 根据新出歷日簡牘試論秦和漢初的曆法, _Zhongyuan wenwu_ 中原文物 2007.5: 62–77.

## Contributing

The preferred method to contribute is through forking and pull requests:

1. Fork it (<https://github.com/PotatoSinology/sanmiao/fork>)
2. Create your feature branch (`git checkout -b feature/fooBar`)
3. Commit your changes (`git commit -am 'Add some fooBar'`)
4. Push to the branch (`git push origin feature/fooBar`)
5. Create a new Pull Request

## Supply chain security

Releases published to PyPI from GitHub Actions use [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no long-lived API tokens in the repository) and [PEP 740 digital attestations](https://peps.python.org/pep-0740/) signed via [Sigstore](https://www.sigstore.dev/). Each wheel and sdist is cryptographically linked to the GitHub workflow that built and uploaded it.

To verify a release manually:

```sh
pip install pypi-attestations
pypi-attestations verify pypi \
  --repository https://github.com/PotatoSinology/sanmiao \
  pypi:sanmiao-<version>-py3-none-any.whl
```

Replace `<version>` with the release you want to check. See the [PyPI attestation documentation](https://docs.pypi.org/attestations/consuming-attestations/) for details.