"""从编译日志中提取对模型有用的错误信息（喂给修复提示词用）。"""


def extract_errors(log: str, max_chars: int = 3500) -> str:
    """抓取以「!」或「error:」开头的错误块；抓不到就返回日志末尾。"""
    lines = log.splitlines()
    picked: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("!") or line.startswith("error:"):
            block = [line]
            j = i + 1
            while j < len(lines) and len(block) < 8:
                nxt = lines[j]
                if nxt.startswith("!") or nxt.startswith("error:"):
                    break
                block.append(nxt)
                j += 1
            picked.append("\n".join(block))
            i = j
        else:
            i += 1

    text = "\n\n".join(picked)
    if not text.strip():
        text = "\n".join(lines[-40:])
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（日志过长，已截断）"
    return text
