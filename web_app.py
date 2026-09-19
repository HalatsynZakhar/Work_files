"""
Веб-сервер и API для интерактивного дашборда мониторинга цен и синхронизации с Хорошоп.
FastAPI + Uvicorn.
"""

import json
import os
import sys
import threading
import time
import webbrowser
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

import analytics
from horoshop_api import horoshop_client, HoroshopApiError
from images_feed import images_feed

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")


def get_config() -> dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


config = get_config()
server_cfg = config.get("server", {})
SERVER_HOST = server_cfg.get("host", "127.0.0.1")
SERVER_PORT = int(server_cfg.get("port", 8090))
AUTO_OPEN = bool(server_cfg.get("auto_open_browser", True))

app = FastAPI(title="Horoshop Price Tracker Dashboard", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальное состояние данных в памяти
state = {
    "consolidated_rows": [],
    "raw_watches": [],
    "docker_live": False,
    "last_loaded": None,
    "rrc_map": {},
    "locked_articles": set(),
}


def reload_all_data(force_refresh_remote: bool = False) -> list[dict[str, Any]]:
    """Загружает или обновляет все данные из Docker, Хорошоп и файлов."""
    print("-> Обновление данных мониторинга и цен...")

    # 1. Загрузка справочников
    rrc_map = analytics.load_rrc_prices()
    locked = analytics.load_locked_articles()
    catalog_df = analytics.load_catalog_dataframe()

    state["rrc_map"] = rrc_map
    state["locked_articles"] = locked

    # 2. Docker Watches
    raw_docker, is_live = analytics.get_docker_watches_data(force_refresh=force_refresh_remote)
    state["docker_live"] = is_live
    watches = analytics.parse_all_watches(raw_docker)
    state["raw_watches"] = watches

    # 3. Экспорт каталога Хорошоп
    horoshop_cat = None
    try:
        horoshop_cat = horoshop_client.export_catalog(force_refresh=force_refresh_remote)
    except Exception as e:
        print(f"[WARN] Каталог Хорошоп недоступен: {e}")

    # 4. XML фид фото
    try:
        images_feed.load(force_refresh=force_refresh_remote)
    except Exception as e:
        print(f"[WARN] Фид изображений недоступен: {e}")

    # 5. Сводная таблица
    rows = analytics.build_consolidated_pivot(
        df_catalog=catalog_df,
        watches_list=watches,
        rrc_map=rrc_map,
        locked_articles=locked,
        horoshop_catalog=horoshop_cat
    )

    state["consolidated_rows"] = rows
    state["last_loaded"] = time.time()
    print(f"[OK] Сводная таблица обновлена: {len(rows)} позиций.")
    return rows


# =================================================================
# PYDANTIC МОДЕЛИ ЗАПРОСОВ
# =================================================================

class UpdateSinglePriceRequest(BaseModel):
    article: str
    price: float
    rrc: Optional[float] = None
    horoshop_article: Optional[str] = None


class BatchItem(BaseModel):
    article: str
    price: float
    rrc: Optional[float] = None
    horoshop_article: Optional[str] = None


class UpdateBatchRequest(BaseModel):
    items: list[BatchItem]


class ToggleLockRequest(BaseModel):
    article: str
    locked: Optional[bool] = None


class ExportExcelRequest(BaseModel):
    strategy: Optional[str] = None
    store: Optional[str] = None
    columns: Optional[list[str]] = None
    custom_prices: Optional[dict[str, float]] = None


# =================================================================
# РОУТЫ
# =================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Шаблон index.html не найден")
    return FileResponse(index_path)


@app.get("/api/status")
async def get_system_status():
    """Возвращает статус компонентов системы и проверку файлов."""
    file_checks = analytics.check_startup_files()

    docker_status = {
        "active": state["docker_live"],
        "watches_count": len(state["raw_watches"])
    }

    horoshop_status = {
        "connected": bool(horoshop_client._catalog_cache),
        "catalog_count": len(horoshop_client._catalog_cache) // 2 if horoshop_client._catalog_cache else 0,
        "domain": horoshop_client.domain
    }

    images_status = {
        "loaded": images_feed._loaded,
        "count": len(images_feed.article_to_image)
    }

    return {
        "status": "OK",
        "docker": docker_status,
        "horoshop": horoshop_status,
        "images": images_status,
        "files": file_checks,
        "locked_count": len(state["locked_articles"]),
        "last_loaded": state["last_loaded"]
    }


@app.get("/api/data")
async def get_products_data(refresh: bool = Query(False)):
    """Возвращает список сводных товаров для таблицы дашборда."""
    if refresh or not state["consolidated_rows"]:
        rows = reload_all_data(force_refresh_remote=refresh)
    else:
        rows = state["consolidated_rows"]

    return {
        "total": len(rows),
        "products": rows
    }


@app.post("/api/update-price")
async def update_single_price_endpoint(req: UpdateSinglePriceRequest):
    """Устанавливает цену для одного товара с проверкой оптовых порогов и защитой блокировки."""
    art = req.article.strip().upper()
    hor_art = (req.horoshop_article or "").strip().upper()
    locked = state["locked_articles"] or analytics.load_locked_articles()

    if art in locked or (hor_art and hor_art in locked):
        return {
            "success": False,
            "article": req.article,
            "horoshop_article": req.horoshop_article,
            "message": f"Артикул '{req.article}' зафиксирован замком в интерфейсе — изменение заблокировано!"
        }

    try:
        res = horoshop_client.update_single_price(
            article=req.article,
            new_price=req.price,
            rrc_price=req.rrc,
            locked_articles=locked,
            horoshop_article=req.horoshop_article
        )

        if res.get("success"):
            # Обновляем в текущем кеше
            for r in state["consolidated_rows"]:
                if r["article"].upper() == art or (hor_art and r.get("horoshop_article", "").upper() == hor_art):
                    r["our_price"] = req.price
                    break

        return res
    except Exception as e:
        return {
            "success": False,
            "article": req.article,
            "horoshop_article": req.horoshop_article,
            "message": f"Внутренняя ошибка обновления: {e}"
        }


@app.post("/api/toggle-lock")
async def toggle_lock_endpoint(req: ToggleLockRequest):
    """Переключает статус замка (блокировки) товара и сохраняет в таблицу locked_articles."""
    new_status = analytics.toggle_article_lock(req.article, req.locked)
    state["locked_articles"] = analytics.load_locked_articles()

    art_clean = req.article.strip().upper()
    # Обновляем состояние в сводной таблице памяти
    for r in state["consolidated_rows"]:
        if r["article"].upper() == art_clean:
            r["is_locked"] = new_status
            break

    return {
        "success": True,
        "article": req.article,
        "is_locked": new_status,
        "locked_count": len(state["locked_articles"]),
        "message": f"Артикул {req.article} {'зафиксирован замком 🔒' if new_status else 'разблокирован 🔓'}"
    }


@app.post("/api/update-batch")
async def update_batch_endpoint(req: UpdateBatchRequest):
    """Массовое обновление цен выбранных товаров."""
    locked = state["locked_articles"] or analytics.load_locked_articles()
    items_dicts = [item.model_dump() for item in req.items]

    try:
        res = horoshop_client.update_batch_prices(
            items=items_dicts,
            locked_articles=locked
        )

        if res.get("updated", 0) > 0:
            updated_map = {it["article"].upper(): it["price"] for it in items_dicts if it.get("article")}
            updated_hor_map = {it["horoshop_article"].upper(): it["price"] for it in items_dicts if it.get("horoshop_article")}
            for r in state["consolidated_rows"]:
                art_up = r["article"].upper()
                hor_up = r.get("horoshop_article", "").upper()
                if (art_up in updated_map or (hor_up and hor_up in updated_hor_map)) and art_up not in locked and hor_up not in locked:
                    r["our_price"] = updated_map.get(art_up) if art_up in updated_map else updated_hor_map.get(hor_up)

        return res
    except Exception as e:
        return {
            "total": len(req.items),
            "updated": 0,
            "message": f"Ошибка пакетного обновления: {e}"
        }


@app.get("/api/export-excel")
async def export_excel_get_endpoint(
    store: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    columns: Optional[str] = Query(None)
):
    """Генерирует актуальный Excel-отчет и отдает на скачивание (GET)."""
    if not state["consolidated_rows"]:
        reload_all_data()

    cols_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None

    file_path = analytics.generate_full_excel_report(
        consolidated_rows=state["consolidated_rows"],
        raw_watches=state["raw_watches"],
        chosen_store=store,
        strategy=strategy,
        columns_to_export=cols_list
    )

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Не удалось создать Excel файл")

    return FileResponse(
        path=file_path,
        filename="ИТОГОВЫЙ_ОТЧЕТ.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.post("/api/export-excel")
async def export_excel_post_endpoint(req: ExportExcelRequest):
    """
    Генерирует актуальный Excel-отчет согласно выбранной стратегии,
    набору колонок и точным ценам из полей таблицы дашборда (POST).
    """
    if not state["consolidated_rows"]:
        reload_all_data()

    file_path = analytics.generate_full_excel_report(
        consolidated_rows=state["consolidated_rows"],
        raw_watches=state["raw_watches"],
        chosen_store=req.store,
        strategy=req.strategy,
        custom_prices=req.custom_prices,
        columns_to_export=req.columns
    )

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Не удалось создать Excel файл")

    return FileResponse(
        path=file_path,
        filename="ИТОГОВЫЙ_ОТЧЕТ.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# =================================================================
# ЗАПУСК СЕРВЕРА
# =================================================================

def open_browser_later():
    time.sleep(1.2)
    url = f"http://{SERVER_HOST}:{SERVER_PORT}"
    print(f"\n-> Открытие дашборда в браузере: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass


def print_startup_banner():
    print("=" * 68)
    print("   ХОРОШОП МОНИТОРИНГ И УСТАНОВКА ЦЕН (FASTAPI DASHBOARD)")
    print("=" * 68)
    print(f"Адрес панели управления: http://{SERVER_HOST}:{SERVER_PORT}")

    print("\n--- ПРОВЕРКА ВХОДНЫХ ФАЙЛОВ ДАННЫХ ---")
    checks = analytics.check_startup_files()
    for c in checks:
        icon = "[OK]" if not c["is_warning"] else "[ПРЕДУПРЕЖДЕНИЕ]"
        print(f"{icon:16} {c['filename']:<28} : {c['message']}")

    locked = analytics.load_locked_articles()
    print(f"\n[ИНФО] Зафиксированных позиций (защита от изменений): {len(locked)}")
    if locked:
        print(f"       Защищены артикулы: {', '.join(sorted(locked))}")
    print("=" * 68 + "\n")


def run_server():
    print_startup_banner()
    # Первичная загрузка данных в фоне
    threading.Thread(target=reload_all_data, daemon=True).start()

    if AUTO_OPEN:
        threading.Thread(target=open_browser_later, daemon=True).start()

    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    run_server()
