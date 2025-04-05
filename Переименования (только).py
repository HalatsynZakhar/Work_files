import os
from PIL import Image, UnidentifiedImageError
from natsort import natsorted


def rename_and_convert_images(folder_path, article_name):
    """
    Обрабатывает изображения в папке:
    1. Конвертирует все изображения в формат JPG.
    2. Обрабатывает прозрачность (заменяет белым фоном).
    3. Сохраняет изображения с оригинальными размерами (без изменения холста).
    4. Переименовывает файлы в формат article_name.jpg, article_name_1.jpg, ...
       с натуральной сортировкой исходных имен.
    """
    # Получение списка файлов в папке и натуральная сортировка
    try:
        files = natsorted(os.listdir(folder_path))
    except FileNotFoundError:
        print(f"Ошибка: Папка не найдена '{folder_path}'")
        return
    except Exception as e:
        print(f"Ошибка при чтении папки '{folder_path}': {e}")
        return

    print(f"Найдено файлов для обработки: {len(files)}")

    processed_files_count = 0
    # Обработка и конвертация всех изображений в JPG
    for file in files:
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            try:
                with Image.open(file_path) as img:
                    print(f"Обработка файла: {file} (Режим: {img.mode}, Размер: {img.size})")
                    img_to_save = img  # Используем копию или новую переменную для сохранения

                    # Конвертация в RGB и замена прозрачности
                    if img.mode in ('RGBA', 'LA'):
                        # Создаем новое изображение с белым фоном
                        new_img = Image.new("RGB", img.size, (255, 255, 255))
                        # Накладываем исходное изображение, используя альфа-канал как маску
                        mask = img.getchannel('A') if img.mode == 'RGBA' or img.mode == 'LA' else None
                        new_img.paste(img, (0, 0), mask=mask)
                        img_to_save = new_img
                        print(f"  > Конвертировано из {img.mode} в RGB с белым фоном.")
                    elif img.mode != 'RGB':
                        # Конвертируем другие режимы (например, P, L) в RGB
                        img_to_save = img.convert("RGB")
                        print(f"  > Конвертировано из {img.mode} в RGB.")
                    else:
                        # Если уже RGB, просто используем его
                        img_to_save = img
                        print(f"  > Файл уже в формате RGB.")

                    # --- Изменение размера и создание холста УДАЛЕНО ---
                    # Изображение 'img_to_save' теперь имеет оригинальные размеры после конвертации

                    # Сохранение как JPG
                    # Генерируем имя .jpg файла
                    base_name = os.path.splitext(file)[0]
                    new_file_name = base_name + ".jpg"
                    new_file_path = os.path.join(folder_path, new_file_name)

                    # Проверяем, не совпадает ли имя с исходным (если исходный был JPG)
                    is_original_jpg = file.lower().endswith('.jpg')
                    # Если имя совпадает И это был исходный JPG, не нужно пересохранять под тем же именем,
                    # но если режим изменился (например, P -> RGB), то нужно.
                    # Простой способ: всегда сохранять во временное имя, если есть риск перезаписи.
                    # Но для ясности, сначала сохраним, потом удалим оригинал (если не JPG).

                    img_to_save.save(new_file_path, "JPEG", quality=100, optimize=True)
                    print(f"  > Сохранено как: {new_file_name} (Качество: 100)")
                    processed_files_count += 1

                    # Удаление исходного файла, если это НЕ JPG или если он был конвертирован
                    # (т.е., если new_file_path отличается от file_path по расширению)
                    if not is_original_jpg:
                        try:
                            os.remove(file_path)
                            print(f"  > Удален исходный файл: {file}")
                        except OSError as e_del:
                            print(f"  > Не удалось удалить исходный файл {file}: {e_del}")

            except UnidentifiedImageError:
                print(f"Не удалось идентифицировать файл как изображение: {file}")
                continue
            except Exception as e:
                print(f"Не удалось обработать файл {file}: {e}")
                continue  # Переходим к следующему файлу

    print(f"\nКонвертация завершена. Обработано файлов: {processed_files_count}")

    # --- Переименование ---
    print("Начало переименования файлов...")
    # Обновление списка файлов ПОСЛЕ конвертации и натуральная сортировка
    try:
        # Фильтруем только .jpg файлы для переименования
        current_files = natsorted([f for f in os.listdir(folder_path) if
                                   f.lower().endswith('.jpg') and os.path.isfile(os.path.join(folder_path, f))])
    except Exception as e:
        print(f"Ошибка при получении списка JPG файлов для переименования: {e}")
        return

    # Проверяем, есть ли файлы после преобразования
    if not current_files:
        print("В папке нет JPG файлов для переименования.")
        return

    print(f"Найдено JPG файлов для переименования: {len(current_files)}")

    # Проверяем, есть ли файл с точным совпадением с article_name.jpg
    exact_match_target = f"{article_name}.jpg"
    exact_match_source_file = None

    # Ищем файл, который *должен* стать article_name.jpg
    # Обычно это первый файл в натурально отсортированном списке ИСХОДНЫХ имен.
    # Но после конвертации имена могли измениться. Пересортируем текущие JPG.
    # Если файл с именем article_name.jpg УЖЕ существует, он должен быть первым.
    if exact_match_target in current_files:
        exact_match_source_file = exact_match_target
        current_files.remove(exact_match_target)  # Убираем его из основного списка для переименования
        print(f"Найден файл '{exact_match_target}', он будет сохранен.")
    elif current_files:
        # Если точного совпадения нет, первый файл в списке станет им
        exact_match_source_file = current_files.pop(0)  # Берем первый и удаляем из списка
        print(f"Файл '{exact_match_source_file}' будет переименован в '{exact_match_target}'.")

    # Временные имена для ОСТАЛЬНЫХ файлов, чтобы избежать конфликтов
    temp_suffix = "_temp_rename_"
    temp_files_map = {}  # Словарь для отслеживания: временное имя -> оригинальное имя

    # Сначала переименуем все ОСТАВШИЕСЯ файлы во временные
    print("Переименование во временные имена...")
    for i, filename in enumerate(current_files):
        original_path = os.path.join(folder_path, filename)
        # Генерируем уникальное временное имя
        temp_filename = f"temp_{i}_{filename}{temp_suffix}.jpg"
        temp_path = os.path.join(folder_path, temp_filename)
        try:
            os.rename(original_path, temp_path)
            temp_files_map[temp_path] = filename  # Сохраняем связь
            # print(f"  '{filename}' -> '{temp_filename}'")
        except OSError as e:
            print(f"Ошибка переименования '{filename}' во временное имя: {e}")
            # Возможно, стоит прервать процесс или пропустить файл
            continue

    # Теперь присваиваем файлам правильные имена
    print("Присвоение финальных имен...")
    counter = 1

    # Переименовываем основной файл (если он был найден)
    if exact_match_source_file:
        source_path = os.path.join(folder_path, exact_match_source_file)
        target_path = os.path.join(folder_path, exact_match_target)
        if source_path != target_path:  # Переименовываем, только если имена отличаются
            try:
                os.rename(source_path, target_path)
                print(f"  '{exact_match_source_file}' -> '{exact_match_target}'")
            except OSError as e:
                print(
                    f"Ошибка переименования основного файла '{exact_match_source_file}' в '{exact_match_target}': {e}")
        else:
            print(f"  Основной файл '{exact_match_target}' уже имеет правильное имя.")

    # Переименовываем остальные файлы из временных имен
    # Сортируем временные пути по их исходным именам с помощью natsort, чтобы порядок сохранился
    sorted_temp_paths = natsorted(temp_files_map.keys(), key=lambda p: temp_files_map[p])

    for temp_path in sorted_temp_paths:
        original_filename = temp_files_map[temp_path]  # Получаем исходное имя для логгирования
        target_filename = f"{article_name}_{counter}.jpg"
        target_path = os.path.join(folder_path, target_filename)
        try:
            os.rename(temp_path, target_path)
            print(f"  '{os.path.basename(temp_path)}' (исходный: '{original_filename}') -> '{target_filename}'")
            counter += 1
        except OSError as e:
            print(f"Ошибка переименования временного файла '{os.path.basename(temp_path)}' в '{target_filename}': {e}")

    print("Переименование завершено.")


# --- Пример использования ---
folder_path = r"C:\Users\zakhar\Downloads\Test3"  # Укажите АБСОЛЮТНЫЙ путь к вашей папке
article_name = "20241"  # Укажите название артикула

# Проверка существования папки перед вызовом функции
if os.path.isdir(folder_path):
    rename_and_convert_images(folder_path, article_name)
else:
    print(f"Ошибка: Папка не найдена '{folder_path}'")