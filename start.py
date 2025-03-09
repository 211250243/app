import json
import os
from pathlib import Path  # 用于处理文件路径
from PySide6.QtCore import QDateTime, Signal, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QDialog, QMessageBox, QLabel
from PySide6.QtUiTools import QUiLoader

import config
from main import MainWindow
from utils import join_path, show_message_box, check_and_create_path, FloatingTimer


class NewProjectDialog(QDialog):
    # 创建一个信号，返回项目的元数据
    project_info = Signal(str)

    def __init__(self):
        super().__init__()

        # 加载UI文件
        self.ui = QUiLoader().load(r'ui/new_project.ui')

        # 设置按钮点击事件
        self.ui.newButton.clicked.connect(self.create_new_project)
        self.ui.pathButton.clicked.connect(self.select_path)
        self.ui.cancelButton.clicked.connect(self.cancel)

        self.path = ""  # 用于保存项目的路径

    def create_new_project(self):
        """
        创建新项目并保存到指定路径
        """
        # 检查项目名称是否合法
        project_name = self.ui.nameEdit.text()
        if not project_name.isidentifier():  # 判断是否是合法的标识符
            show_message_box("错误", "项目名称不合法！", QMessageBox.Critical)
            return

        # 检查路径是否存在
        self.path = self.ui.pathEdit.text()
        if not check_and_create_path(self.path):
            return  # 如果没有指定路径或路径非法，返回

        # 在指定路径下创建一个名为 project_name 的文件夹
        project_folder = join_path(self.path, project_name)
        # 检查该文件夹是否已经存在，如果不存在则创建，如果存在则提示用户
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
            print(f"创建文件夹: {project_folder}")
        else:
            show_message_box("错误", "项目已存在，请选择其他路径！", QMessageBox.Critical)
            return

        # 生成项目的元数据
        metadata = {
            "project_name": project_name,
            "project_path": str(project_folder),
            "description": self.ui.descriptionEdit.toPlainText(),
            "create_time": QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        }

        # 保存到 metadata.json
        metadata_file_path = join_path(project_folder, "metadata.json")
        with open(metadata_file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

        show_message_box("成功", f"项目已保存到 {metadata_file_path}", QMessageBox.Information)

        # 发射信号，将项目路径传递给父窗口
        self.project_info.emit(str(project_folder))
        # 关闭新建项目窗口
        self.ui.accept()

    def select_path(self):
        """
        让用户选择保存路径
        """
        folder = QFileDialog.getExistingDirectory(self, "选择项目保存路径")
        if folder:
            self.path = folder
            self.ui.pathEdit.setText(self.path)

    def cancel(self):
        """
        关闭新建项目窗口，返回到开始窗口
        """
        self.ui.reject()  # 关闭当前窗口


# 开始界面窗口
class StartWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 创建UI对象并设置界面
        self.ui = QUiLoader().load(r'ui\start.ui')

        # 设置按钮点击事件
        self.ui.newButton.clicked.connect(self.create_new_archive)
        self.ui.openButton.clicked.connect(self.open_existing_archive)
        
        # 创建悬浮计时器
        self.floating_timer = FloatingTimer(self.ui)
        self.floating_timer.show()

    def create_new_archive(self):
        """
        打开新建项目窗口
        """
        # 创建新建项目窗口
        new_project_dialog = NewProjectDialog()
        # 连接信号：接收项目信息
        new_project_dialog.project_info.connect(self.save_project_info)
        # 使用 exec() 让新建项目窗口成为模态窗口，阻止父窗口操作
        result = new_project_dialog.ui.exec()
        # 根据返回值判断用户操作
        if result == QDialog.Accepted:
            print("新建项目成功，项目路径：", self.project_folder)
            # 在这里执行项目创建成功后的操作
            self.open_existing_archive(self.project_folder)
        elif result == QDialog.Rejected:
            print("取消新建项目")
            # 在这里执行项目取消操作

    def save_project_info(self, project_folder):
        """
        处理新建项目后的项目信息
        """
        self.project_folder = project_folder

    def open_existing_archive(self, folder=None):
        """
        点击打开归档按钮，弹出文件选择对话框
        """
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if folder:
            # 检查文件夹中是否存在 metadata.json
            metadata_path = config.PROJECT_METADATA_PATH = join_path(folder, config.PROJECT_METADATA_FILE)
            if os.path.exists(metadata_path):
                try:
                    # 读取 metadata.json
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        config.PROJECT_METADATA = json.load(f)
                        print("项目信息：", config.PROJECT_METADATA)
                    # 显示读取的项目信息
                    self.open_main_window()
                except Exception as e:
                    show_message_box("错误", f"读取项目元数据失败: {str(e)}", QMessageBox.Critical)
            else:
                show_message_box("错误", "选择的文件夹没有找到 metadata.json 文件", QMessageBox.Critical)

    def open_main_window(self):
        """
        跳转到主窗口，显示项目的详细信息
        """
        # 创建主窗口并传递计时器
        self.main_window = MainWindow(floating_timer=self.floating_timer)
        self.main_window.ui.show()  # 显示主窗口
        self.ui.close()  # 关闭开始窗口


if __name__ == "__main__":
    app = QApplication([])

    window = StartWindow()
    window.ui.show()

    app.exec()