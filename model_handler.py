import os
import shutil
import random

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QDialog, QMessageBox, QFileDialog, QVBoxLayout, QTreeWidgetItem, QListWidgetItem
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

import config
from http_server import HttpServer
from sample_handler import SampleGroupDialog
from ssh_server import PatchCoreParamMapper_SSH
from utils import check_sample_group, copy_image, show_message_box, update_metadata, join_path, is_image



class ModelHandler:
    """
    处理 ModelWidget中的所有操作
    """
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        # 将所有子控件添加为实例属性
        for child in self.ui.findChildren(QWidget):
            setattr(self.ui, child.objectName(), child)
        # 初始化样本组
        self.init_sample_group()
        # 初始化模型组
        self.init_model_group()
        # 初始化模型参数
        self.init_model_params()

    def init_sample_group(self):
        self.ui.importDirButton.clicked.connect(self.import_dir)
        self.ui.importFileButton.clicked.connect(self.import_files)
        self.ui.changeSampleGroupButton.clicked.connect(self.change_sample_group)
    
    def update_sample_group(self):
        """
        跳转到模型标签页时，更新样本组
        """
        self.ui.curSampleGroupEdit.setText(config.SAMPLE_GROUP)

    def import_dir(self):
        """
        导入文件夹，扩充样本组
        """
        # 检查是否存在样本组
        if not check_sample_group():
            return
        folder = QFileDialog.getExistingDirectory(self.ui, "选择图片文件夹")
        if folder:
            sample_group_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, config.SAMPLE_LABEL_TRAIN_GOOD)
            for file_name in os.listdir(folder):
                if is_image(file_name):
                    file_path = join_path(folder, file_name)
                    copy_image(file_path, sample_group_path)
    
    def import_files(self):
        """
        导入文件，扩充样本组（支持多选）
        """
        # 检查是否存在样本组
        if not check_sample_group():
            return
        files = QFileDialog.getOpenFileNames(self.ui, "选择图片文件", "", "图片文件 (*.png *.jpg *.jpeg)")
        if files:
            sample_group_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, config.SAMPLE_LABEL_TRAIN_GOOD)
            print(files)
            for file_path in files:
                copy_image(file_path, sample_group_path)
    
    def change_sample_group(self):
        """
        弹出选择框，切换样本组
        """
        # 创建并显示样本组选择对话框
        dialog = SampleGroupDialog(self.ui)
        result = dialog.exec()
        if result == QDialog.Accepted and dialog.selected_group:
            # 更新数据
            config.SAMPLE_GROUP = dialog.selected_group
            update_metadata('sample_group', dialog.selected_group)
            sample_group_path = join_path(config.SAMPLE_PATH, dialog.selected_group, config.SAMPLE_LABEL_TRAIN_GOOD)
            if not os.listdir(sample_group_path):
                show_message_box("警告", "该样本组为空，建议更换！", QMessageBox.Warning)
            else:
                show_message_box("成功", "已切换样本组！", QMessageBox.Information)
            # 更新样本组显示
            self.ui.curSampleGroupEdit.setText(dialog.selected_group)

    def init_model_group(self):
        self.ui.newModelButton.clicked.connect(self.new_model_group)
        self.ui.importModelButton.clicked.connect(self.import_model_group)
        self.ui.deleteModelButton.clicked.connect(self.delete_model_group)
        self.ui.trainButton.clicked.connect(self.train_model) # 训练模型
        self.ui.viewParamsButton.clicked.connect(self.view_parameters) # 查看参数
        # 获取模型组并初始化路径
        model_group = config.PROJECT_METADATA.get('model_group')
        group_path = config.MODEL_PATH  # 默认路径
        os.makedirs(group_path, exist_ok=True) # 确保路径存在
        if model_group:
            # 尝试构建模型组路径
            tmp_path = join_path(group_path, model_group)
            if os.path.exists(tmp_path):
                group_path = tmp_path
            else:
                # 路径无效时清除模型组配置
                model_group = None
                update_metadata('model_group', None)
        # 同步配置和实例变量
        config.MODEL_GROUP = model_group
        self.group_path = group_path

    def update_model_group(self):
        """
        更新模型组路径和模型组名称
        """
        if config.MODEL_GROUP:
            self.group_path = join_path(config.MODEL_PATH, config.MODEL_GROUP)
        else:
            self.group_path = config.MODEL_PATH
        self.ui.curModelEdit.setText(config.MODEL_GROUP)

    def init_model_params(self):
        """初始化模型选项下拉框"""
        # 初始化参数映射器
        self.param_mapper = PatchCoreParamMapper_SSH()
        # 初始化选项，如果下拉框存在
        options = self.param_mapper.get_all_options()
        # 设置模型精度选项
        self.ui.accuracyComboBox.clear()
        self.ui.accuracyComboBox.addItems(options["accuracy"])
        self.ui.accuracyComboBox.setCurrentIndex(1)  # 默认选中中等精度
        # 设置缺陷大小选项
        self.ui.defectSizeComboBox.clear()
        self.ui.defectSizeComboBox.addItems(options["defect_size"])
        self.ui.defectSizeComboBox.setCurrentIndex(1)  # 默认选中中等缺陷
        # 设置训练速度选项
        self.ui.speedComboBox.clear()
        self.ui.speedComboBox.addItems(options["training_speed"])
        self.ui.speedComboBox.setCurrentIndex(1)  # 默认选中均衡
        

    def new_model_group(self):
        """
        创建新项目
        """
        # 不能合并为 NewModelDialog().ui.exec()，否则实例无引用，会立即被销毁！！！
        dialog = NewModelGroupDialog()
        result = dialog.ui.exec()
        model_group = dialog.get_model_group()
        if result == QDialog.Accepted and model_group:
            # 检查项目名称是否合法
            if not model_group.isidentifier():  # 判断是否是合法的标识符
                show_message_box("错误", "模型名称不合法！", QMessageBox.Critical)
                return
            # 创建模型文件夹
            group_path = join_path(config.MODEL_PATH, model_group)
            if not os.path.exists(group_path):
                # # 对接 http_server: 创建模型组
                # try:
                #     id = HttpServer().add_model(model_group)
                #     print(f"http_server创建模型组成功 ID={id}")
                # except Exception as e:
                #     print(f"http_server创建模型组失败: {str(e)}")
                # 创建模型文件夹
                os.makedirs(group_path)
                # 更新数据
                config.MODEL_GROUP = model_group
                update_metadata('model_group', model_group)
                self.update_model_group()
                show_message_box("成功", "已创建模型组！", QMessageBox.Information, self.ui)
            else:
                show_message_box("错误", "模型已存在，请选择其他名称！", QMessageBox.Critical, self.ui)

    def import_model_group(self):
        """
        导入模型组，弹出自定义对话框让用户选择模型组
        """
        # 创建并显示模型组选择对话框
        dialog = ModelGroupDialog(self.ui)
        result = dialog.exec()
        # 如果用户点击了确定按钮并选择了模型组
        if result == QDialog.Accepted and dialog.selected_group:
            # 更新数据
            config.MODEL_GROUP = dialog.selected_group
            update_metadata('model_group', dialog.selected_group)            
            self.update_model_group()
            show_message_box("成功", "已导入模型组！", QMessageBox.Information)

    def delete_model_group(self):
        """
        删除模型组，弹出模型组选择对话框让用户选择要删除的模型组
        """
        # 创建并显示模型组选择对话框
        dialog = ModelGroupDialog(self.ui)
        dialog.setWindowTitle("删除模型组")
        # 修改对话框标题标签文本
        dialog.ui.titleLabel.setText("请选择要删除的模型组：")
        result = dialog.exec()
        # 如果用户点击了确定按钮并选择了模型组
        if result == QDialog.Accepted and dialog.selected_group:
            # 获取选中的模型组名称
            model_group = dialog.selected_group
            # 弹出确认对话框
            confirm = QMessageBox.question(
                self.ui,
                "确认删除",
                f"确定要删除模型 {model_group} 吗？\n此操作不可恢复！",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            # 如果用户确认删除
            if confirm == QMessageBox.Yes:
                # 删除模型组
                group_path = join_path(config.MODEL_PATH, model_group)
                shutil.rmtree(group_path, ignore_errors=True)
                # # 对接 http_server: 删除模型组
                # try:
                #     id = HttpServer().get_model_id(model_group)
                #     HttpServer().delete_model(id)
                #     print(f"http_server删除模型组成功 ID={id}")
                # except Exception as e:
                #     print(f"http_server删除模型组失败: {str(e)}")
                # 如果删除的是当前模型组，清空当前模型组
                if config.MODEL_GROUP == model_group:
                    config.MODEL_GROUP = None
                    update_metadata('model_group', None)
                    self.update_model_group()
                # 显示成功消息
                show_message_box("成功", "已删除模型组！", QMessageBox.Information)

    def train_model(self):
        """
        训练模型
        """
        # 检查是否有选择模型和样本组
        if not config.MODEL_PATH or not os.path.exists(config.MODEL_PATH):
            show_message_box("错误", "请先创建或导入模型！", QMessageBox.Critical)
            return
        if not config.SAMPLE_GROUP:
            show_message_box("错误", "请先创建或导入样本组！", QMessageBox.Critical)
            return

        # 从UI获取参数选择
        accuracy = self.ui.accuracyComboBox.currentText()
        defect_size = self.ui.defectSizeComboBox.currentText()
        training_speed = self.ui.speedComboBox.currentText()
        # 获取完整的训练参数
        params = self.param_mapper.get_params(accuracy, defect_size, training_speed)
        
        # 这里可以调用实际的训练函数
        # train_patchcore(config.MODEL_PATH, config.PROJECT_METADATA['sample_path'], params)
        
        # 显示训练开始的消息
        show_message_box("信息", "模型训练已开始，请耐心等待...", QMessageBox.Information)
        # 这里应该有实际的训练代码，可能需要多线程实现
        print(f"开始训练模型，参数：{params}")
        

    def view_parameters(self):
        """
        查看当前选择的参数对应的详细PatchCore参数
        """
        # 从UI获取参数选择
        accuracy = self.ui.accuracyComboBox.currentText()
        defect_size = self.ui.defectSizeComboBox.currentText()
        training_speed = self.ui.speedComboBox.currentText()
        # 获取完整的参数
        params = self.param_mapper.get_params(accuracy, defect_size, training_speed)
        # 格式化参数显示
        param_text = ""
        for key, value in params.items():
            param_text += f"{key}: {value}\n"
        # 显示参数对话框
        msg_box = QMessageBox()
        msg_box.setWindowTitle("PatchCore 详细参数")
        msg_box.setText(param_text)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.exec()



class NewModelGroupDialog(QDialog):
    """
    新建模型组对话框
    """
    def __init__(self):
        super().__init__()
        # 加载UI文件
        self.ui = QUiLoader().load(r'ui/new_model.ui')
        # 设置按钮点击事件
        self.ui.newButton.clicked.connect(self.ui.accept)
        self.ui.cancelButton.clicked.connect(self.ui.reject)

    def get_model_group(self):
        """
        获取模型组名称
        """
        return self.ui.nameEdit.text()
    


class ModelGroupDialog(QDialog):
    """
    模型组选择对话框 - 使用UI文件加载
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_group = None
        # 加载UI文件
        self.ui = QUiLoader().load(r'ui\show_group_list.ui')
        # 修改窗口标题
        self.ui.titleLabel.setText("请选择模型组：")
        # 设置主窗口属性
        self.setWindowTitle("选择模型组")
        self.setMinimumSize(self.ui.width(), self.ui.height())
        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.ui)
        # 连接信号
        self.ui.refreshButton.clicked.connect(self.load_model_groups)
        self.ui.okButton.clicked.connect(self.accept)
        self.ui.cancelButton.clicked.connect(self.reject)
        self.ui.listWidget.itemDoubleClicked.connect(self.accept)
        # 加载模型组
        self.load_model_groups()

    def load_model_groups(self):
        """
        加载模型组列表
        """
        # 清空列表
        self.ui.listWidget.clear()
        # 获取模型文件夹路径
        # 获取模型文件夹下的所有子文件夹
        model_groups = []
        for item in os.listdir(config.MODEL_PATH):
            item_path = join_path(config.MODEL_PATH, item)
            if os.path.isdir(item_path):
                # 检查模型文件夹中是否有文件
                has_files = bool(os.listdir(item_path))
                model_groups.append((item, has_files))
        # 对接 http_server: 如果模型组列表为空，则从服务器获取模型组列表
        if not model_groups:
            try:
                group_list = HttpServer().list_model()
                print(f"http_server获取模型组列表成功: {group_list}")
                if group_list:
                    for group in group_list:
                        group_name = group.get("name")
                        model_groups.append((group_name, True))
            except Exception as e:
                print(f"从http_server获取模型组失败: {str(e)}")
        # 如果没有模型组，显示提示
        if not model_groups:
            empty_item = QListWidgetItem("没有找到模型组")
            empty_item.setFlags(Qt.NoItemFlags)  # 禁用选择
            self.ui.listWidget.addItem(empty_item)
            return
        # 添加模型组到列表
        for group_name, has_files in model_groups:
            item = QListWidgetItem(group_name)
            # 根据文件夹中有无文件，设置图标
            icon_path = "ui/icon/non-empty_folder.svg" if has_files else "ui/icon/empty_folder.svg"
            item.setIcon(QIcon(icon_path))
            self.ui.listWidget.addItem(item)
            # 如果是当前模型组，选中它
            if group_name == config.MODEL_GROUP:
                item.setSelected(True)
                self.ui.listWidget.setCurrentItem(item)
                self.selected_group = group_name
        
    def get_selected_group(self):
        """
        获取选中的模型组
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
            show_message_box("提示", "请选择一个模型组", QMessageBox.Information, self)