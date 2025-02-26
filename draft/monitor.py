import os
import paramiko
from PySide6.QtCore import QObject, QTimer, Signal, QThread


class RemoteFileMonitor(QObject):
    new_image_detected = Signal(bytes, str)  # 图片数据，文件名

    def __init__(self, host, username, password, remote_path):
        super().__init__()
        self.host = host
        self.username = username
        self.password = password
        self.remote_path = remote_path
        self.processed_files = set()
        self.ssh = None
        self.sftp = None
        self.timer = QTimer()

    def start_monitoring(self):
        """初始化连接并启动定时器"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.host, username=self.username, password=self.password)
            self.sftp = self.ssh.open_sftp()
            print("连接成功")
            self.timer.timeout.connect(self._check_remote_files)
            self.timer.start(1000)  # 每秒检查一次
        except Exception as e:
            print(f"连接失败: {e}")

    def _check_remote_files(self):
        """检查远程目录中的新文件"""
        try:
            files = self.sftp.listdir_attr(self.remote_path)
            print(f"检查文件: {len(files)}")
            new_files = [
                f for f in files
                if f.filename not in self.processed_files
                   and f.filename.lower().endswith(('.png', '.jpg', '.jpeg'))
            ]
            # 按修改时间排序
            new_files.sort(key=lambda x: x.st_mtime)

            for file_attr in new_files:
                self._process_file(file_attr)

        except Exception as e:
            print(f"检查文件出错: {e}")

    def _process_file(self, file_attr):
        """处理单个文件"""
        filename = file_attr.filename
        remote_path = os.path.join(self.remote_path, filename)
        try:
            with self.sftp.file(remote_path, 'rb') as remote_file:
                data = remote_file.read()
                self.new_image_detected.emit(data, filename)
                self.processed_files.add(filename)
        except Exception as e:
            print(f"文件处理失败 {filename}: {e}")

    def stop_monitoring(self):
        """停止监控并清理资源"""
        self.timer.stop()
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()