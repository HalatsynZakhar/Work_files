import os
from PIL import Image
from natsort import natsorted


def rename_and_convert_images(folder_path, article_name):
    # Получение списка файлов в папке и натуральная сортировка
    files = natsorted(os.listdir(folder_path))

    # Обработка и конвертация всех изображений в JPG с изменением размера
    for file in files:
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            try:
                with Image.open(file_path) as img:
                    # Конвертация в RGB и замена прозрачности
                    if img.mode in ('RGBA', 'LA'):
                        new_img = Image.new("RGB", img.size, (255, 255, 255))
                        new_img.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else img.getchannel('A'))
                        img = new_img
                    elif img.mode != 'RGB':
                        img = img.convert("RGB")

                    # Изменение размера до 1500x1500
                    if img.size != (1500, 1500):
                        original_width, original_height = img.size
                        ratio = min(1500 / original_width, 1500 / original_height)
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)

                        resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                        canvas = Image.new('RGB', (1500, 1500), (255, 255, 255))
                        x = (1500 - new_width) // 2
                        y = (1500 - new_height) // 2
                        canvas.paste(resized_img, (x, y))
                        img = canvas

                    # Сохранение как JPG
                    new_file_path = os.path.splitext(file_path)[0] + ".jpg"
                    img.save(new_file_path, "JPEG", quality=100, optimize=True)

                    # Удаление исходного файла, если это не JPG
                    if not file.lower().endswith('.jpg'):
                        os.remove(file_path)
            except Exception as e:
                print(f"Не удалось обработать файл {file}: {e}")
                continue

    # Обновление списка файлов после конвертации и натуральная сортировка
    files = natsorted(os.listdir(folder_path))

    # Проверяем, есть ли файлы после преобразования
    if not files:
        print("Папка пуста после преобразования. Нет файлов для обработки.")
        return

    # Проверяем, есть ли файл с точным совпадением с article_name
    exact_match_file = f"{article_name}.jpg"
    if exact_match_file in files:
        files.remove(exact_match_file)
        exact_match_path = os.path.join(folder_path, exact_match_file)
    else:
        exact_match_path = None

    # Временные имена для файлов, чтобы избежать конфликтов
    temp_suffix = "_temp"
    temp_files = []

    # Сначала переименуем все файлы с конфликтными именами во временные
    for i, file in enumerate(files):
        file_path = os.path.join(folder_path, file)
        temp_file_path = os.path.join(folder_path, f"temp_{i}{temp_suffix}.jpg")
        os.rename(file_path, temp_file_path)
        temp_files.append(temp_file_path)

    # Теперь присваиваем файлам правильные имена
    counter = 1

    # Если есть точное совпадение, оставляем его с правильным именем
    if exact_match_path:
        new_file_path = os.path.join(folder_path, f"{article_name}.jpg")
        os.rename(exact_match_path, new_file_path)

    for temp_file_path in temp_files:
        new_file_path = os.path.join(folder_path, f"{article_name}_{counter}.jpg")
        os.rename(temp_file_path, new_file_path)
        counter += 1


# Пример использования
folder_path = r"C:\Users\ABM\Desktop\MM"  # Укажите путь к вашей папке
article_name = "20241"  # Укажите название артикула
rename_and_convert_images(folder_path, article_name)