from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsMapLayer, QgsRenderContext, QgsLayerTreeGroup, QgsLayerTreeLayer
from PyQt5.QtCore import QCoreApplication

def change_line_width(iface, plugin_ui):
    try:
        width_text = plugin_ui.input_line_width.text().strip()
        if not width_text:
            QMessageBox.warning(plugin_ui, "입력 오류", "두께 값을 입력해주세요.")
            return
        target_width = float(width_text)
    except ValueError:
        QMessageBox.warning(plugin_ui, "입력 오류", "두께는 숫자(정수 또는 실수)로 입력해야 합니다. (예: 0.3)")
        return

    iface.messageBar().pushMessage(f'선 두께 {target_width} 변경 작업을 실행합니다.')

    selected_nodes = iface.layerTreeView().selectedNodes()

    if not selected_nodes:
        QMessageBox.warning(
            plugin_ui,
            "레이어 선택 필요",
            "선택된 레이어나 그룹이 없습니다. 레이어 패널에서 대상을 클릭해주세요."
        )
        return

    def update_symbol_recursive(symbol):
        if not symbol:
            return

        if hasattr(symbol, 'setWidth'):
            symbol.setWidth(target_width)

        for i in range(symbol.symbolLayerCount()):
            lyr = symbol.symbolLayer(i)

            if hasattr(lyr, 'setStrokeWidth'):
                lyr.setStrokeWidth(target_width)
            elif hasattr(lyr, 'setWidth'):
                lyr.setWidth(target_width)

            if hasattr(lyr, 'subSymbol'):
                update_symbol_recursive(lyr.subSymbol())

    def apply_width_to_layer(layer):
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return False

        renderer = layer.renderer()
        if not renderer:
            return False

        if hasattr(renderer, 'symbols'):
            symbols = renderer.symbols(QgsRenderContext())
        elif hasattr(renderer, 'symbol'):
            symbols = [renderer.symbol()]
        else:
            symbols = []

        for symbol in symbols:
            update_symbol_recursive(symbol)

        layer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(layer.id())
        return True

    layers_to_process = []
    for node in selected_nodes:
        if isinstance(node, QgsLayerTreeGroup):
            for child in node.findLayers():
                if child.layer() and child.layer().type() == QgsMapLayer.VectorLayer:
                    layers_to_process.append(child.layer())
        elif isinstance(node, QgsLayerTreeLayer):
            if node.layer() and node.layer().type() == QgsMapLayer.VectorLayer:
                layers_to_process.append(node.layer())

    if not layers_to_process:
        QMessageBox.warning(plugin_ui, "적용 대상 없음", "선택된 항목 중 두께를 변경할 수 있는 벡터 레이어가 없습니다.")
        return

    plugin_ui.progressBar.setMaximum(len(layers_to_process))
    plugin_ui.progressBar.setValue(0)

    for idx, layer in enumerate(layers_to_process):
        iface.messageBar().pushMessage(f"⚙️ [{layer.name()}] 선 두께 변경 중...")

        apply_width_to_layer(layer)

        plugin_ui.progressBar.setValue(idx + 1)
        QCoreApplication.processEvents()

    QMessageBox.information(
        plugin_ui,
        "변경 완료",
        f"선택한 레이어의 선 두께를 {target_width}(으)로 성공적으로 변경했습니다"
    )
    plugin_ui.progressBar.setValue(0)
