from deep_translator import GoogleTranslator
import time


class SmartTextTranslator:
    def __init__(self, source_lang='uk', target_lang='ru', pause_seconds=1):
        self.translator = GoogleTranslator(source=source_lang, target=target_lang)
        self.pause_seconds = pause_seconds

    def translate(self, text):
        if not text or str(text).strip() == "":
            return ""

        text_str = str(text).strip()
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Ограничение длины для API Google Translate
                if len(text_str) > 4500:
                    parts = text_str.split('. ')
                    translated_parts = []
                    current_chunk = ""

                    for part in parts:
                        if len(current_chunk) + len(part) < 4500:
                            current_chunk += part + ". "
                        else:
                            if current_chunk:
                                translated_parts.append(self.translator.translate(current_chunk.strip()))
                                time.sleep(self.pause_seconds)
                            current_chunk = part + ". "

                    if current_chunk:
                        translated_parts.append(self.translator.translate(current_chunk.strip()))

                    return " ".join(translated_parts)
                else:
                    return self.translator.translate(text_str)

            except Exception as e:
                print(f"[Внимание] Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.pause_seconds * 2)
                else:
                    return f"[ОШИБКА ПЕРЕВОДА: {text_str[:50]}...]"
        return ""


# ==========================================
# КОРОТКИЙ ТЕСТОВЫЙ ЗАПУСК
# ==========================================
if __name__ == "__main__":
    my_translator = SmartTextTranslator(source_lang='uk', target_lang='ru', pause_seconds=1)

    sample_text = """Furby Coral - це інтерактивна плюшева іграшка, яка стане найкращим другом для вашої дитини. Ця надзвичайно інтерактивна іграшка може рухатись, розмовляти, співати, світитись і навіть відповідати на голосові команди. Furby здатний реагувати на обійми, постукування по голові, струшування та "годування" уявною піцою (або вашим пальцем). Чим більше ви граєтесь з Furby, тим більше цікавих можливостей він відкриває. Furby також вміє розповідати жарти, співати пісні та видавати смішні фрази на англійській та фурбській мовах.

Особливості:
*	Завжди готовий до дружби: Furby - це інтерактивна іграшка для хлопчиків та дівчаток, яка рухається, розмовляє, співає, світиться та відповідає на голосові команди.
*	Голосові команди: Натисніть на сердечко Furby та скажіть "Hey Furby!" для активації голосових команд, які відкривають 5 режимів гри (без підключення до інтернету).
*	Понад 600 відповідей: Спілкуйтесь, співайте та смійтеся разом з Furby, який видає більш ніж 600 різних фраз та реакцій.
*	Світлові та танцювальні ефекти: Furby вміє танцювати, мигати очима та світитись різними кольорами.
*	Взаємодія з іншими Furby: Якщо у вас є два Furby, вони можуть взаємодіяти між собою. Кожен Furby продається окремо.
*	Спільні та носибельні аксесуари: Створюйте унікальні модні аксесуари для себе та Furby за допомогою намистин та гребінця, які входять до комплекту.
*	Подарунок для дітей: Furby висотою понад 15 см є чудовим подарунком для хлопчиків та дівчаток, який можна взяти з собою або використовувати для декору кімнати.

Комплектація:
*	Furby
*	13 намистин
*	Гребінець
*	Шнурок
*	Посібник з дружби

Додаткова інформація:
*	Рекомендовано для дітей віком від 6 років
*	Потребує 4 батарейки типу AA (не входять в комплект)
*	Іграшка не підключається до інтернету
*	Режими Tell My Fortune та інші є виключно розважальними
*	Лише поверхневе очищення

Відео:"""

    print("⏳ Перевожу текст...\n")

    translated_text = my_translator.translate(sample_text)

    print("✅ РЕЗУЛЬТАТ ПЕРЕВОДА:")
    print("-" * 50)
    print(translated_text)
    print("-" * 50)