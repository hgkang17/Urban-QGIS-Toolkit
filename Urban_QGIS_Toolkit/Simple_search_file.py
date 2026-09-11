import os
import urllib.request
import urllib.parse
import json
from qgis.core import (
    QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsPointXY, QgsVectorLayer, QgsWkbTypes
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from qgis.PyQt.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from qgis.PyQt.QtCore import QTimer, Qt, QStringListModel
from qgis.PyQt.QtWidgets import (
    QCompleter, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QToolButton, QVBoxLayout,
)


_simple_address_click_tool = None


class SimpleAddressClickTool(QgsMapToolEmitPoint):

    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog
        self.iface = dialog.dock_widget.iface
        self._set_cross_cursor()
        self.canvasClicked.connect(self._read_address)

    def _set_cross_cursor(self):
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.setPen(QPen(Qt.GlobalColor.white, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(10, 10, 38, 38)
        painter.drawLine(10, 38, 38, 10)

        painter.setPen(QPen(Qt.GlobalColor.black, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(10, 10, 38, 38)
        painter.drawLine(10, 38, 38, 10)
        painter.end()
        self.setCursor(QCursor(pixmap, 24, 24))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.iface.actionPan().trigger()
            self.iface.mainWindow().statusBar().showMessage("주소 지점 선택이 취소되었습니다.", 3000)
            event.accept()
            return
        super().keyPressEvent(event)

    def _read_address(self, point, button):
        api_key = self.dialog.dock_widget.input_API.text().strip()
        if not api_key:
            self.iface.actionPan().trigger()
            return

        try:
            project_crs = QgsProject.instance().crs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            if project_crs.authid() == wgs84.authid():
                longitude, latitude = point.x(), point.y()
            else:
                transform = QgsCoordinateTransform(project_crs, wgs84, QgsProject.instance())
                transformed_point = transform.transform(point)
                longitude, latitude = transformed_point.x(), transformed_point.y()

            base_url = "https://api.vworld.kr/req/address?"
            params = {
                "service": "address",
                "request": "getaddress",
                "crs": "epsg:4326",
                "point": f"{longitude},{latitude}",
                "format": "json",
                "type": "parcel",
                "key": api_key,
            }
            base_params = urllib.parse.urlencode(params)
            url = base_url + base_params
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))

            if result.get("response", {}).get("status") != "OK":
                error_text = result.get("response", {}).get("error", {}).get("text", "주소를 찾을 수 없는 위치입니다.")
                self.iface.messageBar().pushWarning("주소 호출 실패", error_text)
                return

            address = result["response"]["result"][0]["text"]
            self.dialog.input_address.setText(address)
            _highlight_parcel(address, api_key, self.iface)
            self.dialog.raise_()
            self.dialog.activateWindow()
            self.iface.messageBar().pushSuccess("주소 호출 완료", address)
        except Exception as error:
            self.iface.messageBar().pushCritical("주소 호출 오류", str(error))
        finally:
            self.iface.actionPan().trigger()


def _highlight_parcel(address, api_key, iface):
    addr_type = "ROAD" if any(k in address for k in ["로 ", "길 "]) else "PARCEL"
    base_url = "https://api.vworld.kr/req/address?"
    params = {
        "service": "address",
        "version": "2.0",
        "request": "GetCoord",
        "format": "json",
        "type": addr_type,
        "address": address,
        "key": api_key,
        "crs": "epsg:4326",
    }

    base_params = urllib.parse.urlencode(params)
    url = base_url + base_params
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode('utf-8'))
        if data['response']['status'] != 'OK':
            print("[ERROR] 주소 검색 실패")
            return

        px = float(data['response']['result']['point']['x'])
        py = float(data['response']['result']['point']['y'])

    proj = QgsProject.instance()
    crs_wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    crs_3857 = QgsCoordinateReferenceSystem("EPSG:3857")
    point_wgs = QgsPointXY(px, py)

    transform_to_3857 = QgsCoordinateTransform(crs_wgs, crs_3857, proj)
    point_3857 = transform_to_3857.transform(point_wgs)
    cx, cy = point_3857.x(), point_3857.y()

    base_url = "https://api.vworld.kr/req/data?"
    params = {
        "service": "data",
        "request": "GetFeature",
        "data": "LP_PA_CBND_BUBUN",
        "geomFilter": f"POINT({cx} {cy})",
        "crs": "EPSG:3857",
        "key": api_key,
        "domain": "localhost",
    }
    base_params = urllib.parse.urlencode(params)
    url = base_url + base_params
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as res:
        res_data = json.loads(res.read().decode('utf-8'))

    if res_data.get('response', {}).get('status') != 'OK':
        print("알림: 해당 위치에 지적 데이터 없음")
        return

    features = res_data['response']['result']['featureCollection']['features']
    if not features:
        print("알림: 해당 위치에 지적 데이터 없음")
        return

    raw_json_str = json.dumps(res_data['response']['result']['featureCollection'])
    temp_layer = QgsVectorLayer(raw_json_str, "temp", "ogr")
    temp_layer.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    geom = next(temp_layer.getFeatures()).geometry()

    geom.transform(QgsCoordinateTransform(crs_3857, proj.crs(), proj))

    canvas = iface.mapCanvas()
    canvas.setCenter(geom.centroid().asPoint())
    canvas.zoomScale(1000)
    canvas.refresh()

    if hasattr(iface, '_parcel_rubber') and iface._parcel_rubber:
        iface._parcel_rubber.reset()

    iface._parcel_rubber = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
    iface._parcel_rubber.setColor(QColor(0, 0, 255, 50))
    iface._parcel_rubber.setStrokeColor(QColor(255, 0, 0, 255))
    iface._parcel_rubber.setWidth(3)
    iface._parcel_rubber.setToGeometry(geom, None)
    iface._parcel_rubber.show()

    canvas.unsetMapTool(canvas.mapTool())

    print("[OK] 필지 강조 완료")

    def remove_rubber():
        if hasattr(iface, '_parcel_rubber') and iface._parcel_rubber:
            iface._parcel_rubber.reset()
            iface._parcel_rubber = None

    QTimer.singleShot(10000, remove_rubber)


def _search_address_suggestions(raw_query, api_key):
    category = "road" if any(k in raw_query for k in ["로 ", "길 "]) else "parcel"
    query = raw_query.strip()

    base_url = "https://api.vworld.kr/req/search?"
    params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "crs": "EPSG:4326",
        "size": "10",
        "page": "1",
        "query": query,
        "type": "address",
        "category": category,
        "format": "json",
        "errorformat": "json",
        "key": api_key,
    }
    base_params = urllib.parse.urlencode(params)
    url = base_url + base_params
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[WARN] 주소 자동완성 요청 실패: {e}")
        return []

    if data.get('response', {}).get('status') != 'OK':
        return []

    items = data['response']['result'].get('items', [])
    addresses = [item['address'][category] for item in items if item.get('address', {}).get(category)]
    return list(dict.fromkeys(addresses))


def install_address_autocomplete(line_edit, api_key_getter):
    completer_model = QStringListModel(line_edit)
    completer = QCompleter(completer_model, line_edit)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
    completer.popup().setStyleSheet("""
        QListView {
            color: rgb(0, 0, 0);
            background-color: rgb(255, 255, 255);
            border: 1px solid rgb(180, 220, 250);
            outline: none;
            font-family: "Noto Sans KR";
            font-size: 9pt;
        }
        QListView::item {
            padding: 5px 8px;
        }
        QListView::item:selected {
            color: rgb(255, 255, 255);
            background-color: rgb(13, 27, 61);
        }
    """)
    line_edit.setCompleter(completer)

    debounce_timer = QTimer(line_edit)
    debounce_timer.setSingleShot(True)
    debounce_timer.setInterval(300)

    def update_suggestions():
        raw_text = line_edit.text()
        api_key = api_key_getter().strip() if api_key_getter else ""
        if len(raw_text.strip()) < 2 or not api_key:
            completer_model.setStringList([])
            return

        suggestions = _search_address_suggestions(raw_text, api_key)
        completer_model.setStringList(suggestions)
        if suggestions:
            completer.complete()

    def schedule_update(text):
        debounce_timer.stop()
        if len(text.strip()) >= 2:
            debounce_timer.start()
        else:
            completer_model.setStringList([])

    debounce_timer.timeout.connect(update_suggestions)
    line_edit.textEdited.connect(schedule_update)

    line_edit._address_completer_model = completer_model
    line_edit._address_completer = completer
    line_edit._address_debounce_timer = debounce_timer


class SimpleSearchDialog(QDialog):
    def __init__(self, iface, dock_widget, parent=None):
        super().__init__(parent)
        self.dock_widget = dock_widget
        self.iface = iface
        self.setWindowTitle("주소검색")
        self.setFixedWidth(450)
        self.setStyleSheet("""
            QDialog {
                background-color: rgb(42, 120, 214);
                font-family: "Noto Sans KR";
                font-size: 9pt;
            }
            QDialog QLabel {
                color: rgb(255, 255, 255);
                background: transparent;
                font-family: "Noto Sans KR";
            }
            QDialog QLineEdit {
                color: rgb(0, 0, 0);
                background-color: rgb(255, 255, 255);
                border: 1px solid rgb(180, 220, 250);
                border-radius: 4px;
                padding: 5px 8px;
                min-height: 20px;
                font-family: "Noto Sans KR";
            }
            QDialog QLineEdit:hover,
            QDialog QLineEdit:focus {
                border: 1px solid rgb(13, 27, 61);
            }
            QDialog QPushButton {
                color: rgb(13, 27, 61);
                background-color: rgb(255, 255, 255);
                border: 1px solid rgb(13, 27, 61);
                border-radius: 4px;
                padding: 6px 14px;
                min-width: 64px;
                font-family: "Noto Sans KR";
                font-weight: bold;
            }
            QDialog QPushButton:hover {
                color: rgb(13, 27, 61);
                background-color: rgb(225, 242, 255);
                border: 1px solid rgb(13, 27, 61);
            }
            QDialog QPushButton:pressed {
                color: rgb(255, 255, 255);
                background-color: rgb(13, 27, 61);
                border: 1px solid rgb(13, 27, 61);
            }
            QDialog QToolButton {
                color: rgb(13, 27, 61);
                background-color: rgb(255, 255, 255);
                border: 1px solid rgb(13, 27, 61);
                border-radius: 4px;
                padding: 3px;
            }
            QDialog QToolButton:hover {
                background-color: rgb(225, 242, 255);
            }
            QDialog QToolButton:pressed {
                background-color: rgb(13, 27, 61);
            }
        """)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("주소를 입력하세요"))

        input_row = QHBoxLayout()
        self.input_address = QLineEdit(self)
        self.input_address.returnPressed.connect(self._on_search)
        input_row.addWidget(self.input_address)

        self.btn_pick_address = QToolButton(self)
        self.btn_pick_address.setObjectName("btn_pick_address")
        self.btn_pick_address.setIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "pin.svg")))
        self.btn_pick_address.setToolTip("지도에서 지점을 선택해 주소 입력")
        self.btn_pick_address.setFixedSize(32, 32)
        self.btn_pick_address.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pick_address.clicked.connect(self._activate_address_picker)
        input_row.addWidget(self.btn_pick_address)

        self.btn_search = QPushButton("검색", self)
        self.btn_search.clicked.connect(self._on_search)
        input_row.addWidget(self.btn_search)

        layout.addLayout(input_row)

        install_address_autocomplete(
            self.input_address,
            lambda: self.dock_widget.input_API.text()
        )

    def _activate_address_picker(self):
        global _simple_address_click_tool

        api_key = self.dock_widget.input_API.text().strip()
        if not api_key:
            self.iface.messageBar().pushWarning("API 키 필요", "VWorld API 인증키를 입력해주세요.")
            return

        canvas = self.iface.mapCanvas()
        _simple_address_click_tool = SimpleAddressClickTool(canvas, self)
        canvas.setMapTool(_simple_address_click_tool)
        self.iface.mainWindow().statusBar().showMessage(
            "주소를 가져올 지도 위치를 한 번 클릭하세요. [ESC: 취소]"
        )

    def _on_search(self):
        address = self.input_address.text().strip()
        api_key = self.dock_widget.input_API.text().strip()

        if not address or not api_key:
            return

        _highlight_parcel(address, api_key, self.iface)


def open_simple_search(iface, dock_widget):
    dialog = SimpleSearchDialog(iface, dock_widget, dock_widget)
    dock_widget._simple_search_dialog = dialog
    dialog.show()
