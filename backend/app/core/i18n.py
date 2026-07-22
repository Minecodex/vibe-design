from fastapi import Request
from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "资源不存在": "Resource not found",
        "资源已存在": "Resource already exists",
        "未授权": "Unauthorized access",
        "权限不足": "Insufficient permissions",
        "无效的认证凭据": "Invalid credentials",
        "邮箱或密码错误": "Incorrect email or password",
        "用户不存在": "User not found",
        "项目不存在": "Project not found",
        "项目不存在或无权限": "Project not found or unauthorized",
        "无权访问该项目": "Not authorized to access this project",
        "不能删除其他成员添加的素材，除非您是项目创建者": "Cannot delete assets you did not add unless you are the project creator",
        "对话不存在": "Conversation not found",
        "计划不存在": "Plan not found",
        "计划状态不允许执行": "Plan status does not allow execution",
        "当前没有待回答的问题": "No pending questions to answer",
        "系统错误": "System error",
        # Default pydantic translations if necessary
        "field required": "Field required",
        "value is not a valid email address": "Invalid email address",
    }
}

def translate_msg(msg: str, lang: str) -> str:
    if "en" in lang.lower():
        # Fallback to English translation mapping
        return TRANSLATIONS["en"].get(msg, msg)
    return msg

def get_lang(request: Request) -> str:
    return request.headers.get("accept-language", "zh")
