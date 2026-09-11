import os
import re
import json
import urllib.error
import urllib.parse
import urllib.request
import random
from qgis.core import *
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtGui import QColor
from qgis.PyQt import QtGui
from .dict_DB import (
    kcode_dict, STYLES_dict,
    STYLES_ZONE_URBAN_6, STYLES_ZONE_MANAGE_6, STYLES_ZONE_AGRI_6,
    STYLES_ZONE_NATURE_6,
    STYLES_DISTRICT_LANDSCAPE_6,
    STYLES_DISTRICT_ALTITUDE_6,
    STYLES_DISTRICT_FIRE_6, STYLES_DISTRICT_DISASTER_6,
    STYLES_DISTRICT_PROTECTION_6, STYLES_DISTRICT_SETTLEMENT_6,
    STYLES_DISTRICT_DEVELOPMENT_6, STYLES_DISTRICT_SPECIFIC_USE_6,
    STYLES_PLANNING_ZONE_6, STYLES_GREENBELT_6,
    STYLES_DISTRICT_UNIT_PLAN_6, STYLES_URBAN_NATURE_PARK_6,
    STYLES_DEVELOPMENT_RESTRICTION_6,
    STYLES_FACILITY_ROAD_6, STYLES_FACILITY_TRAFFIC_6, STYLES_FACILITY_SPACE_6,
    STYLES_FACILITY_SUPPLY_6, STYLES_FACILITY_CULTURE_6,
    STYLES_FACILITY_DISASTER_6, STYLES_FACILITY_HEALTH_6,
    STYLES_FACILITY_ENV_6, STYLES_FACILITY_ETC_6,
    wfs_api_dict, wfs_field_cnd, wfs_tree_structure
)
from .symbol_style_utils import build_symbol_from_style
from qgis.core import (
    QgsSymbol, QgsApplication,
    QgsCategorizedSymbolRenderer, QgsRendererCategory
)
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

_active_wfs_tasks = []


def _save_layer_as_shp(vlayer, layer_name):
    project = QgsProject.instance()
    home_path = project.homePath()
    if not home_path:
        home_path = os.path.join(os.path.expanduser("~"), "Desktop")

    shp_dir = os.path.join(home_path, "shp_api")
    os.makedirs(shp_dir, exist_ok=True)

    safe_name = re.sub(r'[\\/:*?"<>|]', "_", str(layer_name)).strip().strip(".") or "layer"
    shp_path = os.path.join(shp_dir, f"{safe_name}.shp")

    result = QgsVectorFileWriter.writeAsVectorFormat(
        vlayer, shp_path, "UTF-8", vlayer.crs(), "ESRI Shapefile"
    )
    error_code = result[0] if isinstance(result, tuple) else result

    if error_code == QgsVectorFileWriter.NoError:
        print(f"[OK] \"{layer_name}\" 레이어를 {shp_path} 에 저장했습니다.")
        return shp_path
    else:
        print(f"[ERROR] \"{layer_name}\" shp 저장 실패: {result}")
        return None


def _build_wfs_native_renderer(vlayer, target_value, category_found):
    registry = QgsApplication.symbolLayerRegistry()

    boundary_style_keys = {
        "시도경계",
        "시군구경계",
        "읍면동경계",
        "리경계",
    }
    if category_found in boundary_style_keys:
        symbol = QgsSymbol.defaultSymbol(vlayer.geometryType())
        symbol.deleteSymbolLayer(0)
        raw_style = STYLES_dict.get(
            category_found, STYLES_dict.get("기본값")
        ).copy()
        build_symbol_from_style(symbol, raw_style, registry)
        vlayer.setRenderer(QgsSingleSymbolRenderer(symbol))
        return

    if category_found == "uname_fd":
        category_code_field = "ucode"
        category_name_field = "uname"
    elif category_found == "atrb_se_fd":
        category_code_field = "atrb_se"
        category_name_field = "dgm_nm"
    else:
        category_code_field = ""
        category_name_field = ""

    styles_by_target = {
        "용도지역도_도시지역": STYLES_ZONE_URBAN_6,
        "용도지역도_관리지역": STYLES_ZONE_MANAGE_6,
        "용도지역도_농림지역": STYLES_ZONE_AGRI_6,
        "용도지역도_자연환경보전지역": STYLES_ZONE_NATURE_6,
        "용도지구도_경관지구": STYLES_DISTRICT_LANDSCAPE_6,
        "용도지구도_고도지구": STYLES_DISTRICT_ALTITUDE_6,
        "용도지구도_방화지구": STYLES_DISTRICT_FIRE_6,
        "용도지구도_방재지구": STYLES_DISTRICT_DISASTER_6,
        "용도지구도_보호지구": STYLES_DISTRICT_PROTECTION_6,
        "용도지구도_취락지구": STYLES_DISTRICT_SETTLEMENT_6,
        "용도지구도_개발진흥지구": STYLES_DISTRICT_DEVELOPMENT_6,
        "용도지구도_특정용도제한지구": STYLES_DISTRICT_SPECIFIC_USE_6,
        "용도구역도_개발제한구역": STYLES_GREENBELT_6,
        "용도구역도_국토계획구역": STYLES_PLANNING_ZONE_6,
        "용도구역도_도시자연공원구역": STYLES_URBAN_NATURE_PARK_6,
        "지구단위계획도_지구단위계획": STYLES_DISTRICT_UNIT_PLAN_6,
        "개발행위허가도_개발행위허가제한지역": STYLES_DEVELOPMENT_RESTRICTION_6,
        "도시계획시설도_도시계획(도로)": STYLES_FACILITY_ROAD_6,
        "도시계획시설도_도시계획(교통시설)": STYLES_FACILITY_TRAFFIC_6,
        "도시계획시설도_도시계획(공간시설)": STYLES_FACILITY_SPACE_6,
        "도시계획시설도_도시계획(유통공급시설)": STYLES_FACILITY_SUPPLY_6,
        "도시계획시설도_도시계획(공공문화체육시설)": STYLES_FACILITY_CULTURE_6,
        "도시계획시설도_도시계획(방재시설)": STYLES_FACILITY_DISASTER_6,
        "도시계획시설도_도시계획(보건위생시설)": STYLES_FACILITY_HEALTH_6,
        "도시계획시설도_도시계획(환경기초시설)": STYLES_FACILITY_ENV_6,
        "도시계획시설도_도시계획(기타기반시설)": STYLES_FACILITY_ETC_6,
    }
    styles_by_code = styles_by_target.get(target_value, {})

    has_category_fields = (
        category_code_field
        and vlayer.fields().indexFromName(category_code_field) >= 0
        and vlayer.fields().indexFromName(category_name_field) >= 0
    )

    if has_category_fields and not styles_by_code:
        symbol = QgsSymbol.defaultSymbol(vlayer.geometryType())
        symbol.deleteSymbolLayer(0)
        default_style = STYLES_dict.get('기본값').copy()
        build_symbol_from_style(symbol, default_style, registry)
        vlayer.setRenderer(QgsSingleSymbolRenderer(symbol))
        return

    if has_category_fields:
        categories = []
        for code6, raw_style in sorted(styles_by_code.items()):
            symbol = QgsSymbol.defaultSymbol(vlayer.geometryType())
            symbol.deleteSymbolLayer(0)
            build_symbol_from_style(symbol, raw_style.copy(), registry)

            name = kcode_dict.get(code6, "")
            label = f"{code6} {name}".strip()
            categories.append(QgsRendererCategory(code6, symbol, label))

        other_value = "__OTHER__"
        other_symbol = QgsSymbol.defaultSymbol(vlayer.geometryType())
        other_symbol.deleteSymbolLayer(0)
        unregistered_style = {
            "color": "255,255,255,0",
            "style": "no",
            "outline_color": "255,0,0,255",
            "outline_width": "0.26",
            "outline_style": "solid",
        }
        build_symbol_from_style(other_symbol, unregistered_style, registry)
        categories.append(
            QgsRendererCategory(
                other_value,
                other_symbol,
                "기타 (6자리 code 분류값 없음)"
            )
        )

        quoted_field = QgsExpression.quotedColumnRef(category_code_field)
        quoted_codes = ", ".join(
            QgsExpression.quotedValue(code6) for code6 in styles_by_code
        )
        category_expression = (
            f"CASE WHEN {quoted_field} IN ({quoted_codes}) "
            f"THEN {quoted_field} ELSE '{other_value}' END"
        )
        renderer = QgsCategorizedSymbolRenderer(
            category_expression, categories
        )
        vlayer.setRenderer(renderer)
        return

    random_color = QColor.fromHsv(
        random.randint(0, 359),
        random.randint(130, 190),
        random.randint(225, 250)
    )
    symbol = QgsSymbol.defaultSymbol(vlayer.geometryType())
    symbol.deleteSymbolLayer(0)
    from qgis.core import QgsSimpleFillSymbolLayer
    s_layer = QgsSimpleFillSymbolLayer()
    s_layer.setColor(random_color)
    symbol.appendSymbolLayer(s_layer)
    vlayer.setRenderer(QgsSingleSymbolRenderer(symbol))


def show_map_Vworld_WFS_native(
    iface, target_value, ms, add_to_API=True, save_snapshot=False
):
    vworld_key = ""
    if hasattr(ms, 'input_API') and ms.input_API:
        vworld_key = ms.input_API.text().strip()

    if not vworld_key:
        QMessageBox.warning(ms, "경고", "브이월드 API 인증키를 입력해 주세요.")
        return None
    if len(str(vworld_key)) != 36:
        QMessageBox.warning(ms, "경고", "브이월드 API 인증키 36개 글자수가 아닙니다. 인증키를 재확인해주세요.")
        return None

    target_key = wfs_api_dict.get(target_value)
    category_found = next((cat for cat, items in wfs_field_cnd.items() if target_value in items), "없음")

    supported_wfs_crs = {
        "EPSG:4326",
        "EPSG:3857",
        "EPSG:2096",
        "EPSG:2097",
        "EPSG:2098",
    }
    prj_crs = QgsProject.instance().crs()
    request_crs_authid = (
        prj_crs.authid()
        if prj_crs.authid() in supported_wfs_crs
        else "EPSG:3857"
    )

    wfs_url = (
        "maxNumFeatures='1000' "
        "pagingEnabled='true' "
        "preferCoordinatesForWfsT11='false' "
        "restrictToRequestBBOX='1' "
        f"srsname='{request_crs_authid}' "
        f"typename='{target_key}' "
        f"url='https://api.vworld.kr/req/wfs?key={vworld_key}&maxfeatures=1000' "
        "version='auto'"
    )

    try:
        vlayer = QgsVectorLayer(wfs_url, target_value, "WFS")
    except Exception as exc:
        safe_error = str(exc).replace(vworld_key, "***")
        print(
            f'[ERROR] "{target_value}" 네이티브 WFS 프로바이더 생성 중 예외: '
            f"{safe_error}"
        )
        return None

    admin_boundary_fallbacks = {
        "lt_c_adsido_info": "lt_c_adsido",
        "lt_c_adsigg_info": "lt_c_adsigg",
        "lt_c_ademd_info": "lt_c_ademd",
        "lt_c_adri_info": "lt_c_adri",
    }
    fallback_key = admin_boundary_fallbacks.get(target_key)
    if not vlayer.isValid() and fallback_key:
        fallback_url = wfs_url.replace(
            f"typename='{target_key}'", f"typename='{fallback_key}'"
        )
        fallback_layer = QgsVectorLayer(fallback_url, target_value, "WFS")
        if fallback_layer.isValid():
            print(
                f'[INFO] "{target_value}"는 V-QGIS 행정경계 우회 typename '
                f"({fallback_key})으로 불러왔습니다."
            )
            vlayer = fallback_layer
            target_key = fallback_key

    if not vlayer.isValid():
        error = vlayer.error()
        details = []
        for value in (error.summary(), error.message()):
            value = (value or "").strip()
            if value and value not in details:
                details.append(value)
        for message in error.messageList():
            text = (message.message() or "").strip()
            if text and text not in details:
                details.append(text)
        canvas_extent = iface.mapCanvas().extent()
        extent_text = ",".join(
            f"{value:.3f}" for value in (
                canvas_extent.xMinimum(), canvas_extent.yMinimum(),
                canvas_extent.xMaximum(), canvas_extent.yMaximum()
            )
        )
        error_msg = " | ".join(details).replace(vworld_key, "***")
        if not error_msg:
            error_msg = (
                "QGIS WFS 프로바이더가 오류 세부 내용을 반환하지 않았습니다. "
                "GetCapabilities/DescribeFeatureType 거부 또는 요청 범위 문제일 수 있습니다."
            )
        error_msg += (
            f" | typename={target_key} | 요청 CRS={request_crs_authid}"
            f" | 현재 화면 범위={extent_text}"
        )
        print(f"[ERROR] \"{target_value}\" 네이티브 WFS 레이어 추가 실패: {error_msg}")
        return None

    _build_wfs_native_renderer(vlayer, target_value, category_found)
    vlayer.triggerRepaint()

    if save_snapshot:
        shp_path = _save_layer_as_shp(vlayer, target_value)
        if shp_path:
            saved_layer = QgsVectorLayer(shp_path, target_value, "ogr")
            if saved_layer.isValid():
                saved_layer.setRenderer(vlayer.renderer().clone())
                QgsProject.instance().addMapLayer(saved_layer, add_to_API)
                saved_layer.triggerRepaint()
                iface.layerTreeView().refreshLayerSymbology(saved_layer.id())
                print(f"[OK] \"{target_value}\" 레이어를 shp로 저장했습니다: {shp_path}")
                return saved_layer
            else:
                print(f"[ERROR] 저장된 shp 파일을 레이어로 불러오지 못했습니다: {shp_path}")

    QgsProject.instance().addMapLayer(vlayer, add_to_API)
    print(f"[OK] \"{target_value}\" 레이어(읽기전용)가 지도에 추가되었습니다.")
    return vlayer


def show_map_Vworld_WFS(iface, target_value, ms, show_warning=True, add_to_API=True, on_done=None):
    def finish(layer=None):
        if on_done:
            on_done(layer)

    vworld_key = ms.input_API.text().strip() if hasattr(ms, "input_API") else ""
    if not vworld_key or len(vworld_key) != 36:
        QMessageBox.warning(ms, "경고", "36자리 브이월드 API 인증키를 입력해 주세요.")
        finish()
        return None

    target_key = wfs_api_dict.get(target_value)
    if not target_key:
        print(f'[ERROR] "{target_value}"에 해당하는 WFS typename이 없습니다.')
        finish()
        return None

    project = QgsProject.instance()
    project_crs = project.crs()
    request_crs = QgsCoordinateReferenceSystem("EPSG:3857")
    extent = iface.mapCanvas().extent()
    if project_crs != request_crs:
        transform = QgsCoordinateTransform(project_crs, request_crs, project)
        extent = transform.transformBoundingBox(extent)

    params = {
        "service": "WFS", "version": "1.1.0", "request": "GetFeature",
        "key": vworld_key, "typename": target_key,
        "bbox": ",".join(map(str, (extent.xMinimum(), extent.yMinimum(),
                                    extent.xMaximum(), extent.yMaximum()))),
        "srsname": "EPSG:3857", "output": "application/json",
    }
    url = "https://api.vworld.kr/req/wfs?" + urllib.parse.urlencode(params)

    def fetch(task):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {
                "_client_error": (
                    f"HTTP {exc.code} {exc.reason}; 응답={body[:500]}"
                )
            }
        except Exception as exc:
            print(f"[ERROR] WFS 네트워크 요청 실패: {exc}")
            return None

    def fetched(exception, payload):
        if task in _active_wfs_tasks:
            _active_wfs_tasks.remove(task)
        if payload and payload.get("_client_error"):
            print(
                f'[ERROR] "{target_value}" 현재 화면 WFS 요청 실패: '
                f'{payload["_client_error"]}'
            )
            finish()
            return
        if exception is not None or not payload or not payload.get("features"):
            print(f'[ERROR] "{target_value}" WFS 임시데이터를 불러오지 못했습니다.')
            if show_warning:
                QMessageBox.warning(ms, "알림", f'현재 화면에 "{target_value}" 데이터가 없습니다.')
            finish()
            return

        source = QgsVectorLayer(json.dumps(payload, ensure_ascii=False), target_value, "ogr")
        if not source.isValid():
            finish()
            return

        geometry_type = QgsWkbTypes.displayString(source.wkbType())
        layer = QgsVectorLayer(
            f"{geometry_type}?crs={project_crs.authid()}", target_value, "memory"
        )
        provider = layer.dataProvider()
        provider.addAttributes(source.fields())
        layer.updateFields()
        features = list(source.getFeatures())
        if project_crs != request_crs:
            back_transform = QgsCoordinateTransform(request_crs, project_crs, project)
            for feature in features:
                geometry = feature.geometry()
                geometry.transform(back_transform)
                feature.setGeometry(geometry)
        provider.addFeatures(features)

        category = next(
            (name for name, items in wfs_field_cnd.items() if target_value in items),
            "없음"
        )
        _build_wfs_native_renderer(layer, target_value, category)
        layer.setCustomProperty("wfs_target", target_value)

        if hasattr(ms, "cb_Temporary_api") and ms.cb_Temporary_api.isChecked():
            shp_path = _save_layer_as_shp(layer, target_value)
            saved = QgsVectorLayer(shp_path, target_value, "ogr") if shp_path else None
            if saved and saved.isValid():
                saved.setRenderer(layer.renderer().clone())
                layer = saved

        project.addMapLayer(layer, add_to_API)
        layer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(layer.id())
        print(f'[OK] "{target_value}" WFS 임시데이터를 지도에 추가했습니다.')
        finish(layer)

    task = QgsTask.fromFunction(
        f"WFS 임시데이터 불러오기: {target_value}", fetch, on_finished=fetched
    )
    _active_wfs_tasks.append(task)
    QgsApplication.taskManager().addTask(task)
    return None


def refresh_all_wfs_layers(iface, ms):
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    for old_layer in list(project.mapLayers().values()):
        target_value = old_layer.customProperty("wfs_target")
        if not target_value:
            continue
        old_id = old_layer.id()
        old_node = root.findLayer(old_id)
        parent = old_node.parent() if old_node else None
        visible = old_node.isVisible() if old_node else True

        def replace(new_layer, old_id=old_id, parent=parent, visible=visible):
            if new_layer is None:
                return
            if project.mapLayer(old_id) is None:
                project.removeMapLayer(new_layer.id())
                return
            project.removeMapLayer(old_id)
            if parent is not None:
                parent.addLayer(new_layer)
            else:
                project.addMapLayer(new_layer, True)
            node = root.findLayer(new_layer.id())
            if node is not None:
                node.setItemVisibilityChecked(visible)

        show_map_Vworld_WFS(
            iface, target_value, ms, show_warning=False, add_to_API=False, on_done=replace
        )


def show_all_Vworld_WFS_native(iface, ms):
    root = QgsProject.instance().layerTreeRoot()

    def get_or_create_group(parent, name):
        group = parent.findGroup(name)
        if not group:
            group = parent.insertGroup(0, name)
        return group

    group_top = get_or_create_group(root, "도시관리계획도(WFS)")
    category_names = (
        "용도지역(WFS)",
        "용도지구(WFS)",
        "국토계획구역(WFS)",
        "도시계획시설(WFS)",
    )

    loaded_layers = []
    for category_name in category_names:
        category_group = get_or_create_group(group_top, category_name)
        for layer_name in wfs_tree_structure.get(category_name, []):
            layer = show_map_Vworld_WFS_native(iface, layer_name, ms, add_to_API=False)
            if layer:
                category_group.addLayer(layer)
                loaded_layers.append(layer)
            QApplication.processEvents()

    return loaded_layers
