"""`/api/ai/*` 的四个 router。

011 §5 裁定走 A：ai 领域拆成**子包**而不是一个文件。原因是算出来的，不是偏好——
`api_ai_question` 一个函数就 433 行，六组平拆的话 ai 组无论怎么分派职责都过不了
< 500 行。代价照记：ai 从此是一个目录，计划 §6 写的「六组」在**实现文件**这一层
变成七个上下；`routers/__init__.py` 里那条「绑模块不绑属性」的规矩在这里同样适用，
只是相对导入要多一层（`from ... import server as _server`）。

  chat.py           问答 + SSE 流。**带着唯一一条具名、可到期的行数豁免（≤ 560）。**
  conversations.py  会话读写／删除／导出。
  summary.py        整本与多章摘要。
  rag.py            只做检索，不碰 provider。

出口分布（ADR-0006）：chat.py 与 summary.py 各有真实的 LLM 出口，
conversations.py 与 rag.py 没有。别在后两个文件里新增 provider 调用。
"""
