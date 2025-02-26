from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout,
                               QScrollArea, QApplication)
from PySide6.QtGui import QPixmap


class DetectWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("检测结果展示")
        self._setup_ui()

    def _setup_ui(self):
        # 滚动区域设置
        self.scroll_area = QScrollArea()
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.setWidgetResizable(True)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.scroll_area)

    def add_image(self, data, filename):
        """添加新图片到界面"""
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            label = QLabel()
            label.setPixmap(pixmap.scaledToWidth(400))  # 宽度适配
            label.setToolTip(filename)  # 显示文件名
            self.scroll_layout.addWidget(label)