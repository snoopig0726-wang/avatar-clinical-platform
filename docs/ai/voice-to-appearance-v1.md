# Q1–Q8 声音到外貌特征与 GPT Image 2 Prompt

- Prompt 模板：`voice-to-appearance-v1.1`
- 映射规则：`deterministic-voice-appearance-v1.1`
- 当前状态：与 2026-07-30 运行时代码同步
- 运行时实现：
  - `backend/app/adapters/feature_mapping/deterministic_mapper.py`
  - `backend/app/adapters/feature_mapping/prompt_builder.py`
  - `backend/app/services/avatar_generation.py`

## 1. 当前链路

```text
医生录入本次会话 Q1–Q8
→ 后端校验固定枚举和数值范围
→ 确定性映射为 9 个受控视觉字段
→ 医生可从受控选项中调整并确认
→ 只使用已确认的 effective_visual_features 构建 Prompt
→ GPT Image 2 生成一张候选图
→ 图片结构检查与独立语义安全复检
→ 医生审核
→ 授权当前患者会话
```

Q1–Q8 不是身份推断，也不用于推断种族、职业、诊断、人格或患者本人长相。

## 2. Q1–Q8 输入契约

运行时声音特征：

```json
{
  "voice_gender": "male",
  "age_sense": "young",
  "pitch_level": 3,
  "speaking_rate_level": null,
  "timbre": null,
  "emotions": ["sadness"],
  "power_level": null,
  "malice_level": null
}
```

| 字段 | 约束 |
|---|---|
| `voice_gender` | `male` / `female` / `uncertain_mixed` |
| `age_sense` | `child` / `adolescent` / `young` / `middle_aged` / `elderly` / `uncertain` |
| `pitch_level` | 必填整数 1–5 |
| `speaking_rate_level` | 可选整数 1–5 |
| `timbre` | 可选固定枚举 |
| `emotions` | 1–6 项固定枚举，不得重复 |
| `power_level` | 可选整数 1–5 |
| `malice_level` | 可选整数 1–5 |

音色枚举：

- `hoarse_rough`
- `clear_transparent`
- `sharp_piercing`
- `low_rich`
- `breathy_weak`
- `nasal`
- `mumbled`
- `heavy_accent`
- `fine_soft`

情绪枚举：

- `anger`
- `indifference`
- `sarcasm`
- `sadness`
- `fear`
- `commanding`

当前 Q1–Q8 请求中没有必填 `risk_level`。首轮结构化访谈不对固定枚举内容运行患者调整文本风险分类器。患者后续自由文本调整和医生改写由独立 `RISK-V1.3` 门禁处理。

## 3. 受控视觉输出

系统映射输出 9 个字段：

```json
{
  "gender_expression": "...",
  "age_expression": "...",
  "face_shape": "...",
  "skin_texture": "...",
  "facial_expression": "...",
  "gaze": "...",
  "lighting": "...",
  "composition": "...",
  "background": "..."
}
```

每个字段只能使用 `CONTROLLED_VISUAL_OPTIONS` 中的受控选项或系统确定性映射结果。医生不能输入任意视觉 Prompt；医生调整仍受长度、内容和永久禁止项约束。

系统同时保存：

- `system_result_json`
- `doctor_edited_json`
- `effective_json`
- `mapping_explanation`
- `mapping_version`
- 医生确认人和确认时间

生图只执行医生确认后的 `effective_json`。

## 4. 映射规则

### 4.1 固定优先级

1. 声音性别与年龄感决定基础结构；
2. 情绪决定眉、眼、唇的局部状态；
3. 音调、语速和音色决定比例、质感、轮廓和微张力；
4. 强大感和恶意感只调节人物占比、明暗与距离感；
5. 儿童、老年和高冲突组合执行安全等价转换；
6. 医生从受控选项中确认最终视觉蓝图。

### 4.2 情绪

虽然表单允许最多 6 项固定情绪，但图片最多呈现两组局部面部信号。其余情绪只能作为相容的轻度气质，不能叠加第三组动作或提高刺激强度。

当 `anger` 与 `commanding` 同时存在时合并为一组克制信号，并禁止笑容。

### 4.3 强度上限

- 儿童：强大感最高 2，恶意感固定为 1；
- 老年且恶意感 ≥4：有效恶意感降至 2；
- 强大感与恶意感同时 ≥4：两者有效值降至 3；
- 所有组合保持眼平、浅色背景、浅色衣着、柔光和非压迫构图。

## 5. Prompt 输入契约

Prompt 构建器接收：

```json
{
  "voice_features": {
    "voice_gender": "male",
    "age_sense": "young",
    "pitch_level": 3,
    "speaking_rate_level": 3,
    "timbre": "clear_transparent",
    "emotions": ["sadness"],
    "power_level": 3,
    "malice_level": 2
  },
  "effective_visual_features": {
    "gender_expression": "...",
    "age_expression": "...",
    "face_shape": "...",
    "skin_texture": "...",
    "facial_expression": "...",
    "gaze": "...",
    "lighting": "...",
    "composition": "...",
    "background": "..."
  },
  "generation_mode": "initial",
  "doctor_confirmed": true
}
```

`doctor_confirmed=false` 时不能构建 Prompt。

生成模式：

- `initial`
- `same_features_regenerate`
- `feature_update`
- 患者调整生成由业务层使用对应的 `patient_adjustment` 模式

## 6. 固定肖像契约

- 1024×1024、1:1 PNG；
- 单人、虚构、非身份化、写实胸像；
- 正面或不超过 15° 轻微侧脸；
- 眼平、人物居中；
- 浅暖灰或医疗纸白纯色背景；
- 柔和均匀漫射光；
- 米白、浅灰或浅雾蓝纯色上衣；
- 无首饰、文字、logo 或水印。

## 7. 永久禁止项

Prompt 和受控特征永久禁止：

- 真实人物复刻、身份信息和患者本人长相；
- 医疗诊断暗示、种族、职业或人格推断；
- 武器、伤口、血迹、自伤、攻击、暴力；
- 恶魔、鬼怪、尖牙尖角、恐怖鬼脸；
- 夸张瞪眼、青筋、面部扭曲、纹身；
- 黑暗牢笼、废墟、阴暗小巷；
- 多人、文字、logo、水印；
- 黑衣、低机位、强阴影、阴影眼窝、压迫构图。

## 8. 患者调整

患者调整不进入本文件的 Q1–Q8 输入契约。处理流程为：

1. 患者自由文本执行多语言 `RISK-V1.3`；
2. 系统把安全文本映射为低刺激受控指令；
3. 医生可以直接接受；
4. 医生也可以选择性改写患者原话，改写后重新执行风险检查并重新映射；
5. 只有医生确认后的受控指令附加到生成 Prompt；
6. 患者原文和医生自然语言改写都不会直接发送给 GPT Image 2。

## 9. 生成与记录

当前 Provider 为 OpenAI `gpt-image-2`，默认 `quality=low`，每次生成 1 张图片。

`avatar_versions` 保存：

- Provider、模型和 Provider 请求 ID；
- Prompt 模板版本；
- Prompt SHA-256；
- Q1–Q8 与视觉特征快照；
- 输出格式、尺寸、存储键；
- 安全与医生审核状态。

系统不保存完整 Prompt，也不保存 API Key。

## 10. 版本记录

```text
v1.0  初始声音到外貌 Prompt
v1.1  固定肖像契约、确定性受控映射、医生确认门禁、最多两组面部信号与安全等价转换
```
