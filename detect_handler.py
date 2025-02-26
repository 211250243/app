import os
import shutil

import paramiko
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
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


class DetectHandler:
    """
    处理 DetectWidget中的所有操作
    """
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        # 将所有子控件添加为实例属性
        for child in self.ui.findChildren(QWidget):
            setattr(self.ui, child.objectName(), child)
        self.init_ui()
        self.ssh_client = None
        self.sftp_client = None
        self.processed_files = set()
        self.result_timer = QTimer()
        self.result_timer.timeout.connect(self.fetch_new_results)
        self.connect_to_server()

    def init_ui(self):
        """Initialize the UI components"""
        self.ui.resultLabel.setAlignment(Qt.AlignCenter)
        self.ui.resultLabel.setMinimumSize(400, 300)

    def connect_to_server(self):
        """Connect to remote server"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                config.SERVER_HOSTNAME,
                config.SERVER_PORT,
                config.SERVER_USERNAME,
                config.SERVER_PASSWORD
            )
            self.sftp_client = self.ssh_client.open_sftp()
            self.result_timer.start(1000)  # Check every second
        except Exception as e:
            show_message_box("错误", f"连接服务器失败: {str(e)}", QMessageBox.Critical)

    def fetch_new_results(self):
        """Fetch new results from server"""
        try:
            result_dir = config.SERVER_UPLOAD_PATH
            files = self.sftp_client.listdir(result_dir)
            print(files)

            # Filter for new image files
            new_files = [f for f in files if f not in self.processed_files
                         and f.lower().endswith(('.png', '.jpg', '.jpeg'))]

            if new_files:
                # Get the newest file
                newest_file = max(new_files, key=lambda x:
                self.sftp_client.stat(join_path(result_dir, x)).st_mtime)

                # Download and display the file
                local_path = join_path(config.PROJECT_METADATA['project_path'],
                                       'results', newest_file)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                self.sftp_client.get(
                    join_path(result_dir, newest_file),
                    local_path
                )

                self.display_result(local_path)
                self.processed_files.add(newest_file)
        except Exception as e:
            print(f"Error fetching new results: {str(e)}")

    def display_result(self, image_path: str):
        """Display detection result image"""
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
        """Disconnect from server"""
        if self.result_timer.isActive():
            self.result_timer.stop()
        if self.sftp_client:
            self.sftp_client.close()
        if self.ssh_client:
            self.ssh_client.close()