"""
AILinux Markdown Renderer
=========================

Converts Markdown to styled HTML for QTextEdit display.
Supports: Headers, Bold, Italic, Code blocks, Lists, Links
"""
import re
import logging
from typing import Optional

try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

logger = logging.getLogger("ailinux.markdown")


# CSS Styles for Markdown elements
MARKDOWN_CSS = '''
<style>
    .md-content {
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
        line-height: 1.6;
        color: #e0e0e0;
    }
    .md-content h1 {
        font-size: 24px;
        font-weight: bold;
        color: #60a5fa;
        margin: 16px 0 8px 0;
        padding-bottom: 4px;
        border-bottom: 2px solid #3b82f6;
    }
    .md-content h2 {
        font-size: 20px;
        font-weight: bold;
        color: #60a5fa;
        margin: 14px 0 6px 0;
        padding-bottom: 3px;
        border-bottom: 1px solid #3b82f6;
    }
    .md-content h3 {
        font-size: 17px;
        font-weight: bold;
        color: #93c5fd;
        margin: 12px 0 4px 0;
    }
    .md-content h4 {
        font-size: 15px;
        font-weight: bold;
        color: #93c5fd;
        margin: 10px 0 4px 0;
    }
    .md-content p {
        margin: 8px 0;
    }
    .md-content strong, .md-content b {
        font-weight: bold;
        color: #f0f0f0;
    }
    .md-content em, .md-content i {
        font-style: italic;
        color: #d4d4d4;
    }
    .md-content code {
        background: #1e1e1e;
        color: #4ade80;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 12px;
    }
    .md-content pre {
        background: #1a1a2e;
        border: 1px solid #333;
        border-radius: 6px;
        padding: 12px;
        margin: 10px 0;
        overflow-x: auto;
    }
    .md-content pre code {
        background: transparent;
        padding: 0;
        color: #e0e0e0;
        display: block;
        white-space: pre;
    }
    .md-content ul, .md-content ol {
        margin: 8px 0 8px 20px;
        padding-left: 10px;
    }
    .md-content li {
        margin: 4px 0;
    }
    .md-content blockquote {
        border-left: 4px solid #3b82f6;
        margin: 10px 0;
        padding: 8px 16px;
        background: #1a1a2e;
        color: #a0a0a0;
    }
    .md-content a {
        color: #60a5fa;
        text-decoration: none;
    }
    .md-content hr {
        border: none;
        border-top: 1px solid #444;
        margin: 16px 0;
    }
    .md-content table {
        border-collapse: collapse;
        margin: 10px 0;
        width: 100%;
    }
    .md-content th, .md-content td {
        border: 1px solid #444;
        padding: 8px 12px;
        text-align: left;
    }
    .md-content th {
        background: #2a2a3e;
        font-weight: bold;
    }
</style>
'''


class MarkdownRenderer:
    """Renders Markdown to styled HTML for Qt widgets."""
    
    def __init__(self):
        self.md = None
        if HAS_MARKDOWN:
            self.md = markdown.Markdown(
                extensions=[
                    'fenced_code',
                    'tables',
                    'nl2br',
                    'sane_lists',
                ]
            )
    
    def render(self, text: str) -> str:
        """Convert Markdown text to styled HTML."""
        if not text:
            return ""
        
        if self.md:
            self.md.reset()
            html = self.md.convert(text)
        else:
            html = self._fallback_render(text)
        
        return f'{MARKDOWN_CSS}<div class="md-content">{html}</div>'
    
    def _fallback_render(self, text: str) -> str:
        """Basic Markdown rendering without library"""
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        
        # Headers
        text = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        
        # Bold and Italic
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        
        # Code blocks
        text = re.sub(
            r'```(\w*)\n(.*?)```',
            r'<pre><code>\2</code></pre>',
            text,
            flags=re.DOTALL
        )
        
        # Inline code
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # Lists
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        
        # Line breaks
        text = text.replace('\n\n', '</p><p>')
        text = text.replace('\n', '<br>')
        
        return f'<p>{text}</p>'
    
    def extract_code_blocks(self, text: str) -> list:
        """Extract code blocks from markdown text."""
        blocks = []
        pattern = r'```(\w*)\n(.*?)```'
        
        for match in re.finditer(pattern, text, re.DOTALL):
            blocks.append({
                "lang": match.group(1) or "text",
                "code": match.group(2).strip()
            })
        
        return blocks


# Singleton instance
_renderer = None

def get_renderer() -> MarkdownRenderer:
    """Get singleton renderer instance"""
    global _renderer
    if _renderer is None:
        _renderer = MarkdownRenderer()
    return _renderer


def render_markdown(text: str) -> str:
    """Convenience function to render markdown"""
    return get_renderer().render(text)
