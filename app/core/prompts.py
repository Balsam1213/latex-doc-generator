"""提示词工程：系统提示词、文档类型骨架模板（few-shot）、修复提示词。

免费档模型能力有限，这里用「硬性约束 + 骨架模板 + 编译反馈修复」三层手段，
尽量保证产出可直接编译的完整文档。
"""

SYSTEM_PROMPT = r"""你是一位资深 LaTeX 排版专家，根据用户需求生成可以直接编译通过的 LaTeX 文档。你必须严格遵守：

1. 只输出一个 ```latex 代码块，代码块之外不要输出任何解释、前言或道歉。
2. 代码必须是完整文档：以 \documentclass 开头，以 \end{document} 结尾。
3. 只允许使用这些常见宏包（按需选用）：ctex、amsmath、amssymb、amsthm、graphicx、booktabs、longtable、array、multirow、geometry、hyperref、xcolor、enumitem、titlesec、fancyhdr、caption、subcaption、listings、tikz、siunitx。禁止使用需要调用外部程序的宏包（如 minted）。
4. 不要引用任何外部文件：不要用 \includegraphics 引用不存在的图片（需要示意图时用 TikZ 绘制，或改用表格/文字描述），不要 \input 或 \include 其他文件，参考文献直接写在 thebibliography 环境中，不要引用 .bib 文件。
5. 中文内容必须使用 ctex 文档类（ctexart/ctexrep/ctexbook/ctexbeamer），不要用 article 配合 CJK 宏包。
6. 编译引擎是 XeTeX，不要使用 pdfTeX 专有命令；字体交给 ctex 默认设置即可，不要手动指定生僻字体。
7. 数学公式用标准 LaTeX 语法，表格用 booktabs 三线表，整体结构清晰、缩进规范。
8. 内容要专业充实：用户指定了篇幅就按要求写；没指定篇幅就写一篇结构完整、内容详实的文档。
9. 如果用户的需求与 LaTeX 文档无关，也要尽力把它组织成一篇文档（如说明、总结），仍按上述格式输出。"""

FIX_SYSTEM_PROMPT = r"""你是 LaTeX 编译错误修复专家。用户会提供一份完整的 LaTeX 源码和编译器（XeTeX）输出的错误日志，你的任务是修复问题，让文档编译通过。

规则：
1. 只输出一个 ```latex 代码块，内容是修复后的【完整】文档（从 \documentclass 到 \end{document}）。不要只输出修改的片段，不要输出解释。
2. 优先处理错误日志指向的问题；日志中靠前的错误通常最关键。
3. 若错误由某个宏包或命令不存在导致，改用常见宏包的等价写法。
4. 不要删减文档内容，保持原有结构与信息完整。"""

# ---------- 各文档类型的骨架模板（few-shot 注入） ----------

_S_REPORT_ZH = r"""\documentclass[UTF8,fontset=windows,12pt]{ctexart}
\usepackage{amsmath,amssymb,graphicx,booktabs,longtable,geometry,hyperref}
\geometry{a4paper,margin=2.5cm}
\title{文档标题}
\author{作者名}
\date{\today}
\begin{document}
\maketitle
\begin{abstract}
这里是摘要。
\end{abstract}
\tableofcontents
\section{一级标题}
正文内容，行内公式如 $E=mc^2$，独立公式如：
\[ \int_{-\infty}^{+\infty} e^{-x^2}\,dx = \sqrt{\pi} \]
\subsection{二级标题}
三线表示例：
\begin{table}[htbp]
  \centering
  \caption{示例表格}
  \begin{tabular}{lcc}
    \toprule
    项目 & 数值一 & 数值二 \\
    \midrule
    示例A & 1.0 & 2.0 \\
    示例B & 3.0 & 4.0 \\
    \bottomrule
  \end{tabular}
\end{table}
\end{document}"""

_S_PAPER_EN = r"""\documentclass[11pt]{article}
\usepackage{amsmath,amssymb,amsthm,graphicx,booktabs,geometry,hyperref}
\geometry{a4paper,margin=1in}
\title{Paper Title}
\author{Author Name}
\date{\today}
\begin{document}
\maketitle
\begin{abstract}
This paper studies ...
\end{abstract}
\section{Introduction}
...
\section{Methodology}
...
\section{Experiments}
...
\section{Conclusion}
...
\begin{thebibliography}{9}
\bibitem{ref1} Author A. Paper title. Journal Name, 2024.
\end{thebibliography}
\end{document}"""

_S_RESUME = r"""\documentclass[UTF8,fontset=windows,10.5pt]{ctexart}
\usepackage[a4paper,margin=1.8cm]{geometry}
\usepackage{titlesec,xcolor,enumitem}
\definecolor{main}{RGB}{0,82,155}
\titleformat{\section}{\Large\bfseries\color{main}}{}{0em}{}[\titlerule]
\titlespacing{\section}{0pt}{10pt}{6pt}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\begin{document}
{\Huge\bfseries 姓名}\hfill {\large 电话：138-0000-0000 \quad 邮箱：me@example.com}
\vspace{4pt}

{\color{main}\rule{\textwidth}{1.2pt}}
\section{教育背景}
\textbf{某某大学} \hfill 某某专业 · 本科 \hfill 2020.09 -- 2024.06

主修课程：课程一、课程二、课程三
\section{技能特长}
\begin{itemize}[leftmargin=1.5em]
  \item 熟练掌握：……
  \item 了解：……
\end{itemize}
\section{项目经历}
\textbf{项目名称} \hfill 2023.06 -- 2023.12

\begin{itemize}[leftmargin=1.5em]
  \item 负责……，实现了……，效果……
\end{itemize}
\end{document}"""

_S_LETTER = r"""\documentclass[UTF8,fontset=windows,12pt]{ctexart}
\usepackage[a4paper,margin=2.5cm]{geometry}
\pagestyle{empty}
\setlength{\parindent}{2em}
\begin{document}
\begin{flushright}
写信人姓名\\
单位 / 地址\\
\today
\end{flushright}

\vspace{1em}
\noindent 尊敬的某某先生/女士：

您好！

\hspace{2em}（正文第一段，说明写信目的……）

\hspace{2em}（正文第二段，展开具体内容……）

\vspace{2em}
\begin{flushright}
此致

敬礼！

写信人姓名\\
\today
\end{flushright}
\end{document}"""

_S_SLIDES = r"""\documentclass[fontset=windows,aspectratio=169]{ctexbeamer}
\usetheme{Madrid}
\title{演示标题}
\subtitle{副标题}
\author{演讲人}
\institute{单位}
\date{\today}
\begin{document}
\maketitle
\begin{frame}{目录}
  \tableofcontents
\end{frame}
\section{第一部分}
\begin{frame}{帧标题}
  \begin{itemize}
    \item 要点一
    \item 要点二
  \end{itemize}
\end{frame}
\begin{frame}{公式示例}
  \[ \hat{f}(x) = \sum_{i=1}^{n} \alpha_i k(x_i, x) \]
\end{frame}
\end{document}"""

DOC_TYPES: dict[str, dict] = {
    "auto": {"label": "智能判断", "skeleton": None},
    "report_zh": {"label": "中文文章 / 报告", "skeleton": _S_REPORT_ZH},
    "paper_en": {"label": "英文学术论文", "skeleton": _S_PAPER_EN},
    "resume": {"label": "个人简历", "skeleton": _S_RESUME},
    "letter": {"label": "信件", "skeleton": _S_LETTER},
    "slides": {"label": "幻灯片 (Beamer)", "skeleton": _S_SLIDES},
}


def build_user_prompt(prompt: str, doc_type: str) -> str:
    info = DOC_TYPES.get(doc_type, DOC_TYPES["auto"])
    parts = [f"【文档类型】{info['label']}"]
    if info["skeleton"]:
        parts.append(
            "【参考骨架】请按以下模板的结构组织文档（内容按用户需求替换，"
            "宏包可按需增删，但必须保持可直接编译）：\n```latex\n"
            + info["skeleton"] + "\n```"
        )
    if doc_type == "auto":
        parts.append(
            "【语言判断】若需求是中文内容，使用 ctexart 等中文文档类；"
            "若为纯英文内容则使用 article。"
        )
    parts.append(f"【需求描述】\n{prompt.strip()}")
    return "\n\n".join(parts)


def build_fix_prompt(tex: str, error_log: str) -> str:
    return (
        "【当前 LaTeX 源码】\n```latex\n" + tex + "\n```\n\n"
        "【编译错误日志】\n```\n" + error_log + "\n```\n\n"
        "请输出修复后的完整文档。"
    )


# ---------- PDF → LaTeX 转换 ----------

CONVERT_SYSTEM_PROMPT = r"""你是 PDF→LaTeX 转换专家。用户提供一份从 PDF 提取的纯文本，请你将其重建为一份结构对应的 LaTeX 文档。

要求：
1. 只输出一个 ```latex 代码块，为完整可编译文档（从 \documentclass 到 \end{document}）。
2. 尽量还原原文结构：标题层级、章节、列表、表格（用 booktabs 三线表重建）、数学公式（用 LaTeX 语法重写）。
3. 图片无法还原：在对应位置用注释「% 原文此处有图：…」或 \fbox 占位框说明，禁止引用外部图片文件。
4. 中文内容使用 ctexart 文档类，纯英文用 article；编译引擎为 XeTeX。
5. 只使用常见宏包（ctex、amsmath、amssymb、graphicx、booktabs、longtable、geometry、hyperref、xcolor、enumitem 等）。
6. 忠实于原文内容，不要增删观点；原文提取乱码或缺失处用 [?] 标注。
7. 这是对 PDF 的近似重建，无法与原版式完全一致，请优先保证内容完整、结构清晰、可编译。"""


def build_convert_prompt(pdf_text: str) -> str:
    return (
        "【从 PDF 提取的文本内容】\n```\n" + pdf_text + "\n```\n\n"
        "请将其重建为对应的 LaTeX 文档。"
    )


# ---------- 附件（上传文件/图片）相关提示词 ----------

VISION_PROMPT = """请分两部分输出对这张图片的描述：
1）格式特征：如果这是文档、试卷、论文、幻灯片、笔记等版面截图，请描述其版式与格式：标题层级与样式、是否编号、段落组织、列表/表格/公式的排版方式、页眉页脚、整体风格等。
2）内容转录：完整转录图中出现的文字（保持层级结构）；数学公式用 LaTeX 语法转录；表格逐行转录（用「列1：…；列2：…」形式）；如有图形请说明其表达的信息。
如果这不是版面截图而是照片或示意图，则跳过第 1 部分，直接详细描述图中可见的内容与信息。"""

_ATTACHMENT_PURPOSE_NOTES = {
    "auto": "附件既可作为内容素材与事实依据，也可借鉴其结构与排版风格；若附件本身是格式示范（如 LaTeX 源码或版面截图），请优先模仿其格式，内容按用户需求撰写。",
    "format": "只参考附件的格式、结构与排版风格，不要照搬附件中的具体内容；生成的内容以用户需求描述为准。",
    "content": "附件仅作为内容素材与事实依据使用，与其冲突时以附件为准；不必模仿附件的格式。",
}


def build_attachment_section(purpose: str, parts: list[tuple[str, str, str]]) -> str:
    """把各附件的处理结果拼成提示词段落。parts: [(类别标签, 文件名, 文本), ...]"""
    if not parts:
        return ""
    blocks = []
    for label, name, text in parts:
        blocks.append(f"### {label}——《{name}》\n```\n{text}\n```")
    note = _ATTACHMENT_PURPOSE_NOTES.get(purpose, _ATTACHMENT_PURPOSE_NOTES["auto"])
    return (
        f"【附件参考资料】以下是用户上传附件的处理结果，共 {len(parts)} 份。\n"
        f"使用原则：{note}\n"
        "另外：若参考的 LaTeX 源码中含有 \\includegraphics、\\input 等外部文件引用，"
        "必须以等价方式替代（如 TikZ 绘制、直接写内容或删除），不得引用不存在的文件。\n\n"
        + "\n\n".join(blocks)
    )
