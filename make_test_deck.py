#!/usr/bin/env python3
"""Build a disposable 12-card CVS APKG fixture for testing the image pipeline.
This is synthetic test data, NOT the user's original deck.
"""
import genanki

DECK_ID = 2056110401
MODEL_ID = 2056110402

cards = [
    ("xll$L=c}o-", "ما المعلم التشريحي الأبرز على الحاجز بين الأذينين داخل الأذين الأيمن؟", "الحفرة البيضوية (Fossa ovalis)، ويحيط بها بروز الحافة (Limbus fossae ovalis)."),
    ("yo~|<,}%RA", "ما التركيب الذي يفصل الجزء الخشن الأمامي عن الجزء الأملس الخلفي في الأذين الأيمن؟", "العرف الانتهائي (Crista terminalis)."),
    ("D0a8mV4oy.", "ما المقصود بـ Moderator band؟", "حزمة عضلية (Trabecula septomarginalis) تمتد من الحاجز بين البطينين إلى العضلة الحليمية الأمامية في البطين الأيمن."),
    ("ctiNCpCE,3", "ما مصير القرن الأيسر للجيب الوريدي؟", "يتحول أساسًا إلى الجيب التاجي (Coronary sinus) والوريد المائل للأذين الأيسر."),
    ("rqiVxmtsFq", "كيف يتكون Ostium secundum؟", "ينشأ من حدوث ثقوب في الجزء العلوي من الحاجز الأولي ثم اندماجها لتكوين الفتحة الثانوية."),
    ("H~:}ihjX$*", "ما التغيرات الضغطية التي تؤدي إلى إغلاق Foramen ovale بعد الولادة؟", "يزداد ضغط الأذين الأيسر مع انخفاض ضغط الأذين الأيمن؛ فينطبق الحاجز الأولي على الحاجز الثانوي."),
    ("FdM4l5uzje", "ما المقصود بـ Cardiac looping؟", "انثناء الأنبوب القلبي البدائي والتفافه لتكوين الوضع المكاني الأساسي لحجرات القلب."),
    ("qv=4)gpYi[", "رتّب الانتفاخات الخمسة البدائية للأنبوب القلبي من الذنبي إلى الرأسي.", "الجيب الوريدي، الأذين البدائي، البطين البدائي، البصل القلبي، الجذع الشرياني."),
    ("m`Z@R$FVHx", "ما مكونات الصمام ثلاثي الشرفات الخمسة؟", "الشرفات، الحلقة الليفية، الحبال الوترية، العضلات الحليمية، والهيكل الليفي الداعم."),
    ("jJjG[rL(Td", "ما وظيفة Trabeculae carneae؟", "نتوءات عضلية في البطينين تساعد في كفاءة الانقباض وتمنع التصاق جدران البطين."),
    ("HZ68FxcJ_o", "ما المقصود بالحزمة الموصلة بين الأذينين؟", "مسار باخمان (Bachmann bundle)، ينقل التنبيه الكهربائي من الأذين الأيمن إلى الأيسر."),
    ("LC}`gteH[w", "ما مصير Bulbus cordis؟", "يسهم في تكوين أجزاء من البطين الأيمن ومخارج البطينين، وفق تقسيماته الجنينية."),
]

model = genanki.Model(
    MODEL_ID,
    "CVS Pipeline Test Model",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Image"}],
    templates=[{
        "name": "Card 1",
        "qfmt": "{{Front}}",
        "afmt": "{{FrontSide}}<hr id=answer>{{Back}}<br>{{#Image}}{{Image}}{{/Image}}",
    }],
    css=".card { font-family: Arial; font-size: 20px; text-align: center; }",
)

deck = genanki.Deck(DECK_ID, "CVS Image Pipeline — TEST ONLY")
for guid, front, back in cards:
    note = genanki.Note(model=model, fields=[front, back, ""], guid=guid)
    deck.add_note(note)

genanki.Package(deck).write_to_file("cvs_pipeline_test.apkg")
print(f"Created cvs_pipeline_test.apkg with {len(cards)} test notes.")
