# dsh-vision 插件

给 dsh agent 注册 `vision` 工具：把本地图片发送到**你配置的 OpenAI 兼容视觉模型端点**返回文字描述——用于当前会话模型不支持图像输入的场景。

**插件没有任何内置默认值**：provider、凭据、模型全部在**安装时由你配置**。未配置完整时插件正常加载但不会注册 vision 工具（日志提示缺项），不会影响宿主。

## 安装（配置在安装时完成）

```bash
cd dsh-vision-install

# 方式 A：交互式——直接运行，按提示逐项输入 baseURL / 模型 / 凭据
bash install.sh --restart

# 方式 B：参数式——一键传参（适合脚本化/重复部署）
bash install.sh --restart \
  --vision-base-url https://opencode.ai/zen/go/v1 \
  --vision-api-key-env OPENCODE_GO_API_KEY \
  --vision-model mimo-v2.5 \
  --vision-models mimo-v2.5,qwen3.8-max,kimi-k3 \
  --vision-max-tokens 2000
```

## 安装参数（--vision-*）

| 参数 | 必填 | 说明 |
|---|---|---|
| `--vision-base-url` | ✅ | OpenAI 兼容 chat/completions 端点（任何厂商） |
| `--vision-model` | ✅ | 默认视觉模型 |
| `--vision-api-key` | 二选一 | 直接填 API key |
| `--vision-api-key-env` | 二选一 | 环境变量名（也尝试 ~/.dsh/.credentials.yaml 同名键） |
| `--vision-models` | 可选 | cross_check=true 时的核对模型列表（逗号分隔） |
| `--vision-max-tokens` | 可选 | 不配则请求不带 max_tokens |

> 未提供参数且是交互终端 → 引导式逐项询问；
> 未提供参数且非交互 → 写入空配置（工具不注册），可重跑传参，或编辑 `~/.dsh/profiles/web/cordis.patch.yml` 的 dsh-vision config 段。

## 使用（agent 内）

```
vision image_path=/tmp/shot.png
vision image_path=/tmp/shot.png question="图里有什么文字？"
vision image_path=/tmp/shot.png model=gpt-4o
vision image_path=/tmp/shot.png cross_check=true   # 需安装时配置了 --vision-models
```

## 安全说明

- 插件不含任何内置密钥；密钥只来自你的安装参数/环境/凭据文件
- 凭据文件 `~/.dsh/.credentials.yaml` 权限建议 `chmod 600`

## 常见问题

- 工具不出现：日志有 `[dsh-vision] 未配置 ...`——重跑 install.sh 传 `--vision-*` 参数后重启
- 凭据解析失败：`apiKey` 或 `apiKeyEnv`（含凭据文件同名键）至少其一
- 端点不兼容：确认 baseURL 是 OpenAI 兼容的 `/chat/completions`，鉴权 `Authorization: Bearer`
- reasoning 模型输出为空：配置 `--vision-max-tokens 2000` 以上
