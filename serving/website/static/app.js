/* Apertus Data Search — frontend */

/* ─── Language name map — complete ISO 639-1 + 639-2/T + 639-2/B ─ */
const LANG_NAMES = {
  "aa":"Afar","aai":"Arifama-Miniafia","aak":"Ankave","aar":"Afar",
  "aau":"Abau","aaz":"Amarasi","ab":"Abkhaz","abk":"Abkhazian",
  "abq":"Abaza","abs":"Ambonese Malay","abt":"Ambulas","abx":"Inabaknon",
  "aby":"Aneme Wake","acd":"Gikyode","ace":"Achinese","acf":"Saint Lucian Creole French",
  "ach":"Acoli","acm":"Mesopotamian Arabic","acn":"Achang","acr":"Achi",
  "acu":"Achuar-Shiwiar","ada":"Adangme","adj":"Adioukrou","ady":"Adyghe",
  "ae":"Avestan","aeb":"Tunisian Arabic","aeu":"Akeu","aey":"Amele",
  "af":"Afrikaans","afr":"Afrikaans","agd":"Agarabi","agg":"Angor",
  "agn":"Agutaynen","agr":"Aguaruna","agu":"Aguacateco","agx":"Aghul",
  "aii":"Assyrian Neo-Aramaic","ain":"Ainu (Japan)","aji":"Ajië","ak":"Akan",
  "aka":"Akan","akp":"Siwu","alb":"Albanian","aln":"Gheg Albanian",
  "alp":"Alune","alq":"Algonquin","als":"Tosk Albanian","alt":"Southern Altai",
  "aly":"Alyawarr","alz":"Alur","am":"Amharic","amh":"Amharic",
  "ami":"Amis","amm":"Ama (Papua New Guinea)","amp":"Alamblak","amu":"Guerrero Amuzgo",
  "an":"Aragonese","ang":"Old English (ca. 450-1100)","anp":"Angika","aoj":"Mufian",
  "aom":"Ömie","aoz":"Uab Meto","apc":"Levantine Arabic","ape":"Bukiyip",
  "apr":"Arop-Lokep","ar":"Arabic","ara":"Arabic","arb":"Standard Arabic",
  "arg":"Aragonese","arm":"Armenian","arn":"Mapudungun","ars":"Najdi Arabic",
  "ary":"Moroccan Arabic","arz":"Egyptian Arabic","as":"Assamese","asm":"Assamese",
  "aso":"Dano","ast":"Asturian","ata":"Pele-Ata","atb":"Zaiwa",
  "atj":"Atikamekw","att":"Pamplona Atta","av":"Avaric","ava":"Avaric",
  "ave":"Avestan","avk":"Kotava","avu":"Avokaya","awa":"Awadhi",
  "awx":"Awara","ay":"Aymara","aym":"Aymara","ayr":"Central Aymara",
  "az":"Azerbaijani","azb":"South Azerbaijani","aze":"Azerbaijani","azj":"North Azerbaijani",
  "ba":"Bashkir","bak":"Bashkir","bam":"Bambara","ban":"Balinese",
  "bao":"Waimaha","baq":"Basque","bar":"Bavarian","bas":"Basa (Cameroon)",
  "bba":"Baatonum","bbc":"Batak Toba","bbr":"Girawa","bch":"Bariai",
  "bci":"Baoulé","bcl":"Central Bikol","bdd":"Bunama","bdh":"Baka (South Sudan)",
  "be":"Belarusian","bel":"Belarusian","bem":"Bemba (Zambia)","ben":"Bengali",
  "bew":"Betawi","bfd":"Bafut","bfo":"Malba Birifor","bg":"Bulgarian",
  "bgr":"Bawm Chin","bgs":"Tagabawa","bgt":"Bughotu","bh":"Bihari",
  "bhl":"Bimin","bho":"Bhojpuri","bhp":"Bima","bhw":"Biak",
  "bi":"Bislama","bib":"Bissa","bih":"Bihari","bin":"Bini",
  "bis":"Bislama","biv":"Southern Birifor","bjn":"Banjar","bjr":"Binumarien",
  "bjv":"Bedjond","bku":"Buhid","blh":"Kuwaa","blk":"Pa'o Karen",
  "blz":"Balantak","bm":"Bambara","bmh":"Kein","bmr":"Muinane",
  "bmu":"Somba-Siawari","bn":"Bengali","bno":"Bantoanon","bnp":"Bola",
  "bo":"Tibetan","bod":"Tibetan","boj":"Anjam","bon":"Bine",
  "bos":"Bosnian","bpr":"Koronadal Blaan","bpy":"Bishnupriya","bqc":"Boko (Benin)",
  "br":"Breton","bre":"Breton","brh":"Brahui","bru":"Eastern Bru",
  "brx":"Bodo (India)","bs":"Bosnian","bsn":"Barasana-Eduria","bss":"Akoose",
  "bts":"Batak Simalungun","btx":"Batak Karo","bud":"Ntcham","buk":"Bugawac",
  "bul":"Bulgarian","bum":"Bulu (Cameroon)","bur":"Burmese","bus":"Bokobaru",
  "bvr":"Burarra","bvz":"Bauzi","bxr":"Russia Buriat","byr":"Baruya",
  "byx":"Qaqet","bzh":"Mapos Buang","bzj":"Belize Kriol English","ca":"Catalan",
  "cab":"Garifuna","cac":"Chuj","cak":"Kaqchikel","caq":"Car Nicobarese",
  "car":"Galibi Carib","cas":"Tsimané","cat":"Catalan","cav":"Cavineña",
  "cax":"Chiquitano","cbc":"Carapana","cbk":"Chavacano","cbs":"Cashinahua",
  "cbu":"Candoshi-Shapra","cbv":"Cacua","cce":"Chopi","cco":"Comaltepec Chinantec",
  "ccp":"Chakma","ce":"Chechen","ceb":"Cebuano","ceg":"Chamacoco",
  "ces":"Czech","cfm":"Falam Chin","cgc":"Kagayanen","ch":"Chamorro",
  "cha":"Chamorro","chd":"Highland Oaxaca Chontal","che":"Chechen","chi":"Chinese",
  "chk":"Chuukese","chu":"Church Slavic","chv":"Chuvash","chw":"Chuwabu",
  "chz":"Ozumacín Chinantec","cjp":"Cabécar","ckb":"Central Kurdish","cko":"Anufo",
  "cle":"Lealao Chinantec","cmn":"Mandarin Chinese","cmo":"Central Mnong","cmr":"Mro-Khimi Chin",
  "cnh":"Hakha Chin","cni":"Asháninka","cnk":"Khumi Chin","cnt":"Tepetotutla Chinantec",
  "co":"Corsican","coe":"Koreguaje","cok":"Santa Teresa Cora","cop":"Coptic",
  "cor":"Cornish","cos":"Corsican","cpa":"Palantla Chinantec","cpy":"South Ucayali Ashéninka",
  "cr":"Cree","cre":"Cree","crh":"Crimean Tatar","crk":"Plains Cree",
  "crm":"Moose Cree","crn":"El Nayar Cora","crs":"Seselwa Creole French","crx":"Carrier",
  "cs":"Czech","csb":"Kashubian","cso":"Sochiapam Chinantec","csy":"Siyin Chin",
  "ctd":"Tedim Chin","ctu":"Chol","cu":"Old Church Slavonic","cuc":"Usila Chinantec",
  "cui":"Cuiba","cuk":"San Blas Kuna","cv":"Chuvash","cwt":"Kuwaataay",
  "cy":"Welsh","cya":"Nopala Chatino","cym":"Welsh","cze":"Czech",
  "czt":"Zotung Chin","da":"Danish","dad":"Marik","dag":"Dagbani",
  "dah":"Gwahatike","dan":"Danish","dar":"Dargwa","de":"German",
  "ded":"Dedua","des":"Desano","deu":"German","dgc":"Casiguran Dumagat Agta",
  "dgi":"Northern Dagara","dgr":"Tlicho","dgz":"Daga","dhv":"Dehu",
  "dig":"Digo","dik":"Southwestern Dinka","diq":"Dimli (individual language)","div":"Dhivehi",
  "dnj":"Dan","dob":"Dobu","doi":"Dogri (macrolanguage)","dop":"Lukpa",
  "dsb":"Lower Sorbian","dtp":"Kadazan Dusun","dts":"Toro So Dogon","dua":"Duala",
  "dut":"Dutch","dv":"Divehi","dwr":"Dawro","dww":"Dawawa",
  "dyi":"Djimini Senoufo","dyo":"Jola-Fonyi","dyu":"Dyula","dz":"Dzongkha",
  "dzo":"Dzongkha","ee":"Ewe","efi":"Efik","ekk":"Standard Estonian",
  "el":"Greek","ell":"Modern Greek (1453-)","eml":"Emiliano-Romagnolo","emp":"Northern Emberá",
  "en":"English","enb":"Markweeta","eng":"English","enm":"Middle English (1100-1500)",
  "eo":"Esperanto","epo":"Esperanto","es":"Spanish","esk":"Northwest Alaska Inupiatun",
  "est":"Estonian","esu":"Central Yupik","et":"Estonian","eu":"Basque",
  "eus":"Basque","ewe":"Ewe","ewo":"Ewondo","ext":"Extremaduran",
  "eza":"Ezaa","fa":"Persian","fai":"Faiwol","fal":"South Fali",
  "fao":"Faroese","fas":"Persian","fat":"Fanti","ff":"Fula",
  "ffm":"Maasina Fulfulde","fi":"Finnish","fij":"Fijian","fil":"Filipino",
  "fin":"Finnish","fit":"Tornedalen Finnish","fj":"Fijian","fkv":"Kven Finnish",
  "fo":"Faroese","fon":"Fon","fr":"French","fra":"French",
  "fre":"French","fro":"Old French (842-ca. 1400)","frp":"Arpitan","frr":"Northern Frisian",
  "fry":"Western Frisian","fuf":"Pular","fuh":"Western Niger Fulfulde","ful":"Fula",
  "fur":"Friulian","fuv":"Nigerian Fulfulde","fy":"Western Frisian","ga":"Irish",
  "gaa":"Ga","gag":"Gagauz","gai":"Borei","gaw":"Nobonob",
  "gaz":"West Central Oromo","gbi":"Galela","gbo":"Northern Grebo","gcf":"Guadeloupean Creole French",
  "gcr":"Guianese Creole French","gd":"Scottish Gaelic","gde":"Gude","gdr":"Wipi",
  "geo":"Georgian","ger":"German","gfk":"Patpatar","gil":"Gilbertese",
  "gkn":"Gokana","gl":"Galician","gla":"Scottish Gaelic","gle":"Irish",
  "glg":"Galician","glk":"Gilaki","glv":"Manx","gmh":"Middle High German (ca. 1050-1500)",
  "gmv":"Gamo","gn":"Guarani","gnd":"Zulgo-Gemzek","gng":"Ngangam",
  "gnn":"Gumatj","gnw":"Western Bolivian Guaraní","gof":"Gofa","gog":"Gogo",
  "goh":"Old High German (ca. 750-1050)","gom":"Goan Konkani","gor":"Gorontalo","gos":"Gronings",
  "grc":"Ancient Greek (to 1453)","gre":"Greek","grn":"Guarani","grt":"Garo",
  "gso":"Southwest Gbaya","gsw":"Swiss German","gu":"Gujarati","guc":"Wayuu",
  "gug":"Paraguayan Guaraní","gui":"Eastern Bolivian Guaraní","guj":"Gujarati","guk":"Gumuz",
  "gul":"Sea Island Creole English","gum":"Guambiano","gun":"Mbyá Guaraní","gur":"Farefare",
  "guw":"Gun","gux":"Gourmanchéma","gv":"Manx","gvl":"Gulay",
  "gym":"Ngäbere","ha":"Hausa","hac":"Gurani","hag":"Hanga",
  "hak":"Hakka Chinese","hat":"Haitian","hau":"Hausa","haw":"Hawaiian",
  "hay":"Haya","hbo":"Ancient Hebrew","he":"Hebrew","heb":"Hebrew",
  "heg":"Helong","heh":"Hehe","her":"Herero","hi":"Hindi",
  "hif":"Fiji Hindi","hig":"Kamwe","hil":"Hiligaynon","hin":"Hindi",
  "hla":"Halia","hmo":"Hiri Motu","hmr":"Hmar","hne":"Chhattisgarhi",
  "hnj":"Hmong Njua","hns":"Caribbean Hindustani","ho":"Hiri Motu","hr":"Croatian",
  "hrv":"Croatian","hrx":"Hunsrik","hsb":"Upper Sorbian","ht":"Haitian Creole",
  "hto":"Minica Huitoto","hu":"Hungarian","hui":"Huli","hun":"Hungarian",
  "hus":"Huastec","hwc":"Hawai'i Creole English","hy":"Armenian","hye":"Armenian",
  "hyw":"Western Armenian","hz":"Herero","ia":"Interlingua","iba":"Iban",
  "ibg":"Ibanag","ibo":"Igbo","ice":"Icelandic","id":"Indonesian",
  "ido":"Ido","ie":"Interlingue","ifb":"Batad Ifugao","ifk":"Tuwali Ifugao",
  "ify":"Keley-I Kallahan","ig":"Igbo","ii":"Nuosu","iii":"Nuosu",
  "ik":"Inupiaq","ike":"Eastern Canadian Inuktitut","ikt":"Inuinnaqtun","iku":"Inuktitut",
  "ile":"Interlingue","ilo":"Iloko","imo":"Imbongu","ina":"Interlingua (IALA)",
  "inb":"Inga","ind":"Indonesian","inh":"Ingush","io":"Ido",
  "ipi":"Ipili","ipk":"Inupiaq","irk":"Iraqw","is":"Icelandic",
  "isd":"Isnag","isl":"Icelandic","iso":"Isoko","it":"Italian",
  "ita":"Italian","itv":"Itawit","iu":"Inuktitut","ium":"Iu Mien",
  "ixl":"Ixil","izr":"Izere","ja":"Japanese","jac":"Popti'",
  "jae":"Yabem","jam":"Jamaican Creole English","jav":"Javanese","jbo":"Lojban",
  "jbu":"Jukun Takum","jiv":"Shuar","jpn":"Japanese","jra":"Jarai",
  "jv":"Javanese","jvn":"Caribbean Javanese","ka":"Georgian","kaa":"Kara-Kalpak",
  "kab":"Kabyle","kac":"Kachin","kal":"Kalaallisut","kam":"Kamba (Kenya)",
  "kan":"Kannada","kao":"Xaasongaxango","kas":"Kashmiri","kat":"Georgian",
  "kau":"Kanuri","kaz":"Kazakh","kbd":"Kabardian","kbp":"Kabiyè",
  "kbr":"Kafa","kca":"Khanty","kde":"Makonde","kdi":"Kumam",
  "kdr":"Karaim","kea":"Kabuverdianu","kek":"Kekchí","ken":"Kenyang",
  "keo":"Kakwa","kew":"West Kewa","kez":"Kukele","kg":"Kongo",
  "kgp":"Kaingang","kha":"Khasi","khk":"Halh Mongolian","khm":"Khmer",
  "khs":"Kasua","khz":"Keapara","ki":"Kikuyu","kij":"Kilivila",
  "kik":"Kikuyu","kin":"Kinyarwanda","kir":"Kirghiz","kiu":"Kirmanjki (individual language)",
  "kix":"Khiamniungan Naga","kj":"Kwanyama","kjh":"Khakas","kjs":"East Kewa",
  "kk":"Kazakh","kkc":"Odoodee","kki":"Kagulu","kkj":"Kako",
  "kl":"Kalaallisut","klv":"Maskelynes","km":"Khmer","kmb":"Kimbundu",
  "kmg":"Kâte","kmh":"Kalam","kmo":"Kwoma","kmr":"Northern Kurdish",
  "kmu":"Kanite","kn":"Kannada","knc":"Central Kanuri","knf":"Mankanya",
  "kng":"Koongo","knj":"Western Kanjobal","knk":"Kuranko","knv":"Tabo",
  "ko":"Korean","koi":"Komi-Permyak","kom":"Komi","kon":"Kongo",
  "koo":"Konzo","kor":"Korean","kos":"Kosraean","kpe":"Kpelle",
  "kpf":"Komba","kpg":"Kapingamarangi","kpr":"Korafe-Yegha","kpv":"Komi-Zyrian",
  "kpw":"Kobon","kpz":"Kupsabiny","kqn":"Kaonde","kqp":"Kimré",
  "kr":"Kanuri","krc":"Karachay-Balkar","kri":"Krio","krj":"Kinaray-A",
  "krl":"Karelian","ks":"Kashmiri","ksd":"Kuanua","ksh":"Kölsch",
  "ksr":"Borong","kss":"Southern Kisi","ksw":"S'gaw Karen","kto":"Kuot",
  "ku":"Kurdish","kua":"Kuanyama","kud":"'Auhelawa","kum":"Kumyk",
  "kup":"Kunimaipa","kur":"Kurdish","kus":"Kusaal","kv":"Komi",
  "kw":"Cornish","kwi":"Awa-Cuaiquer","kwj":"Kwanga","kwn":"Kwangali",
  "kwy":"San Salvador Kongo","kxc":"Konso","ky":"Kyrgyz","kyc":"Kyaka",
  "kyq":"Kenga","kyz":"Kayabí","kze":"Kosena","kzj":"Coastal Kadazan",
  "la":"Latin","lac":"Lacandon","lad":"Ladino","lam":"Lamba",
  "lao":"Lao","lat":"Latin","lav":"Latvian","lb":"Luxembourgish",
  "lbe":"Lak","lee":"Lyélé","lef":"Lelemi","leu":"Kara (Papua New Guinea)",
  "lex":"Luang","lez":"Lezghian","lfn":"Lingua Franca Nova","lg":"Ganda",
  "lgg":"Lugbara","lhu":"Lahu","li":"Limburgish","lia":"West-Central Limba",
  "lid":"Nyindrou","lij":"Ligurian","lim":"Limburgan","lin":"Lingala",
  "lit":"Lithuanian","ljp":"Lampung Api","lki":"Laki","lld":"Ladin",
  "lmo":"Lombard","lmp":"Limbum","ln":"Lingala","lo":"Lao",
  "loz":"Lozi","lrc":"Northern Luri","lsm":"Saamia","lt":"Lithuanian",
  "ltg":"Latgalian","ltz":"Luxembourgish","lu":"Luba-Katanga","lua":"Luba-Lulua",
  "lub":"Luba-Katanga","lue":"Luvale","lug":"Ganda","luo":"Luo (Kenya and Tanzania)",
  "lus":"Lushai","lv":"Latvian","lvs":"Standard Latvian","lzh":"Literary Chinese",
  "maa":"San Jerónimo Tecóatl Mazatec","mac":"Macedonian","mad":"Madurese","mag":"Magahi",
  "mah":"Marshallese","mai":"Maithili","mak":"Makasar","mal":"Malayalam",
  "mam":"Mam","mao":"Maori","maq":"Chiquihuitlán Mazatec","mar":"Marathi",
  "mas":"Masai","mau":"Huautla Mazatec","may":"Malay","maz":"Central Mazahua",
  "mbb":"Western Bukidnon Manobo","mbf":"Baba Malay","mbi":"Ilianen Manobo","mbt":"Matigsalug Manobo",
  "mco":"Coatlán Mixe","mcq":"Ese","mcu":"Cameroon Mambila","mdf":"Moksha",
  "mdy":"Male","med":"Melpa","mej":"Meyah","men":"Mende (Sierra Leone)",
  "meq":"Merey","mer":"Meru","meu":"Motu","mfe":"Morisyen",
  "mfi":"Wandala","mfq":"Moba","mfz":"Mabaan","mg":"Malagasy",
  "mgr":"Mambwe-Lungu","mh":"Marshallese","mhl":"Mauwake","mhr":"Eastern Mari",
  "mi":"Maori","mif":"Mofu-Gudur","mil":"Peñoles Mixtec","min":"Minangkabau",
  "miq":"Mískito","mjw":"Karbi","mk":"Macedonian","mkd":"Macedonian",
  "mkn":"Kupang Malay","ml":"Malayalam","mlg":"Malagasy","mlp":"Bargam",
  "mlt":"Maltese","mmn":"Mamanwa","mmo":"Mangga Buang","mmx":"Madak",
  "mn":"Mongolian","mni":"Manipuri","mnw":"Mon","mon":"Mongolian",
  "mop":"Mopán Maya","mos":"Mossi","mpp":"Migabac","mps":"Dadibi",
  "mpx":"Misima-Panaeati","mqb":"Mbuko","mr":"Marathi","mri":"Maori",
  "mrj":"Western Mari","ms":"Malay","msa":"Malay","msb":"Masbatenyo",
  "msy":"Aruamu","mt":"Maltese","mtp":"Wichí Lhamtés Nocten","muh":"Mündü",
  "mui":"Musi","mup":"Malvi","mux":"Bo-Ung","mva":"Manam",
  "mwl":"Mirandese","mwq":"Mün Chin","mwv":"Mentawai","mww":"Hmong Daw",
  "mxb":"Tezoatlán Mixtec","mxp":"Tlahuitoltepec Mixe","mxq":"Juquila Mixe","mxt":"Jamiltepec Mixtec",
  "mxv":"Metlatónoc Mixtec","my":"Burmese","mya":"Burmese","myv":"Erzya",
  "myw":"Muyuw","myy":"Macuna","mzn":"Mazanderani","mzw":"Deg",
  "na":"Nauruan","nah":"Nahuatl","nak":"Nakanai","nan":"Min Nan Chinese",
  "nap":"Neapolitan","naq":"Khoekhoe","nas":"Naasioi","nau":"Nauruan",
  "nav":"Navajo","nb":"Norwegian Bokmal","nba":"Nyemba","nbl":"South Ndebele",
  "nbu":"Rongmei Naga","nch":"Central Huasteca Nahuatl","ncj":"Northern Puebla Nahuatl","nct":"Chothe Naga",
  "ncx":"Central Puebla Nahuatl","nd":"Northern Ndebele","ndc":"Ndau","nde":"North Ndebele",
  "ndo":"Ndonga","nds":"Low German","ne":"Nepali","nep":"Nepali",
  "new":"Nepal Bhasa","nfr":"Nafaanra","ng":"Ndonga","ngl":"Lomwe",
  "ngu":"Guerrero Nahuatl","nhe":"Eastern Huasteca Nahuatl","nhi":"Zacatlán-Ahuacatlán-Tepetzintla Nahuatl","nho":"Takuu",
  "nhu":"Noone","nhw":"Western Huasteca Nahuatl","nhy":"Northern Oaxaca Nahuatl","nia":"Nias",
  "nij":"Ngaju","nim":"Nilamba","nin":"Ninzo","niu":"Niuean",
  "njo":"Ao Naga","nl":"Dutch","nld":"Dutch","nn":"Norwegian Nynorsk",
  "nnb":"Nande","nno":"Norwegian Nynorsk","no":"Norwegian","noa":"Woun Meu",
  "nob":"Norwegian Bokmål","nod":"Northern Thai","nog":"Nogai","non":"Old Norse",
  "nop":"Numanggang","nor":"Norwegian","nov":"Novial","npi":"Nepali (individual language)",
  "npy":"Napu","nqo":"N'Ko","nr":"Southern Ndebele","nrf":"Jèrriais",
  "nrm":"Narom","nso":"Pedi","ntr":"Delo","ntu":"Natügu",
  "nv":"Navajo","nwi":"Southwest Tanna","ny":"Chichewa","nya":"Chichewa",
  "nyn":"Nyankole","nyo":"Nyoro","nyu":"Nyungwe","nzi":"Nzima",
  "oc":"Occitan","oci":"Occitan (post 1500)","ogo":"Khana","oj":"Ojibwe",
  "ojb":"Northwestern Ojibwa","oji":"Ojibwe","olo":"Livvi","om":"Oromo",
  "opm":"Oksapmin","or":"Oriya","ori":"Oriya","orm":"Oromo",
  "orv":"Old Russian","ory":"Odia","os":"Ossetian","oss":"Iron Ossetic",
  "ota":"Ottoman Turkish (1500-1928)","ote":"Mezquital Otomi","otq":"Querétaro Otomi","otw":"Ottawa",
  "ozm":"Koonzime","pa":"Punjabi","pab":"Parecís","pad":"Paumarí",
  "pag":"Pangasinan","pah":"Tenharim","pam":"Pampanga","pan":"Panjabi",
  "pap":"Papiamento","pau":"Palauan","pbt":"Southern Pashto","pcd":"Picard",
  "pck":"Paite Chin","pcm":"Nigerian Pidgin","pdc":"Pennsylvania German","pdt":"Plautdietsch",
  "pem":"Phende","per":"Persian","pfl":"Pfaelzisch","pi":"Pali",
  "pir":"Piratapuyo","pis":"Pijin","pjt":"Pitjantjatjara","pl":"Polish",
  "pli":"Pali","plt":"Plateau Malagasy","pma":"Paama","pms":"Piemontese",
  "pnb":"Western Panjabi","pnt":"Pontic","poh":"Poqomchi'","pol":"Polish",
  "pon":"Pohnpeian","por":"Portuguese","ppk":"Uma","pri":"Paicî",
  "ps":"Pashto","pt":"Portuguese","ptu":"Bambam","pus":"Pashto",
  "pwg":"Gapapaiwa","pwn":"Paiwan","qu":"Quechua","qub":"Quechua",
  "quc":"K'iche'","que":"Quechua","quf":"Quechua","qug":"Quechua",
  "quh":"Quechua","qul":"Quechua","qup":"Quechua","qus":"Quechua",
  "quw":"Quechua","quy":"Quechua","quz":"Quechua","qve":"Quechua",
  "qvh":"Quechua","qvi":"Quechua","qvm":"Quechua","qvn":"Quechua",
  "qvs":"Quechua","qvw":"Quechua","qvz":"Quechua","qwh":"Quechua",
  "qxh":"Quechua","rad":"Rade","rar":"Rarotongan","raw":"Rawang",
  "rcf":"Réunion Creole French","rej":"Rejang","rm":"Romansh","rmc":"Carpathian Romani",
  "rme":"Angloromani","rmn":"Balkan Romani","rmo":"Sinte Romani","rmy":"Vlax Romani",
  "rn":"Kirundi","rnd":"Ruund","ro":"Romanian","roh":"Romansh",
  "ron":"Romanian","rop":"Kriol","rro":"Waima","rtm":"Rotuman",
  "ru":"Russian","rue":"Rusyn","rug":"Roviana","rum":"Romanian",
  "run":"Rundi","rup":"Macedo-Romanian","rus":"Russian","rw":"Kinyarwanda",
  "rwo":"Rawa","sa":"Sanskrit","sag":"Sango","sah":"Yakut",
  "san":"Sanskrit","sas":"Sasak","sat":"Santali","sbe":"Saliba",
  "sbl":"Botolan Sambal","sc":"Sardinian","scn":"Sicilian","sco":"Scots",
  "sd":"Sindhi","sdc":"Sassarese Sardinian","sdh":"Southern Kurdish","se":"Northern Sami",
  "seh":"Sena","sg":"Sango","sgb":"Mag-antsi Ayta","sgc":"Kipsigis",
  "sgs":"Samogitian","sgw":"Sebat Bet Gurage","shi":"Tachelhit","shn":"Shan",
  "si":"Sinhala","sid":"Sidamo","sig":"Paasaal","sim":"Mende (Papua New Guinea)",
  "sin":"Sinhala","sja":"Epena","sk":"Slovak","skg":"Sakalava Malagasy",
  "skr":"Saraiki","sl":"Slovene","slk":"Slovak","slo":"Slovak",
  "slv":"Slovenian","sm":"Samoan","sma":"Southern Sami","sme":"Northern Sami",
  "smj":"Lule Sami","smk":"Bolinao","sml":"Central Sama","smn":"Inari Sami",
  "smo":"Samoan","sms":"Skolt Sami","sn":"Shona","sna":"Shona",
  "snd":"Sindhi","snp":"Siane","sny":"Saniyo-Hiyewe","so":"Somali",
  "som":"Somali","sop":"Songe","soq":"Kanasi","sot":"Southern Sotho",
  "spa":"Spanish","spl":"Selepet","spp":"Supyire Senoufo","sps":"Saposa",
  "spy":"Sabaot","sq":"Albanian","sqi":"Albanian","sr":"Serbian",
  "srd":"Sardinian","srn":"Sranan Tongo","srp":"Serbian","ss":"Swati",
  "ssw":"Swati","st":"Southern Sotho","stq":"Saterfriesisch","su":"Sundanese",
  "sua":"Sulka","sue":"Suena","suk":"Sukuma","sun":"Sundanese",
  "sur":"Mwaghavul","sus":"Susu","sv":"Swedish","sw":"Swahili",
  "swa":"Swahili","swc":"Congo Swahili","swe":"Swedish","swg":"Swabian",
  "swh":"Swahili (individual language)","swp":"Suau","syc":"Classical Syriac","syl":"Sylheti",
  "szl":"Silesian","szy":"Sakizaya","ta":"Tamil","tab":"Tabassaran",
  "tac":"Lowland Tarahumara","tah":"Tahitian","taj":"Eastern Tamang","tam":"Tamil",
  "taq":"Tamasheq","tat":"Tatar","tay":"Atayal","tbc":"Takia",
  "tbg":"North Tairora","tby":"Tabaru","tbz":"Ditammari","tca":"Ticuna",
  "tcf":"Malinaltepec Me'phaa","tcs":"Torres Strait Creole","tcy":"Tulu","tcz":"Thado Chin",
  "te":"Telugu","ted":"Tepo Krumen","tee":"Huehuetla Tepehua","tel":"Telugu",
  "teo":"Teso","ter":"Tereno","tet":"Tetum","tfr":"Teribe",
  "tg":"Tajik","tgk":"Tajik","tgl":"Tagalog","th":"Thai",
  "tha":"Thai","thk":"Tharaka","thl":"Dangaura Tharu","ti":"Tigrinya",
  "tib":"Tibetan","tir":"Tigrinya","tiv":"Tiv","tiy":"Tiruray",
  "tk":"Turkmen","tl":"Tagalog","tlf":"Telefol","tlh":"Klingon",
  "tly":"Talysh","tn":"Tswana","tnn":"North Tanna","tnp":"Whitesands",
  "to":"Tonga","tog":"Tonga (Nyasa)","toh":"Gitonga","toi":"Tonga (Zambia)",
  "toj":"Tojolabal","tok":"Toki Pona","ton":"Tonga (Tonga Islands)","top":"Papantla Totonac",
  "tos":"Highland Totonac","tpi":"Tok Pisin","tpt":"Tlachichilco Tepehua","tpz":"Tinputz",
  "tr":"Turkish","trn":"Trinitario","trp":"Kok Borok","trv":"Sediq",
  "ts":"Tsonga","tsc":"Tswa","tsg":"Tausug","tsn":"Tswana",
  "tso":"Tsonga","tsz":"Purepecha","tt":"Tatar","tte":"Bwanabwana",
  "tuc":"Mutu","tuk":"Turkmen","tum":"Tumbuka","tuo":"Tucano",
  "tur":"Turkish","tvk":"Southeast Ambrym","tvl":"Tuvalu","tw":"Twi",
  "twi":"Twi","twu":"Termanu","txu":"Kayapó","ty":"Tahitian",
  "tyv":"Tuvinian","tzh":"Tzeltal","tzj":"Tz'utujil","tzm":"Central Atlas Tamazight",
  "tzo":"Tzotzil","ubr":"Ubir","ubu":"Umbu-Ungu","udm":"Udmurt",
  "udu":"Uduk","ug":"Uyghur","uig":"Uighur","uk":"Ukrainian",
  "ukr":"Ukrainian","umb":"Umbundu","ur":"Urdu","ura":"Urarina",
  "urd":"Urdu","urh":"Urhobo","urk":"Urak Lawoi'","usp":"Uspanteco",
  "uz":"Uzbek","uzb":"Uzbek","uzn":"Northern Uzbek","uzs":"Southern Uzbek",
  "vap":"Vaiphei","ve":"Venda","vec":"Venetian","ven":"Venda",
  "vep":"Veps","vi":"Vietnamese","vie":"Vietnamese","viv":"Iduna",
  "vls":"Vlaams","vmw":"Makhuwa","vmy":"Ayautla Mazatec","vo":"Volapuk",
  "vol":"Volapük","vro":"Võro","vun":"Vunjo","wa":"Walloon",
  "wal":"Wolaytta","war":"Waray (Philippines)","wel":"Welsh","wes":"Cameroon Pidgin",
  "wim":"Wik-Mungkan","wln":"Walloon","wo":"Wolof","wol":"Wolof",
  "wos":"Hanga Hundi","wrk":"Garrwa","wuu":"Wu Chinese","wuv":"Wuvulu-Aua",
  "xal":"Kalmyk","xav":"Xavánte","xbi":"Kombio","xh":"Xhosa",
  "xho":"Xhosa","xla":"Kamula","xmf":"Mingrelian","xon":"Konkomba",
  "xrb":"Eastern Karaboro","xsi":"Sio","xsm":"Kasem","xtn":"Northern Tlaxiaco Mixtec",
  "yal":"Yalunka","yap":"Yapese","ybb":"Yemba","yby":"Yaweyuha",
  "ydd":"Eastern Yiddish","yi":"Yiddish","yid":"Yiddish","yle":"Yele",
  "yli":"Angguruk Yali","yml":"Iamalele","yo":"Yoruba","yom":"Yombe",
  "yon":"Yongkom","yor":"Yoruba","yre":"Yaouré","yrk":"Nenets",
  "yss":"Yessan-Mayo","yua":"Yucateco","yue":"Yue Chinese","yuj":"Karkar-Yuri",
  "yuw":"Yau (Morobe Province)","za":"Zhuang","zac":"Ocotlán Zapotec","zai":"Isthmus Zapotec",
  "zea":"Zeeuws","zh":"Chinese","zha":"Zhuang","zho":"Chinese",
  "zia":"Zia","ziw":"Zigula","zne":"Zande (individual language)","zom":"Zou",
  "zpa":"Lachiguiri Zapotec","zpl":"Lachixío Zapotec","zpu":"Yalálag Zapotec","zpv":"Chichicapan Zapotec",
  "zpz":"Texmelucan Zapotec","zsm":"Standard Malay","ztq":"Quioquitani-Quierí Zapotec","zty":"Yatee Zapotec",
  "zu":"Zulu","zul":"Zulu","zyb":"Yongbei Zhuang","zyp":"Zyphe Chin"
};

function normLang(code) {
  // Strip script suffix: fra_Latn → fra, zh_Hans → zh
  return code.split("_")[0];
}

function _resolveSingle(code) {
  const n = normLang(code);
  return LANG_NAMES[code] || LANG_NAMES[n] || code;
}

function langLabel(code) {
  // Some ES values are stored as comma-separated lists e.g. "kpv,koi"
  if (code.includes(",")) {
    const names = [...new Set(code.split(",").map(c => _resolveSingle(c.trim())))];
    return names.join(" / ");
  }
  return _resolveSingle(code);
}

function langShort(code) {
  if (code.includes(",")) {
    const names = [...new Set(code.split(",").map(c => _resolveSingle(c.trim())))];
    return names.join("/");
  }
  return _resolveSingle(code);
}

/* ─── Dataset metadata ─────────────────────────────────────────── */
const DS = {
  "fineweb-1":           { group: "web",           label: "FineWeb-1" },
  "fineweb-edu":         { group: "web",           label: "FineWeb-edu" },
  "dclm":                { group: "web",           label: "DCLM" },
  "fineweb-2":           { group: "multi",         label: "FineWeb-2" },
  "finemath":            { group: "math",          label: "FineMath" },
  "infiwebmath":         { group: "math",          label: "InfiWebMath" },
  "megamath-web":        { group: "math",          label: "MegaMath-Web" },
  "starcoder":           { group: "code",          label: "StarCoder" },
  "starcoder-extras":    { group: "code",          label: "StarCoder-extras" },
  "stackv2-edu":         { group: "code",          label: "StackV2-edu" },
  "wikipedia":           { group: "curated-multi", label: "Wikipedia" },
  "europarl":            { group: "curated-multi", label: "EuroParl" },
  "paradocs":            { group: "curated-multi", label: "ParaDocs" },
  "flan":                { group: "curated-en",    label: "FLAN" },
  "euroblocks":          { group: "curated-en",    label: "EuroBlocks" },
  "institutional-books": { group: "curated-en",    label: "Institutional Books" },
  "gutenberg":           { group: "curated-en",    label: "Gutenberg" },
  "canaries":            { group: "curated-en",    label: "Canaries" },
  "sft-mixture":         { group: "post",          label: "SFT-Mixture" },
  "alignment":           { group: "post",          label: "Alignment" },
};

const GROUPS = [
  { id: "web",           label: "English Web",          color: "#2563eb", datasets: ["fineweb-1","fineweb-edu","dclm"] },
  { id: "multi",         label: "Multilingual Web",     color: "#0891b2", datasets: ["fineweb-2"] },
  { id: "math",          label: "Math",                 color: "#7c3aed", datasets: ["finemath","infiwebmath","megamath-web"] },
  { id: "code",          label: "Code",                 color: "#ea580c", datasets: ["starcoder","starcoder-extras","stackv2-edu"] },
  { id: "curated-multi", label: "Multilingual Curated", color: "#059669", datasets: ["wikipedia","europarl","paradocs"] },
  { id: "curated-en",    label: "English Curated",      color: "#b45309", datasets: ["flan","euroblocks","institutional-books","gutenberg","canaries"] },
  { id: "post",          label: "Posttraining",         color: "#be185d", datasets: ["sft-mixture","alignment"] },
];

/* ─── State ─────────────────────────────────────────────────────── */
const S = {
  query:       "",
  mode:        "all",    // "all" | "any" | "phrase" (server: /api/search?mode=)
  slop:        0,
  must:        [],       // phrases, one per textarea line
  should:      [],
  mustNot:     [],
  exactTotal:  false,
  page:        0,
  selDS:       new Set(),
  selLangs:    new Set(),
  dateFrom:    "",
  dateTo:      "",
  inclNoLang:  false,
  inclNoDate:  false,
  results:     null,
  aggs:        null,
  expanded:    new Set(),
  activeTab:   {},
  langQ:       "",
  showAllL:    false,
  loading:     false,
  collapsedDS: new Set(["web","multi","math","code","curated-multi","curated-en","post"]),
  collapsedLangs: true,
  openPanel:   null,   // "about" | "people" | null
  panelLoaded: {},     // panel id → true once content injected
};

/* ─── DOM refs ──────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const si = $("search-input");
const sb = $("search-btn");
const cb = $("clear-btn");

/* ─── Bootstrap ─────────────────────────────────────────────────── */
async function init() {
  bindGlobal();
  await Promise.all([loadHealth(), loadAggs()]);
  renderSidebar();
}

async function loadHealth() {
  try {
    const r = await fetch("/api/health");
    const d = await r.json();
    if (d.status === "ok") {
      setStatus("ok", `Connected · ${fmt(d.doc_count)} documents indexed`);
    } else {
      setStatus("warn", `Elasticsearch status: ${d.es_status}`);
    }
  } catch {
    setStatus("error", "Cannot reach Elasticsearch — check ES_HOST / port");
  }
}

async function loadAggs() {
  try {
    const r  = await fetch("/api/aggregations");
    S.aggs   = await r.json();
    if (S.aggs.partial) {
      const cur = $("status-text").textContent;
      $("status-text").textContent = cur + " · indexing in progress, sidebar counts are partial";
    }
  } catch (e) {
    console.warn("Aggregations unavailable:", e);
    $("status-text").textContent += " · filter counts unavailable";
  }
}

function setStatus(cls, msg) {
  $("status-bar").className = "status-bar " + cls;
  $("status-text").textContent = msg;
}

/* ─── Global events ─────────────────────────────────────────────── */
function bindGlobal() {
  si.addEventListener("keydown", e => { if (e.key === "Enter") doSearch(true); });
  si.addEventListener("input",   () => { cb.style.display = si.value ? "inline" : "none"; });
  sb.addEventListener("click",   () => doSearch(true));
  cb.addEventListener("click",   () => { si.value = ""; cb.style.display = "none"; S.query = ""; doSearch(true); });
  $("lang-search").addEventListener("input", e => { S.langQ = e.target.value.toLowerCase(); renderLangs(); });
  $("date-from").addEventListener("change", e => { S.dateFrom = e.target.value; doSearch(true); });
  $("date-to"  ).addEventListener("change", e => { S.dateTo   = e.target.value; doSearch(true); });
  $("reset-btn").addEventListener("click",  resetFilters);
  $("incl-no-lang").addEventListener("change", e => { S.inclNoLang = e.target.checked; doSearch(true); });
  $("incl-no-date").addEventListener("change", e => { S.inclNoDate = e.target.checked; doSearch(true); });

  // Search mode and phrase conditions
  document.querySelectorAll('input[name="match-mode"]').forEach(r => {
    r.addEventListener("change", e => { S.mode = e.target.value; renderMode(); if (hasQuery()) doSearch(true); });
  });
  $("slop-input").addEventListener("change", e => {
    S.slop = Math.max(0, Math.min(50, parseInt(e.target.value, 10) || 0));
    e.target.value = S.slop;
    if (hasQuery()) doSearch(true);
  });
  $("adv-apply").addEventListener("click", () => { readPhrases(); doSearch(true); });
  ["must-input", "should-input", "mustnot-input"].forEach(id => {
    $(id).addEventListener("keydown", e => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { readPhrases(); doSearch(true); }
    });
  });
  $("exact-total").addEventListener("change", e => { S.exactTotal = e.target.checked; if (hasQuery()) doSearch(true); });

  // Panel nav buttons
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => togglePanel(btn.dataset.panel));
  });

  // Home button — close any open panel
  $("home-btn").addEventListener("click", () => {
    if (S.openPanel) togglePanel(S.openPanel);
  });

  // Result card delegation
  $("results-list").addEventListener("click", handleCardClick);
}

function handleCardClick(e) {
  const expandBtn = e.target.closest(".expand-btn");
  if (expandBtn) { toggleExpand(expandBtn.dataset.id); return; }
  const tabBtn = e.target.closest(".tab-btn");
  if (tabBtn) { switchTab(tabBtn.dataset.doc, tabBtn.dataset.tab); return; }
  const simBtn = e.target.closest(".load-similar-btn");
  if (simBtn) { loadSimilar(simBtn.dataset.id); return; }
  const expBtn = e.target.closest(".export-btn");
  if (expBtn) {
    const hit = S.results?.hits.find(h => h.id === expBtn.dataset.id);
    if (hit) exportDoc(hit);
  }
}

/* ─── Panel toggle ───────────────────────────────────────────────── */
function togglePanel(name) {
  const wasOpen = S.openPanel === name;

  // Close any open panel
  if (S.openPanel) {
    const prev = $(`panel-${S.openPanel}`);
    prev?.classList.remove("open");
    prev?.setAttribute("aria-hidden", "true");
    document.querySelector(`.nav-btn[data-panel="${S.openPanel}"]`)?.classList.remove("active");
    $("main-layout").style.display = "";
  }

  if (wasOpen) {
    S.openPanel = null;
    $("main-layout").style.display = "";
    return;
  }

  S.openPanel = name;
  const panel = $(`panel-${name}`);
  if (!S.panelLoaded[name]) {
    $(`${name}-content`).innerHTML = name === "about" ? buildAbout() : buildPeople();
    S.panelLoaded[name] = true;
  }
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  document.querySelector(`.nav-btn[data-panel="${name}"]`)?.classList.add("active");
  panel.scrollTop = 0;
  $("main-layout").style.display = "none";
}

/* ─── About content ─────────────────────────────────────────────── */
function buildAbout() {
  return `<article class="panel-article">
<h1>About Apertus Data Search</h1>
<p class="article-lead">
  Apertus Data Search is a provenance explorer for the Swiss-AI pretraining and posttraining corpus.
  It provides full-text search over every training document and traces the exact origin of any content,
  supporting transparency and accountability in large language model development.
</p>

<h2>How Search Works</h2>
<p>
  Queries run as BM25 full-text searches against an Elasticsearch 7.17 index.
  The <code>text</code> field uses a custom <code>web_content_analyzer</code> pipeline:
  HTML tag stripping, standard tokenization, lowercasing, and ASCII-folding.
  This means accented characters match their ASCII equivalents
  (searching <code>resume</code> also matches <code>résumé</code>).
</p>
<p>
  Multi-word queries use AND semantics by default: all terms must appear in the document.
  Results are ranked by TF-IDF relevance. The index stores term positions,
  so phrase-level proximity influences ranking.
</p>
<p>
  <strong>Find Similar</strong> runs Elasticsearch's <code>more_like_this</code> query.
  It extracts statistically distinctive terms from a selected document and queries for
  documents that share them. This is lexical term-frequency similarity, not semantic or
  embedding-based similarity. There is no vector index.
</p>

<h2>Deduplication</h2>
<p>
  The index contains one document per unique text content.
  Deduplication uses the SHA-256 hash of the raw text as the document ID.
  If the same text appears in multiple datasets or crawls, it is stored once
  with a <code>sources[]</code> array recording every occurrence.
  The <code>source_count</code> field records the total number of occurrences before deduplication.
</p>
<p>
  English web datasets (FineWeb-1, FineWeb-edu, DCLM) were deduplicated jointly using
  Apache Spark before indexing, because they overlap significantly.
  All other datasets were indexed with <code>_id = SHA-256(text)</code>, so any
  cross-dataset duplicate is silently dropped on write (first write wins).
</p>

<h2>Index Schema</h2>
<table>
  <tr><th>Field</th><th>Type</th><th>Description</th></tr>
  <tr><td><code>text</code></td><td>full-text</td><td>Document content, indexed with <code>web_content_analyzer</code></td></tr>
  <tr><td><code>datasets</code></td><td>keyword[]</td><td>Source dataset names, filterable</td></tr>
  <tr><td><code>language</code></td><td>keyword[]</td><td>ISO 639 language codes, filterable. Empty for code and most posttraining data.</td></tr>
  <tr><td><code>date</code></td><td>date[]</td><td>Web crawl or publication dates. Empty for most curated datasets.</td></tr>
  <tr><td><code>source_count</code></td><td>integer</td><td>Number of times this exact text appeared across all sources before dedup</td></tr>
  <tr><td><code>sources[]</code></td><td>object</td><td>Full provenance array: URL, date, language score, folder path, repo name, etc. Stored but not indexed.</td></tr>
</table>
<div class="article-note">
  Language codes: English web datasets (FineWeb-1, FineWeb-edu, DCLM) use ISO 639-1 two-letter codes
  (e.g. <code>en</code>), while FineWeb-2 and Wikipedia use ISO 639-3 three-letter codes
  (e.g. <code>eng</code>). Both appear in the language filter.
</div>

<h2>Datasets</h2>
<table>
  <tr><th>Dataset</th><th>Group</th><th>Description</th><th>Language</th><th>Date</th></tr>
  <tr><td>FineWeb-1</td><td>English Web</td><td>Large-scale English web text from Common Crawl, quality-filtered</td><td>ISO 639-1</td><td>Crawl date</td></tr>
  <tr><td>FineWeb-edu</td><td>English Web</td><td>Educational-quality subset of Common Crawl web text (score &ge; 2)</td><td>ISO 639-1</td><td>Crawl date</td></tr>
  <tr><td>DCLM</td><td>English Web</td><td>DataComp for Language Models, English web text with quality filtering</td><td>ISO 639-1</td><td>Crawl date</td></tr>
  <tr><td>FineWeb-2</td><td>Multilingual Web</td><td>Multilingual Common Crawl web text, quality-filtered per language</td><td>ISO 639-3</td><td>Crawl date</td></tr>
  <tr><td>FineMath</td><td>Math</td><td>Mathematical content from the web</td><td>ISO 639-3</td><td>Crawl date</td></tr>
  <tr><td>InfiWebMath</td><td>Math</td><td>Web-crawled mathematical content</td><td>ISO 639-3</td><td>Crawl date</td></tr>
  <tr><td>MegaMath-Web</td><td>Math</td><td>Large-scale mathematical web data</td><td>ISO 639-3</td><td>Crawl date</td></tr>
  <tr><td>StarCoder</td><td>Code</td><td>Permissively licensed source code from GitHub</td><td>None</td><td>None</td></tr>
  <tr><td>StarCoder-extras</td><td>Code</td><td>Additional code data from GitHub</td><td>None</td><td>None</td></tr>
  <tr><td>StackV2-edu</td><td>Code</td><td>Educational-quality code from GitHub</td><td>None</td><td>None</td></tr>
  <tr><td>Wikipedia</td><td>Multilingual Curated</td><td>Wikipedia dumps across many languages</td><td>ISO 639-3</td><td>Dump date</td></tr>
  <tr><td>EuroParl</td><td>Multilingual Curated</td><td>European Parliament proceedings as parallel translation pairs</td><td>Language pair</td><td>None</td></tr>
  <tr><td>ParaDocs</td><td>Multilingual Curated</td><td>Parallel documents as translation pairs</td><td>Language pair</td><td>None</td></tr>
  <tr><td>FLAN</td><td>English Curated</td><td>Flan collection of instruction-following templates</td><td>None (English)</td><td>None</td></tr>
  <tr><td>EuroBlocks</td><td>English Curated</td><td>Synthetic SFT data in European languages</td><td>None</td><td>None</td></tr>
  <tr><td>Institutional Books</td><td>English Curated</td><td>Scanned books from institutions, OCR-quality filtered</td><td>ISO 639-3</td><td>Publication date</td></tr>
  <tr><td>Gutenberg</td><td>English Curated</td><td>Project Gutenberg public domain books</td><td>ISO 639-3</td><td>None</td></tr>
  <tr><td>Canaries</td><td>English Curated</td><td>Privacy and security canary documents</td><td>None</td><td>None</td></tr>
  <tr><td>SFT-Mixture</td><td>Posttraining</td><td>Supervised fine-tuning conversation mix</td><td>None</td><td>None</td></tr>
  <tr><td>Alignment</td><td>Posttraining</td><td>RLHF and DPO alignment data</td><td>None</td><td>None</td></tr>
</table>

<h2>Caveats and Limitations</h2>
<ul>
  <li>Search is capped at the first 10,000 results due to Elasticsearch pagination constraints. For exhaustive enumeration, query the ES API directly using <code>curl</code> or a client.</li>
  <li>The index may be partially populated while data is still being ingested.</li>
  <li>Language and date metadata are absent for many datasets. Use the "include documents without" toggles in the filter panel to control whether untagged documents appear when filtering.</li>
  <li>EuroParl and ParaDocs documents contain text from both sides of a translation pair (e.g. <code>lt: ... \n sk: ...</code>). Their language is stored as a pair in the sources provenance but is not in the top-level language filter.</li>
  <li>Web-crawled documents may retain HTML entities in the stored text. The search index strips these for matching, but they may appear in the displayed text.</li>
</ul>
</article>`;
}

/* ─── People content ─────────────────────────────────────────────── */
function buildPeople() {
  const people = [
    { name: "Alexander Sternfeld",     role: "Lead Engineer",    img: "alexander.jfif" },
    { name: "Anastasiia Kucherenko",   role: "Senior Engineer",  img: "anastasiia.jfif" },
    { name: "Inés Altemir Mariñas",    role: "Engineer",         img: "ines.jfif" },
    { name: "Arthur Wuhrmann",         role: "Engineer",         img: null },
    { name: "Andrei Kucharavy",        role: "Project Lead",     img: "andrei.jfif" },
  ];

  const cards = people.map(p => {
    const initials = p.name.split(" ").map(n => n[0]).join("").slice(0, 2);
    const avatar = p.img
      ? `<img src="/images/${p.img}" alt="${esc(p.name)}">`
      : `<div class="avatar-initials">${initials}</div>`;
    return `<div class="person-card">
      <div class="person-avatar">${avatar}</div>
      <div class="person-name">${esc(p.name)}</div>
      <div class="person-role">${esc(p.role)}</div>
    </div>`;
  }).join("");

  return `<div>
<h1 style="font-size:26px;font-weight:700;letter-spacing:-.02em;margin-bottom:14px;color:var(--text)">People</h1>
<p class="people-intro">
  Apertus Data Search is part of the <strong>Apertus Safety team</strong>'s effort to provide
  transparency about the data used to train Apertus. Knowing what text a model was trained on
  is a prerequisite for understanding its capabilities, biases, and potential failure modes.
  This platform makes the full training corpus searchable and traceable for researchers inside
  and outside the project.
</p>
<div class="people-grid">${cards}</div>
</div>`;
}

/* ─── Search mode ─────────────────────────────────────────────────── */
const MODE_HELP = {
  all:    "Every word must occur, in any order.",
  any:    "At least one of the words must occur.",
  phrase: "The words must occur together, in this order. Case, accents and punctuation are ignored.",
};

function renderMode() {
  $("mode-help").textContent = MODE_HELP[S.mode];
  $("slop-row").hidden = S.mode !== "phrase";
  const n = S.must.length + S.should.length + S.mustNot.length;
  const mb = $("badge-mode");
  const label = [S.mode !== "all" ? S.mode : "", n ? `${n} phrase${n > 1 ? "s" : ""}` : ""].filter(Boolean).join(" · ");
  mb.hidden = !label; mb.textContent = label;
}

function linesOf(id) {
  return $(id).value.split("\n").map(s => s.trim()).filter(Boolean);
}

function readPhrases() {
  S.must = linesOf("must-input"); S.should = linesOf("should-input"); S.mustNot = linesOf("mustnot-input");
  if (S.must.length || S.should.length || S.mustNot.length) $("adv-box").open = true;
  renderMode();
}

function hasQuery() {
  return Boolean(si.value.trim() || S.must.length || S.should.length || S.mustNot.length);
}

/* ─── Search ──────────────────────────────────────────────────────── */
function doSearch(resetPage = false) {
  if (resetPage) S.page = 0;
  S.query = si.value;
  readPhrases();
  runSearch();
}

async function runSearch() {
  S.loading = true;
  showLoading();

  const p = new URLSearchParams();
  if (S.query)       p.set("q", S.query);
  if (S.mode !== "all") p.set("mode", S.mode);
  if (S.slop)        p.set("slop", S.slop);
  S.must.forEach   (x => p.append("must",     x));
  S.should.forEach (x => p.append("should",   x));
  S.mustNot.forEach(x => p.append("must_not", x));
  if (S.exactTotal)  p.set("exact_total", "true");
  S.selDS.forEach   (d => p.append("datasets",  d));
  S.selLangs.forEach(l => p.append("languages", l));
  if (S.dateFrom)    p.set("date_from", S.dateFrom);
  if (S.dateTo)      p.set("date_to",   S.dateTo);
  if (S.inclNoLang)  p.set("include_no_lang", "true");
  if (S.inclNoDate)  p.set("include_no_date", "true");
  p.set("page", S.page);
  p.set("size", 10);

  try {
    const r  = await fetch(`/api/search?${p}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    S.results = await r.json();
  } catch (err) {
    S.results = { total: 0, hits: [], _error: err.message };
  }

  S.loading = false;
  renderResults();
  renderHeader();
  renderPagination();
  updateBadges();
}

function showLoading() {
  $("results-list").innerHTML =
    `<div class="loading-state"><div class="spinner"></div><p>Searching…</p></div>`;
  $("results-header").innerHTML = "";
  $("pagination").innerHTML     = "";
}

/* ─── Render results ─────────────────────────────────────────────── */
function renderHeader() {
  if (!S.results) return;
  const { total, total_relation, hits, _error } = S.results;
  if (_error) { $("results-header").textContent = `Error: ${_error}`; return; }
  if (total === 0) { $("results-header").textContent = "No results found."; return; }
  const from = S.page * 10 + 1, to = S.page * 10 + hits.length;
  // "gte": Elasticsearch stopped counting at 10,000. "Count all matches exactly" gives the real number.
  const totalTxt = total_relation === "gte" ? `${fmt(total)}+` : fmt(total);
  $("results-header").innerHTML =
    `Showing <strong>${fmt(from)}–${fmt(to)}</strong> of <strong>${totalTxt}</strong> results`;
}

function renderResults() {
  if (!S.results) return;
  const { hits, _error } = S.results;
  const el = $("results-list");

  if (_error) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠</div><p>${esc(_error)}</p></div>`;
    return;
  }
  if (!hits.length) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">🔍</div>
      <p>No results found</p><p class="empty-sub">Try different terms or fewer filters</p></div>`;
    return;
  }

  el.innerHTML = hits.map(cardHtml).join("");
}

function cardHtml(hit) {
  const exp = S.expanded.has(hit.id);
  const tab = S.activeTab[hit.id] || "text";

  const badges = [
    ...hit.datasets.map(dsBadge),
    ...hit.language.slice(0, 4).map(l => `<span class="badge b-lang" title="${esc(l)}">${esc(langShort(l))}</span>`),
  ].join("");

  const meta = [];
  const firstUrl = hit.sources?.find(s => s.url)?.url;
  if (firstUrl) meta.push(`<a href="${esc(firstUrl)}" target="_blank" rel="noopener" title="${esc(firstUrl)}">🔗 ${esc(trimUrl(firstUrl))}</a>`);
  if (hit.date?.length)     meta.push(`<span>📅 ${esc(hit.date.slice(0,2).join(", "))}</span>`);
  if (hit.source_count > 1) meta.push(`<span>🔁 ${hit.source_count} sources</span>`);

  const srcCount = hit.sources?.length || 0;

  return `
<div class="result-card" id="card-${hit.id}">
  <div class="card-top">
    <div class="card-badges">${badges}</div>
    <div class="card-actions">
      <button class="icon-btn expand-btn${exp ? " active" : ""}" data-id="${hit.id}" title="Expand / collapse">
        ${exp ? "▲" : "▼"}
      </button>
      <button class="icon-btn export-btn" data-id="${hit.id}" title="Export as JSON">⬇</button>
    </div>
  </div>
  <div class="card-snippet">${hit.snippet}</div>
  ${meta.length ? `<div class="card-meta">${meta.join("")}</div>` : ""}
  <div class="doc-id">${esc(hit.id)}</div>
  <div class="card-expanded${exp ? " open" : ""}" id="exp-${hit.id}">
    <div class="tab-bar">
      <button class="tab-btn${tab==="text"    ?" active":""}" data-doc="${hit.id}" data-tab="text">Full Text</button>
      <button class="tab-btn${tab==="sources" ?" active":""}" data-doc="${hit.id}" data-tab="sources">Sources (${srcCount})</button>
      <button class="tab-btn${tab==="similar" ?" active":""}" data-doc="${hit.id}" data-tab="similar">Similar</button>
    </div>
    <div class="tab-panel${tab==="text"    ?" active":""}" id="tp-text-${hit.id}">${renderText(hit)}</div>
    <div class="tab-panel${tab==="sources" ?" active":""}" id="tp-sources-${hit.id}">${renderSources(hit)}</div>
    <div class="tab-panel${tab==="similar" ?" active":""}" id="tp-similar-${hit.id}">
      <button class="load-similar-btn" data-id="${hit.id}">≈ Find similar documents</button>
    </div>
  </div>
</div>`;
}

function renderText(hit) {
  const isPost = hit.datasets.some(d => d === "sft-mixture" || d === "alignment");
  if (isPost && hit.text) return parseChatText(hit.text);
  return `<div class="full-text">${esc(hit.text || "(no text)")}</div>`;
}

function parseChatText(text) {
  const turns = text.split(/\n\n(?=(?:System|User|Assistant):\s)/);
  if (turns.length < 2) return `<div class="full-text">${esc(text)}</div>`;
  return turns.map(t => {
    const m = t.match(/^(System|User|Assistant):\s([\s\S]*)/);
    if (!m) return `<div class="full-text">${esc(t)}</div>`;
    return `<div class="chat-turn ${m[1].toLowerCase()}">
      <div class="chat-role">${m[1]}</div>
      <div class="chat-content">${esc(m[2])}</div>
    </div>`;
  }).join("");
}

function renderSources(hit) {
  const sources = hit.sources || [];
  if (!sources.length) return `<p style="color:var(--text-muted);font-size:13.5px">No source metadata.</p>`;
  const SKIP = new Set(["text"]);
  return `<div class="sources-list">${sources.map((s, i) => {
    const fields = Object.entries(s).filter(([k, v]) => !SKIP.has(k) && v != null && v !== "");
    const nonDs  = fields.filter(([k]) => k !== "dataset");
    return `<div class="source-card">
      <div class="source-header">${dsBadge(s.dataset)}<span>Source ${i+1}</span></div>
      <div class="source-fields">${nonDs.map(([k, v]) => {
        const display = k === "url"
          ? `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(trimUrl(v))}</a>`
          : esc(String(v));
        return `<div class="src-field"><span class="src-key">${k}</span><span class="src-val">${display}</span></div>`;
      }).join("")}</div>
    </div>`;
  }).join("")}</div>`;
}

/* ─── Expand / collapse ─────────────────────────────────────────── */
function toggleExpand(id) {
  const panel = document.getElementById(`exp-${id}`);
  const btn   = document.querySelector(`.expand-btn[data-id="${id}"]`);
  if (S.expanded.has(id)) {
    S.expanded.delete(id);
    panel?.classList.remove("open");
    if (btn) { btn.textContent = "▼"; btn.classList.remove("active"); }
  } else {
    S.expanded.add(id);
    panel?.classList.add("open");
    if (btn) { btn.textContent = "▲"; btn.classList.add("active"); }
  }
}

/* ─── Tab switching ─────────────────────────────────────────────── */
function switchTab(docId, tab) {
  S.activeTab[docId] = tab;
  const panel = document.getElementById(`exp-${docId}`);
  if (!panel) return;
  panel.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  panel.querySelectorAll(".tab-panel").forEach(p => {
    const panelTab = p.id.replace(`tp-`, "").replace(`-${docId}`, "");
    p.classList.toggle("active", panelTab === tab);
  });
}

/* ─── Similar documents ─────────────────────────────────────────── */
async function loadSimilar(docId) {
  const container = document.getElementById(`tp-similar-${docId}`);
  if (!container) return;
  container.innerHTML = `<div class="loading-state" style="padding:30px"><div class="spinner"></div></div>`;
  S.expanded.add(docId);
  document.getElementById(`exp-${docId}`)?.classList.add("open");
  const btn = document.querySelector(`.expand-btn[data-id="${docId}"]`);
  if (btn) { btn.textContent = "▲"; btn.classList.add("active"); }
  switchTab(docId, "similar");

  try {
    const r    = await fetch(`/api/similar/${docId}`);
    const data = await r.json();
    if (!data.hits?.length) {
      container.innerHTML = `<p style="color:var(--text-muted);font-size:13.5px">No similar documents found.</p>`;
      return;
    }
    container.innerHTML = `<div class="similar-grid">${data.hits.map(h => `
      <div class="mini-card">
        <div class="mini-card-badges">
          ${h.datasets.map(dsBadge).join("")}
          ${h.language.slice(0,2).map(l=>`<span class="badge b-lang" title="${esc(l)}">${esc(langShort(l))}</span>`).join("")}
        </div>
        <div class="mini-card-snippet">${h.snippet || esc((h.text||"").slice(0,260))}</div>
        <div class="doc-id" style="padding:6px 0 0">${esc(h.id)}</div>
      </div>`).join("")}</div>`;
  } catch (err) {
    container.innerHTML = `<p style="color:#ef4444;font-size:13.5px">Error: ${esc(err.message)}</p>`;
  }
}

/* ─── Export ─────────────────────────────────────────────────────── */
function exportDoc(hit) {
  const blob = new Blob([JSON.stringify(hit, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement("a"), {
    href: url, download: `doc-${hit.id.slice(0, 12)}.json`
  });
  a.click();
  URL.revokeObjectURL(url);
}

/* ─── Sidebar rendering ─────────────────────────────────────────── */
function renderSidebar() { renderDatasets(); renderLangs(); }

function renderDatasets() {
  const counts = {};
  (S.aggs?.datasets || []).forEach(d => { counts[d.key] = d.count; });

  $("dataset-filters").innerHTML = GROUPS.map(g => {
    const collapsed = S.collapsedDS.has(g.id);
    const selCount  = g.datasets.filter(d => S.selDS.has(d)).length;
    const items = g.datasets.map(d => {
      const meta = DS[d] || { label: d };
      const cnt  = counts[d];
      return `<div class="filter-item" onclick="toggleDS('${d}')">
        <input type="checkbox" id="ck-${d}" ${S.selDS.has(d)?"checked":""} onclick="event.stopPropagation();toggleDS('${d}')">
        <label for="ck-${d}">${meta.label}</label>
        ${cnt != null ? `<span class="filter-count">${fmt(cnt)}</span>` : ""}
      </div>`;
    }).join("");
    return `<div class="dataset-group">
      <div class="group-header" style="color:${g.color}" onclick="toggleDSGroup('${g.id}')">
        <span class="toggle-arrow">${collapsed ? "▸" : "▾"}</span>
        <span class="group-label-text">${g.label}</span>
        ${selCount ? `<span class="group-sel-count">${selCount}</span>` : ""}
      </div>
      ${collapsed ? "" : `<div class="group-items">${items}</div>`}
    </div>`;
  }).join("");
}

function renderLangs() {
  const langSearchEl = $("lang-search");
  if (S.collapsedLangs) {
    langSearchEl.style.display = "none";
    $("language-filters").innerHTML =
      `<button class="section-toggle-btn" onclick="toggleLangsSection()">▸ Show languages</button>`;
    return;
  }
  langSearchEl.style.display = "";

  const all = langGroups();
  const q   = S.langQ;
  const filtered = q
    ? all.filter(g => g.label.toLowerCase().includes(q) || g.codes.some(c => c.toLowerCase().includes(q)))
    : all;
  const shown = S.showAllL ? filtered : filtered.slice(0, 25);

  $("language-filters").innerHTML =
    `<button class="section-toggle-btn" onclick="toggleLangsSection()">▾ Hide languages</button>` +
    shown.map(g => {
      const i = all.indexOf(g);
      const on = g.codes.every(c => S.selLangs.has(c));
      return `
      <div class="filter-item" onclick="toggleLangGroup(${i})" title="${esc(g.codes.join(", "))}">
        <input type="checkbox" id="lk-${i}" ${on ? "checked" : ""} onclick="event.stopPropagation();toggleLangGroup(${i})">
        <label for="lk-${i}">${esc(g.label)}${g.codes.length > 1 ? ` <span class="lang-codes">${esc(g.codes.join(", "))}</span>` : ""}</label>
        <span class="filter-count">${fmt(g.count)}</span>
      </div>`;
    }).join("") +
    (filtered.length > 25 && !S.showAllL
      ? `<button class="show-more-btn" onclick="S.showAllL=true;renderLangs()">Show all ${filtered.length} languages</button>`
      : "");
}

// The index mixes ISO 639-1 and 639-3 codes for the same language (English is `en` in
// the English web data and `eng` in FineWeb-2/Wikipedia), so the list merges codes that
// share a display name: one checkbox selects all of them, with their summed count.
// Distinct varieties keep their own names (Standard vs Egyptian Arabic) and stay separate.
function langGroups() {
  if (S._langGroupsFor === S.aggs) return S._langGroups;
  const byLabel = new Map();
  (S.aggs?.languages || []).forEach(l => {
    const label = langLabel(l.key);
    const g = byLabel.get(label) || { label, codes: [], count: 0 };
    g.codes.push(l.key); g.count += l.count;
    byLabel.set(label, g);
  });
  S._langGroups = [...byLabel.values()].sort((a, b) => b.count - a.count);
  S._langGroupsFor = S.aggs;
  return S._langGroups;
}

function toggleLangGroup(i) {
  const g = langGroups()[i];
  if (!g) return;
  const on = g.codes.every(c => S.selLangs.has(c));
  g.codes.forEach(c => on ? S.selLangs.delete(c) : S.selLangs.add(c));
  renderLangs();
  doSearch(true);
}

function updateBadges() {
  const db = $("badge-datasets"); db.hidden = !S.selDS.size;    db.textContent = S.selDS.size;
  // Count languages, not codes: English is two codes but one choice.
  const nLangs = langGroups().filter(g => g.codes.some(c => S.selLangs.has(c))).length;
  const lb = $("badge-langs");    lb.hidden = !nLangs;          lb.textContent = nLangs;
}

function toggleDS(name) {
  S.selDS.has(name) ? S.selDS.delete(name) : S.selDS.add(name);
  renderDatasets();
  doSearch(true);
}

function toggleDSGroup(gid) {
  S.collapsedDS.has(gid) ? S.collapsedDS.delete(gid) : S.collapsedDS.add(gid);
  renderDatasets();
}

function toggleLangsSection() {
  S.collapsedLangs = !S.collapsedLangs;
  renderLangs();
}

function resetFilters() {
  S.selDS.clear(); S.selLangs.clear();
  S.dateFrom = ""; S.dateTo = "";
  S.inclNoLang = false; S.inclNoDate = false;
  $("date-from").value = ""; $("date-to").value = "";
  $("incl-no-lang").checked = false; $("incl-no-date").checked = false;
  S.langQ = ""; S.showAllL = false; $("lang-search").value = "";
  S.mode = "all"; S.slop = 0; S.exactTotal = false;
  document.querySelector('input[name="match-mode"][value="all"]').checked = true;
  $("slop-input").value = 0; $("exact-total").checked = false;
  ["must-input", "should-input", "mustnot-input"].forEach(id => { $(id).value = ""; });
  $("adv-box").open = false;
  renderSidebar(); updateBadges(); doSearch(true);
}

/* ─── Pagination ─────────────────────────────────────────────────── */
function renderPagination() {
  if (!S.results || S.results.total === 0) { $("pagination").innerHTML = ""; return; }
  const total = Math.min(Math.ceil(S.results.total / 10), 1000);
  if (total <= 1) { $("pagination").innerHTML = ""; return; }
  const p = S.page;
  const pages = pageNums(p, total);
  $("pagination").innerHTML = [
    `<button class="page-btn" ${p===0?"disabled":""} onclick="gotoPage(${p-1})">← Prev</button>`,
    ...pages.map(n => n === "…"
      ? `<span class="page-ellipsis">…</span>`
      : `<button class="page-btn${n===p?" active":""}" onclick="gotoPage(${n})">${n+1}</button>`),
    `<button class="page-btn" ${p>=total-1?"disabled":""} onclick="gotoPage(${p+1})">Next →</button>`,
  ].join("");
}

function pageNums(cur, total) {
  if (total <= 7) return Array.from({length:total},(_,i)=>i);
  if (cur < 4)       return [0,1,2,3,4,"…",total-1];
  if (cur > total-5) return [0,"…",total-5,total-4,total-3,total-2,total-1];
  return [0,"…",cur-1,cur,cur+1,"…",total-1];
}

function gotoPage(p) {
  S.page = p;
  runSearch();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ─── Helpers ────────────────────────────────────────────────────── */
function dsBadge(name) {
  const meta = DS[name];
  const cls  = meta ? `b-${meta.group}` : "b-lang";
  const lbl  = meta?.label || name;
  return `<span class="badge ${cls}">${esc(lbl)}</span>`;
}

function fmt(n) {
  if (n == null) return "?";
  if (n >= 1e9) return (n/1e9).toFixed(1)+"B";
  if (n >= 1e6) return (n/1e6).toFixed(1)+"M";
  if (n >= 1e3) return (n/1e3).toFixed(1)+"K";
  return n.toLocaleString();
}

function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function trimUrl(u) {
  try {
    const p = new URL(u);
    const s = p.hostname + p.pathname;
    return s.length > 65 ? s.slice(0,65)+"…" : s;
  } catch { return u.length > 65 ? u.slice(0,65)+"…" : u; }
}

/* Expose for inline onclick (sidebar, pagination) */
window.toggleDS   = toggleDS;
window.toggleLangGroup  = toggleLangGroup;
window.gotoPage         = gotoPage;
window.S                = S;
window.renderLangs      = renderLangs;
window.toggleDSGroup    = toggleDSGroup;
window.toggleLangsSection = toggleLangsSection;

init();
