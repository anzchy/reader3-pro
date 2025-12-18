## 在 AI chat 界面增加功能：

1.用户在每个书籍聊天（用 ollama 或其他 Ai Provider回复）记录对应的文件保存在哪里？

2.此外，新增聊天对话窗口（new chat），当新增窗口后，保留历史对话记录，避免一个对话窗口中聊天数量太多，挤占 Context。

3.结构化保存每一次对话记录，最好以 JSON 格式存储到对应书籍 data 文件夹（如 dracula_data）中。

![image-20251218223550993](https://picbox-1313243162.cos.ap-nanjing.myqcloud.com/typora/image-20251218223550993.png)





## library 界面重塑

Library 界面描述：左边侧边栏有按照文档类型来展示 pdf/epub/ all books 的数量。然后下方有 collection，可以按照作者或者一个主题来将多个 epub 电子书选中加入对应 collections 中。

中间展示所有的电子书的封面。

右边分别有几个切换按钮，在右下角，分别是 Dashboard，Chat，Search

- Dashboard: 显示 Books电子书数量，Indexed 过的电子书数量及 index 的比例。Sections 指所有的书划分成了多少个章节。Chunks 指 RAG 处理后合计有多少个 chunks。右下角有几个按钮，

- Chat：可以选择 all books，也可以选择单个书籍，或者某个 collection 进行一类主题的书籍的聊天

- Search指 cross-book search，之前已经实现过，支持 keyword search，semantic search，或者混合搜索模式。

![img](https://picbox-1313243162.cos.ap-nanjing.myqcloud.com/typora/5df32d90ly1i88biik2xtj221o28ub2b.jpg)

Chat 页面的原型

![img](https://picbox-1313243162.cos.ap-nanjing.myqcloud.com/typora/5df32d90ly1i7ump8vv7rj225c2cinpd.jpg)