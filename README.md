# TODO
finish toml
install with conda, if I can get that working

# Sanmiao
> **Chinese and Japanese historical date conversion in Python**.

Author: Daniel Patrick Morgan (CNRS-CRCAO)

Sanmiao is a Python package for date conversion to and from Chinese and Japanese historical calendars (3rd cent. B.C.–20th cent.) written by a historian of astronomy. 

GitHub: [https://github.com/architest/pymeeus](https://github.com/architest/pymeeus)

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

Sanmiao uses the astronomical year, where 1 B.C. = 0, 100 B.C. = -99, etc. To convert years, run:

```sh
import sanmiao

year = -99
cjk_date_string = sanmiao.jy_to_ccs(year)
```

To convert a Y-M-D date string or Julian Day Number, run:

```sh
import sanmiao

iso_string = "-99-3-15"
cjk_date_string = sanmiao.jdn_to_ccs(iso_string)

jdn = 1684971.5
cjk_date_string = sanmiao.jdn_to_ccs(jdn)
```

To look up a historical CJK date from a full or partial string, run:

...
## Sources
What distinguishes this date convertor from others is that it uses historical tables based, notably those of Zhang Peiyu[^1] and Uchida Masao,[^2] and it is updated to include new archeological evidence[^3] as well as minor dynasties and reign eras. The tables are based on calculation from contemporary procedure texts (_lifa_ 曆法), eclipses, and recorded dates, and I plan to expand them in future versions to include Korean tables and independantly calculated new moons for minor dynasties running different calendars.

[^1]: Zhang Peiyu 張培瑜, _Sanqianwubai nian liri tianxiang_ 三千五百年曆日天象 (Zhengzhou: Daxiang chubanshe, 1997).

[^2] Uchida Masao, _Nihon rekijitsu genten_ 日本暦日原典 (Tōkyō : Yūzankaku shuppan , 1975).

[^3] E.g., Zhang Peiyu 張培瑜, "Genju xinchu liri jiandu shilun Qin he Han chu de lifa" 根据新出歷日簡牘試論秦和漢初的曆法, _Zhongyuan wenwu_ 中原文物 2007.5: 62–77.

## Contributing

The preferred method to contribute is through forking and pull requests:

1. Fork it (<https://github.com/PotatoSinology/sanmiao/fork>)
2. Create your feature branch (`git checkout -b feature/fooBar`)
3. Commit your changes (`git commit -am 'Add some fooBar'`)
4. Push to the branch (`git push origin feature/fooBar`)
5. Create a new Pull Request