import cv2
import os
import shutil
import random
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, QThread, QEventLoop, QTimer, QCoreApplication
from PySide6.QtGui import QPixmap, QColor, QPen, QPainter, QIcon, QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QCheckBox, QWidget, QListWidgetItem, \
    QGraphicsPixmapItem, QGraphicsBlurEffect, QGraphicsRectItem, QGraphicsScene, QGraphicsView, \
    QFileDialog, QAbstractItemView, QMessageBox, QDialog, QPushButton, QInputDialog, QLineEdit, QListWidget, \
    QFrame
from PySide6.QtUiTools import QUiLoader

import config
from server import Server
from utils import LoadingAnimation, is_image, join_path, ProgressDialog, show_message_box, update_metadata
from PySide6.QtCore import Signal


class SampleHandler:
    """
    处理 SampleWidget中的所有操作
    """

    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        # 将所有子控件添加为实例属性
        for child in self.ui.findChildren(QWidget):
            setattr(self.ui, child.objectName(), child)
        # 初始化各部分
        self.init_sample_group()
        self.init_image_list()
        self.init_detail_frame()
        self.init_operate_column()

    def init_sample_group(self):
        """
        初始化样本组
        """
        self.ui.newSampleGroupButton.clicked.connect(self.new_sample_group)
        self.ui.importSampleGroupButton.clicked.connect(self.import_sample_group)
        self.ui.deleteSampleGroupButton.clicked.connect(self.delete_sample_group)
        # 初始化样本组路径
        if 'sample_group' in config.PROJECT_METADATA and config.PROJECT_METADATA['sample_group']:
            config.SAMPLE_GROUP = self.sample_group = config.PROJECT_METADATA['sample_group']
            self.group_path = join_path(config.SAMPLE_PATH, self.sample_group, config.SAMPLE_LABEL_TRAIN_GOOD)
        else:
            self.sample_group = None
            self.group_path = config.SAMPLE_PATH
        # 确保样本组路径存在
        os.makedirs(self.group_path, exist_ok=True)

    def update_button_visibility(self):
        """
        根据当前样本组状态更新按钮显示
        """
        # 样本操作按钮区域仅当有当前样本组时显示
        has_sample_group = self.sample_group is not None
        self.ui.sampleOperationFrame.setVisible(has_sample_group)
        # 更新当前样本组标签
        if has_sample_group:
            self.ui.currentGroupLabel.setText(f"当前样本组：{self.sample_group}")
            self.ui.currentGroupLabel.setVisible(True)
            # 恢复默认按钮显示状态
            self.updateButtonState(True)
            # 重置默认裁剪框按钮状态
            self.restoreButtonState()
            # 清除detailFrame图像
            self.clear_detail_frame()
        else:
            self.ui.currentGroupLabel.setVisible(False)

    def new_sample_group(self):
        """
        新建样本组，弹出对话框让用户输入样本组名称
        """
        # 弹出自定义美化的对话框
        dialog = NewSampleGroupDialog(self.ui)
        result = dialog.exec()
        text = dialog.get_input_text()

        # 如果用户点击了确定按钮且输入了名称
        if result == QDialog.Accepted and text:
            # 创建样本组文件夹
            train_path = join_path(config.SAMPLE_PATH, text, config.SAMPLE_LABEL_TRAIN_GOOD)
            if not os.path.exists(train_path):
                # 创建训练集
                os.makedirs(train_path)
                # 更新数据
                config.SAMPLE_GROUP = self.sample_group = text
                self.group_path = train_path
                update_metadata('sample_group', text)
                # 更新按钮显示状态
                self.update_button_visibility()
                # 清空图片列表
                self.ui.imageList.clear()
                # 显示成功消息
                show_message_box("成功", f"已创建样本组：{text}", QMessageBox.Information, self.ui)
            else:  # 如果样本组已存在，显示错误消息
                show_message_box("错误", f"样本组已存在：{text}", QMessageBox.Critical, self.ui)

    def import_sample_group(self):
        """
        导入样本组，弹出自定义对话框让用户选择样本组
        """
        # 创建并显示样本组选择对话框
        dialog = SampleGroupDialog(self.ui)
        result = dialog.exec()

        # 如果用户点击了确定按钮并选择了样本组
        if result == QDialog.Accepted and dialog.selected_group:
            # 更新数据
            config.SAMPLE_GROUP = self.sample_group = dialog.selected_group
            self.group_path = join_path(config.SAMPLE_PATH, self.sample_group, config.SAMPLE_LABEL_TRAIN_GOOD)
            update_metadata('sample_group', self.sample_group)
            # 加载样本组中的图片
            LoadImages(self.ui).load_with_progress()
            # 更新按钮显示状态
            self.update_button_visibility()
            # 显示成功消息
            show_message_box("成功", f"已导入样本组：{self.sample_group}", QMessageBox.Information, self.ui)

    def delete_sample_group(self):
        """
        删除样本组，弹出样本组选择对话框让用户选择要删除的样本组
        """
        # 创建并显示样本组选择对话框
        dialog = SampleGroupDialog(self.ui)
        dialog.setWindowTitle("删除样本组")
        # 修改对话框标题标签文本
        dialog.ui.titleLabel.setText("请选择要删除的样本组：")
        result = dialog.exec()

        # 如果用户点击了确定按钮并选择了样本组
        if result == QDialog.Accepted and dialog.selected_group:
            # 获取选中的样本组名称
            sample_group = dialog.selected_group
            # 弹出确认对话框
            confirm = QMessageBox.question(
                self.ui,
                "确认删除",
                f"确定要删除样本组 {sample_group} 吗？\n此操作将删除该样本组的所有图片，且不可恢复！",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            # 如果用户确认删除
            if confirm == QMessageBox.Yes:
                # 获取样本组路径
                group_path = join_path(config.SAMPLE_PATH, sample_group)
                try:
                    # 删除样本组文件夹及其内容
                    shutil.rmtree(group_path)
                    # 如果删除的是当前样本组，清空当前样本组
                    if self.sample_group == sample_group:
                        config.SAMPLE_GROUP = self.sample_group = None
                        self.group_path = config.SAMPLE_PATH
                        update_metadata('sample_group', None)
                        # 更新按钮显示状态
                        self.update_button_visibility()
                        # 清空图片列表
                        self.ui.imageList.clear()
                    # 显示成功消息
                    show_message_box("成功", f"已删除样本组：{sample_group}", QMessageBox.Information, self.ui)
                except Exception as e:
                    # 如果删除失败，显示错误消息
                    show_message_box("错误", f"删除样本组失败：{str(e)}", QMessageBox.Critical, self.ui)

    def init_image_list(self):
        """
        初始化图片列表
        """
        # 设置列表样式
        self.ui.imageList.setSpacing(10)  # 设置项之间的间距
        # 绑定点击事件
        self.ui.imageList.itemClicked.connect(self.show_image_info)  # 设置列表项点击事件
        self.ui.foldButton.clicked.connect(self.fold)  # 设置折叠按钮的点击事件
        self.ui.addButton.clicked.connect(self.import_images)  # 设置添加按钮的点击事件
        self.ui.importButton.clicked.connect(self.import_dir)  # 绑定导入按钮事件
        self.ui.deleteButton.clicked.connect(self.delete_images)  # 绑定删除按钮事件
        self.ui.selectAllButton.clicked.connect(self.select_all_images)  # 绑定全选按钮事件
        self.ui.selectButton.clicked.connect(self.select_enabled)
        self.ui.completeButton.clicked.connect(self.select_disabled)
        # 加载图片
        if self.sample_group:
            LoadImages(self.ui).load_with_progress()  # 加载图片列表
            self.update_button_visibility()  # 更新按钮显示状态

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
        # 更改按钮显示状态
        self.updateButtonState(False)

    def updateButtonState(self, state: bool):
        """
        修改按钮显示状态，True为默认状态
        """
        self.ui.selectButton.setVisible(state)
        self.ui.importButton.setVisible(state)
        self.ui.addButton.setVisible(state)
        self.ui.deleteButton.setVisible(not state)
        self.ui.selectAllButton.setVisible(not state)
        self.ui.completeButton.setVisible(not state)

    def select_disabled(self):
        """
        取消所有图片的选中状态, 并恢复按钮显示状态
        """
        self.ui.imageList.clearSelection()  # Clear any selected items
        self.ui.imageList.setSelectionMode(QAbstractItemView.SingleSelection)  # Enable single-selection mode
        for index in range(self.ui.imageList.count()):
            item = self.ui.imageList.item(index)
            checkbox = item.checkbox  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setVisible(False)
        # 恢复按钮显示状态
        self.updateButtonState(True)

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
        LoadImages(self.ui).load_with_animation()  # 重新加载图片列表
        self.clear_detail_frame()  # 清除detailFrame
        # 删除完图片后，重置选择模式为禁用状态
        self.select_disabled()

    def import_dir(self):
        """
        从本地选择文件夹，导入其中的图片
        """
        # 打开文件夹选择对话框
        folder = QFileDialog.getExistingDirectory(self.ui, "选择图片文件夹")
        if folder:
            # 遍历文件夹中的所有图片文件
            for file_name in os.listdir(folder):
                if is_image(file_name):
                    file_path = join_path(folder, file_name)
                    self.copy_image(file_path)
            LoadImages(self.ui).load_with_progress()  # 重新加载图片列表

    def copy_image(self, file_path):
        """
        复制图片到 img 文件夹, 并修改权限为可读写
        """
        destination_path = join_path(self.group_path, os.path.basename(file_path))
        shutil.copy(file_path, destination_path)
        os.chmod(destination_path, 0o777)

    def import_images(self):
        """
        从本地文件夹中选择图片导入
        """
        # 打开文件对话框选择图片
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles)  # 设置文件对话框模式为选择多个文件
        file_dialog.setNameFilters(["Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)"])  # 设置文件过滤器
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            for file_path in selected_files:
                self.copy_image(file_path)
            LoadImages(self.ui).load_with_progress()  # 重新加载图片列表

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
        # 设置视图自适应 detailFrame 的大小
        self.ui.view.setGeometry(0, 0, 475, 400)
        # self.ui.view.setSceneRect(0, 0, 494, 400)
        # QTimer.singleShot(0, self.on_ui_ready)

        # 绑定按钮事件
        self.ui.cropButton.clicked.connect(self.show_crop_rect)
        self.ui.acceptButton.clicked.connect(self.accept_crop)
        self.ui.rejectButton.clicked.connect(self.reject_crop)
        self.ui.cancelButton.clicked.connect(self.cancel_crop)
        self.ui.saveButton.clicked.connect(self.save_image)
        self.ui.scaleUpButton.clicked.connect(self.scale_up)
        self.ui.scaleDownButton.clicked.connect(self.scale_down)
        self.ui.rotateLeftButton.clicked.connect(self.rotate_left)
        self.ui.rotateRightButton.clicked.connect(self.rotate_right)
        # 初始化裁剪框默认按钮状态
        self.restoreButtonState()

        # 初始化变量
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
        if not hasattr(self.ui, 'scene'):
            return  # 如果场景尚未初始化，直接返回
        if self.ui.image_item:  # 如果存在图片项
            self.ui.scene.removeItem(self.ui.image_item)
            self.ui.image_item = None
        if self.ui.cropped_item:  # 如果存在裁剪项
            self.ui.scene.removeItem(self.ui.cropped_item)
            self.ui.cropped_item = None
        if self.ui.crop_rect:  # 如果存在裁剪框
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

        # 重置裁剪框默认按钮状态
        self.restoreButtonState()

    def show_crop_rect(self):
        """
        显示裁剪框
        """
        # 移除已有的裁剪框（如果存在）
        if self.ui.crop_rect:
            self.ui.scene.removeItem(self.ui.crop_rect)
            self.ui.crop_rect = None

        # 创建新的裁剪框，确保它总是基于当前图像尺寸
        self.ui.crop_rect = ResizableRectItem(self, self.ui.image_item.pos().x(), self.ui.image_item.pos().y(),
                                              self.ui.image_item.pixmap().width(), self.ui.image_item.pixmap().height())
        self.ui.scene.addItem(self.ui.crop_rect)

        # 隐藏裁剪按钮，显示接受和拒绝按钮
        self.ui.cropButton.setVisible(False)
        self.ui.acceptButton.setVisible(True)
        self.ui.rejectButton.setVisible(True)

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

    def accept_crop(self):
        """
        接受裁剪
        """
        if self.ui.crop_rect:
            # 获取裁剪区域
            rect = QRectF(self.ui.crop_rect.pos(), self.ui.crop_rect.rect().size())
            cropped_pixmap = self.ui.pixmap.copy(rect.toRect())  # 裁剪图像
            # 将裁剪后的图像显示在界面上，并设置位置
            self.ui.image_item.setPixmap(cropped_pixmap)
            self.ui.image_item.setPos(rect.topLeft())
            # 清除裁剪框
            self.ui.scene.removeItem(self.ui.crop_rect)
            self.ui.crop_rect = None
            # 修改按钮状态
            self.ui.acceptButton.setVisible(False)
            self.ui.rejectButton.setVisible(False)
            self.ui.cancelButton.setVisible(True)
            self.ui.saveButton.setVisible(True)

    def reject_crop(self):
        """
        点击裁剪后取消操作
        """
        # 移除裁剪框
        if self.ui.crop_rect:
            self.ui.scene.removeItem(self.ui.crop_rect)
            self.ui.crop_rect = None  # 完全清除裁剪框引用
        # 移除模糊效果和裁剪预览
        if self.ui.image_item and self.ui.image_item.graphicsEffect():
            self.ui.image_item.setGraphicsEffect(None)
        if self.ui.cropped_item:
            self.ui.scene.removeItem(self.ui.cropped_item)
            self.ui.cropped_item = None
        # 恢复裁剪框默认按钮状态
        self.restoreButtonState()

    def cancel_crop(self):
        """
        点击接受后取消操作，需要恢复原始图片
        """
        self.reject_crop()
        if self.ui.image_item and self.image_path:
            # 重新加载原始图片并恢复位置
            self.ui.pixmap = QPixmap(self.image_path)
            self.ui.image_item.setPixmap(self.ui.pixmap)
            self.ui.image_item.setPos(0, 0)  # 重置位置到原点
            self.ui.image_item.setScale(1.0)  # 重置缩放比例
            self.ui.image_item.setRotation(0)  # 重置旋转角度
            # 重置视图尺寸
            self.ui.view.setSceneRect(self.ui.pixmap.rect())
            self.ui.view.fitInView(self.ui.image_item, Qt.KeepAspectRatio)

    def save_image(self):
        """
        保存裁剪后的图像
        """
        # 保存图像
        if self.ui.image_item and self.image_path:
            self.ui.image_item.pixmap().save(self.image_path)  # 保存图像
            self.refresh_image_item(self.image_path)  # 刷新这个选中项的图片
            self.refresh_detail_frame()
            # 显示保存成功提示
            show_message_box("保存成功", "图片已成功保存", QMessageBox.Information, self.ui)
        # 恢复裁剪框默认按钮状态
        self.restoreButtonState()

    def restoreButtonState(self):
        """
        恢复裁剪框默认按钮状态
        """
        self.ui.cropButton.setVisible(True)
        self.ui.acceptButton.setVisible(False)
        self.ui.rejectButton.setVisible(False)
        self.ui.cancelButton.setVisible(False)
        self.ui.saveButton.setVisible(False)

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
        self.ui.autoGenerateTestButton.clicked.connect(lambda: self.generate_test_set())
        self.ui.augmentButton.clicked.connect(self.augment)
        # 初始化augment中的选项组
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
        if not self.check_sample_group():
            return
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
                if self.ui.coverOption.isChecked():  # 覆盖原图
                    cv2.imwrite(image_path, cropped_image)
                elif self.ui.saveAsOption.isChecked():  # 另存为
                    cropped_image_path = image_path.replace(".", "_cropped.")
                    cv2.imwrite(cropped_image_path, cropped_image)
        # 刷新（仅当选中一项且选择了覆盖原图时刷新单项，否则刷新全部）
        if len(selected_items) == 1 and self.ui.coverOption.isChecked():
            self.refresh_image_item()
            self.refresh_detail_frame()
        else:
            LoadImages(self.ui).load_with_animation()  # 重新加载图片列表
        # LoadImages(self.ui).run()
        # if len(selected_items) == 1:
        #     self.ui.imageList.setCurrentItem(selected_items[0]) # 移动到当前项

    def augment(self):
        """
        对选中项进行数据增强(正样本增强)，并将增强后的图片保存
        正样本增强不会改变样本的本质特征，只增加样本的多样性
        """
        if not self.check_sample_group():
            return
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
                    augmented_images.append((self.augment_rotate_image(image)))
                if self.ui.turnOverOption.isChecked():
                    augmented_images.append((self.augment_flip_image(image)))
                if self.ui.changeColorOption.isChecked():
                    augmented_images.append((self.augment_color(image)))
                if self.ui.changeBrightnessOption.isChecked():
                    augmented_images.append((self.augment_brightness(image)))

            # 保存增强后的图像
            for augmented_image, suffix in augmented_images:
                augmented_image_path = image_path.replace(".", f"_{suffix}.")
                cv2.imwrite(augmented_image_path, augmented_image)
                print(f"保存增强后的图像: {augmented_image_path}")

        LoadImages(self.ui).load_with_animation()  # 重新加载图片列表

    def random_augmentation(self, image):
        """
        随机选择一种正样本数据增强操作
        """
        augmentations = [self.augment_rotate_image, self.augment_flip_image, self.augment_brightness,
                         self.augment_color]
        augmentation = random.choice(augmentations)
        return augmentation(image)

    def augment_rotate_image(self, image):
        """
        随机旋转图像 - 正样本几何变换
        保持物体特征不变，只改变视角
        """
        angle = random.choice([90, 180, 270])
        print(f"旋转角度: {angle}")
        if angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), "rotated90"
        elif angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180), "rotated180"
        elif angle == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), "rotated270"

    def augment_flip_image(self, image):
        """
        随机翻转图像 - 正样本几何变换
        保持物体特征不变，只改变视角
        """
        flip_code = random.choice([-1, 0, 1])
        flip_name = "flip_both" if flip_code == -1 else ("flip_vertical" if flip_code == 0 else "flip_horizontal")
        return cv2.flip(image, flip_code), flip_name

    def augment_brightness(self, image):
        """
        随机改变图像亮度 - 正样本光照变化
        轻微调整亮度，模拟不同光照条件，但不会产生异常
        范围控制在[-30, 30]，避免过度偏离正常样本
        """
        value = random.randint(-30, 30)  # 保持较小的变化范围
        print(f"正样本亮度调整值: {value}")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        v = v.astype(np.int16)  # Convert to int16 to prevent overflow
        v = np.clip(v + value, 0, 255)
        v = v.astype(np.uint8)  # Convert back to uint8
        final_hsv = cv2.merge((h, s, v))
        return cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR), "brightness_normal"

    def augment_color(self, image):
        """
        随机改变图像颜色 - 正样本色调变化
        轻微调整色相，模拟不同色温，但不会产生异常
        范围控制在[-20, 20]，避免过度偏离正常样本
        """
        value = random.randint(-20, 20)  # 保持较小的变化范围
        print(f"正样本色调调整值: {value}")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        h = h.astype(np.int16)  # Convert to int16 to prevent overflow
        h = (h + value) % 180  # Hue values are in the range [0, 179]
        h = h.astype(np.uint8)  # Convert back to uint8
        # 不额外增加饱和度
        final_hsv = cv2.merge((h, s, v))
        return cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR), "color_normal"

    def generate_test_set(self):
        """
        准备MVTec格式的测试集：
        1. 将部分训练样本复制到test/good文件夹
        2. 使用特殊的数据增强技术生成伪缺陷样本放入test/defect_*文件夹
        3. 同时生成对应的ground_truth掩码，放入ground_truth文件夹中

        伪缺陷样本会明显偏离正常样本的特征，模拟实际缺陷
        每种缺陷类型都有独立的子文件夹
        """
        if not self.check_sample_group():
            return

        # 获取训练集路径
        train_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, config.SAMPLE_LABEL_TRAIN_GOOD)

        # 创建MVTec格式的目录结构
        test_good_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, config.SAMPLE_LABEL_TEST_GOOD)

        # 定义所有缺陷类型及其对应的文件夹名
        defect_types = {
            'color_shift': 'test/defect_color_shift',  # 颜色偏移缺陷
            'brightness': 'test/defect_brightness',  # 亮度异常缺陷
            'noise': 'test/defect_noise',  # 噪点缺陷
            'blur': 'test/defect_blur',  # 模糊缺陷
            'distortion': 'test/defect_distortion'  # 扭曲变形缺陷
        }

        # 为掩码创建ground_truth目录
        ground_truth_base = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, "ground_truth")
        ground_truth_paths = {}
        for defect_type in defect_types.keys():
            ground_truth_paths[defect_type] = join_path(ground_truth_base, 'defect_' + defect_type)

        # 测试集存在性检查
        test_paths = [test_good_path] + [join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, path)
                                         for path in defect_types.values()]
        test_paths.append(ground_truth_base)  # 添加ground_truth目录到检查列表

        if any(os.path.exists(path) and len(os.listdir(path)) > 0 for path in test_paths):
            confirm = QMessageBox.question(
                self.ui,
                "确认覆盖",
                "已存在测试集数据，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm == QMessageBox.No:
                return
            # 清空测试集文件夹
            for path in test_paths:
                if os.path.exists(path):
                    for file in os.listdir(path):
                        file_path = join_path(path, file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                        elif os.path.isdir(file_path):
                            # 这里处理ground_truth下的子目录
                            shutil.rmtree(file_path)

        # 创建必要的目录
        os.makedirs(test_good_path, exist_ok=True)
        for defect_path in defect_types.values():
            full_defect_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, defect_path)
            os.makedirs(full_defect_path, exist_ok=True)
        # 创建ground_truth目录
        for gt_path in ground_truth_paths.values():
            os.makedirs(gt_path, exist_ok=True)

        # 获取训练集中的所有图片
        train_images = [f for f in os.listdir(train_path) if os.path.isfile(join_path(train_path, f)) and is_image(f)]

        # 如果训练集为空，显示错误消息并返回
        if not train_images:
            show_message_box("错误", "训练集中没有图片！", QMessageBox.Critical)
            return

        # 计算需要移动到测试集的图片数量
        test_count = max(1, int(len(train_images) * config.TEST_RATIO))

        # 随机选择图片复制到测试集
        test_images = random.sample(train_images, test_count)

        # 复制图片到测试集good文件夹
        for image_name in test_images:
            src_path = join_path(train_path, image_name)
            dst_path = join_path(test_good_path, image_name)
            shutil.copy(src_path, dst_path)  # 复制而不是移动

        # 生成伪缺陷样本
        # 选择部分训练图片作为生成伪缺陷样本的基础
        defect_base_count = min(5, len(train_images))  # 最多使用5张基础图片
        defect_base_images = random.sample(train_images, defect_base_count)

        # 记录每种缺陷类型生成的样本数量
        defect_counts = {defect_type: 0 for defect_type in defect_types.keys()}

        for image_name in defect_base_images:
            image_path = join_path(train_path, image_name)
            image = cv2.imread(image_path)
            if image is None:
                continue

            # 1. 颜色偏移缺陷 - 使用带掩码的版本
            defect_img, mask = self.defect_color_shift_with_mask(image)
            defect_filename = f"defect_{defect_counts['color_shift']}.jpg"
            defect_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP,
                                    defect_types['color_shift'], defect_filename)
            cv2.imwrite(defect_path, defect_img)

            # 保存对应的ground_truth掩码
            mask_path = join_path(ground_truth_paths['color_shift'],
                                  f"defect_{defect_counts['color_shift']}.png")
            cv2.imwrite(mask_path, mask)
            defect_counts['color_shift'] += 1

            # 2. 亮度异常缺陷 - 使用带掩码的版本
            defect_img, mask = self.defect_brightness_with_mask(image)
            defect_filename = f"defect_{defect_counts['brightness']}.jpg"
            defect_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP,
                                    defect_types['brightness'], defect_filename)
            cv2.imwrite(defect_path, defect_img)

            # 保存对应的ground_truth掩码
            mask_path = join_path(ground_truth_paths['brightness'],
                                  f"defect_{defect_counts['brightness']}.png")
            cv2.imwrite(mask_path, mask)
            defect_counts['brightness'] += 1

            # 3. 噪点缺陷 - 使用带掩码的版本
            defect_img, mask = self.defect_add_noise_with_mask(image)
            defect_filename = f"defect_{defect_counts['noise']}.jpg"
            defect_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP,
                                    defect_types['noise'], defect_filename)
            cv2.imwrite(defect_path, defect_img)

            # 保存对应的ground_truth掩码
            mask_path = join_path(ground_truth_paths['noise'],
                                  f"defect_{defect_counts['noise']}.png")
            cv2.imwrite(mask_path, mask)
            defect_counts['noise'] += 1

            # 4. 模糊缺陷 - 使用带掩码的版本
            defect_img, mask = self.defect_add_blur_with_mask(image)
            defect_filename = f"defect_{defect_counts['blur']}.jpg"
            defect_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP,
                                    defect_types['blur'], defect_filename)
            cv2.imwrite(defect_path, defect_img)

            # 保存对应的ground_truth掩码
            mask_path = join_path(ground_truth_paths['blur'],
                                  f"defect_{defect_counts['blur']}.png")
            cv2.imwrite(mask_path, mask)
            defect_counts['blur'] += 1

            # 5. 扭曲变形缺陷 - 使用带掩码的版本
            defect_img, mask = self.defect_add_distortion_with_mask(image)
            defect_filename = f"defect_{defect_counts['distortion']}.jpg"
            defect_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP,
                                    defect_types['distortion'], defect_filename)
            cv2.imwrite(defect_path, defect_img)

            # 保存对应的ground_truth掩码
            mask_path = join_path(ground_truth_paths['distortion'],
                                  f"defect_{defect_counts['distortion']}.png")
            cv2.imwrite(mask_path, mask)
            defect_counts['distortion'] += 1

        # 显示成功消息，包含每种缺陷类型的数量
        success_message = f"已准备测试集数据：\n- test/good: {len(test_images)}张正常图片"
        for defect_type, count in defect_counts.items():
            success_message += f"\n- {defect_types[defect_type]}: {count}张缺陷图片"
        success_message += f"\n- ground_truth: 已生成所有缺陷的掩码"

        show_message_box(
            "成功",
            success_message,
            QMessageBox.Information
        )

    def defect_add_distortion_with_mask(self, image):
        """
        伪缺陷：局部扭曲/变形，同时返回变形区域的掩码
        添加明显的非线性变形，模拟凹陷、变形等结构缺陷

        返回:
            (变形后的图像, 变形区域的掩码)
        """
        height, width = image.shape[:2]

        # 创建扭曲映射
        map_x = np.zeros((height, width), dtype=np.float32)
        map_y = np.zeros((height, width), dtype=np.float32)

        # 创建掩码，初始为黑色（无缺陷）
        mask = np.zeros((height, width), dtype=np.uint8)

        # 随机选择一个区域进行扭曲
        cx, cy = random.randint(width // 4, 3 * width // 4), random.randint(height // 4, 3 * height // 4)
        radius = min(width, height) // 4
        strength = 60  # 更大的扭曲强度

        # 生成扭曲映射
        for y in range(height):
            for x in range(width):
                dx = x - cx
                dy = y - cy
                distance = np.sqrt(dx * dx + dy * dy)

                if distance < radius:
                    # 在扭曲区域内生成掩码（255为白色，表示缺陷区域）
                    mask[y, x] = 255

                    factor = 1 - distance / radius
                    angle = factor * strength * (np.pi / 180)
                    nx = x + dx * np.cos(angle) - dy * np.sin(angle) - dx
                    ny = y + dx * np.sin(angle) + dy * np.cos(angle) - dy
                    map_x[y, x] = nx
                    map_y[y, x] = ny
                else:
                    map_x[y, x] = x
                    map_y[y, x] = y

        # 应用扭曲
        distorted = cv2.remap(image, map_x, map_y, cv2.INTER_LINEAR)

        return distorted, mask

    def defect_color_shift_with_mask(self, image):
        """
        伪缺陷：强烈颜色偏移，同时返回掩码
        在图像的随机局部区域显著改变图像颜色，模拟局部褪色、氧化等缺陷

        返回:
            (颜色偏移后的图像, 颜色偏移区域的掩码)
        """
        height, width = image.shape[:2]

        # 创建掩码，初始为黑色（无缺陷）
        mask = np.zeros((height, width), dtype=np.uint8)

        # 随机选择一个区域进行颜色偏移
        # 可以是圆形、椭圆形或多边形区域
        shape_type = random.choice(["circle", "ellipse", "polygon"])

        # 复制原始图像，我们将在此基础上修改
        result_image = image.copy()

        if shape_type == "circle":
            # 圆形缺陷区域
            center_x = random.randint(width // 4, 3 * width // 4)
            center_y = random.randint(height // 4, 3 * height // 4)
            radius = random.randint(min(height, width) // 10, min(height, width) // 5)

            # 转换图像到HSV空间以便修改颜色
            hsv_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2HSV)

            # 对图像的每个像素检查是否在圆内
            for y in range(height):
                for x in range(width):
                    dist = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
                    if dist <= radius:
                        # 在圆内区域修改颜色
                        h, s, v = hsv_image[y, x]
                        h = (h + random.randint(70, 100)) % 180  # 大幅度的颜色偏移
                        s = min(255, s + random.randint(30, 70))  # 增加饱和度使缺陷更明显
                        hsv_image[y, x] = [h, s, v]

                        # 在掩码上标记缺陷区域（白色）
                        mask[y, x] = 255

            # 将修改后的HSV图像转换回BGR
            result_image = cv2.cvtColor(hsv_image, cv2.COLOR_HSV2BGR)

        elif shape_type == "ellipse":
            # 椭圆形缺陷区域
            center_x = random.randint(width // 4, 3 * width // 4)
            center_y = random.randint(height // 4, 3 * height // 4)
            axis_x = random.randint(width // 10, width // 3)
            axis_y = random.randint(height // 10, height // 3)
            angle = random.randint(0, 180)

            # 转换图像到HSV空间以便修改颜色
            hsv_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2HSV)

            # 创建椭圆掩码
            cv2.ellipse(mask, (center_x, center_y), (axis_x, axis_y), angle, 0, 360, 255, -1)

            # 对掩码中为白色的像素进行颜色偏移
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        h, s, v = hsv_image[y, x]
                        h = (h + random.randint(70, 100)) % 180  # 大幅度的颜色偏移
                        s = min(255, s + random.randint(30, 70))  # 增加饱和度使缺陷更明显
                        hsv_image[y, x] = [h, s, v]

            # 将修改后的HSV图像转换回BGR
            result_image = cv2.cvtColor(hsv_image, cv2.COLOR_HSV2BGR)

        else:  # polygon
            # 多边形缺陷区域
            vertices = random.randint(3, 6)  # 随机选择3到6个顶点
            points = []

            # 生成多边形的顶点
            center_x = width // 2
            center_y = height // 2
            radius = min(width, height) // 4

            for i in range(vertices):
                angle = 2 * np.pi * i / vertices
                x = int(center_x + radius * np.cos(angle) * random.uniform(0.5, 1.0))
                y = int(center_y + radius * np.sin(angle) * random.uniform(0.5, 1.0))
                points.append((x, y))

            # 转换成numpy数组
            points = np.array(points, np.int32)
            points = points.reshape((-1, 1, 2))

            # 创建多边形掩码
            cv2.fillPoly(mask, [points], 255)

            # 转换图像到HSV空间以便修改颜色
            hsv_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2HSV)

            # 对掩码中为白色的像素进行颜色偏移
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        h, s, v = hsv_image[y, x]
                        h = (h + random.randint(70, 100)) % 180  # 大幅度的颜色偏移
                        s = min(255, s + random.randint(30, 70))  # 增加饱和度使缺陷更明显
                        hsv_image[y, x] = [h, s, v]

            # 将修改后的HSV图像转换回BGR
            result_image = cv2.cvtColor(hsv_image, cv2.COLOR_HSV2BGR)

        return result_image, mask

    def defect_brightness_with_mask(self, image):
        """
        伪缺陷：亮度异常，同时返回掩码
        在图像的随机局部区域改变亮度，模拟局部曝光不足、过度曝光或光源问题

        返回:
            (亮度异常的图像, 亮度异常区域的掩码)
        """
        height, width = image.shape[:2]

        # 创建掩码，初始为黑色（无缺陷）
        mask = np.zeros((height, width), dtype=np.uint8)

        # 复制原始图像，我们将在此基础上修改
        result_image = image.copy()
        hsv_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2HSV)

        # 随机确定亮度变化类型和值
        is_dark = random.choice([True, False])
        if is_dark:
            # 暗区域
            value_change = random.randint(-120, -80)
        else:
            # 亮区域
            value_change = random.randint(80, 120)

        # 随机选择缺陷形状
        shape_type = random.choice(["gradient", "rectangle", "irregular"])

        if shape_type == "gradient":
            # 渐变式亮度变化 - 从一侧到另一侧
            direction = random.choice(["horizontal", "vertical", "diagonal"])

            if direction == "horizontal":
                # 水平方向的亮度渐变
                start_x = random.randint(0, width // 2)
                end_x = random.randint(start_x + width // 4, width)

                for y in range(height):
                    for x in range(width):
                        if start_x <= x <= end_x:
                            # 计算渐变系数，在起点处为0，终点处为1
                            ratio = min(1.0, max(0.0, (x - start_x) / (end_x - start_x)))

                            # 应用亮度变化，渐变程度随着x的增加而增强
                            h, s, v = hsv_image[y, x]
                            v = np.clip(int(v) + int(value_change * ratio), 0, 255)
                            hsv_image[y, x] = [h, s, v]

                            # 根据渐变程度确定掩码的值
                            mask[y, x] = int(255 * ratio)

            elif direction == "vertical":
                # 垂直方向的亮度渐变
                start_y = random.randint(0, height // 2)
                end_y = random.randint(start_y + height // 4, height)

                for y in range(height):
                    if start_y <= y <= end_y:
                        ratio = min(1.0, max(0.0, (y - start_y) / (end_y - start_y)))
                        for x in range(width):
                            h, s, v = hsv_image[y, x]
                            v = np.clip(int(v) + int(value_change * ratio), 0, 255)
                            hsv_image[y, x] = [h, s, v]
                            mask[y, x] = int(255 * ratio)

            else:  # diagonal
                # 对角线方向的亮度渐变
                for y in range(height):
                    for x in range(width):
                        # 计算到图像中心的距离比例
                        dy = y - height // 2
                        dx = x - width // 2
                        distance = np.sqrt(dx * dx + dy * dy)
                        max_distance = np.sqrt((width // 2) ** 2 + (height // 2) ** 2)
                        ratio = min(1.0, distance / max_distance)

                        # 应用亮度变化
                        h, s, v = hsv_image[y, x]
                        v = np.clip(int(v) + int(value_change * ratio), 0, 255)
                        hsv_image[y, x] = [h, s, v]

                        # 设置掩码值
                        mask[y, x] = int(255 * ratio)

        elif shape_type == "rectangle":
            # 矩形区域亮度变化
            rect_width = random.randint(width // 5, width // 2)
            rect_height = random.randint(height // 5, height // 2)
            rect_x = random.randint(0, width - rect_width)
            rect_y = random.randint(0, height - rect_height)

            # 创建矩形掩码
            cv2.rectangle(mask, (rect_x, rect_y), (rect_x + rect_width, rect_y + rect_height), 255, -1)

            # 对掩码中为白色的像素应用亮度变化
            for y in range(rect_y, rect_y + rect_height):
                for x in range(rect_x, rect_x + rect_width):
                    h, s, v = hsv_image[y, x]
                    v = np.clip(int(v) + value_change, 0, 255)
                    hsv_image[y, x] = [h, s, v]

        else:  # irregular
            # 不规则形状的亮度变化 - 使用多个重叠的圆形
            num_circles = random.randint(3, 6)

            # 随机确定中心点
            center_x = random.randint(width // 4, 3 * width // 4)
            center_y = random.randint(height // 4, 3 * height // 4)

            # 创建多个重叠的圆形区域
            for _ in range(num_circles):
                circle_x = center_x + random.randint(-width // 8, width // 8)
                circle_y = center_y + random.randint(-height // 8, height // 8)
                radius = random.randint(min(width, height) // 15, min(width, height) // 8)

                # 添加到掩码
                cv2.circle(mask, (circle_x, circle_y), radius, 255, -1)

            # 对掩码中为白色的像素应用亮度变化
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        h, s, v = hsv_image[y, x]
                        v = np.clip(int(v) + value_change, 0, 255)
                        hsv_image[y, x] = [h, s, v]

        # 将修改后的HSV图像转换回BGR
        result_image = cv2.cvtColor(hsv_image, cv2.COLOR_HSV2BGR)

        return result_image, mask

    def defect_add_noise_with_mask(self, image):
        """
        伪缺陷：添加噪点，同时返回掩码
        在图像的随机局部区域添加噪点，模拟灰尘、颗粒、传感器损坏等局部缺陷

        返回:
            (添加噪点后的图像, 噪点区域的掩码)
        """
        height, width = image.shape[:2]

        # 创建掩码，初始为黑色（无缺陷）
        mask = np.zeros((height, width), dtype=np.uint8)

        # 复制原始图像，我们将在此基础上修改
        result_image = image.copy()

        # 随机选择缺陷形状和位置
        noise_type = random.choice(["spot", "streak", "scattered"])

        if noise_type == "spot":
            # 圆形或椭圆形噪点区域
            center_x = random.randint(width // 4, 3 * width // 4)
            center_y = random.randint(height // 4, 3 * height // 4)

            if random.choice([True, False]):  # 圆形
                radius = random.randint(min(width, height) // 10, min(width, height) // 5)
                cv2.circle(mask, (center_x, center_y), radius, 255, -1)
            else:  # 椭圆形
                axis_x = random.randint(width // 10, width // 4)
                axis_y = random.randint(height // 10, height // 4)
                angle = random.randint(0, 180)
                cv2.ellipse(mask, (center_x, center_y), (axis_x, axis_y), angle, 0, 360, 255, -1)

            # 生成高强度的噪声
            sigma = random.randint(30, 60)  # 更高的噪声强度
            noise = np.zeros_like(result_image, dtype=np.float32)

            # 对掩码中为白色的像素添加噪声
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        # 为每个像素单独生成噪声值
                        pixel_noise = np.random.normal(0, sigma, 3)
                        result_image[y, x] = np.clip(result_image[y, x] + pixel_noise, 0, 255).astype(np.uint8)

        elif noise_type == "streak":
            # 条纹状噪点 - 可以是水平、垂直或对角线
            direction = random.choice(["horizontal", "vertical", "diagonal"])
            line_width = random.randint(max(1, min(width, height) // 30), min(width, height) // 15)

            if direction == "horizontal":
                # 水平条纹
                y_pos = random.randint(height // 4, 3 * height // 4)
                streak_height = random.randint(line_width, 2 * line_width)

                # 创建条纹掩码
                for y in range(y_pos, min(height, y_pos + streak_height)):
                    mask[y, :] = 255

                # 对掩码区域添加随机噪声
                sigma = random.randint(30, 50)
                for y in range(y_pos, min(height, y_pos + streak_height)):
                    noise_line = np.random.normal(0, sigma, (width, 3))
                    result_image[y, :] = np.clip(result_image[y, :] + noise_line, 0, 255).astype(np.uint8)

            elif direction == "vertical":
                # 垂直条纹
                x_pos = random.randint(width // 4, 3 * width // 4)
                streak_width = random.randint(line_width, 2 * line_width)

                # 创建条纹掩码
                for x in range(x_pos, min(width, x_pos + streak_width)):
                    mask[:, x] = 255

                # 对掩码区域添加随机噪声
                sigma = random.randint(30, 50)
                for x in range(x_pos, min(width, x_pos + streak_width)):
                    noise_line = np.random.normal(0, sigma, (height, 3))
                    result_image[:, x] = np.clip(result_image[:, x] + noise_line, 0, 255).astype(np.uint8)

            else:  # diagonal
                # 对角线条纹 - 使用线段
                start_x = random.randint(0, width // 4)
                start_y = random.randint(0, height // 4)
                end_x = random.randint(3 * width // 4, width)
                end_y = random.randint(3 * height // 4, height)

                # 创建对角线掩码 - 使用粗线条
                cv2.line(mask, (start_x, start_y), (end_x, end_y), 255, line_width * 2)

                # 对掩码区域添加随机噪声
                sigma = random.randint(30, 50)
                for y in range(height):
                    for x in range(width):
                        if mask[y, x] == 255:
                            pixel_noise = np.random.normal(0, sigma, 3)
                            result_image[y, x] = np.clip(result_image[y, x] + pixel_noise, 0, 255).astype(np.uint8)

        else:  # scattered
            # 散布的多个小噪点区域
            num_spots = random.randint(5, 15)
            spots_radius = random.randint(3, 10)

            # 随机位置生成多个小噪点
            for _ in range(num_spots):
                spot_x = random.randint(0, width - 1)
                spot_y = random.randint(0, height - 1)
                cv2.circle(mask, (spot_x, spot_y), spots_radius, 255, -1)

            # 对掩码区域添加高强度噪声
            sigma = random.randint(40, 70)  # 更高的噪声强度，使小噪点更明显
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        pixel_noise = np.random.normal(0, sigma, 3)
                        result_image[y, x] = np.clip(result_image[y, x] + pixel_noise, 0, 255).astype(np.uint8)

        return result_image, mask

    def defect_add_blur_with_mask(self, image):
        """
        伪缺陷：添加模糊，同时返回掩码
        在图像的随机局部区域添加模糊效果，模拟局部失焦、运动模糊、液体污渍等缺陷

        返回:
            (模糊后的图像, 模糊区域的掩码)
        """
        height, width = image.shape[:2]

        # 创建掩码，初始为黑色（无缺陷）
        mask = np.zeros((height, width), dtype=np.uint8)

        # 复制原始图像，我们将在此基础上修改
        result_image = image.copy()

        # 随机选择模糊类型
        blur_effect = random.choice(["gaussian", "motion", "median", "partial"])

        if blur_effect == "gaussian":
            # 高斯模糊 - 圆形或椭圆形区域
            center_x = random.randint(width // 4, 3 * width // 4)
            center_y = random.randint(height // 4, 3 * height // 4)

            if random.choice([True, False]):  # 圆形
                radius = random.randint(min(width, height) // 8, min(width, height) // 4)
                cv2.circle(mask, (center_x, center_y), radius, 255, -1)
            else:  # 椭圆形
                axis_x = random.randint(width // 8, width // 3)
                axis_y = random.randint(height // 8, height // 3)
                angle = random.randint(0, 180)
                cv2.ellipse(mask, (center_x, center_y), (axis_x, axis_y), angle, 0, 360, 255, -1)

            # 创建局部高斯模糊的临时图像
            kernel_size = random.choice([9, 15, 21])  # 较大的核意味着更模糊
            blurred = cv2.GaussianBlur(result_image, (kernel_size, kernel_size), 0)

            # 根据掩码融合原始图像和模糊图像
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        result_image[y, x] = blurred[y, x]

        elif blur_effect == "motion":
            # 运动模糊 - 沿特定方向的拖尾效果
            direction = random.choice(["horizontal", "vertical", "diagonal"])
            kernel_size = random.randint(15, 25)  # 运动模糊的长度

            if direction == "horizontal":
                # 水平方向的运动模糊
                kernel = np.zeros((kernel_size, kernel_size))
                kernel[kernel_size // 2, :] = 1.0 / kernel_size
                motion_blur = cv2.filter2D(result_image, -1, kernel)

                # 创建水平区域的掩码
                rect_height = random.randint(height // 5, height // 2)
                y_pos = random.randint(0, height - rect_height)
                cv2.rectangle(mask, (0, y_pos), (width, y_pos + rect_height), 255, -1)

            elif direction == "vertical":
                # 垂直方向的运动模糊
                kernel = np.zeros((kernel_size, kernel_size))
                kernel[:, kernel_size // 2] = 1.0 / kernel_size
                motion_blur = cv2.filter2D(result_image, -1, kernel)

                # 创建垂直区域的掩码
                rect_width = random.randint(width // 5, width // 2)
                x_pos = random.randint(0, width - rect_width)
                cv2.rectangle(mask, (x_pos, 0), (x_pos + rect_width, height), 255, -1)

            else:  # diagonal
                # 对角线方向的运动模糊
                angle = random.randint(30, 150)  # 运动模糊的角度
                rad_angle = np.deg2rad(angle)

                kernel = np.zeros((kernel_size, kernel_size))
                center = kernel_size // 2

                # 创建对角线模糊核
                for i in range(kernel_size):
                    offset = i - center
                    x = int(center + offset * np.cos(rad_angle))
                    y = int(center + offset * np.sin(rad_angle))
                    if 0 <= x < kernel_size and 0 <= y < kernel_size:
                        kernel[y, x] = 1.0 / kernel_size

                motion_blur = cv2.filter2D(result_image, -1, kernel)

                # 创建对角线区域的掩码 - 使用多边形
                poly_width = min(width, height) // 2
                start_x = random.randint(0, width // 4)
                start_y = random.randint(0, height // 4)

                if random.choice([True, False]):  # 左上到右下
                    points = np.array([
                        [start_x, start_y],
                        [start_x + poly_width, start_y],
                        [start_x + poly_width + poly_width // 2, start_y + poly_width // 2],
                        [start_x + poly_width, start_y + poly_width],
                        [start_x, start_y + poly_width]
                    ], np.int32)
                else:  # 右上到左下
                    start_x = random.randint(width // 2, 3 * width // 4)
                    points = np.array([
                        [start_x, start_y],
                        [start_x + poly_width, start_y],
                        [start_x + poly_width - poly_width // 2, start_y + poly_width // 2],
                        [start_x, start_y + poly_width],
                        [start_x - poly_width // 2, start_y + poly_width // 2]
                    ], np.int32)

                points = points.reshape((-1, 1, 2))
                cv2.fillPoly(mask, [points], 255)

            # 根据掩码融合原始图像和运动模糊图像
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        result_image[y, x] = motion_blur[y, x]

        elif blur_effect == "median":
            # 中值模糊 - 适合模拟液体或污渍造成的模糊
            # 不规则形状区域
            center_x = random.randint(width // 4, 3 * width // 4)
            center_y = random.randint(height // 4, 3 * height // 4)

            # 创建不规则形状掩码 - 使用多个重叠的圆形
            num_circles = random.randint(3, 7)
            base_radius = min(width, height) // 10

            for _ in range(num_circles):
                circle_x = center_x + random.randint(-width // 10, width // 10)
                circle_y = center_y + random.randint(-height // 10, height // 10)
                radius = random.randint(base_radius // 2, base_radius)
                cv2.circle(mask, (circle_x, circle_y), radius, 255, -1)

            # 应用中值模糊
            kernel_size = random.choice([7, 11, 15])  # 较大的核意味着更模糊
            median_blur = cv2.medianBlur(result_image, kernel_size)

            # 根据掩码融合原始图像和中值模糊图像
            for y in range(height):
                for x in range(width):
                    if mask[y, x] == 255:
                        result_image[y, x] = median_blur[y, x]

        else:  # partial - 渐变模糊效果，从清晰到模糊
            # 渐变模糊 - 模拟部分区域逐渐失焦
            direction = random.choice(["left-to-right", "top-to-bottom", "radial"])

            if direction == "left-to-right":
                # 水平方向渐变模糊
                start_x = random.randint(0, width // 3)
                end_x = random.randint(2 * width // 3, width)

                # 创建一系列不同强度的模糊图像
                blurred_images = []
                max_kernel = 25
                steps = 5

                for i in range(steps):
                    kernel_size = 1 + 2 * (i * max_kernel // steps)  # 确保是奇数
                    if kernel_size > 1:
                        blur = cv2.GaussianBlur(result_image, (kernel_size, kernel_size), 0)
                        blurred_images.append(blur)
                    else:
                        blurred_images.append(result_image.copy())

                # 根据x位置融合不同程度的模糊图像
                for y in range(height):
                    for x in range(width):
                        if start_x <= x <= end_x:
                            # 计算模糊程度（0到steps-1之间）
                            ratio = (x - start_x) / (end_x - start_x)
                            blur_idx = min(steps - 1, int(ratio * steps))
                            result_image[y, x] = blurred_images[blur_idx][y, x]

                            # 设置掩码 - 渐变
                            mask[y, x] = min(255, int(ratio * 255))

            elif direction == "top-to-bottom":
                # 垂直方向渐变模糊
                start_y = random.randint(0, height // 3)
                end_y = random.randint(2 * height // 3, height)

                # 创建一系列不同强度的模糊图像
                blurred_images = []
                max_kernel = 25
                steps = 5

                for i in range(steps):
                    kernel_size = 1 + 2 * (i * max_kernel // steps)  # 确保是奇数
                    if kernel_size > 1:
                        blur = cv2.GaussianBlur(result_image, (kernel_size, kernel_size), 0)
                        blurred_images.append(blur)
                    else:
                        blurred_images.append(result_image.copy())

                # 根据y位置融合不同程度的模糊图像
                for y in range(height):
                    if start_y <= y <= end_y:
                        # 计算模糊程度（0到steps-1之间）
                        ratio = (y - start_y) / (end_y - start_y)
                        blur_idx = min(steps - 1, int(ratio * steps))
                        result_image[y, :] = blurred_images[blur_idx][y, :]

                        # 设置掩码 - 渐变
                        mask[y, :] = min(255, int(ratio * 255))

            else:  # radial
                # 径向渐变模糊 - 从中心向外扩散
                center_x = random.randint(width // 3, 2 * width // 3)
                center_y = random.randint(height // 3, 2 * height // 3)
                max_radius = min(min(width, height) // 2,
                                 max(abs(center_x - 0), abs(center_x - width),
                                     abs(center_y - 0), abs(center_y - height)))

                # 创建一系列不同强度的模糊图像
                blurred_images = []
                max_kernel = 25
                steps = 5

                for i in range(steps):
                    kernel_size = 1 + 2 * (i * max_kernel // steps)  # 确保是奇数
                    if kernel_size > 1:
                        blur = cv2.GaussianBlur(result_image, (kernel_size, kernel_size), 0)
                        blurred_images.append(blur)
                    else:
                        blurred_images.append(result_image.copy())

                # 根据到中心的距离融合不同程度的模糊图像
                for y in range(height):
                    for x in range(width):
                        distance = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
                        if distance <= max_radius:
                            # 计算模糊程度（0到steps-1之间）
                            ratio = min(1.0, distance / max_radius)
                            blur_idx = min(steps - 1, int(ratio * steps))
                            result_image[y, x] = blurred_images[blur_idx][y, x]

                            # 设置掩码 - 渐变
                            mask[y, x] = min(255, int(ratio * 255))

        return result_image, mask

    def check_sample_group(self):
        """
        检查是否选择样本组
        """
        if not config.SAMPLE_GROUP:
            show_message_box("错误", "请先创建或导入样本组！", QMessageBox.Critical)
            return False
        return True


class CustomListWidgetItem(QListWidgetItem):
    """
    自定义 QListWidgetItem，用于存储图片路径和复选框控件
    """

    def __init__(self, image_path, image_name, index, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_path = image_path
        self.image_label = QLabel()
        self.checkbox = QCheckBox()
        self.checkbox.setVisible(False)  # 初始状态下隐藏复选框
        self.setToolTip(image_path)  # 鼠标悬浮时显示路径
        self.item_widget = self.create_item_widget(image_name, index)
        self.setSizeHint(self.item_widget.sizeHint())  # 设置 item 的大小以适应内容

    def create_item_widget(self, image_name, index):
        # 创建水平布局来包含复选框和图片
        item_layout = QHBoxLayout()

        # 添加序号标签
        label = QLabel(str(index + 1))  # 序号从1开始
        item_layout.addWidget(label)

        # 创建垂直布局用于放置图片和图片名
        image_layout = QVBoxLayout()
        # 添加图片
        pixmap = QPixmap(self.image_path).scaled(100, 100, Qt.KeepAspectRatio)  # 设定图片缩放
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
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)  # 设置可移动
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)  # 设置可选择
        self.setFlag(QGraphicsRectItem.ItemIsFocusable, True)  # 设置可聚焦
        # 添加裁剪区域框
        pen = QPen(QColor("white"))  # 设置边框颜色
        pen.setWidth(3)  # 设置边框宽度
        self.setPen(pen)
        self.setAcceptHoverEvents(True)  # 设置接受鼠标悬停事件
        # 初始化变量
        self.resizing = False  # 是否正在缩放
        self.resize_handle_size = 10  # 缩放手柄的大小
        self.cursor = Qt.ArrowCursor  # 鼠标样式
        # 保存原始图片边界
        self.image_rect = QRectF(args[0], args[1], args[2], args[3])
        # 设置最小尺寸
        self.min_size = 20

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
            new_pos = event.pos()
            current_pos = self.pos()

            # 计算边界的最大可拖动范围
            max_bottom = self.image_rect.height() - current_pos.y()
            max_right = self.image_rect.width() - current_pos.x()

            # 确保缩放不超出原始图片范围
            if new_pos.x() > max_right:
                new_pos.setX(max_right)
            if new_pos.y() > max_bottom:
                new_pos.setY(max_bottom)

            # 防止裁剪框反向和过小
            if new_pos.x() < self.min_size:
                new_pos.setX(self.min_size)
            if new_pos.y() < self.min_size:
                new_pos.setY(self.min_size)

            # 设置新的裁剪框大小
            rect.setBottomRight(new_pos)
            self.setRect(rect)
        else:
            # 保存当前位置，用于后续边界检查
            old_pos = self.pos()

            # 调用父类的事件处理
            super().mouseMoveEvent(event)

            # 获取移动后的位置和矩形
            current_pos = self.pos()
            current_rect = self.rect()

            # 检查是否超出图片边界
            if current_pos.x() < 0:
                current_pos.setX(0)
            if current_pos.y() < 0:
                current_pos.setY(0)

            # 检查右边界和底边界
            if current_pos.x() + current_rect.width() > self.image_rect.width():
                current_pos.setX(self.image_rect.width() - current_rect.width())
            if current_pos.y() + current_rect.height() > self.image_rect.height():
                current_pos.setY(self.image_rect.height() - current_rect.height())

            # 应用修正后的位置
            self.setPos(current_pos)

    def mouseReleaseEvent(self, event):
        """
        鼠标释放事件：结束缩放或移动操作
        """
        self.resizing = False
        super().mouseReleaseEvent(event)
        # 鼠标释放后，如果已经创建了裁剪框，则执行裁剪（预览）
        self.parent.crop_image()

    def is_on_resize_handle(self, pos):
        """
        判断鼠标是否在缩放手柄上（即右下角）
        """
        rect = self.rect()
        handle_rect = QRectF(rect.bottomRight() - QPointF(self.resize_handle_size, self.resize_handle_size),
                             rect.bottomRight())
        return handle_rect.contains(pos)


class UploadThread(QThread):
    """
    上传样本到服务器的线程
    """
    upload_finished = Signal(bool)  # 上传完成时发出的信号

    def __init__(self, ui):
        super().__init__()
        self.local_sample_path = config.SAMPLE_PATH
        self.remote_sample_path = config.SERVER_SAMPLE_PATH
        self.ui = ui
        self.e = "未知错误"  # 用于存储异常信息
        self.total_files = 0  # 总文件数
        self.uploaded_files = 0  # 已上传文件数

        msg = {
            "title": "上传样本",
            "text": "正在上传样本组..."
        }
        self.progressDialog = ProgressDialog(self.ui, msg)
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

    def count_files(self, directory):
        """统计目录中的所有图片文件数量"""
        count = 0
        for root, dirs, files in os.walk(directory):
            for file in files:
                if is_image(file):
                    count += 1
        return count

    def upload_directory_with_progress(self, server, local_path, remote_path):
        """递归上传整个目录，并更新进度条"""
        # 确保远程目录存在
        try:
            server.sftp_client.mkdir(remote_path)
        except IOError:
            pass  # 目录已存在则跳过
        # 遍历本地目录
        for item in os.listdir(local_path):
            local_item_path = join_path(local_path, item)
            remote_item_path = join_path(remote_path, item)

            if os.path.isdir(local_item_path):
                # 如果是目录，递归上传
                try:
                    server.sftp_client.mkdir(remote_item_path)
                except IOError:
                    pass  # 目录已存在则跳过
                self.upload_directory_with_progress(server, local_item_path, remote_item_path)
            elif os.path.isfile(local_item_path) and is_image(item):
                # 如果是图片文件，上传
                try:
                    server.upload_file(local_item_path, remote_item_path)
                    self.uploaded_files += 1
                    # 更新进度条
                    progress = int(self.uploaded_files / self.total_files * 100)
                    self.progressDialog.setValue(progress)
                except Exception as e:
                    self.e = str(e) or "文件上传失败"
                    raise  # 继续抛出异常

    def run(self):
        # 连接服务器
        server = Server()
        try:
            server.connect_to_server()
        except Exception as e:
            self.e = str(e) or "服务器连接失败"
            self.upload_finished.emit(False)
            return
        try:
            # 统计所有需要上传的文件数量
            self.total_files = self.count_files(self.local_sample_path)
            if self.total_files == 0:
                self.e = "没有找到可上传的图片文件"
                self.upload_finished.emit(False)
                return
            # 更新进度条文本
            self.progressDialog.setLabelText(f"正在上传 {self.total_files} 个文件...")
            # 上传整个样本组文件夹
            self.uploaded_files = 0
            self.upload_directory_with_progress(server, self.local_sample_path, self.remote_sample_path)
            # 上传成功
            self.upload_finished.emit(True)
        except Exception as e:
            self.e = str(e) or "上传过程中出错"
            self.upload_finished.emit(False)
        finally:
            server.close_connection()


class LoadImages:
    """加载图片列表的类，提供两种加载方式：进度条和加载动画"""

    def __init__(self, ui):
        self.group_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, config.SAMPLE_LABEL_TRAIN_GOOD)
        self.ui = ui

    def load_with_progress(self):
        # QCoreApplication.processEvents() # 强制处理所有之前的UI更新事件（现已移至ProgressDialog）
        """使用进度条加载图片"""
        # 创建进度对话框
        progress_dialog = ProgressDialog(self.ui, {
            "title": "加载图片",
            "text": "正在加载图片..."
        })
        # 显示对话框并开始加载
        progress_dialog.show()
        # QCoreApplication.processEvents() # 确保进度条显示！！！（现已移至ProgressDialog）

        # 重新获取图片列表
        self.ui.imageList.clear()
        images = [f for f in os.listdir(self.group_path) if is_image(f)]
        total_images = len(images)
        # 处理空图片列表情况
        if total_images == 0:
            progress_dialog.setValue(100)
            return
        # 加载图片
        for index, image in enumerate(images):
            # 添加图片到列表
            image_path = join_path(self.group_path, image)
            self._add_to_list(image_path, image, index)
            # 更新进度
            progress = int((index + 1) / total_images * 100)
            progress_dialog.setValue(progress)

    # def load_with_progress(self):
    #     """使用进度条加载图片"""
    #     # 创建进度对话框
    #     self.progress_dialog = ProgressDialog(self.ui, {
    #         "title": "加载图片",
    #         "text": "正在加载图片..."
    #     })
    #
    #     # 显示对话框并开始加载
    #     self.progress_dialog.show()
    #     QTimer.singleShot(100, self.run)  # Run the image loading process after a short delay
    #     self.progress_dialog.exec()  # 阻塞当前代码的执行，直到对话框关闭
    #
    # def run (self):
    #     # 重新获取图片列表
    #     self.ui.imageList.clear()
    #     images = [f for f in os.listdir(self.sample_path) if is_image(f)]
    #     total_images = len(images)
    #     # 处理空图片列表情况
    #     if total_images == 0:
    #         self.progress_dialog.setValue(100)
    #         return
    #     # 加载图片
    #     for index, image in enumerate(images):
    #         # 添加图片到列表
    #         image_path = join_path(self.sample_path, image)
    #         self._add_to_list(image_path, image, index)
    #         # 更新进度
    #         progress = int((index + 1) / total_images * 100)
    #         self.progress_dialog.setValue(progress)

    def load_with_animation(self):
        """使用加载动画加载图片"""
        # 创建加载动画
        loading = LoadingAnimation(self.ui)
        loading.set_text("正在加载图片...")
        loading.show()
        # QCoreApplication.processEvents()  # 确保动画显示！！！（现已移至LoadingAnimation）

        # 重新获取图片列表
        self.ui.imageList.clear()
        images = [f for f in os.listdir(self.group_path) if is_image(f)]
        # 添加所有图片到列表
        for index, image in enumerate(images):
            image_path = join_path(self.group_path, image)
            self._add_to_list(image_path, image, index)
        # 加载完成后关闭动画
        # QTimer.singleShot(2000, loading.close_animation)
        loading.close_animation()

    def _add_to_list(self, image_path, image_name, index):
        """将图片添加到列表中"""
        item = CustomListWidgetItem(image_path, image_name, index)
        self.ui.imageList.addItem(item)  # 添加 QListWidgetItem
        self.ui.imageList.setItemWidget(item, item.item_widget)  # 设置 QWidget 小部件作为项的显示内容
        # 存储复选框（或其他控件）作为该项的数据
        # 1: item.setData(0, checkbox) -> item.data(0)
        # 2: 也可直接查找widget中的控件
        # 3: 创建一个自定义的 QListWidgetItem 类，将复选框作为属性存储


class SampleGroupDialog(QDialog):
    """
    样本组选择对话框 - 使用UI文件加载
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_group = None
        # 加载UI文件
        self.ui = QUiLoader().load(r'ui\import_sample_group.ui')

        # 设置主窗口属性
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.width(), self.ui.height())

        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.ui)

        # 连接信号
        self.ui.refreshButton.clicked.connect(self.load_sample_groups)
        self.ui.okButton.clicked.connect(self.accept)
        self.ui.cancelButton.clicked.connect(self.reject)
        self.ui.listWidget.itemDoubleClicked.connect(self.accept)

        # 加载样本组
        self.load_sample_groups()

    def load_sample_groups(self):
        """
        加载样本组列表
        """
        # 清空列表
        self.ui.listWidget.clear()
        # 获取样本文件夹路径
        sample_folder = join_path(config.PROJECT_METADATA['project_path'], config.SAMPLE_FOLDER)
        # 获取样本文件夹下的所有子文件夹
        sample_groups = []
        for item in os.listdir(sample_folder):
            item_path = os.path.join(sample_folder, item)
            if os.path.isdir(item_path):
                # 检查文件夹中是否有图片文件
                has_images = any(
                    is_image(f) for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f)))
                sample_groups.append((item, has_images))
        # 如果没有样本组，显示提示
        if not sample_groups:
            empty_item = QListWidgetItem("没有找到样本组")
            empty_item.setFlags(Qt.NoItemFlags)  # 禁用选择
            self.ui.listWidget.addItem(empty_item)
            return
        # 添加样本组到列表
        for group_name, has_images in sample_groups:
            item = QListWidgetItem(group_name)
            # 如果文件夹中有图片，设置图标
            if has_images:
                item.setIcon(QIcon("icon/image.svg"))  # 假设有图片图标
            else:
                item.setIcon(QIcon("icon/folder.svg"))  # 假设有文件夹图标
            self.ui.listWidget.addItem(item)

    def get_selected_group(self):
        """
        获取选中的样本组
        """
        selected_items = self.ui.listWidget.selectedItems()
        if selected_items:
            return selected_items[0].text()
        return None

    def accept(self):
        """
        确定按钮点击事件
        """
        self.selected_group = self.get_selected_group()
        if self.selected_group:
            super().accept()
        else:
            show_message_box("提示", "请选择一个样本组", QMessageBox.Information, self)


class NewSampleGroupDialog(QDialog):
    """
    自定义美化的新建样本组对话框 - 使用UI文件加载
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 加载UI文件
        self.ui = QUiLoader().load(r'ui\new_sample_group.ui')

        # 设置主窗口属性和窗口标题
        self.setWindowTitle(self.ui.windowTitle())
        self.setFixedSize(self.ui.width(), self.ui.height())

        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.ui)

        # 连接信号
        self.ui.confirmButton.clicked.connect(self.accept)
        self.ui.cancelButton.clicked.connect(self.reject)

        # 设置焦点到输入框
        self.ui.inputField.setFocus()

    def get_input_text(self):
        """获取输入的文本"""
        return self.ui.inputField.text().strip()