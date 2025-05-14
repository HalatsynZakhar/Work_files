import os
import shutil
import re


def process_files(input_path, output_path):
    # Проверяем существование выходной папки, создаем если нет
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # Получаем список всех файлов в указанной папке
    files = [f for f in os.listdir(input_path) if os.path.isfile(os.path.join(input_path, f))]

    for file in files:
        # Получаем имя файла без расширения
        filename, extension = os.path.splitext(file)

        # Пропускаем файлы с нижним подчеркиванием в имени
        if '_' in filename:
            continue

        # Проверяем, начинается ли имя файла с нулей
        if filename.startswith('0'):
            # Удаляем все ведущие нули
            new_filename = re.sub('^0+', '', filename)

            # Если после удаления нулей имя пустое, значит файл назывался только нулями
            if not new_filename:
                new_filename = filename  # Оставляем хотя бы один ноль

            # Создаем полное имя нового файла с расширением
            new_file = new_filename + extension

            # Копируем файл в выходную папку с новым именем
            shutil.copy2(os.path.join(input_path, file), os.path.join(output_path, new_file))
            print(f"Скопирован файл: {file} -> {new_file}")


if __name__ == "__main__":
    input_path = r"C:\Users\ABM\Downloads\back_out"  # Путь к исходной папке
    output_path = r"C:\Users\ABM\Downloads\back"  # Путь к выходной папке

    process_files(input_path, output_path)