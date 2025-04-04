import os
import math
from PIL import Image, ImageChops
from natsort import natsorted

# --- Константи ---
# Допуск для білого тепер визначається тільки внизу, у налаштуваннях користувача
# Поля для обрізки не використовуються, обрізка до контуру об'єкта
PADDING_PERCENT = 5 # Відсоток для полів навколо об'єкта (від найдовшої сторони)
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
        return img # Якщо відсоток нульовий або менший, поля не додаємо

    width, height = img.size
    if width == 0 or height == 0:
        return img # Немає сенсу додавати поля до нульового розміру

    longest_side = max(width, height)
    padding_pixels = int(longest_side * (percent / 100.0))

    # Захист від занадто великих полів (можна налаштувати або прибрати)
    # Наприклад, максимальний розмір поля = розміру зображення
    # padding_pixels = min(padding_pixels, longest_side)

    new_width = width + 2 * padding_pixels
    new_height = height + 2 * padding_pixels

    # Створюємо новий прозорий холст більшого розміру
    padded_img = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))

    # Вставляємо оригінальне (обрізане) зображення у центр нового холста
    paste_x = padding_pixels
    paste_y = padding_pixels
    padded_img.paste(img, (paste_x, paste_y), img) # Використовуємо альфу як маску

    return padded_img
# --- Кінець функцій обробки ---


def rename_and_convert_images(folder_path, article_name, white_tolerance, padding_percent):
    print(f"Обробка папки: {folder_path}")
    print(f"Артикул для перейменування: {article_name}")
    print(f"Допуск для білого фону: {white_tolerance}")
    print(f"Поля навколо об'єкта: {padding_percent}%")

    try:
        files = natsorted([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])
        print(f"Знайдено файлів для обробки: {len(files)}")
    except FileNotFoundError:
        print(f"Помилка: Папку не знайдено - {folder_path}")
        return
    except Exception as e:
        print(f"Помилка при читанні вмісту папки {folder_path}: {e}")
        return

    processed_files_count = 0
    for file in files:
        file_path = os.path.join(folder_path, file)
        print(f"\nОбробка файлу: {file}")
        try:
            with Image.open(file_path) as img:
                original_mode = img.mode
                print(f"  - Початковий режим: {original_mode}, Розмір: {img.size}")

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
                if img_padded is None: # Додаткова перевірка
                     print("  ! Помилка при додаванні полів. Пропуск.")
                     continue
                print(f"  - Розмір після додавання полів: {img_padded.size}")

                # --- Тепер логіка з оригінального скрипту, застосована до img_padded ---

                # 4. Конвертація в RGB з білим фоном
                print("  - Крок 4: Конвертація в RGB (заміна прозорості на білий)...")
                # Розмір беремо від зображення з полями
                final_rgb_img = Image.new("RGB", img_padded.size, (255, 255, 255))
                try:
                     # Накладаємо зображення з полями (RGBA) на білий фон
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
                    original_width, original_height = img.size # Розміри RGB зображення з полями

                    if original_width == 0 or original_height == 0:
                        print("  ! Попередження: Розмір зображення нульовий. Пропуск масштабування.")
                        img_for_canvas = img
                        new_width, new_height = img.size
                    else:
                        # Масштабуємо, зберігаючи пропорції зображення з полями
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

                    # Створюємо фінальний білий холст 1500x1500
                    canvas = Image.new('RGB', (target_size, target_size), (255, 255, 255))
                    x = (target_size - new_width) // 2
                    y = (target_size - new_height) // 2
                    canvas.paste(img_for_canvas, (x, y))
                    img = canvas # img тепер фінальний 1500x1500
                else:
                     print("  - Зображення вже має розмір 1500x1500.")

                # 6. Збереження як JPG
                new_file_path = os.path.splitext(file_path)[0] + ".jpg"
                print(f"  - Крок 6: Збереження як {os.path.basename(new_file_path)}...")
                img.save(new_file_path, "JPEG", quality=95, optimize=True)
                processed_files_count += 1

                # 7. Видалення вихідного файлу
                if not file.lower().endswith('.jpg'):
                    try:
                        print(f"  - Видалення оригінального файлу: {file}")
                        os.remove(file_path)
                    except Exception as remove_error:
                        print(f"  ! Помилка при видаленні {file}: {remove_error}")
                elif file_path == new_file_path and file.lower().endswith('.jpg'):
                     print("  - Оригінальний файл JPG перезаписаний.")
                     pass

        except Exception as e:
            print(f"!!! Помилка обробки файлу {file}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\nПопередня обробка завершена. Оброблено файлів: {processed_files_count}")
    print("---")
    print("Перейменування файлів...")

    # Оновлюємо список файлів ТІЛЬКИ JPG після всіх перетворень
    try:
        current_files = natsorted([f for f in os.listdir(folder_path) if f.lower().endswith('.jpg') and os.path.isfile(os.path.join(folder_path, f))])
        print(f"Файлів для перейменування (JPG): {len(current_files)}")
    except Exception as e:
         print(f"Помилка при отриманні списку JPG файлів для перейменування: {e}")
         return

    if not current_files:
        print("Папка не містить JPG файлів після обробки. Перейменування неможливе.")
        return

    exact_match_filename = f"{article_name}.jpg"
    exact_match_temp_name = None
    files_to_rename = []
    temp_rename_map = {}

    print("  - Створення тимчасових імен...")
    temp_counter = 0
    for filename in current_files:
        original_path = os.path.join(folder_path, filename)
        temp_filename = f"__temp_{temp_counter}_{filename}"
        temp_path = os.path.join(folder_path, temp_filename)
        try:
            os.rename(original_path, temp_path)
            temp_rename_map[original_path] = temp_path
            if filename == exact_match_filename:
                exact_match_temp_name = temp_path
            else:
                files_to_rename.append(temp_path)
            temp_counter += 1
        except Exception as rename_error:
            print(f"  ! Помилка перейменування у тимчасове ім'я для {filename}: {rename_error}")

    print("  - Призначення фінальних імен...")
    final_rename_counter = 1

    if exact_match_temp_name:
        final_exact_path = os.path.join(folder_path, exact_match_filename)
        try:
            os.rename(exact_match_temp_name, final_exact_path)
            print(f"    - '{os.path.basename(exact_match_temp_name)}' -> '{exact_match_filename}'")
        except Exception as rename_error:
            print(f"  ! Помилка фінального перейменування для {exact_match_filename}: {rename_error}")
            files_to_rename.append(exact_match_temp_name) # Повертаємо для нумерації

    files_to_rename_sorted = natsorted(files_to_rename, key=lambda x: os.path.basename(x))

    for temp_path in files_to_rename_sorted:
        final_numbered_filename = f"{article_name}_{final_rename_counter}.jpg"
        final_numbered_path = os.path.join(folder_path, final_numbered_filename)
        try:
            os.rename(temp_path, final_numbered_path)
            print(f"    - '{os.path.basename(temp_path)}' -> '{final_numbered_filename}'")
            final_rename_counter += 1
        except Exception as rename_error:
             print(f"  ! Помилка фінального перейменування для {os.path.basename(temp_path)} -> {final_numbered_filename}: {rename_error}")

    print("Перейменування завершено.")


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
    folder_to_process = r"C:\Users\ABM\Desktop\MM"  # !!! ВАШ шлях до папки
    article = "Q9899-A23-1"               # !!! ВАШ артикул
    tolerance_for_white = 0              # !!! Допуск для білого (0-255)
    padding_percentage = 5                # !!! Відсоток полів (наприклад, 5 для 5%)
    # --- ---

    if not os.path.isdir(folder_to_process):
         print(f"Помилка: Вказана папка не існує: {folder_to_process}")
    else:
         rename_and_convert_images(
             folder_to_process,
             article,
             tolerance_for_white,
             padding_percentage # Передаємо новий параметр
         )
         print("\nРобота скрипту завершена.")