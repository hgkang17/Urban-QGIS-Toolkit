import os
import re
import urllib.request
import urllib.parse
import json
import random
from qgis.core import *
from qgis.gui import QgsRubberBand
from PyQt5.QtGui import QColor
from PyQt5 import QtGui
from PyQt5.QtCore import QVariant
from .dict_DB import kcode_dict, STYLES_dict, STYLES_RANDOM, STYLES_codeX_dict, api_dict, tree_structure, kcode_dict_Reverse, api_field_cnd
from .symbol_style_utils import build_symbol_from_style
from qgis.core import (
    QgsField, QgsSymbol, QgsApplication,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSettings
)
from qgis.PyQt.QtWidgets import QMessageBox
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt, QSizeF
from qgis.core import (
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsTextBackgroundSettings, QgsVectorLayerSimpleLabeling, QgsPalLayerSettings, QgsUnitTypes
)

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


def show_map_Vworld_2Dapi(iface, target_value, ms,show_warning=True, add_to_API=True):
    vworld_key = ""
    if hasattr(ms, 'input_API') and ms.input_API:
        vworld_key = ms.input_API.text().strip()

    if not vworld_key :
        QMessageBox.warning(ms, "경고", "브이월드 API 인증키를 입력해 주세요.")
        return
    if len(str(vworld_key)) != 36:
        QMessageBox.warning(ms, "경고", "브이월드 API 인증키 36개 글자수가 아닙니다. 인증키를 재확인해주세요.")
        return

    target_key = api_dict.get(target_value)


    category_found = next((cat for cat, items in api_field_cnd.items() if target_value in items), "없음")


    project = QgsProject.instance()
    prj_crs = project.crs()

    crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
    transform_setting = QgsCoordinateTransform(prj_crs, crs_4326, QgsProject.instance())
    transform_prj_crs = QgsCoordinateTransform(crs_4326, prj_crs, QgsProject.instance())

    canvas = iface.mapCanvas()
    extent = canvas.extent()

    if prj_crs.authid() == crs_4326.authid():
        minx, miny = extent.xMinimum(), extent.yMinimum()
        maxx, maxy = extent.xMaximum(), extent.yMaximum()
    else:
        trans_min = transform_setting.transform(extent.xMinimum(), extent.yMinimum())
        trans_max = transform_setting.transform(extent.xMaximum(), extent.yMaximum())

        minx, miny = trans_min.x(), trans_min.y()
        maxx, maxy = trans_max.x(), trans_max.y()

    BOX = f"BOX({minx},{miny},{maxx},{maxy})"


    def Vworld_2Dapi():
        base_url = "https://api.vworld.kr/req/data?"

        params = {
                "service": "data",
                "request": "GetFeature",
                "format": "json",
                "size": "1000",
                "data": target_key,
                "geomFilter" : BOX,
                "crs": "epsg:4326",
                "key": vworld_key
            }

        base_params = urllib.parse.urlencode(params)
        url = base_url + base_params

        try:
            with urllib.request.urlopen(url) as response:
                result_bytes = response.read()
                result_str = result_bytes.decode('utf-8')
                data_dict = json.loads(result_str)
                return data_dict
        except Exception as e:
                print(f"[ERROR] 네트워크 요청 실패: {e}")
                return None

    features = Vworld_2Dapi()

    if features is None:
        print("[ERROR] API 서버로부터 응답을 받을 수 없습니다.")
        return
    if "response" not in features:
        print("[ERROR] API 응답 구조에 'response'가 없습니다. 요청 파라메타를 확인하세요")
        return

    res = features["response"]

    if res.get("status") == "NOT_FOUND":
        print(f"해당 화면에 \"{target_value}\"이 없습니다. {res.get('status')}")
        if show_warning:
            QMessageBox.warning(
                ms,
                "알림",
                f"해당 화면에 \"{target_value}\"이 없습니다."
            )
        return

    if res.get("status") == "ERROR":
        print(f"[ERROR] 에러 메시지: {res.get('error', {}).get('text', '알 수 없는 에러, 요청 data명을 확인하세요')}")
        if res.get("error"):
            QMessageBox.warning(ms, "경고", res.get("error", {}).get("text"))
        return
    if not res["result"]["featureCollection"]["features"]:
        print("조회 결과가 없습니다.")
        return


    geojson_data = json.dumps(features["response"]["result"]["featureCollection"],ensure_ascii=False)
    geo_Source = QgsVectorLayer(geojson_data, "target_value", "ogr")

    geometry = QgsWkbTypes.displayString(geo_Source.wkbType())

    vlayer = QgsVectorLayer(
        f"{geometry}?crs={prj_crs.authid()}",
        f"{target_value}",
        "memory"
    )

    dp = vlayer.dataProvider()

    dp.addAttributes(geo_Source.fields())
    vlayer.updateFields()

    if prj_crs.authid() == crs_4326.authid():
        dp.addFeatures(geo_Source.getFeatures())
    else:
        features_to_add = []
        for feat in geo_Source.getFeatures():
            geom = feat.geometry()
            geom.transform(transform_prj_crs)
            feat.setGeometry(geom)
            features_to_add.append(feat)
        dp.addFeatures(features_to_add)


    if vlayer.isValid():
                QgsProject.instance().addMapLayer(vlayer, add_to_API)
                print(f"[OK] \"{target_value}\" 레이어가 지도에 추가되었습니다.")
    else:
                print("[ERROR] 레이어를 생성할 수 없습니다.")


    dosi_field = "uname"
    code_field = "atrb_se"
    name_field = "codename"
    plus = "codeplus"

    updates = {}
    unique_values = set()

    if category_found == "uname_fd":

        vlayer.dataProvider().addAttributes([QgsField("atrb_se", QVariant.String), QgsField("codename", QVariant.String),QgsField("codeplus", QVariant.String)])
        vlayer.updateFields()
        code_idx = vlayer.fields().indexFromName(code_field)
        name_idx = vlayer.fields().indexFromName(name_field)
        plus_idx = vlayer.fields().indexFromName(plus)
        dosi_idx = vlayer.fields().indexFromName(dosi_field)


        for feature in vlayer.getFeatures():
            code_name = feature[dosi_idx]
            if code_name :
                code_name_Vlookup_code = kcode_dict_Reverse.get(code_name, "")
            else:
                code_name = ""
                code_name_Vlookup_code = ""

            code6_plus_value = (code_name_Vlookup_code + " " + code_name).strip()

            updates[feature.id()] = {
                code_idx: code_name_Vlookup_code,
                name_idx: code_name,
                plus_idx: code6_plus_value
            }

            if code6_plus_value:
                unique_values.add(code6_plus_value)

    elif category_found == "atrb_se_fd":

        vlayer.dataProvider().addAttributes([QgsField("codename", QVariant.String),QgsField("codeplus", QVariant.String)])

        vlayer.updateFields()

        code_idx = vlayer.fields().indexFromName(code_field)
        name_idx = vlayer.fields().indexFromName(name_field)
        plus_idx = vlayer.fields().indexFromName(plus)


        for feature in vlayer.getFeatures():
            code6 = feature[code_idx]

            if code6 and len(str(code6)) >= 6:
                code6_Vlookup_name = kcode_dict.get(code6, "")
            else:
                code6 = ""
                code6_Vlookup_name = ""

            code6_plus_value = (code6 + " " + code6_Vlookup_name).strip()

            updates[feature.id()] = {
                code_idx: code6,
                name_idx: code6_Vlookup_name,
                plus_idx: code6_plus_value
            }


            unique_values.add(code6_plus_value)

    else:
        unique_values.add("")
    vlayer.startEditing()
    vlayer.dataProvider().changeAttributeValues(updates)
    vlayer.commitChanges()


    boundary_style_keys = {
        "시도경계",
        "시군구경계",
        "읍면동경계",
        "리경계",
    }
    if category_found in boundary_style_keys:
        registry = QgsApplication.symbolLayerRegistry()
        symbol = QgsSymbol.defaultSymbol(vlayer.geometryType())
        symbol.deleteSymbolLayer(0)
        raw_style = STYLES_dict.get(
            category_found, STYLES_dict.get("기본값")
        ).copy()
        build_symbol_from_style(symbol, raw_style, registry)

        renderer = QgsSingleSymbolRenderer(symbol)
        vlayer.setRenderer(renderer)
        vlayer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(vlayer.id())
    elif category_found not in ("uname_fd", "atrb_se_fd"):
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

        renderer = QgsSingleSymbolRenderer(symbol)
        vlayer.setRenderer(renderer)
        vlayer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(vlayer.id())
    else:
        registry = QgsApplication.symbolLayerRegistry()
        categories = []
        all_categories = sorted(list(unique_values), key=lambda x: (x == "", x))

        for val in all_categories:
            symbol = QgsSymbol.defaultSymbol(vlayer.geometryType())
            symbol.deleteSymbolLayer(0)


            code_prefix = str(val).strip()[:3] if val else ""

            if val == "" or code_prefix in STYLES_RANDOM:
                random_color = QColor.fromHsv(
                    random.randint(0, 359),
                    random.randint(130, 190),
                    random.randint(225, 250)
                )

                from qgis.core import QgsSimpleFillSymbolLayer
                s_layer = QgsSimpleFillSymbolLayer()
                s_layer.setColor(random_color)
                symbol.appendSymbolLayer(s_layer)

            else:
                raw_style = STYLES_dict.get(val, STYLES_dict.get('기본값')).copy()
                build_symbol_from_style(symbol, raw_style, registry)

            label = str(val) if val else "빈칸(분류값 없음)"
            category = QgsRendererCategory(val, symbol, label)
            categories.append(category)

        renderer = QgsCategorizedSymbolRenderer(plus, categories)
        vlayer.setRenderer(renderer)
        vlayer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(vlayer.id())


    def apply_full_labeling():
        if target_value == "도시계획시설_도로(광로~소로 등)" :
            if vlayer:
                labeling = vlayer.labeling()
                if labeling:
                    label_settings = labeling.settings()
                    text_format = label_settings.format()
                else:
                    label_settings = QgsPalLayerSettings()
                    label_settings.fieldName = '"grad_se" + \'(\' + left("pmi_nam", 1) + \')\' + \'\n\' + "road_ty" + \'-\' + "road_no"'
                    label_settings.isExpression = True

                    text_format = QgsTextFormat()

                    text_format.setFont(QFont("맑은 고딕", 10))
                    text_format.setColor(QColor(0, 0, 255))


                label_settings.multilineAlign = QgsPalLayerSettings.MultiCenter
                label_settings.placement = QgsPalLayerSettings.Horizontal


                bg_settings = QgsTextBackgroundSettings()
                bg_settings.setEnabled(True)
                bg_settings.setType(QgsTextBackgroundSettings.ShapeMarkerSymbol)

                bg_settings.setSizeType(QgsTextBackgroundSettings.SizeBuffer)
                bg_settings.setSize(QSizeF(1.5, 1.5))
                bg_settings.setSizeUnit(QgsUnitTypes.RenderMillimeters)

                marker_symbol = QgsMarkerSymbol()
                marker_symbol.deleteSymbolLayer(0)

                circle_layer = QgsSimpleMarkerSymbolLayer()
                circle_layer.setColor(QColor(255,255,255,0))
                circle_layer.setStrokeColor(QColor("blue"))
                marker_symbol.appendSymbolLayer(circle_layer)

                bar_layer = QgsSimpleMarkerSymbolLayer()
                bar_layer.setShape(QgsSimpleMarkerSymbolLayerBase.Line)
                bar_layer.setAngle(90)
                bar_layer.setColor(QColor("blue"))
                marker_symbol.appendSymbolLayer(bar_layer)

                bg_settings.setMarkerSymbol(marker_symbol)

                text_format.setBackground(bg_settings)
                label_settings.setFormat(text_format)

                vlayer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
                vlayer.setLabelsEnabled(True)

                vlayer.triggerRepaint()
                iface.mapCanvas().refresh()
    apply_full_labeling()

    if hasattr(ms, 'cb_Temporary_api') and ms.cb_Temporary_api.isChecked():
        shp_path = _save_layer_as_shp(vlayer, target_value)
        if shp_path:
            saved_layer = QgsVectorLayer(shp_path, target_value, "ogr")
            if saved_layer.isValid():
                saved_layer.setRenderer(vlayer.renderer().clone())
                if vlayer.labeling():
                    saved_layer.setLabeling(vlayer.labeling().clone())
                    saved_layer.setLabelsEnabled(vlayer.labelsEnabled())

                QgsProject.instance().removeMapLayer(vlayer.id())
                QgsProject.instance().addMapLayer(saved_layer, add_to_API)
                saved_layer.triggerRepaint()
                iface.layerTreeView().refreshLayerSymbology(saved_layer.id())
                vlayer = saved_layer
            else:
                print(f"[ERROR] 저장된 shp 파일을 레이어로 불러오지 못했습니다: {shp_path}")

    return vlayer


