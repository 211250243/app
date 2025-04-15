import json
import os
import time
import requests
import config
from typing import Optional
from PySide6.QtWidgets import QMessageBox, QWidget, QHBoxLayout, QVBoxLayout, QLabel
from utils import LoadingAnimation, ProgressDialog, check_detect_sample_group, check_model_group, is_image, join_path, show_message_box
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap, QPainter, QFont

class HttpServer:        
    # -------------------- 大模型操作 --------------------
    def anomaly_gpt_infer(self, img_list, question = "", normal_img_list = [], history = []):
        """
        使用大模型进行推理

        Args:
            img_list: 待推理图像列表（必填）
            question: 问题（选填）
            normal_img_list: 正常图像列表（选填）
            history: 历史记录（选填）[ 1号图对话记录[[question1, answer11], [question2,answer21],...], 2号图对话记录[[question1, answer12], [question2,answer22],...], ...]

        Returns:
            返回推理结果，同时生成结果图像，后缀是 __1.png （俩下划线）
            结果格式: [
                'The image shows a bottle of mineral water.',
                ...
            ]
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/anomaly_gpt_infer"
        try:
            response = requests.post(url, json={"img_list": img_list, "question": question, "normal_img_list": normal_img_list, "history": history})
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"大模型推理失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"大模型推理失败: {str(e)}")
            raise

    # -------------------- 模型操作 --------------------
    def add_model(self, model):
        """
        添加模型
        
        Args:
            model: {
                "name": 模型名称,
                "input_h": 输入高度,
                "input_w": 输入宽度,
                "end_acc": 结束精度,
                "layers": 层数列表_形如'[layer1, ...]'字符串,
                "patchsize": 补丁大小,
                "embed_dimension": 嵌入维度
            }
            
        Returns:
            新建模型的ID
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/add_model"
        try:
            response = requests.post(url, json=model)
            if response.status_code == 200:
                print(f"添加模型: {model['name']} -> {url}")
                return response.json()
            else:
                raise Exception(f"添加模型失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"添加模型失败: {str(e)}")
            raise
    
    def delete_model(self, model_id):
        """
        删除模型
        
        Args:
            model_id: 模型ID
            
        Returns:
            删除结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/delete_model/{model_id}"
        try:
            response = requests.delete(url)
            if response.status_code == 200:
                print(f"删除模型: {model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"删除模型失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"删除模型失败: {str(e)}")
            raise

    def update_model(self, model_id, model):
        """
        更新模型
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/update_model/{model_id}"
        try:
            response = requests.post(url, json=model)
            if response.status_code == 200:
                print(f"成功更新模型 {model_id} : {model}")
                return response.json()
            else:
                raise Exception(f"更新模型参数失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"更新模型参数失败: {str(e)}")
            raise

    def list_model(self):
        """
        获取模型列表
        
        Returns:
            模型列表：[{
                'id': 模型ID,
                'input_h': 输入高度,
                'input_w': 输入宽度,
                'end_acc': 结束精度,
                'embed_dimension': 嵌入维度,
                'patchsize': 补丁大小,
                'name': 模型名称,
                'layers': 层数列表,
                'status': 状态，0是新建的 1是已经训练中 2是训练结束 3是推理中，推理结束回到原状态
            }]
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/list_model"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"获取模型列表: {url}")
                return response.json()
            else:
                raise Exception(f"获取模型列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取模型列表失败: {str(e)}")
            raise
    
    def get_model_id(self, model_name):
        """
        根据模型名称获取模型ID
        """
        model_list = self.list_model()
        for model in model_list:
            if model.get("name") == model_name:
                print(f"模型名称匹配成功: {model_name} -> {model.get('id')}")
                return model.get("id")
        print(f"http_server无该模型: {model_list}")
        return None    
    
    def get_model(self, model_name):
        """
        根据模型名称获取模型
        """
        model_list = self.list_model()
        for model in model_list:
            if model.get("name") == model_name:
                print(f"获取模型: {model}")
                return model
        print(f"http_server无该模型: {model_list}")
        return None
    
    def get_model_status(self, model_name):
        """
        根据模型名称获取模型状态：0-新建的，1-训练中，2-训练完成，3-推理中
        """
        model_list = self.list_model()
        for model in model_list:
            if model.get("name") == model_name:
                print(f"获取模型状态: {model_name} -> {model.get('status')}")
                return model.get("status")
        print(f"http_server无该模型: {model_list}")
        return None

    def train_model(self, model_id, group_id):
        """
        训练模型
        
        Args:
            model_id: 模型ID
            group_id: 样本组ID
            
        Returns:
            训练任务提交结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/train_model/{model_id}"
        try:
            params = {'group_id': group_id}
            response = requests.post(url, params=params)
            if response.status_code == 200:
                print(f"开始训练模型: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"开始训练模型失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"开始训练模型失败: {str(e)}")
            raise

    def finish_model(self, model_id):
        """
        结束模型训练
        
        Args:
            model_id: 模型ID
            
        Returns:
            结束训练结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/finish_model/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"结束模型训练: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"结束模型训练失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"结束模型训练失败: {str(e)}")
            raise
        
    def train_info(self, model_id):
        """
        获取模型训练完成后的图像列表
        
        Args:
            model_id: 模型ID
            
        Returns:
            已训练的图像列表 ['image1.jpg', 'image2.jpg', ...]
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/train_info/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取已训练的图像列表: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取已训练的图像列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取已训练的图像列表失败: {str(e)}")
            raise

    def train_process(self, model_id):
        """
        获取模型训练实时信息
        
        Args:
            model_id: 模型ID
            
        Returns:
            训练信息 {
                "p_true": 真实样本概率,
                "p_fake": 生成样本概率,
                "loss": 损失,
                "epoch": 当前训练轮数,
                "distance_loss": 距离损失,
                "begin_time": 开始时间,
                "end_time": 结束时间
            }
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/train_process/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取模型训练信息: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取模型训练信息失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取模型训练信息失败: {str(e)}")
            raise

    def infer_model(self, model_id, group_id):
        """
        使用模型进行推理
        
        Args:
            model_id: 模型ID
            group_id: 样本组ID
            
        Returns:
            推理任务提交结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/infer_model/{model_id}"
        try:
            params = {'group_id': group_id}
            response = requests.post(url, params=params)
            if response.status_code == 200:
                print(f"开始模型推理: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"开始模型推理失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"开始模型推理失败: {str(e)}")
            raise

    def infer_info(self, model_id):
        """
        获取模型推理完成后的图像列表（相当于infer_process的最终状态）
        
        Args:
            model_id: 模型ID
            
        Returns: 
            已推理的图像列表：[{
                'id': 所属的样本组ID,
                'bm_score': 边界框得分（无用）,
                'score': 得分,
                'model_id': 模型ID,
                'img_filename': 图像文件名
            }]
            注：推理结果的图像名为原图加后缀，其中_0.png是前景分割图，_1.png是结果图，_2.png是背景过滤后的结果图，_3.png是异常图，_4.png是背景过滤后的异常图
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/infer_info/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取已推理的图像列表: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取已推理的图像列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取已推理的图像列表失败: {str(e)}")
            raise
    
    def infer_process(self, model_id):
        """
        获取模型推理实时信息
        
        Args:
            model_id: 模型ID
            
        Returns:
            推理信息：{
                'inferPercentage': 推理进度,
                'have_infer_img_list': [{
                    'img_filename': 图像文件名,
                    'result_name': 结果图文件名前缀,
                    'score': 得分
                }]
            }
            注：推理结果的图像名为result_name加后缀，其中_0.png是前景分割图，_1.png是结果图，_2.png是背景过滤后的结果图，_3.png是异常图，_4.png是背景过滤后的异常图
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/infer_process/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取模型推理信息: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取模型推理信息失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取模型推理信息失败: {str(e)}")
            raise
    
    def download_result_images(self, origin_name, alias_name, save_path):
        """
        下载五种结果热图：_0.png, _1.png, _2.png, _3.png, _4.png

        Args:
            origin_name: 服务器原图名 xxx-yyy.png
            alias_name: 结果图别名前缀 zzz
            save_path: 保存路径

        Returns:
            xxx-yyy.png -> yyy 本地初始图名
        """
        base_name = os.path.splitext(origin_name)[0].split("-")[-1] # 返回原图名
        for i in range(5):
            result_name = f"{alias_name}_{i}.png"
            rename = f"{base_name}_{i}.png"
            try:
                content = self.download_sample(result_name)
                full_path = join_path(save_path, rename)
                # 确保目录存在，写入
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(content)
                print(f"下载热图成功: {result_name} -> {full_path}")
            except Exception as e:
                print(f"下载热图失败({i}): {str(e)}")
        return base_name


    # -------------------- 样本组操作 --------------------
        
    def upload_sample(self, file_path, group_id: Optional[int]):
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
                params = {'group_id': group_id}
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
        下载样本并保存到指定路径（去掉前缀）
        
        Args:
            filename: 文件名（有前缀，用-连接）
            save_path: 保存路径
            
        Returns:
            保存文件的完整路径
        """
        content = self.download_sample(filename)
        full_path = join_path(save_path, filename.split("-")[-1]) # 去掉前缀
        # 确保目录存在，写入
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

    def clear_group(self, group_id):
        """
        清空组
        
        Args:
            group_id: 组ID
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/clear_group/{group_id}"
        try:
            response = requests.delete(url)
            if response.status_code == 200:
                print(f"清空组: {group_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"清空组失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"清空组失败: {str(e)}")
            raise
    
    def get_group_list(self):
        """
        获取所有组的列表
        
        Returns:
            组列表：[{
                "id": 组ID,
                "group_name": 组名
            }]
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

    def get_group_id(self, group_name):
        """
        根据组名获取组ID
        """
        group_list = self.get_group_list()
        for group in group_list:
            if group.get("group_name") == group_name:
                print(f"组名匹配成功: {group_name} -> {group.get('id')}")
                return group.get("id")
        print(f"http_server无该样本组: {group_list}")
        return None
            

        
def test_sample_api():
    """
    简单测试脚本，测试HTTP服务器API
    测试流程: add_group -> get_group_list -> upload_sample -> get_sample_list -> 
            download_sample -> get_sample_list -> delete_group -> get_group_list
    """

    # 初始化 HttpServer
    server = HttpServer()

    # 0. 准备测试图片
    test_dir = "B:/Development/GraduationDesign/app/test"

    image_dir = join_path(test_dir, "img2")
    test_images = os.listdir(image_dir)

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
    for image in test_images:
        try:
            uploaded_filename = server.upload_sample(join_path(image_dir, image), group_id)
            print(f"上传成功，服务器文件名: {uploaded_filename}")
        except Exception as e:
            print(f"上传失败: {str(e)}")

    # 4. 获取样本列表
    print(f"\n4. 测试获取组 {group_id} 的样本列表")
    samples = server.get_sample_list(group_id)
    print(f"样本列表: {samples}")

    # 5. 下载样本
    print(f"\n5. 测试下载样本 {uploaded_filename}")
    download_dir = os.path.join(test_dir, "downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    for sample in samples:
        downloaded_path = server.save_downloaded_sample(sample, download_dir)
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

def test_model_api():
    """
    测试模型操作相关的API:
    add_model -> list_model -> train_model -> train_info -> train_process -> infer_model -> infer_info -> infer_process -> delete_model -> list_model
    """

    # 初始化 HttpServer
    server = HttpServer()

    # 0. 准备样本
    test_dir = "B:/Development/GraduationDesign/app/test"
    image_dir = join_path(test_dir, "img")
    download_dir = join_path(test_dir, "downloads")
    test_images = os.listdir(image_dir)[:2]
    # 添加组
    group_name = f"测试组-{int(time.time())}"
    group_id = server.add_group(group_name)
    print(f"创建组成功: 名称={group_name}, ID={group_id}")
    # 上传样本
    print(f"\n2. 上传样本到组 {group_id}")
    for image in test_images:
        try:
            server.upload_sample(join_path(image_dir, image), group_id)
        except Exception as e:
            print(f"上传失败: {str(e)}")

    print("======= 开始测试模型操作API =======")

    # 1. 添加模型
    print("\n1. 测试添加模型")
    model_name = f"测试模型-{int(time.time())}"
    layers = "['layer1', 'layer2', 'layer3']"  # 使用前3层特征
    patchsize = 32  # 中等补丁大小
    embed_dimension = 1024  # 中高嵌入维度

    model_id = server.add_model({
        "name": model_name,
        "input_h": 256,
        "input_w": 256,
        "end_acc": 0.5,
        "layers": layers,
        "patchsize": patchsize,
        "embed_dimension": embed_dimension
    })
    print(f"创建模型成功: 名称={model_name}, ID={model_id}")

    # 2. 获取模型列表
    print("\n2. 测试获取模型列表")
    models = server.list_model()
    print(f"模型列表: {models}")
    # 检查新模型是否在列表中
    model_exists = False
    for model in models:
        if model.get("name") == model_name:
            model_id = model.get("id")
            model_exists = True
            break
    if model_exists:
        print(f"在列表中找到新模型，ID: {model_id}")
    else:
        print("警告: 未在列表中找到新添加的模型")
        exit(1)

    # 3. 开始训练模型
    print(f"\n3. 测试开始训练模型 (模型ID: {model_id}, 组ID: {group_id})")
    try:
        train_result = server.train_model(model_id, group_id)
        print(f"----- 开始训练: {train_result} -----")
    except Exception as e:
        print(f"开始训练失败: {str(e)}")

    # 4/5. 获取训练进度，以及训练实时信息
    print(f"\n4/5. 测试获取训练进度，以及训练实时信息 (模型ID: {model_id})")
    # 循环查询训练进度
    while True:
        try:
            # 等待5秒后再次查询
            time.sleep(5)
            train_info = server.train_info(model_id) # 已训练的图像列表，通过其数量除以测试图片总数，得到训练进度
            print(f"已训练的图像列表: {train_info}")
            train_process = server.train_process(model_id)
            print(f"训练实时信息: {train_process}")
            # 如果训练完成，退出循环
            list_model = server.list_model()
            for model in list_model:
                if model.get("id") == model_id:
                    break
            if model.get("status") == 2:
                print(f"\n----- 模型训练结束 (模型ID: {model_id})-----")
                break
        except Exception as e:
            print(f"获取训练信息失败: {str(e)}")
            break

    # 6. 结束训练
    # try:
    #     finish_result = server.finish_model(model_id)
    #     print(f"结束训练: {finish_result}")
    # except Exception as e:
    #     print(f"结束训练失败: {str(e)}")

    # 7. 开始模型推理
    print(f"\n7. 测试开始模型推理 (模型ID: {model_id}, 组ID: {group_id})")
    try:
        infer_result = server.infer_model(model_id, group_id)
        print(f"----- 开始推理: {infer_result} -----")
    except Exception as e:
        print(f"开始推理失败: {str(e)}")

    # 8/9. 获取推理进度，以及推理实时信息
    print(f"\n8/9. 测试获取推理进度，以及推理实时信息 (模型ID: {model_id})")
    # 循环查询推理进度
    while True:
        try:
            # 等待1秒后再次查询
            time.sleep(1)
            infer_info = server.infer_info(model_id)
            print(f"已推理的图像列表: {infer_info}")
            infer_process = server.infer_process(model_id)
            print(f"推理信息: {infer_process}")
            # 如果推理完成，退出循环
            list_model = server.list_model()
            for model in list_model:
                if model.get("id") == model_id:
                    break
            if model.get("status") == 2:
                print(f"\n----- 模型推理结束 (模型ID: {model_id})-----")
                break
        except Exception as e:
            print(f"获取推理信息失败: {str(e)}")
            break
    # 根据infer_info下载热图
    print(f"测试下载热图 (模型ID: {model_id})")
    try:
        for result in infer_info:
            img = result.get("img_filename")
            server.download_result_images(img, download_dir)
        print(f"下载热图结果: {img}")
    except Exception as e:
        print(f"下载{img}的结果热图失败: {str(e)}")

    # # 10. 删除模型和组
    # print(f"\n10. 测试删除模型 (模型ID: {model_id})")
    # try:
    #     result = server.delete_model(model_id)
    #     print(f"删除模型结果: {result}")
    #     result = server.delete_group(group_id)
    #     print(f"删除组结果: {result}")
    # except Exception as e:
    #     print(f"删除模型失败: {str(e)}")

    # 11. 再次获取模型列表
    print("\n11. 再次测试获取模型列表")
    models = server.list_model()
    print(f"模型列表: {models}")
    # 检查模型是否已被删除
    model_exists = False
    for model in models:
        if model.get("id") == model_id:
            model_exists = True
            break
    if model_exists:
        print("警告: 模型删除可能失败，模型仍在列表中")
    else:
        print("模型已成功删除")
        
    print("\n======= 测试完成 =======")



# ----------------------其它功能函数----------------------
def is_sample_group_uploaded(sample_group):
        """
        检查当前样本组是否已上传到服务器
        
        Returns:
            bool: 样本组是否已上传到服务器
        """
        # 首先检查是否存在样本组
        if not sample_group:
            return False
        # 对接 http_server: 检查样本组是否上传
        group_path = join_path(config.SAMPLE_PATH, sample_group)
        try:
            # 连接服务器，检查样本组是否上传（样本数量是否相等）
            http_server = HttpServer()
            group_id = http_server.get_group_id(sample_group)
            if not group_id:
                return False
            # 获取服务器上的样本列表
            sample_list = http_server.get_sample_list(group_id)
            # 获取本地样本数量
            local_count = len(os.listdir(group_path))
            # 样本数量相等或服务器数量更多，则认为已上传
            print(sample_list)
            print(len(sample_list))
            return len(sample_list) >= local_count
        except Exception as e:
            print(f"检查样本组上传状态失败: {str(e)}")
            return False



class UploadSampleGroup_HTTP:
    """
    上传样本组到服务器的线程
    """
    def __init__(self, ui, sample_group):
        self.sample_group = sample_group
        self.group_path = join_path(config.SAMPLE_PATH, sample_group) 
        self.ui = ui

    def run(self):
        # 创建进度条
        progressDialog = ProgressDialog(self.ui, {
            "title": "上传样本",
            "text": "正在上传样本组..."
        })
        progressDialog.show()
        # 获取当前样本组中的所有图片文件
        files = [f for f in os.listdir(self.group_path) if is_image(f)]
        total_files = len(files)
        if total_files == 0:
            show_message_box("警告", "样本组为空，请导入样本", QMessageBox.Warning)
            return
        # 更新进度条文本
        progressDialog.setLabelText(f"正在上传 {total_files} 个文件...")
        # 先清空组，再遍历并上传每个文件
        http_server = HttpServer()
        try:
            group_id = http_server.get_group_id(self.sample_group)
            http_server.clear_group(group_id)
        except Exception as e:
            show_message_box("错误", f"清空组失败: {str(e)}", QMessageBox.Critical)
            return
        for index, file_name in enumerate(files):
            file_path = join_path(self.group_path, file_name)
            # 上传文件，先清空组再上传(覆盖旧样本组)，若失败则停止
            try:
                http_server.upload_sample(file_path, group_id)
            except Exception as e:
                show_message_box("错误", f"上传失败: {str(e)}", QMessageBox.Critical)
                return
            # 更新进度条
            progress = int((index + 1) / total_files * 100)
            progressDialog.setValue(progress)

            

class PatchCoreParamMapper_Http:
    """
    将简化的三个参数（模型精度、缺陷大小和训练速度）映射到HttpServer所需的专业PatchCore训练参数
    """
    def __init__(self):
        # 精度选项
        self.accuracy_options = {
            "低精度": {
                "end_acc": 0.85,
                "embed_dimension": 256,
                "layers": ["layer2"]
            },
            "中等精度": {
                "end_acc": 0.92,
                "embed_dimension": 512,
                "layers": ["layer2", "layer3"]
            },
            "高精度": {
                "end_acc": 0.98,
                "embed_dimension": 1024,
                "layers": ["layer1", "layer2", "layer3"]
            }
        }
        
        # 缺陷大小选项
        self.defect_size_options = {
            "小缺陷": {
                "patchsize": 3,
                "input_h": 224,
                "input_w": 224
            },
            "中等缺陷": {
                "patchsize": 5,
                "input_h": 256,
                "input_w": 256
            },
            "大缺陷": {
                "patchsize": 9,
                "input_h": 320,
                "input_w": 320
            }
        }
        
        # 训练速度选项 - 影响多个参数以全面控制训练性能和质量
        self.training_speed_options = {
            "快速": {
                # 低精度层
                "layers_factor": -1,  # 减少使用的层数
                # 减小嵌入维度以加快训练
                "embed_dimension_factor": 0.7,
                # 降低结束精度要求
                "end_acc_delta": -0.03
            },
            "均衡": {
                # 不修改层数
                "layers_factor": 0,
                # 不修改嵌入维度
                "embed_dimension_factor": 1.0,
                # 不修改结束精度
                "end_acc_delta": 0.0
            },
            "慢速高质量": {
                # 增加使用的层数
                "layers_factor": 1,
                # 增大嵌入维度以提高质量
                "embed_dimension_factor": 1.3,
                # 提高结束精度要求
                "end_acc_delta": 0.02
            }
        }
    
    def get_params(self, accuracy, defect_size, training_speed):
        """
        根据三个简化选项获取完整的HttpServer所需PatchCore参数
        
        Args:
            accuracy: 精度选项，可选值为"低精度"、"中等精度"、"高精度"
            defect_size: 缺陷大小选项，可选值为"小缺陷"、"中等缺陷"、"大缺陷"
            training_speed: 训练速度选项，可选值为"快速"、"均衡"、"慢速高质量"
            
        Returns:
            包含六个必要参数 params：{
                "input_h": 输入高度,
                "input_w": 输入宽度,
                "end_acc": 结束精度,
                "layers": 使用的层数,
                "patchsize": 补丁大小,
                "embed_dimension": 嵌入维度
            }
        """
        # 获取基础参数
        params = {}
        params.update(self.accuracy_options[accuracy])
        params.update(self.defect_size_options[defect_size])
        
        # 应用训练速度对多个参数的影响
        speed_params = self.training_speed_options[training_speed]
        
        # 1. 修改嵌入维度
        params["embed_dimension"] = int(params["embed_dimension"] * speed_params["embed_dimension_factor"])
        
        # 2. 修改层数 - 基于layers_factor
        layers_factor = speed_params["layers_factor"]
        base_layers = params["layers"]
        if layers_factor < 0 and len(base_layers) > 1:
            # 减少层数（保留至少一层）
            params["layers"] = base_layers[-min(len(base_layers), abs(layers_factor)+1):]
        elif layers_factor > 0:
            # 增加层数，可能添加额外的层
            available_layers = ["layer1", "layer2", "layer3", "layer4"]
            # 找出当前未使用的层
            unused_layers = [l for l in available_layers if l not in base_layers]
            # 按顺序添加未使用的层，最多添加layers_factor个
            for i in range(min(layers_factor, len(unused_layers))):
                if unused_layers[i] not in params["layers"]:
                    params["layers"] = [unused_layers[i]] + params["layers"]
        
        # 3. 修改结束精度
        params["end_acc"] = min(0.99, max(0.8, params["end_acc"] + speed_params["end_acc_delta"]))
        
        # 确保嵌入维度在合理范围内
        params["embed_dimension"] = max(128, min(2048, params["embed_dimension"]))
        
        # 将layers列表转换为字符串化的列表表示形式
        if isinstance(params["layers"], list):
            # 格式化为 "['layer1', 'layer2', 'layer3']" 形式
            params["layers"] = str(params["layers"])
            
        # 返回的字典包含必要的六个参数
        print(f"训练参数: {params}")
        return params
    
    def get_all_options(self):
        """获取所有可用的选项"""
        return {
            "accuracy": list(self.accuracy_options.keys()),
            "defect_size": list(self.defect_size_options.keys()),
            "training_speed": list(self.training_speed_options.keys())
        }

class HttpDetectSamples:
    """
    使用HTTP服务器处理样本检测的类
    """
    def __init__(self, ui):
        self.ui = ui
        self.processed_files = set()  # 已处理的文件名集合
        self.http_server = HttpServer()
        self.result_timer = None
        self.model_id = None
        self.group_id = None
        self.save_path = None  # 保存图片的路径

    def disable_ui_controls(self):
        """禁用界面控件"""
        # self.ui.setEnabled(False)
        self.ui.detectList.setEnabled(False)
        self.ui.detectColumn.setEnabled(False)
        self.ui.toolbarWidget.setEnabled(False)

    def enable_ui_controls(self):
        """启用界面控件"""
        # self.ui.setEnabled(True)
        self.ui.detectList.setEnabled(True)
        self.ui.detectColumn.setEnabled(True)
        self.ui.toolbarWidget.setEnabled(True)

    def detect_samples(self):
        """启动检测样本的过程"""
        # 检查是否已选择模型和检测样本组
        if not check_detect_sample_group() or not check_model_group():
            return
        # 检查样本组是否上传到服务器
        if not is_sample_group_uploaded(config.DETECT_SAMPLE_GROUP):
            # 提示用户是否要上传样本组
            confirm = QMessageBox.question(
                self.ui,
                "上传提示",
                "样本组未上传到服务器，是否立即上传？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            # 选择是否上传样本组
            if confirm == QMessageBox.Yes:
                UploadSampleGroup_HTTP(self.ui, config.DETECT_SAMPLE_GROUP).run()
            else:
                return
        # 获取模型ID
        try:
            # 禁用界面控件
            self.disable_ui_controls()
            
            # 加载动画
            self.loading_animation = LoadingAnimation(self.ui)
            self.loading_animation.set_text("正在获取模型ID...")
            self.loading_animation.show()
            self.has_infer_process = False
            
            # 获取模型组ID
            self.model_id = self.http_server.get_model_id(config.MODEL_GROUP)
            if not self.model_id:
                show_message_box("错误", f"未找到模型：{config.MODEL_GROUP}", QMessageBox.Critical)
                self.enable_ui_controls()
                return
            # 获取样本组ID
            self.group_id = self.http_server.get_group_id(config.DETECT_SAMPLE_GROUP)
            if not self.group_id:
                show_message_box("错误", f"未找到样本组：{config.DETECT_SAMPLE_GROUP}", QMessageBox.Critical)
                self.enable_ui_controls()
                return
            
            # 创建保存路径
            self.save_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP)
            os.makedirs(self.save_path, exist_ok=True)
            self.origin_path = join_path(config.SAMPLE_PATH, config.DETECT_SAMPLE_GROUP)
            
            # 清空已处理文件的记录
            self.processed_files.clear()
                
            # 启动推理
            infer_result = self.http_server.infer_model(self.model_id, self.group_id)
            print(f"启动推理结果: {infer_result}")
            
            # 开始定时检查结果
            self.result_timer = QTimer()
            self.result_timer.timeout.connect(self.fetch_new_results)
            self.result_timer.start(1000)  # 每秒检查一次
            
        except Exception as e:
            show_message_box("错误", f"启动检测失败: {str(e)}", QMessageBox.Critical)
            print(f"启动检测失败: {str(e)}")
            self.enable_ui_controls()

    def fetch_new_results(self):
        """获取检测结果"""
        try:
            if not self.model_id:
                return
                
            # 获取推理实时信息
            infer_process = self.http_server.infer_process(self.model_id)
            print(f"infer_process: {infer_process}")
            if not infer_process:
                return
            # 首次获取到推理信息，关闭加载动画
            if not self.has_infer_process:
                self.loading_animation.close()
                self.has_infer_process = True
            # 获取已推理的图像列表
            self.image_list = infer_process.get('have_infer_img_list', [])
            
            # 找出未处理的图像
            for img_info in self.image_list:
                origin_name = img_info.get('img_filename') # 原图名
                alias_name = img_info.get('result_name') # 服务器中结果图的别名前缀
                print(f"alias_name: {alias_name}")
                if not alias_name or origin_name in self.processed_files:
                    continue
                
                # 下载热图（5种不同后缀的结果图）
                try:
                    base_name = self.http_server.download_result_images(origin_name, alias_name, self.save_path)
                    
                    # 准备路径
                    original_path = join_path(self.origin_path, f"{base_name}.png")
                    result_path = join_path(self.save_path, f"{base_name}_1.png")
                    heatmap_path = join_path(self.save_path, f"{base_name}_3.png")
                    
                    # 显示原图，直接使用结果标签（最简单的方法）
                    if os.path.exists(result_path):
                        # 合并三张图为一张图
                        combined_pixmap = self.combine_images(original_path, result_path, heatmap_path)
                        
                        # 显示在原来的resultLabel上
                        self.ui.resultLabel.setPixmap(combined_pixmap)
                        self.ui.resultLabel.setToolTip(f"检测结果保存在: {self.save_path}")
                        
                        # 显示检测信息
                        score = img_info.get('score', 0)
                        
                        # 在结果浏览器中显示详细信息
                        self.ui.resultBrowser.clear()
                        self.ui.resultBrowser.append(f"<b>文件名:</b> {img_info.get('name', '未知')}")
                        self.ui.resultBrowser.append(f"<b>缺陷得分:</b> {score:.4f}")
                        self.ui.resultBrowser.append(f"<b>当前阈值:</b> {config.DEFECT_THRESHOLD:.2f}")
                        
                        # 根据阈值判断状态
                        is_defect = float(score) > config.DEFECT_THRESHOLD
                        status_text = "异常" if is_defect else "正常"
                        status_color = "red" if is_defect else "green"
                        self.ui.resultBrowser.append(f"<b>检测状态:</b> <font color='{status_color}'>{status_text}</font>")
                        self.ui.resultBrowser.append(f"<b>保存位置:</b> {self.save_path}")
                    else:
                        print(f"结果图 {result_path} 不存在")
                    
                    # 标记为已处理
                    self.processed_files.add(origin_name)
                    
                except Exception as e:
                    print(f"处理图片结果失败: {str(e)}")
            
            # 检查推理是否已完成
            infer_percentage = infer_process.get('inferPercentage', 0)
            if infer_percentage >= 1.0:
                # 检查模型状态
                model_status = self.http_server.get_model_status(config.MODEL_GROUP)
                if model_status != 3:  # 不再是推理中状态
                    self.end_detection("检测已完成")
                    
        except Exception as e:
            print(f"获取检测结果失败: {str(e)}")

    def end_detection(self, message="检测已完成"):
        """结束检测过程"""
        if self.result_timer:
            self.result_timer.stop()
            self.result_timer = None
            
        # 启用界面控件
        self.enable_ui_controls()
        
        show_message_box("提示", message, QMessageBox.Information)

        # 将 image_list 存入本地
        result = []
        for image_info in self.image_list:
            # 获取得分
            score = image_info.get('score', 0)
            if isinstance(score, str):
                try:
                    score = float(score)
                except:
                    score = 0.0
            
            # 使用配置的阈值判断是否异常
            is_defect = score > config.DEFECT_THRESHOLD
            status = "异常" if is_defect else "正常"
            
            result.append({
                'file_name': image_info.get('img_filename'),
                'score': score,
                'status': status,
                'alias_name': image_info.get('result_name'),
                'origin_name': image_info.get('img_filename').split('-')[-1]
            })
        
        config.DETECT_LIST = result
        
        # 保存结果到JSON文件
        with open(join_path(self.save_path, "detect_list.json"), "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)

        # 清理
        self.model_id = None
        self.group_id = None

    def combine_images(self, original_path, result_path, heatmap_path):
        """
        将三张图像水平合并为一张图像
        总宽度适应resultLabel宽度，高度按等比例缩放
        并保存合并后的图像
        """
        # 获取resultLabel的宽度
        label_width = self.ui.resultLabel.width()
        
        # 加载三张图像
        pixmaps = []
        titles = ["原图", "检测结果", "热力图"]
        paths = [original_path, result_path, heatmap_path]
        
        # 首先加载所有图像
        for path in paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    # 如果图像加载失败，创建一个空白图像
                    pixmap = QPixmap(200, 200)
                    pixmap.fill(Qt.white)
            else:
                # 如果图像不存在，创建一个空白图像
                pixmap = QPixmap(200, 200)
                pixmap.fill(Qt.white)
            
            pixmaps.append(pixmap)
        
        # 确定每张图像在合并后的宽度比例(相同比例)
        single_width = label_width // 3
        
        # 计算每张图像的缩放比例和最终高度
        max_height = 0
        scaled_pixmaps = []
        
        for pixmap in pixmaps:
            if pixmap.width() > 0:  # 避免除以零错误
                # 计算按宽度缩放的比例
                scale_factor = single_width / pixmap.width()
                # 计算缩放后的高度
                scaled_height = int(pixmap.height() * scale_factor)
                # 缩放图像
                scaled_pixmap = pixmap.scaled(
                    single_width, scaled_height, 
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                max_height = max(max_height, scaled_pixmap.height())
            else:
                scaled_pixmap = pixmap
            
            scaled_pixmaps.append(scaled_pixmap)
        
        # 创建一个足够大的图像来容纳所有图像和标题
        TITLE_HEIGHT = 30  # 标题高度
        result = QPixmap(label_width, max_height + TITLE_HEIGHT)
        result.fill(Qt.white)  # 设置白色背景
        
        # 创建画师
        painter = QPainter(result)
        # 设置字体
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        
        # 绘制所有图像和标题
        x_offset = 0
        for i, pixmap in enumerate(scaled_pixmaps):
            # 计算每个图像的宽度
            img_width = single_width
            
            # 绘制标题
            painter.drawText(
                x_offset, 0, img_width, TITLE_HEIGHT, 
                Qt.AlignCenter, titles[i]
            )
            
            # 垂直居中绘制图像
            y_offset = TITLE_HEIGHT + (max_height - pixmap.height()) // 2
            painter.drawPixmap(x_offset, y_offset, pixmap)
            
            # 更新x偏移
            x_offset += img_width
        
        # 完成绘制
        painter.end()
        
        # 保存合并后的图像
        result_file_path = ''
        if original_path:
            # 从原图路径提取文件名
            base_name = os.path.splitext(os.path.basename(original_path))[0]
            result_file_path = join_path(self.save_path, f"{base_name}_combined.png")
            result.save(result_file_path, "PNG")
            print(f"保存合并图像: {result_file_path}")
        
        return result

if __name__ == "__main__":
    # test_sample_api()
    # test_model_api()

    server = HttpServer()

    # print(server.list_model())
    # group_name = f"测试组-{int(time.time())}"
    # group_id = server.add_group(group_name)
    # print(f"创建组成功: 名称={group_name}, ID={group_id}")

    # server.delete_group(2)
    # # 2. 获取组列表
    # groups = server.get_group_list()
    # print(f"组列表: {groups}")

    # samples = server.get_sample_list(1)
    # print(f"样本列表: {samples}")
    
    # 下载样本组
    download_dir = "B:/Development/GraduationDesign/app/test/downloads"
    server.save_downloaded_sample('000__1.png', download_dir)

    # 删除样本组
    # server.clear_group(1)
    # for group in groups:
    #     server.delete_group(group.get("id"))



# 训练实时信息train_process: {'p_true': [0.40771484375, 0.3984375, 0.287841796875, 0.3447265625, 0.2747802734375, 0.2491455078125, 0.2037353515625, 0.146728515625, 0.1463623046875, 0.1300048828125, 0.086181640625, 0.0740966796875, 0.0496826171875, 0.0281982421875, 0.026611328125, 0.03955078125, 0.0440673828125, 0.045166015625, 0.0345458984375, 0.021484375, 0.0177001953125, 0.0203857421875, 0.021240234375, 0.0169677734375, 0.0159912109375, 0.0120849609375, 0.0101318359375, 0.007080078125, 0.0048828125, 0.0081787109375, 0.0166015625, 0.0146484375, 0.0081787109375, 0.002685546875, 0.0018310546875, 0.0013427734375, 0.00146484375, 0.00244140625, 0.0037841796875, 0.005126953125, 0.0050048828125, 0.0045166015625, 0.0040283203125, 0.003173828125, 0.002197265625, 0.001708984375, 0.00146484375, 0.00146484375, 0.0006103515625, 0.001220703125, 0.001708984375, 0.0023193359375, 0.0030517578125, 0.0028076171875, 0.0010986328125], 'p_fake': [0.1591796875, 0.208251953125, 0.1669921875, 0.1199951171875, 0.1175537109375, 0.1151123046875, 0.113037109375, 0.076416015625, 0.0892333984375, 0.1064453125, 0.0814208984375, 0.085693359375, 0.10107421875, 0.11865234375, 0.1103515625, 0.094482421875, 0.0733642578125, 0.05712890625, 0.0394287109375, 0.0302734375, 0.0322265625, 0.0428466796875, 0.0433349609375, 0.03515625, 0.03076171875, 0.01806640625, 0.0157470703125, 0.01513671875, 0.0111083984375, 0.01220703125, 0.013427734375, 0.013671875, 0.01171875, 0.0078125, 0.005859375, 0.0050048828125, 0.0054931640625, 0.0054931640625, 0.00537109375, 0.0042724609375, 0.00341796875, 0.00341796875, 0.0025634765625, 0.0025634765625, 0.0018310546875, 0.0028076171875, 0.00390625, 0.0048828125, 0.004638671875, 0.0052490234375, 0.0048828125, 0.0050048828125, 0.0048828125, 0.0068359375, 0.0054931640625], 'loss': [], 'epoch': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55], 'distance_loss': [], 'begin_time': 1743310973.1871567, 'end_time': 1743310981.645206}

# 推理实时信息infer_process: {'inferPercentage': 1.0, 'have_infer_img_list': [{'name': '9f91f2f7-9035-4a27-b2e0-8374225441ff.png', 'score': -0.4169386327266693}, {'name': '652b745f-1903-42fb-a6c9-30d4f4434316.png', 'score': -0.4127034544944763}]}

# 已推理的图像列表infer_info: [{'id': 1, 'bm_score': 2.0059027671813965, 'score': -0.4169386327266693, 'model_id': 4, 'img_filename': '09d7fbc2-8e66-42e0-aa70-bba7d3c4f06d-000.png'}, {'id': 2, 'bm_score': 2.010138511657715, 'score': -0.4127034544944763, 'model_id': 4, 'img_filename': '6eb1cc47-820c-425e-9806-a53c19a9eea1-001.png'}]