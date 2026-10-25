# 接口与口径

本机服务默认 `http://127.0.0.1:8000`，只读，无鉴权（凭据在服务端，从 `MCD_TOKEN` 环境变量读）。

## 接口一览

| 接口 | 用途 | 备注 |
|---|---|---|
| `GET /api/health` | 服务与凭据状态 | `hasToken:false` 说明服务没拿到 token |
| `GET /api/stores?city=&keyword=` | 按城市/地标查门店 | 无参数时返回附近门店 |
| `GET /api/menu?storeCode=&mode=` | 门店菜单 | `mode` = `lean` / `normal` |
| `GET /api/detail?storeCode=&code=` | 单品详情 | 含 `rounds`（套餐段数）与可定制项 |
| `POST /api/plan` | 生成配餐方案 | 唯一需要 POST 的接口 |
| `POST /api/price` | 单品试算 | 配餐内部已调用，一般不用直接调 |

## POST /api/plan

请求体：

```json
{
  "storeCode": "3560134",
  "mode": "lean",
  "text": "两个人，不吃辣，预算60",
  "cart": [{"code": "520689", "quantity": 1}],
  "skip": [["麦香鱼", "鲜萃咖啡"]],
  "needTableware": true,
  "useLLM": true
}
```

- `cart`：购物车已有商品。**只用于排除重复推荐**，其热量与金额不进入方案计算。
- `skip`：上一套方案的 `signature` 数组，用于「换一套」。
- `text`：用户原话，不要自己改写成数字。
- `useLLM`：是否让模型参与解析（默认 `true`）。服务端未配置 `MINIMAX_API_KEY` 时自动回退正则，不需要调用方判断。

响应（仅列 Skill 会用到的字段）：

```json
{
  "ok": true,
  "mode": "normal",
  "recognized": [{"type": "people", "label": "2 人份：主餐 ×2、饮品 ×2"}, {"type": "budget", "label": "预算 60 元（含上限）"}],
  "unresolved": ["「不超过1000千卡」未生效：配餐只按人数、预算与口味搭配，不按热量筛"],
  "plans": [
    {
      "id": 1,
      "items": [{"code": "1450", "name": "麦香鸡", "quantity": 1, "kcalSource": "official", "sauceOff": false, "macros": {"protein": 15, "fat": 17, "carbohydrate": 39}}],
      "kcal": 869,
      "kcalText": "约 869 千卡",
      "macrosText": "蛋白 ≥15g · 脂肪 ≥17g · 碳水 ≥39g",
      "yuan": 30.5,
      "coupon": null,
      "hasEstimate": true,
      "signature": ["1450", "1451"]
    }
  ],
  "blocker": null,
  "cartKcal": 0,
  "cartPrice": 0,
  "ai": {"used": true, "model": "MiniMax-M3.1-Flash", "summary": "两个人不吃辣，预算 60 元；热量暂不作为条件", "error": null},
  "note": "返回 2 张券，均不适用于当前餐品，已按无券试算；「不超过1000千卡」未生效：配餐只按人数、预算与口味搭配，不按热量筛"
}
```

`ai` 字段说明：

| 字段 | 含义 |
|---|---|
| `used` | 本次是否由模型解析（`false` 表示走了关键词规则） |
| `model` | 实际使用的模型名 |
| `summary` | 模型对用户原话的一句话复述，可直接展示给用户核对 |
| `error` | 未启用/失败原因（如 `未配置 MINIMAX_API_KEY`），正常时为空 |

模型解析出的条件会以 `recognized[].source = "AI 解析"` 出现在列表里，与正则解析出的条件区分开。

**V1.20 起**：`recognized` 只会出现人数（`people`）、预算（`budget`）、份数（`count`）、必选（`must`）、排除（`exclude`）、偏好（`pref`）与默认结构（`default`）这几类；**不再有 `kcalMax` / `macroMin` / `macroMax`**。用户提到热量或营养素时，相关说明只出现在 `unresolved` 与 `note` 里。

## 口径（转述时必须遵守）

1. **`yuan` 是唯一可信价格。** 它来自门店 `calculate-price` 的真实试算（含券后优惠）。菜单里的 `price` 是列表价，部分商品不可信（实测：燕麦奶铁列表 ¥9.9、试算 ¥27；板烧四件套列表 ¥28、试算 ¥87）。
2. **`kcal` 与 `macrosText` 都是「方案自身」口径**，不叠加购物车。
3. **`macrosText` 里的「≥」是下界。** 组合内有商品缺官方营养数据时，缺失部分按 0 计入，所以是下限。`macrosText` 为空表示该方案一件官方数据都没有——此时说「暂无官方营养数据」，不要补 0。
4. **`hasEstimate: true`** 表示方案内至少一件商品的热量是兜底估算（`kcalSource` 为 `heuristic` / `unknown`），转述时保留「约」并说明哪件是估算。
5. **减脂模式（`lean`）** 只含汉堡与黑咖啡，汉堡默认去酱（`sauceOff: true`，热量已按去酱后计）。去酱只扣热量，蛋白质/脂肪/碳水不调整。
6. **无方案时** `plans` 为 `[]`，`blocker.message` 给出基于真实候选与试算价的阻碍原因（V1.20 起只剩预算与搭配两类），`blocker.suggestions` 给出放宽方向。照抄，不要自行推测更低价格。
7. **AI 解析结果要回显。** 当 `ai.used` 为真时，把 `ai.summary` 和标着 `AI 解析` 的条件一起告诉用户，让他确认有没有理解错；不要额外替模型解释或补充它没说过的条件。
8. **热量与营养素不筛选（V1.20）。** 用户提到「不超过 1000 千卡」「蛋白质 25g 以上」时照实说明「该条件未生效，配餐只按人数、预算与口味搭配」；不要替用户把这些条件翻译成任何筛选，也不要自己按热量或营养素挑方案。

## 常见错误

| 返回 | 含义 | 处理 |
|---|---|---|
| `400 缺少 storeCode` | 没传门店 | 先调 `/api/stores` 让用户选 |
| `401` | token 失效 | 让用户重新设置 `MCD_TOKEN` 并重启服务 |
| `blocker.code = no-match` | 条件互相冲突 | 照抄阻碍与建议，等用户决定 |
| `note` 含「未生效」 | 热量/营养素不再参与配餐 | 照实说明，不要自行补条件 |
| `note` 含「试算失败」 | 个别方案没算出来 | 其余方案仍有效，如实说明 |

## 实测样例（2026-10-25，门店 3560097，V1.20 口径）

```
plan --store 3560097 --mode normal --text "三个人，不吃辣，预算90"

1. ¥78.50 · 麦香鱼×1 + 牛肉堡单品精选×2 + 鲜萃咖啡×3
2. ¥81.00 · 麦香鱼×1 + 麦香鸡×1 + 牛肉堡单品精选×1 + 鲜萃咖啡×3
```

同一门店「三个人，不吃辣，预算60」无方案，阻碍原文：

> 最便宜的一组「麦香鱼×1 + 牛肉堡单品精选×2 + 鲜萃咖啡×3」试算应付 78.50 元，超出 60 元预算

「每个人不超过1000千卡，预算100元，蛋白质25g以上，两个人，不要咖啡」——热量与蛋白质均未生效（note 明示），返回 6 组方案（¥28.0~¥76.0），无饮品，主餐 2 份起。
