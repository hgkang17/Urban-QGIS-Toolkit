import os
import xml.etree.ElementTree as ET

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import QPushButton
from qgis.utils import pluginMetadata

PLUGIN_FOLDER = "Urban_QGIS_Toolkit"
REPOSITORY_XML = "https://raw.githubusercontent.com/hgkang17/Urban-QGIS-Toolkit/main/plugins.xml"
UPGRADEABLE_TAB = 3
LOG_TAG = "Urban QGIS Toolkit"


def _version_tuple(text):
    parts = []
    for piece in str(text).strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _qgis_checks_this_start():
    try:
        from pyplugin_installer.installer_data import repositories
        return repositories.checkingOnStart() and repositories.timeForChecking()
    except Exception:
        return False


def _is_compatible(plugin_node):
    try:
        from pyplugin_installer.version_compare import isCompatible, pyQgisVersion
        return isCompatible(pyQgisVersion(),
                            plugin_node.findtext("qgis_minimum_version", "3.0"),
                            plugin_node.findtext("qgis_maximum_version", "3.99"))
    except Exception:
        return True


def _latest_version(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for plugin_node in root.findall("pyqgis_plugin"):
        file_name = plugin_node.findtext("file_name", "")
        if file_name.partition(".")[0] != PLUGIN_FOLDER:
            continue
        if not _is_compatible(plugin_node):
            return None
        return plugin_node.get("version") or plugin_node.findtext("version")
    return None


def _show_update_message(iface, installed, latest):
    bar = iface.messageBar()
    widget = bar.createMessage(LOG_TAG, f"새 버전 {latest} 이(가) 있습니다 (현재 {installed})")
    button = QPushButton("업데이트", widget)

    def open_plugin_manager():
        bar.popWidget(widget)
        import pyplugin_installer
        pyplugin_installer.instance().showPluginManagerWhenReady(UPGRADEABLE_TAB)

    button.pressed.connect(open_plugin_manager)
    widget.layout().addWidget(button)
    bar.pushWidget(widget, Qgis.MessageLevel.Info)
    return widget


def check_for_update(iface, plugin_dir):
    folder = os.path.basename(os.path.normpath(plugin_dir))
    if folder != PLUGIN_FOLDER:
        return None
    if _qgis_checks_this_start():
        return None

    installed = pluginMetadata(folder, "version")
    request = QNetworkRequest(QUrl(REPOSITORY_XML))
    request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                         QNetworkRequest.CacheLoadControl.AlwaysNetwork)
    reply = QgsNetworkAccessManager.instance().get(request)

    def on_finished():
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                QgsMessageLog.logMessage(f"업데이트 확인 실패: {reply.errorString()}", LOG_TAG, Qgis.MessageLevel.Info)
                return
            latest = _latest_version(bytes(reply.readAll()))
            if latest and _version_tuple(latest) > _version_tuple(installed):
                _show_update_message(iface, installed, latest)
        except Exception as error:
            QgsMessageLog.logMessage(f"업데이트 확인 중 오류: {error}", LOG_TAG, Qgis.MessageLevel.Warning)
        finally:
            reply.deleteLater()

    reply.finished.connect(on_finished)
    return reply
