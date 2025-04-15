import json
import os
import shutil
import random
import threading
import time
from datetime import datetime

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QDialog, QMessageBox, QFileDialog, QVBoxLayout, QTreeWidgetItem, QListWidgetItem, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QRadioButton
from PySide6.QtGui import QIcon, QPainter, QShortcut, QKeySequence
from PySide6.QtCore import Qt, QTimer
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis

import config
from http_server import HttpServer, PatchCoreParamMapper_Http, UploadSampleGroup_HTTP
from sample_handler import GroupListItem, SampleGroupDialog
from ssh_server import PatchCoreParamMapper_SSH
from utils import LoadingAnimation, check_model_group, check_sample_group, copy_image, get_model_status, show_message_box, update_metadata, join_path, is_image, create_file_dialog



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
        # 初始化训练参数
        self.init_train_params()

    def init_sample_group(self):
        self.ui.importDirButton.clicked.connect(self.import_dir)
        self.ui.importFileButton.clicked.connect(self.import_files)
        self.ui.changeSampleGroupButton.clicked.connect(self.change_sample_group)
        self.update_sample_group()
    
    def update_sample_group(self):
        """
        跳转到模型标签页时，更新样本组
        """
        self.ui.curSampleGroupEdit.setText(config.SAMPLE_GROUP)

    def upload_sample_group(self):
        """
        上传样本组到服务器
        """
        UploadSampleGroup_HTTP(self.ui, config.SAMPLE_GROUP).run()

    def import_dir(self):
        """
        导入文件夹，扩充样本组
        """
        # 检查是否存在样本组
        if not check_sample_group():
            return
        folder = create_file_dialog(title="选择图片文件夹", is_folder=True)
        if folder:
            sample_group_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP)
            for file_name in os.listdir(folder):
                if is_image(file_name):
                    file_path = join_path(folder, file_name)
                    copy_image(file_path, sample_group_path)
                    # 对接 http_server: 上传样本到服务器
                    try:
                        group_id = HttpServer().get_group_id(config.SAMPLE_GROUP)
                        HttpServer().upload_sample(file_path, group_id)
                    except Exception as e:
                        print(f"上传样本失败: {str(e)}")
            show_message_box("成功", "已导入文件夹至样本组！", QMessageBox.Information, self.ui)
    
    def import_files(self):
        """
        导入文件，扩充样本组（支持多选）
        """
        # 检查是否存在样本组
        if not check_sample_group():
            return
            
        files = create_file_dialog(
            title="选择图片文件",
            is_folder=False,
            file_filter="图片文件 (*.png *.jpg *.jpeg)",
            file_mode=QFileDialog.ExistingFiles
        )
        
        if files:
            sample_group_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP)
            for file_path in files:
                copy_image(file_path, sample_group_path)
                # 对接 http_server: 上传样本到服务器
                try:
                    group_id = HttpServer().get_group_id(config.SAMPLE_GROUP)
                    HttpServer().upload_sample(file_path, group_id)
                except Exception as e:
                    print(f"上传样本失败: {str(e)}")
            show_message_box("成功", "已导入图片至样本组！", QMessageBox.Information, self.ui)
    
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
            sample_group_path = join_path(config.SAMPLE_PATH, dialog.selected_group)
            if not os.listdir(sample_group_path):
                show_message_box("警告", "该样本组为空，建议更换！", QMessageBox.Warning)
            else:
                show_message_box("成功", "已切换样本组！", QMessageBox.Information)
            # 更新样本组显示
            self.update_sample_group()

    def init_model_group(self):
        self.ui.newModelButton.clicked.connect(self.new_model_group)
        self.ui.importModelButton.clicked.connect(self.import_model_group)
        self.ui.deleteModelButton.clicked.connect(self.delete_model_group)
        # 获取模型组并初始化路径
        model_group = config.PROJECT_METADATA.get('model_group')
        os.makedirs(config.MODEL_PATH, exist_ok=True) # 确保路径存在
        if model_group:
            model_info_path = join_path(config.MODEL_PATH, model_group, config.MODEL_INFO_FILE)
            if not os.path.exists(model_info_path):
                # 路径无效时清除模型组配置
                model_group = None
                update_metadata('model_group', None)
            else:
                # 读取模型信息
                with open(model_info_path, 'r', encoding='utf-8') as f:
                    model_info = json.load(f)
                # 更新模型组配置
                config.MODEL_PARAMS = model_info
        # 同步配置和实例变量
        config.MODEL_GROUP = model_group
        self.update_model_view() # 更新模型显示

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
                # 根据训练参数创建模型
                model = {"name": model_group, **config.MODEL_PARAMS}
                # 对接 http_server: 创建模型组
                try:
                    id = HttpServer().add_model(model)
                    model = {"id": id, **model}
                    print(f"http_server创建模型组成功 ID={id} \n模型参数={config.MODEL_PARAMS}")
                except Exception as e:
                    print(f"http_server创建模型组失败: {str(e)}")
                # 创建模型文件夹
                os.makedirs(group_path)
                # 更新数据
                config.MODEL_GROUP = model_group
                update_metadata('model_group', model_group)
                self.update_model_info(model) # 更新模型信息
                self.update_model_view() # 更新模型显示
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
            update_metadata('model_group', config.MODEL_GROUP)   
            # 对接 http_server: 获取模型参数
            try:
                model = HttpServer().get_model(dialog.selected_group)
                config.MODEL_PARAMS = {k: v for k, v in model.items() if k != "name" and k != "id"} # 除去 name 和 id 剩下的部分
                self.update_model_info(model) # 更新模型信息
                print(f"http_server获取模型参数成功: {config.MODEL_PARAMS}")
            except Exception as e:
                print(f"http_server获取模型参数失败: {str(e)}")
            # 更新模型显示
            self.update_model_view() 
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
                # 对接 http_server: 删除模型组
                try:
                    id = HttpServer().get_model_id(model_group)
                    HttpServer().delete_model(id)
                    print(f"http_server删除模型组成功 ID={id}")
                except Exception as e:
                    print(f"http_server删除模型组失败: {str(e)}")
                # 如果删除的是当前模型组，清空当前模型组
                if config.MODEL_GROUP == model_group:
                    config.MODEL_GROUP = None
                    update_metadata('model_group', None)
                    config.MODEL_PARAMS = self.get_params() # 设置默认参数
                    self.update_model_view() # 更新模型显示
                # 显示成功消息
                show_message_box("成功", "已删除模型组！", QMessageBox.Information)



    def init_train_params(self):
        """初始化模型训练板块"""
        self.ui.trainButton.clicked.connect(self.train_model)
        self.ui.viewParamsButton.clicked.connect(self.view_params)
        self.ui.editParamsButton.clicked.connect(self.edit_params)
        self.ui.setParamsButton.clicked.connect(self.set_params)

        # 初始化参数映射器
        self.param_mapper = PatchCoreParamMapper_Http()
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
        # 初始化参数默认值
        config.MODEL_PARAMS = self.get_params()
        
    def update_model_view(self):
        """
        更新模型组及其参数显示
        """
        self.ui.curModelEdit.setText(config.MODEL_GROUP)
        if config.MODEL_GROUP:
            self.ui.heightEdit.setText(str(config.MODEL_PARAMS["input_h"]))
            self.ui.widthEdit.setText(str(config.MODEL_PARAMS["input_w"]))
            self.ui.endAccuracyEdit.setText(str(config.MODEL_PARAMS["end_acc"]))
        else:
            self.ui.heightEdit.setText("")
            self.ui.widthEdit.setText("")
            self.ui.endAccuracyEdit.setText("")

    def update_model_info(self, model_info):
        """
        创建或更新模型信息
        """
        model_file = join_path(config.MODEL_PATH, config.MODEL_GROUP, config.MODEL_INFO_FILE)
        model = {}
        # 如果模型文件存在，读取模型信息
        if os.path.exists(model_file):
            with open(model_file, "r", encoding="utf-8") as f:
                model = json.load(f)
        # 更新模型信息
        model.update(model_info)
        # 保存更新后的模型信息
        with open(model_file, "w", encoding="utf-8") as f:
            json.dump(model, f, ensure_ascii=False, indent=4)

    def upload_model_info(self):
        """
        # 对接 http_server: 更新模型参数
        """
        try:
            http_server = HttpServer()
            model_id = http_server.get_model_id(config.MODEL_GROUP)
            params = config.MODEL_PARAMS
            print(f"更新模型参数: {model_id} -> {params}")
            http_server.update_model(model_id, {
                "name": config.MODEL_GROUP,
                **params
            })
            show_message_box("成功", "模型参数已更新！", QMessageBox.Information, self.ui)
        except Exception as e:
            show_message_box("错误", f"更新参数失败: {str(e)}", QMessageBox.Critical, self.ui)
        
    def get_params(self):
        """
        从UI获取参数选择，获取训练参数
        """
        accuracy = self.ui.accuracyComboBox.currentText()
        defect_size = self.ui.defectSizeComboBox.currentText()
        training_speed = self.ui.speedComboBox.currentText()
        return self.param_mapper.get_params(accuracy, defect_size, training_speed)
    
    def set_params(self):
        """
        通过参数选择自动设置参数，并更新参数显示
        """
        # 检查是否存在模型组
        if check_model_group():
            config.MODEL_PARAMS = self.get_params()
            self.upload_model_info() # 服务器更新模型参数
            self.update_model_info(config.MODEL_PARAMS) # 更新模型信息
            self.update_model_view() # 更新模型显示

    def view_params(self):
        """
        查看当前选择的参数对应的详细PatchCore参数（只读模式）
        """
        # 检查是否存在模型组
        if check_model_group():
            # 创建并显示参数查看对话框（只读模式）
            dialog = ModelParamsDialog(self.ui, config.MODEL_PARAMS, editable=False)
            dialog.exec()

    def edit_params(self):
        """
        编辑模型参数，弹出编辑对话框让用户修改参数
        """
        # 检查是否存在模型组
        if not check_model_group():
            return
        # 创建并显示参数编辑对话框
        dialog = ModelParamsDialog(self.ui, config.MODEL_PARAMS, editable=True)
        result = dialog.exec()
        # 如果用户点击了确定按钮，更新参数
        if result == QDialog.Accepted:
            # 如果当前没有模型组，创建新模型组
            if not check_model_group():
                return
            self.upload_model_info() # 服务器更新模型参数
            self.update_model_info(config.MODEL_PARAMS) # 更新模型信息
            self.update_model_view() # 更新模型显示

    def train_model(self):
        """
        训练模型
        """
        # 检查是否有选择模型和样本组
        if not check_model_group() or not check_sample_group():
            return
        # 对接 http_server: 训练模型
        try:
            http_server = HttpServer()
            # 如果模型组不存在，删除本地模型组，并提示创建新模型组
            model_id = http_server.get_model_id(config.MODEL_GROUP)
            if not model_id:
                # 删除本地模型组
                shutil.rmtree(join_path(config.MODEL_PATH, config.MODEL_GROUP), ignore_errors=True)
                # 更新数据
                config.MODEL_GROUP = None
                update_metadata('model_group', None)
                self.update_model_view() # 更新模型显示
                # 提示创建新模型组
                show_message_box("错误", "模型组不存在于服务器，已删除本地模型组，请重新创建！", QMessageBox.Critical, self.ui)
                return
            # 如果样本组不存在，删除本地样本组，并提示创建新样本组
            group_id = http_server.get_group_id(config.SAMPLE_GROUP)
            if not group_id:
                # 删除本地样本组
                shutil.rmtree(join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP), ignore_errors=True)
                # 更新数据
                config.SAMPLE_GROUP = None
                update_metadata('sample_group', None)
                self.update_sample_group()
                # 提示创建新样本组
                show_message_box("错误", "样本组不存在于服务器，已删除本地样本组，请重新创建！", QMessageBox.Critical, self.ui)
                return
            # 启动训练
            http_server.train_model(model_id, group_id)
            
            # 弹出训练进度对话框
            progress_dialog = TrainingProgressDialog(self.ui, model_id, config.MODEL_GROUP)
            progress_dialog.show()            
        except Exception as e:
            show_message_box("错误", f"训练模型失败: {str(e)}", QMessageBox.Critical, self.ui)

    def is_model_trained(self):
        """
        检查当前选择的模型组是否已经训练过
        
        Returns:
            bool: 模型是否已训练
        """
        # 首先检查是否选择了模型组和样本组
        if not config.MODEL_GROUP or not config.SAMPLE_GROUP:
            return False
        # 对接 http_server: 检查模型训练状态
        try:
            http_server = HttpServer()
            model_id = http_server.get_model_id(config.MODEL_GROUP)
            if not model_id:
                return False
            # 获取模型状态
            model_status = http_server.get_model_status(config.MODEL_GROUP)
            # 检查模型状态，status=2表示训练已完成
            return model_status == 2
        except Exception as e:
            print(f"检查模型训练状态失败: {str(e)}")
            return False

class ModelParamsDialog(QDialog):
    """
    模型参数编辑/查看对话框
    """
    def __init__(self, parent=None, params=None, editable=True):
        super().__init__(parent)
        self.params = params or {}
        self.editable = editable
        self.param_mapper = PatchCoreParamMapper_Http()
        
        # 加载UI文件
        self.ui = QUiLoader().load(r'ui/model_params.ui')
        
        # 设置窗口标题
        if editable:
            self.ui.setWindowTitle("编辑模型参数")
        else:
            self.ui.setWindowTitle("查看模型参数")
            self.ui.titleLabel.setText("PatchCore 模型参数查看")
            
        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.ui)
        
        # 连接信号
        self.ui.saveButton.clicked.connect(self.validate_and_accept)
        self.ui.cancelButton.clicked.connect(self.reject)
        self.ui.resetButton.clicked.connect(self.reset_params)
        
        # 如果是只读模式，禁用编辑和保存
        if not editable:
            self.ui.saveButton.setVisible(False)
            self.ui.resetButton.setVisible(False)
            # 禁用所有输入控件
            self._set_controls_enabled(False)
            # 调整按钮位置，只保留取消按钮（作为关闭按钮）
            self.ui.cancelButton.setText("关闭")
            self.ui.cancelButton.setGeometry(225, 510, 100, 30)
        
        # 初始化界面
        self.init_ui()
        
    def init_ui(self):
        """初始化界面值"""
        if self.params:
            # 设置基本参数
            if "input_h" in self.params:
                self.ui.inputHSpin.setValue(self.params["input_h"])
            if "input_w" in self.params:
                self.ui.inputWSpin.setValue(self.params["input_w"])
            if "patchsize" in self.params:
                self.ui.patchSizeSpin.setValue(self.params["patchsize"])
            if "end_acc" in self.params:
                self.ui.endAccSpin.setValue(self.params["end_acc"])
            if "embed_dimension" in self.params:
                self.ui.embedDimSpin.setValue(self.params["embed_dimension"])
                
            # 设置特征层选择
            if "layers" in self.params:
                layers = self.params["layers"]
                # 如果layers是字符串形式，转换为列表
                if isinstance(layers, str):
                    try:
                        # 移除字符串格式的引号和方括号
                        layers = layers.replace("'", "").replace("[", "").replace("]", "")
                        layers = [l.strip() for l in layers.split(",")]
                    except:
                        layers = []
                        
                # 设置复选框状态
                self.ui.layer1Check.setChecked("layer1" in layers)
                self.ui.layer2Check.setChecked("layer2" in layers)
                self.ui.layer3Check.setChecked("layer3" in layers)
                self.ui.layer4Check.setChecked("layer4" in layers)
    
    def validate_and_accept(self):
        """验证参数是否有效，有效则接受对话框"""
        # 验证是否选择了特征层
        layers_selected = (
            self.ui.layer1Check.isChecked() or
            self.ui.layer2Check.isChecked() or
            self.ui.layer3Check.isChecked() or
            self.ui.layer4Check.isChecked()
        )
        
        if not layers_selected:
            show_message_box("错误", "请至少选择一个特征层！", QMessageBox.Critical, self)
            return
        
        # 验证输入尺寸
        input_h = self.ui.inputHSpin.value()
        input_w = self.ui.inputWSpin.value()
        if input_h < 128 or input_w < 128:
            show_message_box("错误", "输入尺寸不能小于128！", QMessageBox.Critical, self)
            return
        
        # 验证嵌入维度
        embed_dim = self.ui.embedDimSpin.value()
        if embed_dim < 128:
            show_message_box("错误", "嵌入维度不能小于128！", QMessageBox.Critical, self)
            return
        
        # 获取参数并判断是否有变化
        new_params = self.get_params()
        has_changes = False
        
        # 如果参数不存在，视为有变化
        if not self.params:
            has_changes = True
        else:
            # 逐个比较关键参数
            for key in ["input_h", "input_w", "patchsize", "end_acc", "embed_dimension", "layers"]:
                if key not in self.params or str(self.params[key]) != str(new_params[key]):
                    has_changes = True
                    break
        if not has_changes:
            show_message_box("提示", "参数未发生变化！", QMessageBox.Information, self)
            return
            
        # 更新参数并接受对话框
        self.params = new_params
        config.MODEL_PARAMS = new_params  # 更新全局参数
        print(f"参数已更新: {self.params}")
        super().accept()
        
    def _set_controls_enabled(self, enabled):
        """设置所有控件的启用状态"""
        # 基本参数
        self.ui.inputHSpin.setEnabled(enabled)
        self.ui.inputWSpin.setEnabled(enabled)
        self.ui.patchSizeSpin.setEnabled(enabled)
        self.ui.endAccSpin.setEnabled(enabled)
        
        # 特征提取参数
        self.ui.embedDimSpin.setEnabled(enabled)
        self.ui.layer1Check.setEnabled(enabled)
        self.ui.layer2Check.setEnabled(enabled)
        self.ui.layer3Check.setEnabled(enabled)
        self.ui.layer4Check.setEnabled(enabled)
        
    def get_params(self):
        """获取界面上的参数值"""
        # 获取所有特征层
        layers = []
        if self.ui.layer1Check.isChecked():
            layers.append("layer1")
        if self.ui.layer2Check.isChecked():
            layers.append("layer2")
        if self.ui.layer3Check.isChecked():
            layers.append("layer3")
        if self.ui.layer4Check.isChecked():
            layers.append("layer4")
            
        # 至少选择一个特征层
        if not layers:
            layers = ["layer2"]
            
        # 构造参数字典
        params = {
            "input_h": self.ui.inputHSpin.value(),
            "input_w": self.ui.inputWSpin.value(),
            "patchsize": self.ui.patchSizeSpin.value(),
            "end_acc": self.ui.endAccSpin.value(),
            "embed_dimension": self.ui.embedDimSpin.value(),
            "layers": str(layers).replace('"', "'")
        }
        
        return params
    
    def reset_params(self):
        """重置参数为默认值"""
        # 设置基本参数默认值
        self.ui.inputHSpin.setValue(256)
        self.ui.inputWSpin.setValue(256)
        self.ui.patchSizeSpin.setValue(5)
        self.ui.endAccSpin.setValue(0.92)
        self.ui.embedDimSpin.setValue(512)
        
        # 设置特征层默认值
        self.ui.layer1Check.setChecked(False)
        self.ui.layer2Check.setChecked(True)
        self.ui.layer3Check.setChecked(True)
        self.ui.layer4Check.setChecked(False)


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

        # 添加回车键确认功能
        self.shortcut_return = QShortcut(QKeySequence(Qt.Key_Return), self)
        self.shortcut_return.activated.connect(self.accept)
        self.shortcut_enter = QShortcut(QKeySequence(Qt.Key_Enter), self)
        self.shortcut_enter.activated.connect(self.accept)

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
                # 从本地获取模型组状态
                status = get_model_status(item)
                model_groups.append((item, has_files, status))
        # 对接 http_server: 如果模型组列表为空，则从服务器获取模型组列表
        if not model_groups:
            try:
                group_list = HttpServer().list_model()
                print(f"http_server获取模型组列表成功: {group_list}")
                if group_list:
                    for group in group_list:
                        group_name = group.get("name")
                        model_groups.append((group_name, True, group.get("status")))
            except Exception as e:
                print(f"从http_server获取模型组失败: {str(e)}")
        # 如果没有模型组，显示提示
        if not model_groups:
            empty_item = QListWidgetItem("没有找到模型组")
            empty_item.setFlags(Qt.NoItemFlags)  # 禁用选择
            self.ui.listWidget.addItem(empty_item)
            return
        # 添加模型组到列表
        for group_name, has_files, status in model_groups:
            # 根据文件夹中有无文件，设置图标
            icon = "ui/icon/non-empty_folder.svg" if has_files else "ui/icon/empty_folder.svg"
            
            # 根据状态设置不同颜色和文本
            if status == 0:
                text = "未训练"
                color = "#666"  # 灰色
            elif status == 1:
                text = "训练中"
                color = "#FF9800"  # 黄色
            elif status == 2:
                text = "已训练"
                color = "#4CAF50"  # 绿色
            elif status == 3:
                text = "推理中"
                color = "#FF9800"  # 黄色
            else:
                text = "未知状态"
                color = "#666"  # 灰色
                
            item = GroupListItem(group_name, icon, text)
            self.ui.listWidget.addItem(item)
            
            # 设置自定义widget到列表项
            self.ui.listWidget.setItemWidget(item, item.custom_widget)
            
            # 应用颜色样式到描述标签
            item.desc_label.setStyleSheet(f"color: {color};")
            
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
            return selected_items[0].group_name
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

class TrainingProgressDialog(QDialog):
    """
    训练进度可视化对话框，用于实时显示模型训练信息
    """
    def __init__(self, parent=None, model_id=None, model_name=None):
        super().__init__(parent)
        self.setWindowTitle("模型训练进度")
        self.resize(800, 500)
        self.model_id = model_id
        self.model_name = model_name
        self.http_server = HttpServer()
        self.stopped = False
        self.show_full_curve = True  # 默认显示全部曲线
        
        # 创建主布局
        main_layout = QVBoxLayout()
        
        # 添加标题
        title_label = QLabel(f"模型 [{model_name}] 训练进度")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 创建图表
        self.create_chart()
        main_layout.addWidget(self.chart_view)
        
        # 创建图表控制区域
        chart_control_layout = QHBoxLayout()
        
        # 添加切换视图按钮
        self.view_toggle_button = QPushButton("切换为最近视图")
        self.view_toggle_button.clicked.connect(self.toggle_chart_view)
        chart_control_layout.addWidget(self.view_toggle_button)
        
        main_layout.addLayout(chart_control_layout)
        
        # 创建信息展示区域
        info_layout = QHBoxLayout()
        
        # 左侧信息
        left_info = QVBoxLayout()
        self.epoch_label = QLabel("当前轮数: 0")
        self.loss_label = QLabel("损失值: 0.0")
        self.p_true_label = QLabel("真实样本概率: 0.0")
        self.p_fake_label = QLabel("生成样本概率: 0.0")
        
        left_info.addWidget(self.epoch_label)
        left_info.addWidget(self.loss_label)
        left_info.addWidget(self.p_true_label)
        left_info.addWidget(self.p_fake_label)
        
        # 右侧信息
        right_info = QVBoxLayout()
        self.begin_time_label = QLabel("开始时间: --")
        self.end_time_label = QLabel("结束时间: --")
        self.total_time_label = QLabel("训练总时间: --")
        self.status_label = QLabel("状态: 训练中")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        
        right_info.addWidget(self.begin_time_label)
        right_info.addWidget(self.end_time_label)
        right_info.addWidget(self.total_time_label)
        right_info.addWidget(self.status_label)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        self.stop_button = QPushButton("停止训练")
        self.stop_button.clicked.connect(self.stop_training)
        button_layout.addStretch()
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()
        
        # 将所有布局添加到主布局
        info_layout.addLayout(left_info)
        info_layout.addLayout(right_info)
        main_layout.addLayout(info_layout)
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
        # 启动定时器，每秒更新一次
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_data)
        self.timer.start(1000)
        
        # 记录初始时间
        self.start_time = time.time()
        
        # 创建加载动画，设置为对话框的子部件
        self.loading = LoadingAnimation(self)
        self.loading.set_text("正在准备训练...")
        # 确保加载动画显示在对话框中央
        self.loading.setGeometry(self.rect())
        self.loading.show()

    def toggle_chart_view(self):
        """切换图表显示模式：全部曲线或最近20个点"""
        self.show_full_curve = not self.show_full_curve
        if self.show_full_curve:
            self.view_toggle_button.setText("切换为最近视图")
        else:
            self.view_toggle_button.setText("切换为全部视图")
        # 强制更新图表
        self.update_data()
        
    def create_chart(self):
        """创建图表"""
        # 创建图表和视图
        self.chart = QChart()
        self.chart.setTitle("训练损失与概率")
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        
        # 启用图表缩放
        self.chart_view.setRubberBand(QChartView.RectangleRubberBand)
        self.chart_view.setDragMode(QChartView.ScrollHandDrag)
        
        # 创建数据系列
        self.loss_series = QLineSeries()
        self.loss_series.setName("损失值")
        
        self.p_true_series = QLineSeries()
        self.p_true_series.setName("真实样本概率")
        
        self.p_fake_series = QLineSeries()
        self.p_fake_series.setName("生成样本概率")
        
        # 添加系列到图表
        self.chart.addSeries(self.loss_series)
        self.chart.addSeries(self.p_true_series)
        self.chart.addSeries(self.p_fake_series)
        
        # 创建坐标轴
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("训练轮数")
        self.axis_x.setRange(0, 10)  # 初始显示10轮
        self.axis_x.setTickCount(11)
        self.axis_x.setLabelFormat("%d")  # 整数格式
        self.axis_x.setLabelsFont(self.font())
        
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("损失值和概率")  # 更明确的标题
        self.axis_y.setRange(0, 1)
        self.axis_y.setTickCount(6)  # 减少刻度数量，避免拥挤
        self.axis_y.setLabelFormat("%.3f")  # 三位小数格式
        self.axis_y.setLabelsFont(self.font())
        self.axis_y.setTitleFont(self.font())
        
        # 将坐标轴添加到图表
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        
        # 将系列附加到坐标轴
        self.loss_series.attachAxis(self.axis_x)
        self.loss_series.attachAxis(self.axis_y)
        
        self.p_true_series.attachAxis(self.axis_x)
        self.p_true_series.attachAxis(self.axis_y)
        
        self.p_fake_series.attachAxis(self.axis_x)
        self.p_fake_series.attachAxis(self.axis_y)
        
        # 调整图表外观
        self.chart.setBackgroundVisible(False)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        self.chart_view.setMinimumHeight(300)
        
    def update_data(self):
        """获取并更新训练数据"""
        if self.stopped:
            return
            
        try:
            # 获取训练进度信息
            train_process = self.http_server.train_process(self.model_id)
            
            # 如果获取到数据，关闭加载动画
            if train_process and hasattr(self, 'loading') and self.loading.isVisible():
                self.loading.close_animation()
                
            # 更新图表数据
            epochs = train_process.get("epoch", [0])
            losses = train_process.get("loss", [])
            p_trues = train_process.get("p_true", [0])
            p_fakes = train_process.get("p_fake", [0])
            begin_time = train_process.get("begin_time", "")
            end_time = train_process.get("end_time", "")
            
            # 清除当前所有数据点
            self.loss_series.clear()
            self.p_true_series.clear()
            self.p_fake_series.clear()
            
            # 添加所有数据点
            for i, epoch in enumerate(epochs):
                # p_true和p_fake数据
                if i < len(p_trues):
                    self.p_true_series.append(epoch, p_trues[i])
                if i < len(p_fakes):
                    self.p_fake_series.append(epoch, p_fakes[i])
                
                # loss数据（如果存在）
                if i < len(losses):
                    self.loss_series.append(epoch, losses[i])
            
            # 获取最新的数据点用于显示
            latest_epoch = epochs[-1] if epochs else 0
            latest_loss = losses[-1] if losses else 0.0
            latest_p_true = p_trues[-1] if p_trues else 0.0
            latest_p_fake = p_fakes[-1] if p_fakes else 0.0
            
            # 调整X轴范围
            start_epoch = epochs[0] if epochs else 0
            
            if self.show_full_curve:
                # 显示全部曲线
                if latest_epoch > 10:
                    # 计算合适的刻度间隔，确保刻度数量在5-10之间
                    tick_interval = max(1, (latest_epoch - start_epoch) // 10)
                    tick_count = (latest_epoch - start_epoch) // tick_interval + 1
                    
                    # 确保刻度数量合理
                    if tick_count > 15:
                        tick_interval = (latest_epoch - start_epoch) // 10
                        tick_count = 11
                    
                    self.axis_x.setRange(start_epoch, latest_epoch)
                    self.axis_x.setTickCount(tick_count)
                else:
                    self.axis_x.setRange(0, 10)
                    self.axis_x.setTickCount(11)
            else:
                # 只显示最近20个点
                window_size = min(20, len(epochs))
                if window_size > 0 and latest_epoch > 10:
                    start_idx = max(0, len(epochs) - window_size)
                    recent_start = epochs[start_idx]
                    self.axis_x.setRange(recent_start, latest_epoch)
                    self.axis_x.setTickCount(min(11, window_size + 1))
                else:
                    self.axis_x.setRange(0, 10)
                    self.axis_x.setTickCount(11)
            
            # 调整Y轴范围
            all_values = p_trues + p_fakes
            if losses:
                all_values += losses
                
            max_y = max(all_values + [0.1]) if all_values else 0.1
            min_y = min(all_values + [0.0]) if all_values else 0.0
            
            # 在最小值和最大值基础上留出一定的空间
            y_range = max_y - min_y
            self.axis_y.setRange(max(0, min_y - y_range * 0.1), max_y * 1.1)
            
            # 确保Y轴有足够的刻度以显示数据
            if max_y > 0.5:
                self.axis_y.setTickCount(6)  # 减少刻度数
            else:
                self.axis_y.setTickCount(6)  # 减少刻度数
                
            # 根据数值范围调整小数点格式
            if max_y < 0.01:
                self.axis_y.setLabelFormat("%.4f")  # 更多小数位
            elif max_y < 0.1:
                self.axis_y.setLabelFormat("%.3f")
            else:
                self.axis_y.setLabelFormat("%.2f")
            
            # 更新标签信息
            self.epoch_label.setText(f"当前轮数: {latest_epoch}")
            self.loss_label.setText(f"损失值: {latest_loss:.4f}")
            self.p_true_label.setText(f"真实样本概率: {latest_p_true:.4f}")
            self.p_fake_label.setText(f"生成样本概率: {latest_p_fake:.4f}")
            
            # 更新时间信息
            current_time = time.time()
            
            # 更新开始时间
            if begin_time:
                if isinstance(begin_time, (int, float)):
                    # 如果是时间戳，转换为可读格式
                    begin_time_str = datetime.fromtimestamp(begin_time).strftime("%Y-%m-%d %H:%M:%S")
                    self.begin_time_label.setText(f"开始时间: {begin_time_str}")
                else:
                    self.begin_time_label.setText(f"开始时间: {begin_time}")
            
            # 检查模型状态并更新结束时间和训练状态
            training_complete = False
            try:
                model_status = self.http_server.get_model_status(self.model_name)
                
                # 状态为2表示训练完成，或者手动停止训练时
                if model_status == 2 or self.stopped:
                    training_complete = True
                    # 设置结束时间为当前时间，如果之前没有设置过
                    if not hasattr(self, 'actual_end_time'):
                        self.actual_end_time = current_time
                        # 格式化结束时间
                        end_time_str = datetime.fromtimestamp(self.actual_end_time).strftime("%Y-%m-%d %H:%M:%S")
                        self.end_time_label.setText(f"结束时间: {end_time_str}")
                    
                    # 更新状态标签
                    if self.stopped:
                        self.status_label.setText("状态: 已手动停止训练")
                        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
                    else:
                        self.status_label.setText("状态: 训练已完成")
                        self.status_label.setStyleSheet("color: green; font-weight: bold;")
                    
                    # 禁用停止按钮
                    self.stop_button.setEnabled(False)
                    # 停止定时器
                    self.timer.stop()
                else:
                    # 训练仍在进行中，显示实时状态
                    self.status_label.setText("状态: 训练中")
                    self.status_label.setStyleSheet("color: blue; font-weight: bold;")
                    # 确保停止按钮可用
                    self.stop_button.setEnabled(True)
                    self.end_time_label.setText("结束时间: --")
            except Exception as e:
                print(f"获取模型状态失败: {str(e)}")
                
            # 计算训练总时间
            if training_complete and hasattr(self, 'actual_end_time'):
                # 使用实际结束时间计算
                if isinstance(begin_time, (int, float)):
                    total_seconds = int(self.actual_end_time - begin_time)
                else:
                    total_seconds = int(self.actual_end_time - self.start_time)
            else:
                # 使用当前时间计算训练中的总时间
                if isinstance(begin_time, (int, float)):
                    total_seconds = int(current_time - begin_time)
                else:
                    total_seconds = int(current_time - self.start_time)
            
            # 显示训练总时间
            minutes, seconds = divmod(total_seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                self.total_time_label.setText(f"训练总时间: {hours}小时{minutes}分{seconds}秒")
            else:
                self.total_time_label.setText(f"训练总时间: {minutes}分{seconds}秒")
                
        except Exception as e:
            print(f"更新训练数据失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def stop_training(self):
        """停止训练"""
        confirm = QMessageBox.question(
            self,
            "确认停止",
            "确定要停止训练吗？停止后无法继续。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                # 设置停止标志
                self.stopped = True
                # 记录实际结束时间
                self.actual_end_time = time.time()
                # 停止训练
                result = self.http_server.finish_model(self.model_id)
                print(f"停止训练结果: {result}")
                
                # 更新UI状态
                self.status_label.setText("状态: 已手动停止训练")
                self.status_label.setStyleSheet("color: orange; font-weight: bold;")
                self.stop_button.setEnabled(False)
                
                # 更新结束时间
                end_time_str = datetime.fromtimestamp(self.actual_end_time).strftime("%Y-%m-%d %H:%M:%S")
                self.end_time_label.setText(f"结束时间: {end_time_str}")
                
                # 更新一次数据以刷新界面
                self.update_data()
            except Exception as e:
                print(f"停止训练失败: {str(e)}")
                import traceback
                traceback.print_exc()
                QMessageBox.critical(self, "错误", f"停止训练失败: {str(e)}")
    
    def closeEvent(self, event):
        """关闭窗口事件"""
        self.timer.stop()
        event.accept()