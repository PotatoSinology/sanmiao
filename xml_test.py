import lxml.etree as et
import pandas as pd
from sanmiao import extract_date_table_bulk, prepare_tables, dates_xml_to_df, filter_annals, backwards_fill_days, normalise_date_fields
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
    <head>周書·帝紀·卷七·宣帝·宇文贇·紀第七·<date index="0"><era>大象</era><year>元年</year></date></head>
    <p><date index="1"><era>大象</era><year>元年</year><season>春</season><month>正月</month><gz>癸巳</gz></date>，受朝於露門，帝服通天冠、絳紗袍，群臣皆服漢魏衣冠。大赦，改<date index="2"><dyn>元</dyn><era>大成</era></date>。初置四輔官，以上柱國大冢宰越王盛為大前疑，相州總管蜀國公尉遲迥為大右弼，申國公李穆為大左輔，大司馬隨國公楊堅為大後丞。<date index="3"><gz>癸卯</gz></date>，封皇子衍為魯王。<date index="4"><gz>甲辰</gz></date>，東巡狩。<date index="5"><gz>丙午</gz></date>，日有背。以柱國、常山公于翼為大司徒。<date index="6"><gz>辛亥</gz></date>，以柱國、許國公宇文善為大宗伯。<date index="7"><gz>癸丑</gz></date>，日又背。<date index="8"><gz>戊午</gz></date>，行幸洛陽。立魯王衍為皇太子。</p>
    <p><date index="9"><month>二月</month><gz>癸亥</gz></date>，詔曰：</p>
    <p>於是發山東諸州兵，增<date index="10"><month>一月</month></date>功為四十<date index="11"><day>五日</day></date>役，起洛陽宮。常役四萬人，以迄于晏駕。并移相州六府於洛陽，稱東京六府。殺柱國、徐州總管、郯國公王軌。停南討諸軍。以趙王招女為千金公主，嫁於突厥。<date index="12"><gz>戊辰</gz></date>，以上柱國、鄖國公韋孝寬為徐州總管。<date index="13"><gz>乙亥</gz></date>，行幸鄴。<date index="14"><gz>丙子</gz></date>，初令授總管刺史及行兵者，加持節，餘悉罷之。<date index="15"><gz>辛巳</gz></date>，詔曰：</p>
    <p>帝於是自稱天元皇帝，所居稱天臺，冕有二十四旒，室車服旗鼓，[三]室車服旗鼓宋本、南本、汲本及北史周本紀下、冊府卷一八０二一五九頁、御覽卷一０五五０六頁「室」都作「車」，今據改。明本冊府「鼓」又作「章」，宋本仍作「鼓」。
皆以二十四為節。內史、御正皆置上大夫。皇帝衍稱正陽宮，置納言、御正、諸衛等官，皆准天臺。尊皇太后為天元皇太后。封內史上大夫鄭譯為沛國公。<date index="16"><gz>癸未</gz></date>，日初出及將入時，其中竝有烏色，大如雞卵，經<date index="17"><day>四日</day></date>滅。<date index="18"><gz>戊子</gz></date>，以上柱國大前疑越王盛為太保，大右弼蜀公尉遲迥為大前疑，代王達為大右弼。<date index="19"><gz>辛卯</gz></date>，詔徙鄴城石經於洛陽。又詔曰：「洛陽舊都，今既修復，凡是元遷之戶，竝聽還洛州。此外諸民欲往者，亦任其意。河陽、幽、相、豫、亳、青、徐七總管，受東京六府處分。」</p>
    <p><date index="20"><month>三月</month><gz>壬寅</gz></date>，以上柱國、薛國公長孫覽為涇州總管。<date index="21"><gz>庚申</gz></date>，至自東巡，大陳軍伍，帝親擐甲冑，入自青門。皇帝衍備法駕從入。百官迎於青門外。其時驟雨，儀衛失容。<date index="22"><gz>辛酉</gz></date>，封趙王招第二子貫為永康縣王。[四]封趙王招第二子貫為永康縣王　卷一三趙王招傳作「永康公貫」，北史卷五八作「永康王貫」。按縣王之稱未見他例，疑有誤。</p>
    <p><date index="23"><season>夏</season><month>四月</month><gz>壬戌</gz><lp>朔</lp></date>，有司奏言日蝕，不視事。過時不食，乃臨軒。立妃朱氏為天元帝后。<date index="24"><gz>癸亥</gz></date>，以柱國、畢王賢為上柱國。<date index="25"><gz>己巳</gz></date>，祠太廟。<date index="26"><gz>壬午</gz></date>，大醮於正武殿。<date index="27"><gz>戊子</gz></date>，太白、歲星、辰星合於東井。</p>
    <p><date index="28"><month>五月</month><gz>辛亥</gz></date>，以洺州襄國郡為趙國，以齊州濟南郡為陳國，以豐州武當、安富二郡為越國，以潞州上黨郡為代國，以荊州新野郡為滕國，邑各一萬戶。令趙王招、陳王純、越王盛、代王達、滕王逌竝之國。<date index="29"><gz>癸丑</gz></date>，有流星大如斗，出太微，落落如遺火。是月，遣使簡視京兆及諸州士民之女，充選後宮。突厥寇幷州。</p>
    <p><date index="30"><month>六月</month><gz>丁卯</gz></date>，有流星大如雞子，出氐，西北流，長一丈，入月中。<date index="31"><gz>己巳</gz></date>，月犯房北頭第二星。<date index="32"><gz>乙酉</gz></date>，有流星大如斗，出營室，流入東壁。是月，咸陽有池水變為血。發山東諸州民，修長城。</p>
    <p><date index="33"><season>秋</season><month>七月</month><gz>庚寅</gz></date>，以大司空、畢王賢為雍州牧，大後丞、隨國公楊堅為大前疑，柱國、滎陽公司馬消難為大後丞。<date index="34"><gz>壬辰</gz></date>，熒惑掩房北頭第一星。<date index="35"><gz>丙申</gz></date>，納大後丞司馬消難女為正陽宮皇后。尊天元帝太后李氏為天皇太后。<date index="36"><gz>壬子</gz></date>，改天元帝后朱氏為天皇后。立妃元氏為天右皇后，妃陳氏為天左皇后。</p>
    <p><date index="37"><month>八月</month><gz>庚申</gz></date>，行幸同州。<date index="38"><gz>壬申</gz></date>，還宮。<date index="39"><gz>甲戌</gz></date>，以天左皇后父大將軍陳山提、天右皇后父開府元晟竝為上柱國。山提封鄅國公，晟封翼國公。開府楊雄為邗國公，[五]開府楊雄為邗國公周書卷二九楊紹傳末云：「子雄嗣，<date index="40"><era>大象</era><suffix>末</suffix></date>上柱國、邽國公。」隋書卷四三觀德王雄傳作「邘國公」。北史卷六八楊紹附子雄傳先作「邗」，後又作「邘」此據百衲本，殿本仍作「邗」。按「邽公」衹見周書楊紹傳。「邘」是古國名，疑當作「邘」。
乙弗寔戴國公。初，高祖作刑書要制，用法嚴重。及帝即位，以海內初平，恐物情未附，乃除之。至是大醮於正武殿，告天而行焉。[六]初高祖作刑書要制至告天而行焉　北史卷一０周本紀下「至是」下有「為刑經聖制，其法深刻」九字。御覽卷六三六二八四九頁「初」上有「詔罷高祖所約法」七字，至「乃除之」止。按如周書之文，好似「刑書要制」廢而復行，如北史所述，則廢「刑書要制」在先，這時「告天而行的是宣帝的刑經聖制」。考隋書卷二五刑法志云：「<date index="41"><era>大象</era><year>元年</year></date>又下詔曰：『高祖所立刑書要制，用法深重，其一切除之。』」下又云：「於是又廣刑書要制而更峻其法，謂之刑經聖制。」據隋志所述，<date index="42"><era>大象</era><year>元年</year></date>廢刑書要制，不記月日，以後宣帝所制定的刑經聖制也沒有說何時頒佈，而確是兩件事，並非刑書要制先廢後復。周書卷四０樂運傳，樂運上疏有云：「豈有削嚴刑之詔，未及半祀，便即追改，更嚴前制」，正是指的廢刑書要制，行刑書聖制事。北史的記載大致可信，這年<date index="43"><month>八月</month></date>「告天而行」的，就是刑經聖制。疑周書原來和北史同，後來脫去九字，但冊府卷六一一七三三九頁已同今本，知脫去已久了。至御覽多出的七字，倒像<date index="44"><month>八月</month></date>是廢刑書要制之時，恐未可據。<date index="45"><gz>辛巳</gz></date>，熒惑犯南斗第五星。<date index="46"><gz>壬午</gz></date>，以上柱國、雍州牧、畢王賢為太師，上柱國、郇國公韓建業為大左輔。是月，所在有蟻群鬭，各方四五尺，死者什八九。</p>
    <p><date index="47"><month>九月</month><gz>己酉</gz></date>，太白入南斗。<date index="48"><gz>乙卯</gz></date>，以酆王貞為大冢宰。上柱國、鄖國公韋孝寬為行軍元帥，率行軍總管杞國公亮、郕國公梁士彥以伐陳。遣御正杜杲、禮部薛舒使於陳。</p>
    <p><date index="49"><season>冬</season><month>十月</month><gz>壬戌</gz></date>，歲星犯軒轅大星。是日，帝幸道會苑大醮，以高祖武皇帝配。醮訖，論議於行殿。是歲，初復佛像及天尊像。至是，帝與二像俱南面而坐，大陳雜戲，令京城士民縱觀。<date index="50"><gz>乙酉</gz></date>，熒惑、鎮星合於虛。是月，相州人段德舉謀反，伏誅。</p>
    <p><date index="51"><month>十一月</month><gz>乙未</gz></date>，幸溫湯。<date index="52"><gz>戊戌</gz></date>，行幸同州。<date index="53"><gz>壬寅</gz></date>，還宮。<date index="54"><gz>己酉</gz></date>，有星大如斗，出張，東南流，光明燭地。<date index="55"><gz>丁巳</gz></date>，初鑄永通萬國錢，以一當十，[七]以一當十宋本、汲本、局本「十」作「千」。張元濟以為「十」字誤，云見北史。按北史周本紀下及御覽卷八三六三七三二頁、通典卷九、通鑑卷一七三五四０一頁都作「千」。隋書卷二四食貨志、冊府卷五００五九九三頁作「十」。
與五行大布竝行。是月，韋孝寬拔壽陽，杞國公亮拔黃城，梁士彥拔廣陵。陳人退走。於是江北盡平。</p>
    <p><date index="56"><month>十二月</month><gz>戊午</gz></date>，以災異屢見，帝御路寢，見百官。詔曰：</p>
    <p>於是舍仗衛，往天興宮。百官上表勸復寢膳，許之。<date index="57"><gz>甲子</gz></date>，還宮。御正武殿，集百官及宮人內外命婦，大列妓樂，又縱胡人乞寒，用水澆沃為戲樂。<date index="58"><gz>乙丑</gz></date>，行幸洛陽。帝親御驛馬，日行三百里。四皇后及文武侍衛數百人，竝乘驛以從。仍令四后方駕齊驅，或有先後，便加譴責，人馬頓仆相屬。<date index="59"><gz>己卯</gz></date>，還宮。</p>
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

print(output_df[['date_string', 'ind_year', 'dyn_id', 'ruler_id', 'era_id', 'year', 'month', 'gz', 'error_str']])
