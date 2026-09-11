import json
import asyncio
import urllib.request
import urllib.parse
from qgis.PyQt import QtWidgets, QtGui, QtCore
from qgis.gui import *
from qgis.core import (
    QgsCoordinateTransform, QgsProject, QgsCoordinateReferenceSystem,
    Qgis, QgsVectorLayer, QgsWkbTypes
)
from qgis.PyQt.QtCore import QTimer
from .vworld_login import (
    _chrome_launch_options,
    _ensure_playwright_event_pump,
    get_or_create_service_browser,
    get_service_chrome_profile_directory,
    get_opposite_monitor_geometry,
)

_active_click_tool = None

class AddressClickTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, dock_widget, mode):
        super().__init__(canvas)
        self.canvas = canvas
        self.dock_widget = dock_widget
        self.iface = dock_widget.iface
        self.mode = mode
        self.rubber = None
        self.setCustomXCursor()
        self.canvasClicked.connect(self.process_click_to_address)

    def setCustomXCursor(self):
        pixmap = QtGui.QPixmap(48, 48)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        white_pen = QtGui.QPen(QtCore.Qt.GlobalColor.white, 6, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(white_pen)
        painter.drawLine(10, 10, 38, 38)
        painter.drawLine(10, 38, 38, 10)
        black_pen = QtGui.QPen(QtCore.Qt.GlobalColor.black, 3, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(black_pen)
        painter.drawLine(10, 10, 38, 38)
        painter.drawLine(10, 38, 38, 10)
        painter.end()
        self.setCursor(QtGui.QCursor(pixmap, 24, 24))

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Escape:


            self.iface.actionPan().trigger()

            if hasattr(self.dock_widget, 'eum_kakao_status'):
                self.dock_widget.eum_kakao_status.setText("검색 취소됨")
                self.dock_widget.eum_kakao_status.setStyleSheet("color: gray;")

            mode_title = "토지이음" if self.mode == "eum" else "카카오맵"
            self.iface.mainWindow().statusBar().showMessage(f"{mode_title} 좌표 지정이 취소되었습니다.")
            event.accept()
        else:
            super().keyPressEvent(event)


    def remove_rubber(self, dock_widget):
        if hasattr(dock_widget, '_parcel_rubber') and dock_widget._parcel_rubber:
            dock_widget._parcel_rubber.reset()
            dock_widget._parcel_rubber = None

    def restore_qgis_focus(self):
        qgis_window = self.iface.mainWindow()
        qgis_window.setWindowState(
            (qgis_window.windowState() & ~QtCore.Qt.WindowState.WindowMinimized)
            | QtCore.Qt.WindowState.WindowActive
        )
        qgis_window.raise_()
        qgis_window.activateWindow()
        self.canvas.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)


    def process_click_to_address(self, point, button):
        self.iface.mapCanvas().setCenter(point)
        self.iface.mapCanvas().zoomScale(1000)


        vworld_key = ""
        if hasattr(self.dock_widget, 'input_API') and self.dock_widget.input_API:
            vworld_key = self.dock_widget.input_API.text().strip()

        if not vworld_key:
            QtWidgets.QMessageBox.warning(self.dock_widget, "경고", "브이월드 API 인증키를 입력해 주세요.")
            if hasattr(self.dock_widget, 'eum_kakao_status'):
                self.dock_widget.eum_kakao_status.setText("API 키 누락")
                self.dock_widget.eum_kakao_status.setStyleSheet("color: orange;")
            return

        project = QgsProject.instance()
        prj_crs = project.crs()
        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        transform_setting = QgsCoordinateTransform(prj_crs, crs_4326, QgsProject.instance())
        transform_prj_crs = QgsCoordinateTransform(crs_4326, prj_crs, QgsProject.instance())

        if prj_crs.authid() == crs_4326.authid():
            lon = point.x()
            lat = point.y()
        else:
            lon_lat_point = transform_setting.transform(point)
            lon = lon_lat_point.x()
            lat = lon_lat_point.y()


        base_url = "https://api.vworld.kr/req/address?"
        params = {
            "service": "address",
            "request": "getaddress",
            "crs": "epsg:4326",
            "point": f"{lon},{lat}",
            "format": "json",
            "type": "parcel",
            "key": vworld_key
        }
        base_params = urllib.parse.urlencode(params)
        url = base_url + base_params

        search_query = ""
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=10) as response:
                res_json = json.loads(response.read().decode("utf-8"))
            if res_json.get("response", {}).get("status") == "OK":
                search_query = res_json["response"]["result"][0]["text"]
                mode_title = "토지이음" if self.mode == "eum" else "카카오맵"
                self.iface.messageBar().pushMessage(
                    "📍 선택 지점 주소 호출 완료 ",
                    f" : {search_query} ({mode_title} 실행 검색합니다.)",
                    level=Qgis.MessageLevel.Success,
                    duration=4
                )
            else:
                error_msg = res_json.get("response", {}).get("error", {}).get("text", "주소를 찾을 수 없는 위치입니다.")
                QtWidgets.QMessageBox.warning(self.dock_widget,"알림", f"{error_msg}\n올바른 인증키를 입력하세요")
                return
        except Exception as e:
            self.iface.messageBar().pushMessage("❌ 시스템 에러", str(e), level=Qgis.MessageLevel.Critical, duration=5)
            return

        if self.mode == "eum":
            if hasattr(self.dock_widget, 'input_search_eum') and self.dock_widget.input_search_eum:
                self.dock_widget.input_search_eum.setText(search_query)
        elif self.mode == "kakao":
            if hasattr(self.dock_widget, 'input_search_kakao') and self.dock_widget.input_search_kakao:
                self.dock_widget.input_search_kakao.setText(search_query)

        if search_query:
            try:
                base_url = "https://api.vworld.kr/req/data?"
                params = {
                    "service": "data",
                    "request": "GetFeature",
                    "data": "LP_PA_CBND_BUBUN",
                    "geomFilter": f"POINT({lon} {lat})",
                    "crs": "EPSG:4326",
                    "key": vworld_key,
                    "domain": "localhost",
                }
                base_params = urllib.parse.urlencode(params)
                url = base_url + base_params
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=10) as api_response:
                    res_data = json.loads(api_response.read().decode('utf-8'))

                if 'response' in res_data and res_data['response'].get('status') == 'OK':
                    features = res_data['response']['result']['featureCollection']['features']
                    if features:
                        raw_json_str = json.dumps(res_data['response']['result']['featureCollection'])
                        temp_layer = QgsVectorLayer(raw_json_str, "temp", "ogr")
                        geom = next(temp_layer.getFeatures()).geometry()

                        geom.transform(transform_prj_crs)

                        if hasattr(self.dock_widget, '_parcel_rubber') and self.dock_widget._parcel_rubber:
                            self.dock_widget._parcel_rubber.reset()
                        self.dock_widget._parcel_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
                        self.dock_widget._parcel_rubber.setColor(QtGui.QColor(0, 0, 255, 50))
                        self.dock_widget._parcel_rubber.setStrokeColor(QtGui.QColor(255, 0, 0, 255))
                        self.dock_widget._parcel_rubber.setWidth(3)
                        self.dock_widget._parcel_rubber.setToGeometry(geom, None)
                        self.dock_widget._parcel_rubber.show()
                        QTimer.singleShot(10000, lambda: self.remove_rubber(self.dock_widget))
                        self.iface.mainWindow().statusBar().showMessage(f"🎯 [필지 표시 완료] {search_query}", 10000)
                    else:
                        print("해당 클릭 지점에 유효한 지적 데이터가 없습니다.")
            except Exception as e:
                print(f"[ERROR] 강조 로직 오류: {e}")


        if search_query:
            if hasattr(self.dock_widget, 'eum_kakao_status'):
                self.dock_widget.eum_kakao_status.setText("크롬 구동 중...")
                self.dock_widget.eum_kakao_status.setStyleSheet("color: green;")
            QtWidgets.QApplication.processEvents()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._run_browser_search(search_query))
                else:
                    loop.run_until_complete(self._run_browser_search(search_query))
                    _ensure_playwright_event_pump(self.dock_widget, loop)
            except Exception as e:
                print(f"[ERROR] 루프 예외 발생: {e}")


    async def _run_browser_search(self, search_query):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            if hasattr(self.dock_widget, 'eum_kakao_status'):
                self.dock_widget.eum_kakao_status.setText("Playwright 미설치")
            return

        try:
            target_x, target_y, target_w, target_h, has_other_monitor = get_opposite_monitor_geometry(self.iface)

            if not hasattr(self.dock_widget, '_playwright_instance') or not self.dock_widget._playwright_instance:
                from playwright.async_api import async_playwright
                self.dock_widget._playwright_instance = await async_playwright().start()

            chrome_args = [
                f"--window-position={target_x},{target_y}",
                f"--window-size={target_w},{target_h}",
            ]

            if has_other_monitor:
                chrome_args.append("--start-maximized")

            context_attr = f"{self.mode}_browser_context"
            service_name = "Eum" if self.mode == "eum" else "Kakao"
            new_context, page, _ = await get_or_create_service_browser(
                self.dock_widget,
                service_name,
                context_attr,
                f"{self.mode}_browser",
                f"{self.mode}_page",
                chrome_args,
                accept_downloads=True,
            )

            if self.mode == "eum":
                target_url = "https://eum.go.kr/web/mp/mpMapDet.jsp"
                search_input_selector = ".map_header input[type='text']"
                first_item_selector = "ul.scrollbar-outer > li:first-child"
            elif self.mode == "kakao":
                target_url = "https://map.kakao.com"
                search_input_selector = "#search\.keyword\.query"
                first_item_selector = ".AddressSection .item:first-child"

            await page.goto(target_url, wait_until="domcontentloaded")

            await page.wait_for_selector(search_input_selector, state="visible", timeout=10000)
            await page.locator(search_input_selector).fill(search_query)

            try:
                await page.wait_for_selector(first_item_selector, state="visible", timeout=1200)
                await page.locator(first_item_selector).click()
                print(f"[OK] {self.mode.upper()} 자동완성 첫 번째 항목을 클릭했습니다.")
                await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"[WARN] 자동완성 레이어 유실 또는 클릭 실패 (엔터 키 우회 진입): {e}")
                await page.locator(search_input_selector).press("Enter")
                await page.wait_for_timeout(1000)

            setattr(self.dock_widget, context_attr, new_context)
            setattr(self.dock_widget, f"{self.mode}_browser", new_context.browser)
            setattr(self.dock_widget, f"{self.mode}_page", page)

            if hasattr(self.dock_widget, 'eum_kakao_status'):
                self.dock_widget.eum_kakao_status.setText("주소 검색 완료")
                self.dock_widget.eum_kakao_status.setStyleSheet("color: blue; font-weight: bold;")

            if self.mode == "eum":
                self.restore_qgis_focus()
                QTimer.singleShot(500, self.restore_qgis_focus)

        except Exception as err:
            print(f"[ERROR] 매크로 런타임 실패: {err}")
            if hasattr(self.dock_widget, 'eum_kakao_status'):
                self.dock_widget.eum_kakao_status.setText("검색 실패")
                self.dock_widget.eum_kakao_status.setStyleSheet("color: red;")


def function_point_eum(iface, dock_widget):
    global _active_click_tool
    canvas = iface.mapCanvas()
    if canvas is None: return

    _active_click_tool = AddressClickTool(canvas, dock_widget, mode="eum")
    canvas.setMapTool(_active_click_tool)


    if hasattr(dock_widget, 'eum_kakao_status'):
        dock_widget.eum_kakao_status.setText("토지이음 맵 클릭 활성")
        dock_widget.eum_kakao_status.setStyleSheet("color: green;")
    iface.mainWindow().statusBar().showMessage("토지이음 좌표 지정 툴이 활성화되었습니다. [맵 1회 클릭] 또는 [ESC: 취소]")


def function_point_kakao(iface, dock_widget):
    global _active_click_tool
    canvas = iface.mapCanvas()
    if canvas is None: return

    _active_click_tool = AddressClickTool(canvas, dock_widget, mode="kakao")
    canvas.setMapTool(_active_click_tool)

    if hasattr(dock_widget, 'eum_kakao_status'):
        dock_widget.eum_kakao_status.setText("카카오맵 맵 클릭 활성")
        dock_widget.eum_kakao_status.setStyleSheet("color: green;")
    iface.mainWindow().statusBar().showMessage("카카오맵 좌표 지정 툴이 활성화되었습니다. [맵 1회 클릭] 또는 [ESC: 취소]")
