from deep_translator import GoogleTranslator
import time


class SmartTextTranslator:
    def __init__(self, source_lang='uk', target_lang='ru', pause_seconds=1):
        """
        Инициализация переводчика.
        :param source_lang: Исходный язык (по умолчанию украинский 'uk')
        :param target_lang: Целевой язык (по умолчанию русский 'ru')
        :param pause_seconds: Пауза между запросами (чтобы не заблокировал Google)
        """
        self.translator = GoogleTranslator(source=source_lang, target=target_lang)
        self.pause_seconds = pause_seconds

    def translate(self, text):
        """Перевод текста с разбиением длинных строк и повторными попытками."""
        if not text or str(text).strip() == "":
            return ""

        text_str = str(text).strip()
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Ограничение длины для API Google Translate (~5000 символов)
                # Берем с запасом - 4500
                if len(text_str) > 4500:
                    # Разбиваем длинный текст по предложениям
                    parts = text_str.split('. ')
                    translated_parts = []
                    current_chunk = ""

                    for part in parts:
                        if len(current_chunk) + len(part) < 4500:
                            current_chunk += part + ". "
                        else:
                            if current_chunk:
                                translated_parts.append(
                                    self.translator.translate(current_chunk.strip())
                                )
                                time.sleep(self.pause_seconds)
                            current_chunk = part + ". "

                    # Допереводим остаток
                    if current_chunk:
                        translated_parts.append(
                            self.translator.translate(current_chunk.strip())
                        )

                    return " ".join(translated_parts)

                else:
                    # Если текст короткий - переводим целиком
                    return self.translator.translate(text_str)

            except Exception as e:
                print(f"[Внимание] Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.pause_seconds * 2)  # Увеличиваем паузу перед повтором
                else:
                    print("[Ошибка] Не удалось перевести текст после всех попыток.")
                    return f"[ОШИБКА ПЕРЕВОДА: {text_str[:50]}...]"

        return ""


# ==========================================
# ТЕСТОВЫЙ КОД ДЛЯ ПРОВЕРКИ
# ==========================================
if __name__ == "__main__":
    # Создаем экземпляр переводчика (с украинского на русский)
    my_translator = SmartTextTranslator(source_lang='uk', target_lang='ru', pause_seconds=1)

    print("--- Тест 1: Обычный короткий текст ---")
    short_text = "Привіт, як твої справи? Це тестове повідомлення для перевірки роботи перекладача."
    print("Оригинал:", short_text)
    print("Перевод: ", my_translator.translate(short_text))
    print("-" * 40)

    print("--- Тест 2: Пустая строка (проверка на ошибку) ---")
    empty_text = "   "
    print("Перевод пустой строки:", f"'{my_translator.translate(empty_text)}'")
    print("-" * 40)

    print("--- Тест 3: Очень длинный текст (эмуляция > 4500 символов) ---")
    # Генерируем искусственно длинный текст (много предложений)
    long_sentence = "Це дуже довге речення, яке ми будемо повторювати багато разів. "
    long_text = long_sentence * 70  # Около 4500+ символов

    print(f"Длина оригинала: {len(long_text)} символов.")
    start_time = time.time()

    translated_long = my_translator.translate(long_text)

    print(f"Длина перевода: {len(translated_long)} символов.")
    print(f"Перевод завершен за {round(time.time() - start_time, 2)} сек.")
    print("Фрагмент начала перевода:", translated_long[:100], "...")