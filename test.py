from gtts import gTTS

# Оригинальный текст
original_text = "Иди сюда. Мне нужно рассказать тебе что-то важное."

# Ручные переводы: язык → (название_языка, перевод)
manual_translations = {
    'ru': ("russian", "Иди сюда. Мне нужно рассказать тебе что-то важное."),
    'uk': ("ukrainian", "Йди сюди. Мені потрібно тобі розповісти дещо важливе."),
    'en': ("english", "Come here. I need to tell you something important."),
    'de': ("german", "Komm her. Ich muss dir etwas Wichtiges erzählen."),
    'fr': ("french", "Viens ici. Je dois te dire quelque chose d'important."),
    'es': ("spanish", "Ven aquí. Necesito contarte algo importante."),
    'it': ("italian", "Vieni qui. Devo dirti qualcosa di importante."),
    'el': ("greek", "Έλα εδώ. Πρέπει να σου πω κάτι σημαντικό."),
    'fi': ("finnish", "Tule tänne. Minun täytyy kertoa sinulle jotain tärkeää."),
    'bg': ("bulgarian", "Ела тук. Трябва да ти кажа нещо важно."),
}

# Озвучка переведённых фраз
for lang_code, (lang_name, translated_text) in manual_translations.items():
    try:
        print(f"[{lang_name.capitalize()}] Перевод: {translated_text}")

        tts = gTTS(text=translated_text, lang=lang_code)
        filename = f"{lang_name}.mp3"
        tts.save(filename)
        print(f"✅ Сохранено: {filename}")

    except Exception as e:
        print(f"❌ Ошибка для языка {lang_name}: {e}")

# Закомментированный автоматический перевод
"""
from googletrans import Translator  # googletrans==4.0.0-rc1
translator = Translator()

async def auto_translate_and_speak():
    for lang_code in manual_translations.keys():
        translated = await translator.translate(original_text, dest=lang_code)
        print(f"[{lang_code}] Автоперевод: {translated.text}")
        # gTTS(...)

# asyncio.run(auto_translate_and_speak())
"""
