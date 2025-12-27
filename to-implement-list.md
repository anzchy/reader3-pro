## ✅在 AI chat 界面增加功能：

1.用户在每个书籍聊天（用 ollama 或其他 Ai Provider回复）记录对应的文件保存在哪里？

2.此外，新增聊天对话窗口（new chat），当新增窗口后，保留历史对话记录，避免一个对话窗口中聊天数量太多，挤占 Context。

3.结构化保存每一次对话记录，最好以 JSON 格式存储到对应书籍 data 文件夹（如 dracula_data）中。

![image-20251218223550993](https://picbox-1313243162.cos.ap-nanjing.myqcloud.com/typora/image-20251218223550993.png)





## ✅branch 004-library UI 重塑

Library 界面重塑如下：

左边侧边栏有按照文档类型来展示 pdf/epub/ all books 的数量。然后下方有 collections，可以按照作者或者一个主题来将多个 epub 电子书选中加入对应 collections 中。

中间展示所有的电子书的封面，中间上方一横排按钮分别有 搜索框（用于搜索书籍名称），添加书籍、排序（根据字母顺序）、网格视图、列表视图、选择（用于选择多个指定书籍，添加到 collection，或者批量 Index）

右边栏有多个页面可以，切换按钮在右下角，分别是 Dashboard，Chat，Search

- Dashboard: 显示 Books电子书数量，Indexed 过的电子书数量及 index 的比例。Sections 指所有的书划分成了多少个章节。Chunks 指 RAG 处理后合计有多少个 chunks。右下角有几个按钮，

- Chat：可以选择 all books，也可以选择单个书籍，或者某个 collection 进行一类主题的书籍的聊天

- Search指 cross-book search，之前已经实现过，支持 keyword search，semantic search，或者混合搜索模式。

![img](https://picbox-1313243162.cos.ap-nanjing.myqcloud.com/typora/5df32d90ly1i88biik2xtj221o28ub2b.jpg)



Chat 页面的原型

![img](https://picbox-1313243162.cos.ap-nanjing.myqcloud.com/typora/5df32d90ly1i7ump8vv7rj225c2cinpd.jpg)



### 20251224 ✅用得到 style guide  重塑UI

在书籍阅读页面有些细节有待进一步打磨。



## 界面 hot fix[completed partially]

✅1.书籍阅读页面，全局（无论点击到哪一章节）显示一个 `←`，点击后 back to Library interface.

![image-20251220092439241](https://picbox-1313243162.cos.ap-nanjing.myqcloud.com/typora/image-20251220092439241.png)

2. library right panel Search 界面，输入关键词，不能实现跨书籍全局搜索。

Seach 界面功能增强：类似于library right panel  Chat 页面，可以选择单个书籍或者单个 collection 或者 all books。

Search 界面 semantic search 似乎没有起到作用，仍然只是关键词搜索。譬如 money 和 wealth 算是关键词相近的，但是搜索 money，并不会显示 wealth，看看 semantic search 相关算法是否需要改进。

先去网上 github, stack_overflow,reddit 等搜索 long txt的 semantic search 最优算法，和如下我的思路比较。

我的思路：①当使用 semantic search 的时候，用户输入 money，后台先调用大模型（这个模型设置在 setting 中设置好了），输入Prompt 给模型：{$search_word} 相关的近义词有哪些？返回 3 个最相关的。②再根据 search_word + 3 个大模型返回的单词，来进行 keyword search，并返回所有搜索结果。

最终对比后，你返回一个最有的 算法，供我选择。



3. 调查一下 RAG 用法：

这个里面提到的用 mp4 file 来存储 chunks，https://github.com/memvid/memvid-mind，

和目前 repo 所用的 chunks 存储技术架构有什么不一样？哪一种更优？
