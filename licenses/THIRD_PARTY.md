# 第三方素材来源与授权

本仓库的**代码**采用 MIT（见根目录 `LICENSE`）。下列素材的权利不因本仓库而转移，也未获得额外授权。

索引中只保存编号、名称、关键词与公开相对路径，**不保存任何图片文件，也不镜像、不转存、不再分发**。图片在展示与生成时按需从原始站点读取。

`docs/gallery/` 中的示例是例外，见第 3 节。

## 1. 姿势线稿

- 权利人：ギア（https://x.com/giaaibusi）
- 中文译名与目录：[anhao/ai-pose-gallery-zh](https://github.com/anhao/ai-pose-gallery-zh)
- 原站：https://ai-pose-gallery.pages.dev/
- 图床：https://ai-pose-gallery.anhao.app
- 规模：288 组 / 1439 张视角图
- 授权要点：**上游说明这些素材不得用于商业用途。** 该仓库的 MIT 许可只覆盖它自己的页面与脚本，不覆盖 `img/`、`thumbs/` 与原始数据。
- 本仓库的处理：标记 `license=upstream-noncommercial`、`commercial_use=false`；商用部署（`POSE_DEPLOYMENT=commercial`）下整体禁用，接口返回 `LICENSE_BLOCKED`。需要商用请替换为自有或已授权姿势库。索引不内置图片；`docs/gallery/pose.jpg` 仅内置 1 张预览用于非商业演示。

## 2. 服装参考（COSTUME-DB-01）

- 作者：ギア
- 原站：https://ai-costume-gallery.pages.dev/
- 规模：1407 套，图内无人物
- 授权要点：允许把这些图用作创作参考，包括编辑与商业作品中的参考；**禁止再分发、转载或转售图像数据本身**，原尺寸与加工后的图同样适用。署名不是对方要求，本仓库仍注明来源。
- 本仓库的处理：标记 `license=reference-only`、`commercial_use=true`、`mirror_allowed=false`；不缓存到磁盘、不转存对象存储、不打进发布包；路径只能指向原始站点。索引不内置图片；`docs/gallery/outfit.jpg` 仅内置 1 张预览用于非商业演示。

## 3. 示例素材（docs/gallery）

| 文件 | 来源 / 权利人 | 授权 | 是否内置 |
|---|---|---|---|
| `subject.jpg` | 上善无形 / ZipZipPipe，收录于 `TreapGoGo/deepseek-whale-girl` | **CC BY-NC-SA 4.0**（署名、非商业、相同方式共享；非官方社区角色） | 是，仅非商业演示 |
| `result.jpg` | 本项目生成，衍生自上述素材 | 随源素材，仅非商业演示 | 是，仅非商业演示 |
| 姿势 P069 | ギア / AI Pose Gallery | 非商业 | 是（1 张预览，非商业） |
| 服装 AUT-0051 | ギア / COSTUME-DB-01 | 仅参考、禁再分发 | 是（1 张预览，非商业；商用前删除） |

- 示例成品不代表获得上述素材的商业授权。
- 测试主体图为 CC BY-NC-SA 4.0（上善无形 / ZipZipPipe，收录于 `TreapGoGo/deepseek-whale-girl`）；该角色为非官方社区形象，本仓库与 DeepSeek 无关联。
- 如果要替换示例，请使用你拥有权利或 CC0 的素材。
- 索引数据组织与「姿势/服装参考」思路参考了 [wzc520pyfm/gen-ai-pose-image](https://github.com/wzc520pyfm/gen-ai-pose-image)，本项目与其无隶属关系。

## 4. 索引数据来源

- 姿势 catalog 与服装 catalog 的字段组织参考 [wzc520pyfm/gen-ai-pose-image](https://github.com/wzc520pyfm/gen-ai-pose-image)，该仓库同样只保存编号与公开地址，不附带图片。
- `scripts/build_index.py` 从上游 catalog 读取后，仅保留白名单分类与非成人向条目，写入本地索引。

## 5. 内容边界

- 索引在构建期丢弃全部成人向分类与条目，schema 中不保留相关字段。
- 加载期再次校验；出现白名单外分类、多人姿势或额外字段即整体拒绝。
- 运行时不提供任何开启成人向内容的配置项或环境变量。

## 6. 商用风险矩阵

| 行为 | 姿势库 | 服装库 | 测试主体（内置） | 生成结果 |
|---|---|---|---|---|
| 个人/非商业使用 | 允许 | 允许（作参考） | 允许（署名 + 相同方式共享） | 允许（非商业） |
| 商业使用 | **禁止** | 允许（作参考） | **禁止** | 取决于源素材与模型条款 |
| 在仓库/镜像中再分发原图 | 预览 1 张，仅非商业 | 预览 1 张，仅非商业；严格说与条款冲突 | 允许（CC BY-NC-SA） | 谨慎 |
| 转售图像数据本身 | **禁止** | **禁止** | **禁止** | **禁止** |
| 商用部署 | 必须替换为自有/已授权素材 | 可用 | 不使用 | 自行评估 |

商用部署的强制闸门：`POSE_DEPLOYMENT=commercial` + `POSE_LIBRARY=own`，索引中不得再包含 `pose-gallery-anhao` 条目，否则启动失败。

## 7. 商标与角色

- 本仓库不包含任何公司商标素材。
- 示例角色为社区创作，不代表任何公司官方形象。
- 若使用者自行导入模型、角色或品牌素材，需自行取得相应授权。

## 8. 建议的署名文案

出图结果或在产品界面中建议保留：

```text
Pose reference: AI Pose Gallery by ギア (via ai-pose-gallery.anhao.app), non-commercial.
Outfit reference: COSTUME-DB-01 by ギア (via ai-costume-gallery.pages.dev), reference use only, not redistributed.
Character sheet (demo): 上善无形 / ZipZipPipe, CC BY-NC-SA 4.0.
```
