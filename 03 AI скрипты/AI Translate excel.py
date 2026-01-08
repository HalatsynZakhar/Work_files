import openpyxl
from deep_translator import GoogleTranslator
import time
from pathlib import Path
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('translation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


class ExcelTranslator:
    def __init__(self, file_path, source_column, target_column, pause_seconds=2):
        """
        Инициализация переводчика Excel

        :param file_path: Путь к Excel файлу
        :param source_column: Буква столбца с исходным текстом (например, 'A')
        :param target_column: Буква столбца для результата (например, 'B')
        :param pause_seconds: Пауза между запросами (секунды)
        """
        self.file_path = Path(file_path)
        self.source_column = source_column.upper()
        self.target_column = target_column.upper()
        self.pause_seconds = pause_seconds
        self.translator = GoogleTranslator(source='uk', target='ru')

        if not self.file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

    def translate_text(self, text):
        """Перевод текста с повторными попытками при ошибках"""
        if not text or str(text).strip() == "":
            return ""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Ограничение длины для API
                text_str = str(text).strip()
                if len(text_str) > 4500:
                    # Разбиваем на части по предложениям
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

                    if current_chunk:
                        translated_parts.append(
                            self.translator.translate(current_chunk.strip())
                        )

                    return " ".join(translated_parts)
                else:
                    result = self.translator.translate(text_str)
                    return result

            except Exception as e:
                logging.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.pause_seconds * 2)
                else:
                    logging.error(f"Не удалось перевести текст после {max_retries} попыток")
                    return f"[ОШИБКА ПЕРЕВОДА: {text_str[:50]}...]"

        return ""

    def process_translation(self, start_row=2):
        """
        Основной процесс перевода

        :param start_row: Строка, с которой начать (по умолчанию 2, пропуская заголовок)
        """
        try:
            # Открываем файл
            workbook = openpyxl.load_workbook(self.file_path)
            sheet = workbook.active

            total_rows = sheet.max_row
            logging.info(f"Начинаем обработку файла: {self.file_path}")
            logging.info(f"Всего строк: {total_rows}")

            # Определяем с какой строки продолжить
            current_row = start_row
            for row in range(start_row, total_rows + 1):
                target_cell = f"{self.target_column}{row}"
                if sheet[target_cell].value is None or str(sheet[target_cell].value).strip() == "":
                    current_row = row
                    break
                current_row = row + 1

            if current_row > total_rows:
                logging.info("Все строки уже переведены!")
                return

            logging.info(f"Продолжаем с строки: {current_row}")

            # Обрабатываем каждую строку
            for row in range(current_row, total_rows + 1):
                source_cell = f"{self.source_column}{row}"
                target_cell = f"{self.target_column}{row}"

                source_text = sheet[source_cell].value

                # Пропускаем пустые ячейки
                if source_text is None or str(source_text).strip() == "":
                    logging.info(f"Строка {row}: пустая, пропускаем")
                    continue

                # Проверяем, не переведена ли уже
                if sheet[target_cell].value and str(sheet[target_cell].value).strip() != "":
                    logging.info(f"Строка {row}: уже переведена, пропускаем")
                    continue

                logging.info(f"Строка {row}/{total_rows}: переводим...")

                # Переводим
                translated = self.translate_text(source_text)

                # Сохраняем результат
                sheet[target_cell] = translated

                # Сохраняем файл после каждого перевода
                workbook.save(self.file_path)
                logging.info(f"Строка {row}: успешно переведена и сохранена")

                # Пауза между запросами
                if row < total_rows:
                    time.sleep(self.pause_seconds)

            logging.info("Перевод завершен успешно!")
            workbook.close()

        except KeyboardInterrupt:
            logging.info("Процесс прерван пользователем. Прогресс сохранен.")
            workbook.save(self.file_path)
            workbook.close()
        except Exception as e:
            logging.error(f"Критическая ошибка: {e}")
            raise


# ============= НАСТРОЙКИ =============
FILE_PATH = r"C:\Users\ABM\Desktop\Робота\57 Переклад описів\Переклад.xlsx"  # Путь к вашему Excel файлу
SOURCE_COLUMN = "C"  # Столбец с украинским текстом
TARGET_COLUMN = "D"  # Столбец для русского перевода
PAUSE_SECONDS = 2  # Пауза между запросами (секунды)
START_ROW = 2  # С какой строки начать (2 = пропускаем заголовок)

# ============= ЗАПУСК =============
if __name__ == "__main__":
    try:
        translator = ExcelTranslator(
            file_path=FILE_PATH,
            source_column=SOURCE_COLUMN,
            target_column=TARGET_COLUMN,
            pause_seconds=PAUSE_SECONDS
        )

        translator.process_translation(start_row=START_ROW)

    except Exception as e:
        logging.error(f"Ошибка выполнения: {e}")
        print(f"\nОшибка: {e}")