import subprocess
import shutil


class InputMethod:
    """使用 xdotool 模拟键盘输入文本"""

    def __init__(self):
        self._xdotool = shutil.which("xdotool")

    def is_available(self) -> bool:
        return self._xdotool is not None

    def type_text(self, text: str):
        if not text or not self._xdotool:
            return
        subprocess.run(
            [self._xdotool, "type", "--clearmodifiers", "--", text],
            check=False,
            capture_output=True,
        )


input_method = InputMethod()
