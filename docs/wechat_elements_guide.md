# 公众号文章支持的元素

## 1. 基础文本元素

### ✅ 支持
- **加粗**：`<strong>文字</strong>` 或 `<b>文字</b>`
- *斜体*：`<em>文字</em>` 或 `<i>文字</i>`
- 下划线：`<span style="text-decoration:underline">文字</span>`
- 删除线：`<span style="text-decoration:line-through">文字</span>`
- 颜色：`<span style="color:#ff0000">红色文字</span>`
- 字号：`<span style="font-size:18px">大字</span>`

### ❌ 不支持
- `<h1>` `<h2>` 等标题标签（会被过滤）
- `<code>` 代码标签
- `<ul>` `<ol>` 列表标签

**替代方案：**
```html
<!-- 标题用加粗 + 大字号 -->
<p><strong style="font-size:18px">一、核心概念</strong></p>

<!-- 列表用 emoji + 换行 -->
<p>
✅ 要点1<br/>
✅ 要点2<br/>
✅ 要点3
</p>

<!-- 代码用等宽字体 + 背景色 -->
<p style="font-family:Consolas,Monaco,monospace;background:#f5f5f5;padding:10px">
代码内容
</p>
```

## 2. 图片

### ✅ 支持
- 微信图片 URL（必须是 mmbiz.qpic.cn 域名）
- 通过 API 上传后获得的 URL

### 使用方法
```python
# 1. 上传图片
python3 upload_img.py image.png
# 输出：https://mmbiz.qpic.cn/...

# 2. 插入 HTML
<p><img src="https://mmbiz.qpic.cn/..." style="width:100%;max-width:600px"/></p>
```

### 图片样式
```html
<!-- 居中 -->
<p style="text-align:center">
  <img src="..." style="width:80%;max-width:500px"/>
</p>

<!-- 左右排列 -->
<p>
  <img src="..." style="width:48%;display:inline-block"/>
  <img src="..." style="width:48%;display:inline-block;margin-left:4%"/>
</p>
```

## 3. 链接

### ✅ 支持
- 外部链接（需要在公众号后台配置白名单）
- 公众号文章链接
- 小程序链接（需要关联）

### 使用方法
```html
<!-- 普通链接 -->
<a href="https://example.com" style="color:#576b95">点击查看</a>

<!-- 公众号文章链接 -->
<a href="https://mp.weixin.qq.com/s/..." style="color:#576b95">相关阅读</a>
```

### ⚠️ 注意
- 外部链接需要在公众号后台「设置与开发 > 公众号设置 > 功能设置 > 业务域名」中添加白名单
- 未添加白名单的域名会被过滤

## 4. 小程序卡片

### ✅ 支持（需要关联小程序）

### 使用方法
```html
<!-- 小程序卡片 -->
<mp-miniprogram 
  data-miniprogram-appid="小程序AppID"
  data-miniprogram-path="pages/index/index"
  data-miniprogram-title="小程序标题"
  data-miniprogram-imageurl="封面图URL">
</mp-miniprogram>
```

### 前置条件
1. 在公众号后台「设置与开发 > 公众号设置 > 相关小程序」中关联小程序
2. 小程序需要审核通过

## 5. 视频

### ✅ 支持
- 微信视频号视频
- 上传到公众号素材库的视频

### 使用方法
```html
<!-- 视频号视频 -->
<iframe class="video_iframe" 
  src="视频号视频链接" 
  frameborder="0" 
  allowfullscreen="true">
</iframe>
```

## 6. 音频

### ✅ 支持
- 上传到公众号素材库的音频

### 使用方法
```html
<mpvoice 
  src="音频素材ID" 
  name="音频标题">
</mpvoice>
```

## 7. 引用/卡片

### ✅ 支持（通过样式模拟）

```html
<!-- 引用框 -->
<section style="border-left:3px solid #576b95;padding-left:15px;margin:20px 0;background:#f7f7f7;padding:15px">
  <p style="color:#888;font-size:14px">💡 小贴士</p>
  <p>这里是引用内容</p>
</section>

<!-- 高亮卡片 -->
<section style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:20px;border-radius:8px;margin:20px 0">
  <p><strong>核心要点</strong></p>
  <p>重要内容...</p>
</section>
```

## 8. 表格

### ⚠️ 部分支持（样式受限）

```html
<table style="width:100%;border-collapse:collapse;margin:20px 0">
  <tr>
    <th style="border:1px solid #ddd;padding:8px;background:#f5f5f5">列1</th>
    <th style="border:1px solid #ddd;padding:8px;background:#f5f5f5">列2</th>
  </tr>
  <tr>
    <td style="border:1px solid #ddd;padding:8px">内容1</td>
    <td style="border:1px solid #ddd;padding:8px">内容2</td>
  </tr>
</table>
```

## 9. 分隔线

```html
<hr style="border:none;border-top:1px solid #eee;margin:30px 0"/>
```

## 10. 按钮/CTA

```html
<!-- 模拟按钮 -->
<p style="text-align:center;margin:30px 0">
  <a href="链接" style="display:inline-block;background:#576b95;color:#fff;padding:12px 30px;border-radius:5px;text-decoration:none">
    立即查看
  </a>
</p>
```

## 完整示例

```html
<section>
  <!-- 标题 -->
  <p><strong style="font-size:18px;color:#333">一、什么是 Prompt Engineering</strong></p>
  
  <!-- 正文 -->
  <p style="line-height:1.8;color:#555">
    简单来说，就是跟 AI 说话的艺术。你问得越清楚，AI 答得越靠谱。
  </p>
  
  <!-- 插图 -->
  <p style="text-align:center;margin:20px 0">
    <img src="https://mmbiz.qpic.cn/..." style="width:90%;max-width:600px"/>
  </p>
  
  <!-- 要点列表 -->
  <section style="background:#f7f7f7;padding:15px;border-radius:5px;margin:20px 0">
    <p><strong>核心要点：</strong></p>
    <p>
      ✅ 明确目标<br/>
      ✅ 提供上下文<br/>
      ✅ 分步骤引导
    </p>
  </section>
  
  <!-- 链接 -->
  <p>
    想深入了解？看这篇：
    <a href="https://mp.weixin.qq.com/s/..." style="color:#576b95">《Prompt 完全指南》</a>
  </p>
  
  <!-- CTA -->
  <p style="text-align:center;margin:30px 0">
    <span style="display:inline-block;background:#667eea;color:#fff;padding:12px 30px;border-radius:5px">
      关注公众号，回复「Prompt」获取模板
    </span>
  </p>
</section>
```

## 样式注意事项

1. **必须用 inline style**，不支持 `<style>` 标签和外部 CSS
2. **颜色建议：**
   - 正文：`#555` 或 `#333`
   - 链接：`#576b95`（微信蓝）
   - 强调：`#ff6b6b`（红色）或 `#667eea`（紫色）
3. **字号建议：**
   - 正文：14-16px
   - 标题：18-20px
   - 小字：12px
4. **行高：** `line-height:1.8` 提升可读性

## 推荐工具

- **Markdown 转公众号：** https://md.openwrite.cn/
- **样式编辑器：** https://editor.mdnice.com/
- **排版工具：** 秀米、135编辑器（但要注意代码清理）

## 最佳实践

1. **图片优先用微信 CDN**，不要用外部图床
2. **链接要测试**，确保在手机端能正常打开
3. **样式简洁**，过度设计在手机上显示不好
4. **留白充足**，`margin` 和 `padding` 要给够
5. **测试预览**，推草稿箱后在手机上看效果
