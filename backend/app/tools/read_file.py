import logging
import os

from langchain_core.tools import tool
from app.services.file_parser import extract_text_from_file

logger = logging.getLogger(__name__)


@tool
def read_file(file_path: str) -> str:
    """Read the content of a local PDF or Word document.

    Args:
        file_path: The absolute path to the file to read.

    Returns:
        The extracted text content from the file.
    """
    logger.info("read_file called: path=%s", file_path)
    if not os.path.exists(file_path):
        logger.warning("read_file: file not found: %s", file_path)
        return f"文件不存在: {file_path}"

    # Security: restrict to upload directory
    allowed_base = os.path.abspath("data/uploads")
    abs_path = os.path.abspath(file_path)
    if not abs_path.startswith(allowed_base):
        logger.warning("read_file blocked: path=%s outside allowed base=%s", abs_path, allowed_base)
        return "访问被拒绝：文件路径超出允许范围"

    try:
        text = extract_text_from_file(file_path)
        logger.info("read_file success: extracted %d chars from %s", len(text), file_path)
        return text
    except Exception as e:
        logger.exception("read_file failed for path=%s", file_path)
        return f"读取文件失败: {str(e)}"
