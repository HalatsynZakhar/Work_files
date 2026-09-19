"""
Модуль интеграции с API Хорошоп (attoys.com.ua).
Реализует:
- Авторизацию (/api/auth/)
- Экспорт каталога товаров и цен (/api/catalog/export/)
- Безопасный расчет оптовых цен (устранение конфликта wholesale_price >= price)
- Защиту зафиксированных позиций (ФИКСИРОВАТЬ ЦЕНУ.xlsx)
- Обновление цен одиночно и пакетами (/api/catalog/import/)
"""

import json
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional
from urllib.parse import urljoin
import requests

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Файл конфигурации не найден: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class HoroshopApiError(RuntimeError):
    pass


def extract_brand_name(p: dict[str, Any]) -> str:
    """Извлекает наименование бренда из структуры ответа Хорошоп."""
    brand_data = p.get("brand")
    if not brand_data:
        return ""
    if isinstance(brand_data, dict):
        val = brand_data.get("value")
        if isinstance(val, dict):
            return str(val.get("ru") or val.get("ua") or "").strip()
        elif val is not None:
            return str(val).strip()
        if brand_data.get("title"):
            return str(brand_data.get("title")).strip()
    elif isinstance(brand_data, str):
        return brand_data.strip()
    return ""


class HoroshopClient:
    def __init__(self, config_dict: Optional[dict[str, Any]] = None):
        self.config = config_dict or load_config()
        self.horoshop_cfg = self.config.get("horoshop", {})
        self.wholesale_cfg = self.config.get("wholesale", {})

        self.domain = self.horoshop_cfg.get("domain", "https://attoys.com.ua").rstrip("/")
        self.login = self.horoshop_cfg.get("login", "")
        self.password = self.horoshop_cfg.get("password", "")
        self.batch_size = max(1, int(self.horoshop_cfg.get("batch_size", 50)))
        self.timeout = max(10, int(self.horoshop_cfg.get("request_timeout_seconds", 60)))

        self.session = requests.Session()
        self._token: Optional[str] = None
        self._catalog_cache: dict[str, dict[str, Any]] = {}
        self._display_to_article: dict[str, str] = {}
        self._normalized_to_article: dict[str, str] = {}

    def _url(self, endpoint: str) -> str:
        return urljoin(f"{self.domain}/", endpoint.lstrip("/"))

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._url(endpoint)
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise HoroshopApiError(f"Ошибка HTTP при обращении к {endpoint}: {e}") from e
        except ValueError as e:
            raise HoroshopApiError(f"Некорректный JSON от Хорошоп ({endpoint}): {e}") from e

        if not isinstance(data, dict):
            raise HoroshopApiError(f"Некорректный формат ответа Хорошоп: {data}")

        if str(data.get("status", "")).upper() in {"ERROR", "EXCEPTION"}:
            msg = data.get("message") or data.get("response") or str(data)
            raise HoroshopApiError(f"Ошибка Хорошоп API: {msg}")

        return data

    def get_token(self, force_refresh: bool = False) -> str:
        if self._token and not force_refresh:
            return self._token

        if not self.login or not self.password:
            raise HoroshopApiError("Логин или пароль Хорошоп не указаны в config.json.")

        data = self._post("/api/auth/", {"login": self.login, "password": self.password})
        token = data.get("response", {}).get("token")
        if not token:
            raise HoroshopApiError("Хорошоп не вернул токен авторизации.")

        self._token = str(token)
        return self._token

    def export_catalog(self, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        """
        Выгружает все товары из каталога Хорошоп с их текущими ценами и оптовыми порогами.
        Кэширует результат в оперативной памяти.
        """
        if self._catalog_cache and not force_refresh:
            return self._catalog_cache

        token = self.get_token()
        offset = 0
        limit = 500
        products_list: list[dict[str, Any]] = []

        print("-> Экспорт каталога товаров из Хорошоп...")
        while True:
            payload = {
                "token": token,
                "offset": offset,
                "limit": limit,
                "includedParams": ["article_for_display", "price", "price_old", "wholesale_prices", "brand"]
            }
            res = self._post("/api/catalog/export/", payload)
            nested = res.get("response")
            page = nested.get("products") if isinstance(nested, dict) else res.get("products")
            if not isinstance(page, list):
                raise HoroshopApiError("Ответ каталога Хорошоп не содержит списка products.")

            products_list.extend(item for item in page if isinstance(item, dict))
            if len(page) < limit:
                break
            offset += limit

        self._catalog_cache.clear()
        self._display_to_article.clear()
        self._normalized_to_article.clear()

        for p in products_list:
            art = str(p.get("article", "")).strip()
            disp_art = str(p.get("article_for_display", "")).strip()
            if not art:
                continue

            p["brand_title"] = extract_brand_name(p)

            # art - это внутренний уникальный артикул Хорошоп (UUID вида ce06d003-8aa5-11ed-870e-1402ec4177b7)
            art_up = art.upper()
            self._catalog_cache[art_up] = p
            norm_art = re.sub(r'[^A-Z0-9]', '', art_up)
            if norm_art:
                self._normalized_to_article[norm_art] = art_up

            # disp_art - артикул для отображения покупателю (X15T BLUE и т.д.)
            if disp_art:
                disp_up = disp_art.upper()
                self._display_to_article[disp_up] = art_up
                if disp_up not in self._catalog_cache:
                    self._catalog_cache[disp_up] = p
                norm_disp = re.sub(r'[^A-Z0-9]', '', disp_up)
                if norm_disp and norm_disp not in self._normalized_to_article:
                    self._normalized_to_article[norm_disp] = art_up

        print(f"[OK] Экспортировано {len(products_list)} товаров из Хорошоп.")
        return self._catalog_cache

    def find_product(self, article: str, horoshop_article: Optional[str] = None) -> Optional[dict[str, Any]]:
        """
        Ищет товар по точному артикулу или внутреннему UUID Хорошоп (ce06d003-8aa5-11ed-870e-1402ec4177b7).
        Приоритет поиска:
        1. horoshop_article (UUID): прямой поиск в кэше, по display_to_article или по нормализованному ключу.
        2. article: прямой поиск, через соответствие display_to_article, либо нормализованное сопоставление.
        """
        if not self._catalog_cache:
            self.export_catalog()

        # 1. Приоритет: horoshop_article (внутренний GUID/UUID каталога)
        if horoshop_article:
            hor_clean = str(horoshop_article).strip().upper()
            if hor_clean:
                if hor_clean in self._catalog_cache:
                    return self._catalog_cache[hor_clean]
                target_art = self._display_to_article.get(hor_clean)
                if target_art and target_art in self._catalog_cache:
                    return self._catalog_cache[target_art]
                hor_norm = re.sub(r'[^A-Z0-9]', '', hor_clean)
                if hor_norm and hor_norm in self._normalized_to_article:
                    target_art = self._normalized_to_article[hor_norm]
                    if target_art in self._catalog_cache:
                        return self._catalog_cache[target_art]

        # 2. Поиск по основному артикулу (может быть как человекочитаемым X15T BLUE, так и UUID)
        art_clean = str(article).strip().upper()
        if not art_clean:
            return None

        # 2.1 Прямой поиск в каталоге
        if art_clean in self._catalog_cache:
            return self._catalog_cache[art_clean]

        # 2.2 Через сопоставление display_article -> internal article
        internal_art = self._display_to_article.get(art_clean)
        if internal_art and internal_art in self._catalog_cache:
            return self._catalog_cache[internal_art]

        # 2.3 Поиск по нормализованному коду (без пробелов, дефисов и спецзнаков)
        art_norm = re.sub(r'[^A-Z0-9]', '', art_clean)
        if art_norm and art_norm in self._normalized_to_article:
            target_art = self._normalized_to_article[art_norm]
            if target_art in self._catalog_cache:
                return self._catalog_cache[target_art]

        return None

    def calculate_safe_wholesale_prices(
        self,
        new_retail_price: float,
        rrc_price: Optional[float] = None,
        existing_wholesale: Optional[list[dict[str, Any]]] = None
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Рассчитывает безопасные оптовые цены:
        1. Если recalculate_from_rrc = True и есть РРЦ/старая цена, формирует сетку (Опт 1: -10%, Опт 2: -15%, Опт 3: -25%).
        2. Иначе сохраняет существующие оптовые цены.
        3. КРИТИЧЕСКИ ВАЖНО: Удаляет любые оптовые цены, которые >= новой розничной цене!
        Возвращает: (список оптовых цен, список предупреждений)
        """
        recalc_from_rrc = bool(self.wholesale_cfg.get("recalculate_from_rrc", True))
        rules = self.wholesale_cfg.get("rules", [
            {"tier": 1, "minimal_threshold": 2, "discount_percent": 10},
            {"tier": 2, "minimal_threshold": 5, "discount_percent": 15},
            {"tier": 3, "minimal_threshold": 10, "discount_percent": 25}
        ])

        wholesale_map: dict[int, Decimal] = {}
        warnings: list[str] = []

        # Базовые оптовые цены из имеющихся
        if existing_wholesale:
            for item in existing_wholesale:
                try:
                    thresh = int(item.get("minimal_threshold", 0))
                    pr = Decimal(str(item.get("price", 0)))
                    if thresh > 0 and pr > 0:
                        wholesale_map[thresh] = pr
                except Exception:
                    continue

        # Пересчет от РРЦ если включено и РРЦ задана
        base_for_wholesale = Decimal(str(rrc_price)) if rrc_price and rrc_price > 0 else None

        if recalc_from_rrc and base_for_wholesale:
            for r in rules:
                threshold = int(r.get("minimal_threshold", 0))
                discount = Decimal(str(r.get("discount_percent", 0)))
                if threshold > 0 and 0 < discount < 100:
                    tier_price = (base_for_wholesale * (Decimal("100") - discount) / Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    wholesale_map[threshold] = tier_price
            warnings.append("Оптовые пороги 1-3 пересчитаны от РРЦ.")

        # Устранение конфликта: опт ДОЛЖЕН быть строго меньше новой розничной цены
        retail_dec = Decimal(str(new_retail_price))
        invalid_thresholds = [th for th, pr in wholesale_map.items() if pr >= retail_dec]
        for th in invalid_thresholds:
            del wholesale_map[th]

        if invalid_thresholds:
            warnings.append(
                f"Отключены оптовые уровни (пороги {sorted(invalid_thresholds)} шт.), где цена не ниже розничной ({new_retail_price} грн)."
            )

        result_wholesale = [
            {"minimal_threshold": th, "price": float(pr)}
            for th, pr in sorted(wholesale_map.items())
        ]
        return result_wholesale, warnings

    def update_single_price(
        self,
        article: str,
        new_price: float,
        rrc_price: Optional[float] = None,
        locked_articles: Optional[set[str]] = None,
        horoshop_article: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Устанавливает новую розничную цену на товар с безопасным расчетом опта
        и защитой заблокированных артикулов.
        Поддерживает передачу как человекочитаемого артикула, так и внутреннего UUID Хорошоп (ce06d003-8aa5-11ed-870e-1402ec4177b7).
        """
        art_clean = str(article).strip().upper()
        hor_clean = str(horoshop_article).strip().upper() if horoshop_article else ""

        # 1. Проверка блокировки (по артикулу и по UUID)
        is_locked = False
        if locked_articles:
            if art_clean in locked_articles:
                is_locked = True
            elif hor_clean and hor_clean in locked_articles:
                is_locked = True

        if is_locked:
            return {
                "success": False,
                "article": article,
                "horoshop_article": horoshop_article,
                "status": "LOCKED",
                "message": f"Артикул '{article}' ({horoshop_article or ''}) зафиксирован замком — обновление запрещено."
            }

        # 2. Поиск товара в каталоге Хорошоп (приоритет horoshop_article, затем article)
        product = self.find_product(art_clean, horoshop_article=hor_clean)
        if not product:
            return {
                "success": False,
                "article": article,
                "horoshop_article": horoshop_article,
                "status": "NOT_FOUND",
                "message": f"Товар '{article}' (UUID: {horoshop_article or 'не указан'}) не найден в каталоге Хорошоп."
            }

        # В Хорошоп для /api/catalog/import/ ОБЯЗАТЕЛЬНО передавать внутренний GUID/UUID каталога (product['article'])
        internal_article = product.get("article") or hor_clean or art_clean
        existing_wholesale = product.get("wholesale_prices", [])
        existing_rrc = product.get("price_old")

        effective_rrc = rrc_price if (rrc_price and rrc_price > 0) else existing_rrc

        # 3. Безопасный расчет опта
        safe_wholesale, warnings = self.calculate_safe_wholesale_prices(
            new_retail_price=new_price,
            rrc_price=effective_rrc,
            existing_wholesale=existing_wholesale
        )

        payload_product: dict[str, Any] = {
            "article": internal_article,
            "price": float(new_price),
            "wholesale_prices": safe_wholesale
        }
        if effective_rrc:
            payload_product["price_old"] = float(effective_rrc)

        # 4. Отправка в API Хорошоп
        token = self.get_token()
        try:
            res = self._post("/api/catalog/import/", {
                "token": token,
                "products": [payload_product]
            })
            log_entries = res.get("response", {}).get("log", []) if isinstance(res.get("response"), dict) else []
            has_errors = any(
                any(code != 0 for code in [info.get("code") for info in entry.get("info", [])])
                for entry in log_entries if isinstance(entry, dict)
            )

            if res.get("status") == "OK" and not has_errors:
                # Обновляем локальный кэш
                product["price"] = float(new_price)
                if effective_rrc:
                    product["price_old"] = float(effective_rrc)
                product["wholesale_prices"] = safe_wholesale

                return {
                    "success": True,
                    "article": article,
                    "horoshop_article": internal_article,
                    "new_price": new_price,
                    "old_price": effective_rrc,
                    "wholesale_prices": safe_wholesale,
                    "warnings": warnings,
                    "message": f"Цена успешно обновлена на {new_price} грн."
                }
            else:
                return {
                    "success": False,
                    "article": article,
                    "horoshop_article": internal_article,
                    "status": "API_ERROR",
                    "message": f"Хорошоп сообщил об ошибке импорта: {res}"
                }
        except Exception as e:
            return {
                "success": False,
                "article": article,
                "horoshop_article": internal_article,
                "status": "EXCEPTION",
                "message": f"Ошибка запроса импорта цены: {e}"
            }

    def update_batch_prices(
        self,
        items: list[dict[str, Any]],
        locked_articles: Optional[set[str]] = None
    ) -> dict[str, Any]:
        """
        Массовое обновление цен списка товаров.
        items: [{"article": "...", "horoshop_article": "...", "price": 450.0, "rrc": 500.0}, ...]
        """
        locked = locked_articles or set()
        to_process: list[dict[str, Any]] = []
        skipped_locked: list[str] = []
        not_found: list[str] = []

        if not self._catalog_cache:
            self.export_catalog()

        for it in items:
            art = str(it.get("article", "")).strip()
            hor_art = str(it.get("horoshop_article", "")).strip()
            art_upper = art.upper()
            hor_upper = hor_art.upper()
            if not art and not hor_art:
                continue

            if (art_upper and art_upper in locked) or (hor_upper and hor_upper in locked):
                skipped_locked.append(art or hor_art)
                continue

            product = self.find_product(art_upper, horoshop_article=hor_upper)
            if not product:
                not_found.append(f"{art} [{hor_art}]" if hor_art else art)
                continue

            try:
                new_price = float(it.get("price", 0))
            except (ValueError, TypeError):
                continue

            if new_price <= 0:
                continue

            rrc_val = it.get("rrc")
            try:
                effective_rrc = float(rrc_val) if rrc_val else product.get("price_old")
            except Exception:
                effective_rrc = product.get("price_old")

            internal_article = product.get("article") or hor_upper or art_upper
            existing_wholesale = product.get("wholesale_prices", [])

            safe_wholesale, _ = self.calculate_safe_wholesale_prices(
                new_retail_price=new_price,
                rrc_price=effective_rrc,
                existing_wholesale=existing_wholesale
            )

            p_payload: dict[str, Any] = {
                "article": internal_article,
                "price": new_price,
                "wholesale_prices": safe_wholesale
            }
            if effective_rrc:
                p_payload["price_old"] = float(effective_rrc)

            to_process.append({
                "payload": p_payload,
                "product_ref": product,
                "article": art,
                "horoshop_article": hor_art,
                "new_price": new_price,
                "effective_rrc": effective_rrc,
                "wholesale": safe_wholesale
            })

        if not to_process:
            return {
                "total": len(items),
                "updated": 0,
                "skipped_locked": skipped_locked,
                "not_found": not_found,
                "message": "Нет товаров для обновления (все заблокированы или не найдены)."
            }

        # Отправка батчами
        updated_count = 0
        errors: list[dict[str, Any]] = []
        token = self.get_token()

        for i in range(0, len(to_process), self.batch_size):
            chunk = to_process[i:i + self.batch_size]
            products_chunk = [c["payload"] for c in chunk]
            try:
                res = self._post("/api/catalog/import/", {
                    "token": token,
                    "products": products_chunk
                })
                # Обновление локального кэша
                for c in chunk:
                    pref = c["product_ref"]
                    pref["price"] = c["new_price"]
                    if c["effective_rrc"]:
                        pref["price_old"] = c["effective_rrc"]
                    pref["wholesale_prices"] = c["wholesale"]
                updated_count += len(chunk)
            except Exception as e:
                errors.append({
                    "batch_start": i,
                    "count": len(chunk),
                    "error": str(e)
                })

        return {
            "total": len(items),
            "updated": updated_count,
            "skipped_locked": skipped_locked,
            "not_found": not_found,
            "errors": errors,
            "message": f"Успешно обновлено {updated_count} позиций. Заблокировано: {len(skipped_locked)}."
        }


# Глобальный клиент
horoshop_client = HoroshopClient()

if __name__ == "__main__":
    client = HoroshopClient()
    print("Проверка подключения к Хорошоп API...")
    try:
        t = client.get_token()
        print(f"[OK] Токен авторизации получен: {t[:8]}...")
        cat = client.export_catalog()
        print(f"[OK] Загружено товаров: {len(cat)}")
    except Exception as ex:
        print(f"[WARN] Ошибка проверки Хорошоп API: {ex}")
