#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path


def rename_files_recursively(directory_path):
    """
    Рекурсивно переименовывает все файлы в директории и всех поддиректориях,
    удаляя все что идет после первого нижнего подчеркивания (включая само подчеркивание)

    Args:
        directory_path (str): Путь к директории
    """
    try:
        path = Path(directory_path)

        # Проверяем, существует ли директория
        if not path.exists():
            print(f"❌ Ошибка: Директория '{directory_path}' не существует")
            return False

        if not path.is_dir():
            print(f"❌ Ошибка: '{directory_path}' не является директорией")
            return False

        # Получаем все файлы рекурсивно
        all_files = list(path.rglob('*'))
        files = [f for f in all_files if f.is_file()]

        if not files:
            print(f"📁 В директории '{directory_path}' и поддиректориях нет файлов для переименования")
            return True

        renamed_count = 0
        skipped_count = 0

        print(f"🔍 Найдено файлов во всех поддиректориях: {len(files)}")
        print("=" * 70)

        for file_path in files:
            original_name = file_path.name
            relative_path = file_path.relative_to(path)

            # Разделяем имя файла и расширение
            name_without_ext = file_path.stem
            extension = file_path.suffix

            # Ищем первое нижнее подчеркивание
            if '_' in name_without_ext:
                # Берем все до первого подчеркивания
                new_name_without_ext = name_without_ext.split('_')[0]
                new_name = new_name_without_ext + extension
                new_path = file_path.parent / new_name

                # Проверяем, не существует ли уже файл с таким именем
                if new_path.exists() and new_path != file_path:
                    print(f"⚠️  Пропущен: '{relative_path}' -> '{new_name}' (файл уже существует)")
                    skipped_count += 1
                    continue

                try:
                    file_path.rename(new_path)
                    new_relative = new_path.relative_to(path)
                    print(f"✅ Переименован: '{relative_path}' -> '{new_relative}'")
                    renamed_count += 1
                except OSError as e:
                    print(f"❌ Ошибка при переименовании '{relative_path}': {e}")
                    skipped_count += 1
            else:
                print(f"⏭️  Пропущен: '{relative_path}' (нет подчеркивания в имени)")
                skipped_count += 1

        print("=" * 70)
        print(f"📊 Результат:")
        print(f"   Переименовано: {renamed_count} файлов")
        print(f"   Пропущено: {skipped_count} файлов")

        return True

    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False


def main():
    """Основная функция программы"""
    # ========================================
    # НАСТРОЙКА: Укажите здесь путь к вашей директории
    # ========================================
    directory_path = r"\\10.10.100.2\FotoPack"  # Замените на ваш путь

    print("🔧 Утилита для переименования файлов (рекурсивно)")
    print("Удаляет все после первого нижнего подчеркивания из имени файла")
    print("Обрабатывает все файлы в директории и всех поддиректориях")
    print(f"📂 Обрабатываем директорию: {directory_path}")
    print()

    # Выполняем переименование
    success = rename_files_recursively(directory_path)

    if success:
        print("\n✨ Операция завершена!")
    else:
        print("\n💥 Операция завершена с ошибками")


if __name__ == "__main__":
    main()