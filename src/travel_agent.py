import os
import json
import logging
import requests
from openai import OpenAI

# ==========================================
# 配置日志记录器（仅输出到日志文件，如果不需要可以注释）
# ==========================================
logger = logging.getLogger("api_logger")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("travel_agent.log", encoding="utf-8")
formatter = logging.Formatter('%(asctime)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# ==========================================
# 加载配置文件
# ==========================================
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return {}

config = load_config()
AMAP_API_KEY = config.get("amap_api_key", "")

# ==========================================
# 1. 纯 Python 工具函数定义
# ==========================================
def get_location_by_ip(ip: str = "") -> str:
    if not AMAP_API_KEY:
        return "错误: 请在 config.json 中配置高德地图 API Key"
    
    url = "https://restapi.amap.com/v3/ip"
    params = {
        "key": AMAP_API_KEY,
        "output": "json"
    }
    if ip:
        params["ip"] = ip
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "1":
            result = {
                "省份": data.get("province", ""),
                "城市": data.get("city", ""),
                "行政区划代码": data.get("adcode", ""),
                "矩形区域": data.get("rectangle", "")
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return f"定位失败: {data.get('info', '未知错误')}"
    except Exception as e:
        return f"请求失败: {str(e)}"

# 工具映射字典，为了通过字符串名字能调用到对象
tools_map = {
    "get_location_by_ip": get_location_by_ip
}

# ==========================================
# 2. 定义 OpenAI 格式的 Tools Schema
# ==========================================
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_location_by_ip",
            "description": "根据IP地址获取地理位置信息（省份、城市等），如果不指定IP则获取当前请求IP的位置",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {
                        "type": "string",
                        "description": "要查询的IP地址，可选，不填则使用当前请求IP"
                    }
                },
                "required": []
            }
        }
    }
]

# ==========================================
# 3. 主程序与 OpenAI 原生 Agent 循环
# ==========================================
if __name__ == "__main__":
    # 初始化原生 OpenAI Client
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY") or config.get("api_key", ""),
        base_url=os.getenv("OPENAI_BASE_URL") or config.get("base_url", "https://api.deepseek.com")
    )

    print("=" * 60)
    print("旅行 Agent - 带定位功能")
    print("=" * 60)
    
    user_input = input("请输入你的需求：\n").strip()
    
    if not user_input:
        print("需求不能为空！")
        exit()

    print(f"\n用户输入：\n{user_input}")
    print("\n" + "="*60)
    print("处理中...")
    print("="*60)

    # 维护上下文数组 (即历史记录)
    messages = [
        {"role": "system", "content": "你是一个旅行助手，能够帮助用户查询地理位置信息。你可以使用 get_location_by_ip 工具来获取IP地址对应的位置信息。"},
        {"role": "user", "content": user_input}
    ]

    while True:
        # 向 DeepSeek 发起请求：附加 extra_body 开启 thinking
        logger.info(f"发起请求，当前 messages 长度: {len(messages)}")
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            tools=tools_schema,
            extra_body={"thinking": {"type": "enabled"}}
        )

        msg = response.choices[0].message
        
        messages.append(msg)

        # 把它正在思考的过程打印出来给用户看
        if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            print(f"\n[思考过程]: {msg.reasoning_content}")
            logger.info("本轮思考过程: " + msg.reasoning_content)

        # 检查是否调用了工具
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                print(f"\n调用工具: {func_name}\n参数: {args}")
                
                func = tools_map.get(func_name)
                if func:
                    func_result = func(**args)
                else:
                    func_result = f"找不到工具 {func_name}"
                
                logger.info(f"工具返回: {func_result}")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(func_result)
                })
        else:
            final_content = msg.content
            print("\n" + "="*60)
            print("最终回复：")
            print("="*60)
            print(final_content)
            break
