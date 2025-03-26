import os
import paramiko
from PySide6.QtWidgets import QFileDialog, QMessageBox

import config
from utils import show_message_box, ProgressDialog, is_image, join_path


class SSHServer:
    def __init__(self):
        self.ssh_client = None # SSH 客户端，用于执行命令
        self.sftp_client = None # SFTP 客户端，用于传输文件

    def connect_to_server(self):
        """连接远程服务器"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(config.SERVER_HOSTNAME, config.SERVER_PORT,
                                    config.SERVER_USERNAME, config.SERVER_PASSWORD, timeout=3)
            self.sftp_client = self.ssh_client.open_sftp()
            print("连接服务器成功")
        except Exception as e:
            print(f"连接服务器失败：{str(e)}")
            raise # 继续抛出异常

    def upload_file(self, local_file_path, remote_file_path):
        """上传文件到远程服务器"""
        try:
            self.sftp_client.put(local_file_path, remote_file_path)
            print(f"上传文件: {local_file_path} -> {remote_file_path}")
        except Exception as e:
            print(f"文件上传失败：{str(e)}")
            raise # 继续抛出异常
    
    def upload_directory(self, local_path, remote_path):
        """递归上传整个目录"""
        # root, dirs, files 分别是当前目录、子目录、子文件
        for root, dirs, files in os.walk(local_path):
            # 创建对应的远程目录
            remote_dir = root.replace(local_path, remote_path, 1)
            try:
                self.sftp_client.mkdir(remote_dir)
            except IOError:
                pass  # 目录已存在则跳过
            # 上传所有文件
            for file in files:
                local_file = os.path.join(root, file)
                remote_file = os.path.join(remote_dir, file)
                self.upload_file(local_file, remote_file)

    def download_file(self, remote_file_path, local_file_path):
        """从远程服务器下载文件"""
        try:
            self.sftp_client.get(remote_file_path, local_file_path)
            print(f"下载文件: {remote_file_path} -> {local_file_path}")
        except Exception as e:
            print(f"文件下载失败：{str(e)}")
            raise

    def listdir(self, remote_path):
        """列出远程目录下的文件"""
        try:
            files = self.sftp_client.listdir(remote_path)
            return files
        except Exception as e:
            print(f"列出目录失败：{str(e)}")
            raise

    def stat(self, remote_path):
        """获取远程文件信息"""
        try:
            file_info = self.sftp_client.stat(remote_path)
            return file_info
        except Exception as e:
            print(f"获取文件信息失败：{str(e)}")
            raise

    def close_connection(self):
        """关闭连接"""
        if self.sftp_client:
            self.sftp_client.close()
        if self.ssh_client:
            self.ssh_client.close()






    def select_file_and_upload(self):
        """选择文件并上传"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(None, "选择文件", "", "所有文件 (*)")

        if file_path:
            # 远程文件路径，例如：/remote-home/user/images/
            remote_path = '/remote-home/user/images/' + file_path.split('/')[-1]
            self.upload_file(file_path, remote_path)

    def execute_training_command(self, dataset_path):
        """在远程服务器上执行训练命令"""
        command = f"python3 /remote-home/user/train_model.py --dataset {dataset_path}"
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            print("Training started...")
            output = stdout.read().decode()
            print(output)
            error = stderr.read().decode()
            if error:
                print(f"Error: {error}")
            else:
                show_message_box("训练完成", "模型训练完成", QMessageBox.Information)
        except Exception as e:
            show_message_box("训练失败", f"训练执行失败：{str(e)}", QMessageBox.Warning)

    def upload_and_test_image(self, image_path):
        """上传图片并执行测试"""
        # 上传图片
        remote_test_path = '/remote-home/user/test_images/' + image_path.split('/')[-1]
        self.upload_file(image_path, remote_test_path)

        # 执行测试命令
        test_command = f"python3 /remote-home/user/test_model.py --image {remote_test_path}"
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(test_command)
            print("Testing started...")
            output = stdout.read().decode()
            print(output)
            error = stderr.read().decode()
            if error:
                print(f"Error: {error}")
            else:
                show_message_box("测试完成", "模型测试完成", QMessageBox.Information)
        except Exception as e:
            show_message_box("测试失败", f"测试执行失败：{str(e)}", QMessageBox.Warning)

    def test_exe_command(self, command="ls -l"):
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        print(stdout.read().decode())
    def test_upload_file(self, src="test/img/000.png", dest="000.png"):
        self.sftp_client.put(src, dest)
    def test_download_file(self, src="000.png", dest="test/img/000.png"):
        self.sftp_client.get(src, dest)


class UploadSampleGroup_SSH:
    """上传样本组到服务器的线程"""
    def __init__(self, ui):
        self.local_sample_path = config.SAMPLE_PATH
        self.remote_sample_path = config.SERVER_SAMPLE_PATH
        self.ui = ui
        self.total_files = 0  # 总文件数
        self.uploaded_files = 0  # 已上传文件数

        self.progressDialog = ProgressDialog(self.ui, {
            "title": "上传样本",
            "text": "正在上传样本组..."
        })

    def count_files(self, directory):
        """统计目录中的所有图片文件数量"""
        count = 0
        for root, dirs, files in os.walk(directory):
            for file in files:
                if is_image(file):
                    count += 1
        return count

    def upload_directory_with_progress(self, server, local_path, remote_path):
        """递归上传整个目录，并更新进度条"""
        # 确保远程目录存在
        try:
            server.sftp_client.mkdir(remote_path)
        except IOError:
            pass  # 目录已存在则跳过
        # 遍历本地目录
        for item in os.listdir(local_path):
            local_item_path = join_path(local_path, item)
            remote_item_path = join_path(remote_path, item)

            if os.path.isdir(local_item_path):
                # 如果是目录，递归上传
                try:
                    server.sftp_client.mkdir(remote_item_path)
                except IOError:
                    pass  # 目录已存在则跳过
                self.upload_directory_with_progress(server, local_item_path, remote_item_path)
            elif os.path.isfile(local_item_path) and is_image(item):
                # 如果是图片文件，上传
                try:
                    server.upload_file(local_item_path, remote_item_path)
                    self.uploaded_files += 1
                    # 更新进度条
                    progress = int(self.uploaded_files / self.total_files * 100)
                    self.progressDialog.setValue(progress)
                except Exception as e:
                    show_message_box("错误", f"上传失败: {str(e)}", QMessageBox.Critical)

    def run(self):
        # 连接服务器
        server = SSHServer()
        try:
            server.connect_to_server()
        except Exception as e:
            show_message_box("错误", f"连接服务器失败: {str(e)}", QMessageBox.Critical)
            return
        try:
            # 统计所有需要上传的文件数量
            self.total_files = self.count_files(self.local_sample_path)
            if self.total_files == 0:
                show_message_box("警告", "没有找到可上传的图片文件", QMessageBox.Warning)
                return
            # 更新进度条文本
            self.progressDialog.setLabelText(f"正在上传 {self.total_files} 个文件...")
            # 上传整个样本组文件夹
            self.uploaded_files = 0
            self.upload_directory_with_progress(server, self.local_sample_path, self.remote_sample_path)
            # 上传成功
            show_message_box("成功", "样本组上传成功", QMessageBox.Information)
        except Exception as e:
            show_message_box("错误", f"上传失败: {str(e)}", QMessageBox.Critical)
        finally:
            server.close_connection()

if __name__ == "__main__":
    # Create a server instance（自动连接服务器）
    server = SSHServer()
    server.connect_to_server()

    # Execute a command
    stdin, stdout, stderr = server.ssh_client.exec_command("ls -l")
    print(stdout.read().decode())

    # Upload / Download a file
    # server.sftp_client.put("test/img/000.png", "000.png")
    # server.sftp_client.get("/remote-home/user/test.txt", "test_download.txt")

    # Close the connection
    server.close_connection()