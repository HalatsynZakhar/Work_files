#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path
from PIL import Image, ImageOps
import argparse


def make_image_square(image_path, background_color=(255, 255, 255)):
    """
    Преобразует изображение в квадратное, добавляя фон по длинной стороне

    Args:
        image_path (Path): Путь к изображению
        background_color (tuple): Цвет фона (R, G, B)

    Returns:
        bool: True если успешно, False если ошибка
    """
    try:
        # Открываем изображение
        with Image.open(image_path) as img:
            # Конвертируем в RGB если нужно (для PNG с прозрачностью)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Создаем белый фон для прозрачных изображений
                rgb_img = Image.new('RGB', img.size, background_color)
                if img.mode == 'P':
                    img = img.convert('RGBA')
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = rgb_img
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            width, height = img.size

            # Проверяем, является ли изображение уже квадратным
            if width == height:
                print(f"⏭️  Пропущен: '{image_path.name}' (уже квадратное {width}x{height})")
                return True

            # Определяем размер квадрата (по длинной стороне)
            square_size = max(width, height)

            # Создаем квадратный холст с фоном
            square_img = Image.new('RGB', (square_size, square_size), background_color)

            # Вычисляем позицию для центрирования изображения
            x_offset = (square_size - width) // 2
            y_offset = (square_size - height) // 2

            # Вставляем изображение в центр квадратного холста
            square_img.paste(img, (x_offset, y_offset))

            # Сохраняем с тем же именем (заменяем оригинал)
            square_img.save(image_path, quality=95, optimize=True)

            print(f"✅ Обработан: '{image_path.name}' ({width}x{height} -> {square_size}x{square_size})")
            return True

    except Exception as e:
        print(f"❌ Ошибка при обработке '{image_path.name}': {e}")
        return False


def process_images_in_directory(directory_path, recursive=False, background_color=(255, 255, 255)):
    """
    Обрабатывает все изображения в директории

    Args:
        directory_path (str): Путь к директории
        recursive (bool): Обрабатывать поддиректории рекурсивно
        background_color (tuple): Цвет фона (R, G, B)

    Returns:
        bool: True если успешно
    """
    try:
        path = Path(directory_path)

        # Проверяем существование директории
        if not path.exists():
            print(f"❌ Ошибка: Директория '{directory_path}' не существует")
            return False

        if not path.is_dir():
            print(f"❌ Ошибка: '{directory_path}' не является директорией")
            return False

        # Поддерживаемые форматы изображений
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

        # Получаем список файлов изображений
        if recursive:
            image_files = [f for f in path.rglob('*') if f.is_file() and f.suffix.lower() in image_extensions]
        else:
            image_files = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() in image_extensions]

        if not image_files:
            print(f"📁 В директории '{directory_path}' не найдено изображений")
            return True

        processed_count = 0
        skipped_count = 0
        error_count = 0

        print(f"🔍 Найдено изображений: {len(image_files)}")
        print("=" * 70)

        for image_file in image_files:
            try:
                # Получаем относительный путь для красивого вывода
                if recursive:
                    relative_path = image_file.relative_to(path)
                    print(f"📂 Обрабатываем: {relative_path}")

                result = make_image_square(image_file, background_color)

                if result:
                    if "Пропущен" in str(result):
                        skipped_count += 1
                    else:
                        processed_count += 1
                else:
                    error_count += 1

            except Exception as e:
                print(f"❌ Неожиданная ошибка с '{image_file.name}': {e}")
                error_count += 1

        print("=" * 70)
        print(f"📊 Результат:")
        print(f"   Обработано: {processed_count} изображений")
        print(f"   Пропущено (уже квадратные): {skipped_count} изображений")
        print(f"   Ошибок: {error_count}")

        return True

    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False


def process_single_image(image_path, background_color=(255, 255, 255)):
    """
    Обрабатывает одно изображение

    Args:
        image_path (str): Путь к изображению
        background_color (tuple): Цвет фона (R, G, B)

    Returns:
        bool: True если успешно
    """
    path = Path(image_path)

    if not path.exists():
        print(f"❌ Ошибка: Файл '{image_path}' не существует")
        return False

    if not path.is_file():
        print(f"❌ Ошибка: '{image_path}' не является файлом")
        return False

    # Проверяем расширение файла
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
    if path.suffix.lower() not in image_extensions:
        print(f"❌ Ошибка: '{image_path}' не является поддерживаемым форматом изображения")
        return False

    print(f"🖼️  Обрабатываем изображение: {path.name}")
    print("=" * 50)

    result = make_image_square(path, background_color)

    if result:
        print("✨ Обработка завершена успешно!")
    else:
        print("💥 Обработка завершена с ошибкой")

    return result


def parse_color(color_str):
    """
    Парсит строку цвета в кортеж RGB

    Args:
        color_str (str): Цвет в формате "255,255,255" или "white"

    Returns:
        tuple: (R, G, B)
    """
    # Предустановленные цвета
    colors = {
        'white': (255, 255, 255),
        'black': (0, 0, 0),
        'red': (255, 0, 0),
        'green': (0, 255, 0),
        'blue': (0, 0, 255),
        'gray': (128, 128, 128),
        'grey': (128, 128, 128),
    }

    color_str = color_str.lower().strip()

    if color_str in colors:
        return colors[color_str]

    # Пытаемся парсить как RGB значения
    try:
        rgb_parts = [int(x.strip()) for x in color_str.split(',')]
        if len(rgb_parts) == 3 and all(0 <= x <= 255 for x in rgb_parts):
            return tuple(rgb_parts)
    except ValueError:
        pass

    print(f"⚠️  Неверный формат цвета '{color_str}', используется белый цвет")
    return (255, 255, 255)


def main():
    """Основная функция программы"""
    parser = argparse.ArgumentParser(
        description="Преобразует изображения в квадратный формат",
        epilog="Примеры использования:\n"
               "  python script.py -d /path/to/images\n"
               "  python script.py -f image.jpg\n"
               "  python script.py -d /path/to/images -r --color black\n"
               "  python script.py -f image.png --color 128,128,128",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-d', '--directory', help='Путь к директории с изображениями')
    group.add_argument('-f', '--file', help='Путь к одному файлу изображения')

    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Обрабатывать поддиректории рекурсивно (только для -d)')
    parser.add_argument('--color', default='white',
                        help='Цвет фона (white, black, red, green, blue, gray или R,G,B). По умолчанию: white')

    args = parser.parse_args()

    # Парсим цвет фона
    background_color = parse_color(args.color)

    print("🖼️  Утилита для преобразования изображений в квадратный формат")
    print(f"🎨 Цвет фона: RGB{background_color}")
    print()

    if args.file:
        # Обрабатываем один файл
        success = process_single_image(args.file, background_color)
    else:
        # Обрабатываем директорию
        print(f"📂 Обрабатываем директорию: {args.directory}")
        if args.recursive:
            print("🔄 Режим: рекурсивная обработка поддиректорий")
        print()

        success = process_images_in_directory(args.directory, args.recursive, background_color)

    if success:
        print("\n✨ Операция завершена!")
    else:
        print("\n💥 Операция завершена с ошибками")


if __name__ == "__main__":
    # Если нет аргументов командной строки, используем настройки по умолчанию
    if len(sys.argv) == 1:
        print("🖼️  Утилита для преобразования изображений в квадратный формат")
        print()
        print("📂 Использование настроек по умолчанию:")

        # ========================================
        # НАСТРОЙКА: Укажите здесь путь к вашей директории
        # ========================================
        directory_path = r"\\10.10.100.2\FotoPack"  # Замените на ваш путь
        recursive_mode = True  # True для рекурсивной обработки
        background_color = (255, 255, 255)  # Белый фон

        print(f"   Директория: {directory_path}")
        print(f"   Рекурсивно: {recursive_mode}")
        print(f"   Цвет фона: RGB{background_color}")
        print()

        success = process_images_in_directory(directory_path, recursive_mode, background_color)

        if success:
            print("\n✨ Операция завершена!")
        else:
            print("\n💥 Операция завершена с ошибками")
    else:
        main()