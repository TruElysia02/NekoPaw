# `scene json`（场景布局描述）v2

这份说明只管当前已经稳定下来的 `scene json`（场景布局描述）输入结构。

现在可以这样理解：

- `Markdown`（标记文本）适合自然文本流、段落、列表和“一张图配一段文字”。
- `scene json`（场景布局描述）适合固定坐标布局、卡片式排版、图片窗口、角标和状态块。
- 当前设备主目标还是 `296x128`（分辨率）黑白墨水屏，所以这一版优先收敛“稳定可用”，不追求一开始就做成很重的通用设计系统。
- 当前 `296x128`（分辨率）低分屏最终位图里，关键文字已经优先走目标像素网格直出；浏览器预览链会保留，但小尺寸 `badge`（徽标块）、`caption`（小标题）和多行标题会按低分屏规则自动收紧。
- 这条低分屏文字链现在会先在各自的 `text block`（文字块）小画布里完成背景、边框和文字栅格化，再按块级层级贴回最终位图，块内裁切和视觉居中会比整页统一覆盖更稳。

## 顶层结构

`scene json`（场景布局描述）顶层目前只约定一个 `blocks`（块数组）：

```json
{
  "blocks": [
    {
      "type": "text",
      "x": 12,
      "y": 12,
      "w": 120,
      "h": 24,
      "text": "Signal report",
      "role": "title"
    }
  ]
}
```

- `blocks`（块数组）必须存在，且至少包含一个块。
- 块数组里的每一项都必须是对象。
- 相对路径图片默认相对于当前 `scene json`（场景布局描述）文件所在目录解析；也可以在命令行用 `--assets-root`（素材根目录）覆盖。

## 稳定字段

### 通用块字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `type` | string | 当前只支持 `text`（文字块）和 `image`（图片块） |
| `x` / `y` | int | 左上角坐标，单位像素 |
| `w` / `h` | int | 宽高，必须大于 `0` |
| `padding` | int | 可选，块内边距，必须大于等于 `0` |
| `z` | int | 可选，默认 `0`，同一视觉层里数值越大越靠上 |

### 文字块字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `text` | string | 必填，块内文字 |
| `role` | string | 可选，支持 `title`、`subtitle`、`body`、`caption`、`badge` |
| `align` | string | 可选，支持 `left`、`center`、`right` |
| `valign` | string | 可选，支持 `top`、`middle`、`bottom` |
| `frame` | bool | 可选，给文字块加边框 |
| `invert` | bool | 可选，文字块反相显示 |

### 图片块字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `src` | string | 必填，本地相对路径、绝对路径，或可直接给浏览器的 URL |
| `alt` | string | 可选，图片描述 |
| `fit` | string | 可选，支持 `cover`、`contain`、`fill` |
| `anchor` | string | 可选，默认 `center`，支持 `top-left`、`top`、`top-right`、`left`、`center`、`right`、`bottom-left`、`bottom`、`bottom-right` |
| `frame` | bool | 可选，给图片块加边框 |

## 图层规则

这一版的 `z`（层级）先按当前渲染链的真实约束来定：

- 同一视觉层里，`z`（层级）越大越靠上。
- 同一个 `z`（层级）时，仍按 `blocks`（块数组）原顺序叠放。
- 当前 `296x128 epd_bw`（296x128 黑白墨水屏）走的是“图片层 + 前景层”分层栅格化，所以文字层会固定压在图片层上面，保证预览图和最终位图一致。
- 当前低分屏最终位图已经把 `text`（文字块）从浏览器缩放文字层里拆出来，改成按目标像素网格直接绘制；图片块和图片边框仍继续走现有浏览器分层捕获。
- 低分屏块内文字默认会优先挑更适合小屏的字体组合：纯英文 / 数字块偏向 `Verdana`（字体）/ `Tahoma`（字体），含中文块偏向 `Microsoft YaHei`（字体）/ `Yu Gothic`（字体）；如果你已经在环境变量里设置了 `NEKOPAW_RENDER_FONT_REGULAR/BOLD`（低分屏字体覆盖），仍然会直接以那两项为准。
- 也就是说，当前 `z`（层级）不会把图片盖到文字上面。如果想做更强的视觉重点，优先用更大的图片窗口、边框、反相文字块，或者留到后面的排版阶段处理。

## 推荐边界

- 页面主要是标题、正文、列表、脚注这类自然流内容时，优先用 `Markdown`（标记文本）。
- 页面需要固定位置图片、贴角标签、上下分栏、叠层卡片时，用 `scene json`（场景布局描述）。
- 不要把长篇自由文本硬塞进很多绝对定位文字块里；那种情况后面更适合交给 `pretext`（文本排版库）阶段处理。

## 示例

仓库里现在有两套可以直接渲染的示例：

- `skill/render/examples/scene_news_card.json`
- `skill/render/examples/scene_poster_card.json`

直接渲染预览图和位图：

```bash
python skill/render_cli.py scene --input skill/render/examples/scene_news_card.json --preview out/news_card.png --bitmap out/news_card.bin

python skill/render_cli.py scene --input skill/render/examples/scene_poster_card.json --preview out/poster_card.png --bitmap out/poster_card.bin
```

如果只想看结构，不想马上转位图，也可以先只出预览图。
