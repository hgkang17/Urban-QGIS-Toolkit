import os
import re
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
    launch_options = _chrome_launch_options(
        headless=False,
        downloads_path=downloads_path,
        args=chrome_args,
    )
    browser = None
    try:
        context = await dock_widget._playwright_instance.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            no_viewport=True,
            accept_downloads=accept_downloads,
            **launch_options,
        )
        browser = context.browser
    except Exception as persistent_error:
        persistent_summary = str(persistent_error).splitlines()[0]
        print(
            "[WARN] Chrome 영구 프로필을 열지 못해 임시 자동화 창으로 전환합니다: "
            f"{persistent_summary}"
        )
        browser = await dock_widget._playwright_instance.chromium.launch(
            **launch_options,
        )
        context = await browser.new_context(
            no_viewport=True,
            accept_downloads=accept_downloads,
        )

    page = context.pages[0] if context.pages else await context.new_page()
    setattr(dock_widget, context_attr, context)
    setattr(dock_widget, browser_attr, browser)
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


def _plain_text(html_text):
    text = re.sub(r"<br\s*/?>", " ", html_text or "", flags=re.IGNORECASE)
    return re.sub(r"<[^>]+>", "", text).strip()


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

        browser = None
        login_ok = False
        try:
            if not hasattr(dock_widget, '_playwright_instance') or not dock_widget._playwright_instance:
                dock_widget._playwright_instance = await async_playwright().start()

            old_login_browser = getattr(dock_widget, "vworld_login_browser", None)
            if old_login_browser is not None:
                try:
                    await old_login_browser.close()
                except Exception:
                    pass
            else:
                old_context = getattr(dock_widget, "vworld_context", None)
                if old_context is not None and old_context is not getattr(dock_widget, "vworld_visible_context", None):
                    try:
                        await dock_widget.vworld_browser.close()
                    except Exception:
                        pass
            dock_widget.vworld_context = None
            dock_widget.vworld_login_browser = None
            dock_widget.vworld_login_context = None
            dock_widget.vworld_login_page = None

            browser = await dock_widget._playwright_instance.chromium.launch(
                **_chrome_launch_options(
                    headless=True,
                    args=[]
                )
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True,
            )
            page = await context.new_page()

            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("로그인 시도 중")
                dock_widget.Vworld_status.setStyleSheet("color: green")
            QtWidgets.QApplication.processEvents()

            await page.goto("https://www.vworld.kr/v4po_usrlogin_a001.do", wait_until="domcontentloaded")

            try:
                await page.wait_for_selector("#loginId", timeout=10000)
            except Exception:
                raise RuntimeError(f"로그인 입력칸을 찾지 못했습니다 (현재 페이지: {await page.title()} / {page.url})")
            await page.locator("#loginId").fill(user_id)
            await page.wait_for_timeout(100)

            await page.wait_for_selector("#loginPwd", timeout=5000)
            await page.locator("#loginPwd").fill(user_pw)
            await page.wait_for_timeout(100)

            login_result = {}

            async def capture_login_result(route):
                response = await route.fetch()
                try:
                    login_result.update((await response.json()).get("resultMap") or {})
                except Exception:
                    pass
                await route.fulfill(response=response)

            await page.route(lambda url: "v4po_usrlogin_a004.do" in url, capture_login_result)

            button_selector = "button.bt.max.bg.primary"
            async with page.expect_response(lambda r: "v4po_usrlogin_a004.do" in r.url, timeout=10000):
                await page.click(button_selector)
            result = login_result.get("result")
            message = _plain_text(login_result.get("msg"))

            if result == "success":
                await page.wait_for_timeout(1500)
                await page.wait_for_load_state("load")
                login_ok = True

                dock_widget.vworld_browser = browser
                dock_widget.vworld_context = context
                dock_widget.vworld_page = page
                dock_widget.vworld_login_browser = browser
                dock_widget.vworld_login_context = context
                dock_widget.vworld_login_page = page

                if hasattr(dock_widget, 'Vworld_status'):
                    dock_widget.Vworld_status.setText("로그인 완료")
                    dock_widget.Vworld_status.setStyleSheet("color: blue; font-weight: bold;")
            elif result == "error":
                print(f"[ERROR] 브이월드 로그인 실패: {message}")
                if hasattr(dock_widget, 'Vworld_status'):
                    dock_widget.Vworld_status.setText("로그인 실패: 아이디·비밀번호 확인")
                    dock_widget.Vworld_status.setStyleSheet("color: red; font-weight: bold;")
            elif not result:
                print("[ERROR] 브이월드 로그인 결과를 확인하지 못했습니다.")
                if hasattr(dock_widget, 'Vworld_status'):
                    dock_widget.Vworld_status.setText("로그인 실패")
                    dock_widget.Vworld_status.setStyleSheet("color: red;")
            else:
                print(f"[WARN] 브이월드 안내: {message}")
                print("[WARN] 브이월드 사이트(https://www.vworld.kr)에서 직접 로그인해 안내에 따라 처리한 뒤 다시 로그인하세요.")
                if hasattr(dock_widget, 'Vworld_status'):
                    dock_widget.Vworld_status.setText("비밀번호 변경 필요 (사이트)")
                    dock_widget.Vworld_status.setStyleSheet("color: red; font-weight: bold;")

        except Exception as err:
            print(f"[ERROR] 백그라운드 로그인 실패: {err}")
            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("로그인 실패")
                dock_widget.Vworld_status.setStyleSheet("color: red;")

        finally:
            if not login_ok and browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_run_login_only())
        else:
            loop.run_until_complete(_run_login_only())
            _ensure_playwright_event_pump(dock_widget, loop)
    except Exception as e:
        print(f"[ERROR] 루프 예외: {e}")


def vworld_backend_search(
    dock_widget,
    search_query_override=None,
    after_search=None,
    download_directory_override=None,
):
    if not hasattr(dock_widget, 'vworld_context') or not dock_widget.vworld_context:
        QtWidgets.QMessageBox.warning(dock_widget, "경고", "먼저 로그인을 진행해 주세요.")
        return

    search_query = (search_query_override or "").strip()
    if not search_query and hasattr(dock_widget, 'input_search_vworld'):
        search_query = dock_widget.input_search_vworld.text().strip()

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

            download_path = (
                os.path.abspath(download_directory_override)
                if download_directory_override
                else _get_download_directory()
            )
            os.makedirs(download_path, exist_ok=True)
            profile_path = _get_vworld_chrome_profile_directory()
            target_x, target_y, target_w, target_h, has_other_monitor = get_opposite_monitor_geometry(dock_widget.iface)
            chrome_args = [
                f"--window-position={target_x},{target_y}",
                f"--window-size={target_w},{target_h}",
            ]
            if has_other_monitor:
                chrome_args.append("--start-maximized")


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

            if after_search is None:
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

            if after_search is not None:
                await after_search(new_context, page)

        except Exception as err:
            print(f"[ERROR] 검색 처리 중 실패: {err}")
            if hasattr(dock_widget, 'Vworld_status'):
                dock_widget.Vworld_status.setText("검색 실패")
                dock_widget.Vworld_status.setStyleSheet("color: red;")
            if after_search is not None:
                status_label = getattr(dock_widget, "elevation_status", None)
                if status_label is not None:
                    status_label.setText(f"실패: {err}")
                    status_label.setStyleSheet("color: rgb(180, 45, 45);")
                run_button = getattr(dock_widget, "elevation_run_button", None)
                if run_button is not None:
                    run_button.setEnabled(True)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_run_search_process())
        else:
            loop.run_until_complete(_run_search_process())
            _ensure_playwright_event_pump(dock_widget, loop)
    except Exception as e:
        print(f"[ERROR] 루프 예외: {e}")


def vworld_download_named_file(
    dock_widget,
    filename,
    output_directory,
    completed_callback=None,
):
    if not getattr(dock_widget, "vworld_context", None):
        QtWidgets.QMessageBox.warning(
            dock_widget,
            "브이월드 로그인 필요",
            "먼저 VWorld API 호출 탭에서 브이월드 로그인을 진행해 주세요.",
        )
        return False

    filename = os.path.basename(str(filename).strip())
    if not filename:
        QtWidgets.QMessageBox.warning(dock_widget, "입력 확인", "다운로드 파일명이 비어 있습니다.")
        return False

    output_directory = os.path.abspath(output_directory)
    os.makedirs(output_directory, exist_ok=True)

    async def _download_in_background():
        try:
            context = getattr(dock_widget, "vworld_login_context", None)
            page = getattr(dock_widget, "vworld_login_page", None)

            if context is not None:
                try:
                    await context.cookies()
                except Exception:
                    context = None
                    page = None

            if context is None:
                source_context = getattr(dock_widget, "vworld_context", None)
                if source_context is None:
                    raise RuntimeError("브이월드 로그인이 필요합니다.")

                storage_state = await source_context.storage_state()
                browser = await dock_widget._playwright_instance.chromium.launch(
                    **_chrome_launch_options(headless=True, args=[])
                )
                context = await browser.new_context(
                    storage_state=storage_state,
                    viewport={'width': 1920, 'height': 1080},
                    accept_downloads=True,
                )
                page = await context.new_page()
                dock_widget.vworld_login_browser = browser
                dock_widget.vworld_login_context = context
                dock_widget.vworld_login_page = page
            elif page is None or page.is_closed():
                page = await context.new_page()
                dock_widget.vworld_login_page = page

            try:
                cdp_session = await context.new_cdp_session(page)
                await cdp_session.send(
                    "Browser.setDownloadBehavior",
                    {
                        "behavior": "allow",
                        "downloadPath": output_directory,
                        "eventsEnabled": True,
                    },
                )
            except Exception as cdp_error:
                print(f"[WARN] 백그라운드 Chrome 다운로드 경로 설정 실패: {cdp_error}")

            if hasattr(dock_widget, "Vworld_status"):
                dock_widget.Vworld_status.setText("백그라운드에서 표고 자료 찾는 중")
                dock_widget.Vworld_status.setStyleSheet("color: black;")

            base_url = (
                "https://www.vworld.kr/dtmk/dtmk_ntads_s002.do"
                "?datIde=30205&dsId=30205&datPageSize=100"
                "&searchKeyword=%EC%88%98%EC%B9%98%EC%A7%80%ED%98%95%EB%8F%84"
                "&svcCde=MK&datPageIndex={}"
            )

            download_button = None
            target_item = None
            for page_number in range(1, 5):
                await page.goto(
                    base_url.format(page_number),
                    wait_until="domcontentloaded",
                )
                await page.wait_for_selector(
                    "article article ul > li",
                    state="attached",
                    timeout=15000,
                )
                item = page.locator("article article ul > li").filter(
                    has_text=filename
                ).first
                if await item.count():
                    target_item = item
                    download_button = item.get_by_role(
                        "button", name="다운로드", exact=True
                    )
                    break

            if target_item is None or download_button is None:
                raise RuntimeError(f"VWorld 파일 목록에서 찾지 못했습니다: {filename}")

            onclick_text = await download_button.get_attribute("onclick") or ""
            size_match = re.search(r"download\([^,]+,[^,]+,\s*['\"]?(\d+)", onclick_text)
            file_size_kb = int(size_match.group(1)) if size_match else 0

            files_before = {}
            for existing_name in os.listdir(output_directory):
                existing_path = os.path.join(output_directory, existing_name)
                if os.path.isfile(existing_path):
                    stat = os.stat(existing_path)
                    files_before[existing_name] = (stat.st_mtime_ns, stat.st_size)
            target_path = _unique_download_path(output_directory, filename)

            async with page.expect_download(timeout=120000) as download_info:
                if file_size_kb > 512000:
                    checkbox = target_item.locator("input[name='chkDs']")
                    await checkbox.check(force=True)
                    await page.get_by_role(
                        "button", name="선택다운로드", exact=True
                    ).click()
                else:
                    await download_button.click()

            download = await download_info.value
            download_error = await download.failure()
            if download_error:
                raise RuntimeError(download_error)

            native_candidates = []
            for current_name in os.listdir(output_directory):
                current_path = os.path.join(output_directory, current_name)
                if not os.path.isfile(current_path):
                    continue
                stat = os.stat(current_path)
                current_signature = (stat.st_mtime_ns, stat.st_size)
                if files_before.get(current_name) != current_signature:
                    native_candidates.append((stat.st_mtime_ns, current_path))

            if native_candidates:
                _, native_path = max(native_candidates)
                if os.path.normcase(native_path) != os.path.normcase(target_path):
                    os.replace(native_path, target_path)
            else:
                await download.save_as(target_path)

            print(f"[OK] VWorld 자동 다운로드 완료: {target_path}")
            if hasattr(dock_widget, "Vworld_status"):
                dock_widget.Vworld_status.setText("표고 자료 다운로드 완료")
                dock_widget.Vworld_status.setStyleSheet(
                    "color: blue; font-weight: bold;"
                )
            if completed_callback is not None:
                completed_callback(target_path)

        except Exception as error:
            print(f"[ERROR] VWorld 지정 파일 다운로드 실패: {error}")
            if hasattr(dock_widget, "Vworld_status"):
                dock_widget.Vworld_status.setText("표고 자료 다운로드 실패")
                dock_widget.Vworld_status.setStyleSheet(
                    "color: red; font-weight: bold;"
                )
            status_label = getattr(dock_widget, "elevation_status", None)
            if status_label is not None:
                status_label.setText(f"실패: {error}")
                status_label.setStyleSheet("color: rgb(180, 45, 45);")
            run_button = getattr(dock_widget, "elevation_run_button", None)
            if run_button is not None:
                run_button.setEnabled(True)

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_download_in_background())
        if not loop.is_running():
            _ensure_playwright_event_pump(dock_widget, loop)
    except Exception as error:
        print(f"[ERROR] 백그라운드 다운로드 루프 예외: {error}")
        status_label = getattr(dock_widget, "elevation_status", None)
        if status_label is not None:
            status_label.setText(f"실패: {error}")
            status_label.setStyleSheet("color: rgb(180, 45, 45);")
        run_button = getattr(dock_widget, "elevation_run_button", None)
        if run_button is not None:
            run_button.setEnabled(True)
    return True


def vworld_download_matching_file(
    dock_widget,
    dataset_id,
    filename_regex,
    output_directory,
    save_name_builder=None,
    result_callback=None,
    max_pages=5,
    skip_existing=True,
    check_only=False,
):
    def report(**result):
        if result_callback is not None:
            result_callback(result)

    if not getattr(dock_widget, "vworld_context", None):
        report(status="failed", error="브이월드 로그인이 필요합니다.")
        return False

    pattern = re.compile(filename_regex)
    output_directory = os.path.abspath(output_directory)
    if not check_only:
        os.makedirs(output_directory, exist_ok=True)
    detail_url = (
        "https://www.vworld.kr/dtmk/dtmk_ntads_s002.do"
        f"?datIde={dataset_id}&dsId={dataset_id}&datPageSize=100"
        "&svcCde=MK&datPageIndex={}"
    )

    async def _download_matching():
        try:
            context = getattr(dock_widget, "vworld_login_context", None)
            page = getattr(dock_widget, "vworld_login_page", None)
            if context is not None:
                try:
                    await context.cookies()
                except Exception:
                    context = None
                    page = None
            if context is None:
                source_context = getattr(dock_widget, "vworld_context", None)
                if source_context is None:
                    raise RuntimeError("브이월드 로그인이 필요합니다.")
                storage_state = await source_context.storage_state()
                browser = await dock_widget._playwright_instance.chromium.launch(
                    **_chrome_launch_options(headless=True, args=[])
                )
                context = await browser.new_context(
                    storage_state=storage_state,
                    viewport={'width': 1920, 'height': 1080},
                    accept_downloads=True,
                )
                page = await context.new_page()
                dock_widget.vworld_login_browser = browser
                dock_widget.vworld_login_context = context
                dock_widget.vworld_login_page = page
            elif page is None or page.is_closed():
                page = await context.new_page()
                dock_widget.vworld_login_page = page

            try:
                cdp_session = await context.new_cdp_session(page)
                await cdp_session.send(
                    "Browser.setDownloadBehavior",
                    {"behavior": "allow", "downloadPath": output_directory, "eventsEnabled": True},
                )
            except Exception as cdp_error:
                print(f"[WARN] 백그라운드 Chrome 다운로드 경로 설정 실패: {cdp_error}")

            candidates = []
            for page_number in range(1, max_pages + 1):
                await page.goto(detail_url.format(page_number), wait_until="domcontentloaded")
                try:
                    await page.wait_for_selector(
                        "article article ul > li", state="attached", timeout=15000
                    )
                except Exception:
                    break
                texts = await page.locator("article article ul > li").evaluate_all(
                    "els => els.map(e => e.innerText)"
                )
                file_rows = 0
                for text in texts:
                    name_match = re.search(r"([0-9A-Za-z_가-힣().\-]+\.zip)", text)
                    if not name_match:
                        continue
                    file_rows += 1
                    name = name_match.group(1)
                    if not pattern.fullmatch(name):
                        continue
                    date_match = re.search(r"기준일\s*(\d{4}-\d{2}(?:-\d{2})?)", text)
                    base_date = date_match.group(1) if date_match else ""
                    candidates.append((base_date, name, page_number))
                if file_rows < 100:
                    break

            if not candidates:
                report(status="not_found")
                return

            base_date, filename, page_number = max(candidates)
            if check_only:
                report(status="available", filename=filename, base_date=base_date)
                return
            save_name = save_name_builder(filename, base_date) if save_name_builder else filename
            target_path = os.path.join(output_directory, save_name)
            if skip_existing and os.path.isfile(target_path):
                report(status="skipped", path=target_path, filename=filename, base_date=base_date)
                return

            await page.goto(detail_url.format(page_number), wait_until="domcontentloaded")
            await page.wait_for_selector("article article ul > li", state="attached", timeout=15000)
            target_item = page.locator("article article ul > li").filter(has_text=filename).first
            if not await target_item.count():
                raise RuntimeError(f"다운로드 직전에 목록에서 파일이 사라졌습니다: {filename}")
            download_button = target_item.get_by_role("button", name="다운로드", exact=True)
            onclick_text = await download_button.get_attribute("onclick") or ""
            size_match = re.search(r"download\([^,]+,[^,]+,\s*['\"]?(\d+)", onclick_text)
            file_size_kb = int(size_match.group(1)) if size_match else 0

            files_before = {}
            for existing_name in os.listdir(output_directory):
                existing_path = os.path.join(output_directory, existing_name)
                if os.path.isfile(existing_path):
                    stat = os.stat(existing_path)
                    files_before[existing_name] = (stat.st_mtime_ns, stat.st_size)

            async with page.expect_download(timeout=300000) as download_info:
                if file_size_kb > 512000:
                    await target_item.locator("input[name='chkDs']").check(force=True)
                    await page.get_by_role("button", name="선택다운로드", exact=True).click()
                else:
                    await download_button.click()
            download = await download_info.value
            download_error = await download.failure()
            if download_error:
                raise RuntimeError(download_error)

            native_candidates = []
            for current_name in os.listdir(output_directory):
                current_path = os.path.join(output_directory, current_name)
                if not os.path.isfile(current_path):
                    continue
                stat = os.stat(current_path)
                if files_before.get(current_name) != (stat.st_mtime_ns, stat.st_size):
                    native_candidates.append((stat.st_mtime_ns, current_path))
            if native_candidates:
                _, native_path = max(native_candidates)
                if os.path.normcase(native_path) != os.path.normcase(target_path):
                    os.replace(native_path, target_path)
            else:
                await download.save_as(target_path)

            print(f"[OK] VWorld 다운로드 완료: {target_path}")
            report(status="downloaded", path=target_path, filename=filename, base_date=base_date)
        except Exception as error:
            print(f"[ERROR] VWorld 자료 다운로드 실패({dataset_id}): {error}")
            report(status="failed", error=str(error))

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_download_matching())
        if not loop.is_running():
            _ensure_playwright_event_pump(dock_widget, loop)
    except Exception as error:
        print(f"[ERROR] 백그라운드 다운로드 루프 예외: {error}")
        report(status="failed", error=str(error))
        return False
    return True
