"""Uçtan uca (E2E) arayüz testi — demo derlemesine karşı gerçek tarayıcıda.

Çalıştırma (depo kökünden):
    node node_modules/vite/bin/vite.js build --mode demo
    engine\\.venv\\Scripts\\python.exe -m pytest e2e

Demo derlemesi örnek verilerle (src/lib/mock.ts) çalışır; hiçbir platforma bağlanmaz. Tarayıcı olarak
sistemdeki Microsoft Edge ya da Google Chrome kullanılır (ek indirme yok).
Tarayıcı veya `dist-demo` yoksa testler atlanır.
"""

from __future__ import annotations

import functools
import http.server
import re
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

DIST = Path(__file__).resolve().parent.parent / "dist-demo"
PIN = "123456"


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    if not (DIST / "index.html").exists():
        pytest.skip("dist-demo yok: önce `vite build --mode demo` çalıştırın")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()


@pytest.fixture()
def page(base_url: str) -> Iterator[playwright_api.Page]:
    with playwright_api.sync_playwright() as p:
        browser = None
        for channel in ("msedge", "chrome"):  # sistemdeki tarayıcı; Playwright tarayıcısı indirilmez
            try:
                browser = p.chromium.launch(channel=channel, headless=True)
                break
            except playwright_api.Error:
                continue
        if browser is None:
            pytest.skip("Edge veya Chrome bulunamadı")
        context = browser.new_context(viewport={"width": 1400, "height": 900}, locale="tr-TR")
        tab = context.new_page()
        errors: list[str] = []
        tab.on("pageerror", lambda exc: errors.append(str(exc)))
        tab.goto(base_url)
        yield tab
        browser.close()
        assert errors == [], f"Sayfa hataları: {errors}"


def _nav(page: playwright_api.Page, label: str) -> None:
    page.locator(".nav-link", has_text=label).click()


def _switch_to_admin(page: playwright_api.Page) -> None:
    page.get_by_role("button", name=re.compile("Yönetici hesabına geç")).click()
    dialog = page.get_by_role("form", name="Yönetici girişi")
    dialog.get_by_label("PIN").fill(PIN)
    dialog.get_by_role("button", name="Doğrula").click()
    playwright_api.expect(page.get_by_text("Yönetici hesabı", exact=True)).to_be_visible()


def test_opens_in_user_account_with_demo_strip(page: playwright_api.Page) -> None:
    playwright_api.expect(page.get_by_role("note")).to_contain_text("DEMO")
    playwright_api.expect(
        page.get_by_role("button", name=re.compile("Yönetici hesabına geç"))
    ).to_be_visible()
    playwright_api.expect(page.locator(".nav-link", has_text="Sistem")).to_have_count(0)


def test_user_adds_a_link_with_campaign_and_note(page: playwright_api.Page) -> None:
    _nav(page, "Paylaşımlar")
    page.get_by_label("Paylaşım linki").fill("https://www.reddit.com/r/FPS_Games/comments/e2e/test/")
    playwright_api.expect(page.locator(".link-detect")).to_contain_text("Reddit")
    page.get_by_label("Kampanya", exact=True).select_option(label="Nova Beta Duyurusu · Project Nova")
    page.get_by_label("İçerik türü").select_option("video")
    page.get_by_label("Sayfa hakkında not").fill("E2E: görselle paylaşım daha iyi")
    page.get_by_role("button", name="Takibi başlat").click()
    playwright_api.expect(page.get_by_text("paylaşımı kaydedildi")).to_be_visible()


def test_admin_reaches_campaigns_system_and_analytics(page: playwright_api.Page) -> None:
    _switch_to_admin(page)
    _nav(page, "Kampanyalar")
    playwright_api.expect(page.get_by_text("Nova Beta Duyurusu").first).to_be_visible()
    _nav(page, "Sistem")
    playwright_api.expect(page.get_by_role("heading", name="Platform sağlığı")).to_be_visible()
    playwright_api.expect(page.get_by_text("Duraklatıldı")).to_be_visible()
    _nav(page, "Analitik")
    playwright_api.expect(page.get_by_role("heading", name="Performans puanı")).to_be_visible()


def test_global_search_opens_a_post(page: playwright_api.Page) -> None:
    page.get_by_role("searchbox", name="Ara").fill("IndieGaming")
    results = page.get_by_role("listbox", name="Arama sonuçları")
    results.get_by_role("option").first.click()
    playwright_api.expect(page.get_by_role("dialog", name="Gönderi ayrıntısı")).to_be_visible()
