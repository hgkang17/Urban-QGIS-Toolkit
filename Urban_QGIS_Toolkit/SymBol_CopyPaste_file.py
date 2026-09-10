from qgis.core import QgsLayerTreeGroup, QgsVectorLayer, QgsSingleSymbolRenderer, QgsSymbolLegendNode, QgsLayerTreeModelLegendNode
from qgis.PyQt.QtWidgets import QMessageBox

_copied_symbol = None


def _get_selection(iface):
    view = iface.layerTreeView()
    nodes = view.selectedNodes()
    legend_nodes = view.selectedLegendNodes()
    return nodes, legend_nodes


def copy_symbol(iface, dock_widget):
    global _copied_symbol
    nodes, legend_nodes = _get_selection(iface)
    total = len(nodes) + len(legend_nodes)

    if total == 0:
        QMessageBox.warning(dock_widget, "경고", "복사할 레이어(또는 심볼)를 선택해주세요.")
        return
    if total > 1:
        QMessageBox.warning(dock_widget, "경고", "레이어(또는 심볼)를 하나만 선택해주세요.")
        return

    if legend_nodes:
        legend_node = legend_nodes[0]
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            QMessageBox.warning(dock_widget, "경고", "심볼이 없는 항목입니다.")
            return
        _copied_symbol = legend_node.symbol().clone()
        QMessageBox.information(dock_widget, "완료", "심볼이 복사되었습니다.")
        return

    node = nodes[0]
    if isinstance(node, QgsLayerTreeGroup):
        QMessageBox.warning(dock_widget, "경고", "그룹은 선택할 수 없습니다. 레이어를 선택해주세요.")
        return

    layer = node.layer()
    if not isinstance(layer, QgsVectorLayer):
        QMessageBox.warning(dock_widget, "경고", "벡터 레이어만 심볼을 복사할 수 있습니다.")
        return

    renderer = layer.renderer()
    if isinstance(renderer, QgsSingleSymbolRenderer):
        _copied_symbol = renderer.symbol().clone()
        QMessageBox.information(dock_widget, "완료", "심볼이 복사되었습니다.")
    else:
        QMessageBox.warning(dock_widget, "경고", "분류된 심볼입니다. 레이어를 펼쳐서 복사할 개별 심볼을 선택해주세요.")


def paste_symbol(iface, dock_widget):
    if _copied_symbol is None:
        QMessageBox.warning(dock_widget, "경고", "먼저 심볼을 복사해주세요.")
        return

    nodes, legend_nodes = _get_selection(iface)

    if legend_nodes:
        if nodes:
            QMessageBox.warning(dock_widget, "경고", "레이어와 심볼을 함께 선택할 수 없습니다.")
            return

        touched_layers = {}
        for legend_node in legend_nodes:
            layer = legend_node.layerNode().layer()
            renderer = layer.renderer()
            rule_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
            renderer.setLegendSymbolItem(rule_key, _copied_symbol.clone())
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

        for layer in touched_layers.values():
            layer.triggerRepaint()
            iface.layerTreeView().refreshLayerSymbology(layer.id())

        QMessageBox.information(dock_widget, "완료", f"{len(legend_nodes)}개 심볼이 붙여넣기 되었습니다.")
        return

    if not nodes:
        QMessageBox.warning(dock_widget, "경고", "붙여넣을 레이어를 선택해주세요.")
        return

    if any(isinstance(n, QgsLayerTreeGroup) for n in nodes):
        QMessageBox.warning(dock_widget, "경고", "그룹에는 붙여넣을 수 없습니다. 레이어만 선택해주세요.")
        return

    applied = 0
    for node in nodes:
        layer = node.layer()
        if not isinstance(layer, QgsVectorLayer):
            continue
        layer.setRenderer(QgsSingleSymbolRenderer(_copied_symbol.clone()))
        layer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(layer.id())
        applied += 1

    if applied == 0:
        QMessageBox.warning(dock_widget, "경고", "벡터 레이어에만 붙여넣을 수 있습니다.")
        return

    QMessageBox.information(dock_widget, "완료", f"{applied}개 레이어에 심볼이 붙여넣기 되었습니다.")
