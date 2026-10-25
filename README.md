# 麦当劳智能配餐 Skill

调用麦当劳点餐服务，按人数、预算和口味生成最多 6 个经过门店真实价格试算的方案。Skill 只封装查询与结果展示，不下单、不支付。

## 依赖

- Python 3.10 或更新版本，CLI 无第三方依赖。
- 已启动的[麦当劳点餐网站与服务](https://github.com/chaoyuebro/mcd-ordering-assistant)，默认地址 `http://127.0.0.1:8000`。服务端需要配置 `MCD_TOKEN`，配置方式见网站仓库 README。

## 安装

将本仓库克隆到支持 `SKILL.md` 的客户端的 skills 目录。例如，在网站项目目录下安装为 WorkBuddy 项目级 Skill：

```bash
git clone https://github.com/chaoyuebro/mcd-meal-planner.git .workbuddy/skills/mcd-meal-planner
```

其他客户端请按其 skills 目录约定放置本仓库。网站与本 Skill 分别维护、分别克隆。

## 使用

以下命令在本仓库目录中执行：

```bash
python scripts/plan.py --help
python scripts/plan.py health
python scripts/plan.py stores --city 郑州 --keyword 二七广场
```

让用户从查询结果中选择门店，再将该门店编码用于配餐：

```bash
python scripts/plan.py plan --store <门店编码> --mode normal --text "两个人，预算60元，不吃辣"
```

服务地址可通过环境变量 `MCD_APP_HOST` 和 `MCD_APP_PORT` 配置。完整工作流与约束见 [SKILL.md](SKILL.md)，接口字段见 [references/api.md](references/api.md)。

价格来自服务端真实试算，热量和营养素只作展示，不作为配餐筛选条件。CLI 不需要保存或接触麦当劳 token。
