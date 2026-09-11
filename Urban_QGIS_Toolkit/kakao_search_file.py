import os
import asyncio
from qgis.PyQt import QtWidgets
from .vworld_login import (
    _chrome_launch_options,
    _ensure_playwright_event_pump,
    get_or_create_service_browser,
    get_service_chrome_profile_directory,
    get_opposite_monitor_geometry,
)

def kakao_search_function(dock_widget):
    search_query = ""
    if hasattr(dock_widget, 'input_search_kakao') and dock_widget.input_search_kakao:
        search_query = dock_widget.input_search_kakao.text().strip()

    if not search_query:
        QtWidgets.QMessageBox.warning(dock_widget, "경고", "카카오맵 검색 주소를 입력해 주세요.")
        return

    if hasattr(dock_widget, 'eum_kakao_status'):
        dock_widget.eum_kakao_status.setText("크롬 구동 중...")
        dock_widget.eum_kakao_status.setStyleSheet("color: green;")
    QtWidgets.QApplication.processEvents()

    print(f"검색어: {search_query}")

    async def _run_eum_search():
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            if hasattr(dock_widget, 'eum_kakao_status'):
                dock_widget.eum_kakao_status.setText("Playwright 미설치")
            return

        try:
            target_x, target_y, target_w, target_h, has_other_monitor = get_opposite_monitor_geometry(dock_widget.iface)

            if not hasattr(dock_widget, '_playwright_instance') or not dock_widget._playwright_instance:
                from playwright.async_api import async_playwright
                dock_widget._playwright_instance = await async_playwright().start()

            chrome_args = [
                f"--window-position={target_x},{target_y}",
                f"--window-size={target_w},{target_h}",
            ]

            if has_other_monitor:
                chrome_args.append("--start-maximized")

            new_context, page, _ = await get_or_create_service_browser(
                dock_widget,
                "Kakao",
                "kakao_browser_context",
                "kakao_browser",
                "kakao_page",
                chrome_args,
            )

            await page.goto("https://map.kakao.com", wait_until="domcontentloaded")

            search_input_selector = ".box_searchbar input[type='text']"
            await page.wait_for_selector(search_input_selector, state="visible", timeout=10000)
            await page.locator(search_input_selector).fill(search_query)

            await page.locator(search_input_selector).press("Enter")
            await page.wait_for_timeout(1000)

            if hasattr(dock_widget, 'eum_kakao_status'):
                dock_widget.eum_kakao_status.setText("주소 검색 완료")
                dock_widget.eum_kakao_status.setStyleSheet("color: blue; font-weight: bold;")

        except Exception as err:
            print(f"[ERROR] 카카오맵 스크립트 실행 실패: {err}")
            if hasattr(dock_widget, 'eum_kakao_status'):
                dock_widget.eum_kakao_status.setText("검색 실패")
                dock_widget.eum_kakao_status.setStyleSheet("color: red;")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_run_eum_search())
        else:
            loop.run_until_complete(_run_eum_search())
            _ensure_playwright_event_pump(dock_widget, loop)
    except Exception as e:
        print(f"[ERROR] 루프 예외: {e}")
