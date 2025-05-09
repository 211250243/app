"""
让 `DetectHandler` 继承 `QObject` 并内部实现事件处理与使用单独的 `ImageClickEventFilter` 类相比，各有优劣：

### 性能方面

从运行速度来看，两种方式几乎没有明显差异：

1. **事件传递路径**：
   - 内部实现：事件直接从 `resultLabel` → `DetectHandler`
   - 外部过滤器：事件从 `resultLabel` → `ImageClickEventFilter` → `DetectHandler`

   外部过滤器多了一次函数调用，但这种微小的差异在现代处理器上基本可以忽略不计。

2. **内存占用**：
   - 内部实现：只需要一个 `DetectHandler` 对象
   - 外部过滤器：需要 `DetectHandler` 和 `ImageClickEventFilter` 两个对象

   但额外的小对象所占用的内存非常少，不会对应用性能产生实质影响。

### 设计方面

1. **继承 QObject 的影响**：
   - 让 `DetectHandler` 继承 `QObject` 意味着它获得了 Qt 的信号槽机制和事件系统支持
   - 如果 `DetectHandler` 将来需要发射信号或与其他 Qt 组件更深入地交互，这是有益的
   - 但如果 `DetectHandler` 只是作为一个功能类，不需要 Qt 的特性，那么无谓的继承会增加类的复杂性

2. **职责划分**：
   - 外部过滤器：遵循单一职责原则，`ImageClickEventFilter` 只负责事件过滤，`DetectHandler` 负责业务逻辑
   - 内部实现：将事件处理和业务逻辑混合在一起，可能导致类变得更庞大

### 哪种更好？

**从实用角度看**：内部实现更简单直接，对于这种简单的交互场景足够了。

**从设计角度看**：如果应用正在不断扩展，外部过滤器提供了更好的扩展性和维护性。

**我的建议**：
- 如果 `DetectHandler` 已经是或将来可能成为 Qt 组件体系的一部分（需要使用信号槽或其他 Qt 特性），那么让它继承 `QObject` 并内部实现事件处理是合理的
- 如果 `DetectHandler` 主要是业务逻辑类，而且应用正在变得复杂，那么使用专门的事件过滤器类可能更有利于长期维护

对于当前的应用场景，考虑到功能相对简单，我认为内部实现（让 `DetectHandler` 继承 `QObject` 并自行处理事件）是更合适的选择，它减少了类的数量，让代码更紧凑，同时没有显著的性能影响。
"""
import os
import shutil

from PySide6.QtCore import QTimer, Qt, QEvent, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (QWidget, QDialog, QMessageBox, QFileDialog, 
                             QAbstractItemView)

import config
from sample_handler import CustomListWidgetItem, SampleGroupDialog, NewSampleGroupDialog, LoadImages
from http_server import HttpServer, HttpDetectSamples, UploadSampleGroup_HTTP
from ssh_server import SSHServer, DefectSamples
from utils import ProgressDialog, check_detect_sample_group, check_sample_group, show_message_box, join_path, is_image, update_metadata, copy_image
from model_handler import ModelGroupDialog


class DetectHandler():
    """
    处理 DetectWidget中的所有操作
    """
    def __init__(self, ui):
        super().__init__()
        # 初始化
        self.ui = ui
        self.processed_files = set()
        # 初始化DefectSamples (使用HTTP服务器)
        self.detect_samples_handler = HttpDetectSamples(ui)
        # 将所有子控件添加为实例属性
        for child in self.ui.findChildren(QWidget):
            setattr(self.ui, child.objectName(), child)
            
        # 初始化样本组
        self.init_sample_group()
        # 初始化模型组
        self.init_model_group()
        # 初始化检测列表
        self.init_detect_list()
        
        # 启动检测按钮        
        self.ui.startDetectButton.clicked.connect(self.detect_samples_handler.detect_samples)
        # 设置事件过滤器（外部过滤器 -> handler继承QObject并重写eventFilter）
        self.ui.resultLabel.setCursor(Qt.PointingHandCursor)
        self.event_filter = ImageClickEventFilter(self)
        self.ui.resultLabel.installEventFilter(self.event_filter)
        # self.ui.resultLabel.installEventFilter(self)

    # def eventFilter(self, obj, event):
    #     """事件过滤器，处理图片点击事件"""
    #     if obj is self.ui.resultLabel and event.type() == QEvent.MouseButtonPress:
    #         self.toggle_image()
    #         return True
    #     return super(DetectHandler, self).eventFilter(obj, event)

    def init_sample_group(self):
        """
        初始化样本组
        """
        self.ui.newDetectSampleGroupButton.clicked.connect(self.new_sample_group)
        self.ui.importDetectSampleGroupButton.clicked.connect(self.import_sample_group)
        self.ui.deleteDetectSampleGroupButton.clicked.connect(self.delete_sample_group)
        self.ui.uploadDetectSampleGroupButton.clicked.connect(self.upload_sample_group)
        # 获取样本组并初始化路径
        sample_group = config.PROJECT_METADATA.get('detect_sample_group')
        group_path = config.SAMPLE_PATH  # 默认路径
        os.makedirs(group_path, exist_ok=True) # 确保路径存在
        if sample_group:
            # 尝试构建样本组路径
            tmp_path = join_path(group_path, sample_group)
            if os.path.exists(tmp_path):
                group_path = tmp_path
            else:
                # 路径无效时清除样本组配置
                sample_group = None
                update_metadata('detect_sample_group', None)
        # 同步配置和实例变量
        config.DETECT_SAMPLE_GROUP = self.sample_group = sample_group
        self.group_path = group_path

    def update_button_visibility(self):
        """
        根据当前样本组状态更新按钮显示
        """
        # 样本操作按钮区域仅当有当前样本组时显示
        has_sample_group = self.sample_group is not None
        self.ui.detectSampleOperationFrame.setVisible(has_sample_group)
        # 更新当前样本组标签
        self.ui.detectSampleGroupEdit.setText(self.sample_group)
        if has_sample_group:
            self.ui.currentDetectGroupLabel.setText(f"当前检测样本组：{self.sample_group}")
            self.ui.currentDetectGroupLabel.setVisible(True)
            # 恢复默认按钮显示状态
            self.updateButtonState(True)
            # 清除detailFrame图像
            self.clear_detail_frame()
        else:
            self.ui.currentDetectGroupLabel.setVisible(False)

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
            # 检查样本组名称是否合法
            if not text.isidentifier():  # 判断是否是合法的标识符
                show_message_box("错误", "样本组名称不合法！", QMessageBox.Critical)
                return
            # 创建样本组文件夹
            group_path = join_path(config.SAMPLE_PATH, text)
            if not os.path.exists(group_path):
                # 对接 http_server: 创建样本组
                try:
                    group_id = HttpServer().add_group(text)
                    print(f"http_server创建样本组成功 ID={group_id}")
                except Exception as e:
                    print(f"http_server创建样本组失败: {str(e)}")
                # 创建检测样本组
                os.makedirs(group_path)
                # 更新数据
                config.DETECT_SAMPLE_GROUP = self.sample_group = text
                self.group_path = group_path
                update_metadata('detect_sample_group', text)
                # 更新按钮显示状态
                self.update_button_visibility()
                # 清空图片列表
                self.ui.detectList.clear()
                # 显示成功消息
                show_message_box("成功", f"已创建样本组：{text}", QMessageBox.Information, self.ui)
            else: # 如果样本组已存在，显示错误消息
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
            config.DETECT_SAMPLE_GROUP = self.sample_group = dialog.selected_group
            self.group_path = join_path(config.SAMPLE_PATH, self.sample_group)
            update_metadata('detect_sample_group', self.sample_group)
            # 对接 http_server: 如果样本组为空，则从服务器下载样本
            os.makedirs(self.group_path, exist_ok=True) # 确保本地文件夹存在
            if not os.listdir(self.group_path):
                try:
                    # 连接服务器
                    http_server = HttpServer()
                    group_id = http_server.get_group_id(config.DETECT_SAMPLE_GROUP)
                    samples = http_server.get_sample_list(group_id)
                    # 创建进度对话框
                    progress_dialog = ProgressDialog(self.ui, {
                        "title": "下载样本",
                        "text": f"正在下载 {len(samples)} 个样本文件..."
                    })
                    progress_dialog.show()
                    # 下载每个样本并更新进度
                    for index, sample in enumerate(samples):
                        http_server.save_downloaded_sample(sample, self.group_path)
                        print(f"http_server下载样本成功: {sample}")
                        # 更新进度
                        progress = int((index + 1) / len(samples) * 100)
                        progress_dialog.setValue(progress)
                except Exception as e:
                    print(f"从http_server加载图片失败: {str(e)}")
            # 加载样本组中的图片
            LoadImages(self.ui, self.group_path, 'detectList').load_with_progress()
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
                # 获取样本组根路径
                group_path = join_path(config.SAMPLE_PATH, sample_group)
                # 删除样本组文件夹及其内容, 如果不存在则不删除
                shutil.rmtree(group_path, ignore_errors=True)
                # 对接 http_server: 删除样本组
                try:
                    group_id = HttpServer().get_group_id(sample_group)
                    HttpServer().delete_group(group_id)
                    print(f"http_server删除样本组成功 ID={group_id}")
                except Exception as e:
                    print(f"http_server删除样本组失败: {str(e)}")
                # 如果删除的是当前样本组，清空当前样本组
                if self.sample_group == sample_group:
                    config.DETECT_SAMPLE_GROUP = self.sample_group = None
                    self.group_path = config.SAMPLE_PATH
                    update_metadata('detect_sample_group', None)
                    # 更新按钮显示状态
                    self.update_button_visibility()
                    # 清空图片列表
                    self.ui.imageList.clear()
                # 显示成功消息
                show_message_box("成功", f"已删除样本组：{sample_group}", QMessageBox.Information, self.ui)

    def upload_sample_group(self):
        """
        上传样本组到服务器
        """
        UploadSampleGroup_HTTP(self.ui, config.DETECT_SAMPLE_GROUP).run()



    def init_model_group(self):
        """
        初始化模型组
        """
        self.ui.importDetectModelButton.clicked.connect(self.import_model_group)
        # 获取模型组并初始化路径
        model_group = config.PROJECT_METADATA.get('model_group')
        os.makedirs(config.MODEL_PATH, exist_ok=True) # 确保路径存在
        if model_group and not os.path.exists(join_path(config.MODEL_PATH, model_group)):
            # 路径无效时清除模型组配置
            model_group = None
            update_metadata('model_group', None)
        # 同步配置和实例变量
        config.MODEL_GROUP = model_group
        # 更新模型组显示
        self.update_model_group()

    def import_model_group(self):
        """
        导入检测用的模型组，弹出选择对话框
        """
        # 创建并显示模型组选择对话框
        dialog = ModelGroupDialog(self.ui)
        dialog.setWindowTitle("导入检测模型组")
        dialog.ui.titleLabel.setText("请选择检测模型组：")
        result = dialog.exec()
        # 如果用户点击了确定按钮并选择了模型组
        if result == QDialog.Accepted and dialog.selected_group:
            # 对接 http_server: 检查模型是否已训练完成
            try:
                model_status = HttpServer().get_model_status(dialog.selected_group)
                if model_status != 2:
                    show_message_box("警告", "该模型尚未完成训练，请选择已训练完成的模型！", QMessageBox.Warning)
                    return
            except Exception as e:
                print(f"获取模型状态失败: {str(e)}")
                show_message_box("错误", f"获取模型状态失败: {str(e)}", QMessageBox.Critical)
            # 更新数据
            config.MODEL_GROUP = dialog.selected_group
            update_metadata('model_group', dialog.selected_group)
            self.update_model_group()
            show_message_box("成功", f"已导入检测模型组：{dialog.selected_group}", QMessageBox.Information, self.ui)
    
    def update_model_group(self):
        """更新当前模型组的显示"""
        self.ui.detectModelEdit.setText(config.MODEL_GROUP)
    


    def init_detect_list(self):
        """
        初始化图片列表
        """
        # 设置列表样式
        self.ui.detectList.setSpacing(10) # 设置项之间的间距
        # 绑定点击事件
        self.ui.detectList.itemClicked.connect(self.show_detect_image) # 设置列表项点击事件
        self.ui.foldListButton.clicked.connect(self.fold) # 设置折叠按钮的点击事件
        self.ui.addSamplesButton.clicked.connect(self.import_images) # 设置添加按钮的点击事件
        self.ui.importSamplesButton.clicked.connect(self.import_dir)  # 绑定导入按钮事件
        self.ui.deleteSamplesButton.clicked.connect(self.delete_images)  # 绑定删除按钮事件
        self.ui.selectAllSamplesButton.clicked.connect(self.select_all_images)  # 绑定全选按钮事件
        self.ui.selectSamplesButton.clicked.connect(self.select_enabled)
        self.ui.completeSamplesButton.clicked.connect(self.select_disabled)
        # 加载图片
        if self.sample_group:
            LoadImages(self.ui, self.group_path, 'detectList').load_with_progress() # 加载图片列表
            self.update_button_visibility() # 更新按钮显示状态

    def fold(self):
        """
        点击折叠按钮，折叠或展开左侧导航栏
        """
        # 获取当前左侧导航栏的宽度
        width = self.ui.detectList.width()
        if width > 0:
            self.ui.detectList.setFixedWidth(0)  # 隐藏导航栏，将宽度设为0
            self.ui.foldListButton.move(0, self.ui.foldListButton.y())  # 折叠按钮跟着向左移
        else:
            self.ui.detectList.setFixedWidth(250)  # 展开导航栏，设置宽度为250
            self.ui.foldListButton.move(230, self.ui.foldListButton.y())

    def select_enabled(self):
        """
        选中所有图片
        """
        # 检查是否有样本组
        if not check_detect_sample_group():
            return
        self.ui.detectList.clearSelection()  # Clear any selected items
        self.ui.detectList.setSelectionMode(QAbstractItemView.MultiSelection)  # Enable multi-selection mode
        for index in range(self.ui.detectList.count()):
            item = self.ui.detectList.item(index)
            checkbox = item.checkbox  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setVisible(True)
        # 更改按钮显示状态
        self.updateButtonState(False)

    def updateButtonState(self, state: bool):
        """
        修改按钮显示状态，True为默认状态
        """
        self.ui.selectSamplesButton.setVisible(state)
        self.ui.importSamplesButton.setVisible(state)
        self.ui.addSamplesButton.setVisible(state)
        self.ui.deleteSamplesButton.setVisible(not state)
        self.ui.selectAllSamplesButton.setVisible(not state)
        self.ui.completeSamplesButton.setVisible(not state)

    def select_disabled(self):
        """
        取消所有图片的选中状态, 并恢复按钮显示状态
        """
        self.ui.detectList.clearSelection()  # Clear any selected items
        self.ui.detectList.setSelectionMode(QAbstractItemView.SingleSelection)  # Enable single-selection mode
        for index in range(self.ui.detectList.count()):
            item = self.ui.detectList.item(index)
            checkbox = item.checkbox  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setChecked(False)
                checkbox.setVisible(False)
        # 恢复按钮显示状态
        self.updateButtonState(True)

    def select_all_images(self):
        """
        选中所有图片
        """
        for index in range(self.ui.detectList.count()):
            item = self.ui.detectList.item(index)
            item.setSelected(True)
            checkbox = item.checkbox  # Retrieve the checkbox from the item's data
            if checkbox:
                checkbox.setChecked(True)

    def delete_images(self):
        """
        删除选中的图片
        """
        selected_items = self.ui.detectList.selectedItems()
        for item in selected_items:
            print(f"删除图片: {item.image_path}")
            image_path = item.image_path
            if os.path.exists(image_path):
                os.remove(image_path)  # 删除文件
            # self.ui.detectList.takeItem(self.ui.detectList.row(item))  # 从列表中移除项
        LoadImages(self.ui, self.group_path, 'detectList').load_with_animation()  # 重新加载图片列表
        self.clear_detail_frame()  # 清除detailFrame
        # 删除完图片后，重置选择模式为禁用状态
        self.select_disabled()

    def import_dir(self):
        """
        从本地选择文件夹，导入其中的图片
        """
        # 检查是否有样本组
        if not check_detect_sample_group():
            return
        # 打开文件夹选择对话框
        folder = QFileDialog.getExistingDirectory(self.ui, "选择图片文件夹")
        if folder:
            # 遍历文件夹中的所有图片文件
            for file_name in os.listdir(folder):
                if is_image(file_name):
                    file_path = join_path(folder, file_name)
                    copy_image(file_path, self.group_path)
            LoadImages(self.ui, self.group_path, 'detectList').load_with_progress()  # 重新加载图片列表

    def import_images(self):
        """
        从本地文件夹中选择图片导入
        """
        # 检查是否有样本组
        if not check_detect_sample_group():
            return
        # 打开文件对话框选择图片
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles) # 设置文件对话框模式为选择多个文件
        file_dialog.setNameFilters(["Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)"]) # 设置文件过滤器
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            for file_path in selected_files:
                copy_image(file_path, self.group_path)
            LoadImages(self.ui, self.group_path, 'detectList').load_with_progress()  # 重新加载图片列表

    def show_detect_image(self, item):
        """显示选中的检测图片，支持原图和结果图的切换显示"""
        if not hasattr(item, 'image_path'):
            return
            
        # 获取原图和结果图的路径
        original_path = item.image_path
        base_name = os.path.splitext(os.path.basename(original_path))[0]
        result_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP, f"{base_name}_combined.png")
        
        # 检查是否存在结果图
        has_result = os.path.exists(result_path)
        
        # 保存当前图像信息
        self.current_original_path = original_path
        self.current_result_path = result_path
        self.has_result = has_result
        self.show_result = has_result  # 默认显示结果图（如果有）
        
        # 显示图片
        self.update_image_display()
        
        # 处理复选框状态
        checkbox = getattr(item, 'checkbox', None)
        if checkbox and checkbox.isVisible():
            checkbox.setChecked(not checkbox.isChecked())

    def update_image_display(self):
        """根据当前状态更新图片显示"""
        if self.show_result and self.has_result:
            # 显示结果图
            pixmap = QPixmap(self.current_result_path)
            tooltip = f"检测结果图: {os.path.basename(self.current_result_path)}"
        else:
            # 显示原图
            pixmap = QPixmap(self.current_original_path)
            tooltip = f"原图: {os.path.basename(self.current_original_path)}"
            
        # 缩放图片以适应显示区域
        scaled_pixmap = pixmap.scaled(
            self.ui.resultLabel.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.ui.resultLabel.setPixmap(scaled_pixmap)
        self.ui.resultLabel.setToolTip(tooltip)
        
        # 更新状态文本
        if self.has_result:
            self.ui.infoLabel.setText("点击图片切换显示原图和结果图")
        else:
            self.ui.infoLabel.setText("等待检测...")
        
        # 清空结果浏览器
        self.ui.resultBrowser.clear()
    
    def toggle_image(self):
        """切换原图和结果图的显示"""
        if self.has_result:  # 只有在有结果图的情况下才切换
            print("切换至结果图" if self.show_result else "切换至原图")
            self.show_result = not self.show_result
            self.update_image_display()

    def clear_detail_frame(self):
        """清除检测信息"""
        self.ui.resultBrowser.clear()
        self.ui.resultLabel.clear()
        self.ui.infoLabel.setText("等待检测...")
        # 重置图像状态
        self.current_original_path = None
        self.current_result_path = None
        self.has_result = False
        self.show_result = False
            


class ImageClickEventFilter(QObject):
    """图片点击事件过滤器"""
    def __init__(self, detect_handler):
        super().__init__()
        self.detect_handler = detect_handler
        
    def eventFilter(self, obj, event):
        if obj is self.detect_handler.ui.resultLabel and event.type() == QEvent.MouseButtonPress:
            self.detect_handler.toggle_image()
            return True
        return super().eventFilter(obj, event)