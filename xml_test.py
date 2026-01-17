import lxml.etree as et
import pandas as pd
from sanmiao import extract_date_table_bulk, filter_annals, backwards_fill_days
from sanmiao.config import DEFAULT_TPQ, DEFAULT_TAQ


ui = """
  <body>
    <head>後漢書·本紀·卷六·孝順孝沖孝質帝紀第六·質帝·劉纘</head>
    <p>孝質皇帝諱纘，<note type="comm">[一]謚法：「忠正無邪曰質。」古今注曰：「纘之字曰繼。」</note>肅宗玄孫。曾祖父千乘貞王伉，祖父樂安夷王寵，父勃海孝王鴻，母陳夫人。沖帝不豫，大將軍梁冀徵帝到洛陽都亭。及沖帝崩，皇太后與冀定策禁中，<date index="0" era_id="63" year="1" month="12"><gz>丙辰</gz></date>，使冀持節，以王青蓋車迎帝入南宮。<date index="1"><gz>丁巳</gz></date>，封為建平侯，其日即皇帝位，年八歲。</p>
    <p><date index="2"><gz>己未</gz></date>，葬孝沖皇帝于懷陵。<note type="comm">[一]在洛陽西北十五里，伏侯古今注曰：「高四丈六尺，周百八十三步。」</note></p>
    <p>廣陵賊張嬰等復反，攻殺堂邑、江都長。<note type="comm">[一]堂邑，縣，屬廣陵郡，今揚州六合縣也。</note>九江賊徐鳳等攻殺曲陽、東城長。<note type="comm">[二]曲陽，縣，屬九江郡，在淮曲之陽，故城在今豪州定遠縣西北。東城，縣，故城在定遠縣東南也。</note></p>
    <p><date index="3"><gz>甲申</gz></date>，謁高廟，<date index="4"><gz>乙酉</gz></date>，謁光武廟。</p>
    <p><date index="5" era_id="63" year="2" month="12"><month>二月</month></date>，豫章太守虞續坐贓，下獄死。</p>
    <p><date index="6"><gz>乙酉</gz></date>，大赦天下，賜人爵及粟帛各有差。還王侯所削戶邑。</p>
    <p>彭城王道薨。</p>
    <p>叛羌詣左馮翊梁並降。</p>
    <p><date index="7"><month>三月</month></date>，九江賊馬勉稱「黃帝」。<note type="comm">[一]東觀記曰：「傳勉頭及所帶玉印、鹿皮冠、黃衣詣洛陽，詔懸<season>夏</season>城門外，章示百姓。」</note></p>
    <p><date index="8"><season>夏</season><month>四月</month><gz>壬申</gz></date>，雩。</p>
    <p><date index="9"><gz>庚辰</gz></date>，濟北王安薨。</p>
    <p>丹陽賊陸宮等圍城，燒亭寺，丹陽太守江漢擊破之。</p>
    <p><date index="10"><month>五月</month><gz>甲午</gz></date>，詔曰：「朕以不德，託母天下，布政不明，每失厥中。自<season>春</season>涉<season>夏</season>，大旱炎赫，憂心京京，<note type="comm">[一]爾雅曰：「京京，憂也。」</note>故得禱祈明祀，<note type="comm">[二]寤，覺也。寐，臥也。詩曰：「寤寐永歎，唯憂用老。」</note>將二千石、令長不崇寬和，暴刻之為乎？其令中都官繫囚罪非殊死考未竟者，一切任出，以須立<season>秋</season>。<note type="comm">[三]任，保也。</note>郡國有名山大澤能興雲雨者，二千石長吏各絜齊請禱，謁誠盡禮。又兵役連年，死亡流離，或支骸不斂，或停棺莫收，朕甚愍焉。昔文王葬枯骨，人賴其德。<note type="comm">[四]呂氏<season>春</season><season>秋</season>曰：「<date index="11"><dyn>周</dyn><ruler>文王</ruler></date>使人掘地，得死人骸。文王曰：『更葬之。』吏曰：『此無主。』文王曰：『有天下者，天下之主，今我非其主邪？』遂令吏以衣棺葬之。天下聞之，曰：『文王賢矣。澤及枯骨，又況人乎！』」</note>今遣使者案行，若無家屬及貧無資者，隨宜賜卹，以慰孤魂。」</p>
    <p>是月，下邳人謝安應募擊徐鳳等，斬之。</p>
    <p><date index="12"><gz>丙辰</gz></date>，詔曰：「孝殤皇帝雖不永休祚，而即位踰年，君臣禮成。孝安皇帝承襲統業，而前世遂令恭陵在康陵之上，先後相踰，失其次序，非所以奉宗廟之重，垂無窮之制。昔定公追正順祀，<season>春</season><season>秋</season>善之。<note type="comm">[一]魯閔公立<date index="13"><year>二年</year></date>而薨，次僖公立，僖雖是閔庶兄，然嘗為閔臣，位次當在閔下。後文公即位，乃進僖公神位居閔之上，左傳曰：「躋僖公，逆祀也。」定公<date index="14"><year>八年</year></date>經書「從祀先公」。從，順也。順祀謂退僖神位於閔下。穀梁曰：「從祀先公，貴正也。」</note>其令恭陵次康陵，憲陵次恭陵，以序親秩，為萬世法。」</p>
    <p><date index="15"><month>六月</month></date>，鮮卑寇代郡。</p>
    <p><date index="16"><season>秋</season><month>七月</month><gz>庚寅</gz></date>，阜陵王代薨。</p>
    <p>廬江盜賊攻尋陽，又攻盱台，<note type="comm">[一]音吁夷，今楚州縣也。</note>滕撫遣司馬王章擊破之。</p>
    <p><date index="17"><month>九月</month><gz>庚戌</gz></date>，太傅趙峻薨。</p>
    <p><date index="18"><season>冬</season><month>十一月</month><gz>己丑</gz></date>，南陽太守韓昭坐贓下獄死。<note type="comm">[一]東觀記曰：「強賦一億五千萬，檻車徵下獄。」</note></p>
    <p><date index="19"><gz>丙午</gz></date>，中郎將滕撫擊廣陵賊張嬰，破之。</p>
    <p><date index="20"><gz>丁未</gz></date>，中郎將趙序坐事弃巿。<note type="comm">[一]東觀記曰：「取錢縑三百七十五萬。」</note></p>
    <p>歷陽賊華孟自稱「黑帝」，攻殺九江太守楊岑，滕撫率諸將擊孟等，大破斬之。</p>
  </body>
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