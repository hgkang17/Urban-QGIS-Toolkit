import os
import logging
import asyncio
from qgis.PyQt import QtCore, QtWidgets

try:
    import winreg
except ImportError:
    winreg = None

logger = logging.getLogger("VWorldLogin")


def _ensure_playwright_event_pump(dock_widget, loop):
    current_timer = getattr(dock_widget, "_playwright_event_timer", None)
    if current_timer is not None and current_timer.isActive():
        return

    timer = QtCore.QTimer(dock_widget)
    timer.setInterval(25)

    def process_playwright_events():
        if loop.is_closed():
            timer.stop()
            return
        if loop.is_running():
            return

        try:
            loop.call_soon(loop.stop)
            loop.run_forever()
        except RuntimeError as error:
            logger.warning("Playwright 이벤트 처리 중지: %s", error)
            timer.stop()

    timer.timeout.connect(process_playwright_events)
    timer.start()
    dock_widget._playwright_event_timer = timer


def get_opposite_monitor_geometry(iface):
    app = QtWidgets.QApplication.instance()
    screens = app.screens()
    if not screens:
        return 0, 0, 1280, 800, False

    qgis_window = iface.mainWindow()
    qgis_screen = qgis_window.screen() if hasattr(qgis_window, "screen") else None
    if qgis_screen not in screens:
        qgis_screen = app.screenAt(qgis_window.frameGeometry().center())
    if qgis_screen not in screens:
        qgis_screen = screens[0]

    target_screen = qgis_screen
    if len(screens) > 1:
        target_screen = next(screen for screen in screens if screen is not qgis_screen)

    rect = target_screen.availableGeometry()
    return rect.x(), rect.y(), rect.width(), rect.height(), len(screens) > 1


def _find_chrome_executable():
    candidates = []

    if winreg is not None:
        registry_keys = (
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        )
        for root_key, sub_key in registry_keys:
            try:
                with winreg.OpenKey(root_key, sub_key) as key:
                    chrome_path, _ = winreg.QueryValueEx(key, None)
                    candidates.append(chrome_path)
            except OSError:
                pass

    for env_name in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        base_path = os.environ.get(env_name)
        if base_path:
            candidates.append(os.path.join(base_path, "Google", "Chrome", "Application", "chrome.exe"))

    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.normpath(path)

    return None


def _get_download_directory():
    download_path = None

    if winreg is not None:
        try:
            shell_folder_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            downloads_guid = "{374DE290-123F-4565-9164-39C4925E467B}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, shell_folder_key) as key:
                download_path, _ = winreg.QueryValueEx(key, downloads_guid)
        except OSError:
            pass

    if download_path:
        download_path = os.path.expandvars(download_path)
    else:
        user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        download_path = os.path.join(user_profile, "Downloads")

    download_path = os.path.abspath(download_path)
    os.makedirs(download_path, exist_ok=True)
    return download_path


def get_service_chrome_profile_directory(service_name):
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "AppData", "Local")

    safe_service_name = "".join(
        character for character in str(service_name)
        if character.isalnum() or character in ("_", "-")
    ) or "Browser"
    profile_path = os.path.join(local_app_data, "Urban_QGIS_Toolkit", f"{safe_service_name}ChromeProfile")
    os.makedirs(profile_path, exist_ok=True)
    return profile_path


def _get_vworld_chrome_profile_directory():
    return get_service_chrome_profile_directory("VWorld")


def _chrome_launch_options(headless, downloads_path=None, args=None):
    options = {
        "headless": headless,
        "chromium_sandbox": True,
        "args": args or [],
    }
    chrome_path = _find_chrome_executable()
    if chrome_path:
        options["executable_path"] = chrome_path
        logger.info("설치된 Chrome 사용: %s", chrome_path)
    else:
        logger.warning("설치된 Chrome을 찾지 못해 Playwright Chromium을 사용합니다.")

    if downloads_path:
        options["downloads_path"] = downloads_path

    return options


async def get_or_create_service_browser(
    dock_widget,
    service_name,
    context_attr,
    browser_attr,
    page_attr,
    chrome_args,
    accept_downloads=False,
    downloads_path=None,
):
    context = getattr(dock_widget, context_attr, None)
    if context is not None:
        try:
            page = await context.new_page()
            setattr(dock_widget, page_attr, page)
            return context, page, True
        except Exception:
            setattr(dock_widget, context_attr, None)

    profile_path = get_service_chrome_profile_directory(service_name)
    context = await dock_widget._playwright_instance.chromium.launch_persistent_context(
        user_data_dir=profile_path,
        no_viewport=True,
        accept_downloads=accept_downloads,
        **_chrome_launch_options(
            headless=False,
            downloads_path=downloads_path,
            args=chrome_args,
        )
    )
    page = context.pages[0] if context.pages else await context.new_page()
    setattr(dock_widget, context_attr, context)
    setattr(dock_widget, browser_attr, context.browser)
    setattr(dock_widget, page_attr, page)
    return context, page, False


def _unique_download_path(download_directory, filename):
    safe_filename = os.path.basename(filename) or "download"
    target_path = os.path.join(download_directory, safe_filename)
    if not os.path.exists(target_path):
        return target_path

    name, extension = os.path.splitext(safe_filename)
    number = 1
    while True:
        target_path = os.path.join(download_directory, f"{name} ({number}){extension}")
        if not os.path.exists(target_path):
            return target_path
        number += 1

def vworld_backend_login(dock_widget):
    user_id = ""
    user_pw = ""
    if hasattr(dock_widget, 'input_id'):
        user_id = dock_widget.input_id.text().strip()
    if hasattr(dock_widget, 'input_pw'):
        user_pw = dock_widget.input_pw.text().strip()

    if not user_id or not user_pw:
        QtWidgets.QMessageBox.warning(dock_widget, "경고", "플러그인 창에 아이디와 비밀번호를 입력해 주세요.")
        return

    if hasattr(dock_widget, 'Vworld_status'):
        dock_widget.Vworld_status.setText("크롬 구동 중")
        dock_widget.Vworld_status.setStyleSheet("color: green;")
    QtWidgets.QApplication.processEvents()

    async def _run_login_only():
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("Playwright 미설치")
            return

        try:
            if not hasattr(dock_widget, '_playwright_instance') or not dock_widget._playwright_instance:
                dock_widget._playwright_instance = await async_playwright().start()

            context = getattr(dock_widget, "vworld_context", None)
            if context is not None:
                try:
                    page = await context.new_page()
                    browser = context.browser
                except Exception:
                    context = None

            if context is None:
                browser = await dock_widget._playwright_instance.chromium.launch(
                    **_chrome_launch_options(
                        headless=True,
                        args=[]
                    )
                )
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()

            dock_widget.vworld_browser = browser
            dock_widget.vworld_context = context
            dock_widget.vworld_page = page

            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("로그인 시도 중")
                dock_widget.Vworld_status.setStyleSheet("color: green")
            QtWidgets.QApplication.processEvents()

            await page.goto("https://www.vworld.kr/v4po_usrlogin_a001.do", wait_until="domcontentloaded")

            await page.wait_for_selector("#loginId", timeout=10000)
            await page.locator("#loginId").fill(user_id)
            await page.wait_for_timeout(100)

            await page.wait_for_selector("#loginPwd", timeout=5000)
            await page.locator("#loginPwd").fill(user_pw)
            await page.wait_for_timeout(100)

            button_selector = "button.bt.max.bg.primary"
            await page.click(button_selector)

            error_selector = "#dialogMsg .infotxt.msg"

            try:
                await page.wait_for_selector(error_selector, timeout=2500, state="visible")

                error_text = await page.locator(error_selector).inner_text()
                error_text = error_text.strip() if error_text else "로그인 정보가 올바르지 않습니다."

                if hasattr(dock_widget, 'Vworld_status'):
                    dock_widget.Vworld_status.setText(f"로그인 실패: {error_text}")
                    dock_widget.Vworld_status.setStyleSheet("color: red; font-weight: bold;")
                return

            except:
                if hasattr(dock_widget, 'Vworld_status'):
                    dock_widget.Vworld_status.setText("로그인 완료")
                    dock_widget.Vworld_status.setStyleSheet("color: blue; font-weight: bold;")


        except Exception as err:
            print(f"[ERROR] 백그라운드 로그인 실패: {err}")
            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("로그인 실패")
                dock_widget.Vworld_status.setStyleSheet("color: red;")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_run_login_only())
        else:
            loop.run_until_complete(_run_login_only())
            _ensure_playwright_event_pump(dock_widget, loop)
    except Exception as e:
        print(f"[ERROR] 루프 예외: {e}")


def vworld_backend_search(dock_widget):
    if not hasattr(dock_widget, 'vworld_context') or not dock_widget.vworld_context:
        QtWidgets.QMessageBox.warning(dock_widget, "경고", "먼저 로그인을 진행해 주세요.")
        return

    search_query = ""
    if hasattr(dock_widget, 'input_serch'):
        search_query = dock_widget.input_serch.text().strip()

    if not search_query:
        QtWidgets.QMessageBox.warning(dock_widget, "경고", "검색어를 입력해 주세요.")
        return

    if hasattr(dock_widget, 'Vworld_status'):
        dock_widget.Vworld_status.setText(f"'{search_query}' 검색 창 띄우는 중...")
        dock_widget.Vworld_status.setStyleSheet("color: black;")
    QtWidgets.QApplication.processEvents()

    async def _run_search_process():
        try:
            cookies = await dock_widget.vworld_context.cookies()

            download_path = _get_download_directory()
            profile_path = _get_vworld_chrome_profile_directory()
            target_x, target_y, target_w, target_h, has_other_monitor = get_opposite_monitor_geometry(dock_widget.iface)
            chrome_args = [
                f"--window-position={target_x},{target_y}",
                f"--window-size={target_w},{target_h}",
            ]
            if has_other_monitor:
                chrome_args.append("--start-maximized")

            visible_context = getattr(dock_widget, "vworld_visible_context", None)
            if visible_context is None:
                try:
                    await dock_widget.vworld_browser.close()
                except Exception:
                    pass

            new_context, page, _ = await get_or_create_service_browser(
                dock_widget,
                "VWorld",
                "vworld_visible_context",
                "vworld_browser",
                "vworld_page",
                chrome_args,
                accept_downloads=True,
                downloads_path=download_path,
            )

            await new_context.add_cookies(cookies)

            async def save_download_permanently(download):
                try:
                    completed_filename = download.suggested_filename
                    if native_download_enabled:
                        download_error = await download.failure()
                        if download_error:
                            raise RuntimeError(download_error)
                    else:
                        target_path = _unique_download_path(
                            download_path,
                            download.suggested_filename
                        )
                        await download.save_as(target_path)
                        completed_filename = os.path.basename(target_path)

                    print(f"[OK] {completed_filename} 다운로드 완료")
                    if hasattr(dock_widget, 'Vworld_status'):
                        dock_widget.Vworld_status.setText("다운로드 완료")
                        dock_widget.Vworld_status.setStyleSheet("color: blue; font-weight: bold;")
                except Exception as download_error:
                    print(f"[ERROR] 다운로드 저장 실패: {download_error}")
                    if hasattr(dock_widget, 'Vworld_status'):
                        dock_widget.Vworld_status.setText("다운로드 저장 실패")
                        dock_widget.Vworld_status.setStyleSheet("color: red; font-weight: bold;")

            native_download_enabled = False
            try:
                cdp_session = await new_context.new_cdp_session(page)
                await cdp_session.send(
                    "Browser.setDownloadBehavior",
                    {
                        "behavior": "allow",
                        "downloadPath": download_path,
                        "eventsEnabled": True,
                    }
                )
                native_download_enabled = True
            except Exception as cdp_error:
                print(f"[WARN] Chrome 기본 다운로드 설정 실패: {cdp_error}")

            page.on("download", save_download_permanently)

            dock_widget.vworld_browser = new_context.browser
            dock_widget.vworld_context = new_context
            dock_widget.vworld_visible_context = new_context
            dock_widget.vworld_page = page
            dock_widget.vworld_profile_path = profile_path

            await page.goto("https://www.vworld.kr/dtmk/dtmk_ntads_s001.do", wait_until="domcontentloaded")

            search_selector = "#searchKeyword"
            await page.wait_for_selector(search_selector, timeout=5000)
            await page.locator(search_selector).fill(search_query)
            await page.wait_for_timeout(200)

            await page.locator(search_selector).press("Enter")
            await page.wait_for_load_state("load")

            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("검색 완료 · 다운로드 대기 중")
                dock_widget.Vworld_status.setStyleSheet("color: blue; font-weight: bold;")

        except Exception as err:
            print(f"[ERROR] 검색 처리 중 실패: {err}")
            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("검색 실패")
                dock_widget.Vworld_status.setStyleSheet("color: red;")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_run_search_process())
        else:
            loop.run_until_complete(_run_search_process())
            _ensure_playwright_event_pump(dock_widget, loop)
    except Exception as e:
        print(f"[ERROR] 루프 예외: {e}")
