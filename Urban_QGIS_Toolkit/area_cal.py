from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsField, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
from qgis.PyQt.QtCore import QVariant, QCoreApplication


def area_cal(iface, dock_widget):
    iface.messageBar().pushMessage("면적계산을 실행하였습니다")

    selected_layers_list = iface.layerTreeView().selectedLayers()
    if not selected_layers_list:
        QMessageBox.warning(
            dock_widget,
            "레이어 선택 필요",
            "선택된 레이어가 없습니다. 레이어 패널에서 레이어를 클릭해주세요.",
        )
        return

    cnt_total = sum(
        layer.featureCount()
        for layer in selected_layers_list
        if layer.type() == layer.VectorLayer
    )
    dock_widget.progressBar.setMaximum(cnt_total)
    dock_widget.progressBar.setValue(0)

    current_progress = 0
    updated_field_names = set()
    successful_layers = []
    failed_layers = []

    for layer in selected_layers_list:
        if layer.type() != layer.VectorLayer:
            iface.messageBar().pushMessage(
                f"⚠️ {layer.name()} 은(는) 벡터 레이어가 아니라서 제외합니다."
            )
            continue

        iface.messageBar().pushMessage(f"⚙️ [{layer.name()}] 면적 계산 작업 중...")

        is_geographic = layer.crs().isGeographic()
        is_shapefile = layer.source().split("|", 1)[0].lower().endswith(".shp")

        if is_geographic:
            decimal_name = "area_GCS"
            integer_name = "area_Gint"
            expression = QgsExpression("$area")
        else:
            decimal_name = "area_CAD"
            integer_name = "area_int"
            expression = QgsExpression("area($geometry)")

        integer_field_type = QVariant.Double if is_shapefile else QVariant.LongLong
        field_specs = (
            (decimal_name, QVariant.Double, 20, 3),
            (integer_name, integer_field_type, 20, 0),
        )

        delete_indexes = []
        for field_name, *_ in field_specs:
            field_index = layer.fields().indexFromName(field_name)
            if field_index != -1:
                delete_indexes.append(field_index)

        if delete_indexes:
            if not layer.dataProvider().deleteAttributes(delete_indexes):
                failed_layers.append(layer.name())
                QMessageBox.warning(
                    dock_widget,
                    "기존 필드 삭제 실패",
                    f"'{layer.name()}' 레이어의 기존 면적 필드를 삭제하지 못했습니다.",
                )
                continue
            layer.updateFields()

        for field_name, field_type, length, precision in field_specs:
            new_field = QgsField(field_name, field_type, "", length, precision)
            layer.dataProvider().addAttributes([new_field])
        layer.updateFields()

        decimal_index = layer.fields().indexFromName(decimal_name)
        integer_index = layer.fields().indexFromName(integer_name)

        if decimal_index == -1 or integer_index == -1:
            failed_layers.append(layer.name())
            QMessageBox.warning(
                dock_widget,
                "필드 생성 실패",
                f"'{layer.name()}' 레이어에 면적 필드를 생성하지 못했습니다.\n"
                "레이어가 읽기 전용인지 또는 DBF 필드 제한을 확인해주세요.",
            )
            continue

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))

        ui_update_interval = max(cnt_total // 200, 500)

        updates = {}
        update_failed = False
        for feature in layer.getFeatures():
            context.setFeature(feature)
            decimal_value = expression.evaluate(context)
            try:
                integer_value = int(round(float(decimal_value)))
            except (TypeError, ValueError):
                integer_value = None
            updates[feature.id()] = {
                decimal_index: decimal_value,
                integer_index: integer_value,
            }

            if len(updates) >= 10000:
                if not layer.dataProvider().changeAttributeValues(updates):
                    update_failed = True
                    break
                updates.clear()

            current_progress += 1
            if current_progress % ui_update_interval == 0:
                dock_widget.progressBar.setValue(current_progress)
                QCoreApplication.processEvents()

        dock_widget.progressBar.setValue(current_progress)
        QCoreApplication.processEvents()

        if not update_failed and updates:
            update_failed = not layer.dataProvider().changeAttributeValues(updates)

        if update_failed:
            failed_layers.append(layer.name())
            QMessageBox.warning(
                dock_widget,
                "면적 저장 실패",
                f"'{layer.name()}' 레이어의 면적 값을 저장하지 못했습니다.",
            )
            continue

        successful_layers.append(layer.name())
        updated_field_names.update((decimal_name, integer_name))
        layer.triggerRepaint()

    if successful_layers:
        QMessageBox.information(
            dock_widget,
            "면적계산 완료",
            f"완료 레이어: {len(successful_layers)}개\n"
            f"업데이트 필드: {', '.join(sorted(updated_field_names))}",
        )
    else:
        QMessageBox.warning(
            dock_widget,
            "면적계산 실패",
            "면적 계산이 완료된 레이어가 없습니다.",
        )
    dock_widget.progressBar.setValue(0)
