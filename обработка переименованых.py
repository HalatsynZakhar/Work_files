import os
import math
from PIL import Image, ImageChops
from natsort import natsorted

# --- Константи ---
# Допуск для білого і відсоток полів визначаються внизу, у налаштуваннях
# --- ---

# --- Функції обробки зображення ---
def remove_white_background(img, tolerance):
    """Видаляє майже білий фон з зображення RGBA."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    datas = img.getdata()
    newData = []
    cutoff = 255 - tolerance
    for item in datas:
        if item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff:
            newData.append((item[0], item[1], item[2], 0)) # Прозорий
        else:
            newData.append(item) # Зберігаємо
    img.putdata(newData)
    return img

def crop_transparent_border(img):
    """Обрізає прозорий простір навколо зображення (потребує RGBA)."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    try:
        alpha = img.split()[-1]
        bbox = alpha.getbbox()
    except (ValueError, IndexError):
        bbox = None
    if bbox:
        return img.crop(bbox)
    else:
        return img # Повертаємо як є, якщо не вдалося обрізати

def add_padding(img, percent):
    """Додає прозорі поля навколо RGBA зображення."""
    if img is None:
        return None
    if percent <= 0:
        return img

    width, height = img.size
    if width == 0 or height == 0:
        return img

    longest_side = max(width, height)
    padding_pixels = int(longest_side * (percent / 100.0))
    new_width = width + 2 * padding_pixels
    new_height = height + 2 * padding_pixels

    padded_img = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
    paste_x = padding_pixels
    paste_y = padding_pixels
    padded_img.paste(img, (paste_x, paste_y), img)
    return padded_img
# --- Кінець функцій обробки ---


def process_images_without_rename(folder_path, white_tolerance, padding_percent):
    print(f"Обробка папки: {folder_path}")
    print(f"Допуск для білого фону: {white_tolerance}")
    print(f"Поля навколо об'єкта: {padding_percent}%")

    try:
        # Фільтруємо одразу, щоб брати тільки файли
        files = natsorted([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])
        print(f"Знайдено файлів для обробки: {len(files)}")
    except FileNotFoundError:
        print(f"Помилка: Папку не знайдено - {folder_path}")
        return
    except Exception as e:
        print(f"Помилка при читанні вмісту папки {folder_path}: {e}")
        return

    processed_files_count = 0
    # Обробка і конвертація всіх зображень
    for file in files:
        file_path = os.path.join(folder_path, file)
        print(f"\nОбробка файлу: {file}")
        try:
            with Image.open(file_path) as img:
                original_mode = img.mode
                print(f"  - Початковий режим: {original_mode}, Розмір: {img.size}")

                # Визначаємо нове ім'я файлу (завжди .jpg)
                base_name = os.path.splitext(file)[0]
                new_filename = f"{base_name}.jpg"
                new_file_path = os.path.join(folder_path, new_filename)

                # --- Інтегрована обробка ---
                # 0. Завжди конвертуємо в RGBA
                img_rgba = img.convert("RGBA")

                # 1. Видалення білого фону
                print(f"  - Крок 1: Видалення білого фону (допуск {white_tolerance})...")
                img_no_bg = remove_white_background(img_rgba, white_tolerance)

                # 2. Обрізка прозорих країв
                print("  - Крок 2: Обрізка прозорих країв...")
                img_cropped = crop_transparent_border(img_no_bg)

                if img_cropped is None or not img_cropped.getbbox():
                    print("  ! Попередження: Зображення стало порожнім після видалення фону/обрізки. Пропуск.")
                    continue
                print(f"  - Розмір після обрізки: {img_cropped.size}")

                # 3. Додавання полів (Padding)
                print(f"  - Крок 3: Додавання полів ({padding_percent}%)...")
                img_padded = add_padding(img_cropped, padding_percent)
                if img_padded is None:
                     print("  ! Помилка при додаванні полів. Пропуск.")
                     continue
                print(f"  - Розмір після додавання полів: {img_padded.size}")

                # 4. Конвертація в RGB з білим фоном
                print("  - Крок 4: Конвертація в RGB (заміна прозорості на білий)...")
                final_rgb_img = Image.new("RGB", img_padded.size, (255, 255, 255))
                try:
                     if 'A' in img_padded.getbands():
                          mask = img_padded.split()[3]
                          final_rgb_img.paste(img_padded, (0, 0), mask)
                     else:
                          final_rgb_img.paste(img_padded, (0, 0))
                except IndexError:
                     print("  ! Помилка при отриманні альфа-каналу для paste. Спроба прямої конвертації.")
                     final_rgb_img = img_padded.convert("RGB")

                img = final_rgb_img # img тепер RGB з полями
                print(f"  - Розмір перед масштабуванням: {img.size}")

                # 5. Зміна розміру до 1500x1500 з центровкою
                print("  - Крок 5: Масштабування до 1500x1500 з центровкою...")
                target_size = 1500
                if img.size != (target_size, target_size):
                    original_width, original_height = img.size

                    if original_width == 0 or original_height == 0:
                        print("  ! Попередження: Розмір зображення нульовий. Пропуск масштабування.")
                        img_for_canvas = img
                        new_width, new_height = img.size
                    else:
                        ratio = min(target_size / original_width, target_size / original_height)
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)

                        if new_width > 0 and new_height > 0:
                            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            img_for_canvas = resized_img
                        else:
                             print(f"  ! Попередження: Новий розрахований розмір ({new_width}x{new_height}) некоректний.")
                             img_for_canvas = img
                             new_width, new_height = img.size

                    canvas = Image.new('RGB', (target_size, target_size), (255, 255, 255))
                    x = (target_size - new_width) // 2
                    y = (target_size - new_height) // 2
                    canvas.paste(img_for_canvas, (x, y))
                    img = canvas
                else:
                     print("  - Зображення вже має розмір 1500x1500.")

                # 6. Збереження як JPG
                print(f"  - Крок 6: Збереження як {new_filename}...")
                # Зберігаємо з якістю 95 для кращого балансу розмір/якість
                img.save(new_file_path, "JPEG", quality=95, optimize=True)
                processed_files_count += 1

                # 7. Видалення вихідного файлу, якщо це не був JPG з тим самим іменем
                # Перевіряємо, чи відрізняється оригінальний шлях від нового шляху
                # І чи оригінал не був JPG
                if file_path.lower() != new_file_path.lower() and not file.lower().endswith('.jpg'):
                    try:
                        print(f"  - Видалення оригінального файлу: {file}")
                        os.remove(file_path)
                    except Exception as remove_error:
                        print(f"  ! Помилка при видаленні {file}: {remove_error}")
                elif file_path.lower() == new_file_path.lower():
                    print("  - Оригінальний файл був JPG і був перезаписаний.")
                # Випадок, коли оригінал був НЕ jpg, але мав таке саме ім'я (без розширення)
                # як новий jpg файл - теж треба видалити оригінал
                elif file_path.lower() != new_file_path.lower() and file.lower().endswith('.jpg'):
                     # Це може статись, якщо регістр літер відрізнявся.
                     # Ми вже перезаписали файл, тому видаляти не треба.
                     print(f"  - Оригінальний файл {file} перезаписаний як {new_filename}.")
                     pass

        except Exception as e:
            print(f"!!! Помилка обробки файлу {file}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\nОбробка завершена. Успішно оброблено файлів: {processed_files_count}")

# --- Приклад використання ---
if __name__ == "__main__":
    try:
        import PIL
    except ImportError:
        print("Помилка: Бібліотека Pillow не знайдена.\nВстановіть її: pip install Pillow")
        exit()
    try:
        import natsort
    except ImportError:
        print("Помилка: Бібліотека natsort не знайдена.\nВстановіть її: pip install natsort")
        exit()

    # --- Налаштування користувача ---
    folder_to_process = r"\\10.10.100.2\Foto\ROAD RIPPERS"  # !!! ВАШ шлях до папки
    tolerance_for_white = 0              # !!! Допуск для білого (0-255)
    padding_percentage = 5                # !!! Відсоток полів (наприклад, 5 для 5%)
    # --- ---

    if not os.path.isdir(folder_to_process):
         print(f"Помилка: Вказана папка не існує або недоступна: {folder_to_process}")
         # Перевірка доступу до мережевого шляху може бути складнішою
         # Можна додати ping або спробу запису тестового файлу, якщо потрібно
    else:
         process_images_without_rename(
             folder_to_process,
             tolerance_for_white,
             padding_percentage
         )
         print("\nРобота скрипту завершена.")