import os
import re
import pandas as pd

# --- НАСТРОЙКИ (ИЗМЕНИТЕ ЭТИ ЗНАЧЕНИЯ) ---

# 1. Путь к вашему файлу Excel
EXCEL_FILE_PATH = r"C:\Users\ABM\Desktop\Лист Microsoft Excel (3).xlsx"

# 2. Путь к корневой папке с файлами для переименования
TARGET_DIRECTORY_PATH = r'\\10.10.100.2\Foto\Maisto _Copy\MAISTO'

# 3. Буквы столбцов в Excel
# Важно: используйте заглавные латинские буквы
ARTICLE_COLUMN = 1
SUB_ARTICLE_COLUMN = 2


# --- КОНЕЦ НАСТРОЕК ---


def sanitize_for_new_filename(text: str) -> str:
    """
    Полная очистка строки для нового имени файла.
    Заменяет все, что не является латинской буквой или цифрой, на дефис.
    Также убирает множественные дефисы.
    """
    if not isinstance(text, str):
        text = str(text)
    # Заменяем все не-буквенно-цифровые символы на дефис
    text = re.sub(r'[^a-zA-Z0-9]+', '-', text)
    # Убираем дефисы в начале или конце строки
    text = text.strip('-')
    return text


def contains_cyrillic(text: str) -> bool:
    """Проверяет, содержит ли строка кириллические символы."""
    if not isinstance(text, str):
        text = str(text)
    return bool(re.search('[а-яА-Я]', text))


def run_renamer():
    """Основная функция для выполнения переименования."""
    print("--- Запуск программы переименования файлов ---")

    # Проверка существования путей
    if not os.path.isfile(EXCEL_FILE_PATH):
        print(f"ОШИБКА: Файл Excel не найден по пути: {EXCEL_FILE_PATH}")
        return
    if not os.path.isdir(TARGET_DIRECTORY_PATH):
        print(f"ОШИБКА: Директория с файлами не найдена по пути: {TARGET_DIRECTORY_PATH}")
        return

    try:
        # Чтение только нужных столбцов из Excel
        df = pd.read_excel(EXCEL_FILE_PATH, usecols=[ARTICLE_COLUMN, SUB_ARTICLE_COLUMN], dtype=str)
        # Присваиваем колонкам стандартные имена для удобства
        df.columns = ['article', 'sub_article']
    except Exception as e:
        print(f"ОШИБКА: Не удалось прочитать файл Excel. Убедитесь, что путь и буквы столбцов верны. Детали: {e}")
        return

    processed_sub_articles = {}  # Словарь для отслеживания дубликатов

    print(f"Начинаю обход директории: {TARGET_DIRECTORY_PATH}")

    # Рекурсивно собираем все файлы .jpg
    all_jpg_files = []
    for root, _, files in os.walk(TARGET_DIRECTORY_PATH):
        for file in files:
            if file.lower().endswith('.jpg'):
                all_jpg_files.append(os.path.join(root, file))

    print(f"Найдено всего {len(all_jpg_files)} файлов .jpg для анализа.")

    # Итерация по строкам таблицы Excel
    for index, row in df.iterrows():
        article = row['article']
        sub_article = row['sub_article']

        # --- Проверки входных данных ---
        if pd.isna(article) or pd.isna(sub_article) or not str(sub_article).strip():
            continue  # Пропускаем строки с пустыми значениями

        if contains_cyrillic(article) or contains_cyrillic(sub_article):
            print(
                f"Строка {index + 2}: Артикул '{article}' или подартикул '{sub_article}' содержит кириллицу. Пропускаю.")
            continue

        # --- Поиск соответствующих файлов ---
        files_to_rename = []
        # Имя файла может быть точным совпадением или иметь суффикс _число
        # Создаем регулярное выражение для поиска
        # Экранируем спецсимволы в имени для корректной работы regex
        escaped_sub_article = re.escape(sub_article)
        pattern = re.compile(rf"^{escaped_sub_article}(_\d+)?\.jpg$", re.IGNORECASE)

        for file_path in all_jpg_files:
            file_name = os.path.basename(file_path)
            if pattern.match(file_name):
                files_to_rename.append(file_path)

        if not files_to_rename:
            continue  # Если файлы не найдены, идем дальше

        # --- Проверка на дубликаты подартикулов в Excel ---
        if sub_article in processed_sub_articles:
            print(
                f"ВНИМАНИЕ: Подартикул '{sub_article}' уже встречался в строке {processed_sub_articles[sub_article]}. "
                f"Пропускаю обработку строки {index + 2}, чтобы избежать конфликтов.")
            continue

        processed_sub_articles[sub_article] = index + 2

        # --- Формирование нового имени и запрос подтверждения ---
        sanitized_article = sanitize_for_new_filename(article)
        sanitized_sub_article = sanitize_for_new_filename(sub_article)
        new_base_name = f"{sanitized_article}-{sanitized_sub_article}"

        print("\n" + "=" * 50)
        print(f"Для подартикула: '{sub_article}' (строка {index + 2})")
        print(f"Найдено файлов для переименования: {len(files_to_rename)}")
        for f in files_to_rename:
            print(f" - {os.path.basename(f)}")
        print(f"Предлагаемый новый формат имени: {new_base_name}_[номер].jpg")

        user_input = input("Переименовать эти файлы? (1 - Да, 2 - Нет): ")

        if user_input.strip() == '1':
            renamed_count = 0
            for old_path in files_to_rename:
                try:
                    # Извлекаем суффикс (_1, _2 и т.д.)
                    old_name_no_ext = os.path.splitext(os.path.basename(old_path))[0]
                    suffix = old_name_no_ext.replace(sub_article, '')

                    new_filename = f"{new_base_name}{suffix}.jpg"
                    dir_path = os.path.dirname(old_path)
                    new_path = os.path.join(dir_path, new_filename)

                    # Проверка на случай, если файл с таким именем уже существует
                    if os.path.exists(new_path):
                        print(f"  ПРЕДУПРЕЖДЕНИЕ: Файл с именем {new_filename} уже существует. Пропускаю.")
                        continue

                    os.rename(old_path, new_path)
                    print(f"  УСПЕШНО: '{os.path.basename(old_path)}' -> '{new_filename}'")
                    renamed_count += 1
                except Exception as e:
                    print(f"  ОШИБКА при переименовании файла {os.path.basename(old_path)}: {e}")
            print(f"Переименовано {renamed_count} из {len(files_to_rename)} файлов.")
        else:
            print("Пропущено по команде пользователя.")
        print("=" * 50)

    print("\n--- Работа программы завершена ---")


if __name__ == '__main__':
    run_renamer()