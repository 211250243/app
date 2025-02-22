import cv2
import os
import shutil
import random
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, QThread, QEventLoop, QTimer, QCoreApplication
from PySide6.QtGui import QPixmap, QColor, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QCheckBox, QWidget, QListWidgetItem, \
    QGraphicsPixmapItem, QGraphicsBlurEffect, QGraphicsRectItem, QGraphicsScene, QGraphicsView, \
    QFileDialog, QAbstractItemView, QMessageBox, QProgressDialog

import config
from server import Server
from utils import is_image, join_path, ProgressDialog, show_message_box, CustomProgressDialog
from PySide6.QtCore import Signal


class LoadImages:
    def __init__(self, ui):
        super().__init__()
        self.sample_path = config.SAMPLE_PATH
        self.ui = ui
        self.progressDialog = None

    def run_with_progress(self):
        self.progressDialog = QProgressDialog(self.ui)
        self.progressDialog.setWindowTitle("加载图片")
        self.progressDialog.setLabelText("正在加载图片...")
        self.progressDialog.setRange(0, 100)
        self.progressDialog.setCancelButton(None) # 隐藏取消按钮
        # 执行加载图片的操作
        self.progressDialog.show()
        QTimer.singleShot(100, self.run)  # Run the image loading process after a short delay
        self.progressDialog.exec() # 阻塞当前代码的执行，直到对话框关闭

    def run_with_wait(self):
        self.progressDialog = CustomProgressDialog(self.ui)
        self.progressDialog.show()

        # 启动一个定时器来逐步更新进度
        self.timer = QTimer()
        self.timer.timeout.connect(self.run)  # 每隔一段时间更新一次进度
        self.timer.start(100)  # 每 100 毫秒触发一次
        # self.timer.stop()
        # self.progressDialog.close()

    def run(self):
        """
        加载工作目录下的 img 文件夹中的图片，并添加到列表中
        """
        # 清空图片列表
        self.ui.imageList.clear()
        # 获取 img 文件夹中的所有图片
        if not os.path.exists(self.sample_path):
            os.makedirs(self.sample_path)
        # 遍历并上传图片
        images = [f for f in os.listdir(self.sample_path) if is_image(f)]
        total_images = len(images)
        for index, image in enumerate(images):
            # 向图片列表中添加一张图片
            image_path = os.path.join(self.sample_path, image)
            self.add_image_to_list(image_path, image, index)
            # 更新进度条
            if self.progressDialog:
                progress = int((index + 1) / total_images * 100)
                self.progressDialog.setValue(progress)

    def add_image_to_list(self, image_path, image_name, index):
        """
        向图片列表中添加一张图片
        """
        item = CustomListWidgetItem(image_path, image_name, index)
        self.ui.imageList.addItem(item) # 添加 QListWidgetItem
        self.ui.imageList.setItemWidget(item, item.item_widget) # 设置 QWidget 小部件作为项的显示内容
        # 存储复选框（或其他控件）作为该项的数据
        # 1: item.setData(0, checkbox) -> item.data(0)
        # 2: 也可直接查找widget中的控件
        # 3: 创建一个自定义的 QListWidgetItem 类，将复选框作为属性存储

class SampleHandler:
    """
    处理 SampleWidget中的所有操作
    """
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self.sample_path = config.SAMPLE_PATH
        # 将所有子控件添加为实例属性
        for child in self.ui.findChildren(QWidget):
            setattr(self.ui, child.objectName(), child)
        # 初始化各部分
        self.init_image_list()
        self.init_detail_frame()
        self.init_operate_column()
        
    def init_image_list(self):
        """
        初始化图片列表
        """
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
        LoadImages(self.ui).run_with_progress()

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

    def select_enabled(self):
        """
        选中所有图片
        """
        self.ui.imageList.clearSelection()  # Clear any selected items
        self.ui.imageList.setSelectionMode(QAbstractItemView.MultiSelection)  # Enable multi-selection mode
        for index in range(self.ui.imageList.count()):
            item = self.ui.imageList.item(index)
            checkbox = item.checkbox  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setVisible(True)

    def select_disabled(self):
        """
        取消所有图片的选中状态
        """
        self.ui.imageList.clearSelection()  # Clear any selected items
        self.ui.imageList.setSelectionMode(QAbstractItemView.SingleSelection)  # Enable single-selection mode
        for index in range(self.ui.imageList.count()):
            item = self.ui.imageList.item(index)
            checkbox = item.checkbox  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setVisible(False)

    def select_all_images(self):
        """
        选中所有图片
        """
        for index in range(self.ui.imageList.count()):
            item = self.ui.imageList.item(index)
            item.setSelected(True)
            checkbox = item.checkbox  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setChecked(True)

    def delete_images(self):
        """
        删除选中的图片
        """
        selected_items = self.ui.imageList.selectedItems()
        for item in selected_items:
            print(f"删除图片: {item.image_path}")
            image_path = item.image_path
            if os.path.exists(image_path):
                os.remove(image_path)  # 删除文件
            # self.ui.imageList.takeItem(self.ui.imageList.row(item))  # 从列表中移除项
        LoadImages(self.ui).run_with_wait()  # 重新加载图片列表
        self.clear_detail_frame()  # 清除detailFrame

    def import_dir(self):
        """
        从本地选择文件夹，导入其中的图片
        """
        # 打开文件夹选择对话框
        folder = QFileDialog.getExistingDirectory(self.ui, "选择图片文件夹")
        if folder:
            if not os.path.exists(self.sample_path):
                os.makedirs(self.sample_path)
            # 遍历文件夹中的所有图片文件
            for file_name in os.listdir(folder):
                if is_image(file_name):
                    file_path = os.path.join(folder, file_name)
                    self.copy_image(file_path)
            LoadImages(self.ui).run_with_progress()  # 重新加载图片列表

    def copy_image(self, file_path):
        """
        复制图片到 img 文件夹, 并修改权限为可读写
        """
        destination_path = os.path.join(self.sample_path, os.path.basename(file_path))
        shutil.copy(file_path, destination_path)
        os.chmod(destination_path, 0o777)

    def import_images(self):
        """
        从本地文件夹中选择图片导入
        """
        # 打开文件对话框选择图片
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles) # 设置文件对话框模式为选择多个文件
        file_dialog.setNameFilters(["Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)"]) # 设置文件过滤器
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if not os.path.exists(self.sample_path):
                os.makedirs(self.sample_path)
            for file_path in selected_files:
                self.copy_image(file_path)
            LoadImages(self.ui).run_with_progress()  # 重新加载图片列表



    # def on_ui_ready(self):
    #     print(self.ui.detailFrame.size())
    #     self.ui.view.setSceneRect(0, 0, 1000, 400)
    def init_detail_frame(self):
        """
        初始化图像预览区
        """
        # 创建场景和视图
        self.ui.scene = QGraphicsScene(self.ui.detailFrame)
        self.ui.view = QGraphicsView(self.ui.scene, self.ui.detailFrame)
        # 设置裁剪区域自适应 detailFrame 的大小
        self.ui.view.setSceneRect(0, 0, 494, 400)
        # QTimer.singleShot(0, self.on_ui_ready)

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

    def clear_detail_frame(self):
        """
        清除图像信息
        """
        if self.ui.image_item: # 如果存在图片项
            self.ui.scene.removeItem(self.ui.image_item)
            self.ui.image_item = None
        if self.ui.cropped_item: # 如果存在裁剪项
            self.ui.scene.removeItem(self.ui.cropped_item)
            self.ui.cropped_item = None
        if self.ui.crop_rect: # 如果存在裁剪框
            self.ui.scene.removeItem(self.ui.crop_rect)
            self.ui.crop_rect = None

    def show_image_info(self, item):
        """
        显示所选图片的详细信息
        """
        # 获取图片路径
        self.image_path = item.image_path

        # 创建 detailFrame 项
        self.refresh_detail_frame()

        # 获取该项的复选框（从 item 的数据中）
        checkbox = item.checkbox  # 通过 setData 和 getData 来存储和访问控件
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

    def refresh_detail_frame(self, image_path=None):
        if not image_path:
            image_path = self.image_path
        # 清除之前的图片信息
        self.clear_detail_frame()
        # 创建图片项
        self.ui.pixmap = QPixmap(image_path)
        self.ui.image_item = QGraphicsPixmapItem(self.ui.pixmap)
        self.ui.scene.addItem(self.ui.image_item)
        print(f"图片路径: {image_path}\n尺寸: {self.ui.pixmap.width()}x{self.ui.pixmap.height()}px")
        # 设置裁剪区域大小
        self.ui.view.setSceneRect(self.ui.pixmap.rect())
        self.ui.view.fitInView(self.ui.image_item, Qt.KeepAspectRatio)  # Ensure the view fits the image

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
        """
        裁剪图像
        """
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
        """
        完成裁剪
        """
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
        保存裁剪后的图像
        """
        # 先判断crop_rect是否可见，如果可见，说明还未完成裁剪
        if self.ui.crop_rect.isVisible():
            self.finish_crop()
        if self.ui.image_item and self.image_path:
            self.ui.image_item.pixmap().save(self.image_path) # 保存图像
            self.refresh_image_item(self.image_path) # 刷新这个选中项的图片

    def refresh_image_item(self, image_path=None):
        """
        刷新选中项的图片
        """
        if not image_path:
            image_path = self.image_path
        auto_pixmap = QPixmap(image_path).scaled(100, 100, Qt.KeepAspectRatio)
        selected_items = self.ui.imageList.selectedItems()[0]
        selected_items.image_label.setPixmap(auto_pixmap)

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



    def init_operate_column(self):
        """
        初始化操作栏
        """
        self.ui.shrinkDoAndExcludeBgButton.clicked.connect(self.shrink_domain_exclude_background)
        self.ui.augmentButton.clicked.connect(self.augment)
        self.ui.randomOption.clicked.connect(self.random_option)
        self.ui.optionGroup.buttonClicked.connect(self.specified_option)

    def random_option(self):
        for option in self.ui.optionGroup.buttons():
            if option.isChecked():
                option.setChecked(False)

    def specified_option(self):
        if self.ui.randomOption.isChecked():
            self.ui.randomOption.setChecked(False)

    def shrink_domain_exclude_background(self):
        """
        缩小域并排除背景
        """
        # 获取选中的项并遍历处理
        selected_items = self.ui.imageList.selectedItems()
        for item in selected_items:
            # 读取图像
            image_path = item.image_path
            image = cv2.imread(image_path)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # 找到轮廓
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                # 获取最大轮廓的边界框
                x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
                # 裁剪图像
                cropped_image = image[y:y + h, x:x + w]
                # 保存裁剪后的图像
                if self.ui.coverOption.isChecked(): # 覆盖原图
                    cv2.imwrite(image_path, cropped_image)
                elif self.ui.saveAsOption.isChecked(): # 另存为
                    cropped_image_path = image_path.replace(".", "_cropped.")
                    cv2.imwrite(cropped_image_path, cropped_image)
        # 刷新（仅当选中一项且选择了覆盖原图时刷新单项，否则刷新全部）
        if len(selected_items) == 1 and self.ui.coverOption.isChecked():
            self.refresh_image_item()
            self.refresh_detail_frame()
        else:
            LoadImages(self.ui).run_with_wait()  # 重新加载图片列表
        # LoadImages(self.ui).run()
        # if len(selected_items) == 1:
        #     self.ui.imageList.setCurrentItem(selected_items[0]) # 移动到当前项


    def augment(self):
        """
        对选中项进行数据增强，并将增强后的图片保存
        """
        selected_items = self.ui.imageList.selectedItems()
        for item in selected_items:
            image_path = item.image_path
            image = cv2.imread(image_path)
            augmented_images = []  # 存储增强后的图像

            # 随机数据增强
            if self.ui.randomOption.isChecked():
                augmented_images.append((self.random_augmentation(image)))
            # 根据指定的选项进行数据增强
            else:
                if self.ui.rotateOption.isChecked():
                    augmented_images.append((self.rotate_image(image)))
                if self.ui.turnOverOption.isChecked():
                    augmented_images.append((self.turn_over_image(image)))
                if self.ui.changeColorOption.isChecked():
                    augmented_images.append((self.change_color(image)))
                if self.ui.changeBrightnessOption.isChecked():
                    augmented_images.append((self.change_brightness(image)))

            # 保存增强后的图像
            for augmented_image, suffix in augmented_images:
                augmented_image_path = image_path.replace(".", f"_{suffix}.")
                cv2.imwrite(augmented_image_path, augmented_image)
                print(f"保存增强后的图像: {augmented_image_path}")

        LoadImages(self.ui).run_with_wait()  # 重新加载图片列表

    def random_augmentation(self, image):
        """
        随机选择一种数据增强操作
        """
        augmentations = [self.rotate_image, self.turn_over_image, self.change_brightness]
        augmentation = random.choice(augmentations)
        return augmentation(image)

    def rotate_image(self, image):
        """
        随机旋转图像
        """
        angle = random.choice([90, 180, 270])
        print(f"旋转角度: {angle}")
        if angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), "rotated"

    def turn_over_image(self, image):
        """
        随机翻转图像
        """
        flip_code = random.choice([-1, 0, 1])
        return cv2.flip(image, flip_code), "turned_over"

    def change_brightness(self, image):
        """
        随机改变图像亮度
        """
        value = random.randint(-50, 50)
        print(f"亮度值: {value}")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        v = v.astype(np.int16)  # Convert to int16 to prevent overflow
        v = np.clip(v + value, 0, 255)
        v = v.astype(np.uint8)  # Convert back to uint8
        final_hsv = cv2.merge((h, s, v))
        return cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR), "brightness_changed"

    def change_color(self, image):
        """
        随机改变图像颜色
        """
        value = random.randint(-50, 50)  # Adjust the range as needed
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        h = h.astype(np.int16)  # Convert to int16 to prevent overflow
        h = (h + value) % 180  # Hue values are in the range [0, 179]
        h = h.astype(np.uint8)  # Convert back to uint8
        final_hsv = cv2.merge((h, s, v))
        return cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR), "color_changed"



class CustomListWidgetItem(QListWidgetItem):
    """
    自定义 QListWidgetItem，用于存储图片路径和复选框控件
    """
    def __init__(self, image_path, image_name, index, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_path = image_path
        self.image_label = QLabel()
        self.checkbox = QCheckBox()
        self.checkbox.setVisible(False) # 初始状态下隐藏复选框
        self.setToolTip(image_path) # 鼠标悬浮时显示路径
        self.item_widget = self.create_item_widget(image_name, index)
        self.setSizeHint(self.item_widget.sizeHint()) # 设置 item 的大小以适应内容

    def create_item_widget(self, image_name, index):
        # 创建水平布局来包含复选框和图片
        item_layout = QHBoxLayout()

        # 添加序号标签
        label = QLabel(str(index + 1)) # 序号从1开始
        item_layout.addWidget(label)

        # 创建垂直布局用于放置图片和图片名
        image_layout = QVBoxLayout()
        # 添加图片
        pixmap = QPixmap(self.image_path).scaled(100, 100, Qt.KeepAspectRatio) # 设定图片缩放
        self.image_label.setPixmap(pixmap)
        image_layout.addWidget(self.image_label)
        # 添加图片名称
        name_label = QLabel(image_name)  # 直接显示图片的文件名
        image_layout.addWidget(name_label)
        # 将垂直布局添加到水平布局中
        item_layout.addLayout(image_layout)

        # 添加复选框
        item_layout.addWidget(self.checkbox)

        # 创建一个用于显示该布局的 widget
        item_widget = QWidget()
        item_widget.setLayout(item_layout)
        return item_widget


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


class UploadThread(QThread):
    """
    上传样本到服务器的线程
    """
    upload_finished = Signal(bool)  # 上传完成时发出的信号

    def __init__(self, ui):
        super().__init__()
        self.sample_path = config.SAMPLE_PATH
        self.remote_dir = config.SERVER_UPLOAD_PATH
        self.ui = ui
        self.e = "未知错误"  # 用于存储异常信息

        self.progressDialog = ProgressDialog(self.ui)
        self.upload_finished.connect(self.on_upload_finished)

    def on_upload_finished(self, success):
        self.progressDialog.close()  # 关闭进度条
        self.ui.upload_result = success  # 保存上传结果
        if success:
            print("----------------Upload success----------------")
        else:
            print("----------------Upload failed----------------")
            show_message_box("上传失败", f"失败原因：{str(self.e)}", QMessageBox.Critical, self.ui)

    def execute(self):
        self.progressDialog.show()  # 显示进度条
        self.start()  # 启动线程
        # Use QEventLoop to wait for the thread to finish
        print("----------------Upload started----------------")
        loop = QEventLoop()
        self.upload_finished.connect(loop.quit)
        loop.exec()

    def run(self):
        # 连接服务器
        server = Server()
        try:
            server.connect_to_server()
        except Exception as e:
            self.e = str(e) or "服务器连接失败"
            self.upload_finished.emit(False)
            return
        # 获取所有图片文件
        files = [f for f in os.listdir(self.sample_path) if is_image(f)]
        total_files = len(files)
        # 遍历并上传每个文件
        for index, file_name in enumerate(files):
            file_path = os.path.join(self.sample_path, file_name)
            remote_path = join_path(self.remote_dir, file_name)
            # 上传文件，若失败则停止上传
            try:
                server.upload_file(file_path, remote_path)
            except Exception as e:
                self.e = str(e) or "服务器连接断开"
                self.upload_finished.emit(False)
                return
            # 更新进度条
            progress = int((index + 1) / total_files * 100)
            self.progressDialog.setValue(progress)
        self.upload_finished.emit(True)  # 上传成功
        server.close_connection()