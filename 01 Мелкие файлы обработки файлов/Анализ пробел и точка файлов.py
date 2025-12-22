import os
import re
import shutil
from collections import defaultdict

# --- НАСТРОЙКИ (ИЗМЕНИТЕ ЭТОТ ПУТЬ) ---

# Укажите путь к корневой папке с изображениями.
TARGET_DIRECTORY_PATH = r'\\10.10.100.2\Foto'

# Расширения файлов, которые считаются изображениями
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']


# --- КОНЕЦ НАСТРОЕК ---


def sanitize_base_name(name: str) -> str:
    """
    Очищает основную часть имени файла от нежелательных символов.
    """
    sanitized = re.sub(r'[^a-zA-Z0-9-]+', '-', name)
    sanitized = sanitized.strip('-')
    return sanitized


def create_sanitized_copies_interactive():
    """
    Интерактивно создает "чистые" копии файлов, группируя их по артикулу.
    """
    print("--- Запуск интерактивной программы создания 'чистых' копий ---")

    if not os.path.isdir(TARGET_DIRECTORY_PATH):
        print(f"ОШИБКА: Директория не найдена: {TARGET_DIRECTORY_PATH}")
        return

    # Шаг 1: Сбор всех "проблемных" групп файлов
    # Структура: { 'оригинальный_артикул': [список_полных_путей] }
    groups_to_process = defaultdict(list)
    print("Шаг 1: Сканирование директории и сбор кандидатов...")

    for root, _, files in os.walk(TARGET_DIRECTORY_PATH):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in IMAGE_EXTENSIONS:
                continue

            name_without_ext = os.path.splitext(filename)[0]

            # Разделяем на основную часть (артикул) и суффикс
            base_name = name_without_ext.split('_', 1)[0]

            # Проверяем, нуждается ли артикул в очистке
            sanitized_base = sanitize_base_name(base_name)
            if sanitized_base != base_name:
                groups_to_process[base_name].append(os.path.join(root, filename))

    if not groups_to_process:
        print("\nОтлично! Файлов, требующих исправления, не найдено.")
        return

    print(f"Найдено {len(groups_to_process)} уникальных артикулов, требующих обработки.")

    # Шаг 2: Фильтрация уже обработанных групп
    final_groups = {}
    for base_name, file_list in groups_to_process.items():
        first_file_path = file_list[0]
        # Проверяем на примере первого файла в группе
        name_without_ext, ext = os.path.splitext(os.path.basename(first_file_path))

        # Восстанавливаем суффикс
        parts = name_without_ext.split('_', 1)
        suffix = f"_{parts[1]}" if len(parts) > 1 else ""

        sanitized_base = sanitize_base_name(base_name)
        potential_new_name = f"{sanitized_base}{suffix}{ext}"
        potential_new_path = os.path.join(os.path.dirname(first_file_path), potential_new_name)

        if not os.path.exists(potential_new_path):
            final_groups[base_name] = file_list

    if not final_groups:
        print("\nВсе найденные кандидаты, похоже, уже были обработаны ранее. Завершаю работу.")
        return

    # Шаг 3: Интерактивная обработка оставшихся групп
    print("\nШаг 2: Подтверждение операций.")
    yes_to_all = False
    total_copies_created = 0

    for base_name, file_list in final_groups.items():
        sanitized_base = sanitize_base_name(base_name)

        user_choice = ''
        if not yes_to_all:
            print("\n" + "=" * 70)
            print(f"Найдена группа с артикулом: '{base_name}' ({len(file_list)} шт.)")
            print(f"Предлагаемое новое имя артикула: '{sanitized_base}'")
            print("Примеры файлов в группе:")
            for f_path in file_list[:3]:  # Показываем до 3 примеров
                print(f" - {os.path.basename(f_path)}")

            user_choice = input(
                "Создать исправленные копии для этой группы?\n"
                "(1 - Да, 2 - Нет, 3 - Да для всех оставшихся): "
            ).strip()

        if user_choice == '3':
            yes_to_all = True

        if user_choice == '1' or yes_to_all:
            print(f"Обрабатываю группу '{base_name}'...")
            copied_in_group = 0
            for old_path in file_list:
                try:
                    old_filename = os.path.basename(old_path)
                    name_without_ext, ext = os.path.splitext(old_filename)

                    parts = name_without_ext.split('_', 1)
                    suffix = f"_{parts[1]}" if len(parts) > 1 else ""

                    new_filename = f"{sanitized_base}{suffix}{ext}"
                    new_path = os.path.join(os.path.dirname(old_path), new_filename)

                    if os.path.exists(new_path):
                        print(f"  -> Пропущено: '{new_filename}' уже существует.")
                        continue

                    shutil.copy2(old_path, new_path)
                    print(f"  -> УСПЕХ: '{old_filename}' -> '{new_filename}'")
                    copied_in_group += 1
                except Exception as e:
                    print(f"  -> ОШИБКА при копировании '{old_filename}': {e}")
            if copied_in_group > 0:
                total_copies_created += copied_in_group
        elif user_choice == '2':
            print("Пропущено по команде пользователя.")
        else:
            if not yes_to_all:
                print("Неверный ввод. Группа пропущена.")

    print("\n" + "=" * 50)
    print("--- Работа программы завершена ---")
    print(f"Всего создано новых 'чистых' копий: {total_copies_created}")
    print("=" * 50)


if __name__ == '__main__':
    create_sanitized_copies_interactive()