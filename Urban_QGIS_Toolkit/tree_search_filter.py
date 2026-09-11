from qgis.PyQt.QtCore import QSortFilterProxyModel, Qt


class RecursiveFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self.setDynamicSortFilter(True)

    def setSearchText(self, text):
        self._search_text = (text or "").strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._search_text:
            return True

        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)

        if self._matches(index):
            return True
        if self._ancestor_matches(source_parent):
            return True
        return self._has_matching_descendant(index)

    def _matches(self, index):
        text = self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole) or ""
        return self._search_text in text.lower()

    def _ancestor_matches(self, index):
        while index.isValid():
            if self._matches(index):
                return True
            index = index.parent()
        return False

    def _has_matching_descendant(self, index):
        model = self.sourceModel()
        for row in range(model.rowCount(index)):
            child = model.index(row, 0, index)
            if self._matches(child) or self._has_matching_descendant(child):
                return True
        return False
