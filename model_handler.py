import os
import shutil

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QDialog, QMessageBox, QFileDialog

import config
from utils import show_message_box, update_metadata, join_path


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
        model_folder = os.path.join(config.PROJECT_METADATA['project_path'], config.MODEL_FOLDER)
        if not os.path.exists(model_folder):
            os.makedirs(model_folder)
        model_path = os.path.join(model_folder, model_name)
        if not os.path.exists(model_path):
            os.makedirs(model_path)
            config.MODEL_PATH = model_path
        else:
            show_message_box("错误", "模型已存在，请选择其他名称！", QMessageBox.Critical)
            return
        # 修改项目的元数据
        update_metadata('model', model_name)
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
        self.init()

    def init(self):
        self.ui.newModelButton.clicked.connect(self.create_new_model)
        self.ui.importModelButton.clicked.connect(self.import_model)

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
                config.MODEL_PATH = os.path.join(model_folder, model_name)
                update_metadata('model', model_name)
                self.ui.curModelEdit.setText(config.MODEL_PATH)
                show_message_box("成功", "导入模型成功！", QMessageBox.Information)
