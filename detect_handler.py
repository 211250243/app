import json
import os
import shutil
import traceback
import matplotlib.pyplot as plt
import time
from datetime import datetime
import numpy as np

from PySide6.QtCore import Qt, QEvent, QObject, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QDialog, QMessageBox, QFileDialog, 
                             QAbstractItemView, QTreeWidgetItem, QApplication, QVBoxLayout)
from PySide6.QtUiTools import QUiLoader

import config
from sample_handler import SampleGroupDialog, NewSampleGroupDialog, LoadImages
from http_server import HttpServer, HttpDetectSamples, UploadSampleGroup_HTTP
from ssh_server import SSHServer, DefectSamples
from utils import LoadingAnimation, ProgressDialog, check_detect_sample_group, show_message_box, join_path, is_image, update_metadata, copy_image
from model_handler import ModelGroupDialog
from anomaly_gpt import AIChatDialog
from detect_report import analyze_defect_textures, generate_pdf_report


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
        detect_list_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP, 'detect_list.json')
        if config.DETECT_SAMPLE_GROUP and os.path.exists(detect_list_path):
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
            # 调用分析函数，传递进度回调
            result = analyze_defect_textures(
                self.detect_path,
                self.detect_group,
                self.threshold,
                self.eps,
                self.min_samples,
                self.grid_size,
                self.update_progress
            )
            
            if result:
                self.finished_signal.emit(result)
            else:
                self.error_signal.emit("分析未返回有效结果")
                
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
        self.current_report = result
        
        # 更新UI
        self.setWindowTitle("缺陷纹理分析 - 分析完成")
        self.ui.analyzeButton.setEnabled(True)
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
        
        # 显示完成消息
        QMessageBox.information(self, "完成", "缺陷纹理分析已完成")
    
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
            html_content.append(f"<p>区域均值的平均值: <b>{patch_stats.get('mean_avg', 0):.2f}</b>（图像整体亮度水平）</p>")
            html_content.append(f"<p>区域方差的平均值: <b>{patch_stats.get('variance_avg', 0):.2f}</b>（图像整体纹理复杂度）</p>")
            html_content.append(f"<p>区域边缘密度平均值: <b>{patch_stats.get('edges_avg', 0):.4f}</b>（图像整体边缘特征强度）</p>")
            
            # 显示直方图图像（从报告中获取路径）
            if 'histogram_chart' in self.current_report and os.path.exists(self.current_report['histogram_chart']):
                html_content.append("<p>图像区域特征分布:</p>")
                html_content.append(f'<p><img src="{self.current_report["histogram_chart"]}" width="500"/></p>')
                
                # 解释直方图意义
                html_content.append("<p><small><i>均值分布表示图像不同区域的亮度分布情况，可识别出暗区和亮区的比例。</i></small></p>")
                html_content.append("<p><small><i>方差分布表示图像不同区域的纹理复杂度，高方差区域通常包含复杂纹理。</i></small></p>")
                html_content.append("<p><small><i>边缘密度分布（Sobel算子）表示图像不同区域的边缘特征占比，高值区域通常包含明显的缺陷边界。</i></small></p>")
            else:
                html_content.append("<p>未生成区域特征分布图表</p>")
        
        # 纹理分析
        html_content.append("<h3>纹理分析</h3>")
        texture_counts = report_data['texture_analysis']['texture_counts']
        if texture_counts:
            # 显示饼图（从报告中获取路径）
            if 'pie_chart' in self.current_report and os.path.exists(self.current_report['pie_chart']):
                html_content.append('<div style="margin:15px 0;">')
                html_content.append(f'<img src="{self.current_report["pie_chart"]}" width="450" style="max-width:100%; border-radius:6px;"/>')
                html_content.append('</div>')
            
            main_texture = max(texture_counts.items(), key=lambda x: x[1])[0]
            html_content.append(f"<p>主要纹理类型: <b>{main_texture}</b></p>")
            
            html_content.append("<p>纹理类型分布:</p>")
            html_content.append("<ul style='margin-top: 5px; margin-bottom: 10px;'>")
            for texture, count in texture_counts.items():
                html_content.append(f"<li>{texture}: {count}个</li>")
            html_content.append("</ul>")
        
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
        
        # 添加缺陷图像列表 (使用config.DETECT_LIST)
        if config.DETECT_LIST:
            images_item = QTreeWidgetItem(basic_info)
            images_item.setText(0, "缺陷图像列表")
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
        
        # 添加纹理信息
        texture_info = QTreeWidgetItem(root)
        texture_info.setText(0, "纹理分析")
        
        # 添加纹理统计
        texture_counts = QTreeWidgetItem(texture_info)
        texture_counts.setText(0, "纹理统计")
        
        # 为每种纹理类型计算每个图像中该纹理的数量
        texture_images_count = {}
        if 'texture_details' in report_data['texture_analysis']:
            for texture_detail in report_data['texture_analysis']['texture_details']:
                texture_type = texture_detail['texture_type']
                image_name = texture_detail['image']
                
                if texture_type not in texture_images_count:
                    texture_images_count[texture_type] = {}
                
                if image_name not in texture_images_count[texture_type]:
                    texture_images_count[texture_type][image_name] = 0
                
                texture_images_count[texture_type][image_name] += 1
        
        for texture, count in report_data['texture_analysis']['texture_counts'].items():
            texture_item = QTreeWidgetItem(texture_counts)
            texture_item.setText(0, texture)
            texture_item.setText(1, str(count))
            
            # 添加该纹理类型对应的图像列表 (左侧为文件名，右侧为纹理数量)
            if texture in texture_images_count:
                # 按照图像名称排序
                sorted_images = sorted(texture_images_count[texture].items(), key=lambda x: x[0])
                for img_name, texture_count in sorted_images:
                    img_item = QTreeWidgetItem(texture_item)
                    img_item.setText(0, img_name)
                    img_item.setText(1, f"{texture_count}个")
        
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
            save_dialog = QFileDialog()
            save_dialog.setAcceptMode(QFileDialog.AcceptSave)
            save_dialog.setNameFilter("PDF文件 (*.pdf)")
            save_dialog.setDefaultSuffix("pdf")
            
            # 设置默认文件名（使用报告的时间戳）
            timestamp = self.current_report['report_data']['timestamp']
            default_filename = f"defect_analysis_report_{timestamp}.pdf"
            save_dialog.selectFile(default_filename)
            
            if not save_dialog.exec():
                return  # 用户取消了保存对话框
                
            # 获取用户选择的文件路径
            user_selected_path = save_dialog.selectedFiles()[0]
            
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
                QMessageBox.information(self, "成功", f"PDF报告已生成并保存到:\n{pdf_file}")
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