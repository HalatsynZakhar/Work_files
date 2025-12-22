import os
from PIL import Image

# Поддерживаемые расширения изображений
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}

# Укажите пути здесь ↓↓↓
source_folder = r"\\10.10.100.2\Foto\LUKKY"
target_folder = r"C:\Users\ABM\Downloads\test"


def is_image_square(image_path):
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            return width == height
    except Exception as e:
        print(f"Ошибка при обработке файла {image_path}: {e}")
        return True  # Пропускаем поврежденные файлы


def main():
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

    for filename in os.listdir(source_folder):
        file_path = os.path.join(source_folder, filename)

        # Проверяем, является ли файл изображением
        name, ext = os.path.splitext(filename.lower())
        if ext not in IMAGE_EXTENSIONS:
            continue

        # Проверяем, есть ли символ '_' в имени файла
        if '_' in filename:
            continue

        # Проверяем соотношение сторон
        if not is_image_square(file_path):
            target_path = os.path.join(target_folder, filename)
            try:
                import shutil
                shutil.copy(file_path, target_path)
                print(f"Скопировано: {filename}")
            except Exception as e:
                print(f"Не удалось скопировать {filename}: {e}")

    print("Обработка завершена.")


if __name__ == '__main__':
    main()