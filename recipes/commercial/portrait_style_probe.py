#!/usr/bin/env python3
"""立繪風格探針：同一組角色 prompt × 多種寫法 × 多顆 seed，比較模型的畫質與寫法效果。

背景（2026-09-15）：使用者看了三模型對照（outputs/commercial_ab/20260915_131202_official/quality_compare_*.jpg），
偏好 klein-4B 的寫實畫質（A），但喜歡 Z-Image base 那張低胸領口的性感感（C）。
做法：預設模型 klein-4B（Apache-2.0，可商用），只改 prompt。寫法依
The-Age-of-Exploration/tools/art-pipeline/FLUX2-KLEIN-PROMPT-LESSONS.md：
§1 服裝／身形放前面、§2 描述衣服底下的身體並避開會帶偏的名詞、§4 不寫否定句。
角色年齡設 24 歲（成年）。每種寫法 × 多顆 seed，輸出中文標籤對照表與 results.json。
個人用途（不商用）：--use personal 可用非商用授權模型（如 klein-9B）＋ --lora 外掛；
不進版控的本機寫法放同資料夾的 portrait_variants_local.py（定義 extra_variants(style, expression)），存在就自動載入。

跑（專案根目錄）：
  ~/.local/share/uv/tools/mflux/bin/python recipes/commercial/portrait_style_probe.py \
      [--use commercial|personal] [--model klein-4b|klein-9b|z-image-turbo|...] [--lora 路徑或 org/repo:檔名] \
      [--lora-scale 1.0] [--painted] [--skin clean|natural|beauty,...] [--variants 名稱,...] [--seeds 1131265990,424242] [--size 768x1152] [--dry-run]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_models as lm  # noqa: E402

MODEL = "klein-9b"
STYLE = ("Semi-realistic painted character portrait for a historical strategy game, "
         "soft cinematic key light, muted warm palette, head-and-shoulders framing, plain dark backdrop. ")
HAIR = "Her chestnut hair is pinned up at the back of the head, a few loose strands at the temples. "
IDENTITY = "A 24-year-old woman, the daughter of a sixteenth-century Lisbon chart-maker. "
NEUTRAL_IDENTITY = "A 24-year-old woman. "  # 選了族裔時改用這句（見 build_prompt）
FACE = "Strong level brows with a high clean arch, set well apart. "
SKIN = ("Flawless skin in one single even clean tone, a healthy warm glow, a soft matte finish, "
        "bright clear eyes with crisp catchlights, beautiful appealing features.")
EXPRESSION = ("A soft knowing half-smile, lips slightly parted, a warm confident gaze straight at the viewer, "
              "head tilted slightly. ")
LOW_NECK = ("She wears a deep green wool bodice laced at the front, cut low and square across the chest, "
            "over a white linen chemise whose gathered neckline sits low below the collarbones, "
            "showing her décolletage and the upper curve of her bust. ")
LOW_BODY = ("Under the bodice her figure is slender with a narrow cinched waist and a full bust; "
            "bare collarbones, upright posture. ")

VARIANTS = {
    "原版高領（對照）": dict(
        style=STYLE, extra="", body="Slender shoulders and an upright posture. ",
        clothing="She wears a deep green wool bodice laced at the front over a white linen chemise with a high gathered collar. "),
    "低胸方領": dict(style=STYLE, clothing=LOW_NECK, body=LOW_BODY, extra=""),
    "低胸方領＋神情": dict(style=STYLE, clothing=LOW_NECK, body=LOW_BODY, extra=EXPRESSION),
    "露肩＋低胸＋柔光": dict(
        style=STYLE.replace("soft cinematic key light", "warm soft window light grazing her bare shoulders"),
        clothing=("She wears a white linen chemise slipping off both shoulders, with a deep green wool bodice laced "
                  "at the front cut low across the chest, showing her décolletage and the upper curve of her bust. "),
        body="Bare smooth shoulders and collarbones, a narrow cinched waist and a full bust. ",
        extra=EXPRESSION),
    # 全身照（2026-09-15 使用者要「全身照，要有美腿的」）：直式尺寸建議 704x1216 或 1024x1536。
    "全身＋美腿": dict(
        style=STYLE.replace("soft cinematic key light", "warm soft window light across her bare shoulders and legs")
                   .replace("head-and-shoulders framing", "full-length framing from head to toe"),
        clothing=("She wears a white linen chemise slipping off both shoulders that ends high on her thighs, with a deep "
                  "green wool bodice laced at the front cut low across the chest, showing her décolletage; her long bare "
                  "legs are fully visible, barefoot on a wooden floor. "),
        body=("Bare smooth shoulders, a narrow cinched waist, a full bust, and long slender shapely legs with smooth skin. "
              "She stands with her weight on one leg, one knee slightly bent. "),
        extra=EXPRESSION),
    # 現代風格（2026-09-16 使用者要牛仔窄短裙）
    "現代牛仔短裙": dict(
        style=STYLE.replace("soft cinematic key light", "warm soft window light across her bare shoulders and legs")
                   .replace("head-and-shoulders framing", "full-length framing from head to toe"),
        clothing=("She wears a fitted white ribbed crop top and a tight denim mini skirt that sits high on her hips, "
                  "bare legs, white sneakers. "),
        body=("Bare smooth shoulders, a narrow waist, and long slender shapely legs with smooth skin. She stands with "
              "her weight on one leg, one knee slightly bent. "),
        identity="A 24-year-old woman with a slim figure, present-day fashion. ",
        extra=EXPRESSION),

    # 無審查 / 大膽性感系列（個人自用）
    "【無審查】全裸藝術人體寫真": dict(
        style=STYLE.replace("soft cinematic key light", "dramatic artistic chiaroscuro fine art lighting, soft shadows contouring the body")
                   .replace("head-and-shoulders framing", "three-quarter artistic fine art nude portrait"),
        clothing="She is completely nude with no clothes, fully uncovered bare skin, natural fine art nudity. ",
        body="Bare smooth shoulders, natural bare breasts, graceful collarbones, slender toned waist and natural feminine curves. ",
        extra=EXPRESSION),
    "【無審查】上空微光臥室寫真": dict(
        style=STYLE.replace("soft cinematic key light", "moody intimate bedroom lighting, warm morning sunlight grazing bare skin")
                   .replace("head-and-shoulders framing", "three-quarter framing from waist up"),
        clothing="She is topless, wearing only sheer silk lounge bottoms, bare upper body with exposed bare breasts. ",
        body="Smooth bare shoulders, uncovered bare breasts, narrow cinched waist, and graceful collarbones. ",
        extra=EXPRESSION),
    "【無審查】私密浴室濕身寫真": dict(
        style=STYLE.replace("soft cinematic key light", "steamy luxury marble bathroom lighting, soft mist and glistening water droplets")
                   .replace("head-and-shoulders framing", "three-quarter framing"),
        clothing="She is completely nude stepping out of a bath, wet damp skin with glistening water droplets, no clothing. ",
        body="Glistening wet skin, bare shoulders, natural bare breasts, slender waist, and sculpted feminine body. ",
        extra=EXPRESSION),
    "【無審查】性感黑蕾絲睡袍": dict(
        style=STYLE.replace("soft cinematic key light", "moody intimate bedroom lighting with soft warm highlights")
                   .replace("head-and-shoulders framing", "three-quarter framing"),
        clothing=("She wears a translucent black floral lace slip with delicate thin spaghetti straps, "
                  "the sheer fabric draped softly over her curves, revealing hints of her silhouette beneath. "),
        body="Bare smooth shoulders, delicate collarbones, a narrow cinched waist, and a shapely feminine figure. ",
        extra=EXPRESSION),
    "【無審查】微光半透真絲": dict(
        style=STYLE.replace("soft cinematic key light", "soft morning sunlight streaming through sheer curtains, gentle lens bloom")
                   .replace("head-and-shoulders framing", "three-quarter framing"),
        clothing=("She wears an open champagne-hued semi-sheer silk chiffon robe slipping off her bare shoulders, "
                  "unbuttoned at the chest to reveal her décolletage and cleavage. "),
        body="Smooth bare shoulders, glowing skin, a slender waist, and a full voluptuous bust. ",
        extra=EXPRESSION),
    "【無審查】濕身微透白襯衫": dict(
        style=STYLE.replace("soft cinematic key light", "natural diffused daylight, crisp details with subtle rim light")
                   .replace("head-and-shoulders framing", "three-quarter framing"),
        clothing=("She wears an oversized damp white cotton dress shirt unbuttoned low down the chest, "
                  "the semi-translucent wet fabric clinging delicately to her skin and contouring her bust. "),
        body="Bare collarbones, a narrow waist, full bust visible through damp fabric, upright poised posture. ",
        extra=EXPRESSION),
    "【無審查】比基尼泳裝・微風": dict(
        style=STYLE.replace("soft cinematic key light", "golden hour sun-drenched beach lighting, soft sea spray")
                   .replace("head-and-shoulders framing", "full-length framing from head to toe"),
        clothing=("She wears a minimalist chic emerald green triangle string bikini, "
                  "delicate straps tied at the neck and hips, bare legs, glistening fine water droplets on skin. "),
        body=("Sun-kissed smooth skin, athletic slender waist, toned abdomen, full shapely bust, "
              "and long shapely legs. She stands relaxed against a gentle ocean breeze. "),
        extra=EXPRESSION),
    "【無審查】深V露背晚禮服": dict(
        style=STYLE.replace("soft cinematic key light", "dramatic luxury architectural ballroom lighting, golden bokeh")
                   .replace("head-and-shoulders framing", "full-length framing from head to toe"),
        clothing=("She wears an alluring midnight-blue velvet evening gown cut with a daringly deep plunging V-neckline "
                  "down to her navel and an open back, with a high slit revealing her leg. "),
        body="Graceful posture, narrow cinched waist, full firm bust, smooth sculpted back, and long bare legs. ",
        extra=EXPRESSION),
    "【無審查】極致貼身針織裙": dict(
        style=STYLE.replace("soft cinematic key light", "warm contemporary penthouse interior lighting, soft ambient glow")
                   .replace("head-and-shoulders framing", "three-quarter framing"),
        clothing=("She wears an ultra-tight off-shoulder ribbed bodycon knit mini dress hugging every curve of her body, "
                  "accentuating her bust and hips. "),
        body="Sculpted hourglass silhouette, narrow waist, full round bust, smooth bare collarbones and shoulders. ",
        extra=EXPRESSION),
    "【自訂】自訂自由提示詞": dict(
        style="Photorealistic photograph, natural light, real camera photo. ",
        clothing="",
        body="",
        extra=""),

    # 男士正裝（2026-09-16 使用者要男士西裝選項）
    "男士商務正裝西裝": dict(
        gender="male",
        style=STYLE.replace("soft cinematic key light", "refined cinematic studio portrait lighting with subtle rim light")
                   .replace("head-and-shoulders framing", "full-length framing from head to toe"),
        clothing=("He wears an impeccably tailored charcoal-grey bespoke wool suit with sharp notch lapels, "
                  "a crisp pressed white dress shirt, a deep navy silk necktie, a folded white pocket square, "
                  "matching tailored trousers, and polished black leather oxford shoes. "),
        body=("Broad athletic shoulders, a straight upright posture, and a fit masculine physique. "
              "He stands with hands casually resting near his suit pockets in a confident stance. "),
        identity="A 28-year-old handsome man with a sophisticated, professional aura. ",
        extra="A calm, confident gaze straight at the camera, with a subtle determined expression. "),

    "男士雅痞休閒西裝": dict(
        gender="male",
        style=STYLE.replace("soft cinematic key light", "warm soft natural window daylight, modern architectural background")
                   .replace("head-and-shoulders framing", "three-quarter framing from the knees up"),
        clothing=("He wears a modern unconstructed navy blue blazer over an open-collar crisp white shirt "
                  "(no tie), paired with slim tailored trousers, a brown leather belt, and a luxury minimalist wristwatch. "),
        body=("Broad masculine shoulders, a fit athletic build, standing comfortably with an easy, relaxed posture. "),
        identity="A 28-year-old charismatic handsome man, stylish modern smart-casual tailoring. ",
        extra="A relaxed charming expression, subtle confident smile, sharp engaging eyes looking at the viewer. "),
}

BUILTIN_VARIANTS = tuple(VARIANTS)  # 內建（進版控）的寫法名稱，要在載入本機寫法之前記下來

# 不進版控的本機寫法（repo 是公開的）：接在上面四種之後，輸出檔名的編號照順序往後排。
_LOCAL_VARIANTS = Path(__file__).with_name("portrait_variants_local.py")
if _LOCAL_VARIANTS.exists():
    import importlib.util
    _spec = importlib.util.spec_from_file_location("portrait_variants_local", _LOCAL_VARIANTS)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    VARIANTS.update(_mod.extra_variants(style=STYLE, expression=EXPRESSION))


# 寫實照片風（預設）：klein-4B 會把 painted 直接畫成照片，但 klein-9B、Qwen 等較照字面的模型會真的畫成繪畫。
# 使用者 2026-09-15：「不要繪畫風格，都測寫實的」→ 預設一律照片風（也拿掉會帶出遊戲 CG 感的 for a game），--painted 才用原句。
PAINTED_LEAD = "Semi-realistic painted character portrait for a historical strategy game"
# 膚質寫法（照片風的開頭句＋結尾膚質句）：Z-Image-Turbo 很照字面，natural skin texture 會畫出雀斑與明顯毛孔，
# 使用者不喜歡雀斑（2026-09-15）→ 預設 clean。蒸餾模型不吃負面提示詞，只能靠正面描述；也不寫 no freckles（LESSONS §4）。
# 身形微調：接在身形句後面（LESSONS §2 描述衣服底下的身體）。default＝照原寫法。
# 長相類型（不綁定任何真人，只用五官描述）：face 取代預設五官句，hair 有寫就一併取代髮型句。
# 姿勢（2026-09-16 使用者要 12 種）：取代身形句裡的預設站姿；不指定就完全照舊。
# 取景（2026-09-16 使用者：「選全身都只出來半身」）：取景是寫法的風格句決定的，不是輸出尺寸決定的。
# 「原版高領（對照）」寫的是 head-and-shoulders framing，配 704×1216 也只會出頭肩。這裡讓取景可以單獨指定。
FRAMING_PRESETS = {
    "default": dict(label="照寫法", text=None),
    "full": dict(label="全身（頭到腳）", text="full-length framing from head to toe, her whole body and her feet in frame"),
    "threequarter": dict(label="七分身（大腿以上）", text="three-quarter framing from head to mid-thigh"),
    "waist": dict(label="半身（腰以上）", text="waist-up framing"),
    "head": dict(label="頭肩", text="head-and-shoulders framing"),
}
_FRAMING_RE = re.compile(r"(?:head-and-shoulders|waist-up|full-length|three-quarter) framing(?: from head to toe)?")
# 只換取景片語不夠：服裝句還寫著「bare legs, white sneakers」、身形句寫著「long slender shapely legs」，
# 燈光句寫著「across her bare shoulders and legs」，三句都在喊腿，模型就會退遠拍全身（2026-09-16 實測，
# 取景選半身仍出全身、臉太小所以鎖不住）。選半身／頭肩時，把描述腿腳鞋的子句一起拿掉。
_LEG_WORDS = re.compile(r"\b(?:legs?|feet|barefoot|sneakers)\b", re.I)
# 有主詞或動作的子句要留著：「She stands with her weight on one leg」是姿勢不是在描述腿，
# 砍掉會把句子切壞（實測會留下「, one knee slightly bent.」這種殘句）。
_ACTION_WORDS = re.compile(r"\b(?:she|stands?|sits?|kneels?|lies|leans?|wears?|crossed|folded|propped)\b", re.I)
_CLOSE_FRAMINGS = ("waist", "head")


def _drop_leg_clauses(text):
    """拿掉「描述腿腳鞋」的子句，保留有主詞／動作的句子，並把標點接回去。"""
    out = []
    for sent in re.findall(r"[^.]+\.\s*", text):
        clauses = [c.strip() for c in sent.strip().rstrip(".").split(",")]
        keep = [c for c in clauses if c and not (_LEG_WORDS.search(c) and not _ACTION_WORDS.search(c))]
        if keep:
            out.append(", ".join(keep) + ". ")
    return "".join(out)
DEFAULT_POSE = "She stands with her weight on one leg, one knee slightly bent. "
POSE_PRESETS = {
    "default": dict(label="原本站姿", text=DEFAULT_POSE),
    "back": dict(label="背對回眸", text="She stands with her back to the camera, looking back over one shoulder. "),
    "hair": dict(label="雙手撩髮", text="She stands with both arms raised, hands gathering her hair above her head, elbows out. "),
    "profile": dict(label="側身站立", text="She stands in profile, one hip pushed out, arms relaxed at her sides. "),
    "stool": dict(label="坐木凳（優雅斜並腿）", text="She sits upright on a low wooden stool with graceful posture, knees together, both legs kept cleanly together and angled gently to one side, both feet resting naturally on the floor with anatomically correct legs and feet. "),
    "prone_forward": dict(label="往前傾趴臥（手肘支撐）", text="She is lying prone on her stomach, upper body propped up on her elbows and leaning forward toward the camera, chest lifted, looking directly into the lens with an arched back, legs resting naturally behind her. "),
    "glass_press": dict(label="趴在前方透明玻璃上", text="She leans forward pressed against a large clear transparent glass pane directly in front of the camera, both open hands and palms flattened against the smooth glass surface, chest and torso gently pressed against the clear glass pane, gazing directly through the glass at the viewer, subtle clean reflections on the transparent glass. "),
    "kneel_lean": dict(label="跪姿前傾（手撐地）", text="She is on her knees leaning forward with both hands on the floor supporting her weight, back gently arched, chest low, gazing up at the camera. "),
    "floor": dict(label="地板側坐", text="She sits on the floor with her legs folded to one side, one hand on the floor behind her. "),
    "kneel": dict(label="跪坐", text="She kneels upright on the floor, back straight, hands resting on her thighs. "),
    "wall": dict(label="靠牆", text="She leans back against a plain wall, one foot flat against it, head tilted back slightly. "),
    "side": dict(label="側躺", text="She lies on her side on a low bed, head propped on one hand, legs slightly bent. "),
    "supine": dict(label="仰躺", text="She lies on her back on a low bed, knees bent, both arms stretched above her head. "),
    "prone": dict(label="趴臥（平趴放鬆）", text="She lies face down on a low bed, propped up on her forearms, ankles crossed in the air. "),
    "stretch": dict(label="踮腳伸展", text="She stands on tiptoe, arms stretched high above her head, back gently arched. "),
}
# 長相類型（不綁定任何真人，只用五官描述）。ethnic＝族裔短句：prompt 不寫族裔時 klein 一律畫歐美臉
# （2026-09-16 使用者回饋「應該是東方人」），所以東亞選項多一句；有參考圖時只有這句會用到，
# 其餘五官與髮型全部交給參考圖。
_EAST_ASIAN = "She is a young East Asian woman with East Asian facial features. "
FACE_PRESETS = {
    "default": dict(label="原本", face=None, hair=None, ethnic=None),
    "fringe": dict(label="齊瀏海褐眼",
                   face=("An oval face with soft delicate features, high cheekbones, hazel-green eyes with a direct "
                         "gaze, and full natural lips. "),
                   hair=("Her long dark-blonde hair is loosely pinned up, with a soft blunt fringe falling to her "
                         "eyebrows and a few loose strands framing her face. "),
                   ethnic=None),
    "east_asian": dict(label="東亞・黑長髮",
                       face=(_EAST_ASIAN + "A softly oval face with smooth delicate features, high cheekbones, "
                             "dark almond-shaped eyes with a direct gaze, and full natural lips. "),
                       hair="Her long straight black hair falls loosely past her shoulders. ",
                       ethnic=_EAST_ASIAN),
    "east_asian_fringe": dict(label="東亞・齊瀏海",
                              face=(_EAST_ASIAN + "A softly oval face with smooth delicate features, high cheekbones, "
                                    "dark almond-shaped eyes with a direct gaze, and full natural lips. "),
                              hair=("Her long straight black hair falls past her shoulders, with a soft blunt fringe "
                                    "falling to her eyebrows. "),
                              ethnic=_EAST_ASIAN),
    "east_asian_ponytail": dict(label="東亞・高馬尾",
                                face=(_EAST_ASIAN + "A softly oval face with smooth delicate features, high cheekbones, "
                                      "dark almond-shaped eyes with a direct gaze, and full natural lips. "),
                                hair=("Her sleek black hair is pulled up tightly into a high, bouncy ponytail at the crown "
                                      "of her head, with the long tail falling down her back and a few soft wisps framing her face. "),
                                ethnic=_EAST_ASIAN),
    "ponytail": dict(label="高馬尾（歐美褐髮）",
                     face=("An oval face with soft delicate features, high cheekbones, hazel-green eyes with a direct "
                           "gaze, and full natural lips. "),
                     hair=("Her dark-blonde hair is gathered into a sleek high ponytail at the crown of her head, "
                           "with a few soft delicate strands framing her temples. "),
                     ethnic=None),
    "east_asian_male": dict(
        label="東亞男性・俐落短髮",
        gender="male",
        face="A handsome young East Asian man with clean sharp facial contours, a strong jawline, and clear expressive eyes. ",
        hair="His clean short black hair is neatly groomed and styled, short on the sides with subtle modern texture. ",
        ethnic="He is a young East Asian man with East Asian features. "),
    "gentleman_fade": dict(
        label="型男・側分油頭",
        gender="male",
        face="A handsome man with sharp masculine features, high cheekbones, strong jawline, and charismatic direct gaze. ",
        hair="His dark hair is neatly styled into a classic side-part pompadour with a clean fade along the sides. ",
        ethnic=None),
}
BUST_PRESETS = {
    "default": "",
    "slender": "Her bust is petite and modest, a delicate slender silhouette with graceful collarbones. ",
    "full": "Her bust is large, full and firm, with a rounded upper curve and a natural lift. ",
    "fuller": ("Her bust is very large, full and firm, sitting high and round with a pronounced upper curve and a "
               "strong natural lift. "),
    "huge": ("Her bust is extremely large and heavy yet firm, sitting high on her chest with a deep cleavage, a "
             "pronounced round upper curve and a strong lift. "),
    "maximum": ("Her bust is extraordinarily massive, lush and heavy, exceptionally voluptuous with deep cleavage and "
                "an ultra-pronounced curve. "),
}
PROPORTION_PRESETS = {
    "golden_8head": dict(
        label="八頭身超模（黃金比例·小頭長腿）★推薦",
        text=("Perfect golden ratio fashion model proportions, a petite delicate head relative to a tall slender "
              "statuesque physique, long graceful neck, high natural waistline, and exceptionally long slender shapely legs, "
              "flawless 8-head-tall anatomical silhouette. ")
    ),
    "supermodel_9head": dict(
        label="九頭身極致修長（伸展台超模·極致美腿）",
        text=("Ultra-elongated haute couture runway model proportions, an exceptionally small delicate head and face, "
              "long slender neck, high cinched waist, and extraordinarily long slender shapely legs, dramatic 9-head-tall "
              "supermodel silhouette. ")
    ),
    "natural_balanced": dict(
        label="自然勻稱（標緻和諧·真實美感）",
        text=("Naturally well-proportioned feminine silhouette, balanced head-to-body ratio, graceful natural curves "
              "and slender shapely legs with harmonious anatomical proportions. ")
    ),
    "petite_slender": dict(
        label="嬌小苗條（精巧骨架·優雅比例）",
        text=("Petite yet beautifully proportioned frame, delicate small head, slim waist and slender shapely legs "
              "with graceful natural proportions. ")
    ),
    "default": dict(
        label="照寫法預設",
        text=""
    ),
}
## 參考圖鎖臉（GUI 上傳參考圖時用）。
# 修正（2026-09-18）：老底片掃描（如蘇菲·瑪索 90 年代劇照）本身帶有嚴重鎢絲燈偏黃底色。
# 鎖臉詞嚴格鎖定「五官、輪廓、眼神、髮色、髮型與面部神韻」，而將膚色權限保留給使用者所選膚色 preset，
# 避免強行複製參考圖泛黃色調。
REF_LEAD = "A photo of the exact same woman as the person shown in image 1, the same face and the same hair. "
REF_TAIL = ("Keep her facial features, facial contours, eyes, eyebrows, nose, mouth, hair colour, hairstyle "
            "and facial likeness completely identical to image 1. Natural candid pose, real camera photo, "
            "sharp focus.")
DEFAULT_SKIN = {"commercial": "clean", "personal": "cold_white"}
SKIN_PRESETS = {
    "cold_white": dict(
        label="極致冷白皮（零偏黃·冷調透亮）★推薦",
        lead="Photorealistic portrait photograph, clear cool daylight illumination",
        style_swaps=(
            ("warm soft window light", "soft cool daylight from a window"),
            ("soft cinematic key light", "clean cool daylight key light"),
            ("muted warm palette", "crisp cool neutral palette"),
            ("warm morning sunlight", "clear bright morning daylight"),
            ("soft warm highlights", "soft clean neutral highlights"),
            ("golden hour sun-drenched beach lighting", "bright clear daylight coastal lighting"),
            ("golden bokeh", "clean neutral bokeh"),
            ("a healthy warm glow", "a luminous cool fair glow"),
        ),
        skin=("Extremely fair alabaster porcelain skin with delicate cool pink undertones, "
              "a translucent luminous complexion, completely devoid of yellow tint or sallow undertone, "
              "soft clean neutral-cool daylight, bright clear eyes with crisp catchlights, beautiful appealing features.")
    ),
    "rosy_white": dict(
        label="櫻花粉白（白皙透粉·氣色紅潤）",
        lead="Photorealistic portrait photograph, balanced neutral daylight",
        style_swaps=(
            ("warm soft window light", "soft neutral daylight from a window"),
            ("soft cinematic key light", "soft diffused natural daylight"),
            ("muted warm palette", "clean neutral palette with subtle rosy accents"),
            ("warm morning sunlight", "soft fresh morning daylight"),
            ("soft warm highlights", "soft rosy-white highlights"),
            ("golden bokeh", "neutral bokeh"),
            ("a healthy warm glow", "a fresh vibrant rosy glow"),
        ),
        skin=("Very fair porcelain skin with a soft delicate rosy-pink flush on the cheeks and lips, "
              "a vibrant healthy fair complexion, smooth translucent texture with a radiant glow, "
              "clean diffused daylight, bright clear eyes with crisp catchlights, beautiful appealing features.")
    ),
    "fair": dict(
        label="自然白皙（純淨透亮·中性調）",
        lead="Photorealistic portrait photograph, clean natural daylight",
        style_swaps=(
            ("warm soft window light", "soft neutral daylight from a window"),
            ("soft cinematic key light", "soft natural daylight"),
            ("muted warm palette", "clean neutral palette"),
            ("warm morning sunlight", "soft morning daylight"),
            ("soft warm highlights", "soft natural highlights"),
            ("golden bokeh", "neutral bokeh"),
            ("a healthy warm glow", "a clean natural glow"),
        ),
        skin=("Fair, light skin in one single even clean tone with neutral undertones, "
              "a fresh natural glow, smooth texture, soft clean daylight, "
              "bright clear eyes with crisp catchlights, beautiful appealing features.")
    ),
    "porcelain": dict(
        label="柔焦瓷白（古典純白·高級無瑕）",
        lead="Photorealistic high-end beauty portrait, professionally retouched",
        style_swaps=(
            ("warm soft window light", "soft cool daylight from a window"),
            ("soft cinematic key light", "soft diffused studio key light"),
            ("muted warm palette", "clean ivory-neutral palette"),
            ("warm morning sunlight", "clear bright morning light"),
            ("soft warm highlights", "soft ivory highlights"),
            ("golden bokeh", "neutral bokeh"),
        ),
        skin=("Flawless porcelain-white skin with smooth satin finish, perfectly even tone, "
              "soft diffused studio lighting, bright clear eyes with crisp catchlights, beautiful appealing features.")
    ),
    "warm_ivory": dict(
        label="暖白象牙（溫潤柔和·奶油肌）",
        lead="Photorealistic portrait photograph, soft flattering illumination",
        style_swaps=(),
        skin=("Fair creamy ivory skin with a delicate satin glow and soft smooth finish, "
              "gentle flattering light, even ivory complexion, bright clear eyes with crisp catchlights, "
              "beautiful appealing features.")
    ),
    "natural": dict(
        label="原生自然（真實膚質·微暖細節）",
        lead="Photorealistic portrait photograph, natural skin texture",
        style_swaps=(),
        skin=SKIN
    ),
    "clean": dict(
        label="乾淨膚質（商用棚拍標準）",
        lead="Photorealistic portrait photograph",
        style_swaps=(),
        skin=SKIN
    ),
    "sun_kissed": dict(
        label="陽光小麥（健康蜜糖·微古銅光澤）",
        lead="Photorealistic outdoor portrait photograph",
        style_swaps=(),
        skin=("Smooth healthy sun-kissed golden honey skin with a radiant sunlit sheen, "
              "athletic natural glow, warm golden outdoor lighting, bright clear eyes with crisp catchlights, "
              "beautiful appealing features.")
    ),
}
QUALITY_NEGATIVE = ("blurry, low quality, oversized head, big head, short legs, long torso, disproportionate body, "
                    "stubby limbs, deformed limbs, deformed legs, extra legs, extra limbs, bad anatomy, "
                    "deformed face, deformed hands, extra fingers, watermark, text")
PAINT_NEGATIVE = "painting, oil painting, illustration, drawing, cartoon, anime, 3d render, cgi, plastic skin"


def build_prompt(v, photo=False, skin="cold_white", bust="default", face="default", pose="default", ref=False,
                 framing="default", proportion="golden_8head"):
    # LESSONS §1 的段落順序：風格 → 服裝 → 髮型 → 身形 → 身分 → 臉 → 神情 → 膚質
    preset = SKIN_PRESETS.get(skin, SKIN_PRESETS["cold_white"])
    fp = FACE_PRESETS[face]
    is_male = (v.get("gender") == "male") or (fp.get("gender") == "male")

    style = v["style"].replace(PAINTED_LEAD, preset["lead"]) if photo else v["style"]
    for old, new in preset.get("style_swaps", ()):
        style = style.replace(old, new)
    if framing != "default":
        text = FRAMING_PRESETS[framing]["text"]
        style, n = _FRAMING_RE.subn(text, style)
        if not n:  # 風格句沒寫取景就補一句
            style += text[0].upper() + text[1:] + ". "

    prop_obj = PROPORTION_PRESETS.get(proportion, PROPORTION_PRESETS["golden_8head"])
    prop_text = prop_obj["text"]

    body, clothing = v["body"], v["clothing"]
    if framing in _CLOSE_FRAMINGS:
        clothing = _drop_leg_clauses(clothing)
        body = _drop_leg_clauses(body)
        prop_text = _drop_leg_clauses(prop_text)
        style = style.replace(" across her bare shoulders and legs", " across her bare shoulders")
    if pose != "default":
        body = re.sub(r"(She stands with her weight on one leg|She stands relaxed against a gentle ocean breeze|He stands with hands casually resting near his suit pockets|He stands comfortably)[^.]*\.\s*", "", body) + POSE_PRESETS[pose]["text"]

    bust_clause = "" if is_male else BUST_PRESETS[bust]
    body_with_prop = (prop_text + body) if not is_male else body

    if ref:
        n = ref if (isinstance(ref, int) and ref > 1) else 1
        refs_str = "image 1" if n == 1 else ("images " + ", ".join(str(i) for i in range(1, n)) + f" and {n}")
        ref_lead = f"A photo of the exact same person as shown in {refs_str}, identical face and hair. "
        ref_tail = (f"Keep facial features, facial contours, eyes, eyebrows, nose, mouth, hair colour, hairstyle "
                    f"and facial likeness completely identical to {refs_str}. Natural candid pose, real camera photo, "
                    f"sharp focus.")
        skin_clause = f"Her skin tone and complexion is: {preset['skin']} "
        return (ref_lead + (fp.get("ethnic") or "") + style + clothing + body_with_prop + bust_clause
                + skin_clause + v["extra"] + ref_tail)

    if is_male:
        hair_clause = fp["hair"] or "His dark hair is cleanly cut and neatly groomed, short on the sides. "
        face_clause = fp["face"] or "A handsome masculine face with sharp features and a strong jawline. "
        identity = v.get("identity") or ("He is a handsome 28-year-old East Asian man. " if fp.get("ethnic") else "A handsome 28-year-old man. ")
        skin_clause = preset["skin"].replace("beautiful appealing features", "handsome appealing features")
    else:
        hair_clause = fp["hair"] or HAIR
        face_clause = fp["face"] or FACE
        identity = v.get("identity") or (NEUTRAL_IDENTITY if fp.get("ethnic") else IDENTITY)
        skin_clause = preset["skin"]

    return (style + clothing + hair_clause + body_with_prop + bust_clause
            + identity + face_clause + v["extra"] + skin_clause)


def negative_for(key, photo):
    """只有非蒸餾模型吃負面提示詞；照片風再加推離繪畫感的詞（同 2026-06 Qwen 場景圖 recipes 的做法）。"""
    if lm.MODELS[key]["distilled"]:
        return None
    return f"{PAINT_NEGATIVE}, {QUALITY_NEGATIVE}" if photo else QUALITY_NEGATIVE


def load_font(size):
    from PIL import ImageFont
    for path in ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/PingFang.ttc"):
        try:
            return ImageFont.truetype(path, size, index=0)
        except Exception:
            continue
    return ImageFont.load_default()


def contact_sheet(cells, names, seeds, out, thumb_w=384):
    """列＝寫法、欄＝seed；中文標籤用系統內建的冠群黑體。"""
    from PIL import Image, ImageDraw
    if not cells:
        return None
    first = Image.open(next(iter(cells.values()))["path"])
    th = int(first.height * thumb_w / first.width)
    bar = 34
    font = load_font(20)
    sheet = Image.new("RGB", (thumb_w * len(seeds), (th + bar) * len(names)), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    for r, name in enumerate(names):
        for c, seed in enumerate(seeds):
            x, y = c * thumb_w, r * (th + bar)
            cell = cells.get((name, seed))
            label = f"{name} · seed {seed}"
            if not cell:
                draw.text((x + 8, y + 6), label + " · 失敗", font=font, fill=(255, 120, 120))
                continue
            im = Image.open(cell["path"]).convert("RGB").resize((thumb_w, th), Image.Resampling.LANCZOS)
            sheet.paste(im, (x, y + bar))
            size = 20  # 標籤太長會疊到隔壁格：縮字直到放得下
            while size > 12 and draw.textlength(label, font=load_font(size)) > thumb_w - 16:
                size -= 1
            draw.text((x + 8, y + 6), label, font=load_font(size), fill=(240, 240, 240))
    sheet.save(out, quality=92)
    return out


def resolve_lora(spec):
    """解析 LoRA：支援 loras/ 目錄檔案、本機路徑、或 HF org/repo:檔名。"""
    if not spec:
        return None
    # 優先檢查專案根目錄的 loras/ 資料夾
    local_lora = Path("loras") / spec
    if local_lora.is_file():
        return str(local_lora.resolve())
    local_lora_st = Path("loras") / f"{spec}.safetensors"
    if local_lora_st.is_file():
        return str(local_lora_st.resolve())
    if Path(spec).expanduser().exists():
        return str(Path(spec).expanduser().resolve())
    if ":" not in spec:
        return spec
    repo, filename = spec.split(":", 1)
    lm._ensure_hf_env()
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo_id=repo, filename=filename, token=os.environ.get("HF_TOKEN"))


def main():
    ap = argparse.ArgumentParser(description="立繪風格探針（畫質＋寫法對照）")
    ap.add_argument("--seeds", default="1131265990,424242")
    ap.add_argument("--size", default="1024x1536" if lm.total_ram_gb() >= 30 else "768x1152",
                    help="寬x高，需為 16 的倍數（32GB M5 原生支援 1024x1536 與 1024x1024）")
    ap.add_argument("--variants", default=None, help="只跑部分寫法，逗號分隔（預設全部）")
    ap.add_argument("--use", default="personal", choices=lm.USES,
                    help="personal＝自用（預設，支援非商用模型如 klein-9b）；commercial＝商用授權嚴格把關")
    ap.add_argument("--model", default=MODEL,
                    choices=[k for k, m in lm.MODELS.items() if m["kind"] in ("flux2", "z_image", "qwen")])
    ap.add_argument("--quantize", type=int, default=8 if lm.total_ram_gb() >= 30 else 4, choices=[4, 8],
                    help="量化位元：32GB M5 建議 8-bit（消除眼周微變形與色塊），24GB 機器用 4-bit")
    ap.add_argument("--uncensored", action="store_true", help="掛載無審查 Text Encoder 解除提示詞審查限制")
    ap.add_argument("--text-encoder", default=None, help="指定自訂或無審查 Text Encoder 路徑或 HF repo")
    ap.add_argument("--lora", default=None, help="LoRA／LoKr：loras/ 檔名、本機檔案，或 HF 的 org/repo:檔名.safetensors")
    ap.add_argument("--lora-scale", type=float, default=1.0)
    ap.add_argument("--painted", action="store_true",
                    help="改用原本的繪畫風格句（預設是寫實照片風，非蒸餾模型另加推離繪畫感的負面提示詞）")
    ap.add_argument("--photo-style", action="store_true", help=argparse.SUPPRESS)  # 舊參數：現在預設就是照片風
    ap.add_argument("--skin", default=None,
                    help="膚質寫法，逗號分隔可一次比多種：clean（商用預設）、fair（白皙＋中性光，個人預設）、"
                         "porcelain（瓷白＋冷光）、beauty（美妝級）、natural（自然紋理，Z-Image-Turbo 會有雀斑）")
    ap.add_argument("--bust", default="default", choices=list(BUST_PRESETS),
                    help="身形微調：slender＝苗條精巧，full＝豐滿堅挺，fuller＝更大更高，huge＝超大，maximum＝極致巨大")
    ap.add_argument("--face", default="default", choices=list(FACE_PRESETS),
                    help="長相類型：fringe＝齊瀏海、褐綠色眼睛、深金褐長髮；east_asian＝東亞黑長髮、"
                         "east_asian_fringe＝東亞齊瀏海")
    ap.add_argument("--pose", default="default",
                    help="姿勢，逗號分隔可一次跑多種，all＝全部 12 種：" + "、".join(POSE_PRESETS))
    ap.add_argument("--framing", default="default", choices=list(FRAMING_PRESETS),
                    help="取景：full＝全身、threequarter＝七分身、waist＝半身、head＝頭肩（預設照寫法的風格句）")
    ap.add_argument("--low-ram", action="store_true",
                    help="MLX 快取上限 1GB＋VAE 分塊解碼（24GB 機器跑大模型用，32GB 建議免開以加速常駐）")
    ap.add_argument("--dry-run", action="store_true", help="只印計畫與 prompt，不載模型")
    a = ap.parse_args()

    key = a.model
    photo = not a.painted
    lm.require(key, a.use)
    seeds = [int(s) for s in a.seeds.split(",")]
    width, height = (int(v) for v in a.size.lower().split("x"))
    if width % 16 or height % 16:
        raise SystemExit(f"✗ 尺寸需為 16 的倍數：{a.size}")
    names = [n.strip() for n in a.variants.split(",")] if a.variants else list(VARIANTS)
    unknown = [n for n in names if n not in VARIANTS]
    if unknown:
        raise SystemExit(f"✗ 未知寫法 {unknown}；可用：{list(VARIANTS)}")
    # 使用者 2026-09-16 定案：個人用途一律白皙；商用立繪維持 clean（選定的「露肩＋低胸＋柔光」靠的就是暖色窗光）。
    skins = [sk.strip() for sk in (a.skin or DEFAULT_SKIN[a.use]).split(",")]
    bad = [sk for sk in skins if sk not in SKIN_PRESETS]
    if bad:
        raise SystemExit(f"✗ 未知膚質 {bad}；可用：{list(SKIN_PRESETS)}")
    poses = list(POSE_PRESETS) if a.pose == "all" else [p.strip() for p in a.pose.split(",")]
    bad_pose = [p for p in poses if p not in POSE_PRESETS]
    if bad_pose:
        raise SystemExit(f"✗ 未知姿勢 {bad_pose}；可用：{list(POSE_PRESETS)} 或 all")
    def _row(n, sk, po):
        parts = [n]
        if len(skins) > 1:
            parts.append(SKIN_PRESETS[sk]["label"])
        if len(poses) > 1 or po != "default":
            parts.append(POSE_PRESETS[po]["label"])
        return " · ".join(parts)
    rows = [(n, sk, po, _row(n, sk, po)) for n in names for sk in skins for po in poses]

    lora_tag = f"_{re.sub(r'[^A-Za-z0-9._-]+', '-', Path(a.lora.split(':')[-1]).stem)}" if a.lora else ""
    bust_tag = ("" if a.bust == "default" else f"_bust-{a.bust}") + ("" if a.face == "default" else f"_face-{a.face}")
    q_tag = f"_q{a.quantize}"
    out = Path(f"outputs/{a.use}_style/{time.strftime('%Y%m%d_%H%M%S')}_{key}{q_tag}{lora_tag}{bust_tag}")
    neg = negative_for(key, photo)
    d = lm.MODELS[key]["defaults"]
    print(f"== {key}（{lm.MODELS[key]['license']}）· 用途 {a.use} · {a.quantize}-bit 量化 · {len(names)} 種寫法 × {len(skins)} 種膚質 × {len(poses)} 種姿勢 × {len(seeds)} 顆 seed = "
          f"{len(rows) * len(seeds)} 張 · {width}x{height} · steps {d.get('steps')} · guidance {d.get('guidance')} · "
          f"{'照片風' if photo else '原風格句'} · 膚質 {','.join(skins)} · 身形 {a.bust} · 長相 {a.face} · "
          f"姿勢 {','.join(poses)} · 取景 {a.framing}")
    te_target = a.text_encoder or ("darknight9121/FLUX.2-klein-base-9B-bucket-uncensored" if a.uncensored else None)
    if te_target:
        print(f"== 無審查 Text Encoder：{te_target}")
    print(f"== LoRA：{f'{a.lora}（強度 {a.lora_scale}）' if a.lora else '無'}")
    print(f"== 負面提示詞：{neg or '（蒸餾模型不吃）'}")
    for n, sk, po, row in rows:
        print(f"-- {row}：{build_prompt(VARIANTS[n], photo, sk, a.bust, a.face, po, framing=a.framing)}")
    if a.dry_run:
        return

    t0 = time.time()
    lora_path = resolve_lora(a.lora)
    if lora_path:
        print(f"== LoRA 本機路徑：{lora_path}", flush=True)
    model = lm.load(key, a.use, quantize=a.quantize, low_ram=a.low_ram,
                    lora_paths=[lora_path] if lora_path else None,
                    lora_scales=[a.lora_scale] if lora_path else None,
                    text_encoder_path=te_target)
    results, cells = [], {}
    for n, sk, po, row in rows:
        prompt = build_prompt(VARIANTS[n], photo, sk, a.bust, a.face, po, framing=a.framing)
        for seed in seeds:
            t1 = time.time()
            rec = dict(**lm.license_record(key), use=a.use, lora=a.lora, lora_scale=a.lora_scale if a.lora else None,
                       photo_style=photo, skin=sk, bust=a.bust, face=a.face, pose=po, framing=a.framing,
                       variant=n, seed=seed, width=width, height=height, prompt=prompt,
                       negative_prompt=neg, steps=d.get("steps"), guidance=d.get("guidance"))
            try:
                img = lm.generate(model, key, prompt=prompt, seed=seed, width=width, height=height,
                                  negative_prompt=neg)
                idx = list(VARIANTS).index(n)
                parts = [str(idx)] + ([] if sk == "natural" else [sk]) + ([] if po == "default" else [po]) + [str(seed)]
                fname = "_".join(parts) + ".png"
                path = lm.save(img, out / fname)
                rec.update(ok=True, path=str(path), seconds=round(time.time() - t1, 1))
                cells[(row, seed)] = rec
                print(f"   ✓ {row} seed {seed}：{rec['seconds']:.0f}s → {path}", flush=True)
            except Exception as ex:  # noqa: BLE001
                rec.update(ok=False, error=repr(ex)[:300], seconds=round(time.time() - t1, 1))
                print(f"   ✗ {row} seed {seed}：{rec['error']}", flush=True)
            results.append(rec)
            lm.free()
    model = None
    lm.free()
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    sheet = contact_sheet(cells, [row for *_, row in rows], seeds, out / "contact.jpg")
    print(f"\n== 完成 {(time.time() - t0) / 60:.0f} 分鐘 · 對照表 {sheet} · 紀錄 {out / 'results.json'}")


if __name__ == "__main__":
    main()
