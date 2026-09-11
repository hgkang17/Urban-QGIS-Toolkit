import urllib.request
import urllib.parse
import json
from qgis.core import *
from qgis.gui import QgsRubberBand
from qgis.PyQt import QtGui
from qgis.PyQt.QtCore import QTimer


def show_Shading_on_map(iface, dock_widget):
    addr_eum = dock_widget.input_search_eum.text().strip()
    addr_kakao = dock_widget.input_search_kakao.text().strip()
    api_key = dock_widget.input_API.text().strip()

    address = addr_eum if addr_eum else addr_kakao

    if not address or not api_key:
        return

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
        "crs": "EPSG:4326",
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

    project = QgsProject.instance()
    prj_crs = project.crs()
    crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
    transform_setting = QgsCoordinateTransform(crs_4326, prj_crs, QgsProject.instance())


    lon, lat = px, py


    base_url = "https://api.vworld.kr/req/data?"
    params = {
        "service": "data",
        "request": "GetFeature",
        "data": "LP_PA_CBND_BUBUN",
        "geomFilter": f"POINT({lon} {lat})",
        "crs": "EPSG:4326",
        "key": api_key,
        "domain": "localhost",
    }
    base_params = urllib.parse.urlencode(params)
    url = base_url + base_params
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as res:
        res_data = json.loads(res.read().decode('utf-8'))

    if res_data.get('response', {}).get('status') == 'OK':
        features = res_data['response']['result']['featureCollection']['features']
        if features:
            raw_json_str = json.dumps(res_data['response']['result']['featureCollection'])
            temp_layer = QgsVectorLayer(raw_json_str, "temp", "ogr")
            geom = next(temp_layer.getFeatures()).geometry()

            geom.transform(transform_setting)

            canvas = iface.mapCanvas()
            canvas.setCenter(geom.centroid().asPoint())
            canvas.zoomScale(1000)
            canvas.refresh()

            if hasattr(iface, '_parcel_rubber') and iface._parcel_rubber:
                iface._parcel_rubber.reset()

            iface._parcel_rubber = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
            iface._parcel_rubber.setColor(QtGui.QColor(0, 0, 255, 50))
            iface._parcel_rubber.setStrokeColor(QtGui.QColor(255, 0, 0, 255))
            iface._parcel_rubber.setWidth(3)
            iface._parcel_rubber.setToGeometry(geom, None)
            iface._parcel_rubber.show()

            canvas.unsetMapTool(canvas.mapTool())

            print("[OK] 필지 강조 완료")
        else:
            print("알림: 해당 위치에 지적 데이터 없음")

    def remove_rubber():
        if hasattr(iface, '_parcel_rubber') and iface._parcel_rubber:
            iface._parcel_rubber.reset()
            iface._parcel_rubber = None


            try:
                iface.mapCanvas().mapCanvasClicked.disconnect(clear_rubber_band)
            except:
                pass

    QTimer.singleShot(10000, remove_rubber)

