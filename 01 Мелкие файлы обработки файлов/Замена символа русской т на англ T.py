import os
import shutil

# ==== Настройки ====
source_folder = r"C:\Users\ABM\Downloads\input"
target_folder = r"C:\Users\ABM\Downloads\input\Новая папка (3)"

# Русская 'Т' и английская 'T'
CYRILLIC_T = 'С'
LATIN_T = 'C'

def main():
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

    # Подсчет переименованных файлов
    renamed_count = 0

    # Обработка файлов
    for filename in os.listdir(source_folder):
        source_path = os.path.join(source_folder, filename)

        # Пропустить, если это не файл
        if not os.path.isfile(source_path):
            continue

        # Разделяем имя и расширение
        name, ext = os.path.splitext(filename)

        # Проверяем, есть ли русская 'Т'
        if CYRILLIC_T in name:
            new_name = name.replace(CYRILLIC_T, LATIN_T) + ext
            renamed_count += 1
        else:
            new_name = filename

        target_path = os.path.join(target_folder, new_name)

        # Копируем файл
        try:
            shutil.copy2(source_path, target_path)
            print(f"Скопировано: {filename} -> {new_name}")
        except Exception as e:
            print(f"Ошибка при копировании {filename}: {e}")

    print(f"\nОбработка завершена. Всего переименовано файлов: {renamed_count}")

if __name__ == '__main__':
    main()