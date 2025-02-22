import os
import shutil

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QPixmap, QColor, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QCheckBox, QWidget, QListWidgetItem, \
    QGraphicsPixmapItem, QGraphicsBlurEffect, QGraphicsRectItem, QPushButton, QGraphicsScene, QGraphicsView, \
    QListWidget, QFileDialog, QAbstractItemView


class SampleHandler:
    def __init__(self, ui, project_metadata):
        self.ui = ui
        # 将所有子控件添加为实例属性
        for child in self.ui.findChildren(QWidget):
            setattr(self.ui, child.objectName(), child)
        self.project_metadata = project_metadata
        self.init_detail_frame()
        self.init_image_list()  # 设置图片列表
        # self.test("B:/Development/GraduationDesign/app/test/img/test.png")

    def fold(self):
        """
        点击折叠按钮，折叠或展开左侧导航栏
        """
        # 获取当前左侧导航栏的宽度
        width = self.ui.imageList.width()
        if width > 0:
            self.ui.imageList.setFixedWidth(0)  # 隐藏导航栏，将宽度设为0
            self.ui.foldButton.move(0, self.ui.foldButton.y())  # 折叠按钮跟着向左移
        else:
            self.ui.imageList.setFixedWidth(250)  # 展开导航栏，设置宽度为200
            self.ui.foldButton.move(230, self.ui.foldButton.y())

    def init_image_list(self):
        """
        设置图片列表
        """
        # 获取当前工作目录下的 img 文件夹路径
        self.img_folder = os.path.join(self.project_metadata['project_path'], "img")
        print(f"图片文件夹路径: {self.img_folder}")
        # 设置列表样式
        self.ui.imageList.setSpacing(10) # 设置项之间的间距
        # 绑定点击事件
        self.ui.imageList.itemClicked.connect(self.show_image_info) # 设置列表项点击事件
        self.ui.foldButton.clicked.connect(self.fold) # 设置折叠按钮的点击事件
        self.ui.addButton.clicked.connect(self.import_images) # 设置添加按钮的点击事件
        self.ui.importButton.clicked.connect(self.import_dir)  # 绑定导入按钮事件
        self.ui.deleteButton.clicked.connect(self.delete_images)  # 绑定删除按钮事件
        self.ui.selectAllButton.clicked.connect(self.select_all_images)  # 绑定全选按钮事件
        self.ui.selectButton.clicked.connect(self.select_enabled)
        self.ui.completeButton.clicked.connect(self.select_disabled)
        # 加载图片
        self.load_images()

    def select_enabled(self):
        self.ui.imageList.clearSelection()  # Clear any selected items
        self.ui.imageList.setSelectionMode(QAbstractItemView.MultiSelection)  # Enable multi-selection mode
        for index in range(self.ui.imageList.count()):
            item = self.ui.imageList.item(index)
            checkbox = item.data(0)  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setVisible(True)

    def select_disabled(self):
        self.ui.imageList.clearSelection()  # Clear any selected items
        self.ui.imageList.setSelectionMode(QAbstractItemView.SingleSelection)  # Enable single-selection mode
        for index in range(self.ui.imageList.count()):
            item = self.ui.imageList.item(index)
            checkbox = item.data(0)  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setVisible(False)

    def select_all_images(self):
        """
        选中所有图片
        """
        for index in range(self.ui.imageList.count()):
            item = self.ui.imageList.item(index)
            item.setSelected(True)
            checkbox = item.data(0)  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setChecked(True)

    def delete_images(self):
        """
        删除选中的图片
        """
        selected_items = self.ui.imageList.selectedItems()
        for item in selected_items:
            print(f"删除图片: {item.toolTip()}")
            image_path = item.toolTip()
            if os.path.exists(image_path):
                os.remove(image_path)  # 删除文件
            # self.ui.imageList.takeItem(self.ui.imageList.row(item))  # 从列表中移除项
        self.load_images()  # 重新加载图片列表

    def import_dir(self):
        """
        从本地选择文件夹，导入其中的图片
        """
        # 打开文件夹选择对话框
        folder = QFileDialog.getExistingDirectory(self.ui, "选择图片文件夹")
        if folder:
            if not os.path.exists(self.img_folder):
                os.makedirs(self.img_folder)
            # 遍历文件夹中的所有图片文件
            for file_name in os.listdir(folder):
                if file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    file_path = os.path.join(folder, file_name)
                    self.copy_image(file_path)
            self.load_images()  # 重新加载图片列表

    def copy_image(self, file_path):
        """
        复制图片到 img 文件夹, 并修改权限为可读写
        """
        destination_path = os.path.join(self.img_folder, os.path.basename(file_path))
        shutil.copy(file_path, destination_path)
        os.chmod(destination_path, 0o777)

    def import_images(self):
        """
        从本地文件夹中选择图片导入
        """
        # 打开文件对话框选择图片
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles) # 设置文件对话框模式为选择多个文件
        file_dialog.setNameFilters(["Images (*.png *.jpg *.jpeg *.bmp *.gif)"])
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if not os.path.exists(self.img_folder):
                os.makedirs(self.img_folder)
            for file_path in selected_files:
                self.copy_image(file_path)
            self.load_images()  # 重新加载图片列表

    def load_images(self):
        """
        加载工作目录下的 img 文件夹中的图片，并添加到列表中
        """
        # 清空图片列表
        self.ui.imageList.clear()
        # 如果 img 文件夹存在
        if os.path.exists(self.img_folder):
            images = [f for f in os.listdir(self.img_folder) if
                      f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]

            for index, image in enumerate(images):
                image_path = os.path.join(self.img_folder, image)
                self.add_image_to_list(image_path, image, index)
        else:
            print("img 文件夹不存在")

    def add_image_to_list(self, image_path, image_name, index):
        """
        向图片列表中添加一张图片
        """
        # 创建水平布局来包含复选框和图片
        item_layout = QHBoxLayout()

        # 添加序号标签
        label = QLabel(str(index + 1))  # 序号从1开始
        item_layout.addWidget(label)

        # 创建垂直布局用于放置图片和图片名
        image_layout = QVBoxLayout()
        # 添加图片
        pixmap = QPixmap(image_path).scaled(100, 100, Qt.KeepAspectRatio)  # 设定图片缩放
        image_label = QLabel()
        image_label.setPixmap(pixmap)
        image_layout.addWidget(image_label)
        # 添加图片名称
        name_label = QLabel(image_name)  # 直接显示图片的文件名
        image_layout.addWidget(name_label)
        # 将垂直布局添加到水平布局中
        item_layout.addLayout(image_layout)

        # 添加复选框
        checkbox = QCheckBox()
        checkbox.setVisible(False)  # 初始状态下隐藏复选框
        item_layout.addWidget(checkbox)

        # 创建一个用于显示该布局的 widget
        item_widget = QWidget()
        item_widget.setLayout(item_layout)

        # 创建列表项
        item = QListWidgetItem()
        item.setSizeHint(item_widget.sizeHint())  # 设置 item 的大小以适应内容
        item.setToolTip(image_path)  # 鼠标悬浮时显示路径
        # 将复选框和其他控件添加到该项的属性（也可直接查找widget）
        item.setData(0, checkbox)  # 存储复选框（或其他控件）作为该项的数据

        # 将自定义的部件添加到列表项中
        self.ui.imageList.addItem(item)  # 添加 QListWidgetItem
        self.ui.imageList.setItemWidget(item, item_widget)  # 设置 QWidget 小部件作为项的显示内容

    # def on_ui_ready(self):
    #     print(self.ui.detailFrame.size())
    #     self.ui.view.setSceneRect(0, 0, 1000, 400)
    def init_detail_frame(self):
        layout = QVBoxLayout()
        # 创建场景和视图
        self.ui.scene = QGraphicsScene(self.ui.detailFrame)
        self.ui.view = QGraphicsView(self.ui.scene, self.ui.detailFrame)
        # 设置裁剪区域自适应 detailFrame 的大小
        self.ui.view.setSceneRect(0, 0, 494, 400)
        # QTimer.singleShot(0, self.on_ui_ready)

        layout.addWidget(self.ui.view)
        # Connect buttons to their respective methods
        self.ui.cropButton.clicked.connect(self.show_crop_rect)
        self.ui.finishButton.clicked.connect(self.finish_crop)
        self.ui.saveButton.clicked.connect(self.save_image)
        self.ui.scaleUpButton.clicked.connect(self.scale_up)
        self.ui.scaleDownButton.clicked.connect(self.scale_down)
        self.ui.rotateLeftButton.clicked.connect(self.rotate_left)
        self.ui.rotateRightButton.clicked.connect(self.rotate_right)

        self.ui.pixmap = None
        self.ui.crop_rect = None
        self.ui.cropped_item = None
        self.ui.image_item = None

    # def test(self, image_path):
    #     # 显示详细信息
    #     self.image_path = image_path  # Store the image path
    #     # 创建图片项
    #     self.ui.pixmap = QPixmap(image_path)
    #     self.ui.image_item = QGraphicsPixmapItem(self.ui.pixmap)
    #     self.ui.scene.addItem(self.ui.image_item)
    #     # 设置裁剪区域
    #     self.ui.view.setSceneRect(self.ui.pixmap.rect())
    def show_image_info(self, item):
        """
        显示所选图片的详细信息
        """
        # Hide or remove the existing crop rectangle
        if self.ui.crop_rect:
            self.ui.scene.removeItem(self.ui.crop_rect)
            self.ui.crop_rect = None
        # Remove the cropped image item if it exists
        if self.ui.cropped_item:
            self.ui.scene.removeItem(self.ui.cropped_item)
            self.ui.cropped_item = None
        # 获取图片路径
        image_path = item.toolTip()

        # 获取图片的尺寸信息
        pixmap = QPixmap(image_path)
        width = pixmap.width()
        height = pixmap.height()

        # 显示详细信息
        print(f"图片路径: {image_path}\n尺寸: {width}x{height}px")
        self.image_path = image_path  # Store the image path

        # 删除之前的图片项
        if self.ui.image_item:
            self.ui.scene.removeItem(self.ui.image_item)
        # 创建图片项
        self.ui.pixmap = QPixmap(image_path)
        self.ui.image_item = QGraphicsPixmapItem(self.ui.pixmap)
        self.ui.scene.addItem(self.ui.image_item)
        # 设置裁剪区域大小
        self.ui.view.setSceneRect(self.ui.pixmap.rect())
        self.ui.view.fitInView(self.ui.image_item, Qt.KeepAspectRatio)  # Ensure the view fits the image

        # 获取该项的复选框（从 item 的数据中）
        checkbox = item.data(0)  # 通过 setData 和 getData 来存储和访问控件
        if checkbox and checkbox.isVisible():
            # 切换复选框的选中状态
            checkbox.setChecked(not checkbox.isChecked())

        # # 获取该项的 widget，并通过 findChild() 查找复选框控件
        # item_widget = self.ui.imageList.itemWidget(item)
        # checkbox = item_widget.findChild(QCheckBox)  # 找到该项中的复选框
        #
        # if checkbox:
        #     # 切换复选框的选中状态
        #     checkbox.setChecked(not checkbox.isChecked())  # 切换选中状态

    def show_crop_rect(self):
        """
        显示裁剪框
        """
        if self.ui.crop_rect:
            self.ui.crop_rect.setVisible(True)
        else:
            self.ui.crop_rect = ResizableRectItem(self, self.ui.image_item.pos().x(), self.ui.image_item.pos().y(),
                                               self.ui.image_item.pixmap().width(), self.ui.image_item.pixmap().height())
            self.ui.scene.addItem(self.ui.crop_rect)

    def crop_image(self):
        if self.ui.crop_rect:
            # 获取裁剪区域
            rect = QRectF(self.ui.crop_rect.pos(), self.ui.crop_rect.rect().size())
            # 创建模糊效果
            blur_effect = QGraphicsBlurEffect()
            blur_effect.setBlurRadius(10)  # 设置模糊半径
            self.ui.image_item.setGraphicsEffect(blur_effect)  # 将模糊效果应用到图像上
            # 裁剪图像
            cropped_pixmap = self.ui.pixmap.copy(rect.toRect())
            self.ui.cropped_item = QGraphicsPixmapItem(cropped_pixmap)  # 创建裁剪后的图像
            self.ui.cropped_item.setPos(rect.topLeft())  # 设置裁剪图像的位置为裁剪框的位置
            self.ui.cropped_item.setGraphicsEffect(None)  # 移除模糊效果
            # 添加裁剪后的图像
            self.ui.scene.addItem(self.ui.cropped_item)

    def finish_crop(self):
        if self.ui.crop_rect:
            # 获取裁剪区域
            rect = QRectF(self.ui.crop_rect.pos(), self.ui.crop_rect.rect().size())
            cropped_pixmap = self.ui.pixmap.copy(rect.toRect()) # 裁剪图像
            # 将裁剪后的图像显示在界面上，并设置位置
            self.ui.image_item.setPixmap(cropped_pixmap)
            self.ui.image_item.setPos(rect.topLeft())
            # 隐藏裁剪框
            self.ui.crop_rect.setVisible(False)

    def save_image(self):
        """
        保存裁剪/旋转/缩放后的图像
        """
        # 先判断crop_rect是否可见，如果可见，说明还未完成裁剪
        if self.ui.crop_rect.isVisible():
            self.finish_crop()
        if self.ui.image_item and self.image_path:
            self.ui.image_item.pixmap().save(self.image_path)

    def scale_up(self):
        if self.ui.image_item:
            self.ui.image_item.setScale(self.ui.image_item.scale() * 1.1)

    def scale_down(self):
        if self.ui.image_item:
            self.ui.image_item.setScale(self.ui.image_item.scale() * 0.9)

    def rotate_left(self):
        if self.ui.image_item:
            self.ui.image_item.setRotation(self.ui.image_item.rotation() - 10)

    def rotate_right(self):
        if self.ui.image_item:
            self.ui.image_item.setRotation(self.ui.image_item.rotation() + 10)


class ResizableRectItem(QGraphicsRectItem):
    """
    可缩放、移动的裁剪框
    """
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 保存父窗口的引用，用于调用裁剪方法
        self.parent = parent
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
        if self.parent.ui.cropped_item:
            self.parent.ui.scene.removeItem(self.parent.ui.cropped_item)
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
        self.parent.crop_image()  # 调用父窗口的裁剪方法

    def is_on_resize_handle(self, pos):
        """
        判断鼠标是否在缩放手柄上（即右下角）
        """
        rect = self.rect()
        handle_rect = QRectF(rect.bottomRight() - QPointF(self.resize_handle_size, self.resize_handle_size), rect.bottomRight())
        return handle_rect.contains(pos)