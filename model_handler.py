import os
import shutil
import random

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QDialog, QMessageBox, QFileDialog

import config
from utils import show_message_box, update_metadata, join_path, is_image


class PatchCoreParamMapper:
    """
    将简化的三个参数（模型精度、缺陷大小和训练速度）映射到专业的PatchCore训练参数
    """
    def __init__(self):
        # 精度选项
        self.accuracy_options = {
            "低精度": {
                "backbone_names": ["wide_resnet50_2"],
                "layers_to_extract_from": ["layer2", "layer3"],
                "pretrain_embed_dimension": 256,
                "target_embed_dimension": 256,
                "anomaly_scorer_num_nn": 1
            },
            "中等精度": {
                "backbone_names": ["wide_resnet50_2"],
                "layers_to_extract_from": ["layer2", "layer3"],
                "pretrain_embed_dimension": 512,
                "target_embed_dimension": 512,
                "anomaly_scorer_num_nn": 3
            },
            "高精度": {
                "backbone_names": ["wide_resnet50_2"],
                "layers_to_extract_from": ["layer2", "layer3"],
                "pretrain_embed_dimension": 1024,
                "target_embed_dimension": 1024,
                "anomaly_scorer_num_nn": 5
            }
        }
        
        # 缺陷大小选项
        self.defect_size_options = {
            "小缺陷": {
                "patchsize": 3,
                "patchoverlap": 0.25
            },
            "中等缺陷": {
                "patchsize": 5,
                "patchoverlap": 0.5
            },
            "大缺陷": {
                "patchsize": 9,
                "patchoverlap": 0.75
            }
        }
        
        # 训练速度选项
        self.training_speed_options = {
            "快速": {
                "preprocessing": "mean",
                "aggregation": "mean"
            },
            "均衡": {
                "preprocessing": "mean",
                "aggregation": "mlp"
            },
            "慢速高质量": {
                "preprocessing": "conv",
                "aggregation": "mlp"
            }
        }
    
    def get_params(self, accuracy, defect_size, training_speed):
        """
        根据三个简化选项获取完整的PatchCore参数
        
        Args:
            accuracy: 精度选项，可选值为"低精度"、"中等精度"、"高精度"
            defect_size: 缺陷大小选项，可选值为"小缺陷"、"中等缺陷"、"大缺陷"
            training_speed: 训练速度选项，可选值为"快速"、"均衡"、"慢速高质量"
            
        Returns:
            完整的PatchCore参数字典
        """
        params = {}
        params.update(self.accuracy_options[accuracy])
        params.update(self.defect_size_options[defect_size])
        params.update(self.training_speed_options[training_speed])
        
        # 添加固定参数
        params.update({
            "patchscore": "max",
            "faiss_on_gpu": True,
            "faiss_num_workers": 8
        })
        
        return params
    
    def get_all_options(self):
        """获取所有可用的选项"""
        return {
            "accuracy": list(self.accuracy_options.keys()),
            "defect_size": list(self.defect_size_options.keys()),
            "training_speed": list(self.training_speed_options.keys())
        }


class NewModelDialog(QDialog):

    def __init__(self):
        super().__init__()

        # 加载UI文件
        self.ui = QUiLoader().load(r'ui/new_model.ui')
        # 设置按钮点击事件
        self.ui.newButton.clicked.connect(self.create_model)
        self.ui.cancelButton.clicked.connect(self.cancel)

    def create_model(self):
        """
        创建新项目并保存到指定路径
        """
        # 检查项目名称是否合法
        model_name = self.ui.nameEdit.text()
        if not model_name.isidentifier():  # 判断是否是合法的标识符
            show_message_box("错误", "模型名称不合法！", QMessageBox.Critical)
            return
        # 创建模型文件夹
        model_folder = join_path(config.PROJECT_METADATA['project_path'], config.MODEL_FOLDER)
        if not os.path.exists(model_folder):
            os.makedirs(model_folder)
        model_path = join_path(model_folder, model_name)
        if not os.path.exists(model_path):
            os.makedirs(model_path)
            # 更新数据
            config.MODEL_PATH = model_path
            update_metadata('model_path', model_path)
        else:
            show_message_box("错误", "模型已存在，请选择其他名称！", QMessageBox.Critical)
            return
        # 关闭新建模型窗口
        self.ui.accept()

    def cancel(self):
        """
        关闭新建项目窗口，返回到开始窗口
        """
        self.ui.reject()  # 关闭当前窗口

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
        # 初始化参数映射器
        self.param_mapper = PatchCoreParamMapper()
        # 初始化各种UI控件和回调
        self.init()
        # 初始化模型参数选项
        self.init_model_options()

    def init(self):
        self.ui.newModelButton.clicked.connect(self.create_new_model)
        self.ui.importModelButton.clicked.connect(self.import_model)
        self.ui.trainButton.clicked.connect(self.train_model) # 训练模型
        self.ui.viewParamsButton.clicked.connect(self.view_parameters) # 查看参数

    def init_model_options(self):
        """初始化模型选项下拉框"""
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
        

    def create_new_model(self):
        """
        创建新项目
        """
        # 不能合并为 NewModelDialog().ui.exec()，否则实例无引用，会立即被销毁！！！
        new_model_dialog = NewModelDialog()
        result = new_model_dialog.ui.exec()
        if result == QDialog.Accepted:
            print("新建模型成功")
            self.ui.curModelEdit.setText(config.MODEL_PATH)
        else:
            print("取消新建模型")

    def import_model(self):
        """
        从本地导入模型
        """
        folder = QFileDialog.getExistingDirectory(self.ui, "选择模型")
        model_name = os.path.basename(folder)
        if folder:
            model_folder = join_path(config.PROJECT_METADATA['project_path'], config.MODEL_FOLDER)
            if not os.path.exists(model_folder):
                os.makedirs(model_folder)
            # 判断是否在项目文件夹下，不在则复制到项目文件夹下
            if model_name in os.listdir(model_folder):
                show_message_box("警告", "模型已存在！", QMessageBox.Warning)
            else:
                shutil.copytree(folder, join_path(model_folder, model_name))
                print(f"复制{folder}到{model_folder}")
                # 修改项目的元数据
                config.MODEL_PATH = join_path(model_folder, model_name)
                update_metadata('model_path', config.MODEL_PATH)
                self.ui.curModelEdit.setText(config.MODEL_PATH)
                show_message_box("成功", "导入模型成功！", QMessageBox.Information)

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
