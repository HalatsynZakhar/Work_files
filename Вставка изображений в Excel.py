import openpyxl
from openpyxl.drawing.image import Image
from PIL import Image as PILImage  # Для работы с изображениями
import os

# Путь к папке с изображениями
folder_path = "C:/Users/ABM/Desktop/Image_1c/"

# Путь к существующему файлу Excel
file_path = "C:/Users/ABM/Desktop/Лист Microsoft Excel.xlsx"

# Выбор исходной ячейки (столбец с именами изображений)
input_column = 'B'  # Входной столбец с именами изображений

# Выбор целевой ячейки (столбец, куда будут вставляться изображения)
output_column = 'A'  # Столбец, в который вставляются изображения

# Попытка открыть файл
try:
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active  # Получаем активный лист
except FileNotFoundError:
    print(f"Файл {file_path} не найден. Создаю новый файл...")
    wb = openpyxl.Workbook()  # Создаём новый файл
    ws = wb.active

# Начинаем с первой строки
start_row = 2  # Начальная строка для обработки

# Обрабатываем все ячейки в исходной колонке (столбец B) начиная с указанной строки
for row in range(start_row, ws.max_row + 1):  # Обрабатываем все строки начиная с 2-й
    image_name = str(ws[f'{input_column}{row}'].value)  # Получаем имя изображения из исходной ячейки

    if image_name:  # Если имя изображения не пустое
        # Игорируем пробелы и регистр при сравнении имен
        image_name = image_name.strip().lower()  # Убираем пробелы и приводим к нижнему регистру
        image_path = os.path.join(folder_path, image_name + ".jpg")

        # Проверка существования изображения
        if os.path.exists(image_path):
            print(f"Изображение найдено: {image_path}")

            # Загружаем изображение с помощью Pillow для получения размеров
            pil_img = PILImage.open(image_path)
            img_width, img_height = pil_img.size  # Получаем ширину и высоту изображения

            # Создаем объект Image для добавления в Excel
            img = Image(image_path)

            # Получаем размеры целевой ячейки (например, столбец A)
            cell_width = ws.column_dimensions[output_column].width  # Получаем ширину целевого столбца
            cell_height = ws.row_dimensions[row].height  # Получаем высоту строки

            # Проверяем, что высота строки не равна None
            if cell_height is None:
                cell_height = 15  # Устанавливаем дефолтное значение, если высота не задана

            # Размеры ячейки в пикселях (коэффициенты для преобразования)
            cell_width_px = cell_width * 7  # Преобразуем ширину в пиксели (примерный коэффициент)
            cell_height_px = cell_height * 1.5  # Преобразуем высоту в пиксели (примерный коэффициент)

            # Сохраняем пропорции: подгоняем изображение, чтобы оно максимально вписалось в ячейку
            scale_factor = min(cell_width_px / img_width, cell_height_px / img_height)

            # Устанавливаем новые размеры изображения с сохранением пропорций
            img.width = int(img_width * scale_factor)
            img.height = int(img_height * scale_factor)

            # Привязываем изображение к ячейке
            img.anchor = f'{output_column}{row}'  # Размещение изображения в целевой ячейке

            # Центрируем изображение в ячейке
            img.left = (cell_width_px - img.width) / 2  # Центрируем по горизонтали
            img.top = (cell_height_px - img.height) / 2  # Центрируем по вертикали

            # Вставляем изображение в ячейку
            ws.add_image(img, f'{output_column}{row}')
        else:
            print(f"Изображение {image_name}.jpg не найдено по пути: {image_path}")
    else:
        print(f"В ячейке {input_column}{row} нет имени изображения.")

# Сохраняем файл Excel
wb.save(file_path)
print(f"Файл сохранен: {file_path}")
