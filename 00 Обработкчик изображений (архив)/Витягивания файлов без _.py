import os
import shutil


def copy_files_without_underscore(input_path, output_path):
    # Проверяем существование выходной папки, создаем если нет
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # Получаем список всех файлов в указанной папке
    files = [f for f in os.listdir(input_path) if os.path.isfile(os.path.join(input_path, f))]

    for file in files:
        # Получаем имя файла без расширения
        filename, extension = os.path.splitext(file)

        # Копируем только файлы без нижнего подчеркивания в имени
        if '_' not in filename:
            # Копируем файл в выходную папку с тем же именем
            shutil.copy2(os.path.join(input_path, file), os.path.join(output_path, file))
            print(f"Скопирован файл: {file}")


if __name__ == "__main__":
    input_path = r"\\10.10.100.2\Foto\MACHINE MAKER"  # Путь к исходной папке
    output_path = r"C:\Users\ABM\Downloads\input\Новая папка (3)"  # Путь к выходной папке

    copy_files_without_underscore(input_path, output_path)