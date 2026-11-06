# 贡献指南

## 开发环境

- Python 3.9+
- 仅标准库；无需安装依赖
- 可选：`Pillow` 用于剥离用户上传图片的 EXIF（`pip install -e ".[exif]"`）

```bash
git clone https://github.com/miyuki-shirogane/PoseCloset.git
cd PoseCloset
export POSE_STATE_DIR=/tmp/pose-outfit-state
export POSE_RENDERER=mock
python3 -m unittest discover -s tests -t . -v
```

## 提交前检查

```bash
python3 -m unittest discover -s tests -t . -v
python3 scripts/build_index.py --check
```

CI 会在 Python 3.9–3.12 上跑同一套检查。

## 代码约定

- 只使用标准库；新增依赖需在 PR 中说明理由。
- 所有业务规则必须在工具层强制，不能只写在提示词里。
- 新增素材字段时，同步更新 `index/schema.json`、`library.py` 的严格校验与测试。
- 不要在仓库中提交第三方图片、密钥、会话数据库或个人信息。

## 新增渲染后端

实现 `poseoutfit/render/base.py` 中的三个方法：

```python
class MyProvider(RenderProvider):
    def capabilities(self) -> dict: ...
    def submit(self, spec, assets, idempotency_key) -> dict: ...
    def poll(self, run_id) -> dict: ...
```

在 `get_provider()` 中注册，并补充至少一条端到端测试（可用 mock 资产）。

## 素材与授权

- 不要提交姿势线稿、服装图或任何人像素材。
- 新增素材来源时，必须记录 `license`、`commercial_use`、`source_url` 与署名。
- 上游禁止再分发的素材，只能保存编号、关键词与公开地址。

## 报告问题

请附上：

- 复现步骤与工具名
- `session_id` 状态（脱敏）
- 错误码与 `hint`
- 是否可稳定复现
