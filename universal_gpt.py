# Please install OpenAI SDK first: `pip3 install openai`

import config
from openai import OpenAI
import logging
from typing import List, Dict, Any, Optional, Union, Callable

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GPTClient:
    """
    GPT客户端类，提供与GPT模型交互的功能，支持多轮对话
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        base_url: Optional[str] = None,
        default_model: str = config.DEFAULT_MODEL,
        default_temperature: float = config.DEFAULT_TEMPORATURE,
        default_system_prompt: str = config.DEFAULT_PROMPT,
        conversation_history_limit: int = config.HISTORY_LIMIT
    ):
        """
        初始化GPT客户端
        
        Args:
            api_key: API密钥，默认使用config中的DEEPSEEK_API_KEY
            base_url: API基础URL，默认使用DeepSeek的URL
            default_model: 默认使用的模型
            default_temperature: 默认温度参数
            default_system_prompt: 默认系统提示
            conversation_history_limit: 对话历史记录的最大消息数量
        """
        self.client = OpenAI(
            api_key=api_key or config.DEEPSEEK_API_KEY,
            base_url=base_url or config.BASE_URL
        )
        
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.default_system_prompt = default_system_prompt
        self.conversation_history_limit = conversation_history_limit
        
        # 初始化会话历史
        self.reset_conversation()
    
    def reset_conversation(self):
        """重置对话历史"""
        self.conversation_history = [
            {"role": "system", "content": self.default_system_prompt}
        ]
    
    def query(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None, 
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        发送查询到GPT模型并获取响应
        
        Args:
            messages: 消息列表，格式为[{"role": "user", "content": "消息内容"}, ...]
            model: 使用的模型名称，默认为self.default_model
            stream: 是否使用流式响应，默认为False
            temperature: 温度参数，控制随机性
            max_tokens: 最大生成token数
            **kwargs: 传递给OpenAI API的其他参数
            
        Returns:
            如果stream=False，返回完整响应对象
            如果stream=True，返回响应流迭代器
        """
        try:
            # 构建请求参数
            request_kwargs = {
                "model": model or self.default_model,
                "messages": messages,
                "stream": stream,
                "temperature": temperature or self.default_temperature,
            }
            
            # 添加可选参数
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens
                
            # 添加其他参数
            request_kwargs.update(kwargs)
            
            # 发送请求
            response = self.client.chat.completions.create(**request_kwargs)
            
            return response
        except Exception as e:
            logger.error(f"GPT API调用失败: {str(e)}")
            raise
    
    def get_response(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        发送单个问题并返回文本响应（不保存到对话历史）
        
        Args:
            prompt: 用户提问内容
            system_prompt: 系统提示，设置AI的行为和角色
            model: 使用的模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            GPT的文本响应
        """
        try:
            sys_prompt = system_prompt or self.default_system_prompt
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}
            ]
            
            response = self.query(
                messages, 
                model=model,
                temperature=temperature, 
                max_tokens=max_tokens,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"获取GPT响应失败: {str(e)}")
            return f"请求失败: {str(e)}"
    
    def stream_response(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        获取流式响应（不保存到对话历史）
        
        Args:
            prompt: 用户提问内容
            system_prompt: 系统提示
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            流式响应迭代器
        """
        sys_prompt = system_prompt or self.default_system_prompt
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt}
        ]
        
        return self.query(
            messages, 
            model=model,
            stream=True, 
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def chat(
        self, 
        message: str, 
        clear_history: bool = False,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        多轮对话，将消息添加到对话历史并获取响应
        
        Args:
            message: 用户消息
            clear_history: 是否清除之前的对话历史
            system_prompt: 系统提示，如果提供则会更新对话历史中的系统提示
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            GPT的文本响应
        """
        # 如果需要清除历史或更新系统提示，重置对话
        if clear_history or (system_prompt and system_prompt != self.conversation_history[0]["content"]):
            self.reset_conversation()
            if system_prompt:
                self.conversation_history[0]["content"] = system_prompt
        
        # 添加用户消息到历史
        self.conversation_history.append({"role": "user", "content": message})
        
        try:
            # 发送请求
            response = self.query(
                self.conversation_history,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # 提取回复内容
            reply = response.choices[0].message.content
            
            # 添加助手回复到历史
            self.conversation_history.append({"role": "assistant", "content": reply})
            
            # 限制历史长度
            if len(self.conversation_history) > self.conversation_history_limit + 1:  # +1 是因为系统提示
                # 保留系统提示，删除最旧的用户/助手消息对
                self.conversation_history = [self.conversation_history[0]] + self.conversation_history[3:]
            
            return reply
        except Exception as e:
            logger.error(f"对话失败: {str(e)}")
            return f"对话失败: {str(e)}"
    
    def stream_chat(
        self, 
        message: str, 
        callback: Optional[Callable[[str], None]] = None,
        clear_history: bool = False,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        流式多轮对话，会将消息添加到对话历史
        
        Args:
            message: 用户消息
            callback: 处理流式输出的回调函数，接收生成内容片段作为参数
            clear_history: 是否清除之前的对话历史
            system_prompt: 系统提示
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            完整的GPT响应文本
        """
        # 如果需要清除历史或更新系统提示，重置对话
        if clear_history or (system_prompt and system_prompt != self.conversation_history[0]["content"]):
            self.reset_conversation()
            if system_prompt:
                self.conversation_history[0]["content"] = system_prompt
        
        # 添加用户消息到历史
        self.conversation_history.append({"role": "user", "content": message})
        
        try:
            # 发送流式请求
            stream_response = self.query(
                self.conversation_history,
                model=model,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # 收集完整回复
            full_response = ""
            
            # 处理流式响应
            for chunk in stream_response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    
                    # 如果提供了回调函数，调用它
                    if callback:
                        callback(content)
            
            # 添加助手回复到历史
            self.conversation_history.append({"role": "assistant", "content": full_response})
            
            # 限制历史长度
            if len(self.conversation_history) > self.conversation_history_limit + 1:  # +1 是因为系统提示
                # 保留系统提示，删除最旧的用户/助手消息对
                self.conversation_history = [self.conversation_history[0]] + self.conversation_history[3:]
            
            return full_response
        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}")
            error_msg = f"流式对话失败: {str(e)}"
            if callback:
                callback(error_msg)
            return error_msg
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取当前对话历史"""
        return self.conversation_history.copy()



# 示例使用
if __name__ == "__main__":
    # 创建GPT客户端
    gpt_client = GPTClient(default_model="deepseek-chat")
    
    # 简单调用示例
    print("=== 单次调用示例 ===")
    response_text = gpt_client.get_response("Hello")
    print(f"GPT响应: {response_text}")
    
    # 多轮对话示例
    print("\n=== 多轮对话示例 ===")
    
    # 第一轮对话
    response1 = gpt_client.chat("你好，我想了解一下人工智能")
    print(f"用户: 你好，我想了解一下人工智能\nGPT: {response1}")
    
    # 第二轮对话
    response2 = gpt_client.chat("它有哪些应用领域？")
    print(f"\n用户: 它有哪些应用领域？\nGPT: {response2}")
    
    # 流式对话示例
    print("\n=== 流式对话示例 ===")
    print("用户: 请给我详细介绍计算机视觉")
    print("GPT: ", end="", flush=True)
    
    def print_chunk(chunk):
        print(chunk, end="", flush=True)
    
    gpt_client.stream_chat("请给我详细介绍计算机视觉", callback=print_chunk)
    print() # 换行