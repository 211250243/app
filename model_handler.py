import os
import shutil
import random

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QDialog, QMessageBox, QFileDialog, QVBoxLayout, QTreeWidgetItem, QListWidgetItem
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

import config
from http_server import HttpServer, PatchCoreParamMapper_Http, UploadSampleGroup_HTTP
from sample_handler import SampleGroupDialog
from ssh_server import PatchCoreParamMapper_SSH
from utils import check_model_group, check_sample_group, copy_image, show_message_box, update_metadata, join_path, is_image



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
        UploadSampleGroup_HTTP(self.ui).run()

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
        # getOpenFileNames 返回一个元组，包含文件路径列表和文件类型过滤器。
        files, _ = QFileDialog.getOpenFileNames(self.ui, "选择图片文件", "", "图片文件 (*.png *.jpg *.jpeg)")
        if files:
            sample_group_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, config.SAMPLE_LABEL_TRAIN_GOOD)
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
            sample_group_path = join_path(config.SAMPLE_PATH, dialog.selected_group, config.SAMPLE_LABEL_TRAIN_GOOD)
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
                # 对接 http_server: 创建模型组
                try:
                    # 从UI获取参数选择，获取训练参数
                    # 根据训练参数创建模型
                    id = HttpServer().add_model({
                        "name": model_group,
                        **config.MODEL_PARAMS
                    })
                    print(f"http_server创建模型组成功 ID={id} \n模型参数={config.MODEL_PARAMS}")
                except Exception as e:
                    print(f"http_server创建模型组失败: {str(e)}")
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
            # 对接 http_server: 获取模型参数
            try:
                config.MODEL_PARAMS = HttpServer().get_model_params(dialog.selected_group)
                self.update_params() # 更新参数显示
                print(f"http_server获取模型参数成功: {config.MODEL_PARAMS}")
            except Exception as e:
                print(f"http_server获取模型参数失败: {str(e)}")
            # 更新数据
            config.MODEL_GROUP = dialog.selected_group
            update_metadata('model_group', config.MODEL_GROUP)            
            self.update_model_group() # 更新模型组路径和模型组名称
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
                    self.update_model_group()
                    config.MODEL_PARAMS = self.get_params() # 设置默认参数
                    self.update_params()
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
        
    def update_params(self):
        """
        TODO: 更新参数显示
        """

        
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
            self.update_params()

    def train_model(self):
        """
        训练模型
        """
        # 检查是否有选择模型和样本组
        if not check_model_group() or not check_sample_group():
            return
        # 显示训练开始的消息
        show_message_box("信息", "模型训练已开始，请耐心等待...", QMessageBox.Information, self.ui)
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
                self.update_model_group()
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
        except Exception as e:
            show_message_box("错误", f"训练失败: {str(e)}", QMessageBox.Critical, self.ui)

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
            # 对接 http_server: 更新模型参数
            try:
                http_server = HttpServer()
                model_id = http_server.get_model_id(config.MODEL_GROUP)
                params = dialog.params
                print(f"更新模型参数: {model_id} -> {params}")
                # http_server.update_model_params(model_id, params)
                show_message_box("成功", "模型参数已更新！", QMessageBox.Information, self.ui)
            except Exception as e:
                show_message_box("错误", f"更新参数失败: {str(e)}", QMessageBox.Critical, self.ui)

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