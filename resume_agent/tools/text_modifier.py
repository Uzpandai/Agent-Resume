from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

from resume_agent.decision_maker import InputType
from resume_agent.llm_client import LLMClient


@dataclass
class ModifyRequest:
    markdown_text: str
    input_type: InputType
    target_role: Optional[str] = None
    job_description: Optional[str] = None  # 职位描述 JD
    locale: str = "zh-CN"


@dataclass
class ResumeSection:
    """简历的一个模块"""
    name: str  # 模块名称
    content: str
    enhanced_content: str = ""


@dataclass
class IndustryContext:
    """动态识别的行业上下文"""
    industry: str  # tech, finance, consulting, healthcare, education, marketing, hr, design, manufacturing, legal, general
    job_function: str  # engineering, management, sales, research, operations, creative, etc.
    seniority: str  # junior, mid, senior, executive
    hr_persona: str  # 动态生成的 HR 角色描述
    key_metrics: List[str]  # 该行业/岗位常用的量化指标
    strong_verbs: List[str]  # 该行业/岗位推荐的强动词
    few_shot_examples: str  # 行业特定的改写示例


class TextModifier:
    """
    基于高级 Prompt 工程的简历优化器（动态适配版）
    
    核心策略:
    1. 动态场景识别 - 根据简历+JD识别行业、岗位、级别
    2. 角色扮演提示(Role Prompting) - 动态生成行业特定HR角色
    3. 提供上下文信息 - JD + 简历内容 + 行业上下文
    4. 链式思维提示(Chain-of-Thought) - 分步骤分析优化
    5. 分段优化与多次交互 - 逐段打磨
    6. Few-Shot示例引导 - 行业特定的改写范例
    """

    # 模块识别关键词
    SECTION_PATTERNS = {
        "summary": r"(个人简介|自我评价|职业概述|Summary|Profile|About|概述)",
        "experience": r"(工作经历|工作经验|职业经历|Work Experience|Experience)",
        "projects": r"(项目经历|项目经验|Projects)",
        "education": r"(教育背景|教育经历|学历|Education)",
        "skills": r"(技能|专业技能|技术栈|Skills|Technical Skills)",
        "personal_info": r"(个人信息|基本信息|联系方式|Personal Info|Contact)",
    }

    # 行业特定配置
    INDUSTRY_CONFIG = {
        "tech": {
            "hr_persona": "你是一位在头部科技公司（如Google、阿里巴巴、字节跳动）工作了15年的资深技术招聘总监，面试过数千名工程师。",
            "key_metrics": ["QPS/TPS", "响应时间", "并发数", "系统可用性", "代码覆盖率", "用户数/DAU/MAU", "性能提升百分比", "成本降低", "bug修复数"],
            "strong_verbs": ["主导", "设计", "架构", "优化", "重构", "实现", "部署", "迁移", "自动化"],
            "focus_areas": ["技术选型理由", "架构设计", "性能优化", "系统稳定性", "技术难点攻克"],
        },
        "finance": {
            "hr_persona": "你是一位在顶级投行/四大会计师事务所工作了15年的资深招聘总监，深谙金融行业对合规性、风险控制和数据准确性的严格要求。",
            "key_metrics": ["AUM资产管理规模", "投资回报率ROI", "风险敞口", "合规率", "审计发现数", "交易量", "客户满意度", "成本节约金额"],
            "strong_verbs": ["管理", "审计", "分析", "合规", "优化", "评估", "监控", "预测", "对冲"],
            "focus_areas": ["风险控制能力", "合规意识", "数据分析能力", "金融产品理解", "客户关系管理"],
        },
        "consulting": {
            "hr_persona": "你是一位在MBB（麦肯锡、波士顿咨询、贝恩）工作了15年的资深合伙人，清楚咨询公司看重的问题解决能力和客户影响力。",
            "key_metrics": ["项目金额", "客户满意度NPS", "项目数量", "团队规模", "成本节约", "收入增长", "效率提升", "市场份额"],
            "strong_verbs": ["诊断", "设计", "推动", "交付", "影响", "说服", "领导", "协调", "整合"],
            "focus_areas": ["问题解决框架", "客户关系", "项目管理", "团队领导", "商业洞察"],
        },
        "healthcare": {
            "hr_persona": "你是一位在知名医疗机构/生物制药公司工作了15年的资深HR总监，深知医疗行业对专业资质、研究能力和合规性的重视。",
            "key_metrics": ["患者数量", "治愈率", "临床试验阶段", "论文发表数", "专利数", "研发周期缩短", "合规通过率", "成本效益"],
            "strong_verbs": ["诊断", "治疗", "研究", "开发", "验证", "审批", "培训", "协作", "创新"],
            "focus_areas": ["专业资质认证", "研究成果", "临床经验", "合规意识", "跨部门协作"],
        },
        "education": {
            "hr_persona": "你是一位在顶尖高校/教育机构工作了15年的资深人事主管，了解学术界和教育行业对教学能力、研究产出和学生影响的重视。",
            "key_metrics": ["学生数量", "课程评分", "论文引用数", "科研基金金额", "学生就业率", "课程开发数", "培训满意度"],
            "strong_verbs": ["教授", "指导", "研究", "发表", "开发", "培养", "评估", "创新", "推广"],
            "focus_areas": ["教学成果", "研究能力", "学生评价", "课程开发", "学术影响力"],
        },
        "marketing": {
            "hr_persona": "你是一位在知名品牌/4A广告公司工作了15年的资深市场总监，深知营销岗位需要展示的创意能力、数据驱动和商业结果。",
            "key_metrics": ["ROI投资回报率", "转化率", "获客成本CAC", "用户增长", "品牌知名度", "社媒粉丝数", "曝光量", "GMV销售额"],
            "strong_verbs": ["策划", "执行", "增长", "转化", "优化", "推广", "运营", "分析", "创意"],
            "focus_areas": ["营销ROI", "创意能力", "数据分析", "用户增长", "品牌建设"],
        },
        "hr": {
            "hr_persona": "你是一位在世界500强企业工作了15年的CHRO（首席人力资源官），精通人才招聘、组织发展和员工体验的全流程。",
            "key_metrics": ["招聘完成率", "员工留存率", "培训满意度", "人均效能", "招聘周期", "offer接受率", "员工满意度eNPS"],
            "strong_verbs": ["招聘", "培养", "激励", "评估", "规划", "沟通", "协调", "变革", "赋能"],
            "focus_areas": ["人才招聘", "员工发展", "组织文化", "薪酬绩效", "员工关系"],
        },
        "design": {
            "hr_persona": "你是一位在顶级设计公司/互联网大厂设计部门工作了15年的设计总监，清楚设计岗位需要展示的创意思维、用户洞察和商业价值。",
            "key_metrics": ["用户满意度", "转化率提升", "设计效率", "NPS提升", "用户研究数", "设计系统覆盖率", "A/B测试胜率"],
            "strong_verbs": ["设计", "创造", "迭代", "研究", "原型", "测试", "优化", "领导", "协作"],
            "focus_areas": ["作品集质量", "设计思维", "用户研究", "跨团队协作", "设计系统"],
        },
        "sales": {
            "hr_persona": "你是一位在世界500强企业工作了15年的销售VP，深知销售岗位需要展示的业绩数字、客户关系和商业敏锐度。",
            "key_metrics": ["销售额/GMV", "完成率", "新客户数", "客单价", "续约率", "回款率", "市场份额", "团队业绩"],
            "strong_verbs": ["开拓", "成交", "维护", "谈判", "突破", "超额完成", "建立", "拓展", "领导"],
            "focus_areas": ["销售业绩", "客户关系", "商务谈判", "市场开拓", "团队管理"],
        },
        "operations": {
            "hr_persona": "你是一位在知名企业工作了15年的COO（首席运营官），精通运营效率、流程优化和成本控制。",
            "key_metrics": ["运营效率", "成本降低", "SLA达成率", "流程周期缩短", "错误率降低", "产能提升", "库存周转"],
            "strong_verbs": ["优化", "管理", "协调", "改进", "监控", "执行", "整合", "标准化", "自动化"],
            "focus_areas": ["流程优化", "成本控制", "效率提升", "跨部门协调", "问题解决"],
        },
        "general": {
            "hr_persona": "你是一位拥有15年跨行业招聘经验的资深HR总监，熟悉各类岗位的核心能力要求和简历优化技巧。",
            "key_metrics": ["效率提升", "成本降低", "质量改进", "客户满意度", "团队规模", "项目数量", "时间节约"],
            "strong_verbs": ["主导", "管理", "优化", "推动", "建立", "协调", "实现", "改进", "领导"],
            "focus_areas": ["核心成就", "量化结果", "个人贡献", "团队协作", "问题解决"],
        },
    }

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client
        self.context: Optional[IndustryContext] = None

    def run(self, request: ModifyRequest) -> str:
        """
        主入口：执行简历优化
        
        流程:
        1. 动态识别行业上下文
        2. 分析阶段：对比JD和简历，找出差距
        3. 分段优化：逐段使用 Chain-of-Thought 优化
        4. 整合输出：合并所有优化后的内容
        """
        if not self.llm:
            return self._fallback_enhance(request.markdown_text)
        
        # Step 0: 动态识别行业上下文
        self.context = self._detect_industry_context(request)
        
        # Step 1: 分析阶段 - 以HR视角分析简历与JD的匹配度
        analysis = self._analyze_resume_vs_jd(request)
        
        # Step 2: 解析简历模块
        sections = self._parse_sections(request.markdown_text)
        
        # Step 3: 逐段优化（带入分析结论和行业上下文）
        for section in sections:
            section.enhanced_content = self._enhance_section_with_cot(
                section, request, analysis
            )
        
        # Step 4: 整合输出
        return self._merge_sections(sections)

    def _detect_industry_context(self, request: ModifyRequest) -> IndustryContext:
        """
        Step 0: 动态识别行业、岗位类型、级别
        根据简历内容和JD智能判断应该使用哪种优化策略
        """
        system_prompt = """你是一位经验丰富的职业规划专家，擅长分析简历和职位描述来判断行业和岗位特点。

请根据提供的简历内容和目标岗位，分析并返回JSON格式的结果。

## 行业分类（选择最匹配的一个）
- tech: 科技/互联网/软件开发
- finance: 金融/银行/保险/投资
- consulting: 咨询/管理顾问
- healthcare: 医疗/生物/制药
- education: 教育/学术/培训
- marketing: 市场营销/品牌/广告
- hr: 人力资源
- design: 设计/创意/UX
- sales: 销售/商务拓展
- operations: 运营/供应链/物流
- general: 其他/通用

## 岗位职能分类
- engineering: 工程/技术开发
- management: 管理/领导
- analysis: 分析/研究
- creative: 创意/设计
- client_facing: 客户facing/销售
- operations: 运营/执行
- support: 支持/服务

## 级别分类
- junior: 初级（0-2年经验）
- mid: 中级（3-5年经验）
- senior: 高级（6-10年经验）
- executive: 管理层/专家（10年以上）

请只返回JSON，格式如下：
{"industry": "xxx", "job_function": "xxx", "seniority": "xxx"}"""

        jd_info = f"\n\n目标职位：{request.target_role}" if request.target_role else ""
        if request.job_description:
            jd_info += f"\n\n职位描述：\n{request.job_description[:500]}"

        user_prompt = f"""请分析以下内容并返回JSON：

## 简历内容
{request.markdown_text[:1500]}
{jd_info}

请返回JSON："""

        # 默认上下文
        default_context = IndustryContext(
            industry="general",
            job_function="engineering",
            seniority="mid",
            hr_persona=self.INDUSTRY_CONFIG["general"]["hr_persona"],
            key_metrics=self.INDUSTRY_CONFIG["general"]["key_metrics"],
            strong_verbs=self.INDUSTRY_CONFIG["general"]["strong_verbs"],
            few_shot_examples=self._get_few_shot_examples("general", "engineering"),
        )

        try:
            response = self.llm.chat(system_prompt, user_prompt)
            # 解析 JSON
            import json
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(response[start:end])
                industry = data.get("industry", "general")
                job_function = data.get("job_function", "engineering")
                seniority = data.get("seniority", "mid")
                
                # 确保行业在配置中存在
                if industry not in self.INDUSTRY_CONFIG:
                    industry = "general"
                
                config = self.INDUSTRY_CONFIG[industry]
                
                return IndustryContext(
                    industry=industry,
                    job_function=job_function,
                    seniority=seniority,
                    hr_persona=config["hr_persona"],
                    key_metrics=config["key_metrics"],
                    strong_verbs=config["strong_verbs"],
                    few_shot_examples=self._get_few_shot_examples(industry, job_function),
                )
        except Exception:
            pass
        
        return default_context

    def _get_few_shot_examples(self, industry: str, job_function: str) -> str:
        """根据行业和岗位生成特定的 Few-Shot 示例"""
        
        examples = {
            "tech": """
## 改写示例（科技/互联网行业风格）

### 示例1：工作经历
**原文：** 负责后端开发工作。
**改写：** 主导核心交易系统后端架构设计与开发，采用微服务架构重构单体应用，将系统QPS从500提升至5000，响应时间从200ms优化至50ms，支撑日均百万级交易量。

### 示例2：项目经历
**原文：** 做过用户系统，负责登录注册模块。
**改写：** 主导用户认证中心重构，设计并实现基于JWT+Redis的分布式会话方案，替代原Session机制，将认证服务可用性从99.9%提升至99.99%，支撑500万DAU的认证需求。

### 示例3：技能描述
**原文：** 熟悉Java开发
**改写：** 精通Java生态体系（Spring Boot/Cloud、MyBatis、JVM调优），具备5年高并发系统开发经验，主导过3个核心系统从0到1的架构设计与落地。
""",
            "finance": """
## 改写示例（金融行业风格）

### 示例1：工作经历
**原文：** 负责风险管理工作。
**改写：** 主导建立公司信用风险评估体系，设计并实施涵盖500+风险指标的评分模型，将不良贷款率从2.3%降至1.5%，年度减少坏账损失约3000万元。

### 示例2：项目经历
**原文：** 参与了投资分析项目。
**改写：** 负责管理2亿元规模的量化投资组合，开发多因子选股模型，实现年化收益率18%，超越基准指数8个百分点，最大回撤控制在12%以内。

### 示例3：技能描述
**原文：** 会用Excel做数据分析
**改写：** 精通金融数据分析工具（Python/SQL/Excel VBA），熟练运用Wind、Bloomberg等金融终端，具备CFA二级资质，擅长财务建模与估值分析。
""",
            "consulting": """
## 改写示例（咨询行业风格）

### 示例1：工作经历
**原文：** 参与企业咨询项目。
**改写：** 独立负责某世界500强零售企业数字化转型项目（项目金额800万），带领4人团队完成全渠道战略诊断与落地方案设计，助力客户实现线上销售占比从15%提升至40%。

### 示例2：项目经历
**原文：** 做过组织架构优化的工作。
**改写：** 主导某金融集团组织效能提升项目，通过组织诊断与流程再造，精简冗余层级3层，优化审批流程40%，年度节约人力成本2000万元，客户NPS评分达9.5/10。

### 示例3：技能描述
**原文：** 有咨询项目经验
**改写：** 3年顶级咨询公司项目经验，累计服务15+家行业头部客户，擅长战略规划、运营优化与组织变革，精通MECE分析框架与假设驱动方法论。
""",
            "marketing": """
## 改写示例（市场营销行业风格）

### 示例1：工作经历
**原文：** 负责市场推广工作。
**改写：** 统筹年度5000万营销预算，策划并执行品牌全渠道整合营销战役，实现品牌搜索指数增长150%，获客成本降低35%，带动GMV同比增长80%。

### 示例2：项目经历
**原文：** 做过社交媒体运营。
**改写：** 从0到1搭建品牌私域运营体系，6个月内积累粉丝50万，构建10万人高活跃社群，实现私域GMV月均300万，复购率达45%，ROI 1:8。

### 示例3：技能描述
**原文：** 熟悉数字营销
**改写：** 精通全域营销（SEM/信息流/社媒/私域），具备品牌策略与效果营销双重能力，熟练运用Google Analytics、神策等数据分析工具，擅长A/B测试与增长实验。
""",
            "sales": """
## 改写示例（销售行业风格）

### 示例1：工作经历
**原文：** 负责客户销售工作。
**改写：** 独立负责华东区大客户销售，管理年销售额3000万的客户池，连续3年超额完成业绩目标（完成率120%+），新签客户30家，客户续约率达95%。

### 示例2：项目经历
**原文：** 拓展了一些新客户。
**改写：** 成功开拓某行业TOP 3客户（年合同额500万），从初次接触到签约仅用时3个月，创造团队最短大客户成交周期记录，该客户次年续约并追加采购200万。

### 示例3：技能描述
**原文：** 有销售经验
**改写：** 5年B2B大客户销售经验，累计管理销售额过亿，擅长复杂解决方案销售与高层关系突破，精通SPIN销售方法论与顾问式销售技巧。
""",
            "hr": """
## 改写示例（人力资源行业风格）

### 示例1：工作经历
**原文：** 负责招聘工作。
**改写：** 统筹年度300人招聘计划，优化招聘渠道组合与人才评估流程，将平均招聘周期从45天缩短至28天，关键岗位到岗率提升至95%，招聘成本降低20%。

### 示例2：项目经历
**原文：** 参与员工培训项目。
**改写：** 主导构建公司领导力发展体系，设计3阶梯人才培养计划，覆盖200名中高层管理者，培训满意度达4.8/5，内部晋升率从25%提升至40%。

### 示例3：技能描述
**原文：** 熟悉人力资源管理
**改写：** 8年人力资源全模块实战经验，精通招聘、培训、绩效与员工关系，持有人力资源管理师一级证书，熟练运用北森、SAP SuccessFactors等HR系统。
""",
            "design": """
## 改写示例（设计行业风格）

### 示例1：工作经历
**原文：** 负责产品UI设计。
**改写：** 主导核心产品设计升级，通过用户研究与设计迭代，将关键转化路径点击率提升40%，用户满意度NPS从30提升至55，设计方案在行业设计大赛中获银奖。

### 示例2：项目经历
**原文：** 做过APP设计改版。
**改写：** 从0到1构建产品设计系统，制定涵盖组件库、设计规范、交互模式的完整体系，将设计到开发交付效率提升60%，实现多端设计一致性覆盖率95%。

### 示例3：技能描述
**原文：** 会用Figma设计
**改写：** 精通设计全流程工具（Figma/Sketch/Principle/After Effects），具备完整的用户研究与数据驱动设计能力，作品入选站酷首页推荐，Dribbble粉丝2000+。
""",
        }
        
        return examples.get(industry, examples.get("tech", self._get_generic_examples()))

    def _get_generic_examples(self) -> str:
        """通用 Few-Shot 示例"""
        return """
## 改写示例（通用风格）

### 示例1：工作经历
**原文：** 负责管理团队工作。
**改写：** 领导10人跨职能团队，通过优化工作流程和引入敏捷管理方法，在6个月内将团队效率提升30%，项目交付准时率从75%提升至95%。

### 示例2：项目经历
**原文：** 参与了业务流程优化项目。
**改写：** 主导核心业务流程数字化改造，梳理并优化5个关键业务环节，将处理周期从7天缩短至2天，年度节约运营成本150万元，客户满意度提升20个百分点。

### 示例3：技能描述
**原文：** 有项目管理经验
**改写：** 5年项目管理经验，主导过20+项目从规划到交付，精通敏捷/瀑布双模管理方法，持有PMP认证，累计管理项目预算超3000万元。

---
改写要点：
- 量化成果（数字、百分比、金额、时间）
- 使用强动词（主导、设计、优化、推动、建立）
- 突出个人贡献和业务价值
- 匹配目标行业的关注点
"""

    def _analyze_resume_vs_jd(self, request: ModifyRequest) -> str:
        """
        Step 1: 以动态角色视角分析简历与JD的匹配度
        """
        # 使用动态识别的 HR 角色
        hr_persona = self.context.hr_persona if self.context else self.INDUSTRY_CONFIG["general"]["hr_persona"]
        key_metrics = self.context.key_metrics if self.context else self.INDUSTRY_CONFIG["general"]["key_metrics"]
        
        system_prompt = f"""{hr_persona}

你审阅过超过10000份简历，深知什么样的简历能打动招聘官。

该行业/岗位常用的量化指标包括：{', '.join(key_metrics)}

你的任务是：以招聘方视角，分析候选人简历与目标岗位的匹配度，找出改进空间。"""

        jd_section = ""
        if request.job_description:
            jd_section = f"""
## 目标职位描述(JD)
{request.job_description}
"""
        elif request.target_role:
            jd_section = f"""
## 目标职位
{request.target_role}
（未提供详细JD，请基于该岗位的通用要求进行分析）
"""

        user_prompt = f"""请以资深HR的视角，按以下步骤分析这份简历：
{jd_section}

## 候选人简历
{request.markdown_text[:3000]}

---

请按以下步骤进行分析（Chain-of-Thought）：

### 第一步：关键词匹配分析
列出目标岗位要求的核心技能/经验，对照简历检查哪些已覆盖、哪些缺失。

### 第二步：亮点与不足
- 简历中的亮点（招聘官会注意到的优势）
- 需要改进的地方（表述不清、缺乏量化、与岗位不匹配等）

### 第三步：优化方向建议
给出具体的优化方向，包括：
- 哪些经历需要重点突出
- 哪些内容需要补充或量化（建议使用的指标：{', '.join(key_metrics[:5])}）
- 如何调整表述以更好匹配岗位

请简洁输出，控制在500字以内。"""

        try:
            return self.llm.chat(system_prompt, user_prompt)
        except Exception:
            return ""

    def _parse_sections(self, markdown_text: str) -> List[ResumeSection]:
        """解析简历为多个模块"""
        sections = []
        lines = markdown_text.split("\n")
        
        current_section = None
        current_content = []
        
        for line in lines:
            if line.startswith("#"):
                if current_section:
                    sections.append(ResumeSection(
                        name=current_section,
                        content="\n".join(current_content)
                    ))
                current_section = self._identify_section_type(line)
                current_content = [line]
            else:
                current_content.append(line)
        
        if current_section:
            sections.append(ResumeSection(
                name=current_section,
                content="\n".join(current_content)
            ))
        
        if not sections:
            sections.append(ResumeSection(
                name="general",
                content=markdown_text
            ))
        
        return sections

    def _identify_section_type(self, title_line: str) -> str:
        """识别模块类型"""
        for section_type, pattern in self.SECTION_PATTERNS.items():
            if re.search(pattern, title_line, re.IGNORECASE):
                return section_type
        return "general"

    def _enhance_section_with_cot(
        self, 
        section: ResumeSection, 
        request: ModifyRequest,
        analysis: str
    ) -> str:
        """使用 Chain-of-Thought + Few-Shot 优化单个模块"""
        if not self.llm:
            return self._fallback_enhance(section.content)
        
        section_prompts = {
            "summary": self._build_summary_cot_prompt,
            "experience": self._build_experience_cot_prompt,
            "projects": self._build_projects_cot_prompt,
            "skills": self._build_skills_cot_prompt,
            "education": self._build_education_prompt,
            "personal_info": self._build_personal_info_prompt,
        }
        
        prompt_builder = section_prompts.get(section.name, self._build_general_cot_prompt)
        system_prompt, user_prompt = prompt_builder(section.content, request, analysis)
        
        try:
            return self.llm.chat(system_prompt, user_prompt)
        except Exception:
            return self._fallback_enhance(section.content)

    def _build_experience_cot_prompt(
        self, content: str, request: ModifyRequest, analysis: str
    ) -> Tuple[str, str]:
        """工作经历优化 - 动态角色 + CoT + Few-Shot"""
        
        hr_persona = self.context.hr_persona if self.context else self.INDUSTRY_CONFIG["general"]["hr_persona"]
        key_metrics = self.context.key_metrics if self.context else self.INDUSTRY_CONFIG["general"]["key_metrics"]
        strong_verbs = self.context.strong_verbs if self.context else self.INDUSTRY_CONFIG["general"]["strong_verbs"]
        few_shot = self.context.few_shot_examples if self.context else self._get_generic_examples()
        
        system_prompt = f"""{hr_persona}

你深知如何将普通的工作描述改写成能打动招聘官的专业表述。

{few_shot}

## 该行业/岗位常用指标
{', '.join(key_metrics)}

## 推荐使用的强动词
{', '.join(strong_verbs)}

## 输出要求
- 直接输出优化后的 Markdown 内容
- 不要输出分析过程，只输出最终结果
- 保持原有的时间线和公司信息
- 每条经历 2-4 个要点"""

        target_info = f"目标岗位：{request.target_role}" if request.target_role else ""
        jd_info = f"职位要求：{request.job_description[:800]}" if request.job_description else ""
        analysis_info = f"HR分析建议：{analysis[:500]}" if analysis else ""

        user_prompt = f"""请优化以下工作经历部分。

## 背景信息
{target_info}
{jd_info}
{analysis_info}

## 原始内容
{content}

---

请按以下思考步骤优化（但只输出最终结果）：

1. **识别核心成就**：这段经历中最能体现价值的成果是什么？
2. **量化思考**：用哪些指标量化成果？（推荐：{', '.join(key_metrics[:4])}）
3. **动词优化**：用什么强动词开头？（推荐：{', '.join(strong_verbs[:4])}）
4. **与岗位对齐**：如何调整表述以更好匹配目标岗位？

请直接输出优化后的工作经历 Markdown："""

        return system_prompt, user_prompt

    def _build_projects_cot_prompt(
        self, content: str, request: ModifyRequest, analysis: str
    ) -> Tuple[str, str]:
        """项目经历优化"""
        
        hr_persona = self.context.hr_persona if self.context else self.INDUSTRY_CONFIG["general"]["hr_persona"]
        key_metrics = self.context.key_metrics if self.context else self.INDUSTRY_CONFIG["general"]["key_metrics"]
        few_shot = self.context.few_shot_examples if self.context else self._get_generic_examples()
        industry = self.context.industry if self.context else "general"
        
        # 根据行业调整关注点
        focus_areas = self.INDUSTRY_CONFIG.get(industry, self.INDUSTRY_CONFIG["general"]).get("focus_areas", [])
        
        system_prompt = f"""{hr_persona}

你清楚招聘官在项目经历中关注的重点：{', '.join(focus_areas)}

{few_shot}

## 输出要求
- 直接输出优化后的 Markdown 内容
- 每个项目包含：项目背景(1句话)、核心职责、量化成果
- 突出个人贡献和业务价值"""

        target_info = f"目标岗位：{request.target_role}" if request.target_role else ""
        analysis_info = f"HR分析建议：{analysis[:500]}" if analysis else ""

        user_prompt = f"""请优化以下项目经历部分。

## 背景信息
{target_info}
{analysis_info}

## 原始内容
{content}

---

请按以下思考步骤优化（但只输出最终结果）：

1. **项目价值**：这个项目解决了什么业务问题？
2. **核心贡献**：候选人的具体职责和独特贡献是什么？
3. **量化成果**：用哪些指标量化？（推荐：{', '.join(key_metrics[:4])}）
4. **行业关注点**：如何体现{', '.join(focus_areas[:3])}？

请直接输出优化后的项目经历 Markdown："""

        return system_prompt, user_prompt

    def _build_summary_cot_prompt(
        self, content: str, request: ModifyRequest, analysis: str
    ) -> Tuple[str, str]:
        """个人简介/Summary优化"""
        
        hr_persona = self.context.hr_persona if self.context else self.INDUSTRY_CONFIG["general"]["hr_persona"]
        seniority = self.context.seniority if self.context else "mid"
        
        seniority_guidance = {
            "junior": "突出学习能力、成长潜力和相关实习/项目经验",
            "mid": "突出核心技能、主要成就和职业发展方向",
            "senior": "突出专业深度、领导经验和行业影响力",
            "executive": "突出战略视野、管理成就和商业价值",
        }
        
        system_prompt = f"""{hr_persona}

你深知个人简介是简历的"电梯演讲"，招聘官平均只花6秒扫一眼简历。

对于{seniority}级别的候选人，应该：{seniority_guidance.get(seniority, seniority_guidance['mid'])}

## 优秀Summary的特点
- 简洁有力：2-3句话，不超过80字
- 结构清晰：身份定位 + 核心优势 + 关键成就
- 避免空话：不用"认真负责"、"积极主动"等空洞形容词
- 数字说话：用量化成果证明能力

## 输出要求
直接输出优化后的个人简介，2-3句话"""

        target_info = f"目标岗位：{request.target_role}" if request.target_role else ""
        analysis_info = f"优化方向：{analysis[:300]}" if analysis else ""

        user_prompt = f"""请优化以下个人简介。

{target_info}
{analysis_info}

## 原始内容
{content}

---

思考步骤（只输出最终结果）：
1. 候选人的核心身份定位是什么？
2. 最突出的2-3个核心优势是什么？
3. 最有说服力的1个量化成就是什么？

请直接输出优化后的个人简介（2-3句话）："""

        return system_prompt, user_prompt

    def _build_skills_cot_prompt(
        self, content: str, request: ModifyRequest, analysis: str
    ) -> Tuple[str, str]:
        """技能模块优化"""
        
        hr_persona = self.context.hr_persona if self.context else self.INDUSTRY_CONFIG["general"]["hr_persona"]
        industry = self.context.industry if self.context else "general"
        
        system_prompt = f"""{hr_persona}

你清楚如何组织技能列表以吸引招聘官注意。

## 技能列表最佳实践
- 分类组织：按技能类型分组展示
- 优先级排序：将最相关、最擅长的技能放在最前面
- 适度标注熟练度：精通/熟练/了解（可选）
- 与岗位对齐：确保目标岗位要求的技能都有体现

## 输出要求
直接输出优化后的技能列表 Markdown"""

        target_info = f"目标岗位：{request.target_role}" if request.target_role else ""
        jd_info = f"职位要求：{request.job_description[:500]}" if request.job_description else ""
        analysis_info = f"缺失技能提示：{analysis[:300]}" if analysis else ""

        user_prompt = f"""请优化以下技能列表。

{target_info}
{jd_info}
{analysis_info}

## 原始内容
{content}

---

思考步骤（只输出最终结果）：
1. 目标岗位要求了哪些关键技能？简历中是否都有体现？
2. 如何分类组织这些技能更清晰？
3. 哪些技能应该放在最前面以匹配目标岗位？

请直接输出优化后的技能列表 Markdown："""

        return system_prompt, user_prompt

    def _build_education_prompt(
        self, content: str, request: ModifyRequest, analysis: str
    ) -> Tuple[str, str]:
        """教育背景优化"""
        
        system_prompt = """你是一位简历优化专家。

## 教育背景格式要求
- 格式统一：学校 | 专业 | 学历 | 时间
- 突出亮点：GPA(如果>3.5)、荣誉奖项、相关课程
- 保持简洁：每条1-2行

## 输出要求
直接输出优化后的教育背景 Markdown"""

        user_prompt = f"""请整理以下教育背景。

## 原始内容
{content}

请直接输出格式规范的教育背景 Markdown："""

        return system_prompt, user_prompt

    def _build_personal_info_prompt(
        self, content: str, request: ModifyRequest, analysis: str
    ) -> Tuple[str, str]:
        """个人信息优化"""
        
        system_prompt = """你是一位简历优化专家。

## 个人信息格式要求
- 必要信息：姓名、电话、邮箱、所在城市
- 可选信息：LinkedIn、个人网站、作品集链接
- 删除不必要信息：身份证号、详细地址、婚姻状况

## 输出要求
直接输出整理后的个人信息 Markdown"""

        user_prompt = f"""请整理以下个人信息。

## 原始内容
{content}

请直接输出格式规范的个人信息 Markdown："""

        return system_prompt, user_prompt

    def _build_general_cot_prompt(
        self, content: str, request: ModifyRequest, analysis: str
    ) -> Tuple[str, str]:
        """通用优化 prompt"""
        
        hr_persona = self.context.hr_persona if self.context else self.INDUSTRY_CONFIG["general"]["hr_persona"]
        few_shot = self.context.few_shot_examples if self.context else self._get_generic_examples()
        key_metrics = self.context.key_metrics if self.context else self.INDUSTRY_CONFIG["general"]["key_metrics"]
        strong_verbs = self.context.strong_verbs if self.context else self.INDUSTRY_CONFIG["general"]["strong_verbs"]
        
        guidance = {
            InputType.RAW_TEXT: "这是一段非正式的经历描述，需要整理成专业的简历格式。",
            InputType.MATURE_RESUME: "这是一份已有的简历，需要微调措辞并增强成果表达。",
            InputType.IMMATURE_RESUME: "这是一份需要大幅修改的简历，需要重构结构并统一风格。",
        }.get(request.input_type, "请优化以下简历内容。")

        system_prompt = f"""{hr_persona}

## 背景
{guidance}

{few_shot}

## 输出要求
直接输出优化后的 Markdown 内容"""

        target_info = f"目标岗位：{request.target_role}" if request.target_role else ""
        analysis_info = f"优化方向：{analysis[:500]}" if analysis else ""

        user_prompt = f"""请优化以下简历内容。

{target_info}
{analysis_info}

## 原始内容
{content}

---

请按以下思考步骤优化（但只输出最终结果）：
1. 内容中有哪些可以量化的成果？（推荐指标：{', '.join(key_metrics[:4])}）
2. 可以用什么强动词让表述更有力？（推荐：{', '.join(strong_verbs[:4])}）
3. 如何调整结构使其更清晰专业？

请直接输出优化后的 Markdown："""

        return system_prompt, user_prompt

    def _merge_sections(self, sections: List[ResumeSection]) -> str:
        """合并所有优化后的模块"""
        parts = []
        for section in sections:
            content = section.enhanced_content or section.content
            content = re.sub(r'\n{3,}', '\n\n', content.strip())
            parts.append(content)
        return "\n\n".join(parts)

    def _fallback_enhance(self, content: str) -> str:
        """无 LLM 时的降级处理"""
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        result = []
        for line in lines:
            if line.startswith("#"):
                result.append(line)
            elif line.startswith("-") or line.startswith("*"):
                result.append(line)
            else:
                result.append(f"- {line}")
        return "\n".join(result)
