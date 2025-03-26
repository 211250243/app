import os
import shutil

import paramiko
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (QWidget, QDialog, QMessageBox, QFileDialog, 
                             QHBoxLayout, QVBoxLayout, QLabel, QListWidgetItem)

import config
from sample_handler import CustomListWidgetItem
from ssh_server import SSHServer
from utils import show_message_box, join_path, is_image


class DetectHandler:
    """
    处理 DetectWidget中的所有操作
    """
    def __init__(self, ui):
        super().__init__()
        # 初始化
        self.ui = ui
        self.processed_files = set()
        self.detect_path = config.DETECT_PATH
        # 确保检测目录存在
        if not os.path.exists(self.detect_path):
            os.makedirs(self.detect_path)
        # 将所有子控件添加为实例属性
        for child in self.ui.findChildren(QWidget):
            setattr(self.ui, child.objectName(), child)
            
        # 初始化检测列表
        self.init_detect_list()
        # 绑定事件
        self.ui.importDetectButton.clicked.connect(self.import_dir)
        self.ui.startDetectButton.clicked.connect(self.connect_to_server)
        self.ui.detectList.itemClicked.connect(self.show_detect_image)

    def init_detect_list(self):
        """初始化检测图片列表"""
        # 设置列表样式
        self.ui.detectList.setSpacing(10)
        # 加载现有图片
        self.load_detect_images()

    def import_dir(self):
        """从本地选择文件夹，导入其中的图片"""
        # 打开文件夹选择对话框
        folder = QFileDialog.getExistingDirectory(self.ui, "选择图片文件夹")
        if folder:
            
            # 遍历文件夹中的所有图片文件
            for file_name in os.listdir(folder):
                if is_image(file_name):
                    src_path = join_path(folder, file_name)
                    dst_path = join_path(self.detect_path, file_name)
                    shutil.copy2(src_path, dst_path)
                    
            # 重新加载图片列表
            self.load_detect_images()
    
    def load_detect_images(self):
        """加载detect文件夹中的所有图片"""
        # 清空现有列表
        self.ui.detectList.clear()
        
        # 获取所有图片文件
        images = [f for f in os.listdir(self.detect_path) if is_image(f)]
        
        # 添加图片到列表
        for index, image_name in enumerate(images):
            image_path = join_path(self.detect_path, image_name)
            item = CustomListWidgetItem(image_path, image_name, index)
            self.ui.detectList.addItem(item)
            self.ui.detectList.setItemWidget(item, item.item_widget)

    def show_detect_image(self, item):
        """显示选中的检测图片"""
        if hasattr(item, 'image_path'):
            pixmap = QPixmap(item.image_path)
            scaled_pixmap = pixmap.scaled(
                self.ui.resultLabel.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.ui.resultLabel.setPixmap(scaled_pixmap)
            self.ui.resultLabel.setToolTip(f"待检测图片: {os.path.basename(item.image_path)}")
            
            # 清空检测信息
            self.ui.infoLabel.setText("等待检测...")
            self.ui.resultBrowser.clear()

    def connect_to_server(self):
        self.server = SSHServer()
        try:
            self.server.connect_to_server()
        except Exception as e:
            show_message_box("连接失败", str(e), QMessageBox.Critical)
        self.result_timer = QTimer()
        self.result_timer.timeout.connect(self.fetch_new_results)
        self.result_timer.start(1000)  # Check every second
        # 更新UI状态
        self.ui.startDetectButton.setEnabled(False)
        self.ui.infoLabel.setText("检测中...")

    def fetch_new_results(self):
        """获取检测结果"""
        try:
            result_dir = config.SERVER_DOWNLOAD_PATH
            files = self.server.listdir(result_dir)

            # 过滤新的图片文件
            new_files = [f for f in files if f not in self.processed_files
                        and f.lower().endswith(('.png', '.jpg', '.jpeg'))]

            if new_files:
                # 获取最新的文件：按时间排序，返回修改时间最晚的
                newest_file = max(new_files, key=lambda x:
                self.server.stat(join_path(result_dir, x)).st_mtime)

                # 下载最新的文件
                local_path = join_path(config.PROJECT_METADATA['project_path'], 'results', newest_file)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                self.server.download_file(
                    join_path(result_dir, newest_file),
                    local_path
                )

                # 显示检测结果
                self.display_result(local_path)
                self.processed_files.add(newest_file)
        except Exception as e:
            print(f"获取检测结果失败: {str(e)}")

    def display_result(self, image_path: str):
        """显示检测结果图片"""
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(
                self.ui.resultLabel.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.ui.resultLabel.setPixmap(scaled_pixmap)
            self.ui.resultLabel.setToolTip(f"检测结果: {os.path.basename(image_path)}")

    def disconnect_from_server(self):
        """断开服务器连接"""
        # 停止定时器，并断开服务器连接
        if hasattr(self, 'result_timer') and self.result_timer.isActive():
            self.result_timer.stop()
        if hasattr(self, 'server'):
            self.server.close_connection()
        # 恢复UI状态
        self.ui.startDetectButton.setEnabled(True)
        self.ui.infoLabel.setText("检测完成")