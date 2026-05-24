import os

from langchain_core.tools import tool
from app.services.file_parser import extract_text_from_file


@tool
def read_file(file_path: str) -> str:
    """Read the content of a local PDF or Word document.

    Args:
        file_path: The absolute path to the file to read.

    Returns:
        The extracted text content from the file.
    """
    if not os.path.exists(file_path):
        return f"文件不存在: {file_path}"

    # Security: restrict to upload directory
    allowed_base = os.path.abspath("data/uploads")
    abs_path = os.path.abspath(file_path)
    if not abs_path.startswith(allowed_base):
        return "访问被拒绝：文件路径超出允许范围"

    try:
        text = extract_text_from_file(file_path)
        return text
    except Exception as e:
        return f"读取文件失败: {str(e)}"
