from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsField, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
from qgis.PyQt.QtCore import QVariant, QCoreApplication
import sys
from qgis.core import QgsMapLayer


def _find_pnu_field_index(layer):
    for index, field in enumerate(layer.fields()):
        if field.name().casefold() == "pnu":
            return index
    return -1


def PNU_cal(iface, dock_widget):
    plugin_path = r'C:\Users\User\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\khg_main'
    if plugin_path not in sys.path:
        sys.path.append(plugin_path)

    try:
        from .dict_DB import UMD_dict
    except ImportError:
        QMessageBox.critical(dock_widget, "오류", f"'{plugin_path}' 경로에서 dict_DB.py를 찾을 수 없습니다.")
        return

    selected_layers = iface.layerTreeView().selectedLayers()
    if not selected_layers:
        QMessageBox.warning(dock_widget, "레이어 선택 필요", "레이어 패널에서 레이어를 선택해주세요.")
        return

    target_fields = [("주소full", QVariant.String), ("주소short", QVariant.String)]

    eligible_layers = [
        layer
        for layer in selected_layers
        if (
            layer.type() == QgsMapLayer.VectorLayer
            and _find_pnu_field_index(layer) != -1
        )
    ]

    if not eligible_layers:
        dock_widget.progressBar.setRange(0, 100)
        dock_widget.progressBar.setValue(0)
        QMessageBox.warning(
            dock_widget,
            "PNU 필드 없음",
            "선택한 레이어에 'PNU' 필드가 없어 주소 변환을 실행하지 않았습니다.",
        )
        return

    total_features = sum(layer.featureCount() for layer in eligible_layers)
    dock_widget.progressBar.setRange(0, max(1, total_features))
    dock_widget.progressBar.setValue(0)
    current_progress = 0

    for layer in eligible_layers:

        iface.messageBar().pushMessage(f"⚙️ [{layer.name()}] 주소 변환 작업 중...")

        fields = layer.fields()

        idx_pnu = _find_pnu_field_index(layer)
        if idx_pnu == -1:
            iface.messageBar().pushMessage(
                f"⚠️ {layer.name()} 에 'PNU' 필드가 없어 건너뜁니다.",
                level=1,
            )
            continue

        for f_name, f_type in target_fields:
            idx = fields.lookupField(f_name)

            if idx != -1 and fields.at(idx).type() != f_type:
                layer.startEditing()
                layer.dataProvider().deleteAttributes([idx])
                layer.updateFields()
                layer.commitChanges()
                idx = -1

            if idx == -1:
                layer.startEditing()
                layer.dataProvider().addAttributes([QgsField(f_name, f_type, 'string')])
                layer.updateFields()
                layer.commitChanges()

        idx_full = layer.fields().lookupField("주소full")
        idx_short = layer.fields().lookupField("주소short")

        updates = {}
        for feat in layer.getFeatures():
            pnu = str(feat[idx_pnu])
            if len(pnu) < 19:
                current_progress += 1
                continue

            umd_code = pnu[:10]
            san_type = pnu[10]
            bonbun = str(int(pnu[11:15]))
            bubun = str(int(pnu[15:19]))
            dong_name = UMD_dict.get(umd_code, "알수없음")

            san_str = "산" if san_type == "2" else ""
            ji_bun = f"{bonbun}"
            if bubun != "0": ji_bun += f"-{bubun}"

            full_address = f"{dong_name} {san_str}{ji_bun}"
            parts = dong_name.split()
            base_name = parts[-1] if not parts else (f"{parts[-2]} {parts[-1]}" if parts[-1].endswith("리") and len(parts) >= 2 else parts[-1])
            short_address = f"{base_name} {san_str}{ji_bun}"

            updates[feat.id()] = {idx_full: full_address, idx_short: short_address}

            current_progress += 1
            dock_widget.progressBar.setValue(current_progress)
            QCoreApplication.processEvents()

        layer.startEditing()
        layer.dataProvider().changeAttributeValues(updates)
        layer.commitChanges()
        layer.triggerRepaint()

    dock_widget.progressBar.setRange(0, 100)
    dock_widget.progressBar.setValue(0)
    iface.messageBar().pushMessage("✅ 주소 변환이 완료되었습니다.")
    QMessageBox.information(dock_widget, "완료", "주소 변환이 완료되었습니다.")
