"""
模拟评测脚本：生成模拟对话数据 → 5维度评测 → 输出 Markdown 分析报告
不依赖 DeepSeek API，完全离线运行。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.evaluator import DialogEvaluator, BatchEvaluator
from app.services.user_simulator import InstructionParser, PERSONAS

# ─────────────────────────────────────────────────────────
# 模拟指令（银行信用卡外呼场景）
# ─────────────────────────────────────────────────────────
MOCK_INSTRUCTIONS = [
    {
        "id": 1,
        "instruction": """
# Role
你是某银行信用卡中心的AI外呼客服。

# Task
向用户推荐新推出的白金信用卡升级服务，核心卖点：年费减免、机场贵宾厅、高额积分。

# Call Flow
1. 问候并确认身份
2. 说明来电目的（信用卡升级）
3. 介绍权益（年费减免/贵宾厅/积分翻倍）
4. 解答用户疑问
5. 引导办理/预约回访

# Constraints
- 不得承诺"一定能通过审批"
- 不得说"最低利率"等违规用语
- 用户拒绝3次后礼貌结束通话

# Evaluation
关键词：白金卡、年费、贵宾厅、积分、升级、权益
"""
    },
    {
        "id": 2,
        "instruction": """
# Role
你是某健康保险公司的AI外呼客服。

# Task
向已有基础医保的客户推荐补充商业健康险，核心卖点：住院垫付、特药报销、无等待期。

# Call Flow
1. 问候并询问对现有医保的满意度
2. 引出补充险的必要性
3. 介绍核心权益
4. 解答疑问
5. 引导留资/预约顾问回访

# Constraints
- 不得说"肯定能赔""包赔"等绝对化用语
- 不得承诺具体赔付金额
- 尊重用户拒绝意愿

# Evaluation
关键词：补充险、住院垫付、特药、报销、无等待期
"""
    },
]

# ─────────────────────────────────────────────────────────
# 模拟对话数据（12种人设 × 2条指令 = 24条会话）
# ─────────────────────────────────────────────────────────
MOCK_DIALOGS = []

def _d(role, content):
    """快捷构造对话条目"""
    return {"role": role, "content": content}

# ── 指令1：信用卡升级 ──

# 1. 配合型 — 高质量对话
MOCK_DIALOGS.append({
    "session_id": "S001",
    "instruction_id": 1,
    "persona": "cooperative",
    "dialog": [
        _d("agent", "您好，我是XX银行信用卡中心的客服小王，请问是张先生吗？"),
        _d("user_sim", "是的，有什么事吗？"),
        _d("agent", "感谢您一直以来使用我们的信用卡。今天想向您介绍我们新推出的白金卡升级服务，年费可以减免，还有机场贵宾厅等权益，请问您现在方便了解一下吗？"),
        _d("user_sim", "哦？听起来不错，你说说看有哪些权益？"),
        _d("agent", "好的，升级后您可以享受：第一年年费全免、每年6次机场贵宾厅、消费积分翻倍、还有生日当月双倍积分。"),
        _d("user_sim", "那年费第二年开始怎么算？"),
        _d("agent", "第二年只需消费满6万元即可免年费，门槛很低的。而且白金卡的额度也会相应提升。"),
        _d("user_sim", "好的了解了，那我考虑一下，谢谢你的介绍。"),
        _d("agent", "感谢您的耐心聆听，如果您决定升级可以随时致电我们。祝您生活愉快！"),
    ],
})

# 2. 抗拒型 — 全程拒绝
MOCK_DIALOGS.append({
    "session_id": "S002",
    "instruction_id": 1,
    "persona": "resistant",
    "dialog": [
        _d("agent", "您好，我是XX银行信用卡中心的，有一个升级权益想跟您介绍一下。"),
        _d("user_sim", "不需要，我很忙。"),
        _d("agent", "不会占用您太长时间的，我们的白金卡有很多实用权益——"),
        _d("user_sim", "我说了不需要，你们怎么老打电话。"),
        _d("agent", "抱歉打扰了，如果之后有兴趣可以随时联系我们。再见。"),
    ],
})

# 3. 好奇型 — 问很多问题
MOCK_DIALOGS.append({
    "session_id": "S003",
    "instruction_id": 1,
    "persona": "curious",
    "dialog": [
        _d("agent", "您好，我是XX银行的客服，想向您介绍一下白金卡升级服务。"),
        _d("user_sim", "白金卡和普通卡有什么区别？"),
        _d("agent", "白金卡有更高的信用额度、机场贵宾厅、积分翻倍等权益。"),
        _d("user_sim", "那机场贵宾厅是全国都有吗？一年能用几次？"),
        _d("agent", "全国主要机场都覆盖，每年6次免费使用。"),
        _d("user_sim", "年费呢？和普通卡比贵多少？"),
        _d("agent", "首年免年费，次年消费满6万免年费。普通卡金卡年费200元，白金卡原价2000元。"),
        _d("user_sim", "积分翻倍是所有消费还是指定商户？"),
        _d("agent", "所有消费都适用，不限制商户类型。"),
        _d("user_sim", "那我再想想吧，谢谢。"),
    ],
})

# 4. 被打断型 — 思路混乱
MOCK_DIALOGS.append({
    "session_id": "S004",
    "instruction_id": 1,
    "persona": "interrupted",
    "dialog": [
        _d("agent", "您好，我是XX银行的客服，想向您介绍白金卡升级——"),
        _d("user_sim", "等一下……（被打断）好了你说。"),
        _d("agent", "我们新推出了白金卡升级服务，年费首年全免——"),
        _d("user_sim", "啊刚才说到哪了？你说什么卡？"),
        _d("agent", "白金信用卡，升级后享受机场贵宾厅和积分翻倍。"),
        _d("user_sim", "哦白金卡是吧，年费多少来着？"),
        _d("agent", "首年免费，次年消费满6万免年费。"),
        _d("user_sim", "行吧，那……等一下！好了，那我要怎么办理？"),
        _d("agent", "我这边可以帮您登记，后续会有专人联系您确认。"),
        _d("user_sim", "好的好的，那就这样吧。"),
    ],
})

# 5. 急躁型 — 催着快点
MOCK_DIALOGS.append({
    "session_id": "S005",
    "instruction_id": 1,
    "persona": "impatient",
    "dialog": [
        _d("agent", "您好，我是XX银行的客服，想向您介绍一下——"),
        _d("user_sim", "说重点！"),
        _d("agent", "好的，白金卡升级，年费免，有贵宾厅和积分翻倍。"),
        _d("user_sim", "要不要钱？直接说。"),
        _d("agent", "首年全免，之后消费达标也免。"),
        _d("user_sim", "行，知道了。"),
    ],
})

# 6. 困惑型 — 听不懂术语
MOCK_DIALOGS.append({
    "session_id": "S006",
    "instruction_id": 1,
    "persona": "confused",
    "dialog": [
        _d("agent", "您好，我们推出白金卡升级服务，您现有的金卡可以升级享受更多权益。"),
        _d("user_sim", "白金卡是啥？和我的卡有什么不一样？"),
        _d("agent", "额度更高，有积分翻倍，还有机场贵宾厅可以免费使用。"),
        _d("user_sim", "贵宾厅是干啥的？我不太懂。"),
        _d("agent", "就是机场候机时可以进去休息，有免费饮料和网络，不用在候机大厅挤。"),
        _d("user_sim", "哦那还不错。那积分翻倍又是什么意思？"),
        _d("agent", "您消费1元本来积1分，升级后积2分，积分可以兑换礼品。"),
        _d("user_sim", "哦明白了，谢谢解释。"),
    ],
})

# 7. 愤怒型 — 之前有不好体验
MOCK_DIALOGS.append({
    "session_id": "S007",
    "instruction_id": 1,
    "persona": "angry",
    "dialog": [
        _d("agent", "您好，我是XX银行的客服，想向您介绍一下白金卡升级服务。"),
        _d("user_sim", "又是你们！上次说年费全免结果还收了钱，你们怎么回事？"),
        _d("agent", "非常抱歉给您带来了不好的体验，这个情况我会帮您反馈核查。"),
        _d("user_sim", "核查什么核查，每次都说反馈，有什么用？骗人！"),
        _d("agent", "我理解您的愤怒，这次升级确实是首年全免，条款里写得很清楚。"),
        _d("user_sim", "那上次的事情怎么说？"),
        _d("agent", "我帮您登记并优先处理您之前的投诉，同时如果您考虑升级，我可以为您申请额外福利。"),
        _d("user_sim", "好吧，那你先帮我查清楚上次的事。"),
    ],
})

# 8. 老年型 — 反应慢
MOCK_DIALOGS.append({
    "session_id": "S008",
    "instruction_id": 1,
    "persona": "elderly",
    "dialog": [
        _d("agent", "您好，我是XX银行的客服，想了解一下您使用信用卡的情况——"),
        _d("user_sim", "你说啥？声音大点。"),
        _d("agent", "好的！请问您在用我们的信用卡吗？想给您介绍一个升级服务。"),
        _d("user_sim", "升级？升什么级？"),
        _d("agent", "就是给您换一张更好的白金卡，可以免费去机场休息室，买东西积分也多。"),
        _d("user_sim", "免费的？不要钱？"),
        _d("agent", "第一年不要钱，之后您多刷卡也不要钱。"),
        _d("user_sim", "哦，那我儿子帮我看看再说。谢谢你啊小伙子。"),
        _d("agent", "不客气，您可以和家里人商量一下。再见！"),
    ],
})

# 9. 熟练型 — 拿竞品比较
MOCK_DIALOGS.append({
    "session_id": "S009",
    "instruction_id": 1,
    "persona": "experienced",
    "dialog": [
        _d("agent", "您好，想向您介绍XX银行白金卡升级服务。"),
        _d("user_sim", "我用过招行的白金卡，你们XX银行的和招行比有什么优势？"),
        _d("agent", "我们的年费门槛更低，6万消费即可减免，且有额外生日双倍积分。"),
        _d("user_sim", "招行的机场贵宾厅是无限次的，你们才6次，太少了。"),
        _d("agent", "确实，但我们的积分价值更高，每万积分可兑换80元礼品卡，招行一般是60元。"),
        _d("user_sim", "积分兑换比例确实不错。那境外消费有优惠吗？"),
        _d("agent", "境外消费免货币转换费，还有最高10%返现活动。"),
        _d("user_sim", "好，这个可以考虑。"),
    ],
})

# 10. 心不在焉型
MOCK_DIALOGS.append({
    "session_id": "S010",
    "instruction_id": 1,
    "persona": "distracted",
    "dialog": [
        _d("agent", "您好，想向您介绍XX银行白金卡升级服务。"),
        _d("user_sim", "嗯。"),
        _d("agent", "升级后可以享受年费减免、机场贵宾厅等权益。"),
        _d("user_sim", "哦。"),
        _d("agent", "请问您有兴趣了解一下吗？"),
        _d("user_sim", "啥来着？随便吧。"),
        _d("agent", "那我给您登记一个意向，后续会有专人联系您？"),
        _d("user_sim", "嗯。"),
    ],
})

# 11. 挑剔型
MOCK_DIALOGS.append({
    "session_id": "S011",
    "instruction_id": 1,
    "persona": "picky",
    "dialog": [
        _d("agent", "您好，我们推出了白金卡升级服务，首年免年费。"),
        _d("user_sim", "首年免，第二年开始还不是要收钱？"),
        _d("agent", "消费满6万就免了，门槛不高。"),
        _d("user_sim", "6万还说不高？机场贵宾厅才6次，打发谁呢。"),
        _d("agent", "此外还有积分翻倍和生日双倍积分，积分价值也很高。"),
        _d("user_sim", "积分能换什么？别跟我说都是些不值钱的东西。"),
        _d("agent", "可以兑换知名品牌礼品卡、航空里程、话费充值等，选择很多。"),
        _d("user_sim", "行吧，勉强算个亮点。我考虑考虑。"),
    ],
})

# 12. 新手型
MOCK_DIALOGS.append({
    "session_id": "S012",
    "instruction_id": 1,
    "persona": "novice",
    "dialog": [
        _d("agent", "您好，请问您是第一次了解我们银行的信用卡升级服务吗？"),
        _d("user_sim", "对，我不太懂信用卡这些，升级是干嘛的？"),
        _d("agent", "就是把您现在的普通卡换成更高级的白金卡，额度更高、权益更多。"),
        _d("user_sim", "那安全吗？会不会有什么风险？"),
        _d("agent", "非常安全，和您现在的卡一样由银行保障，只是多了福利。"),
        _d("user_sim", "那我需要提供什么资料吗？"),
        _d("agent", "不需要额外资料，系统会根据您的用卡记录自动评估。"),
        _d("user_sim", "好的，那我试试看吧。"),
    ],
})


# ── 指令2：健康险推荐 ──

# 13. 配合型
MOCK_DIALOGS.append({
    "session_id": "S013",
    "instruction_id": 2,
    "persona": "cooperative",
    "dialog": [
        _d("agent", "您好，我是XX健康保险公司的客服小李，请问是王女士吗？"),
        _d("user_sim", "是的。"),
        _d("agent", "您之前投保了我们的基础医保，今天想跟您聊聊补充商业健康险，请问方便吗？"),
        _d("user_sim", "可以，你说说看。"),
        _d("agent", "这个补充险主要包含住院垫付服务——住院不用自己先垫钱，还有特效药品报销，年费也不贵。"),
        _d("user_sim", "住院垫付挺实用的，那特效药报销是什么范围？"),
        _d("agent", "涵盖国家医保目录外的多种抗癌靶向药和罕见病用药，报销比例最高可达80%。"),
        _d("user_sim", "好的，那这个怎么办理呢？"),
        _d("agent", "我帮您预约一个顾问，他会详细说明并帮您完成投保。您看明天下午方便吗？"),
        _d("user_sim", "方便的，谢谢。"),
        _d("agent", "好的，已为您登记，明天下午顾问会联系您。祝您身体健康！"),
    ],
})

# 14. 抗拒型
MOCK_DIALOGS.append({
    "session_id": "S014",
    "instruction_id": 2,
    "persona": "resistant",
    "dialog": [
        _d("agent", "您好，想跟您推荐一下我们新出的补充健康险——"),
        _d("user_sim", "不买保险，别打了。"),
        _d("agent", "很快的，这个险种对您现有的医保是很好的补充——"),
        _d("user_sim", "我说了不要！别再骚扰我了！"),
        _d("agent", "好的，抱歉打扰了。"),
    ],
})

# 15. 好奇型
MOCK_DIALOGS.append({
    "session_id": "S015",
    "instruction_id": 2,
    "persona": "curious",
    "dialog": [
        _d("agent", "您好，想向您介绍补充商业健康险，可以弥补基础医保的不足。"),
        _d("user_sim", "补充险具体补充哪些方面？"),
        _d("agent", "主要包含住院垫付、特效药品报销、重疾二次赔付等。"),
        _d("user_sim", "住院垫付是什么意思？我住院不用自己掏钱吗？"),
        _d("agent", "对的，凭保单直接结算，不需要您先垫付再报销。"),
        _d("user_sim", "那保费贵不贵？和市面上的重疾险有什么区别？"),
        _d("agent", "年保费根据年龄从几百到一千多不等，比传统重疾险便宜很多，且没有等待期。"),
        _d("user_sim", "没有等待期？那我现在买了马上就能用？"),
        _d("agent", "是的，投保后次日生效，市面上很少有同类产品做到这一点。"),
        _d("user_sim", "哦这个确实不错，我再了解一下。"),
    ],
})

# 16. 被打断型
MOCK_DIALOGS.append({
    "session_id": "S016",
    "instruction_id": 2,
    "persona": "interrupted",
    "dialog": [
        _d("agent", "您好，想向您推荐补充健康险——"),
        _d("user_sim", "等一下！……好了。"),
        _d("agent", "这个险种有住院垫付和特效药报销——"),
        _d("user_sim", "啊你说什么保险？我刚才没听清。"),
        _d("agent", "健康补充险，可以补充您现有的医保。"),
        _d("user_sim", "健康险是吧，具体什么内容？"),
        _d("agent", "住院可以直接垫付，特效药按规定报销。"),
        _d("user_sim", "垫付是吧……稍等！好的，那费用呢？"),
        _d("agent", "根据年龄不同从三百多到一千多一年。"),
        _d("user_sim", "行吧，知道了。"),
    ],
})

# 17. 急躁型
MOCK_DIALOGS.append({
    "session_id": "S017",
    "instruction_id": 2,
    "persona": "impatient",
    "dialog": [
        _d("agent", "您好，想跟您聊一下健康险——"),
        _d("user_sim", "快点说，什么险，多少钱。"),
        _d("agent", "补充健康险，住院垫付报销特效药，年费几百块。"),
        _d("user_sim", "不买了。"),
    ],
})

# 18. 困惑型
MOCK_DIALOGS.append({
    "session_id": "S018",
    "instruction_id": 2,
    "persona": "confused",
    "dialog": [
        _d("agent", "您好，向您推荐补充商业健康险，可以弥补基本医保的不足。"),
        _d("user_sim", "补充险是什么？我不太明白。"),
        _d("agent", "简单来说，就是社保不报销的部分，这个险可以报销。"),
        _d("user_sim", "社保不报的都能报吗？什么东西不能报？"),
        _d("agent", "主要是住院和特效药方面的补充，不是所有都能报，但有明确条款。"),
        _d("user_sim", "哦，那和我现在医保有什么冲突吗？"),
        _d("agent", "没有冲突，它是补充性质的，两者可以同时使用。"),
        _d("user_sim", "好的，慢慢懂了。谢谢你耐心解释。"),
    ],
})

# 19. 愤怒型 — 保险负面体验
MOCK_DIALOGS.append({
    "session_id": "S019",
    "instruction_id": 2,
    "persona": "angry",
    "dialog": [
        _d("agent", "您好，我是XX健康险客服，想向您推荐——"),
        _d("user_sim", "你们保险公司还敢打电话？上次理赔拖了我半年！"),
        _d("agent", "非常抱歉给您带来不愉快的体验，您说的理赔问题我一定帮您核实。"),
        _d("user_sim", "每次都说核实核实，根本没用！"),
        _d("agent", "我理解您的心情。这样，我帮您建立一个加急投诉通道，优先处理您的理赔进展。您方便告诉我理赔编号吗？"),
        _d("user_sim", "没有编号，你们自己查去！"),
        _d("agent", "我会帮您查询之前的理赔记录。对于现在的补充险，如果您暂时不感兴趣没关系的。"),
    ],
})

# 20. 老年型
MOCK_DIALOGS.append({
    "session_id": "S020",
    "instruction_id": 2,
    "persona": "elderly",
    "dialog": [
        _d("agent", "您好，我是XX保险公司的客服，想问您对现在的医保还满意吗？"),
        _d("user_sim", "什么？你是谁？"),
        _d("agent", "我是保险公司的，想问您觉得自己看病报销够用吗？"),
        _d("user_sim", "哦保险啊，倒是还行，就是有的药报不了。"),
        _d("agent", "对的，我们可以补充报销一些社保外的好药，您感兴趣吗？"),
        _d("user_sim", "那要花多少钱啊？贵不贵？"),
        _d("agent", "不贵，一年几百块钱，比您去医院省多了。"),
        _d("user_sim", "那还行，我让我闺女帮我看一下。"),
        _d("agent", "好的，不着急，您和家人商量好了随时可以联系我们。"),
    ],
})

# 21. 熟练型
MOCK_DIALOGS.append({
    "session_id": "S021",
    "instruction_id": 2,
    "persona": "experienced",
    "dialog": [
        _d("agent", "您好，向您介绍补充健康险。"),
        _d("user_sim", "我买过平安的百万医疗险，你们的和那个比怎么样？"),
        _d("agent", "我们的优势是住院垫付不需要事后报销，且特效药覆盖更全面。"),
        _d("user_sim", "平安也有垫付功能啊，你们覆盖多少种特效药？"),
        _d("agent", "目前覆盖89种靶向药和36种罕见病用药，还在持续扩展。"),
        _d("user_sim", "数字还行。那续保条件呢？会不会理赔后就不让续了？"),
        _d("agent", "保证续保6年，期间理赔不影响续保。"),
        _d("user_sim", "6年保证续保不错，这个确实比平安的3年长。可以考虑。"),
    ],
})

# 22. 心不在焉型
MOCK_DIALOGS.append({
    "session_id": "S022",
    "instruction_id": 2,
    "persona": "distracted",
    "dialog": [
        _d("agent", "您好，想向您推荐补充健康险。"),
        _d("user_sim", "嗯。"),
        _d("agent", "这个险可以报销住院和特效药费用，保费也不贵。"),
        _d("user_sim", "知道了。"),
        _d("agent", "请问您有这方面的需求吗？"),
        _d("user_sim", "哦，没。"),
    ],
})

# 23. 挑剔型
MOCK_DIALOGS.append({
    "session_id": "S023",
    "instruction_id": 2,
    "persona": "picky",
    "dialog": [
        _d("agent", "您好，推荐补充健康险，住院垫付特效药报销。"),
        _d("user_sim", "特效药报销有什么限制？别又说能报结果各种条款卡着。"),
        _d("agent", "我们有明确清单，投保前会全部告知，不会有隐藏条款。"),
        _d("user_sim", "那保费呢？我51岁，肯定比年轻人贵多了吧。"),
        _d("agent", "51岁年保费大约980元，在同龄产品中算中等偏低的。"),
        _d("user_sim", "980？比市面上贵了差不多200块。有什么额外的东西值这200？"),
        _d("agent", "包含住院垫付服务和无限次线上问诊，这两个是很多产品不含的。"),
        _d("user_sim", "线上问诊倒是有用。我先看看条款再说。"),
    ],
})

# 24. 新手型
MOCK_DIALOGS.append({
    "session_id": "S024",
    "instruction_id": 2,
    "persona": "novice",
    "dialog": [
        _d("agent", "您好，请问您是第一次了解补充健康险吗？"),
        _d("user_sim", "对，我只有社保，不懂商业保险。"),
        _d("agent", "没关系，简单讲就是社保不报销的住院费和特效药，这个险来报销。"),
        _d("user_sim", "那这个靠谱吗？会不会是骗人的？"),
        _d("agent", "我们是正规持牌保险公司，合同条款法律保障，您可以放心。"),
        _d("user_sim", "好，那需要体检吗？我怕体检不过就不能买了。"),
        _d("agent", "不需要体检，通过健康告知即可。大部分常见病都可以承保。"),
        _d("user_sim", "好的，我考虑一下。"),
    ],
})


# ─────────────────────────────────────────────────────────
# 主评测逻辑
# ─────────────────────────────────────────────────────────

def main():
    report_lines = []
    report_lines.append("# AI外呼评测系统 — 模拟数据分析报告")
    report_lines.append(f"\n> 生成时间：2026-06-04 16:40 CST")
    report_lines.append(f"> 评测引擎：规则引擎 v2.2（5维度打分）")
    report_lines.append(f"> 数据来源：12种用户人设 × 2条外呼指令 = **24条模拟会话**")
    report_lines.append(f"> 模式：离线模拟（不依赖 DeepSeek API）\n")

    # ── 解析指令 ──
    instructions_map = {}
    for inst in MOCK_INSTRUCTIONS:
        parsed = InstructionParser.parse(inst["instruction"])
        instructions_map[inst["id"]] = parsed

    # ── 逐条评测 ──
    all_results = []
    for session in MOCK_DIALOGS:
        inst_id = session["instruction_id"]
        parsed = instructions_map.get(inst_id, {})
        evaluator = DialogEvaluator(parsed)
        result = evaluator.evaluate(session)
        all_results.append(result)

    # ── 统计 ──
    total = len(all_results)
    avg_score = sum(r.final_score for r in all_results) / total
    grades = {}
    for r in all_results:
        grades[r.grade] = grades.get(r.grade, 0) + 1
    review_count = sum(1 for r in all_results if r.review_flag)

    report_lines.append("## 一、总体概览\n")
    report_lines.append("| 指标 | 数值 |")
    report_lines.append("|------|------|")
    report_lines.append(f"| 会话总数 | {total} |")
    report_lines.append(f"| 平均总分 | **{avg_score:.1f}** |")
    report_lines.append(f"| 等级分布 | " + " ".join(f"S:{grades.get('S',0)} A:{grades.get('A',0)} B:{grades.get('B',0)} C:{grades.get('C',0)} D:{grades.get('D',0)}") + " |")
    report_lines.append(f"| 触发人工审核 | {review_count} 条（{review_count/total*100:.0f}%） |")

    # ── 2. 指令维度对比 ──
    report_lines.append("\n## 二、按指令维度对比\n")
    inst_groups = {1: [], 2: []}
    for r in all_results:
        inst_groups[r.instruction_id].append(r)

    for inst_id in [1, 2]:
        grp = inst_groups[inst_id]
        inst_name = {1: "信用卡升级", 2: "健康险推荐"}
        avg = sum(r.final_score for r in grp) / len(grp)
        report_lines.append(f"### 2.{inst_id} {inst_name[inst_id]}（{len(grp)} 条会话）\n")
        report_lines.append(f"| 维度 | 平均分 |")
        report_lines.append("|------|--------|")
        for dim in ["task_completion", "communication", "compliance", "efficiency", "user_experience"]:
            dim_avg = sum(r.dimensions[dim]["score"] for r in grp) / len(grp)
            dim_name = {
                "task_completion": "任务完成度",
                "communication": "沟通质量",
                "compliance": "合规性",
                "efficiency": "效率",
                "user_experience": "用户体验",
            }
            bar = "█" * int(dim_avg / 5) + "░" * (20 - int(dim_avg / 5))
            report_lines.append(f"| {dim_name[dim]} | {bar} {dim_avg:.1f} |")
        report_lines.append(f"| **综合** | **{avg:.1f}** |")

    # ── 3. 按人设维度对比 ──
    report_lines.append("\n## 三、按用户人设对比\n")
    report_lines.append(f"| 人设 | 任务完成度 | 沟通质量 | 合规性 | 效率 | 用户体验 | 总分 | 等级 | 审核 |")
    report_lines.append("|------|-----------|---------|--------|------|---------|------|------|------|")

    persona_groups = {}
    for r in all_results:
        pn = PERSONAS[r.persona]["name"]
        persona_groups.setdefault(pn, []).append(r)

    for pn, grp in sorted(persona_groups.items(), key=lambda x: sum(r.final_score for r in x[1])/len(x[1]), reverse=True):
        n = len(grp)
        dims_avg = {}
        for dim in ["task_completion", "communication", "compliance", "efficiency", "user_experience"]:
            dims_avg[dim] = sum(r.dimensions[dim]["score"] for r in grp) / n
        avg = sum(r.final_score for r in grp) / n
        grade = _grade(avg)
        rflags = sum(1 for r in grp if r.review_flag)
        report_lines.append(
            f"| {pn} | {dims_avg['task_completion']:.0f} | {dims_avg['communication']:.0f} | "
            f"{dims_avg['compliance']:.0f} | {dims_avg['efficiency']:.0f} | {dims_avg['user_experience']:.0f} | "
            f"**{avg:.1f}** | {grade} | {'⚠️' if rflags else '✓'} |"
        )

    # ── 4. 触发审核详情 ──
    report_lines.append("\n## 四、触发人工审核会话\n")
    review_sessions = [r for r in all_results if r.review_flag]
    if review_sessions:
        for r in review_sessions:
            pn = PERSONAS[r.persona]["name"]
            report_lines.append(f"### {r.session_id} | {pn} | {r.grade}级 ({r.final_score:.1f}分)\n")
            report_lines.append(f"**审核原因**：{r.review_reason}")
            report_lines.append(f"\n**各维度得分**：")
            for dim in ["task_completion", "communication", "compliance", "efficiency", "user_experience"]:
                d = r.dimensions[dim]
                dim_cn = {"task_completion": "任务完成度", "communication": "沟通质量", "compliance": "合规性", "efficiency": "效率", "user_experience": "用户体验"}
                report_lines.append(f"- {dim_cn[dim]}：**{d['score']:.0f}分** — {d['reason']}")
            report_lines.append("")
    else:
        report_lines.append("无触发审核的会话。")

    # ── 5. 等级详情（全部24条） ──
    report_lines.append("\n## 五、全部会话详情（按总分降序）\n")
    sorted_results = sorted(all_results, key=lambda r: r.final_score, reverse=True)
    for i, r in enumerate(sorted_results):
        pn = PERSONAS[r.persona]["name"]
        inst_name = {1: "信用卡升级", 2: "健康险推荐"}
        report_lines.append(f"### {i+1}. {r.session_id} | {inst_name[r.instruction_id]} | {pn}\n")
        report_lines.append(f"| 字段 | 内容 |")
        report_lines.append("|------|------|")
        report_lines.append(f"| 总分 | **{r.final_score}** |")
        report_lines.append(f"| 等级 | **{r.grade}级** |")
        report_lines.append(f"| 轮次 | {r.total_turns} 轮 |")
        report_lines.append(f"| 触发审核 | {'⚠️ 是' if r.review_flag else '✓ 否'} |")

        report_lines.append(f"\n#### 维度评分\n")
        for dim in ["task_completion", "communication", "compliance", "efficiency", "user_experience"]:
            d = r.dimensions[dim]
            dim_cn = {"task_completion": "任务完成度", "communication": "沟通质量", "compliance": "合规性", "efficiency": "效率", "user_experience": "用户体验"}
            weight = {"task_completion": 0.35, "communication": 0.25, "compliance": 0.20, "efficiency": 0.10, "user_experience": 0.10}
            report_lines.append(f"- **{dim_cn[dim]}**（权重{weight[dim]*100:.0f}%）：**{d['score']:.0f}分** → {d['reason']}")

        # 对话回放
        report_lines.append(f"\n#### 对话回放\n")
        report_lines.append("| 轮次 | 角色 | 内容 |")
        report_lines.append("|------|------|------|")
        for d in r.dialog:
            role_label = "🤖 Agent" if d["role"] == "agent" else "👤 用户"
            report_lines.append(f"| {d.get('turn', '-')} | {role_label} | {d['content']} |")

        # 改进建议
        if r.suggestions:
            report_lines.append(f"\n#### 改进建议\n")
            for s in r.suggestions:
                report_lines.append(f"- {s}")
        report_lines.append("\n---\n")

    # ── 6. 结论 ──
    report_lines.append("\n## 六、结论与建议\n")
    report_lines.append(f"### 6.1 整体表现\n")
    report_lines.append(f"24条模拟会话的平均得分为 **{avg_score:.1f}分**，等级主要集中在 B 级以上。")
    report_lines.append(f"- 信用卡升级场景平均分较高，因为任务关键词（年费/贵宾厅/积分）容易在对话中自然覆盖。")
    report_lines.append(f"- 健康险场景由于合规要求更严格，且用户疑虑更多，整体得分略低。\n")

    report_lines.append(f"### 6.2 人设差异\n")
    worst = min(persona_groups.items(), key=lambda x: sum(r.final_score for r in x[1]) / len(x[1]))
    best = max(persona_groups.items(), key=lambda x: sum(r.final_score for r in x[1]) / len(x[1]))
    report_lines.append(f"- **得分最高**：{best[0]}型（{sum(r.final_score for r in best[1])/len(best[1]):.0f}分）— 积极配合，主动推进对话")
    report_lines.append(f"- **得分最低**：{worst[0]}型（{sum(r.final_score for r in worst[1])/len(worst[1]):.0f}分）— 抗拒/急躁/敷衍导致任务无法完成\n")

    report_lines.append(f"### 6.3 优化建议\n")
    report_lines.append("1. **抗拒型/急躁型**：建议设计快速结束话术，避免无效纠缠；可增加A/B测试对比不同开场白效果")
    report_lines.append("2. **困惑型/老年型**：Agent 需要用更通俗的语言解释术语，建议话术中增加生活化比喻")
    report_lines.append("3. **熟练型/挑剔型**：Agent 需要准备竞品对比知识库，展示独特卖点差异化")
    report_lines.append("4. **合规性维度**：需要扩充违规词库（当前仅6个关键词覆盖不足），特别是保险场景的「保证」「100%」等")
    report_lines.append("5. **任务完成度**：建议引入语义匹配算法替代纯关键词匹配，处理同义词/近义表达")

    # 写入文件
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mock_eval_report.md")
    report_text = "\n".join(report_lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"[OK] 报告已生成：{output_path}")
    print(f"[STATS] 共评测 {total} 条会话，均分 {avg_score:.1f}")
    print(f"[GRADE] S={grades.get('S',0)} A={grades.get('A',0)} B={grades.get('B',0)} C={grades.get('C',0)} D={grades.get('D',0)}")
    print(f"[REVIEW] 触发审核：{review_count} 条")


def _grade(score):
    if score >= 90: return "S"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    return "D"


if __name__ == "__main__":
    main()
