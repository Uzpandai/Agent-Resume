from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

from resume_agent.tools.magic_resume_builder import (
    MagicResumeBuilder,
    MagicResumeDocxBuilder,
)


@dataclass
class GenerateRequest:
    """简历生成请求"""
    markdown_text: str
    output_dir: Path
    output_format: str  # pdf, docx, json
    candidate_name: str = "候选人"
    template_id: str = "classic"  # 模板: classic, modern, left-right, timeline
    
    # 结构化数据（可选，如果提供则优先使用）
    basic_info: Optional[Dict[str, str]] = None
    education: List[Dict[str, Any]] = field(default_factory=list)
    experience: List[Dict[str, Any]] = field(default_factory=list)
    projects: List[Dict[str, Any]] = field(default_factory=list)
    skills: str = ""


class ResumeGenerator:
    """
    简历生成器
    
    支持两种模式:
    1. 传统模式: 基于 Markdown 生成 LaTeX PDF 或 Word
    2. Magic Resume 模式: 生成 Magic Resume JSON 格式，并支持导出 Word/PDF
    """

    def run(self, request: GenerateRequest) -> Path:
        """主入口：根据请求生成简历"""
        request.output_dir.mkdir(parents=True, exist_ok=True)

        # 保存原始 Markdown
        md_path = request.output_dir / "resume.md"
        md_path.write_text(request.markdown_text, encoding="utf-8")

        # 根据输出格式选择生成方式
        output_format = request.output_format.lower()
        
        if output_format == "json":
            return self._generate_magic_json(request)
        elif output_format in ("docx", "word"):
            return self._generate_docx(request)
        elif output_format == "pdf":
            return self._generate_pdf(request)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    def _generate_magic_json(self, request: GenerateRequest) -> Path:
        """生成 Magic Resume JSON 格式"""
        builder = self._build_magic_resume(request)
        
        json_path = request.output_dir / "resume.json"
        builder.to_json(json_path)
        
        return json_path

    def _generate_docx(self, request: GenerateRequest) -> Path:
        """生成 Word 文档"""
        builder = self._build_magic_resume(request)
        json_data = builder.build()
        
        # 同时保存 JSON
        json_path = request.output_dir / "resume.json"
        builder.to_json(json_path)
        
        # 生成 Word
        docx_path = request.output_dir / "resume.docx"
        docx_builder = MagicResumeDocxBuilder(json_data)
        docx_builder.save(str(docx_path))
        
        return docx_path

    def _is_magic_resume_running(self, url: str = "http://localhost:3000") -> bool:
        """检查本地 Magic Resume 是否在运行"""
        import requests
        try:
            response = requests.get(url, timeout=2)
            return response.status_code == 200
        except:
            return False

    def _generate_pdf_via_magic_api(self, html_content: str, styles: str, pdf_path: Path, margin: int = 40) -> bool:
        """
        调用 Magic Resume 云端 API 生成 PDF
        
        这是最推荐的方式，效果与 Magic Resume 前端完全一致
        """
        import requests
        
        url = "https://api.magicv.art/generate-pdf"
        
        # 模拟浏览器请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/json',
            'Origin': 'http://localhost:3000',
            'Referer': 'http://localhost:3000/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
        }
        
        data = {
            'content': html_content,
            'styles': styles,
            'margin': margin
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=60)
        
        if response.status_code == 200:
            pdf_path.write_bytes(response.content)
            return True
        else:
            print(f"Magic Resume API 返回错误: {response.status_code} - {response.text[:200]}")
            return False

    def _generate_pdf(
        self, 
        request: GenerateRequest, 
        use_local_fallback: bool = False,
        magic_resume_url: str = "http://localhost:3000"
    ) -> Path:
        """
        生成 PDF
        
        策略优先级:
        1. 如果本地 Magic Resume 在运行 -> 使用它（真正的模板效果）
        2. 否则使用 Magic Resume 云端 API（自定义 CSS 样式）
        3. 如果 use_local_fallback=True，尝试本地 Pyppeteer 方案
        """
        # 先生成 Word 和 JSON
        builder = self._build_magic_resume(request)
        json_data = builder.build()
        
        # 保存 JSON
        json_path = request.output_dir / "resume.json"
        builder.to_json(json_path)
        
        # 生成 Word
        docx_path = request.output_dir / "resume.docx"
        docx_builder = MagicResumeDocxBuilder(json_data)
        docx_builder.save(str(docx_path))
        
        pdf_path = request.output_dir / "resume.pdf"
        
        # 生成 HTML（用于备份和调试）
        html_content = self._render_full_html(json_data)
        html_path = request.output_dir / "resume.html"
        html_path.write_text(html_content, encoding="utf-8")
        
        # 方案1: 检查本地 Magic Resume 是否在运行
        # 如果运行，优先使用它（真正的模板效果，由 React 渲染）
        if self._is_magic_resume_running(magic_resume_url):
            print(f"检测到本地 Magic Resume 正在运行 ({magic_resume_url})")
            try:
                if self._generate_pdf_via_magic_resume_local(json_data, pdf_path, magic_resume_url):
                    print(f"✅ 使用 Magic Resume 本地前端生成 PDF 成功 (模板: {json_data.get('templateId', 'classic')})")
                    return pdf_path
            except Exception as e:
                print(f"Magic Resume 本地前端失败: {e}")
        
        # 方案2: Magic Resume 云端 API（自定义 CSS 模拟模板样式）
        try:
            full_html = self._render_full_html(json_data)
            
            if self._generate_pdf_via_magic_api(full_html, "", pdf_path):
                print("✅ 使用 Magic Resume API 生成 PDF 成功（注：使用自定义 CSS，非原生模板）")
                return pdf_path
        except Exception as e:
            print(f"Magic Resume API 失败: {e}")
        
        # 如果不使用本地回退，直接返回 DOCX
        if not use_local_fallback:
            print("API 失败，返回 DOCX（如需本地 PDF 生成，请设置 use_local_fallback=True）")
            return docx_path
        
        # 以下是本地回退方案（需要额外下载/安装）
        
        # 本地方案1: Pyppeteer（需要下载 Chromium ~170MB）
        try:
            if self._generate_pdf_via_puppeteer(html_path, pdf_path):
                print("使用 Pyppeteer 生成 PDF 成功")
                return pdf_path
        except Exception as e:
            print(f"Pyppeteer 失败: {e}")
        
        # 本地方案2: WeasyPrint（需要系统库）
        try:
            from weasyprint import HTML, CSS
            HTML(string=html_content).write_pdf(
                str(pdf_path),
                stylesheets=[CSS(string=self._get_pdf_css())]
            )
            if pdf_path.exists():
                print("使用 WeasyPrint 生成 PDF 成功")
                return pdf_path
        except ImportError:
            pass
        except Exception as e:
            print(f"WeasyPrint 失败: {e}")
        
        # 如果都失败，返回 Word 文件
        print("所有 PDF 方案失败，返回 DOCX")
        return docx_path

    def _generate_pdf_via_puppeteer(self, html_path: Path, pdf_path: Path) -> bool:
        """使用 Pyppeteer (无头 Chrome) 生成 PDF - 与 Magic Resume 相同技术"""
        import asyncio
        
        async def _generate():
            from pyppeteer import launch
            
            browser = await launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            try:
                page = await browser.newPage()
                
                # 加载 HTML 文件
                await page.goto(f'file://{html_path.absolute()}', waitUntil='networkidle0')
                
                # 生成 PDF
                await page.pdf({
                    'path': str(pdf_path),
                    'format': 'A4',
                    'printBackground': True,
                    'margin': {
                        'top': '1cm',
                        'bottom': '1cm',
                        'left': '1.27cm',
                        'right': '1.27cm'
                    }
                })
                
                return pdf_path.exists()
            finally:
                await browser.close()
        
        # 运行异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_generate())
        finally:
            loop.close()

    def _generate_pdf_via_magic_resume_local(
        self, 
        json_data: Dict[str, Any], 
        pdf_path: Path,
        magic_resume_url: str = "http://localhost:3000"
    ) -> bool:
        """
        通过本地运行的 Magic Resume 前端生成 PDF
        
        前提条件: Magic Resume 正在本地运行 (pnpm dev)
        
        工作流程:
        1. 将 JSON 数据注入到 Magic Resume 的 localStorage（Zustand persist 格式）
        2. 使用 Puppeteer 打开 Magic Resume 页面
        3. 等待 React 渲染模板后导出 PDF
        """
        import asyncio
        import json
        
        async def _generate():
            from pyppeteer import launch
            
            browser = await launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            try:
                page = await browser.newPage()
                
                # 设置视口大小 (A4 比例)
                await page.setViewport({'width': 794, 'height': 1123})
                
                # 先访问页面
                await page.goto(magic_resume_url, waitUntil='networkidle0')
                
                # 构建 Zustand persist 格式的数据
                # resumes 是 Record<string, ResumeData>，不是数组
                resume_id = json_data.get("id", "default-resume")
                store_data = {
                    "state": {
                        "resumes": {
                            resume_id: json_data
                        },
                        "activeResumeId": resume_id,
                        "activeResume": json_data
                    },
                    "version": 0
                }
                
                # 注入简历数据到 localStorage
                store_json = json.dumps(store_data, ensure_ascii=False)
                await page.evaluate(f'''() => {{
                    localStorage.setItem('resume-store', `{store_json.replace('`', '\\`')}`);
                }}''')
                
                # 访问工作台预览页面
                await page.goto(f'{magic_resume_url}/app/workbench', waitUntil='networkidle0')
                
                # 等待简历内容渲染
                await asyncio.sleep(2)  # 等待 React 渲染
                
                try:
                    await page.waitForSelector('#resume-preview', timeout=15000)
                except:
                    print("警告: 未找到 #resume-preview 元素，尝试继续...")
                
                await asyncio.sleep(1)  # 额外等待动画完成
                
                # 生成 PDF
                await page.pdf({
                    'path': str(pdf_path),
                    'format': 'A4',
                    'printBackground': True,
                    'margin': {
                        'top': '0',
                        'bottom': '0',
                        'left': '0',
                        'right': '0'
                    }
                })
                
                return pdf_path.exists()
            finally:
                await browser.close()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_generate())
        finally:
            loop.close()

    def _render_full_html(self, json_data: Dict[str, Any]) -> str:
        """渲染完整的 HTML（包含内联 CSS）"""
        template_id = json_data.get("templateId", "classic")
        body_content = self._render_html_body(json_data)
        css = self._get_pdf_css(template_id)
        
        # 为不同模板添加不同的 body class
        body_class = f"template-{template_id}"
        
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>简历</title>
    <style>
{css}
    </style>
</head>
<body class="{body_class}">
{body_content}
</body>
</html>"""

    def _render_html_body(self, json_data: Dict[str, Any]) -> str:
        """
        将 Magic Resume JSON 渲染为 HTML body 内容
        
        根据 templateId 生成不同的 HTML 结构：
        - classic: 单栏居中布局
        - modern: 两栏布局（左侧基本信息，右侧其他内容）
        - left-right: 单栏左对齐，标题有背景色
        - timeline: 时间线风格
        """
        template_id = json_data.get("templateId", "classic")
        basic = json_data.get("basic", {})
        education = json_data.get("education", [])
        experience = json_data.get("experience", [])
        projects = json_data.get("projects", [])
        skill_content = json_data.get("skillContent", "")
        global_settings = json_data.get("globalSettings", {})
        theme_color = global_settings.get("themeColor", "#000000")
        
        # 根据模板选择渲染方法
        if template_id == "modern":
            return self._render_modern_template(basic, education, experience, projects, skill_content, theme_color)
        elif template_id == "timeline":
            return self._render_timeline_template(basic, education, experience, projects, skill_content, theme_color)
        else:
            # classic 和 left-right 使用相同的单栏结构，区别在 CSS
            return self._render_classic_template(basic, education, experience, projects, skill_content, template_id)
    
    def _render_basic_info(self, basic: Dict[str, Any], layout: str = "center") -> str:
        """渲染基本信息部分"""
        html_parts = []
        name = basic.get("name", "")
        title = basic.get("title", "")
        
        if name:
            html_parts.append(f'<h1 class="name">{name}</h1>')
        if title:
            html_parts.append(f'<p class="title">{title}</p>')
        
        # 联系方式
        contact_parts = []
        for key in ["email", "phone", "location"]:
            value = basic.get(key, "")
            if value:
                contact_parts.append(value)
        if contact_parts:
            html_parts.append(f'<p class="contact">{" | ".join(contact_parts)}</p>')
        
        return '\n'.join(html_parts)
    
    def _render_section_items(self, section_type: str, items: list) -> str:
        """渲染教育/经历/项目等条目"""
        html_parts = []
        
        for item in items:
            if not item.get("visible", True):
                continue
            
            if section_type == "education":
                school = item.get("school", "")
                degree = item.get("degree", "")
                major = item.get("major", "")
                header = " | ".join([p for p in [school, degree, major] if p])
                date_str = item.get("date", "")
                if not date_str:
                    start = item.get("startDate", "")
                    end = item.get("endDate", "")
                    if start or end:
                        date_str = f"{start[:7] if start else ''} - {end[:7] if end else ''}"
                content = item.get("description", "")
                
            elif section_type == "experience":
                company = item.get("company", "")
                position = item.get("position", "")
                header = f"{company} | {position}" if company and position else company or position
                date_str = item.get("date", "")
                content = item.get("details", "")
                
            elif section_type == "projects":
                name = item.get("name", "")
                role = item.get("role", "")
                header = f"{name} | {role}" if name and role else name or role
                date_str = item.get("date", "")
                content = item.get("description", "")
            else:
                continue
            
            html_parts.append('<div class="item">')
            html_parts.append(f'<div class="item-header"><span class="item-title">{header}</span>')
            if date_str:
                html_parts.append(f'<span class="item-date">{date_str}</span>')
            html_parts.append('</div>')
            if content:
                html_parts.append(f'<div class="item-content">{content}</div>')
            html_parts.append('</div>')
        
        return '\n'.join(html_parts)
    
    def _render_classic_template(self, basic, education, experience, projects, skill_content, template_id) -> str:
        """渲染 Classic / Left-Right 模板（单栏布局）"""
        html_parts = []
        
        # 基本信息
        html_parts.append(self._render_basic_info(basic))
        
        # 教育经历
        if education:
            html_parts.append('<h2>教育经历</h2>')
            html_parts.append(self._render_section_items("education", education))
        
        # 工作经历
        if experience:
            html_parts.append('<h2>工作经验</h2>')
            html_parts.append(self._render_section_items("experience", experience))
        
        # 项目经历
        if projects:
            html_parts.append('<h2>项目经历</h2>')
            html_parts.append(self._render_section_items("projects", projects))
        
        # 技能
        if skill_content:
            html_parts.append('<h2>专业技能</h2>')
            html_parts.append(f'<div class="skills">{skill_content}</div>')
        
        return '\n'.join(html_parts)
    
    def _render_modern_template(self, basic, education, experience, projects, skill_content, theme_color) -> str:
        """
        渲染 Modern 模板（两栏布局）
        
        参考 Magic Resume 的 ModernTemplate.tsx:
        - 左侧 1/3: 基本信息 + 技能（主题色背景）
        - 右侧 2/3: 教育、工作、项目经历
        """
        # 左侧内容
        left_parts = []
        left_parts.append(self._render_basic_info(basic, "left"))
        if skill_content:
            left_parts.append('<div class="sidebar-section">')
            left_parts.append('<h3>专业技能</h3>')
            left_parts.append(f'<div class="skills">{skill_content}</div>')
            left_parts.append('</div>')
        
        # 右侧内容
        right_parts = []
        if education:
            right_parts.append('<h2>教育经历</h2>')
            right_parts.append(self._render_section_items("education", education))
        if experience:
            right_parts.append('<h2>工作经验</h2>')
            right_parts.append(self._render_section_items("experience", experience))
        if projects:
            right_parts.append('<h2>项目经历</h2>')
            right_parts.append(self._render_section_items("projects", projects))
        
        # 两栏布局
        return f'''<div class="modern-layout">
    <div class="modern-sidebar" style="background-color: {theme_color}; color: #ffffff;">
        {chr(10).join(left_parts)}
    </div>
    <div class="modern-main">
        {chr(10).join(right_parts)}
    </div>
</div>'''
    
    def _render_timeline_template(self, basic, education, experience, projects, skill_content, theme_color) -> str:
        """
        渲染 Timeline 模板（时间线风格）
        
        特点：名称右对齐，条目带时间线装饰
        """
        html_parts = []
        
        # 基本信息（右对齐）
        name = basic.get("name", "")
        title = basic.get("title", "")
        if name:
            html_parts.append(f'<h1 class="name" style="text-align: right;">{name}</h1>')
        if title:
            html_parts.append(f'<p class="title" style="text-align: right;">{title}</p>')
        
        contact_parts = []
        for key in ["email", "phone", "location"]:
            value = basic.get(key, "")
            if value:
                contact_parts.append(value)
        if contact_parts:
            html_parts.append(f'<p class="contact" style="text-align: right; border-bottom: 2px solid {theme_color}; padding-bottom: 10pt;">{" | ".join(contact_parts)}</p>')
        
        # 时间线样式的条目
        def render_timeline_items(items, section_type):
            result = []
            for item in items:
                if not item.get("visible", True):
                    continue
                
                if section_type == "education":
                    header = " | ".join([p for p in [item.get("school", ""), item.get("degree", ""), item.get("major", "")] if p])
                    date_str = item.get("date", "") or f"{item.get('startDate', '')[:7] if item.get('startDate') else ''} - {item.get('endDate', '')[:7] if item.get('endDate') else ''}"
                    content = item.get("description", "")
                elif section_type == "experience":
                    header = f"{item.get('company', '')} | {item.get('position', '')}"
                    date_str = item.get("date", "")
                    content = item.get("details", "")
                elif section_type == "projects":
                    header = f"{item.get('name', '')} | {item.get('role', '')}"
                    date_str = item.get("date", "")
                    content = item.get("description", "")
                else:
                    continue
                
                result.append(f'''<div class="timeline-item">
    <div class="timeline-dot" style="background-color: {theme_color};"></div>
    <div class="timeline-content">
        <div class="item-header">
            <span class="item-date">{date_str}</span>
            <span class="item-title">{header}</span>
        </div>
        {f'<div class="item-content">{content}</div>' if content else ''}
    </div>
</div>''')
            return '\n'.join(result)
        
        if education:
            html_parts.append(f'<h2 style="background: #f1f5f9; padding: 6pt 12pt; border-left: 4px solid {theme_color};">教育经历</h2>')
            html_parts.append(f'<div class="timeline-section">{render_timeline_items(education, "education")}</div>')
        
        if experience:
            html_parts.append(f'<h2 style="background: #f1f5f9; padding: 6pt 12pt; border-left: 4px solid {theme_color};">工作经验</h2>')
            html_parts.append(f'<div class="timeline-section">{render_timeline_items(experience, "experience")}</div>')
        
        if projects:
            html_parts.append(f'<h2 style="background: #f1f5f9; padding: 6pt 12pt; border-left: 4px solid {theme_color};">项目经历</h2>')
            html_parts.append(f'<div class="timeline-section">{render_timeline_items(projects, "projects")}</div>')
        
        if skill_content:
            html_parts.append(f'<h2 style="background: #f1f5f9; padding: 6pt 12pt; border-left: 4px solid {theme_color};">专业技能</h2>')
            html_parts.append(f'<div class="skills">{skill_content}</div>')
        
        return '\n'.join(html_parts)

    def _get_pdf_css(self, template_id: str = "classic") -> str:
        """
        获取 PDF 生成用的 CSS 样式
        
        根据不同模板返回不同的样式：
        - classic: 经典单栏，标题居中，简约稳重
        - modern: 两栏布局，现代感强
        - left-right: 标题带背景色，视觉突出
        - timeline: 时间线风格，强调时间顺序
        """
        
        # 基础样式（所有模板共用）
        base_css = """
        @page {
            size: A4;
            margin: 1.5cm;
        }
        
        * {
            box-sizing: border-box;
        }
        
        body {
            font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
            font-size: 10pt;
            line-height: 1.5;
            color: #333;
            margin: 0;
            padding: 0;
        }
        
        .item {
            margin-bottom: 12pt;
            page-break-inside: avoid;
        }
        
        .item-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 4pt;
        }
        
        .item-title {
            font-weight: bold;
            font-size: 10pt;
        }
        
        .item-date {
            font-size: 9pt;
            color: #666;
            white-space: nowrap;
        }
        
        .item-content {
            font-size: 10pt;
        }
        
        .item-content ul {
            margin: 4pt 0;
            padding-left: 18pt;
        }
        
        .item-content li {
            margin-bottom: 3pt;
        }
        
        strong {
            font-weight: 600;
        }
        """
        
        # Classic 模板 - 经典简约
        if template_id == "classic":
            return base_css + """
        /* Classic Template - 经典简约 */
        h1.name {
            font-size: 22pt;
            font-weight: bold;
            text-align: center;
            margin: 0 0 6pt 0;
            color: #000;
        }
        
        p.title {
            font-size: 11pt;
            text-align: center;
            color: #555;
            margin: 0 0 4pt 0;
        }
        
        p.contact {
            font-size: 9pt;
            text-align: center;
            color: #666;
            margin: 0 0 16pt 0;
        }
        
        h2 {
            font-size: 12pt;
            font-weight: bold;
            color: #000;
            border-bottom: 2px solid #000;
            padding-bottom: 4pt;
            margin: 14pt 0 10pt 0;
            text-transform: uppercase;
            letter-spacing: 1pt;
        }
        """
        
        # Modern 模板 - 现代两栏风格（参考 Magic Resume ModernTemplate.tsx）
        elif template_id == "modern":
            return base_css + """
        /* Modern Template - 两栏布局 */
        
        /* 两栏容器 */
        .modern-layout {
            display: grid;
            grid-template-columns: 1fr 2fr;
            min-height: 100%;
            gap: 0;
        }
        
        /* 左侧栏（主题色背景） */
        .modern-sidebar {
            padding: 20pt 16pt;
            color: #ffffff;
        }
        
        .modern-sidebar h1.name {
            font-size: 20pt;
            font-weight: 700;
            color: #ffffff;
            margin: 0 0 8pt 0;
            text-align: left;
        }
        
        .modern-sidebar p.title {
            font-size: 11pt;
            color: rgba(255,255,255,0.9);
            margin: 0 0 4pt 0;
        }
        
        .modern-sidebar p.contact {
            font-size: 9pt;
            color: rgba(255,255,255,0.8);
            margin: 0 0 16pt 0;
        }
        
        .modern-sidebar .sidebar-section {
            margin-top: 16pt;
            padding-top: 12pt;
            border-top: 1px solid rgba(255,255,255,0.3);
        }
        
        .modern-sidebar h3 {
            font-size: 10pt;
            font-weight: 600;
            color: #ffffff;
            margin: 0 0 8pt 0;
            text-transform: uppercase;
            letter-spacing: 1pt;
        }
        
        .modern-sidebar .skills {
            font-size: 9pt;
            color: rgba(255,255,255,0.9);
            line-height: 1.6;
        }
        
        /* 右侧主内容区 */
        .modern-main {
            padding: 20pt 20pt 20pt 16pt;
            background: #ffffff;
        }
        
        .modern-main h2 {
            font-size: 11pt;
            font-weight: 600;
            color: #000;
            border-bottom: 2px solid #000;
            padding-bottom: 4pt;
            margin: 0 0 12pt 0;
            text-transform: uppercase;
            letter-spacing: 1pt;
        }
        
        .modern-main .item {
            margin-bottom: 14pt;
        }
        
        .modern-main .item-title {
            color: #1a1a2e;
            font-weight: 600;
        }
        
        .modern-main .item-date {
            color: #666;
        }
        
        /* 非两栏模式下的默认样式 */
        h1.name {
            font-size: 22pt;
            font-weight: bold;
            text-align: center;
            margin: 0 0 6pt 0;
            color: #000;
        }
        
        p.title {
            font-size: 11pt;
            text-align: center;
            color: #555;
            margin: 0 0 4pt 0;
        }
        
        p.contact {
            font-size: 9pt;
            text-align: center;
            color: #666;
            margin: 0 0 16pt 0;
        }
        
        h2 {
            font-size: 12pt;
            font-weight: bold;
            color: #000;
            border-bottom: 2px solid #000;
            padding-bottom: 4pt;
            margin: 14pt 0 10pt 0;
        }
        
        .item-date {
            color: #4361ee;
            font-weight: 500;
        }
        """
        
        # Left-Right 模板 - 标题背景色
        elif template_id == "left-right":
            return base_css + """
        /* Left-Right Template - 标题背景色 */
        h1.name {
            font-size: 26pt;
            font-weight: 700;
            text-align: center;
            margin: 0 0 8pt 0;
            color: #2d3436;
            background: linear-gradient(135deg, #a29bfe 0%, #6c5ce7 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        p.title {
            font-size: 12pt;
            text-align: center;
            color: #6c5ce7;
            margin: 0 0 4pt 0;
            font-weight: 500;
        }
        
        p.contact {
            font-size: 9pt;
            text-align: center;
            color: #636e72;
            margin: 0 0 20pt 0;
            padding: 8pt;
            background: #f8f9fa;
            border-radius: 4pt;
        }
        
        h2 {
            font-size: 11pt;
            font-weight: 600;
            color: #fff;
            background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
            padding: 8pt 14pt;
            margin: 16pt 0 12pt 0;
            border-radius: 0 20pt 20pt 0;
            display: inline-block;
            min-width: 40%;
        }
        
        .item {
            border-left: 3px solid #a29bfe;
            padding-left: 12pt;
            margin-left: 4pt;
        }
        
        .item-title {
            color: #2d3436;
        }
        
        .item-date {
            color: #6c5ce7;
        }
        """
        
        # Timeline 模板 - 时间线风格（参考 Magic Resume TimelineTemplate.tsx）
        elif template_id == "timeline":
            return base_css + """
        /* Timeline Template - 时间线风格 */
        h1.name {
            font-size: 22pt;
            font-weight: 700;
            text-align: right;
            margin: 0 0 6pt 0;
            color: #18181b;
        }
        
        p.title {
            font-size: 11pt;
            text-align: right;
            color: #64748b;
            margin: 0 0 4pt 0;
        }
        
        p.contact {
            font-size: 9pt;
            text-align: right;
            color: #64748b;
            margin: 0 0 20pt 0;
            border-bottom: 2px solid #18181b;
            padding-bottom: 10pt;
        }
        
        h2 {
            font-size: 11pt;
            font-weight: 600;
            color: #18181b;
            background: #f1f5f9;
            padding: 6pt 12pt;
            margin: 14pt 0 12pt 0;
            border-left: 4px solid #18181b;
        }
        
        /* 时间线容器 */
        .timeline-section {
            position: relative;
            padding-left: 20pt;
            margin-left: 6pt;
        }
        
        .timeline-section::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 2px;
            background: #e2e8f0;
        }
        
        /* 时间线条目 */
        .timeline-item {
            position: relative;
            padding-left: 16pt;
            margin-bottom: 14pt;
        }
        
        .timeline-dot {
            position: absolute;
            left: -24pt;
            top: 4pt;
            width: 10pt;
            height: 10pt;
            border-radius: 50%;
            background: #18181b;
        }
        
        .timeline-content {
            padding-left: 0;
        }
        
        .timeline-item .item-header {
            display: flex;
            flex-direction: row;
            gap: 12pt;
            margin-bottom: 4pt;
        }
        
        .timeline-item .item-date {
            color: #18181b;
            font-weight: 600;
            white-space: nowrap;
        }
        
        .timeline-item .item-title {
            color: #334155;
            font-weight: 500;
        }
        
        .timeline-item .item-content {
            margin-top: 4pt;
        }
        
        /* 兼容旧的 .item 结构 */
        .item {
            position: relative;
            padding-left: 20pt;
            border-left: 2px solid #e2e8f0;
            margin-left: 6pt;
        }
        
        .item::before {
            content: "";
            position: absolute;
            left: -5pt;
            top: 3pt;
            width: 8pt;
            height: 8pt;
            background: #18181b;
            border-radius: 50%;
        }
        """
        
        # 默认使用 classic
        return self._get_pdf_css("classic")

    def _build_magic_resume(self, request: GenerateRequest) -> MagicResumeBuilder:
        """构建 Magic Resume"""
        builder = MagicResumeBuilder(template_id=request.template_id)
        
        # 1. 设置基本信息
        if request.basic_info:
            builder.set_basic_info(**request.basic_info)
        else:
            # 从 candidate_name 推断
            builder.set_basic_info(name=request.candidate_name)
        
        # 2. 添加教育经历
        for edu in request.education:
            builder.add_education(**edu)
        
        # 3. 添加工作经历
        for exp in request.experience:
            builder.add_experience(**exp)
        
        # 4. 添加项目经历
        for proj in request.projects:
            builder.add_project(**proj)
        
        # 5. 设置技能
        if request.skills:
            builder.set_skills(request.skills)
        elif request.markdown_text:
            # 从 Markdown 中提取技能部分
            skills = self._extract_skills_from_markdown(request.markdown_text)
            if skills:
                builder.set_skills(skills)
        
        # 如果没有结构化数据，从 Markdown 解析
        if not request.education and not request.experience and not request.projects:
            self._parse_markdown_to_builder(request.markdown_text, builder, request.candidate_name)
        
        return builder

    def _parse_markdown_to_builder(
        self, 
        markdown_text: str, 
        builder: MagicResumeBuilder,
        candidate_name: str
    ):
        """
        从 Markdown 解析内容到 builder
        
        支持多种格式:
        1. ### 标题 | 日期 | 详情  (单行格式)
        2. ### 标题
           日期 | 学位 | 专业   (分行格式)
        """
        lines = markdown_text.split("\n")
        current_section = None
        current_content = []
        current_item = {}
        pending_title = None  # 暂存的 ### 标题
        
        # 预处理：从 Markdown 提取基本信息
        basic_info = {"name": candidate_name, "title": "", "email": "", "phone": "", "location": ""}
        header_processed = False
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 提取姓名 (# 开头，单个 #)
            if line_stripped.startswith("# ") and not line_stripped.startswith("## "):
                basic_info["name"] = line_stripped.lstrip("#").strip()
                continue
            
            # 提取职位 (## 开头，在模块标题之前)
            if line_stripped.startswith("## ") and not header_processed:
                title_text = line_stripped.lstrip("#").strip()
                # 检查是否是模块标题
                title_lower = title_text.lower()
                if any(k in title_lower for k in ["教育", "工作", "项目", "技能", "经历", "education", "experience", "project", "skill"]):
                    header_processed = True
                else:
                    basic_info["title"] = title_text
                    continue
            
            # 提取联系方式 (包含 邮箱/电话/地址 关键词)
            if not header_processed and ("邮箱" in line_stripped or "电话" in line_stripped or "地址" in line_stripped or "@" in line_stripped):
                parts = [p.strip() for p in line_stripped.replace("：", ":").split("|")]
                for part in parts:
                    if "邮箱" in part or "@" in part:
                        basic_info["email"] = part.replace("邮箱:", "").replace("邮箱：", "").strip()
                    elif "电话" in part:
                        basic_info["phone"] = part.replace("电话:", "").replace("电话：", "").strip()
                    elif "地址" in part or "所在地" in part:
                        basic_info["location"] = part.replace("地址:", "").replace("地址：", "").replace("所在地:", "").strip()
                continue
        
        # 设置基本信息
        builder.set_basic_info(**basic_info)
        
        for line in lines:
            line = line.strip()
            
            # 检测模块标题 (## 开头)
            if line.startswith("## ") and not line.startswith("### "):
                # 保存上一个条目
                self._save_current_item(builder, current_section, current_item, current_content)
                current_content = []
                current_item = {}
                pending_title = None
                
                # 检测新模块
                title = line.lstrip("#").strip()
                title_lower = title.lower()
                
                # 注意：检测顺序很重要，更具体的模式放在前面
                if any(k in title_lower for k in ["项目", "project"]):
                    current_section = "projects"
                elif any(k in title_lower for k in ["教育", "education", "学历"]):
                    current_section = "education"
                elif any(k in title_lower for k in ["工作", "experience", "职业"]):
                    current_section = "experience"
                elif "经历" in title_lower and current_section is None:
                    current_section = "experience"
                elif any(k in title_lower for k in ["技能", "skill"]):
                    current_section = "skills"
                elif any(k in title_lower for k in ["简介", "summary", "profile", "about"]):
                    current_section = "summary"
                else:
                    current_section = "other"
            
            # 检测条目标题 (### 开头)
            elif line.startswith("### "):
                # 保存上一个条目
                self._save_current_item(builder, current_section, current_item, current_content)
                current_content = []
                current_item = {}
                
                title_text = line.lstrip("#").strip()
                
                # 检查是否是单行格式 (### 标题 | 日期 | 详情)
                if "|" in title_text:
                    parts = [p.strip() for p in title_text.split("|")]
                    current_item = self._parse_item_parts(current_section, parts)
                    pending_title = None
                else:
                    # 分行格式，暂存标题
                    pending_title = title_text
            
            # 检测分行格式的第二行（包含 | 的非标题行）
            elif pending_title and "|" in line and not line.startswith("#"):
                parts = [p.strip() for p in line.split("|")]
                current_item = self._parse_item_parts(current_section, [pending_title] + parts)
                pending_title = None
                    
            # 兼容 **标题** 格式
            elif line.startswith("**") and "|" in line and line.endswith("**"):
                self._save_current_item(builder, current_section, current_item, current_content)
                current_content = []
                
                title_text = line.strip("*").strip()
                parts = [p.strip() for p in title_text.split("|")]
                current_item = self._parse_item_parts(current_section, parts)
                pending_title = None
                    
            elif line.startswith("-") or (line.startswith("*") and not line.startswith("**")):
                # 列表项
                content = line[1:].strip().lstrip("*").strip()
                if content:
                    current_content.append(content)
            elif line and current_section == "skills":
                # 技能部分的非列表内容
                current_content.append(line)
        
        # 保存最后一个条目
        self._save_current_item(builder, current_section, current_item, current_content)

    def _parse_item_parts(self, section: Optional[str], parts: List[str]) -> Dict[str, Any]:
        """
        根据模块类型解析条目各字段
        
        智能识别字段类型（日期、职位、专业等），而不是依赖固定顺序
        """
        import re
        
        def is_date(s: str) -> bool:
            """判断是否为日期格式"""
            date_patterns = [
                r'\d{4}',  # 年份
                r'至今|present|current',
                r'\d{1,2}月|\d{1,2}/\d{4}',
            ]
            return any(re.search(p, s, re.I) for p in date_patterns)
        
        def is_degree(s: str) -> bool:
            """判断是否为学历"""
            degrees = ['本科', '硕士', '博士', '学士', 'bachelor', 'master', 'phd', 'mba', '专科', '高中']
            return any(d in s.lower() for d in degrees)
        
        if section == "experience":
            # 工作经历: 公司 | 职位 | 日期 (顺序可能变化)
            result = {"company": parts[0] if parts else "", "position": "", "date": ""}
            for p in parts[1:]:
                if is_date(p) and not result["date"]:
                    result["date"] = p
                elif not result["position"]:
                    result["position"] = p
            return result
            
        elif section == "projects":
            # 项目经历: 项目名 | 角色 | 日期
            result = {"name": parts[0] if parts else "", "role": "", "date": ""}
            for p in parts[1:]:
                if is_date(p) and not result["date"]:
                    result["date"] = p
                elif not result["role"]:
                    result["role"] = p
            return result
            
        elif section == "education":
            # 教育经历: 学校 | 日期 | 专业 | 学历 (顺序可能变化)
            result = {"school": parts[0] if parts else "", "date": "", "major": "", "degree": ""}
            for p in parts[1:]:
                if is_date(p) and not result["date"]:
                    result["date"] = p
                elif is_degree(p) and not result["degree"]:
                    result["degree"] = p
                elif not result["major"]:
                    result["major"] = p
            return result
            
        return {}

    def _save_current_item(
        self,
        builder: MagicResumeBuilder,
        section: Optional[str],
        item: Dict,
        content: List[str]
    ):
        """保存当前条目到 builder"""
        if not section or not (item or content):
            return
        
        content_str = "\n".join([f"- {c}" for c in content if c])
        
        if section == "experience" and item:
            builder.add_experience(
                company=item.get("company", ""),
                position=item.get("position", ""),
                date=item.get("date", ""),
                details=content_str
            )
        elif section == "projects" and item:
            builder.add_project(
                name=item.get("name", ""),
                role=item.get("role", ""),
                date=item.get("date", ""),
                description=content_str
            )
        elif section == "education" and item:
            # 解析日期范围（如 "2018-2022" 或 "2018 - 2022"）
            date_str = item.get("date", "")
            start_date, end_date = "", ""
            if date_str:
                import re
                # 匹配 "2018-2022" 或 "2018 - 2022" 格式
                match = re.match(r'(\d{4})\s*[-–—]\s*(\d{4}|至今|present|current)', date_str, re.I)
                if match:
                    start_date = match.group(1)
                    end_date = match.group(2)
                else:
                    start_date = date_str  # 单个日期作为 start_date
            
            builder.add_education(
                school=item.get("school", ""),
                degree=item.get("degree", ""),
                major=item.get("major", ""),
                start_date=start_date,
                end_date=end_date,
                description=content_str
            )
        elif section == "skills" and content:
            builder.set_skills(content_str)

    def _extract_skills_from_markdown(self, markdown_text: str) -> str:
        """从 Markdown 中提取技能部分"""
        lines = markdown_text.split("\n")
        in_skills = False
        skill_lines = []
        
        for line in lines:
            if any(k in line.lower() for k in ["技能", "skill"]) and line.startswith("#"):
                in_skills = True
                continue
            elif line.startswith("#") and in_skills:
                break
            elif in_skills:
                skill_lines.append(line)
        
        return "\n".join(skill_lines)

    def _render_latex(self, request: GenerateRequest) -> str:
        """渲染 LaTeX 模板"""
        escaped = self._escape_latex(request.markdown_text)
        return f"""\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{hyperref}}
\\usepackage{{titlesec}}
\\usepackage{{enumitem}}
\\usepackage{{fontspec}}
\\setmainfont{{SimSun}}
\\titleformat{{\\section}}{{\\large\\bfseries}}{{}}{{0em}}{{}}
\\setlist[itemize]{{noitemsep, topsep=0pt}}
\\begin{{document}}
\\begin{{center}}
{{\\LARGE {request.candidate_name}}}\\\\
\\end{{center}}
\\vspace{{0.5em}}
{escaped}
\\end{{document}}
"""

    def _escape_latex(self, text: str) -> str:
        """转义 LaTeX 特殊字符"""
        replacements = {
            "&": "\\&",
            "%": "\\%",
            "$": "\\$",
            "#": "\\#",
            "_": "\\_",
            "{": "\\{",
            "}": "\\}",
            "~": "\\textasciitilde{}",
            "^": "\\textasciicircum{}",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        
        lines = []
        for line in text.splitlines():
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                lines.append(f"\\section*{{{title}}}")
            elif line.startswith("-"):
                if not lines or not lines[-1].startswith("\\begin{itemize}"):
                    lines.append("\\begin{itemize}")
                lines.append(f"\\item {line[1:].strip()}")
            else:
                if lines and lines[-1].startswith("\\item"):
                    lines.append("\\end{itemize}")
                if line.strip():
                    lines.append(line + "\\\\")
        
        if lines and lines[-1].startswith("\\item"):
            lines.append("\\end{itemize}")
        
        return "\n".join(lines)

    def _compile_pdf(self, tex_path: Path, output_dir: Path) -> None:
        """编译 LaTeX 生成 PDF"""
        try:
            subprocess.run(
                ["xelatex", "-interaction=nonstopmode", tex_path.name],
                cwd=str(output_dir),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            try:
                subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", tex_path.name],
                    cwd=str(output_dir),
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("LaTeX (xelatex/pdflatex) is required to generate PDF.") from exc
