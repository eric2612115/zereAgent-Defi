# backend/message_structure.py
from typing import Dict, Any
from uuid import uuid4
from datetime import datetime

class MessageStructure:
    """
    統一訊息格式的工具類別。
    """

    @staticmethod
    def format_message(sender: str, text: str, message_type: str = "normal") -> Dict[str, Any]:
        """
        格式化一般訊息。
        """
        return {
            "id": str(uuid4()),
            "sender": sender,
            "text": text,
            "message_type": message_type,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def format_thinking(text: str) -> Dict[str, Any]:
        """
        格式化 AI 思考中的訊息。
        """
        return MessageStructure.format_message("agent", text, "thinking")

    @staticmethod
    def format_status(text: str) -> Dict[str, Any]:
        """
        格式化狀態更新訊息。
        """
        return MessageStructure.format_message("agent", text, "status")

    @staticmethod
    def format_error(text: str) -> Dict[str, Any]:
        """
        格式化錯誤訊息。
        """
        return MessageStructure.format_message("agent", text, "error")

    @staticmethod
    def format_transaction(text: str) -> Dict[str, Any]:
        """
        格式化交易相關訊息。
        """
        return MessageStructure.format_message("agent", text, "transaction")


    @staticmethod
    def format_ai_response(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化 AI 的最終回覆 (可以是文字或結構化資料, 例如推薦)。
        """
        return {
            "id": str(uuid4()),
            "sender": "agent",
            "text": data,  # 可以是文字訊息，也可以是包含結構化資料的字典
            "message_type": "normal",  # 或者根據需要使用 "recommendation" 等其他類型
            "timestamp": datetime.now().isoformat()
        }