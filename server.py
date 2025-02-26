import paramiko
from PySide6.QtWidgets import QFileDialog, QMessageBox

import config
from utils import show_message_box


class Server:
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

if __name__ == "__main__":
    # Create a server instance（自动连接服务器）
    server = Server()
    server.connect_to_server()

    # Execute a command
    stdin, stdout, stderr = server.ssh_client.exec_command("ls -l")
    print(stdout.read().decode())

    # Upload / Download a file
    # server.sftp_client.put("test/img/000.png", "000.png")
    # server.sftp_client.get("/remote-home/user/test.txt", "test_download.txt")

    # Close the connection
    server.close_connection()