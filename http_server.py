import os
import time
import requests
import config
from typing import Optional

from utils import join_path


class HttpServer:        
        
    def upload_sample(self, file_path, group_id: Optional[int] = None):
        """
        通过HTTP接口上传单个文件
        
        Args:
            file_path: 文件路径
            group_id: 组ID，可选
        
        Returns:
            上传文件的文件名
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/upload_sample"
        try:
            with open(file_path, 'rb') as f:
                filename = os.path.basename(file_path)
                files = {'file': (filename, f, 'image/jpeg')}
                
                # 添加组ID参数作为URL参数，而不是表单数据
                params = {}
                if group_id is not None:
                    params['group_id'] = group_id
                
                response = requests.post(url, files=files, params=params)
                
                if response.status_code == 200:
                    print(f"上传文件: {file_path} -> {url}")
                    return response.json()["filename"]
                else:
                    raise Exception(f"上传文件失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"上传文件失败: {str(e)}")
            raise

    def get_sample_list(self, group_id):
        """
        获取指定组的样本名列表
        
        Args:
            group_id: 组ID
            
        Returns:
            样本名称列表
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/get_sample_list/{group_id}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"获取样本列表: {url}")
                return response.json()
            else:
                raise Exception(f"获取样本列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取样本列表失败: {str(e)}")
            raise

    def download_sample(self, filename):
        """
        下载样本文件
        
        Args:
            filename: 文件名
            
        Returns:
            文件内容的二进制数据
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/download_sample"
        try:
            response = requests.get(url, json={"filename": filename})
            if response.status_code == 200:
                print(f"下载样本: {filename} -> {url}")
                return response.content  # 返回二进制内容而不是JSON
            else:
                raise Exception(f"下载样本失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"下载样本失败: {str(e)}")
            raise
            
    def save_downloaded_sample(self, filename, save_path):
        """
        下载样本并保存到指定路径
        
        Args:
            filename: 文件名
            save_path: 保存路径
            
        Returns:
            保存文件的完整路径
        """
        content = self.download_sample(filename)
        full_path = os.path.join(save_path, filename)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'wb') as f:
            f.write(content)
        
        return full_path

    def add_group(self, group_name):
        """
        添加组
        
        Args:
            group_name: 组名
            
        Returns:
            新建组的ID
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/add_group"
        try:
            response = requests.post(url, json={"group_name": group_name})
            if response.status_code == 200:
                print(f"添加组: {group_name} -> {url}")
                return response.json()
            else:
                raise Exception(f"添加组失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"添加组失败: {str(e)}")
            raise

    def delete_group(self, group_id):
        """
        删除组
        
        Args:
            group_id: 组ID
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/delete_group/{group_id}"
        try:
            response = requests.delete(url)
            if response.status_code == 200:
                print(f"删除组: {group_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"删除组失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"删除组失败: {str(e)}")
            raise
    
    def get_group_list(self):
        """
        获取所有组的列表
        
        Returns:
            组列表
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/get_group_list"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"获取组列表: {url}")
                return response.json()
            else:
                raise Exception(f"获取组列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取组列表失败: {str(e)}")
            raise
        

if __name__ == "__main__":
    """
    简单测试脚本，测试HTTP服务器API
    测试流程: add_group -> get_group_list -> upload_sample -> get_sample_list -> 
            download_sample -> get_sample_list -> delete_group -> get_group_list
    """

    # 初始化 HttpServer
    server = HttpServer()

    # 0. 准备测试图片
    test_dir = "B:/Development/GraduationDesign/app/test"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    test_image = join_path(test_dir, "test_image.png")
    if not os.path.exists(test_image):
        print(f"测试图片不存在: {test_image}")
        exit()

    print("======= 开始测试 HttpServer API =======")

    # 1. 添加组
    print("\n1. 测试添加组")
    group_name = f"测试组-{int(time.time())}"
    group_id = server.add_group(group_name)
    print(f"创建组成功: 名称={group_name}, ID={group_id}")

    # 2. 获取组列表
    print("\n2. 测试获取组列表")
    groups = server.get_group_list()
    print(f"组列表: {groups}")

    # 3. 上传样本
    print(f"\n3. 测试上传样本到组 {group_id}")
    uploaded_filename = server.upload_sample(test_image, group_id)
    print(f"上传成功，服务器文件名: {uploaded_filename}")

    # 4. 获取样本列表
    print(f"\n4. 测试获取组 {group_id} 的样本列表")
    samples = server.get_sample_list(group_id)
    print(f"样本列表: {samples}")

    # 5. 下载样本
    print(f"\n5. 测试下载样本 {uploaded_filename}")
    download_dir = os.path.join(test_dir, "downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    downloaded_path = server.save_downloaded_sample(uploaded_filename, download_dir)
    print(f"下载成功，保存路径: {downloaded_path}")

    # 6. 再次获取样本列表
    print(f"\n6. 再次测试获取组 {group_id} 的样本列表")
    samples = server.get_sample_list(group_id)
    print(f"样本列表: {samples}")

    # 7. 删除组
    print(f"\n7. 测试删除组 {group_id}")
    result = server.delete_group(group_id)
    print(f"删除组结果: {result}")

    # 8. 再次获取组列表
    print("\n8. 再次测试获取组列表")
    groups = server.get_group_list()
    print(f"组列表: {groups}")

    print("\n======= 测试完成 =======") 
