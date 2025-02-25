import os
from PIL import Image
from natsort import natsorted


def process_images_without_rename(folder_path):
    # Получение списка файлов в папке и натуральная сортировка
    files = natsorted(os.listdir(folder_path))

    # Обработка и конвертация всех изображений в JPG с изменением размера
    for file in files:
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            try:
                with Image.open(file_path) as img:
                    # Определяем новое имя файла с расширением .jpg
                    new_filename = os.path.splitext(file)[0] + ".jpg"
                    new_file_path = os.path.join(folder_path, new_filename)

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

                    # Сохраняем как JPG (даже если исходный файл уже JPG)
                    img.save(new_file_path, "JPEG", quality=100, optimize=True)

                    # Удаляем исходный файл, если это не JPG
                    if not file.lower().endswith('.jpg'):
                        os.remove(file_path)
            except Exception as e:
                print(f"Не удалось обработать файл {file}: {e}")
                continue


# Пример использования
folder_path = r"C:\Users\ABM\Desktop\MM"  # Укажите путь к вашей папке
process_images_without_rename(folder_path)