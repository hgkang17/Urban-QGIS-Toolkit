import os
import inspect
import re
import random


from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtGui import QColor

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsField, QgsSymbol, QgsApplication,
    QgsCategorizedSymbolRenderer, QgsRendererCategory
)
from .dict_DB import kcode_dict, STYLES_dict, STYLES_RANDOM
from .symbol_style_utils import build_symbol_from_style

SOURCE_ENCODING = "EUC-KR"


def _apply_source_encoding(layer):
    provider = layer.dataProvider()
    if provider is None or not hasattr(provider, "setEncoding"):
        return False

    provider.setEncoding(SOURCE_ENCODING)
    if hasattr(provider, "reloadData"):
        provider.reloadData()
    layer.updateFields()
    return True


def _find_field_index_case_insensitive(layer, field_name):
    target_name = field_name.casefold()
    for index, field in enumerate(layer.fields()):
        if field.name().casefold() == target_name:
            return index
    return -1


def mnum_symbol(iface, dock_widget):

        iface.messageBar().pushMessage('분류 및 심볼을 실행하였습니다')


        CODE_MAP = {
            'UQ111': '도시지역',
            'UQ112': '관리지역',
            'UQ113': '농림지역',
            'UQ121': '경관지구',
            'UQ123': '고도지구',
            'UQ124': '방화지구',
            'UQ125': '방재지구',
            'UQ126': '보호지구',
            'UQ128': '취락지구',
            'UQ129': '개발진흥지구',
            'UQ130': '특정용도제한지구',
            'UQ131': '복합용도지구',
            'UQ141': '구역',
            'UQ161': '교통시설',
            'UQ162': '공간시설',
            'UQ163': '유통공급시설',
            'UQ164': '공공문화체육시설',
            'UQ165': '방재시설',
            'UQ166': '보건위생시설',
            'UQ167': '환경기초시설',
            'UF801': '보전산지',
            'UE101': '농업진흥지역',
            'UI101': '도로용도구역'
        }

        selected_layers = iface.layerTreeView().selectedLayers()

        if not selected_layers:
            QMessageBox.warning(
                dock_widget,
                "레이어 선택 필요",
                "선택된 레이어가 없습니다. 레이어 창에서 대상을 선택해 주세요."
            )
            return
        else:
            code_field = "code"
            name_field = "codename"
            MNUM_field = "MNUM"
            plus = "codeplus"
            registry = QgsApplication.symbolLayerRegistry()


            cntTotal = 0
            for layer in selected_layers:
                if layer.type() == layer.VectorLayer:
                    if _find_field_index_case_insensitive(layer, MNUM_field) != -1:
                        cntTotal += layer.featureCount()

            if cntTotal == 0:
                QMessageBox.warning(
                    dock_widget,
                    "MNUM 필드 없음",
                    "선택한 레이어 중 'MNUM' 필드를 가진 레이어가 없습니다."
                )
                return

            dock_widget.progressBar.setMaximum(cntTotal)
            dock_widget.progressBar.setValue(0)

            current_progress = 0

            for layer in selected_layers:
                if layer.type() == layer.VectorLayer:
                    try:
                        if _apply_source_encoding(layer):
                            iface.messageBar().pushMessage(
                                f"[{layer.name()}] 원본 인코딩: {SOURCE_ENCODING}"
                            )
                        else:
                            iface.messageBar().pushMessage(
                                f"[{layer.name()}] 데이터 공급자가 인코딩 변경을 지원하지 않습니다."
                            )
                    except Exception as encoding_error:
                        QMessageBox.warning(
                            dock_widget,
                            "레이어 인코딩 오류",
                            f"'{layer.name()}' 레이어를 {SOURCE_ENCODING}로 다시 읽지 못했습니다.\n\n"
                            f"{encoding_error}"
                        )
                        continue

                if layer.type() != layer.VectorLayer:
                    iface.messageBar().pushMessage(f"⚠️ {layer.name()} 은(는) 벡터 레이어가 아니라서 제외합니다.")
                    continue

                MNUM_idx = _find_field_index_case_insensitive(layer, MNUM_field)
                if MNUM_idx == -1:
                    iface.messageBar().pushMessage(
                        f"  ❌ '{MNUM_field}' 필드가 존재하지 않아 적용을 건너뜁니다."
                    )
                    continue

                old_layer_name = layer.name()
                iface.messageBar().pushMessage(f"\n⚙️ [{old_layer_name}] 레이어 자동화 작업 시작...")

                base_layer_name = old_layer_name.split('(')[0].strip()
                name_match = re.search(r'LSMD_CONT_([A-Z0-9]+)', base_layer_name)

                if name_match:
                    extracted_layer_code = name_match.group(1)
                    korean_layer_name = CODE_MAP.get(extracted_layer_code, "")

                    if korean_layer_name:
                        new_layer_name = f"{base_layer_name}({korean_layer_name})"
                        if old_layer_name != new_layer_name:
                            layer.setName(new_layer_name)
                    else:
                        iface.messageBar().pushMessage(f"  ⚠️ 용도지역지구 코드 '{extracted_layer_code}'가 CODE_MAP에 없습니다. 데이터를 추가해주세요(개발자용).")
                else:
                    iface.messageBar().pushMessage("  ℹ️ 레이어 이름이 'LSMD_CONT_' 형식이 아니어서 이름 변경을 스킵합니다.")

                layer.startEditing()
                current_fields = {f.name(): f for f in layer.fields()}

                for fname in [code_field, name_field, plus]:
                    if fname in current_fields:
                        f_type = current_fields[fname].type()
                        f_type_name = current_fields[fname].typeName()

                        if f_type != QVariant.String and "String" not in f_type_name and "Text" not in f_type_name:
                            iface.messageBar().pushMessage(f"⚠️ '{fname}' 필드 타입이 문자열이 아니므로 삭제 후 재구축합니다.")
                            idx_to_del = layer.fields().indexFromName(fname)
                            layer.deleteAttribute(idx_to_del)
                            layer.addAttribute(QgsField(fname, QVariant.String))
                    else:
                        layer.addAttribute(QgsField(fname, QVariant.String))
                layer.updateFields()
                layer.commitChanges()

                code_idx = layer.fields().indexFromName(code_field)
                name_idx = layer.fields().indexFromName(name_field)
                plus_idx = layer.fields().indexFromName(plus)

                updates = {}
                unique_values = set()

                for feature in layer.getFeatures():
                    mnum = feature[MNUM_idx]

                    if mnum and len(str(mnum)) >= 26:
                        code6 = str(mnum)[20:26]
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

                    current_progress += 1
                    dock_widget.progressBar.setValue(current_progress)
                    QCoreApplication.processEvents()

                layer.startEditing()
                layer.dataProvider().changeAttributeValues(updates)
                layer.commitChanges()

                categories = []
                all_categories = sorted(list(unique_values), key=lambda x: (x == "", x))

                for val in all_categories:
                    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
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
                layer.setRenderer(renderer)
                layer.triggerRepaint()
                iface.layerTreeView().refreshLayerSymbology(layer.id())


            QMessageBox.warning(
                dock_widget,
                "MNUM 추출 및 심볼 완료",
                "작업이 완료되었습니다."
            )
            dock_widget.progressBar.setValue(0)
