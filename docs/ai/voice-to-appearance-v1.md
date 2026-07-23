# Q1–Q8 声音到外貌特征：一步生图 Prompt

版本：`voice-to-appearance-v1.0`

交付对象：后端 / AI 接入开发

本文件是完整交付物。开发人员只需要本 MD 文件，不需要依赖本项目中的 Python 文件，即可实现 Prompt 构建和图像生成 API 调用。

---

## 1. 功能目标

将医生端录入的 Q1–Q8 结构化声音信息，直接转换为图像生成 API 的 Prompt，生成：

- 单人、虚构、非身份化的人类写实头像；
- 1024×1024 正方形 PNG；
- 正面或不超过 15° 的轻微侧脸；
- 人物居中、纯色极简浅色背景；
- 低刺激、柔和、无暴力和恐怖化元素。

图像模型不需要返回 JSON，只需要生成图片。后端需要自行保存：

- Q1–Q8 输入快照；
- 医生确认后的视觉覆盖项；
- 最终发送给图像模型的完整 Prompt；
- Prompt 模板版本号：`voice-to-appearance-v1.0`；
- 供应商请求 ID。

---

## 2. 正式输入契约

开发时必须使用以下字段，不得混入旧 Demo 字段、患者自由文本或身份信息。

```json
{
  "voice_gender": "male",
  "age_sense": "young",
  "pitch_level": 3,
  "speaking_rate_level": null,
  "timbre": null,
  "emotions": ["sadness"],
  "power_level": null,
  "malice_level": null,
  "risk_level": "normal",
  "doctor_overrides": {},
  "generation_mode": "initial"
}
```

### 2.1 字段规则

| 字段 | 类型 | 必填 | 允许值 / 说明 |
|---|---|---:|---|
| `voice_gender` | string | 是 | `male` / `female` / `uncertain_mixed` |
| `age_sense` | string | 是 | `child` / `adolescent` / `young` / `middle_aged` / `elderly` / `uncertain` |
| `pitch_level` | integer | 是 | 1–5，音调高低 |
| `speaking_rate_level` | integer/null | 否 | 1–5，语速快慢；未填写时不增加语速专属视觉要求 |
| `timbre` | string/null | 否 | 见音色枚举；单选 |
| `emotions` | array | 是 | 只能使用六种固定情绪，可多选，不得为空 |
| `power_level` | integer/null | 否 | 1–5，声音强大感 |
| `malice_level` | integer/null | 否 | 1–5，声音恶意感 |
| `risk_level` | string | 是 | `normal` / `sensitive` / `crisis` / `high_stimulus` |
| `doctor_overrides` | object | 否 | 医生确认后的视觉特征覆盖，见第 5 节 |
| `generation_mode` | string | 否 | `initial` / `same_features_regenerate` / `feature_update` |

### 2.2 音色枚举

```text
hoarse_rough        沙哑粗糙
clear_transparent   清亮通透
sharp_piercing      尖锐刺耳
low_rich            低沉浑厚
breathy_weak        气声虚弱
nasal               鼻音偏重
mumbled             口齿含糊
heavy_accent        厚重口音
fine_soft           纤细轻柔
```

### 2.3 情绪枚举

```text
anger        愤怒
indifference 冷漠
sarcasm      嘲讽
sadness      悲伤
fear         恐惧
commanding   命令式
```

V1 不支持 `other`、自定义情绪、患者原话、患者自由文本和单项情绪强度。

### 2.4 滑块缺省规则

- `pitch_level` 必须填写，范围只能是整数 1–5。
- `speaking_rate_level` 未填写时，不增加语速专属视觉要求。
- `power_level` 未填写时，内部按 3 档中性基线计算，但不得描述为医生明确观察到“中等强大感”。
- `malice_level` 未填写时，内部按 3 档中性基线计算，但不得描述为医生明确观察到“中等恶意感”。

---

## 3. 风险门禁：必须在调用图像 API 前执行

风险门禁不能只依赖图像模型 Prompt，必须由后端先判断 `risk_level`。

```text
normal       允许继续生成，执行全部安全映射
sensitive    允许生成，但必须执行柔和降级
crisis       禁止调用图像 API
high_stimulus 禁止调用图像 API
```

当 `risk_level` 为 `crisis` 或 `high_stimulus` 时：

1. 不调用图像模型；
2. 不保存或发送原始风险文本；
3. 返回内部状态 `IMAGE_GENERATION_BLOCKED`；
4. 保留当前已审核版本，不替换现有头像；
5. 前端只显示产品规定的固定风险提示。

当 `risk_level` 为 `sensitive` 时：

- 降低画面对比度；
- 弱化阴影、冷调、轮廓锋利度和负面神态；
- `power_level` 最高按 3 档执行；
- `malice_level` 最高按 3 档执行；
- 背景保持浅色、干净、非压迫性。

---

## 4. 完整 System Prompt

以下内容直接作为图像模型的 System Prompt，或作为单一 `prompt` 字符串的前置固定部分。

```text
Prompt template version: voice-to-appearance-v1.0

你是幻听患者个性化 Avatar 系统的受控人像生成提示词执行器。

你的唯一任务是：根据医生在 V1 Q1–Q8 表单中录入的匿名、结构化声音特征，生成一个虚构的、非身份化的、低刺激的人类写实头像。声音特征只能映射为抽象且可编辑的外貌、表情、眼神、光影和构图维度，不得声称推断真实身份、人格、种族、医学事实或患者本人长相。

## 输出目标

- 只生成一名虚构人类人物，写实头像，1024×1024 正方形 PNG。
- 正面或不超过 15° 的轻微侧脸，人物居中，纯色极简浅色背景。
- 面部细节自然、光影柔和、低刺激、无文字、无 logo、无水印、无额外人物。
- 不生成场景叙事；声音特征只影响面部与受控画面维度。

## 输入字段边界

只使用以下 Q1–Q8 字段：voice_gender、age_sense、pitch_level、speaking_rate_level、timbre、emotions、power_level、malice_level。情绪只能是 anger、indifference、sarcasm、sadness、fear、commanding 六种固定值。不得使用患者自由文本、身份信息、额外情绪、自定义人格或医学描述。

## 基础属性映射

- male：男性基础面部表达，下颌和眉骨可略有结构感、偏粗眉形、常规短发；不得生成刻板或夸张性别特征。
- female：女性基础面部表达，下颌较圆润、眉眼曲线柔和、软组织自然饱满、常规短发或中长发。
- uncertain_mixed：中性面部表达，不强化男性或女性骨骼、发型或色调。
- child：短宽幼态脸、五官集中、短鼻梁、光滑无皱纹、圆润下颌；必须中性、温和、非威胁。
- adolescent：面部略拉长、五官舒展、无明显细纹、轮廓锋利度中等。
- young：均衡成年人比例，皮肤平整，立体感适中。
- middle_aged：轻微眼角纹和法令纹、轻微松弛，不夸大衰老。
- elderly：自然鱼尾纹、法令纹、松弛和眼袋，眉发可稀疏变白；强制暖中性柔光。
- uncertain：青年至中年之间的中性表达，不强化幼态或老化。

## 音调映射 pitch_level 1–5

1 很低：面部宽大厚重、下颌方正、五官舒展偏大、低饱和中性色调；轮廓锋利度不超过 3。
2 偏低：面部圆润宽厚、五官偏大、柔和低对比光影；整体表情冲击力降低一档。
3 中等：标准均衡脸型、正常五官比例、中性柔和光影。
4 偏高：面部纤细狭长、五官小巧、轻微高光提亮；轮廓锋利度不超过 4，禁止尖脸畸形。
5 很高：狭长纤细脸、眉眼紧凑、浅亮柔和冷中性色调；有负面情绪时进一步削弱凶狠观感。

## 语速映射 speaking_rate_level 1–5

1 很慢：面部完全放松、眉眼舒展、嘴唇自然、眼神平缓；紧绷表现锁定最低。
2 偏慢：面部轻微放松、无紧绷感；负面神态冲击力降低。
3 中等：面部肌肉松紧均衡，正常表达。
4 偏快：眉眼轻微收拢、嘴唇微抿、眼神活跃；只增加细碎柔和高光，不制造压迫感。
5 很快：眉头轻收、嘴唇自然闭合、眼神轻微紧绷；降低画面对比度并弱化阴影。

## 音色映射 timbre

- hoarse_rough：较厚的皮肤纹理、哑光柔光、减少锐利高光；不强化锋利轮廓。
- clear_transparent：细腻皮肤、均匀漫射柔光、干净柔和高光、无厚重阴影。
- sharp_piercing：五官纤细小巧、轮廓仅轻微清晰、浅冷低饱和；凶狠表情严格弱化。
- low_rich：宽厚饱满脸型、软组织自然厚重、低饱和中性柔光、五官舒展。
- breathy_weak：人物画面占比偏小、柔光虚化、低对比、无硬阴影。
- nasal：软组织略饱满、鼻翼光影柔和、温润质感、无尖锐面部线条。
- mumbled：面部边缘和光影过渡柔和，不生成清晰锋利轮廓；负面情绪下大幅降低紧绷感。
- heavy_accent：脸型略宽厚、柔和层次光影、无高对比暗角；快语速时进一步降低阴影。
- fine_soft：五官小巧轻薄、立体感较弱、浅亮柔光、无厚重下颌。

音色为单选。高风险或高恶意时清空音色的锋利、厚重和冷调效果。儿童与冷调音色组合时强制暖柔光。

## 固定情绪映射

- anger：眉头轻微收拢、嘴唇轻合、下颌轻微收紧；禁止咬牙、青筋、扭曲和瞪眼。
- indifference：面部平缓、视线轻微放空、肌肉放松；禁止空洞白眼和发黑眼窝。
- sarcasm：单侧嘴角极细微上扬、眼神平淡；禁止坏笑、露齿、蔑视和俯视构图。
- sadness：眉眼小幅柔和下垂、面部松弛；禁止大哭、泪痕、红肿和崩溃。
- fear：眉眼轻微抬起、瞳孔自然小幅放大、柔和紧绷；禁止惊悚瞪眼、惨白、冷汗和扭曲。
- commanding：端正平视、轮廓清晰平缓；禁止压迫凝视、狰狞和居高临下。

多情绪必须中和，不叠加刺激效果。儿童勾选任何负面情绪时只保留非常轻微、温和、幼态的神态。恶意感升高时，负面神态逐级弱化，最多累计弱化两层。

## 强大感与恶意感

未填写的 power_level 或 malice_level 使用 3 作为内部中性基线，但不得把未填写说成明确观察事实。

power_level：1 为小比例、轻薄、浅亮、强虚化；2 为约 50% 画面占比、低立体度；3 为约 60% 居中、均衡立体；4 为约 75% 主体占比、浅层柔和阴影；5 为约 85% 近景、饱满立体和多层浅柔光。禁止硬阴影、暗角、俯视压迫构图。敏感风险最高执行 3，危机不执行生图。

malice_level：1 为暖调、松弛眼神、无面部阴影、圆润五官；2 为极淡微冷中性、轻微收敛眼神；3 为轻微偏冷低饱和、浅层眼窝和下颌柔影；4 为浅冷中性、提亮背景并弱化锋利五官；5 仍只能是浅微冷、低饱和、极淡单层阴影和圆润五官。禁止黑暗画面、凶狠凝视和尖锐骨骼。儿童强制为 1，老年高恶意自动降至 2。

power_level ≥ 4 且 malice_level ≥ 4 时，两者均不超过 3，并提亮画面、弱化阴影。存在负面情绪时，恶意感每增加一档就再降低负面神态一层，最多两层。

## 风险与优先级

优先级从高到低：高刺激/危机拦截 > 永久禁止元素 > 儿童/老年年龄安全约束 > 敏感风险柔和降级 > 医生确认特征 > 声音映射细节 > 默认中性基线。

- normal：执行映射，但仍遵守所有禁止元素和低刺激约束。
- sensitive：降低对比度和阴影，弱化冷调、锋利度和负面神态，背景保持浅色。
- crisis/high_stimulus：不得生成图像。调用方必须在进入图像 API 前拦截。

医生确认的视觉覆盖项优先于自动映射，但不能突破本节安全边界。不得把医生覆盖项解释为真实身份或医学事实。

## 永久禁止

绝不生成武器、伤口、血迹、攻击动作、自伤动作、暴力场景、恶魔、鬼怪、异兽、尖角、尖牙、利爪、恐怖鬼脸、眼球突出、青筋、面部扭曲、危险符号、纹身、危险图案、阴暗牢笼、废墟、阴暗小巷、真实人物、名人面孔、患者本人复刻、姓名、身份证、住址或其他身份信息。

最终输出必须是一张低刺激的、单人、虚构、写实头像，不输出解释文字，不加入额外对象或叙事场景。
```

---

## 5. 动态 User Prompt 模板

开发人员把下面模板中的变量替换成实际表单值，再拼接到 System Prompt 后发送给图像模型。

```text
请执行一次受控的人像生成，不要输出解释文字。

## 本次结构化输入

{
  "voice_gender": "{{voice_gender}}",
  "age_sense": "{{age_sense}}",
  "pitch_level": {{pitch_level}},
  "speaking_rate_level": {{speaking_rate_level_or_null}},
  "timbre": "{{timbre_or_null}}",
  "emotions": {{emotions_json_array}},
  "power_level": {{power_level_or_null}},
  "malice_level": {{malice_level_or_null}},
  "risk_level": "{{risk_level}}",
  "generation_mode": "{{generation_mode}}"
}

## 本次医生确认的视觉覆盖

{{doctor_overrides_json}}

## 本次映射执行

1. 根据 voice_gender 和 age_sense 执行基础属性映射。
2. 根据 pitch_level、speaking_rate_level 和 timbre 执行声学特征映射。
3. 根据 emotions 执行六种固定情绪的轻度映射，并对多情绪进行中和。
4. 根据 power_level 和 malice_level 执行画面占比、立体感、色调、眼神和阴影映射。
5. 应用儿童、老年、敏感风险和高强大感+高恶意感联动规则。
6. 医生确认的视觉覆盖优先，但不得突破安全上限。
7. 固定输出正面或不超过 15° 轻微侧脸、人物居中、纯色极简浅色背景、1024×1024 正方形单人写实头像。

最终只生成符合 System Prompt 的图片，不添加文字、logo、水印、额外人物、负面场景、暴力、伤害、恐怖化、恶魔化、真实人物复刻或身份信息。
```

### 5.1 变量替换要求

- 字符串必须进行 JSON 转义，不能直接拼接未转义用户文本。
- `emotions_json_array` 必须是 JSON 数组，例如 `["anger", "fear"]`。
- 未填写字段使用 `null`，不要使用空字符串、`未填写` 或中文自然语言。
- `doctor_overrides_json` 使用 JSON 对象；没有覆盖时传 `{}`。
- 不得把患者原始文本插入 Prompt。

---

## 6. 医生视觉覆盖字段

允许覆盖的 key 只有：

```json
{
  "gender_expression": "中性表达",
  "age_expression": "弱化年龄特征",
  "face_shape": "轮廓保持柔和",
  "skin_texture": "皮肤纹理自然",
  "facial_expression": "保持平静、自然、轻微放松",
  "gaze": "视线自然，不形成压迫凝视",
  "lighting": "柔和漫射光，降低阴影",
  "composition": "人物居中，正面头像",
  "background": "浅色纯色背景"
}
```

医生覆盖优先级高于自动映射，但以下内容永远不能被覆盖：

- 不能生成真实人物或身份复刻；
- 不能突破儿童、老年和敏感风险安全上限；
- 不能增加武器、伤口、血迹、攻击动作或恐怖元素；
- 不能生成阴暗牢笼、废墟、阴暗小巷等场景；
- 不能把负面情绪渲染为狰狞、扭曲、青筋、瞪眼或压迫性构图。

医生修改后，后端应记录：

```json
{
  "is_doctor_edited": true,
  "doctor_overrides": {},
  "effective_visual_features": {}
}
```

---

## 7. 生成模式

### `initial`

首次生成。根据完整 Q1–Q8 执行全部映射。

### `same_features_regenerate`

重新生成同一特征。复用当前已确认的有效视觉特征，只更换随机种子；不得重新解释 Q1–Q8，也不得重置医生修改。

### `feature_update`

调整声音字段或视觉特征。使用更新后的 Q1–Q8 和医生覆盖重新执行完整映射，并创建新的 Avatar 版本。

---

## 8. API 调用伪代码

```python
def generate_avatar(form):
    validate_q1_q8(form)

    if form["risk_level"] in {"crisis", "high_stimulus"}:
        return {
            "status": "blocked",
            "code": "IMAGE_GENERATION_BLOCKED"
        }

    system_prompt = SYSTEM_PROMPT_FROM_THIS_DOCUMENT
    user_prompt = render_user_prompt(form)

    request = {
        "model": "供应商模型名称",
        "prompt": system_prompt + "\n\n" + user_prompt,
        "size": "1024x1024",
        "response_format": "b64_json"
    }

    result = image_provider.generate(request)

    save_generation_snapshot(
        sound_snapshot=form,
        prompt=system_prompt + "\n\n" + user_prompt,
        prompt_template_version="voice-to-appearance-v1.0",
        provider_request_id=result.provider_request_id
    )

    return result
```

如果供应商支持 system/user 两段式请求：

```json
{
  "model": "供应商模型名称",
  "system": "第 4 节完整 System Prompt",
  "user": "第 5 节动态 User Prompt",
  "size": "1024x1024",
  "response_format": "b64_json"
}
```

图像生成完成后仍必须执行图片安全检查、医生人工审核和当前会话授权。Prompt 本身不能替代这些后置门禁。

---

## 9. 验收测试

### 9.1 普通场景

输入：

```json
{
  "voice_gender": "male",
  "age_sense": "young",
  "pitch_level": 3,
  "speaking_rate_level": 2,
  "timbre": "low_rich",
  "emotions": ["sadness"],
  "power_level": 3,
  "malice_level": 1,
  "risk_level": "normal"
}
```

预期：均衡成年人脸型、柔和光影、低饱和暖调、轻微悲伤，不出现眼泪或崩溃表情。

### 9.2 儿童+负面情绪+高恶意

输入：`age_sense=child`、`malice_level=5`、`emotions=["anger", "fear"]`。

预期：恶意感锁定 1，强大感最高 2，暖浅色调，负面神态最低柔和表现，不出现冷暗、锋利、威胁或惊悚效果。

### 9.3 高强大感+高恶意感

输入：`power_level=5`、`malice_level=5`。

预期：两者均封顶 3，提亮画面、弱化阴影，不使用近距离压迫构图。

### 9.4 敏感风险

输入：`risk_level=sensitive`。

预期：允许生成，但降低对比度、阴影、冷调、锋利度和负面神态。

### 9.5 危机和高刺激

输入：`risk_level=crisis` 或 `risk_level=high_stimulus`。

预期：不调用图像 API，返回 `IMAGE_GENERATION_BLOCKED`。

### 9.6 医生覆盖

输入：

```json
{
  "doctor_overrides": {
    "facial_expression": "保持平静、自然、轻微放松",
    "lighting": "柔和漫射光，降低阴影"
  }
}
```

预期：覆盖项进入最终 Prompt，但仍保留所有安全边界。

### 9.7 非法输入

以下输入必须拒绝：

- `pitch_level=0` 或 `pitch_level=6`；
- 未知情绪或自定义情绪；
- 旧字段 `free_description`、`voice_traits`；
- 医生覆盖中出现武器、伤口、血迹、暴力、身份信息或真实人物要求。

---

## 10. 版本管理

当前版本：`voice-to-appearance-v1.0`

后续修改必须：

1. 更新版本号；
2. 记录修改原因；
3. 保留旧版本 Prompt；
4. 使用本文件第 9 节测试样例回归；
5. 保存每次生成使用的 Prompt 版本号。

版本记录格式：

```text
v1.0 → 初始 Q1–Q8 一步生图 Prompt
v1.1 → 修改内容、影响字段、回归结果
```

