from collections import deque
from qgis.core import QgsProject, QgsLayerTreeGroup, QgsLayerTreeLayer
from qgis.PyQt.QtWidgets import QMessageBox

_visibility_history = deque(maxlen=10)


def _all_layer_nodes(group):
    nodes = []
    for child in group.children():
        if isinstance(child, QgsLayerTreeGroup):
            nodes.extend(_all_layer_nodes(child))
        elif isinstance(child, QgsLayerTreeLayer):
            nodes.append(child)
    return nodes


def isolate_selected_layers(iface, ms):
    view = iface.layerTreeView()
    selected_layers = view.selectedLayers()

    if not selected_layers:
        QMessageBox.warning(ms, "경고", "표시할 레이어를 선택해주세요.")
        return

    selected_ids = {layer.id() for layer in selected_layers}

    root = QgsProject.instance().layerTreeRoot()
    all_nodes = _all_layer_nodes(root)

    snapshot = {node.layerId(): node.itemVisibilityChecked() for node in all_nodes}
    _visibility_history.append(snapshot)

    for node in all_nodes:
        node.setItemVisibilityChecked(node.layerId() in selected_ids)

    iface.mapCanvas().refresh()


def move_selected_to_top(iface, ms):
    view = iface.layerTreeView()
    root = QgsProject.instance().layerTreeRoot()

    nodes = list(view.selectedNodes())

    if not nodes:
        seen_layer_ids = set()
        for legend_node in view.selectedLegendNodes():
            layer_node = legend_node.layerNode()
            if layer_node is not None and layer_node.layerId() not in seen_layer_ids:
                seen_layer_ids.add(layer_node.layerId())
                nodes.append(layer_node)

    if not nodes:
        QMessageBox.warning(ms, "경고", "최상단으로 올릴 레이어 또는 그룹을 선택해주세요.")
        return

    def _is_descendant_of_any(node, others):
        parent = node.parent()
        while parent is not None:
            if parent in others:
                return True
            parent = parent.parent()
        return False

    nodes = [n for n in nodes if not _is_descendant_of_any(n, nodes)]

    for node in reversed(nodes):
        parent = node.parent()
        if parent is None:
            continue

        clone = node.clone()
        root.insertChildNode(0, clone)
        parent.removeChildNode(node)

    iface.mapCanvas().refresh()


def restore_previous_visibility(iface, ms):
    if not _visibility_history:
        return

    snapshot = _visibility_history.pop()

    root = QgsProject.instance().layerTreeRoot()
    all_nodes = _all_layer_nodes(root)

    for node in all_nodes:
        if node.layerId() in snapshot:
            node.setItemVisibilityChecked(snapshot[node.layerId()])

    iface.mapCanvas().refresh()
