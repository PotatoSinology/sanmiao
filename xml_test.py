import lxml.etree as et
import pandas as pd
from sanmiao import extract_date_table_bulk, prepare_tables, dates_xml_to_df, filter_annals
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
    <head>後漢書·本紀·卷一上·光武帝·劉秀·紀第一上·<date index="0" cal_stream="1" dyn_id="46" ruler_id="3643" era_id="45" year="3" sex_year="24"><era>建武</era><year>三年</year></date></head>
    <p><date index="1"><year>三年</year><season>春</season><month>正月</month><gz>甲子</gz></date>，以偏將軍馮異為征西大將軍，杜茂為驃騎大將軍，大司徒鄧禹及馮異與赤眉戰於回溪，<note type="comm">[一]溪名也，俗名回坑，在今洛州永寧縣東。</note>禹、異敗績。</p>
    <p>征虜將軍祭遵破蠻中，斬張滿。</p>
    <p><date index="2"><gz>辛巳</gz></date>，立皇考南頓君已上四廟。</p>
    <p><date index="3"><gz>壬午</gz></date>，大赦天下。</p>
    <p><date index="4"><int>閏</int><month>月</month><gz>乙巳</gz></date>，大司徒鄧禹免。</p>
    <p>馮異與赤眉戰於崤底，大破之，<note type="comm">[一]崤，山名；底，阪也。一名嶔岑山，在今洛州永寧縣西北。</note>餘眾南向宜陽，<note type="comm">[二]縣名，屬弘農郡，韓國都也，故城在今洛州福昌縣東韓城是也。</note>帝自將征之。<date index="5"><gz>己亥</gz></date>，幸宜陽。<date index="6"><gz>甲辰</gz></date>，親勒六軍，大陳戎馬，大司馬吳漢精卒當前，中軍次之，驍騎、武衞分陳左右。赤眉望見震怖，遣使乞降。<date index="7"><gz>丙午</gz></date>，赤眉君臣面縛，<note type="comm">[三]面，偝也。謂反偝而縛之。</note>奉高皇帝璽綬，<note type="comm">[四]蔡邕獨斷曰：「皇帝六璽，皆玉螭虎紐，文曰『皇帝行璽』、『皇帝之璽』、『皇帝信璽』、『天子行璽』、『天子之璽』、『天子信璽』，皆以武都紫泥封之。」玉璽譜曰：「傳國璽是秦始皇初定天下所刻，其玉出藍田山，丞相李斯所書，其文曰『受命于天，既壽永昌』。高祖至霸上，秦王子嬰獻之。至王莽篡位，就元后求璽，不與，以威逼之，乃出璽投地。璽上螭一角缺。及莽敗，李松持璽詣宛上更始；更始敗，璽入赤眉；劉盆子既敗，以奉光武。」</note>詔以屬城門校尉。<note type="comm">[五]前書曰「城門校尉，掌京師城門屯兵，秩比二千石」也。</note><date index="8"><gz>戊申</gz></date>，至自宜陽，<date index="9"><gz>己酉</gz></date>，詔曰：「群盜縱橫，賊害元元，盆子竊尊號，亂惑天下。朕奮兵討擊，應時崩解，十餘萬眾束手降服，先帝璽綬歸之王府。斯皆祖宗之靈，士人之力，朕曷足以享斯哉！<note type="comm">[六]享，當也。</note>其擇吉日祠高廟，賜天下長子當為父後者爵，人一級。」</p>
    <p><date index="10"><month>二月</month><gz>己未</gz></date>，祠高廟，受傳國璽。</p>
    <p>劉永立董憲為海西王，<note type="comm">[一]海西，縣，屬琅邪郡。</note>張步為齊王。步殺光祿大夫伏隆而反。</p>
    <p>幸懷。遣吳漢率二將軍擊青犢於軹西，大破降之。<note type="comm">[一]軹，縣，屬河內郡，故城在今洛州濟源縣東南。</note></p>
    <p><date index="11"><month>三月</month><gz>壬寅</gz></date>，以大司徒司直伏湛為大司徒。<note type="comm">[一]續漢志曰：「光武即位，依武帝故事置司徒司直，<date index="12"><era>建武</era><year>十一年</year></date>省。」</note></p>
    <p>彭寵陷薊城，寵自立為燕王。</p>
    <p>帝自將征鄧奉，幸堵陽。<date index="13"><season>夏</season><month>四月</month></date>，大破鄧奉於小長安，斬之。</p>
    <p>馮異與延岑戰於上林，破之。<note type="comm">[一]關中上林苑也。</note></p>
    <p>吳漢率七將軍與劉永將蘇茂戰於廣樂，大破之。<note type="comm">[一]廣樂地闕，今宋州虞城縣有長樂故城，蓋避<date index="14"><dyn>隋</dyn><ruler>煬帝</ruler></date>諱。</note>虎牙大將軍蓋延圍劉永於睢陽。</p>
    <p><date index="15"><month>五月</month><gz>己酉</gz></date>，車駕還宮。</p>
    <p><astPhen phen="solar_eclipse"><date index="16"><gz>乙卯</gz><lp>晦</lp></date>，&lt;ast&gt;日&lt;/ast&gt;&lt;astVerb&gt;有食之&lt;/astVerb&gt;。</astPhen><note type="comm">[一]續漢志曰：「日在柳十四度。柳，河南也。時樊崇謀作亂，其<date index="17"><month>七月</month></date>伏誅。」</note></p>
    <p><date index="18"><month>六月</month><gz>壬戌</gz></date>，大赦天下。</p>
    <p>耿弇與延岑戰於穰，大破之。<note type="comm">[一]穰，縣，屬南陽郡，今鄧州縣。</note></p>
    <p><date index="19"><season>秋</season><month>七月</month></date>，征南大將軍岑彭率三將軍伐秦豐，戰於黎丘，大破之，獲其將蔡宏。</p>
    <p><date index="20"><gz>庚辰</gz></date>，詔曰：「吏不滿六百石，下至墨綬長、相，有罪先請。<note type="comm">[一]續漢志曰：「縣大者置令一人，千石；其次置長，四百石；小者三百石。侯國之相亦如之。皆掌理人，並秦制。」</note>男子八十以上，十歲以下，及婦人從坐者，自非不道，詔所名捕，皆不得繫。<note type="comm">[二]詔書有名而特捕者。</note>當驗問者即就驗。女徒雇山歸家。」<note type="comm">[三]前書音義曰：「令甲：女子犯徒遣歸家，每月出錢雇人於山伐木，名曰雇山。」</note></p>
    <p>蓋延拔睢陽，獲劉永，而蘇茂、周建立永子紆為梁王。</p>
    <p><date index="21"><season>冬</season><month>十月</month><gz>壬申</gz></date>，幸舂陵，祠園廟，因置酒舊宅，大會故人父老。<note type="comm">[一]光武舊宅在今隨州棗陽縣東南。宅南二里有白水焉，即張衡所謂「龍飛白水」也。</note><date index="22"><month>十一月</month><gz>乙未</gz></date>，至自舂陵。</p>
    <p>涿郡太守張豐反。<note type="comm">[一]涿郡故城在今幽州范陽縣。</note></p>
    <p>是歲，李憲自稱天子。西州大將軍隗囂奉奏。<note type="comm">[一]時鄧禹承制命囂為西州大將軍，專制涼州、<lp>朔</lp>方事。</note>建義大將軍朱祐率祭遵與延岑戰於東陽，斬其將張成。<note type="comm">[二]東陽，聚名也，故城在今鄧州南。臨淮郡復有東陽縣，非此地也。</note></p>
  </body>
"""

implied = {
    'cal_stream_ls': [],
    'dyn_id_ls': [],
    'ruler_id_ls': [],
    'era_id_ls': [],
    'year': None,
    'month': None,
    'intercalary': None,
    'sex_year': None
}

# Handle both string and Element inputs
if isinstance(ui, str):
    xml_root = et.fromstring(ui)
# Extract date table from XML
df = dates_xml_to_df(xml_root, attributes=True)
# Filter as annals
df = filter_annals(df)
# Prepare tables
tables = prepare_tables(civ=None)
# Extract and resolve dates using optimized bulk function
xml_string, output_df, implied = extract_date_table_bulk(
    xml_root, df=df, implied=implied,
    tables=tables, sequential=True, proliferate=False
)


# print(xml_string)
print()
print(output_df[['date_string', 'ind_year', 'dyn_id', 'ruler_id', 'era_id', 'year', 'month', 'gz', 'error_str']])
output_df.to_csv('output_df.csv')
# TODO hard internal filtering



