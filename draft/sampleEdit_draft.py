from PySide6.QtWidgets import QMainWindow, QApplication, QGraphicsRectItem, QGraphicsView, QGraphicsScene, \
    QGraphicsPixmapItem, QVBoxLayout, QPushButton, QWidget, QGraphicsBlurEffect, QHBoxLayout
from PySide6.QtGui import QPixmap, QPen, QColor, QMouseEvent
from PySide6.QtCore import Qt, QRectF, QPointF


class ResizableRectItem(QGraphicsRectItem):
    """
    可缩放、移动的裁剪框
    """
    def __init__(self, parent_widget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 保存父窗口的引用，用于调用裁剪方法
        self.parent_widget = parent_widget
        # 使裁剪框支持移动和缩放
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True) # 设置可移动
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True) # 设置可选择
        self.setFlag(QGraphicsRectItem.ItemIsFocusable, True) # 设置可聚焦
        # 添加裁剪区域框
        pen = QPen(QColor("white")) # 设置边框颜色
        pen.setWidth(3) # 设置边框宽度
        self.setPen(pen)
        self.setAcceptHoverEvents(True) # 设置接受鼠标悬停事件
        # 初始化变量
        self.resizing = False # 是否正在缩放
        self.resize_handle_size = 10 # 缩放手柄的大小
        self.cursor = Qt.ArrowCursor # 鼠标样式

    def hoverMoveEvent(self, event):
        """
        鼠标悬停事件：当鼠标悬停在缩放手柄上时，将鼠标样式设置为 SizeFDiagCursor
        """
        if self.is_on_resize_handle(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        # 如果存在之前的裁剪图像，先将其移除
        if self.parent_widget.cropped_item:
            self.parent_widget.scene.removeItem(self.parent_widget.cropped_item)
        # 如果鼠标在缩放手柄上，设置正在缩放
        if self.is_on_resize_handle(event.pos()):
            self.resizing = True
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 如果正在缩放，调整裁剪框的大小; 否则，调用父窗口的鼠标移动事件
        if self.resizing:
            rect = self.rect()
            rect.setBottomRight(event.pos())
            self.setRect(rect)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.resizing = False
        super().mouseReleaseEvent(event)
        self.parent_widget.crop_image()  # 调用父窗口的裁剪方法

    def is_on_resize_handle(self, pos):
        """
        判断鼠标是否在缩放手柄上（即右下角）
        """
        rect = self.rect()
        handle_rect = QRectF(rect.bottomRight() - QPointF(self.resize_handle_size, self.resize_handle_size), rect.bottomRight())
        return handle_rect.contains(pos)


class SampleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.show_image_info("/test/img/test.png")

    def init_ui(self):
        self.setWindowTitle("Sample Widget")
        layout = QVBoxLayout()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        layout.addWidget(self.view)

        # Add buttons for cropping and finishing
        button_layout = QHBoxLayout()
        self.crop_button = QPushButton("Crop", self)
        self.finish_button = QPushButton("Finish", self)
        self.save_button = QPushButton("Save", self)  # Add save button
        button_layout.addWidget(self.crop_button)
        button_layout.addWidget(self.finish_button)
        button_layout.addWidget(self.save_button)  # Add save button to layout
        layout.addLayout(button_layout)

        # Add buttons for scaling and rotating
        button_layout = QHBoxLayout()
        self.scale_up_button = QPushButton("Scale Up", self)
        self.scale_down_button = QPushButton("Scale Down", self)
        self.rotate_left_button = QPushButton("Rotate Left", self)
        self.rotate_right_button = QPushButton("Rotate Right", self)
        button_layout.addWidget(self.scale_up_button)
        button_layout.addWidget(self.scale_down_button)
        button_layout.addWidget(self.rotate_left_button)
        button_layout.addWidget(self.rotate_right_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Connect buttons to their respective methods
        self.crop_button.clicked.connect(self.show_crop_rect)
        self.finish_button.clicked.connect(self.finish_crop)
        self.save_button.clicked.connect(self.save_image)
        self.scale_up_button.clicked.connect(self.scale_up)
        self.scale_down_button.clicked.connect(self.scale_down)
        self.rotate_left_button.clicked.connect(self.rotate_left)
        self.rotate_right_button.clicked.connect(self.rotate_right)

        self.scale_factor = 1.0
        self.pixmap = None
        self.image_item = None
        self.crop_rect = None
        self.cropped_item = None
        self.image_path = None  # Add attribute to store image path

    def show_image_info(self, image_path: str):
        """
        显示详细图片信息
        """
        self.image_path = image_path  # Store the image path
        # 创建图片项
        self.pixmap = QPixmap(image_path)
        self.image_item = QGraphicsPixmapItem(self.pixmap)
        self.scene.addItem(self.image_item)
        # 设置裁剪区域
        self.view.setSceneRect(self.pixmap.rect())

    def show_crop_rect(self):
        """
        显示裁剪框
        """
        if self.crop_rect:
            self.crop_rect.setVisible(True)
        else:
            self.crop_rect = ResizableRectItem(self, self.image_item.pos().x(), self.image_item.pos().y(),
                                               self.image_item.pixmap().width(), self.image_item.pixmap().height())
            self.scene.addItem(self.crop_rect)

    def crop_image(self):
        if self.crop_rect:
            # 获取裁剪区域
            rect = QRectF(self.crop_rect.pos(), self.crop_rect.rect().size())
            # 创建模糊效果
            blur_effect = QGraphicsBlurEffect()
            blur_effect.setBlurRadius(10)  # 设置模糊半径
            self.image_item.setGraphicsEffect(blur_effect)  # 将模糊效果应用到图像上
            # 裁剪图像
            cropped_pixmap = self.pixmap.copy(rect.toRect())
            self.cropped_item = QGraphicsPixmapItem(cropped_pixmap)  # 创建裁剪后的图像
            self.cropped_item.setPos(rect.topLeft())  # 设置裁剪图像的位置为裁剪框的位置
            self.cropped_item.setGraphicsEffect(None)  # 移除模糊效果
            # 添加裁剪后的图像
            self.scene.addItem(self.cropped_item)

    def finish_crop(self):
        if self.crop_rect:
            # 获取裁剪区域
            rect = QRectF(self.crop_rect.pos(), self.crop_rect.rect().size())
            cropped_pixmap = self.pixmap.copy(rect.toRect()) # 裁剪图像
            # 将裁剪后的图像显示在界面上，并设置位置
            self.image_item.setPixmap(cropped_pixmap)
            self.image_item.setPos(rect.topLeft())
            # 隐藏裁剪框
            self.crop_rect.setVisible(False)

    def save_image(self):
        """
        保存裁剪/旋转/缩放后的图像
        """
        if self.image_item and self.image_path:
            self.image_item.pixmap().save(self.image_path)

    def scale_up(self):
        if self.image_item:
            self.image_item.setScale(self.image_item.scale() * 1.1)

    def scale_down(self):
        if self.image_item:
            self.image_item.setScale(self.image_item.scale() * 0.9)

    def rotate_left(self):
        if self.image_item:
            self.image_item.setRotation(self.image_item.rotation() - 10)

    def rotate_right(self):
        if self.image_item:
            self.image_item.setRotation(self.image_item.rotation() + 10)


if __name__ == "__main__":
    app = QApplication([])
    window = SampleWidget()
    window.show()
    app.exec()