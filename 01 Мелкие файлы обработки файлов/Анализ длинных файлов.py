import os
from collections import defaultdict

# --- НАСТРОЙКИ (ИЗМЕНИТЕ ЭТОТ ПУТЬ) ---

# Укажите путь к корневой папке, которую нужно проанализировать.
# Скрипт проверит все вложенные папки.
TARGET_DIRECTORY_PATH = r'\\10.10.100.2\Foto'

# Порог длины имени (имена строго БОЛЬШЕ этого значения будут показаны)
LENGTH_THRESHOLD = 20


# --- КОНЕЦ НАСТРОЕК ---


def analyze_long_filenames_grouped():
    """
    Анализирует файлы, группирует результаты по основной части имени
    и выводит компактный отчет.
    """
    print("--- Запуск группирующего анализатора длины имен ---")

    if not os.path.isdir(TARGET_DIRECTORY_PATH):
        print(f"ОШИБКА: Директория не найдена по пути: {TARGET_DIRECTORY_PATH}")
        return

    # Словарь для сбора информации: { 'base_name': {'length': X, 'count': Y} }
    long_names_summary = defaultdict(lambda: {'length': 0, 'count': 0})

    print(f"Сканирую директорию: {TARGET_DIRECTORY_PATH}...")

    # Рекурсивный обход всех папок и файлов
    for root, _, files in os.walk(TARGET_DIRECTORY_PATH):
        for filename in files:
            name_without_ext = os.path.splitext(filename)[0]

            # Определяем "основную часть" имени
            base_name = name_without_ext.split('_', 1)[0]

            # Проверяем длину основной части имени
            if len(base_name) > LENGTH_THRESHOLD:
                # Накапливаем данные
                summary = long_names_summary[base_name]
                summary['length'] = len(base_name)
                summary['count'] += 1

    print("--- Анализ завершен ---")

    # Вывод результатов
    if not long_names_summary:
        print(f"\nОтлично! Артикулов с длиной имени более {LENGTH_THRESHOLD} символов не найдено.")
    else:
        print(
            f"\nВНИМАНИЕ! Найдено {len(long_names_summary)} уникальных артикулов с длиной имени более {LENGTH_THRESHOLD} символов:")
        print("-" * 80)

        # Преобразуем словарь в список для сортировки
        results_list = [
            {'base_name': name, 'length': details['length'], 'count': details['count']}
            for name, details in long_names_summary.items()
        ]

        # Сортируем по длине имени (от большего к меньшему)
        results_list.sort(key=lambda x: x['length'], reverse=True)

        # Выводим заголовок таблицы
        print(f"{'Длина':<7} | {'Файлов':<8} | {'Артикул'}")
        print(f"{'-' * 7} | {'-' * 8} | {'-' * 60}")

        for item in results_list:
            # :<7 - выравнивание по левому краю, 7 символов
            print(f"{item['length']:<7} | {item['count']:<8} | '{item['base_name']}'")

        print("-" * 80)
        print("Рекомендуется переименовать файлы с указанными артикулами.")


if __name__ == '__main__':
    analyze_long_filenames_grouped()