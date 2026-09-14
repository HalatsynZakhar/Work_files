#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт многопоточной рекурсивной обработки и стандартизации изображений под интернет-магазины:
- Настройка путей и всех параметров задается прямо в начале кода.
- Перед запуском выводит подробный план и ожидает подтверждения пользователя.
- Рекурсивный обход папок с сохранением структуры каталогов.
- Опция приведения к квадратному холсту (без потери данных, центрирование на белом фоне).
- Опция ограничения максимального разрешения (макс. ширина и высота).
- Опция автоматического исправления цветового профиля в стандартный sRGB (IEC 61966-2.1).
- Опция замены прозрачности на чисто белые пиксели (255, 255, 255).
- Сохранение в Progressive JPEG высокого качества.
- Высокая скорость работы за счет многопоточности (ThreadPoolExecutor).
"""

import os
import sys
import io
import time
import shutil
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageCms

# Обеспечиваем корректный вывод UTF-8 в консоли Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ==============================================================================
# ⚙️ НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ (ИЗМЕНЯЙТЕ ПАРАМЕТРЫ ЗДЕСЬ)
# ==============================================================================

# 📂 ПУТИ К ПАПКАМ
# Вставьте пути между кавычками r"..." (буква r перед кавычками обязательна для Windows)
INPUT_DIR = r"\\10.10.100.2\k\Таран Ю\Обробка зображень\Вхідні зображення"    # Путь к исходной папке с изображениями (например, r"C:\Users\ABM\Desktop\Foto")
OUTPUT_DIR = r"\\10.10.100.2\k\Таран Ю\Обробка зображень\Результат"   # Путь к выходной папке для готовых файлов (например, r"C:\Users\ABM\Desktop\Foto_Ready")


# 🔲 1. ПРЕОБРАЗОВАНИЕ НА КВАДРАТНЫЙ ФОН
# Помещает изображение по центру квадратного холста (по длинной стороне) без обрезки
MAKE_SQUARE_ENABLED = True
SQUARE_BG_COLOR = (255, 255, 255)  # Цвет полей холста (R, G, B), по умолчанию белый


# 📏 2. ОГРАНИЧЕНИЕ МАКСИМАЛЬНОГО РАЗРЕШЕНИЯ (ШИРИНА И ВЫСОТА)
# Пропорционально уменьшает изображения, если их размер превышает указанные лимиты
MAX_RESOLUTION_ENABLED = False
MAX_WIDTH = 1500                   # Максимальная ширина в пикселях
MAX_HEIGHT = 1500                  # Максимальная высота в пикселях


# 🎨 3. ИСПРАВЛЕНИЕ ЦВЕТОВОГО ПРОФИЛЯ В sRGB
# Автоматически конвертирует CMYK, Adobe RGB, Display P3 в стандартный sRGB для веба
CONVERT_TO_SRGB_ENABLED = True


# ⚪ 4. ЗАМЕНА ПРОЗРАЧНОСТИ НА БЕЛЫЙ ЦВЕТ
# Заменяет прозрачные области PNG/альфа-канала на чисто белые пиксели (255, 255, 255)
REPLACE_TRANSPARENCY_ENABLED = True
TRANSPARENCY_BG_COLOR = (255, 255, 255)  # Цвет фона для прозрачности


# ⚡ 5. ПАРАМЕТРЫ СОХРАНЕНИЯ JPEG ДЛЯ ИНТЕРНЕТ-МАГАЗИНА
JPEG_QUALITY = 95                  # Качество сохранения (1-100), 95 - стандарт e-commerce
PROGRESSIVE_JPEG = True            # True: прогрессивный JPEG (быстрая плавная прогрузка на сайте)
SUBSAMPLING_444 = True             # True: отключить субдискретизацию (максимальная четкость текста/деталей)
DPI = (72, 72)                     # Разрешение экрана для веба (DPI)


# 🧵 6. МНОГОПОТОЧНОСТЬ
# Количество параллельных потоков (None = автоматически по количеству ядер процессора)
MAX_WORKERS = None

# ==============================================================================


# Поддерживаемые расширения файлов
JPG_EXTENSIONS = {'.jpg', '.jpeg'}
CONVERT_EXTENSIONS = {'.png', '.webp', '.bmp', '.tiff', '.tif'}
ALL_SUPPORTED_EXTENSIONS = JPG_EXTENSIONS | CONVERT_EXTENSIONS

# Инициализация эталонного профиля sRGB
SRGB_PROFILE = ImageCms.createProfile('sRGB')
SRGB_PROFILE_BYTES = ImageCms.ImageCmsProfile(SRGB_PROFILE).tobytes()


def is_srgb_profile(profile: ImageCms.ImageCmsProfile) -> bool:
    """Проверяет, является ли профиль уже стандартным sRGB."""
    try:
        desc = (ImageCms.getProfileDescription(profile) or "").lower()
        model = (ImageCms.getProfileModel(profile) or "").lower()
        name = (ImageCms.getProfileName(profile) or "").lower()
        combined = f"{desc} {model} {name}"
        return any(sig in combined for sig in ['srgb', 'iec61966-2.1', 'iec 61966-2.1'])
    except Exception:
        return False


def standardize_image_for_web(
    img: Image.Image,
    convert_srgb: bool = CONVERT_TO_SRGB_ENABLED,
    replace_transparency: bool = REPLACE_TRANSPARENCY_ENABLED,
    transparency_bg: tuple = TRANSPARENCY_BG_COLOR,
    make_square: bool = MAKE_SQUARE_ENABLED,
    square_bg: tuple = SQUARE_BG_COLOR,
    max_res_enabled: bool = MAX_RESOLUTION_ENABLED,
    max_w: int = MAX_WIDTH,
    max_h: int = MAX_HEIGHT
) -> tuple[Image.Image, list[str]]:
    """
    Приводит изображение к заданным настройкам интернет-магазина.
    Возвращает обработанное изображение RGB и список выполненных действий.
    """
    fixes = []

    # 1. Исправление цветового пространства в стандартный sRGB
    if convert_srgb:
        icc_bytes = img.info.get('icc_profile')
        color_converted = False

        if icc_bytes:
            try:
                in_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
                profile_name = ImageCms.getProfileDescription(in_profile) or "ICC"
                if not is_srgb_profile(in_profile) or img.mode == 'CMYK':
                    output_mode = 'RGBA' if img.mode in ('RGBA', 'LA', 'PA') else 'RGB'
                    img = ImageCms.profileToProfile(
                        img,
                        in_profile,
                        SRGB_PROFILE,
                        outputMode=output_mode
                    )
                    fixes.append(f"цветовой профиль '{profile_name}' -> sRGB")
                    color_converted = True
            except Exception as e:
                fixes.append(f"ошибка конвертации профиля ICC ({e})")

        if img.mode == 'CMYK' and not color_converted:
            img = img.convert('RGB')
            fixes.append("CMYK без профиля -> RGB sRGB")
            color_converted = True

    # 2. Обработка прозрачности
    rgba_img = img.convert('RGBA')
    alpha = rgba_img.split()[3]
    min_alpha, max_alpha = alpha.getextrema()

    if replace_transparency and min_alpha < 255:
        background = Image.new('RGB', rgba_img.size, transparency_bg)
        background.paste(rgba_img, mask=alpha)
        rgb_img = background
        fixes.append(f"прозрачный фон -> белые пиксели RGB{transparency_bg}")
    else:
        rgb_img = rgba_img.convert('RGB')

    # 3. Преобразование на квадратный холст (без обрезки, по центру)
    w, h = rgb_img.size
    if make_square and w != h:
        sq_size = max(w, h)
        square_canvas = Image.new('RGB', (sq_size, sq_size), square_bg)
        x_offset = (sq_size - w) // 2
        y_offset = (sq_size - h) // 2
        square_canvas.paste(rgb_img, (x_offset, y_offset))
        rgb_img = square_canvas
        fixes.append(f"квадратный холст ({w}x{h} -> {sq_size}x{sq_size})")
        w, h = sq_size, sq_size

    # 4. Ограничение максимального разрешения (ширина и высота)
    if max_res_enabled and (w > max_w or h > max_h):
        orig_w, orig_h = w, h
        scale = min(max_w / w, max_h / h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        rgb_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        fixes.append(f"макс. размер ({orig_w}x{orig_h} -> {new_w}x{new_h})")

    return rgb_img, fixes


def save_as_ecommerce_jpeg(
    img: Image.Image,
    dst_path: Path,
    quality: int = JPEG_QUALITY,
    progressive: bool = PROGRESSIVE_JPEG,
    subsampling_444: bool = SUBSAMPLING_444,
    dpi: tuple = DPI,
    embed_srgb: bool = CONVERT_TO_SRGB_ENABLED
) -> bool:
    """
    Сохраняет изображение в формате JPEG с веб-настройками.
    """
    try:
        save_kwargs = {
            'format': 'JPEG',
            'quality': quality,
            'subsampling': 0 if subsampling_444 else -1,
            'optimize': True,
            'progressive': progressive,
            'dpi': dpi,
        }
        if embed_srgb:
            save_kwargs['icc_profile'] = SRGB_PROFILE_BYTES

        img.save(dst_path, **save_kwargs)
        return True
    except Exception as e:
        print(f"[ОШИБКА] Не удалось сохранить файл '{dst_path.name}': {e}")
        return False


def process_single_file(
    task: tuple[Path, Path, Path, str],
    settings: dict
) -> tuple[bool, str, str, str]:
    """
    Обрабатывает один файл изображения в отдельном потоке.
    """
    src_file, dst_file, rel_file_path, ext = task
    display_rel = rel_file_path.as_posix()

    try:
        with Image.open(src_file) as img:
            std_img, fixes = standardize_image_for_web(
                img,
                convert_srgb=settings['convert_srgb'],
                replace_transparency=settings['replace_transparency'],
                transparency_bg=settings['transparency_bg'],
                make_square=settings['make_square'],
                square_bg=settings['square_bg'],
                max_res_enabled=settings['max_res_enabled'],
                max_w=settings['max_w'],
                max_h=settings['max_h']
            )

            success = save_as_ecommerce_jpeg(
                std_img,
                dst_file,
                quality=settings['quality'],
                progressive=settings['progressive'],
                subsampling_444=settings['subsampling_444'],
                dpi=settings['dpi'],
                embed_srgb=settings['convert_srgb']
            )

            if success:
                fixes_str = f" [{', '.join(fixes)}]" if fixes else " [готово]"

                if ext in JPG_EXTENSIONS:
                    category = 'jpg_processed'
                    tag = '[JPG -> СТАНДАРТ]'
                elif ext == '.png':
                    category = 'png_converted'
                    tag = '[PNG -> JPG]     '
                else:
                    category = 'other_converted'
                    tag = f'[{ext.upper()} -> JPG]     '

                return True, category, display_rel, f"{tag} {display_rel}{fixes_str}"
            else:
                return False, 'errors', display_rel, f"[ОШИБКА] Не удалось сохранить '{display_rel}'"

    except Exception as e:
        return False, 'errors', display_rel, f"[ОШИБКА] Ошибка при обработке '{display_rel}': {e}"


def display_plan_and_confirm(
    input_path: Path,
    output_path: Path,
    settings: dict,
    total_images: int
) -> bool:
    """
    Выводит понятный и подробный план обработки перед началом работы
    и ожидает подтверждения пользователя.
    """
    square_status = f"ВКЛ (по длинной стороне, фон RGB{settings['square_bg']})" if settings['make_square'] else "ВЫКЛ"
    max_res_status = f"ВКЛ (макс. {settings['max_w']} x {settings['max_h']} px, пропорционально)" if settings['max_res_enabled'] else "ВЫКЛ"
    srgb_status = "ВКЛ (преобразование CMYK/AdobeRGB/P3 в sRGB IEC 61966-2.1)" if settings['convert_srgb'] else "ВЫКЛ"
    transp_status = f"ВКЛ (замена на белые пиксели RGB{settings['transparency_bg']})" if settings['replace_transparency'] else "ВЫКЛ"
    subsampling_str = "4:4:4 (макс. четкость)" if settings['subsampling_444'] else "стандартная (4:2:0)"
    progressive_str = "ВКЛ" if settings['progressive'] else "ВЫКЛ"

    print("\n" + "=" * 80)
    print("📋 ПЛАН ОБРАБОТКИ И СТАНДАРТИЗАЦИИ ИЗОБРАЖЕНИЙ ПОД ИНТЕРНЕТ-МАГАЗИН")
    print("=" * 80)
    print("ℹ️  Все параметры настраиваются в начале файла скрипта в блоке 'НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ'.\n")
    print(f"  📂 Исходная папка:      {input_path}")
    print(f"  📁 Выходная папка:     {output_path}")
    print(f"  🖼️  Найдено картинок:   {total_images}")
    print(f"  🧵 Потоков (workers):   {settings['max_workers']}")
    print("\nПараметры обработки:")
    print(f"  🔲 Квадратный фон:      {square_status}")
    print(f"  📏 Ограничение размера: {max_res_status}")
    print(f"  🎨 Цветовой профиль:    {srgb_status}")
    print(f"  ⚪ Прозрачность PNG:    {transp_status}")
    print(f"  ⚡ Формат сохранения:   JPEG (Качество: {settings['quality']}, Прогрессивный: {progressive_str}, Субдискретизация: {subsampling_str}, DPI: {settings['dpi'][0]})")
    print("=" * 80)

    try:
        user_choice = input("\n👉 Нажмите Enter для запуска обработки (или введите 'q' для отмены): ").strip().lower()
        if user_choice in ('q', 'quit', 'n', 'no', 'отмена', 'нет'):
            print("\n❌ Операция отменена пользователем.")
            return False
        return True
    except (KeyboardInterrupt, EOFError):
        print("\n\n❌ Операция прервана.")
        return False


def process_images(
    input_dir: str | Path,
    output_dir: str | Path,
    settings: dict,
    auto_confirm: bool = False
):
    """
    Основная процедура многопоточного обхода и обработки изображений.
    """
    start_time = time.time()
    input_path = Path(input_dir).resolve()
    output_path = Path(output_dir).resolve()

    if not input_path.exists():
        print(f"[ОШИБКА] Входная папка не существует: {input_path}")
        return

    if not input_path.is_dir():
        print(f"[ОШИБКА] Входной путь не является папкой: {input_path}")
        return

    # Сканируем папки и собираем задачи
    tasks = []
    skipped_count = 0
    dirs_created = 0

    print("🔍 Сканирование папок...")
    for root, dirs, files in os.walk(input_path):
        current_root = Path(root)
        rel_dir = current_root.relative_to(input_path)
        current_target_dir = output_path / rel_dir

        if not current_target_dir.exists():
            current_target_dir.mkdir(parents=True, exist_ok=True)
            dirs_created += 1

        for dir_name in dirs:
            sub_target_dir = current_target_dir / dir_name
            if not sub_target_dir.exists():
                sub_target_dir.mkdir(parents=True, exist_ok=True)
                dirs_created += 1

        for file_name in files:
            src_file = current_root / file_name
            ext = src_file.suffix.lower()

            if ext not in ALL_SUPPORTED_EXTENSIONS:
                skipped_count += 1
                continue

            dst_file = current_target_dir / f"{src_file.stem}.jpg"
            rel_file_path = rel_dir / src_file.name
            tasks.append((src_file, dst_file, rel_file_path, ext))

    total_tasks = len(tasks)

    # Выводим план и запрашиваем подтверждение
    if not auto_confirm:
        confirmed = display_plan_and_confirm(input_path, output_path, settings, total_tasks)
        if not confirmed:
            return

    if total_tasks == 0:
        print("⚠️ Изображений для обработки не найдено.")
        return

    print("\n" + "=" * 80)
    print(f"🚀 Запуск многопоточной обработки ({settings['max_workers']} потоков)...")
    print("=" * 80)

    stats = {
        'jpg_processed': 0,
        'png_converted': 0,
        'other_converted': 0,
        'skipped': skipped_count,
        'errors': 0,
        'directories_created': dirs_created
    }

    print_lock = threading.Lock()
    processed_count = 0

    with ThreadPoolExecutor(max_workers=settings['max_workers']) as executor:
        futures = {
            executor.submit(process_single_file, task, settings): task
            for task in tasks
        }

        for future in as_completed(futures):
            success, category, display_rel, message = future.result()
            with print_lock:
                processed_count += 1
                stats[category] += 1
                progress_tag = f"[{processed_count}/{total_tasks}]"
                print(f"{progress_tag} {message}")

    elapsed_time = time.time() - start_time

    print("\n" + "=" * 80)
    print("✨ Обработка успешно завершена!")
    print(f"   ⏱️ Время выполнения:          {elapsed_time:.2f} сек.")
    print(f"   📋 Обработано/исправлено JPG: {stats['jpg_processed']}")
    print(f"   🔄 Сконвертировано из PNG:    {stats['png_converted']}")
    if stats['other_converted'] > 0:
        print(f"   🖼️ Сконвертировано других:    {stats['other_converted']}")
    print(f"   ⏭️ Пропущено не-изображений:  {stats['skipped']}")
    print(f"   📁 Создано папок:             {stats['directories_created']}")
    if stats['errors'] > 0:
        print(f"   ⚠️ Ошибок при обработке:      {stats['errors']}")
    print("=" * 80)


def prompt_folder_path(prompt_text: str, default_value: str = "") -> str:
    """
    Запрашивает у пользователя путь к папке в консоли,
    очищает от случайных кавычек и пробелов.
    """
    if default_value:
        prompt_text = f"{prompt_text} [по умолчанию: {default_value}]: "
    else:
        prompt_text = f"{prompt_text}: "

    user_input = input(prompt_text).strip()
    user_input = user_input.strip('"\'')

    if not user_input and default_value:
        return default_value
    return user_input


def main():
    parser = argparse.ArgumentParser(
        description="Многопоточный конвертер и стандартизатор изображений под интернет-магазины.",
        epilog="Параметры настраиваются в начале файла скрипта, но могут быть переопределены через аргументы командной строки.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-i', '--input', help='Путь к исходной папке с изображениями')
    parser.add_argument('-o', '--output', help='Путь к выходной папке')
    parser.add_argument('-q', '--quality', type=int, default=None,
                        help=f'Качество сохранения JPEG (по умолчанию {JPEG_QUALITY})')
    parser.add_argument('-w', '--workers', type=int, default=None,
                        help='Количество параллельных потоков')
    parser.add_argument('--square', dest='square', action='store_true', help='Включить квадратный фон')
    parser.add_argument('--no-square', dest='square', action='store_false', help='Выключить квадратный фон')
    parser.set_defaults(square=None)
    parser.add_argument('-y', '--yes', action='store_true', help='Автоматическое подтверждение запуска без паузы')

    args = parser.parse_args()

    # Считываем пути: сначала из аргументов, затем из настроек в начале файла
    input_dir = args.input or INPUT_DIR
    output_dir = args.output or OUTPUT_DIR

    # Если пути не заданы ни в коде, ни через аргументы — запрашиваем в консоли
    if not input_dir:
        print("💡 Путь к исходной папке не указан в начале файла (INPUT_DIR).")
        input_dir = prompt_folder_path("Введите путь к папке с изображениями")

    while not input_dir or not os.path.exists(input_dir):
        print(f"[!] Папка не найдена: '{input_dir}'. Пожалуйста, проверьте путь.")
        input_dir = prompt_folder_path("Введите корректный путь к исходной папке")

    if not output_dir:
        print("💡 Путь к выходной папке не указан в начале файла (OUTPUT_DIR).")
        output_dir = prompt_folder_path("Введите путь к выходной папке")
        while not output_dir:
            output_dir = prompt_folder_path("Путь к выходной папке не может быть пустым. Введите путь")

    # Формируем словарь активных настроек
    active_settings = {
        'make_square': MAKE_SQUARE_ENABLED if args.square is None else args.square,
        'square_bg': SQUARE_BG_COLOR,
        'max_res_enabled': MAX_RESOLUTION_ENABLED,
        'max_w': MAX_WIDTH,
        'max_h': MAX_HEIGHT,
        'convert_srgb': CONVERT_TO_SRGB_ENABLED,
        'replace_transparency': REPLACE_TRANSPARENCY_ENABLED,
        'transparency_bg': TRANSPARENCY_BG_COLOR,
        'quality': args.quality if args.quality is not None else JPEG_QUALITY,
        'progressive': PROGRESSIVE_JPEG,
        'subsampling_444': SUBSAMPLING_444,
        'dpi': DPI,
        'max_workers': args.workers or MAX_WORKERS or os.cpu_count() or 4
    }

    process_images(input_dir, output_dir, active_settings, auto_confirm=args.yes)


if __name__ == '__main__':
    main()
