import json
import os
import shutil
import traceback
import matplotlib.pyplot as plt
import time
from datetime import datetime
import numpy as np
import platform
from PySide6.QtCore import Qt, QEvent, QObject, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QDialog, QMessageBox, QFileDialog, 
                             QAbstractItemView, QTreeWidgetItem, QApplication, QVBoxLayout)
from PySide6.QtUiTools import QUiLoader

import config
from sample_handler import SampleGroupDialog, NewSampleGroupDialog, LoadImages
from http_server import HttpServer, HttpDetectSamples, UploadSampleGroup_HTTP
from ssh_server import SSHServer, DefectSamples
from utils import LoadingAnimation, ProgressDialog, check_detect_sample_group, show_message_box, join_path, is_image, update_metadata, copy_image, create_file_dialog
from model_handler import ModelGroupDialog
from anomaly_gpt import AIChatDialog
from detect_report import generate_pdf_report


class DetectHandler(QObject):
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
        # 初始化检测组件
        self.init_detect_group()
        # 初始化 AI 判别功能
        self.init_ai_infer()
        

    def init_detect_group(self):
        """初始化检测组件"""
        # 启动检测按钮        
        self.ui.startDetectButton.clicked.connect(self.detect_samples_handler.detect_samples)
        # 导出检测报告按钮
        self.ui.exportButton.clicked.connect(self.show_texture_analysis)
        # 设置事件过滤器（外部过滤器 -> handler继承QObject并重写eventFilter）
        self.ui.resultLabel.setCursor(Qt.PointingHandCursor)
        # self.event_filter = ImageClickEventFilter(self)
        # self.ui.resultLabel.installEventFilter(self.event_filter)
        self.ui.resultLabel.installEventFilter(self)
        # 设置阈值
        config.DEFECT_THRESHOLD = config.PROJECT_METADATA.get('defect_threshold', 0.5)
        self.ui.thresholdSlider.setValue(int(config.DEFECT_THRESHOLD * 100))
        self.ui.thresholdValueLabel.setText(f"阈值: {config.DEFECT_THRESHOLD:.2f}")
        self.ui.thresholdSlider.valueChanged.connect(self.on_threshold_changed)
        self.ui.applyThresholdButton.clicked.connect(self.apply_threshold)
        # 初始化检测列表
        if config.DETECT_SAMPLE_GROUP:
            detect_list_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP, 'detect_list.json')
            if os.path.exists(detect_list_path):
                config.DETECT_LIST = json.load(open(detect_list_path))
    
    def init_ai_infer(self):
        """初始化 AI 判别功能"""
        # 连接按钮信号
        self.ui.AIInferButton.clicked.connect(self.on_ai_infer_clicked)
    
    def on_ai_infer_clicked(self):
        """处理 AI 判别按钮点击事件，支持多图像分析"""
        # 检查是否有检测结果
        if not config.DETECT_LIST:
            show_message_box("提示", "请先进行图像检测", QMessageBox.Information)
            return
        
        # 获取选中的图像列表
        selected_items = self.ui.detectList.selectedItems()
        
        # 如果没有选中的项目，使用当前显示的图像
        if not selected_items:
            if not hasattr(self, 'current_original_path') or not self.current_original_path:
                show_message_box("提示", "请先选择一张或多张已检测的图像", QMessageBox.Information)
                return
            
            # 将当前图像作为唯一选择
            origin_name = os.path.basename(self.current_original_path)
            image_info_list = [info for info in config.DETECT_LIST if info.get('origin_name') == origin_name]
            if not image_info_list:
                show_message_box("错误", "未找到当前图像的检测结果信息", QMessageBox.Critical)
                return
        else:
            # 从选中的图像项中提取图像信息
            image_info_list = []
            for item in selected_items:
                origin_name = os.path.basename(item.image_path)
                for info in config.DETECT_LIST:
                    if info.get('origin_name') == origin_name:
                        image_info_list.append(info)
                        break
            
            if not image_info_list:
                show_message_box("错误", "未找到选中图像的检测结果信息", QMessageBox.Critical)
                return
        
        # 创建并显示对话框
        dialog = AIChatDialog(
            parent=self.ui,
            image_info_list=image_info_list
        )
        dialog.exec()
        # 恢复按钮显示状态
        self.select_disabled()

    def on_threshold_changed(self, value):
        """阈值变化时更新显示"""
        threshold = value / 100.0
        self.ui.thresholdValueLabel.setText(f"阈值: {threshold:.2f}")
    
    def apply_threshold(self):
        """应用新的阈值设置"""
        new_threshold = self.ui.thresholdSlider.value() / 100.0
        config.DEFECT_THRESHOLD = new_threshold
        update_metadata('defect_threshold', new_threshold)
        
        # 如果当前有显示结果，使用新阈值刷新显示
        if hasattr(self, 'has_result') and self.has_result:
            self.update_image_display()
        
        # 提示用户
        show_message_box("阈值设置", f"已应用新阈值: {new_threshold:.2f}", QMessageBox.Information)

    def eventFilter(self, obj, event):
        """事件过滤器，处理图片点击事件"""
        if obj is self.ui.resultLabel and event.type() == QEvent.MouseButtonPress:
            self.toggle_image()
            return True
        return super(DetectHandler, self).eventFilter(obj, event)

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
        初始化检测列表
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
            print(f"删除原图: {item.image_path}")
            image_path = item.image_path
            if os.path.exists(image_path):
                os.remove(image_path)  # 删除文件
            # 如果有进行过检测，删除相关图片（可通过是否存在DETECT_LIST判断）
            if config.DETECT_LIST:
                # 获取原图文件名（不含扩展名）
                origin_name = os.path.basename(image_path)
                base_name = os.path.splitext(origin_name)[0] + '_'
                detect_group_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP)  
                # 查找并删除所有以该图片名开头的结果图片
                for result_file in os.listdir(detect_group_path):
                    if result_file.startswith(base_name):
                        result_file_path = join_path(detect_group_path, result_file)
                        print(f"删除检测图: {result_file_path}")
                        os.remove(result_file_path)
                config.DETECT_LIST = [info for info in config.DETECT_LIST if info.get('origin_name') != origin_name]
                # 更新detect_list.json文件
                with open(join_path(detect_group_path, 'detect_list.json'), 'w') as f:
                    json.dump(config.DETECT_LIST, f, ensure_ascii=False, indent=4)
        LoadImages(self.ui, self.group_path, 'detectList').load_with_animation()  # 重新加载图片列表
        self.clear_detail_frame()  # 清除detailFrame
        # 删除完图片后，重置选择模式为禁用状态
        self.select_disabled()

    def import_dir(self):
        """
        从本地选择文件夹，导入其中的图片
        """
        # 检查是否存在检测样本组
        if not check_detect_sample_group():
            return
        # 打开文件夹选择对话框
        folder = create_file_dialog(title="选择图片文件夹", is_folder=True)
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
        # 检查是否存在检测样本组
        if not check_detect_sample_group():
            return
            
        files = create_file_dialog(
            title="选择图片文件",
            is_folder=False,
            file_filter=f"图片文件 ({config.IMAGE_FORMATS})",
            file_mode=QFileDialog.ExistingFiles
        )
        
        if files:
            for file_path in files:
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
            pixmap_path = self.current_result_path
        else:
            pixmap_path = self.current_original_path
            
        # 缩放图片以适应显示区域
        scaled_pixmap = QPixmap(pixmap_path).scaled(
                self.ui.resultLabel.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        self.ui.resultLabel.setPixmap(scaled_pixmap)
        self.ui.resultLabel.setToolTip("点击图片切换显示原图和结果图" if self.has_result else "等待检测...")
            
        # 在结果浏览器中显示详细信息
        self.ui.resultBrowser.clear()
        if not self.has_result:
            return
        
        for img_info in config.DETECT_LIST:
            if img_info.get('origin_name') == os.path.basename(self.current_original_path):
                # 获取分数
                score = img_info.get('score')
                if isinstance(score, str):
                    try:
                        score = float(score)
                    except:
                        score = 0.0
                
                # 根据阈值判断状态
                is_defect = score > config.DEFECT_THRESHOLD
                status_text = "异常" if is_defect else "正常"
                status_color = "red" if is_defect else "green"
                
                # 更新UI显示
                self.ui.resultBrowser.append(f"<b>检测样本名:</b> {img_info.get('origin_name', '未知')}")
                self.ui.resultBrowser.append(f"<b>缺陷得分:</b> {score:.4f}")
                self.ui.resultBrowser.append(f"<b>当前阈值:</b> {config.DEFECT_THRESHOLD:.2f}")
                self.ui.resultBrowser.append(f"<b>检测状态:</b> <font color='{status_color}'>{status_text}</font>")
                self.ui.resultBrowser.append(f"<b>结果保存位置:</b> {self.current_result_path}")
                
                # 更新状态（可能在阈值变化后状态发生变化）
                img_info['status'] = status_text
                return
    
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
        # 重置图像状态
        self.current_original_path = None
        self.current_result_path = None
        self.has_result = False
        self.show_result = False
            
    def show_texture_analysis(self):
        """显示纹理分析对话框"""
        # 检查是否有检测样本组
        if not config.DETECT_SAMPLE_GROUP:
            show_message_box("提示", "请先选择或创建检测样本组", QMessageBox.Information)
            return
            
        # 检查是否已有检测结果
        detect_result_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP)
        if not os.path.exists(detect_result_path) or not os.listdir(detect_result_path):
            show_message_box("提示", "请先进行图像检测", QMessageBox.Information)
            return
            
        # 创建并显示纹理分析对话框
        dialog = TextureAnalysisDialog(config.DETECT_PATH, self.ui)
        dialog.exec()


class AnalysisWorker(QThread):
    """
    执行缺陷纹理分析的工作线程
    """
    progress_signal = Signal(int, str)
    finished_signal = Signal(dict)
    error_signal = Signal(str)
    
    def __init__(self, detect_path, detect_group, threshold, eps, min_samples, grid_size):
        super().__init__()
        self.detect_path = detect_path
        self.detect_group = detect_group
        self.threshold = threshold
        self.eps = eps
        self.min_samples = min_samples
        self.grid_size = grid_size
    
    def run(self):
        try:
            # 设置Matplotlib使用非交互式后端，避免线程问题
            import matplotlib
            matplotlib.use('Agg')  # 使用非交互式后端
            
            print(f"开始分析: 路径={self.detect_path}, 组={self.detect_group}, 网格划分={self.grid_size}×{self.grid_size}")
            
            # 创建分析器
            from detect_report import DefectTextureAnalyzer
            analyzer = DefectTextureAnalyzer(self.detect_path, self.detect_group)
            
            # 设置进度回调
            analyzer.set_progress_callback(self.update_progress)
            
            # 设置分析参数
            analyzer.threshold = self.threshold  # 设置阈值
            analyzer.eps = self.eps  # 设置聚类邻域半径
            analyzer.min_samples = self.min_samples  # 设置聚类最小样本数
            analyzer.grid_size = self.grid_size  # 设置网格大小
            
            # 生成报告（包含所有分析步骤）
            report_info = analyzer.generate_report()
                        
            if report_info:
                self.finished_signal.emit(report_info)
            else:
                # 如果report_info为None，表示"所有检测样本良好"
                self.finished_signal.emit("所有检测样本良好，无需生成缺陷检测报告!")
                
        except Exception as e:
            error_msg = f"分析过程出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.error_signal.emit(str(e))
    
    def update_progress(self, value, message):
        """
        更新进度信息
        """
        self.progress_signal.emit(value, message)


class TextureAnalysisDialog(QDialog):
    """
    缺陷纹理分析对话框
    """
    def __init__(self, detect_path, parent=None):
        super().__init__(parent)
        self.detect_path = detect_path
        
        # 加载UI
        self.ui = QUiLoader().load('ui/detect_report.ui')
        # 设置窗口属性
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.size())        
        # 创建新的布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        # 添加UI控件到布局
        main_layout.addWidget(self.ui)
        
        # 初始化界面
        self.init_ui()
        # 当前报告数据
        self.current_report = None        
        # 分析线程
        self.worker = None
    
    def init_ui(self):
        """
        初始化界面
        """
        # 连接信号槽
        self.ui.analyzeButton.clicked.connect(self.start_analysis)
        self.ui.exportButton.clicked.connect(self.export_report)
        self.ui.thresholdSlider.valueChanged.connect(self.update_threshold_label)
        self.ui.thresholdSlider.setValue(int(config.DEFECT_THRESHOLD * 100))
        self.ui.thresholdValueLabel.setText(f"阈值: {config.DEFECT_THRESHOLD:.2f}")
        
        # 连接eps滑块
        self.ui.epsSlider.valueChanged.connect(self.update_eps_label)
        self.update_eps_label(self.ui.epsSlider.value())
        
        # 连接网格划分滑块
        self.ui.gridSizeSlider.valueChanged.connect(self.update_grid_size_label)
        self.update_grid_size_label(self.ui.gridSizeSlider.value())
        
        # 加载样本组
        self.load_sample_groups()
        
        # 禁用导出按钮，直到分析完成
        self.ui.exportButton.setEnabled(False)
        
        # 设置详情树控件的列宽
        header = self.ui.detailTreeWidget.header()
        header.setSectionResizeMode(0, header.ResizeMode.Interactive)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.resizeSection(0, 250)  # 设置第一列宽度为250像素
    
    def load_sample_groups(self):
        """
        加载所有检测样本组
        """
        self.ui.sampleGroupComboBox.clear()
        
        try:
            # 检查检测路径是否存在
            if not os.path.exists(self.detect_path):
                return
            
            # 获取所有子目录
            sample_groups = [d for d in os.listdir(self.detect_path) 
                            if os.path.isdir(os.path.join(self.detect_path, d))]
            
            # 添加到下拉框
            self.ui.sampleGroupComboBox.addItems(sample_groups)
            
            # 如果当前有选定的检测样本组，自动选择它
            if config.DETECT_SAMPLE_GROUP and config.DETECT_SAMPLE_GROUP in sample_groups:
                index = self.ui.sampleGroupComboBox.findText(config.DETECT_SAMPLE_GROUP)
                if index >= 0:
                    self.ui.sampleGroupComboBox.setCurrentIndex(index)
                    print(f"自动选择当前检测样本组: {config.DETECT_SAMPLE_GROUP}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载样本组失败: {str(e)}")
    
    def update_grid_size_label(self, value):
        """更新网格划分标签"""
        total_cells = value * value
        self.ui.gridSizeValueLabel.setText(f"{value}×{value} ({total_cells}个区域)")
    
    def update_threshold_label(self, value):
        """
        更新阈值标签
        """
        threshold = value / 100.0
        self.ui.thresholdValueLabel.setText(f"阈值: {threshold:.2f}")
    
    def update_eps_label(self, value):
        """更新邻域半径标签"""
        eps_value = value / 100.0
        self.ui.epsValueLabel.setText(f"数值: {eps_value:.2f}")
    
    def start_analysis(self):
        """
        开始分析
        """
        # 获取参数
        detect_group = self.ui.sampleGroupComboBox.currentText()
        if not detect_group:
            QMessageBox.warning(self, "警告", "请选择检测样本组")
            return
        
        threshold = self.ui.thresholdSlider.value() / 100.0
        eps = self.ui.epsSlider.value() / 100.0
        min_samples = self.ui.minSamplesSpinBox.value()
        grid_size = self.ui.gridSizeSlider.value()  # 获取网格划分数量
        
        # 禁用分析按钮
        self.ui.analyzeButton.setEnabled(False)
        self.ui.exportButton.setEnabled(False)
        
        # 创建进度对话框
        self.progress_dialog = ProgressDialog(self, {
            "title": "缺陷纹理分析",
            "text": "正在准备分析..."
        })
        self.progress_dialog.show()
        
        # 创建并启动工作线程
        self.worker = AnalysisWorker(
            self.detect_path, 
            detect_group, 
            threshold, 
            eps, 
            min_samples,
            grid_size  # 传递网格划分数量参数
        )
        
        # 连接信号
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.analysis_finished)
        self.worker.error_signal.connect(self.analysis_error)
        
        # 启动线程
        self.worker.start()
    
    def update_progress(self, value, message):
        """
        更新进度信息
        """
        try:
            self.progress_dialog.setValue(value)
            self.progress_dialog.setLabelText(message)
        except Exception as e:
            print(f"更新进度信息出错: {str(e)}")
    
    def analysis_finished(self, result):
        """
        分析完成
        """        
        # 更新UI
        self.setWindowTitle("缺陷纹理分析 - 分析完成")
        self.ui.analyzeButton.setEnabled(True)
        if not result:
            # 使用信息框显示样本良好的消息
            QMessageBox.information(self, "分析结果", "所有检测样本良好，无需生成缺陷检测报告!")
            return
        self.current_report = result
        self.ui.exportButton.setEnabled(True)
        
        # 显示分析图表
        if 'chart_file' in result and os.path.exists(result['chart_file']):
            pixmap = QPixmap(result['chart_file'])
            self.ui.imageLabel.setPixmap(pixmap.scaled(
                self.ui.imageLabel.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
        
        # 显示统计信息
        self.show_statistics(result['report_data'])
        
        # 显示详细信息
        self.show_details(result['report_data'])

    
    def analysis_error(self, error_message):
        """
        分析出错
        """
        self.ui.analyzeButton.setEnabled(True)
        self.setWindowTitle("缺陷纹理分析")
        
        # 记录错误日志
        print(f"错误: {error_message}")
        
        # 检查常见的错误原因
        error_info = "分析过程中出错"
        suggestion = ""
        
        if "No module named" in error_message:
            suggestion = "可能缺少所需的Python库，请尝试运行: pip install -r requirements.txt"
        elif "FileNotFoundError" in error_message or "No such file or directory" in error_message:
            suggestion = "找不到文件或目录，请检查路径是否正确"
        elif "read_image" in error_message.lower() or "imread" in error_message.lower():
            suggestion = "图像读取失败，请检查图像文件格式是否正确"
        elif "memory" in error_message.lower():
            suggestion = "内存不足，请尝试减少分析的图像数量或关闭其他应用程序"
            
        # 显示带有建议的错误信息
        if suggestion:
            error_info = f"{error_info}:\n\n{error_message}\n\n建议: {suggestion}"
        else:
            error_info = f"{error_info}:\n\n{error_message}"
            
        QMessageBox.critical(self, "错误", error_info)
    
    def show_statistics(self, report_data):
        """
        显示统计信息
        """
        browser = self.ui.statisticsBrowser
        browser.clear()
        
        # 创建HTML内容
        html_content = []
        html_content.append("<html><body style='font-family: Arial, sans-serif; font-size: 10pt;'>")
        
        # 基本信息
        html_content.append("<h3>基本信息</h3>")
        html_content.append(f"<p>检测组: <b>{report_data['detect_group']}</b></p>")
        html_content.append(f"<p>总图像数: <b>{report_data['total_images']}</b></p>")
        html_content.append(f"<p>缺陷图像数: <b>{report_data['defect_images']}</b></p>")
        html_content.append(f"<p>缺陷位置总数: <b>{report_data['defect_positions']}</b></p>")
        
        # 添加缺陷位置统计信息
        html_content.append("<h3>缺陷位置统计</h3>")
        
        # 添加热图分布描述概括
        clusters = report_data['position_clusters']['clusters']
        noise_count = report_data['position_clusters']['noise']
        total_defects = report_data['defect_positions']
        
        # 生成总体分布描述
        if clusters:
            if len(clusters) == 1:
                distribution_pattern = "缺陷高度集中在一个区域"
            elif len(clusters) <= 3:
                distribution_pattern = f"缺陷主要集中在{len(clusters)}个区域"
            else:
                distribution_pattern = f"缺陷分布在{len(clusters)}个不同区域"
            
            # 计算聚类包含的缺陷比例
            clustered_defects = sum([c['count'] for c in clusters])
            clustered_ratio = clustered_defects / total_defects if total_defects > 0 else 0
            
            if clustered_ratio > 0.8:
                concentration = "非常集中"
            elif clustered_ratio > 0.6:
                concentration = "较为集中"
            elif clustered_ratio > 0.4:
                concentration = "分布均匀"
            else:
                concentration = "较为分散"
            
            # 生成描述文本
            html_content.append(f"<p><b>分布概况：</b>{distribution_pattern}，整体分布{concentration}。</p>")
            
            # 描述主要聚类
            if clusters:
                max_cluster = clusters[0]  # 已按大小排序
                center_x, center_y = max_cluster['center']
                html_content.append(f"<p><b>主要聚类：</b>最大的聚类区域位于坐标({center_x:.3f}, {center_y:.3f})附近，包含{max_cluster['count']}个缺陷点，占总缺陷的{(max_cluster['count']/total_defects*100):.1f}%。</p>")
            
            # 描述噪声点情况
            if noise_count > 0:
                noise_ratio = noise_count / total_defects if total_defects > 0 else 0
                if noise_ratio > 0.3:
                    noise_desc = "大量"
                elif noise_ratio > 0.1:
                    noise_desc = "部分"
                else:
                    noise_desc = "少量"
                html_content.append(f"<p><b>离散缺陷：</b>存在{noise_desc}离散缺陷点（{noise_count}个，占比{noise_ratio*100:.1f}%），这些点未形成明显聚类。</p>")
        
        # 显示缺陷位置热图
        if 'chart_file' in self.current_report and os.path.exists(self.current_report['chart_file']):
            html_content.append("<p>缺陷位置分布热图显示了所有检测到的缺陷位置，颜色越亮表示缺陷出现频率越高：</p>")
            html_content.append(f'<p><img src="{self.current_report["chart_file"]}" width="500"/></p>')
            html_content.append("<p><small><i>热图中绿色圆点表示缺陷聚类中心，数字表示该聚类包含的缺陷数量。</i></small></p>")
        
        # 聚类分析
        html_content.append("<h3>聚类分析</h3>")
        clusters = report_data['position_clusters']['clusters']
        html_content.append(f"<p>聚类数量: <b>{len(clusters)}</b></p>")
        if clusters:
            html_content.append(f"<p>最大聚类包含: <b>{clusters[0]['count']}</b>个缺陷</p>")
            html_content.append("<p>前3个聚类:</p>")
            
            # 创建有序列表
            if len(clusters) > 0:
                html_content.append("<ul style='margin-top: 5px; margin-bottom: 10px;'>")
                for i, cluster in enumerate(clusters[:3]):
                    html_content.append(f"<li>聚类 {i+1}: 中心位置({cluster['center'][0]:.2f}, {cluster['center'][1]:.2f}), " 
                                f"半径: {cluster['radius']:.3f}, 包含: {cluster['count']}个缺陷</li>")
                html_content.append("</ul>")
        
        html_content.append(f"<p>噪声点数量: <b>{report_data['position_clusters']['noise']}</b></p>")
        
        # 区域统计信息
        if 'patch_statistics' in report_data and report_data['patch_statistics']:
            # 获取统计数据
            patch_stats = report_data['patch_statistics']
            grid_size = patch_stats.get('patch_size', 8)
            
            # 在浏览器中显示统计信息
            html_content.append("<h3>区域特征统计分析</h3>")
            html_content.append(f"<p>区域划分: <b>{grid_size}×{grid_size}</b>（图像被均匀划分为{grid_size*grid_size}个区域）</p>")
            html_content.append(f"<p>统计区域总数: <b>{len(patch_stats.get('mean', []))}</b></p>")
            html_content.append(f"<p>各区域亮度均值的平均值: <b>{patch_stats.get('mean_avg', 0):.2f}</b>（图像整体亮度水平）</p>")
            html_content.append(f"<p>各区域纹理复杂度方差的平均值: <b>{patch_stats.get('variance_avg', 0):.2f}</b>（图像整体纹理复杂度）</p>")
            html_content.append(f"<p>各区域边缘密度的平均值: <b>{patch_stats.get('edges_avg', 0):.4f}</b>（图像整体边缘特征强度）</p>")
            
            # 添加异常区域与正常区域对比分析
            if 'anomaly_regions' in patch_stats and 'normal_regions' in patch_stats:
                anomaly_regions = patch_stats['anomaly_regions']
                normal_regions = patch_stats['normal_regions']
                
                # 总区域数据
                total_regions = anomaly_regions.get('count', 0) + normal_regions.get('count', 0)
                anomaly_percent = (anomaly_regions.get('count', 0) / total_regions * 100) if total_regions > 0 else 0
                
                html_content.append("<h4>3.1 原图纹理异常分析</h4>")
                html_content.append("<p style='color:#444; font-style:italic; margin-bottom:15px;'>(基于热图选择异常区域，在原图上进行纹理特征分析)</p>")
                
                # 创建表格比较异常区域和正常区域
                html_content.append("<table border='0' cellspacing='0' cellpadding='5' style='width:90%; margin:10px 0; border-collapse:collapse;'>")
                
                # 表头
                html_content.append("<tr style='background-color:#f0f0f0;'>")
                html_content.append("<th style='border-bottom:1px solid #ddd; text-align:left;'>特征</th>")
                html_content.append("<th style='border-bottom:1px solid #ddd; text-align:center;'>异常区域</th>")
                html_content.append("<th style='border-bottom:1px solid #ddd; text-align:center;'>正常区域</th>")
                html_content.append("<th style='border-bottom:1px solid #ddd; text-align:center;'>差异率</th>")
                html_content.append("</tr>")
                
                # 区域数量
                html_content.append("<tr>")
                html_content.append("<td style='border-bottom:1px solid #eee;'>区域数量</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{anomaly_regions.get('count', 0)} ({anomaly_percent:.1f}%)</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{normal_regions.get('count', 0)} ({100-anomaly_percent:.1f}%)</td>")
                html_content.append("<td style='border-bottom:1px solid #eee; text-align:center;'>-</td>")
                html_content.append("</tr>")
                
                # 亮度均值
                anomaly_mean = anomaly_regions.get('mean_avg', 0)
                normal_mean = normal_regions.get('mean_avg', 0)
                mean_diff = ((anomaly_mean - normal_mean) / normal_mean * 100) if normal_mean > 0 else 0
                mean_color = "red" if abs(mean_diff) > 15 else ("orange" if abs(mean_diff) > 5 else "green")
                
                html_content.append("<tr>")
                html_content.append("<td style='border-bottom:1px solid #eee;'>亮度均值</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{anomaly_mean:.2f}</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{normal_mean:.2f}</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center; color:{mean_color};'>{mean_diff:+.1f}%</td>")
                html_content.append("</tr>")
                
                # 纹理复杂度（方差）
                anomaly_var = anomaly_regions.get('variance_avg', 0)
                normal_var = normal_regions.get('variance_avg', 0)
                var_diff = ((anomaly_var - normal_var) / normal_var * 100) if normal_var > 0 else 0
                var_color = "red" if abs(var_diff) > 30 else ("orange" if abs(var_diff) > 10 else "green")
                
                html_content.append("<tr>")
                html_content.append("<td style='border-bottom:1px solid #eee;'>纹理复杂度</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{anomaly_var:.2f}</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{normal_var:.2f}</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center; color:{var_color};'>{var_diff:+.1f}%</td>")
                html_content.append("</tr>")
                
                # 边缘密度
                anomaly_edge = anomaly_regions.get('edges_avg', 0)
                normal_edge = normal_regions.get('edges_avg', 0)
                edge_diff = ((anomaly_edge - normal_edge) / normal_edge * 100) if normal_edge > 0 else 0
                edge_color = "red" if abs(edge_diff) > 40 else ("orange" if abs(edge_diff) > 15 else "green")
                
                html_content.append("<tr>")
                html_content.append("<td style='border-bottom:1px solid #eee;'>边缘密度</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{anomaly_edge:.4f}</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center;'>{normal_edge:.4f}</td>")
                html_content.append(f"<td style='border-bottom:1px solid #eee; text-align:center; color:{edge_color};'>{edge_diff:+.1f}%</td>")
                html_content.append("</tr>")
                
                html_content.append("</table>")
                
                # 添加异常区域特征解读
                html_content.append("<h4>3.2 异常区域特征解读:</h4>")
                
                # 亮度差异解读
                if abs(mean_diff) > 15:
                    brightness_desc = f"异常区域亮度{'明显高于' if mean_diff > 0 else '明显低于'}正常区域（差异{abs(mean_diff):.1f}%），表明{'存在高亮异常' if mean_diff > 0 else '可能有暗区缺陷'}。"
                elif abs(mean_diff) > 5:
                    brightness_desc = f"异常区域亮度{'略高于' if mean_diff > 0 else '略低于'}正常区域（差异{abs(mean_diff):.1f}%）。"
                else:
                    brightness_desc = "异常区域与正常区域亮度相近，缺陷可能不表现为亮度变化。"
                
                # 纹理复杂度解读
                if abs(var_diff) > 30:
                    texture_desc = f"异常区域纹理复杂度{'明显高于' if var_diff > 0 else '明显低于'}正常区域（差异{abs(var_diff):.1f}%），表明{'存在纹理断裂或杂乱' if var_diff > 0 else '可能有纹理缺失或平滑区域'}。"
                elif abs(var_diff) > 10:
                    texture_desc = f"异常区域纹理复杂度{'略高于' if var_diff > 0 else '略低于'}正常区域（差异{abs(var_diff):.1f}%）。"
                else:
                    texture_desc = "异常区域与正常区域纹理复杂度相近。"
                
                # 边缘密度解读
                if abs(edge_diff) > 40:
                    edge_desc = f"异常区域边缘密度{'明显高于' if edge_diff > 0 else '明显低于'}正常区域（差异{abs(edge_diff):.1f}%），表明{'存在明显边缘或轮廓特征' if edge_diff > 0 else '可能有边缘缺失或模糊'}。"
                elif abs(edge_diff) > 15:
                    edge_desc = f"异常区域边缘密度{'略高于' if edge_diff > 0 else '略低于'}正常区域（差异{abs(edge_diff):.1f}%）。"
                else:
                    edge_desc = "异常区域与正常区域边缘密度相近。"
                
                html_content.append(f"<p>{brightness_desc}</p>")
                html_content.append(f"<p>{texture_desc}</p>")
                html_content.append(f"<p>{edge_desc}</p>")
                
                # 综合解释
                html_content.append("<h4>3.3 综合分析:</h4>")
                if abs(mean_diff) > 15 or abs(var_diff) > 30 or abs(edge_diff) > 40:
                    analysis = "异常区域与正常区域存在显著差异，很可能存在实际缺陷。"
                elif abs(mean_diff) > 5 or abs(var_diff) > 10 or abs(edge_diff) > 15:
                    analysis = "异常区域与正常区域存在一定差异，可能存在轻微缺陷。"
                else:
                    analysis = "异常区域与正常区域差异不明显，可能是热图误检或缺陷特征不明显。"
                html_content.append(f"<p>{analysis}</p>")
            
            # 显示直方图图像（从报告中获取路径）
            if 'histogram_chart' in self.current_report and os.path.exists(self.current_report['histogram_chart']):
                html_content.append("<h4>3.4 图像区域特征分布:</h4>")
                html_content.append(f'<p><img src="{self.current_report["histogram_chart"]}" width="500"/></p>')
                
                # 解释直方图意义
                html_content.append("<p>直方图显示了正常区域和异常区域的特征分布对比：</p>")
                html_content.append("<p>1. 亮度分布直方图：用于区分亮度异常导致的缺陷，如过曝、过暗或局部高反差区域。其中绿色表示实际正常区域的亮度分布，红色表示实际异常区域的亮度分布</p>")
                html_content.append("<p>2. 纹理复杂度分布直方图：用于区分纹理异常导致的缺陷，如纹理断裂、杂乱或缺失。其中绿色表示实际正常区域的纹理复杂度分布，红色表示实际异常区域的纹理复杂度分布</p>")
                html_content.append("<p>3. 边缘密度分布直方图：用于识别边缘异常，如裂纹、划痕或轮廓缺失等几何特征缺陷。其中绿色表示实际正常区域的边缘特征分布，红色表示实际异常区域的边缘特征分布</p>")
                html_content.append("<p><i>注：颜色划分是基于热图检测结果确定的，而非人工设定的阈值</i></p>")
            else:
                html_content.append("<p>未生成区域特征分布图表</p>")
        
        # 缺陷类型分析
        html_content.append("<h3>缺陷类型分析</h3>")
        texture_counts = report_data['texture_analysis']['texture_counts']
        if texture_counts:
            # 显示饼图（从报告中获取路径）
            if 'pie_chart' in self.current_report and os.path.exists(self.current_report['pie_chart']):
                html_content.append('<div style="margin:15px 0;">')
                html_content.append(f'<img src="{self.current_report["pie_chart"]}" width="450" style="max-width:100%; border-radius:6px;"/>')
                html_content.append('</div>')
            
            main_texture = max(texture_counts.items(), key=lambda x: x[1])[0]
            html_content.append(f"<p>主要缺陷类型: <b>{main_texture}</b></p>")
            
            html_content.append("<p>缺陷类型分布:</p>")
            html_content.append("<table style='width:90%; border-collapse:collapse; margin:10px 0;'>")
            html_content.append("<tr style='background-color:#f0f0f0;'>")
            html_content.append("<th style='border:1px solid #ddd; padding:8px; text-align:center;'>主要类型</th>")
            html_content.append("<th style='border:1px solid #ddd; padding:8px; text-align:center;'>缺陷数量</th>")
            html_content.append("<th style='border:1px solid #ddd; padding:8px; text-align:center;'>样本数量</th>")
            html_content.append("<th style='border:1px solid #ddd; padding:8px; text-align:center;'>详细类型</th>")
            html_content.append("</tr>")
            
            # 获取样本主要缺陷类型统计
            sample_main_type_counts = report_data['texture_analysis'].get('sample_main_type_counts', {})
            
            for texture, count in texture_counts.items():
                # 获取详细类型描述（如果存在）
                type_desc = report_data['texture_analysis'].get('type_description', {}).get(texture, "")
                # 获取该类型的样本数量
                sample_count = sample_main_type_counts.get(texture, 0)
                
                html_content.append("<tr>")
                html_content.append(f"<td style='border:1px solid #ddd; padding:8px; text-align:center;'>{texture}</td>")
                html_content.append(f"<td style='border:1px solid #ddd; padding:8px; text-align:center;'>{count}个</td>")
                html_content.append(f"<td style='border:1px solid #ddd; padding:8px; text-align:center;'>{sample_count}个样本</td>")
                html_content.append(f"<td style='border:1px solid #ddd; padding:8px; text-align:left;'>{type_desc}</td>")
                html_content.append("</tr>")
            html_content.append("</table>")
        
        # 结束HTML文档
        html_content.append("</body></html>")
        
        # 设置HTML内容到浏览器
        browser.setHtml("".join(html_content))
    
    def show_details(self, report_data):
        """
        显示详细信息树
        """
        tree = self.ui.detailTreeWidget
        tree.clear()
        
        # 添加根节点
        root = QTreeWidgetItem(tree)
        root.setText(0, "缺陷分析报告")
        root.setText(1, report_data['detect_group'])
        
        # 添加基本信息
        basic_info = QTreeWidgetItem(root)
        basic_info.setText(0, "基本信息")
        
        # 格式化时间戳为正规日期格式
        timestamp_str = report_data['timestamp']
        try:
            # 尝试将时间戳转换为正规日期格式
            datetime_obj = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            formatted_date = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
        except:
            formatted_date = timestamp_str  # 如果转换失败，保持原格式
        
        items = [
            ("检测组", report_data['detect_group']),
            ("总图像数", str(report_data['total_images'])),
            ("缺陷图像数", str(report_data['defect_images'])),
            ("缺陷位置数", str(report_data['defect_positions'])),
            ("分析时间", formatted_date)
        ]
        
        for name, value in items:
            item = QTreeWidgetItem(basic_info)
            item.setText(0, name)
            item.setText(1, value)
        
        # 添加检测图像列表 (使用config.DETECT_LIST)
        if config.DETECT_LIST:
            images_item = QTreeWidgetItem(basic_info)
            images_item.setText(0, "检测图像列表")
            images_item.setText(1, f"{len(config.DETECT_LIST)}个图像")
            
            for img_info in config.DETECT_LIST:
                img_item = QTreeWidgetItem(images_item)
                img_item.setText(0, img_info.get('origin_name', '未知'))
                score = img_info.get('score', 'N/A')
                if isinstance(score, str):
                    try:
                        score = float(score)
                        score_text = f"{score:.4f}"
                    except:
                        score_text = score
                else:
                    score_text = f"{score:.4f}"
                img_item.setText(1, f"得分: {score_text}")
        
        # 添加聚类信息
        clusters_info = QTreeWidgetItem(root)
        clusters_info.setText(0, "聚类分析")
        clusters_info.setText(1, str(len(report_data['position_clusters']['clusters'])) + "个聚类")
        
        for i, cluster in enumerate(report_data['position_clusters']['clusters']):
            cluster_item = QTreeWidgetItem(clusters_info)
            cluster_item.setText(0, f"聚类 {i+1}")
            cluster_item.setText(1, f"{cluster['count']}个缺陷")
            
            # 基本属性 (使用中文)
            attr_map = {
                "center": "中心坐标",
                "radius": "半径",
                "count": "缺陷数量"
            }
            
            for attr, chinese_name in attr_map.items():
                attr_item = QTreeWidgetItem(cluster_item)
                attr_item.setText(0, chinese_name)
                attr_item.setText(1, str(cluster[attr]))
            
            # 添加位置范围信息
            if 'points' in cluster and cluster['points']:
                points = np.array(cluster['points'])
                min_x, min_y = np.min(points, axis=0)
                max_x, max_y = np.max(points, axis=0)
                
                range_item = QTreeWidgetItem(cluster_item)
                range_item.setText(0, "位置范围")
                range_item.setText(1, f"X: {min_x:.3f}-{max_x:.3f}, Y: {min_y:.3f}-{max_y:.3f}")
        
        # 添加缺陷类型信息
        texture_info = QTreeWidgetItem(root)
        texture_info.setText(0, "缺陷类型分析")
        
        # 添加样本缺陷类型统计
        sample_main_type_counts = report_data['texture_analysis'].get('sample_main_type_counts', {})
        if sample_main_type_counts:
            sample_types = QTreeWidgetItem(texture_info)
            sample_types.setText(0, "样本缺陷类型统计")
            sample_types.setText(1, f"{sum(sample_main_type_counts.values())}个样本")
            
            # 定义严重程度顺序
            severity_order = {
                "轻微污染": 1,
                "轻度异常": 2,
                "中度缺陷": 3,
                "严重损坏": 4
            }
            
            # 按照严重程度顺序排序（从轻到重）
            for main_type, count in sorted(sample_main_type_counts.items(), key=lambda x: severity_order.get(x[0], 0)):
                type_item = QTreeWidgetItem(sample_types)
                type_item.setText(0, main_type)
                type_item.setText(1, f"{count}个样本")
                
                # 获取该缺陷类型对应的样本列表
                samples_with_type = []
                for img, type_name in report_data['texture_analysis']['image_main_type'].items():
                    if type_name == main_type:
                        samples_with_type.append(img)
                
                # 直接在缺陷类型节点下显示样本列表
                for sample in sorted(samples_with_type):
                    sample_node = QTreeWidgetItem(type_item)
                    sample_node.setText(0, sample)
                    
                    # 统计该样本包含的具体缺陷类型及数量
                    if 'defect_details' in report_data['texture_analysis']:
                        # 创建缺陷类型计数字典
                        sample_defect_counts = {}
                        
                        # 遍历所有缺陷详情
                        for defect in report_data['texture_analysis']['defect_details']:
                            if defect.get('image') == sample:
                                detail_type = defect.get('defect_type', '')
                                if detail_type:
                                    if detail_type not in sample_defect_counts:
                                        sample_defect_counts[detail_type] = 0
                                    sample_defect_counts[detail_type] += 1
                        
                        # 生成缺陷类型统计文本
                        if sample_defect_counts:
                            defect_text = []
                            for defect_type, count in sample_defect_counts.items():
                                defect_text.append(f"{defect_type}: {count}个")
                            sample_node.setText(1, ", ".join(defect_text))
                        else:
                            sample_node.setText(1, "")
                    else:
                        sample_node.setText(1, "")
        
        # 添加缺陷区域类型统计
        texture_counts = QTreeWidgetItem(texture_info)
        texture_counts.setText(0, "缺陷区域类型统计")
        texture_counts.setText(1, f"{sum(report_data['texture_analysis']['texture_counts'].values())}个缺陷")
        
        # 为每种缺陷类型添加详细统计，按照严重程度从轻到重排序
        for texture, count in sorted(report_data['texture_analysis']['texture_counts'].items(), key=lambda x: severity_order.get(x[0], 0)):
            texture_item = QTreeWidgetItem(texture_counts)
            texture_item.setText(0, texture)
            texture_item.setText(1, f"{count}个缺陷")
            
            # 添加详细类型计数信息
            type_desc = report_data['texture_analysis'].get('type_description', {}).get(texture, "")
            if type_desc:
                # 解析type_desc获取详细类型和数量
                # 例如：（包括：5个划痕, 3个小缺口, 2个大面积缺陷）
                if "包括" in type_desc:
                    detail_types_text = type_desc.replace("（包括：", "").replace("）", "")
                    detail_types_list = detail_types_text.split(", ")
                    
                    # 为每个详细类型创建子节点
                    for detail_type_text in detail_types_list:
                        # 将"5个划痕"分解为数量和类型名
                        if "个" in detail_type_text:
                            parts = detail_type_text.split("个")
                            if len(parts) == 2:
                                count_str = parts[0]
                                type_name = parts[1]
                                
                                # 只有当数量大于0时才添加
                                if count_str.isdigit() and int(count_str) > 0:
                                    detail_item = QTreeWidgetItem(texture_item)
                                    detail_item.setText(0, type_name)
                                    detail_item.setText(1, f"{count_str}个")
                else:
                    # 如果不符合预期格式，则直接显示原始描述
                    desc_item = QTreeWidgetItem(texture_item)
                    desc_item.setText(0, "详细类型")
                    desc_item.setText(1, type_desc)
        
        # 展开根节点
        tree.expandItem(root)
    
    def export_report(self):
        """
        导出PDF报告
        """
        if not self.current_report:
            QMessageBox.warning(self, "警告", "没有可导出的报告")
            return
            
        try:
            # 让用户选择保存路径
            timestamp = self.current_report['report_data']['timestamp']
            default_filename = f"defect_analysis_report_{timestamp}.pdf"
            
            user_selected_path = create_file_dialog(
                title="保存PDF报告",
                is_folder=False,
                file_filter="PDF文件 (*.pdf)",
                accept_mode=QFileDialog.AcceptSave,
                default_filename=default_filename
            )
            
            if not user_selected_path:
                return  # 用户取消了保存对话框
                
            # 创建进度对话框
            progress_dialog = ProgressDialog(self, {
                "title": "生成PDF报告",
                "text": "正在生成PDF报告..."
            })
            progress_dialog.show()
            QApplication.processEvents()  # 确保对话框显示
            
            # 获取报告和图表文件路径
            report_file = self.current_report['report_file']
            chart_file = self.current_report.get('chart_file')
            histogram_chart = self.current_report.get('histogram_chart')
            pie_chart = self.current_report.get('pie_chart')
            
            # 生成PDF报告直接到用户选择的路径
            report_path = os.path.dirname(report_file)
            pdf_file = generate_pdf_report(
                self.current_report['report_data'], 
                report_path,
                chart_file,
                histogram_chart,
                pie_chart,
                output_filename=user_selected_path  # 传递用户选择的路径
            )
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 如果生成成功，显示成功信息
            if pdf_file and os.path.exists(pdf_file):
                # 保存PDF文件路径到current_report
                self.current_report['pdf_report'] = pdf_file
                
                # 弹出提示框询问用户是否要查看PDF
                reply = QMessageBox.question(
                    self, 
                    "导出成功", 
                    f"PDF报告已生成并保存到:\n{pdf_file}\n\n是否立即查看?",
                    QMessageBox.Yes | QMessageBox.No, 
                    QMessageBox.Yes
                )
                
                # 如果用户选择查看，则打开PDF文件
                if reply == QMessageBox.Yes:
                    try:
                        # 根据不同操作系统打开PDF文件
                        if platform.system() == 'Windows':
                            os.startfile(pdf_file)
                        elif platform.system() == 'Darwin':  # macOS
                            import subprocess
                            subprocess.run(['open', pdf_file])
                        else:  # Linux
                            import subprocess
                            subprocess.run(['xdg-open', pdf_file])
                    except Exception as e:
                        QMessageBox.warning(self, "警告", f"无法打开PDF文件: {str(e)}")
            else:
                QMessageBox.warning(self, "警告", "PDF报告生成失败")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"生成PDF报告失败: {str(e)}")
            print(f"生成PDF报告失败: {str(e)}")



# class ImageClickEventFilter(QObject):
#     """图片点击事件过滤器"""
#     def __init__(self, detect_handler):
#         super().__init__()
#         self.detect_handler = detect_handler
        
#     def eventFilter(self, obj, event):
#         if obj is self.detect_handler.ui.resultLabel and event.type() == QEvent.MouseButtonPress:
#             self.detect_handler.toggle_image()
#             return True
#         return super().eventFilter(obj, event)