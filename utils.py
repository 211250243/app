import json
import os

from PySide6.QtCore import Signal
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QDialog, QVBoxLayout, QProgressBar, QLabel

import config


class CustomProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loading")
        self.setModal(True)
        self.setFixedSize(300, 150)

        layout = QVBoxLayout()

        self.label = QLabel("Loading, please wait...", self)
        layout.addWidget(self.label)

        self.movie_label = QLabel(self)
        self.movie = QMovie("B:/Development/GraduationDesign/app/ui/gif/loading.gif")
        self.movie_label.setMovie(self.movie)
        layout.addWidget(self.movie_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)
        self.movie.start()

    def setValue(self, value):
        self.progress_bar.setValue(value)
class ProgressDialog(QDialog):
    """
    进度展示框
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Upload Progress")
        self.setModal(True)
        self.setFixedSize(300, 100)

        layout = QVBoxLayout()
        self.label = QLabel("Uploading files...", self)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True) # 显示进度值

        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    def setValue(self, value):
        print(f"设置进度值：{value}")
        self.progress_bar.setValue(value)

def show_message_box(title: str, message: str, icon_type: QMessageBox.Icon, parent=None):
    """
    显示一个弹窗来提示用户当前的状态
    :param title: 弹窗标题
    :param message: 弹窗显示的信息
    :param icon_type: 弹窗的图标类型，如：QMessageBox.Information、QMessageBox.Warning、QMessageBox.Critical
    """
    msg_box = QMessageBox(parent)  # 创建一个消息框
    msg_box.setIcon(icon_type)  # 设置图标
    msg_box.setWindowTitle(title)  # 设置标题
    msg_box.setText(message)  # 设置显示的消息内容
    msg_box.exec()  # 显示弹窗

def check_and_create_path(path: str) -> bool:
    """
    检查路径是否合法，如果路径不存在则创建该路径
    :param path: 要检查或创建的路径
    :return: 如果路径有效（存在或创建成功），返回 True；否则返回 False
    """
    # 检查路径是否为空
    if not path:
        show_message_box("错误", "路径不能为空！", QMessageBox.Critical)
        return False
    # 如果路径存在并且是有效的目录
    if os.path.isdir(path):
        return True
    # 检查路径是否为合法（绝对路径）
    if not os.path.isabs(path):
        show_message_box("错误", "路径非法！", QMessageBox.Critical)
        return False
    # 如果路径不存在，尝试创建该路径
    try:
        os.makedirs(path)  # 尝试递归创建路径
        print(f"创建路径：{path}")
        return True
    except Exception as e:
        show_message_box("错误", "无法创建该路径！", QMessageBox.Critical)
        return False

def is_image(file_name: str) -> bool:
    """
    判断文件是否为图片文件
    """
    return file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'))

def join_path(*args) -> str:
    """
    拼接跨平台路径，强制args之中及其之间的分隔符为 /
    """
    return os.path.join(*args).replace("\\", "/")

def update_metadata(key, value):
    """
    更新项目元数据
    """
    metadata_path = config.PROJECT_METADATA_PATH
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        metadata[key] = value
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)